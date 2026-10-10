import base64
import hashlib
import json
import logging
import os
import secrets
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

import httpx

import registro  # noqa: F401

CARPETA = Path(__file__).parent
ARCHIVO_CONFIG = CARPETA / "spotify_config.json"
ARCHIVO_TOKEN = CARPETA / "spotify_token.json"

PUERTO = 8888
REDIRECT_URI = f"http://127.0.0.1:{PUERTO}/callback"
SCOPES = (
    "user-read-playback-state user-modify-playback-state user-read-currently-playing "
    "user-library-read playlist-read-private playlist-read-collaborative"
)
URL_AUTORIZAR = "https://accounts.spotify.com/authorize"
URL_TOKEN = "https://accounts.spotify.com/api/token"
URL_API = "https://api.spotify.com/v1"
MERCADO = "CO"  # solo canciones que se pueden reproducir en Colombia

_cache = {}


class ErrorSpotify(Exception):
    def __init__(self, mensaje, estado=None):
        super().__init__(mensaje)
        self.estado = estado


def _client_id():
    try:
        datos = json.loads(ARCHIVO_CONFIG.read_text(encoding="utf-8"))
        return datos["client_id"]
    except (OSError, ValueError, KeyError) as error:
        raise ErrorSpotify("Falta el client_id en spotify_config.json.") from error


def configurado():
    return ARCHIVO_CONFIG.exists() and ARCHIVO_TOKEN.exists()


# ---------- Inicio de sesión (una sola vez) ----------

class _Receptor(BaseHTTPRequestHandler):
    codigo = None
    estado = None
    error = None

    def do_GET(self):
        consulta = parse_qs(urlparse(self.path).query)
        _Receptor.codigo = consulta.get("code", [None])[0]
        _Receptor.estado = consulta.get("state", [None])[0]
        _Receptor.error = consulta.get("error", [None])[0]

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(
            "<h2>Listo. Ya puedes cerrar esta pestaña y volver a Corbat.</h2>".encode("utf-8")
        )

    def log_message(self, *args):
        pass


def _guardar_token(datos):
    datos["expira"] = time.time() + datos.get("expires_in", 3600) - 30
    ARCHIVO_TOKEN.write_text(json.dumps(datos), encoding="utf-8")
    _cache["token"] = datos


def iniciar_sesion():
    client_id = _client_id()

    verificador = secrets.token_urlsafe(64)
    desafio = (
        base64.urlsafe_b64encode(hashlib.sha256(verificador.encode()).digest())
        .rstrip(b"=")
        .decode()
    )
    estado = secrets.token_urlsafe(16)

    url = URL_AUTORIZAR + "?" + urlencode(
        {
            "response_type": "code",
            "client_id": client_id,
            "scope": SCOPES,
            "redirect_uri": REDIRECT_URI,
            "code_challenge_method": "S256",
            "code_challenge": desafio,
            "state": estado,
        }
    )

    servidor = HTTPServer(("127.0.0.1", PUERTO), _Receptor)
    servidor.timeout = 180

    print("Abriendo el navegador para autorizar a Corbat en Spotify...")
    webbrowser.open(url)
    servidor.handle_request()
    servidor.server_close()

    if _Receptor.error or not _Receptor.codigo:
        raise ErrorSpotify(f"No se autorizó el acceso ({_Receptor.error or 'sin respuesta'}).")
    if _Receptor.estado != estado:
        raise ErrorSpotify("La respuesta de Spotify no coincide con la solicitud.")

    respuesta = httpx.post(
        URL_TOKEN,
        data={
            "grant_type": "authorization_code",
            "code": _Receptor.codigo,
            "redirect_uri": REDIRECT_URI,
            "client_id": client_id,
            "code_verifier": verificador,
        },
        timeout=10,
    )
    if respuesta.status_code != 200:
        raise ErrorSpotify(f"Spotify rechazó el inicio de sesión: {respuesta.text}")

    _guardar_token(respuesta.json())
    print("Listo: Corbat ya está conectado a tu cuenta de Spotify.")


# ---------- Tokens ----------

def _cargar_token():
    if "token" in _cache:
        return _cache["token"]
    try:
        _cache["token"] = json.loads(ARCHIVO_TOKEN.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ErrorSpotify(
            "Spotify no está conectado. Ejecuta python spotify_api.py una vez."
        ) from error
    return _cache["token"]


def _renovar():
    token = _cargar_token()
    respuesta = httpx.post(
        URL_TOKEN,
        data={
            "grant_type": "refresh_token",
            "refresh_token": token["refresh_token"],
            "client_id": _client_id(),
        },
        timeout=10,
    )
    if respuesta.status_code != 200:
        logging.warning(
            "Spotify: no se pudo renovar el token -> %s %s",
            respuesta.status_code,
            respuesta.text[:200],
        )
        raise ErrorSpotify(
            "No pude renovar la sesión de Spotify. Ejecuta python spotify_api.py de nuevo."
        )

    datos = respuesta.json()
    datos.setdefault("refresh_token", token["refresh_token"])
    _guardar_token(datos)


def _token_acceso():
    token = _cargar_token()
    if time.time() >= token.get("expira", 0):
        _renovar()
        token = _cargar_token()
    return token["access_token"]


# ---------- Peticiones ----------

def _mensaje_error(respuesta):
    razon = ""
    try:
        error = respuesta.json().get("error")
        if isinstance(error, dict):
            razon = error.get("reason", "")
    except ValueError:
        pass

    if respuesta.status_code == 404 or razon == "NO_ACTIVE_DEVICE":
        return "No hay ningún dispositivo de Spotify activo."
    if razon == "PREMIUM_REQUIRED":
        return "Esta acción requiere Spotify Premium."
    if respuesta.status_code == 429:
        return "Spotify me pidió esperar un momento."
    return f"Spotify respondió con el error {respuesta.status_code}."


def _peticion(metodo, ruta, **kwargs):
    respuesta = None

    for intento in range(2):
        cabeceras = {"Authorization": f"Bearer {_token_acceso()}"}
        try:
            respuesta = httpx.request(
                metodo, URL_API + ruta, headers=cabeceras, timeout=8, **kwargs
            )
        except httpx.HTTPError as error:
            logging.warning("Spotify %s %s: error de conexión (%s)", metodo, ruta, error)
            raise ErrorSpotify("No pude conectarme con Spotify. Revisa tu internet.") from error

        if respuesta.status_code == 401 and intento == 0:
            _renovar()
            continue
        break

    if respuesta.status_code >= 400:
        logging.warning(
            "Spotify %s %s -> %s %s",
            metodo,
            ruta,
            respuesta.status_code,
            respuesta.text[:300],
        )
        raise ErrorSpotify(_mensaje_error(respuesta), respuesta.status_code)

    return respuesta


# ---------- Acciones ----------

def buscar_pistas(consulta, limite=10):
    """Devuelve [(uri, nombre, artistas), ...] en el orden de relevancia de Spotify."""
    respuesta = _peticion(
        "GET",
        "/search",
        params={"q": consulta, "type": "track", "limit": limite, "market": MERCADO},
    )
    items = [i for i in respuesta.json().get("tracks", {}).get("items", []) if i]

    reproducibles = [i for i in items if i.get("is_playable", True)]
    if len(reproducibles) < len(items):
        logging.info(
            "Spotify: descarté %d canción(es) no disponibles en %s",
            len(items) - len(reproducibles),
            MERCADO,
        )
    items = reproducibles

    return [
        (i["uri"], i["name"], ", ".join(a["name"] for a in i.get("artists", [])))
        for i in items
    ]


def buscar_pista(texto):
    """Devuelve (uri, nombre, artistas) de la primera coincidencia, o None."""
    pistas = buscar_pistas(texto, limite=5)
    return pistas[0] if pistas else None


def _buscar_dispositivo():
    """Devuelve el dispositivo (dict) que usará Corbat, o None si no hay ninguno."""
    respuesta = _peticion("GET", "/me/player/devices")
    todos = respuesta.json().get("devices", [])
    logging.info(
        "Dispositivos de Spotify: %s",
        [
            (d.get("name"), d.get("type"), "activo" if d.get("is_active") else "inactivo",
             "restringido" if d.get("is_restricted") else "libre")
            for d in todos
        ],
    )
    dispositivos = [d for d in todos if not d.get("is_restricted")]

    elegido = None
    for d in dispositivos:
        if d.get("type") == "Computer":
            elegido = d
            break
    if elegido is None:
        for d in dispositivos:
            if d.get("is_active"):
                elegido = d
                break
    if elegido is None and dispositivos:
        elegido = dispositivos[0]

    if elegido is not None:
        logging.info("Dispositivo elegido: %s (%s)", elegido.get("name"), elegido.get("type"))
    return elegido


def _elegir_dispositivo():
    dispositivo = _buscar_dispositivo()
    return dispositivo["id"] if dispositivo else None


def _esperar_dispositivo():
    dispositivo = _buscar_dispositivo()

    if dispositivo is None:
        os.startfile("spotify:")  # abre la app y espera a que aparezca como dispositivo
        for _ in range(12):
            time.sleep(1)
            dispositivo = _buscar_dispositivo()
            if dispositivo:
                break

    if dispositivo is None:
        raise ErrorSpotify("No encontré un dispositivo de Spotify. Abre la app de escritorio.")
    return dispositivo


def estado():
    """Devuelve {'uri', 'nombre', 'artistas', 'sonando', 'contexto'}, o None si no hay nada."""
    respuesta = _peticion("GET", "/me/player/currently-playing")

    if respuesta.status_code == 204 or not respuesta.content:
        return None

    datos = respuesta.json()
    item = datos.get("item")
    if not item:
        return None

    return {
        "uri": item.get("uri", ""),
        "nombre": item.get("name", ""),
        "artistas": ", ".join(a["name"] for a in item.get("artists", [])),
        "sonando": bool(datos.get("is_playing")),
        "contexto": (datos.get("context") or {}).get("uri", ""),
    }


def _esperar(condicion, segundos):
    limite = time.monotonic() + segundos
    while True:
        try:
            actual_ = estado()
        except ErrorSpotify:
            actual_ = None

        if actual_ and actual_["sonando"] and condicion(actual_):
            return True
        if time.monotonic() >= limite:
            return False
        time.sleep(0.5)


def _suena(uri, nombre, segundos):
    """Espera hasta `segundos` a que Spotify confirme que esa canción está sonando."""
    return _esperar(
        lambda e: e["uri"] == uri
        or (nombre and e["nombre"].strip().lower() == nombre.strip().lower()),
        segundos,
    )


def _suena_contexto(contexto, segundos):
    return _esperar(lambda e: e["contexto"] == contexto, segundos)


def _abrir_en_app(enlace):
    """Le da la orden directamente a la app de escritorio (despierta el dispositivo inactivo)."""
    logging.info("Abriendo en la app de Spotify: %s", enlace)
    os.startfile(enlace)


def _transferir(dispositivo):
    _peticion("PUT", "/me/player", json={"device_ids": [dispositivo["id"]], "play": False})


MAX_COLA = 20  # canciones que se agregan a la cola después de la primera


def _encolar(dispositivo_id, uris):
    agregadas = 0
    for uri in uris[:MAX_COLA]:
        try:
            _peticion(
                "POST", "/me/player/queue", params={"uri": uri, "device_id": dispositivo_id}
            )
        except ErrorSpotify as error:
            logging.warning("No pude agregar a la cola (%s)", error)
            break
        agregadas += 1
    logging.info("Agregué %d canciones a la cola", agregadas)


def _encolar_en_segundo_plano(dispositivo_id, uris):
    threading.Thread(target=_encolar, args=(dispositivo_id, uris), daemon=True).start()


def reproducir_pista(uris, nombre=""):
    """Reproduce una o varias canciones. Devuelve True si Spotify confirma que suena.

    Si el dispositivo está inactivo, la API de Spotify suele aceptar la orden y no hacer
    nada; por eso en ese caso la orden se le da directamente a la app.
    """
    if isinstance(uris, str):
        uris = [uris]
    primera = uris[0]

    dispositivo = _esperar_dispositivo()

    def enviar():
        _peticion(
            "PUT",
            "/me/player/play",
            params={"device_id": dispositivo["id"]},
            json={"uris": uris},
        )

    if dispositivo.get("is_active"):
        try:
            enviar()
            if _suena(primera, nombre, 3):
                return True
            logging.warning("Spotify aceptó play pero no suena; lo abro directo en la app")
        except ErrorSpotify as error:
            logging.warning("play por la API falló (%s); lo abro directo en la app", error)

    _abrir_en_app(f"spotify:track:{primera.split(':')[-1]}:play")
    if _suena(primera, nombre, 8):
        if len(uris) > 1:
            # Un segundo "play" aquí cortaría la canción: el resto se agrega a la cola.
            _encolar_en_segundo_plano(dispositivo["id"], uris[1:])
        return True

    logging.warning("Sigue sin sonar; transfiero la reproducción y reintento por la API")
    try:
        _transferir(dispositivo)
        time.sleep(1)
        enviar()
    except ErrorSpotify as error:
        logging.warning("Reintento por la API falló (%s)", error)
        return False
    return _suena(primera, nombre, 5)


def reproducir_contexto(contexto):
    """Reproduce una playlist, álbum o colección (spotify:playlist:ID). True si suena."""
    dispositivo = _esperar_dispositivo()

    def enviar():
        _peticion(
            "PUT",
            "/me/player/play",
            params={"device_id": dispositivo["id"]},
            json={"context_uri": contexto},
        )

    if dispositivo.get("is_active"):
        try:
            enviar()
            if _suena_contexto(contexto, 4):
                return True
            logging.warning("Spotify aceptó play pero no suena; lo abro directo en la app")
        except ErrorSpotify as error:
            logging.warning("play por la API falló (%s); lo abro directo en la app", error)

    _abrir_en_app(f"{contexto}:play")
    if _suena_contexto(contexto, 8):
        return True

    logging.warning("Sigue sin sonar; transfiero la reproducción y reintento por la API")
    try:
        _transferir(dispositivo)
        time.sleep(1)
        enviar()
    except ErrorSpotify as error:
        logging.warning("Reintento por la API falló (%s)", error)
        return False
    return _suena_contexto(contexto, 5)


# ---------- Biblioteca (Tus me gusta y playlists) ----------

def tiene_permiso(permiso):
    try:
        return permiso in _cargar_token().get("scope", "").split()
    except ErrorSpotify:
        return False


def _exigir_permiso(permiso):
    if not tiene_permiso(permiso):
        raise ErrorSpotify(
            "Corbat necesita un permiso nuevo de Spotify. "
            "Ejecuta python spotify_api.py una vez para volver a conectarlo.",
            403,
        )


def listar_playlists():
    """Devuelve [(uri, nombre), ...] con las playlists de tu biblioteca."""
    _exigir_permiso("playlist-read-private")
    encontradas = []
    for pagina in range(4):  # hasta 200 playlists
        datos = _peticion(
            "GET", "/me/playlists", params={"limit": 50, "offset": pagina * 50}
        ).json()
        for p in datos.get("items", []):
            if p and p.get("uri") and p.get("name"):
                encontradas.append((p["uri"], p["name"]))
        if not datos.get("next"):
            break
    return encontradas


def canciones_me_gusta(limite=50):
    """Devuelve las URIs de tus últimas canciones de 'Tus me gusta'."""
    _exigir_permiso("user-library-read")
    datos = _peticion(
        "GET", "/me/tracks", params={"limit": limite, "market": MERCADO}
    ).json()
    return [
        i["track"]["uri"]
        for i in datos.get("items", [])
        if i.get("track") and i["track"].get("uri") and i["track"].get("is_playable", True)
    ]


def id_usuario():
    return _peticion("GET", "/me").json()["id"]


def pausar():
    _peticion("PUT", "/me/player/pause")


def reanudar():
    dispositivo = _elegir_dispositivo()
    parametros = {"device_id": dispositivo} if dispositivo else None
    _peticion("PUT", "/me/player/play", params=parametros)


def siguiente():
    _peticion("POST", "/me/player/next")


def anterior():
    _peticion("POST", "/me/player/previous")


def actual():
    """Devuelve (nombre, artistas, sonando), o None si no hay nada."""
    datos = estado()
    if datos is None:
        return None
    return datos["nombre"], datos["artistas"], datos["sonando"]


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "playlists":
        for _, nombre_lista in listar_playlists():
            print(" -", nombre_lista)
        try:
            print("Tus me gusta:", len(canciones_me_gusta()), "canciones leídas (máximo 50)")
        except ErrorSpotify as error_me_gusta:
            print("Tus me gusta: no se pudieron leer ->", error_me_gusta)
    else:
        iniciar_sesion()