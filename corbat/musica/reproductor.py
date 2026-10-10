import ctypes
import difflib
import logging
import os
import re
import subprocess
import time
import unicodedata

from corbat import registro  # noqa: F401
from corbat.musica import spotify_api

VK_SIGUIENTE = 0xB0
VK_ANTERIOR = 0xB1
VK_PLAY_PAUSA = 0xB3

TITULOS_GENERICOS = {"", "spotify", "spotify free", "spotify premium"}
PATRON_TRACK = re.compile(r"open\.spotify\.com/(?:intl-[a-z]+/)?track/([A-Za-z0-9]{22})")


PARECIDO_SEGURO = 0.8  # sin todas las palabras y por debajo de esto, Corbat avisa que no está seguro


# ---------- Búsqueda con la API ----------

def _normalizar(texto):
    texto = unicodedata.normalize("NFD", texto.lower())
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    texto = re.sub(r"[^\w\s]", " ", texto)
    return re.sub(r"\s+", " ", texto).strip()


def _separar_cancion_artista(texto):
    """'Virtual Diva de Don Omar' -> ('Virtual Diva', 'Don Omar'); None si no hay 'de'."""
    partes = re.split(r"\s+(?:de|del|by)\s+", texto.strip(), maxsplit=1, flags=re.IGNORECASE)
    if len(partes) == 2 and partes[0].strip() and partes[1].strip():
        return partes[0].strip(), partes[1].strip()
    return None


def _puntaje(consulta, nombre, artistas):
    """Qué tanto se parece una canción a lo pedido.

    Devuelve (puntaje de 0 a 1, seguro, pidieron_artista).
    """
    pedido = _normalizar(consulta)
    titulo = _normalizar(nombre)
    completo = _normalizar(f"{nombre} {artistas}")

    parecido_titulo = max(
        difflib.SequenceMatcher(None, pedido, titulo).ratio(),
        difflib.SequenceMatcher(None, pedido, completo).ratio(),
    )
    parecido_artista = max(
        (difflib.SequenceMatcher(None, pedido, _normalizar(a)).ratio() for a in artistas.split(", ")),
        default=0.0,
    )
    parecido = max(parecido_titulo, parecido_artista)

    palabras = set(pedido.split())
    cobertura = len(palabras & set(completo.split())) / len(palabras) if palabras else 0.0

    seguro = cobertura == 1.0 or parecido >= PARECIDO_SEGURO
    pidieron_artista = parecido_artista >= 0.7 and parecido_artista > parecido_titulo
    return max(parecido, cobertura * 0.95), seguro, pidieron_artista


def _elegir_cancion(texto):
    """Busca en Spotify y devuelve (uris, nombre, artistas, puntaje, seguro), o None.

    `uris` trae la canción elegida y, si pidieron un artista ("algo de X"),
    otras canciones suyas para que siga sonando música.
    """
    partes = _separar_cancion_artista(texto)
    variantes = []

    if partes:
        variantes.append(f'track:"{partes[0]}" artist:"{partes[1]}"')
        pedido = f"{partes[0]} {partes[1]}"
    else:
        pedido = texto
    variantes.append(texto)

    mejor = None
    for numero, consulta in enumerate(variantes):
        try:
            candidatos = spotify_api.buscar_pistas(consulta)
        except spotify_api.ErrorSpotify:
            if numero == len(variantes) - 1:
                raise
            continue  # la búsqueda con filtros falló: se prueba la búsqueda simple

        puntuados = [(*_puntaje(pedido, n, a), u, n, a) for u, n, a in candidatos]
        logging.info(
            "Búsqueda de música %r: %s",
            consulta,
            [(round(p, 2), n, a) for p, _, _, _, n, a in puntuados[:3]],
        )

        for puntaje, seguro, artista, uri, nombre, artistas in puntuados:
            if mejor is None or puntaje > mejor[3]:  # en empate gana el que Spotify puso antes
                mejor = (uri, nombre, artistas, puntaje, seguro, artista, candidatos)

        if mejor and mejor[4]:
            break

    if mejor is None:
        return None

    uri, nombre, artistas, puntaje, seguro, pidieron_artista, candidatos = mejor
    uris = [uri]
    if pidieron_artista:
        principal = artistas.split(", ")[0]
        for otra, _, otros in candidatos:
            if otra != uri and principal in otros.split(", ") and len(uris) < 5:
                uris.append(otra)

    return uris, nombre, artistas, puntaje, seguro


# ---------- Método alternativo (sin API) ----------

def _pulsar_tecla(codigo: int) -> None:
    ctypes.windll.user32.keybd_event(codigo, 0, 0, 0)
    ctypes.windll.user32.keybd_event(codigo, 0, 2, 0)


def _titulo_spotify() -> str:
    comando = (
        "[Console]::OutputEncoding=[Text.Encoding]::UTF8;"
        "(Get-Process Spotify -ErrorAction SilentlyContinue | "
        "Where-Object {$_.MainWindowTitle} | "
        "Select-Object -First 1).MainWindowTitle"
    )
    try:
        resultado = subprocess.run(
            ["powershell", "-NoProfile", "-Command", comando],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=8,
        )
    except (subprocess.TimeoutExpired, OSError):
        return ""
    return resultado.stdout.strip()


def _estado():
    """Devuelve (sonando, titulo). sonando es None si no se puede saber."""
    titulo = _titulo_spotify()
    if not titulo:
        return None, ""
    if titulo.lower() in TITULOS_GENERICOS:
        return False, ""
    return True, titulo


def _buscar_cancion_web(busqueda: str):
    consulta = f"site:open.spotify.com/track {busqueda}"
    try:
        from ddgs import DDGS

        resultados = DDGS().text(consulta, max_results=8)
    except Exception as error:
        logging.warning("reproducir_musica: búsqueda web falló (%s)", error)
        return None

    for resultado in resultados or []:
        encontrado = PATRON_TRACK.search(resultado.get("href", ""))
        if encontrado:
            return encontrado.group(1)
    return None


def _esperar_reproduccion(titulo_anterior: str, limite: float = 12.0):
    inicio = time.monotonic()
    pulsado = False

    while time.monotonic() - inicio < limite:
        sonando, titulo = _estado()

        if sonando and titulo != titulo_anterior:
            return titulo

        if sonando is False and not pulsado and time.monotonic() - inicio > 3:
            _pulsar_tecla(VK_PLAY_PAUSA)
            pulsado = True

        time.sleep(0.4)

    return None


def _reproducir_sin_api(texto: str) -> str:
    identificador = _buscar_cancion_web(texto)

    if identificador is None:
        os.startfile(f"spotify:search:{texto}")
        logging.info("reproducir_musica: sin resultado, se abrió la búsqueda (%s)", texto)
        return f"No encontré esa canción directamente. Abrí la búsqueda de {texto} en Spotify."

    _, titulo_anterior = _estado()
    os.startfile(f"spotify:track:{identificador}:play")

    titulo = _esperar_reproduccion(titulo_anterior)
    logging.info("reproducir_musica: %s -> %s", texto, titulo or "sin confirmar")

    if titulo:
        return f"Reproduciendo {titulo}."
    return f"Abrí {texto} en Spotify, pero no pude confirmar que esté sonando."


def _sonando_api():
    """True o False según Spotify, o None si no se pudo saber."""
    try:
        actual = spotify_api.actual()
    except spotify_api.ErrorSpotify:
        return None
    return bool(actual and actual[2])


# ---------- Herramientas ----------

def reproducir_musica(busqueda: str) -> str:
    """Busca una canción en Spotify y la reproduce.

    Args:
        busqueda: Nombre de la canción y, si se sabe, el artista. Por ejemplo Virtual Diva Don Omar.

    Returns:
        Resultado de la acción.
    """
    texto = busqueda.strip()
    if not texto:
        return "No me dijiste qué canción reproducir."

    if spotify_api.configurado():
        try:
            elegida = _elegir_cancion(texto)
            if elegida is None:
                return f"No encontré ninguna canción que coincida con {texto}."

            uris, nombre, artistas, puntaje, seguro = elegida

            if not seguro:
                # Si lo pedido se parece mucho al nombre de una de tus playlists, es esa.
                lista = _playlist_parecida(texto)
                if lista:
                    return _tocar_playlist(*lista)

            confirmado = spotify_api.reproducir_pista(uris, nombre)
            logging.info(
                "reproducir_musica (API): %s - %s (coincidencia %.2f, %s, %s, %d canciones)",
                nombre,
                artistas,
                puntaje,
                "segura" if seguro else "dudosa",
                "sonando" if confirmado else "SIN CONFIRMAR",
                len(uris),
            )

            if not confirmado:
                return (
                    f"Le pedí a Spotify {nombre} de {artistas}, pero no pude confirmar que esté "
                    "sonando. Revisa la aplicación."
                )
            if not seguro:
                return (
                    "No estoy seguro de que sea lo que pediste, "
                    f"pero reproduje {nombre} de {artistas}."
                )
            return f"Reproduciendo {nombre} de {artistas}."
        except spotify_api.ErrorSpotify as error:
            logging.warning("reproducir_musica: la API falló (%s); uso el método alternativo", error)

    return _reproducir_sin_api(texto)


def _elegir_playlist(nombre):
    """Devuelve ((uri, nombre, puntaje) | None, todas las playlists)."""
    playlists = spotify_api.listar_playlists()
    pedido = _normalizar(nombre)
    palabras = set(pedido.split())

    mejor = None
    for uri, titulo in playlists:
        norm = _normalizar(titulo)
        parecido = difflib.SequenceMatcher(None, pedido, norm).ratio()
        cobertura = len(palabras & set(norm.split())) / len(palabras) if palabras else 0.0
        puntaje = max(parecido, cobertura * 0.9)
        if mejor is None or puntaje > mejor[2]:
            mejor = (uri, titulo, puntaje)

    logging.info("Búsqueda de playlist %r: %s", nombre, mejor)
    return mejor, playlists


def _hablable(titulo):
    """Quita emojis y símbolos del nombre para que la voz no los lea."""
    limpio = re.sub(r"[^\w\s&'-]", "", titulo).strip()
    return limpio or titulo


def _playlist_parecida(texto):
    try:
        mejor, _ = _elegir_playlist(texto)
    except spotify_api.ErrorSpotify:
        return None
    if mejor and mejor[2] >= 0.85:
        return mejor[0], mejor[1]
    return None


def _tocar_playlist(uri, titulo):
    confirmado = spotify_api.reproducir_contexto(uri)
    logging.info(
        "reproducir_playlist: %s (%s)", titulo, "sonando" if confirmado else "SIN CONFIRMAR"
    )
    if not confirmado:
        return f"Le pedí a Spotify la playlist {_hablable(titulo)}, pero no pude confirmar que esté sonando."
    return f"Reproduciendo tu playlist {_hablable(titulo)}."


def reproducir_playlist(nombre: str) -> str:
    """Reproduce una playlist de la biblioteca del usuario por su nombre.

    Args:
        nombre: Nombre de la playlist, por ejemplo Gym o Para estudiar.

    Returns:
        Resultado de la acción.
    """
    if not spotify_api.configurado():
        return "Spotify no está conectado. Ejecuta python -m corbat.musica.spotify_api una vez."
    if not nombre.strip():
        return "No me dijiste qué playlist reproducir."

    try:
        mejor, playlists = _elegir_playlist(nombre)
        if mejor is None or mejor[2] < 0.6:
            ejemplos = ", ".join(_hablable(titulo) for _, titulo in playlists[:5])
            if ejemplos:
                return f"No encontré una playlist llamada {nombre}. Algunas de las tuyas son {ejemplos}."
            return "No encontré playlists en tu biblioteca."
        return _tocar_playlist(mejor[0], mejor[1])
    except spotify_api.ErrorSpotify as error:
        logging.warning("reproducir_playlist: %s", error)
        return str(error)


def reproducir_me_gusta() -> str:
    """Reproduce las canciones de Tus me gusta (canciones que le gustan al usuario) en Spotify.

    Returns:
        Resultado de la acción.
    """
    if not spotify_api.configurado():
        return "Spotify no está conectado. Ejecuta python -m corbat.musica.spotify_api una vez."

    try:
        try:
            uris = spotify_api.canciones_me_gusta()
        except spotify_api.ErrorSpotify as error:
            if error.estado == 403 and "permiso" in str(error):
                raise
            logging.warning("Tus me gusta: no pude leer la lista (%s); uso la colección", error)
            uris = None

        if uris is None:
            contexto = f"spotify:user:{spotify_api.id_usuario()}:collection"
            confirmado = spotify_api.reproducir_contexto(contexto)
        elif not uris:
            return "No tienes canciones en Tus me gusta."
        else:
            confirmado = spotify_api.reproducir_pista(uris)
    except spotify_api.ErrorSpotify as error:
        logging.warning("reproducir_me_gusta: %s", error)
        return str(error)

    logging.info("reproducir_me_gusta: %s", "sonando" if confirmado else "SIN CONFIRMAR")
    if not confirmado:
        return "Le pedí a Spotify tus canciones que te gustan, pero no pude confirmar que estén sonando."
    return "Reproduciendo tus canciones que te gustan."


def pausar_musica() -> str:
    """Pausa la música que está sonando.

    Returns:
        Resultado de la acción.
    """
    if spotify_api.configurado():
        try:
            spotify_api.pausar()
            logging.info("pausar_musica (API)")
            return "Música en pausa."
        except spotify_api.ErrorSpotify as error:
            if error.estado == 403 and _sonando_api() is False:
                return "La música ya está en pausa."
            logging.warning("pausar_musica: la API falló (%s); uso teclas multimedia", error)

    sonando, _ = _estado()
    if sonando is False:
        return "La música ya está en pausa."

    _pulsar_tecla(VK_PLAY_PAUSA)
    logging.info("pausar_musica")
    return "Música en pausa."


def continuar_musica() -> str:
    """Reanuda la música que estaba en pausa.

    Returns:
        Resultado de la acción.
    """
    if spotify_api.configurado():
        try:
            spotify_api.reanudar()
            logging.info("continuar_musica (API)")
            return "Reanudando la música."
        except spotify_api.ErrorSpotify as error:
            if error.estado == 403 and _sonando_api() is True:
                return "La música ya está sonando."
            logging.warning("continuar_musica: la API falló (%s); uso teclas multimedia", error)

    sonando, titulo = _estado()
    if sonando:
        return f"Ya está sonando {titulo}."

    _pulsar_tecla(VK_PLAY_PAUSA)
    logging.info("continuar_musica")
    return "Reanudando la música."


def siguiente_cancion() -> str:
    """Pasa a la siguiente canción.

    Returns:
        Resultado de la acción.
    """
    if spotify_api.configurado():
        try:
            spotify_api.siguiente()
            logging.info("siguiente_cancion (API)")
            return "Siguiente canción."
        except spotify_api.ErrorSpotify as error:
            logging.warning("siguiente_cancion: la API falló (%s); uso teclas multimedia", error)

    _pulsar_tecla(VK_SIGUIENTE)
    logging.info("siguiente_cancion")
    return "Siguiente canción."


def cancion_anterior() -> str:
    """Vuelve a la canción anterior. Si la actual lleva más de unos segundos, la reinicia.

    Returns:
        Resultado de la acción.
    """
    if spotify_api.configurado():
        try:
            spotify_api.anterior()
            logging.info("cancion_anterior (API)")
            return "Canción anterior."
        except spotify_api.ErrorSpotify as error:
            logging.warning("cancion_anterior: la API falló (%s); uso teclas multimedia", error)

    _pulsar_tecla(VK_ANTERIOR)
    logging.info("cancion_anterior")
    return "Canción anterior."


def cancion_actual() -> str:
    """Dice qué canción está sonando en Spotify.

    Returns:
        Título y artista de la canción actual.
    """
    if spotify_api.configurado():
        try:
            actual = spotify_api.actual()
            if actual is None:
                return "No hay nada sonando en este momento."
            nombre, artistas, sonando = actual
            if sonando:
                return f"Está sonando {nombre} de {artistas}."
            return f"{nombre} de {artistas} está en pausa."
        except spotify_api.ErrorSpotify as error:
            logging.warning("cancion_actual: la API falló (%s); leo la ventana", error)

    sonando, titulo = _estado()
    if sonando:
        return f"Está sonando {titulo}."
    if sonando is False:
        return "No hay nada sonando en este momento."
    return "No pude ver Spotify. Puede que esté cerrado o minimizado en la bandeja."