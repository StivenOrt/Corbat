"""Sincroniza tus contactos de Google (gratis) para que Corbat los use en WhatsApp.

Configuración, una sola vez (ver los pasos que te dio Claude):
  1. Descarga el JSON de credenciales de Google Cloud y déjalo en esta carpeta
     (se llama client_secret_....json).
  2. Ejecuta:  python google_contactos.py
     Se abre el navegador, aceptas, y Corbat guarda una copia local de tus contactos.

Después se actualiza solo (una vez al día al iniciar Corbat) o a mano con:
     python google_contactos.py sincronizar
"""
import base64
import hashlib
import json
import logging
import secrets
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

import httpx

import registro  # noqa: F401

CARPETA = Path(__file__).parent
ARCHIVO_TOKEN = CARPETA / "google_token.json"
ARCHIVO_CONTACTOS = CARPETA / "google_contactos.json"

PUERTO = 8889
REDIRECT_URI = f"http://127.0.0.1:{PUERTO}/callback"
SCOPE = "https://www.googleapis.com/auth/contacts.readonly"
URL_AUTORIZAR = "https://accounts.google.com/o/oauth2/v2/auth"
URL_TOKEN = "https://oauth2.googleapis.com/token"
URL_PERSONAS = "https://people.googleapis.com/v1/people/me/connections"
HORAS_ENTRE_SINCRONIZACIONES = 24


class ErrorGoogle(Exception):
    pass


def _credenciales():
    archivos = sorted(CARPETA.glob("client_secret*.json"))
    if not archivos:
        raise ErrorGoogle("Falta el archivo client_secret....json de Google en la carpeta de Corbat.")
    try:
        datos = json.loads(archivos[0].read_text(encoding="utf-8"))
        configuracion = datos.get("installed") or datos.get("web") or datos
        return configuracion["client_id"], configuracion.get("client_secret", "")
    except (OSError, ValueError, KeyError) as error:
        raise ErrorGoogle(f"No pude leer {archivos[0].name}: {error}") from error


def configurado():
    return ARCHIVO_TOKEN.exists() and bool(list(CARPETA.glob("client_secret*.json")))


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
        self.wfile.write("<h2>Listo. Ya puedes cerrar esta pestaña y volver a Corbat.</h2>".encode("utf-8"))

    def log_message(self, *args):
        pass


def _guardar_token(datos, anterior=None):
    datos["expira"] = time.time() + datos.get("expires_in", 3600) - 30
    if anterior and "refresh_token" not in datos:
        datos["refresh_token"] = anterior["refresh_token"]
    ARCHIVO_TOKEN.write_text(json.dumps(datos), encoding="utf-8")
    return datos


def iniciar_sesion():
    client_id, client_secret = _credenciales()

    verificador = secrets.token_urlsafe(64)
    desafio = base64.urlsafe_b64encode(hashlib.sha256(verificador.encode()).digest()).rstrip(b"=").decode()
    estado = secrets.token_urlsafe(16)

    url = URL_AUTORIZAR + "?" + urlencode({
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": REDIRECT_URI,
        "scope": SCOPE,
        "code_challenge_method": "S256",
        "code_challenge": desafio,
        "state": estado,
        "access_type": "offline",
        "prompt": "consent",
    })

    servidor = HTTPServer(("127.0.0.1", PUERTO), _Receptor)
    servidor.timeout = 180
    print("Abriendo el navegador para autorizar a Corbat en Google Contactos...")
    webbrowser.open(url)
    servidor.handle_request()
    servidor.server_close()

    if _Receptor.error or not _Receptor.codigo:
        raise ErrorGoogle(f"No se autorizó el acceso ({_Receptor.error or 'sin respuesta'}).")
    if _Receptor.estado != estado:
        raise ErrorGoogle("La respuesta de Google no coincide con la solicitud.")

    respuesta = httpx.post(URL_TOKEN, data={
        "grant_type": "authorization_code",
        "code": _Receptor.codigo,
        "redirect_uri": REDIRECT_URI,
        "client_id": client_id,
        "client_secret": client_secret,
        "code_verifier": verificador,
    }, timeout=15)
    if respuesta.status_code != 200:
        raise ErrorGoogle(f"Google rechazó el inicio de sesión: {respuesta.text[:200]}")

    _guardar_token(respuesta.json())
    print("Listo: Corbat ya está conectado a tus contactos de Google.")


# ---------- Tokens ----------

def _token_acceso():
    try:
        token = json.loads(ARCHIVO_TOKEN.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ErrorGoogle("Google no está conectado. Ejecuta python google_contactos.py una vez.") from error

    if time.time() < token.get("expira", 0):
        return token["access_token"]

    client_id, client_secret = _credenciales()
    respuesta = httpx.post(URL_TOKEN, data={
        "grant_type": "refresh_token",
        "refresh_token": token["refresh_token"],
        "client_id": client_id,
        "client_secret": client_secret,
    }, timeout=15)
    if respuesta.status_code != 200:
        logging.warning("Google: no se pudo renovar el acceso -> %s %s", respuesta.status_code, respuesta.text[:200])
        raise ErrorGoogle("La sesión de Google venció. Ejecuta python google_contactos.py de nuevo.")
    return _guardar_token(respuesta.json(), anterior=token)["access_token"]


# ---------- Sincronización ----------

def sincronizar():
    """Descarga tus contactos y guarda una copia local. Devuelve cuántos guardó."""
    cabeceras = {"Authorization": f"Bearer {_token_acceso()}"}
    contactos, pagina = [], None

    for _ in range(50):  # hasta 50.000 contactos
        parametros = {"personFields": "names,phoneNumbers", "pageSize": 1000}
        if pagina:
            parametros["pageToken"] = pagina
        try:
            respuesta = httpx.get(URL_PERSONAS, params=parametros, headers=cabeceras, timeout=30)
        except httpx.HTTPError as error:
            raise ErrorGoogle(f"No pude conectarme con Google ({error}).") from error
        if respuesta.status_code != 200:
            logging.warning("Google contactos -> %s %s", respuesta.status_code, respuesta.text[:200])
            raise ErrorGoogle(f"Google respondió con el error {respuesta.status_code}.")

        datos = respuesta.json()
        for persona in datos.get("connections", []):
            nombres = persona.get("names") or []
            telefonos = persona.get("phoneNumbers") or []
            if not nombres or not telefonos:
                continue
            moviles = [t for t in telefonos if (t.get("type") or "").lower() in ("mobile", "cell", "móvil")]
            elegido = (moviles or telefonos)[0]
            numero = elegido.get("canonicalForm") or elegido.get("value", "")
            if numero:
                contactos.append([nombres[0].get("displayName", ""), numero])

        pagina = datos.get("nextPageToken")
        if not pagina:
            break

    ARCHIVO_CONTACTOS.write_text(
        json.dumps({"actualizado": time.time(), "contactos": contactos}, ensure_ascii=False),
        encoding="utf-8",
    )
    logging.info("google_contactos: %d contactos sincronizados", len(contactos))
    return len(contactos)


def _hace_falta():
    if not ARCHIVO_CONTACTOS.exists():
        return True
    return time.time() - ARCHIVO_CONTACTOS.stat().st_mtime > HORAS_ENTRE_SINCRONIZACIONES * 3600


def sincronizar_si_hace_falta():
    if not configurado() or not _hace_falta():
        return
    try:
        sincronizar()
    except ErrorGoogle as error:
        logging.warning("google_contactos: %s", error)


def sincronizar_en_segundo_plano():
    threading.Thread(target=sincronizar_si_hace_falta, daemon=True).start()


if __name__ == "__main__":
    try:
        if len(sys.argv) > 1 and sys.argv[1] == "sincronizar":
            print(f"{sincronizar()} contactos sincronizados.")
        else:
            iniciar_sesion()
            print(f"{sincronizar()} contactos sincronizados.")
    except ErrorGoogle as error:
        print("Error:", error)
