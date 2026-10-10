"""Diagnóstico de la conexión de Corbat con Spotify.

Uso:
    python diagnostico_spotify.py            solo consulta (no cambia la música)
    python diagnostico_spotify.py --probar   además pausa y reanuda la música
"""
import sys
import time

import registro  # noqa: F401
import spotify_api
from spotify_api import ErrorSpotify

SCOPES_NECESARIOS = set(spotify_api.SCOPES.split())


def titulo(texto):
    print(f"\n=== {texto}")


def bien(texto):
    print(f"  [OK]    {texto}")


def mal(texto):
    print(f"  [FALLO] {texto}")


def detalle(error):
    return f"{error} (código {error.estado})" if error.estado else str(error)


def revisar_archivos():
    titulo("1. Archivos")
    todo_bien = True

    for nombre, ruta in (
        ("spotify_config.json", spotify_api.ARCHIVO_CONFIG),
        ("spotify_token.json", spotify_api.ARCHIVO_TOKEN),
    ):
        if ruta.exists():
            bien(f"{nombre} existe")
        else:
            mal(f"{nombre} no existe. Ejecuta: python spotify_api.py")
            todo_bien = False

    return todo_bien


def revisar_sesion():
    titulo("2. Sesión de Spotify")

    try:
        cliente = spotify_api._client_id()
    except ErrorSpotify as error:
        mal(str(error))
        return False

    if len(cliente) == 32:
        bien("client_id con el largo esperado (32 caracteres)")
    else:
        mal(
            f"el client_id tiene {len(cliente)} caracteres y debería tener 32; "
            "revisa spotify_config.json"
        )

    try:
        spotify_api._token_acceso()
    except ErrorSpotify as error:
        mal(detalle(error))
        return False
    bien("token de acceso válido (se renueva solo cuando vence)")

    concedidos = set(spotify_api._cargar_token().get("scope", "").split())
    faltan = SCOPES_NECESARIOS - concedidos
    if faltan:
        mal("faltan permisos: " + ", ".join(sorted(faltan)))
        print("          Ejecuta de nuevo: python spotify_api.py")
        return False

    bien("permisos concedidos: " + ", ".join(sorted(concedidos)))
    return True


def revisar_busqueda():
    titulo("3. Búsqueda de canciones")

    try:
        pista = spotify_api.buscar_pista("Virtual Diva Don Omar")
    except ErrorSpotify as error:
        mal(detalle(error))
        return

    if pista is None:
        mal("la búsqueda no devolvió canciones")
    else:
        bien(f"encontró: {pista[1]} de {pista[2]}")


def revisar_dispositivos():
    titulo("4. Dispositivos de Spotify")

    try:
        respuesta = spotify_api._peticion("GET", "/me/player/devices")
    except ErrorSpotify as error:
        mal(detalle(error))
        return

    dispositivos = respuesta.json().get("devices", [])
    if not dispositivos:
        mal("Spotify no ve ningún dispositivo. Abre la app de escritorio e inicia sesión.")
        return

    for d in dispositivos:
        marcas = []
        if d.get("is_active"):
            marcas.append("activo")
        if d.get("is_restricted"):
            marcas.append("restringido")
        bien(f"{d.get('name')} ({d.get('type')}) {' '.join(marcas)}".rstrip())

    elegido = spotify_api._elegir_dispositivo()
    nombre = next((d.get("name") for d in dispositivos if d.get("id") == elegido), None)
    print(f"          Corbat usaría: {nombre or 'ninguno'}")


def revisar_estado():
    titulo("5. Qué está sonando")

    try:
        actual = spotify_api.actual()
    except ErrorSpotify as error:
        mal(detalle(error))
        return None

    if actual is None:
        bien("no hay nada sonando ahora mismo")
        return None

    nombre, artistas, sonando = actual
    bien(f"{nombre} de {artistas}: {'sonando' if sonando else 'en pausa'}")
    return sonando


def probar_controles(sonando):
    titulo("6. Prueba de pausa y reanudar")

    if not sonando:
        print("  Pon una canción (con Corbat o con la app) y vuelve a ejecutar con --probar.")
        return

    try:
        spotify_api.pausar()
        bien("pausa aceptada por Spotify")
        time.sleep(2)
        spotify_api.reanudar()
        bien("reanudar aceptado por Spotify")
    except ErrorSpotify as error:
        mal(detalle(error))


def main():
    probar = "--probar" in sys.argv

    if not revisar_archivos():
        return
    if not revisar_sesion():
        return

    revisar_busqueda()
    revisar_dispositivos()
    sonando = revisar_estado()

    if probar:
        probar_controles(sonando)

    print("\nListo. El detalle de cada error también queda en acciones.log.")


if __name__ == "__main__":
    main()
