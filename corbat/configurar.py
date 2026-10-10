"""Configuración guiada de Spotify y contactos.  Ejecuta:  configurar.bat

Todo se guarda en la carpeta datos/, que no se sube a git.
"""
import json
import os
import re
import webbrowser

from corbat import rutas
from corbat.contactos import agenda, google
from corbat.musica import spotify_api

URL_SPOTIFY = "https://developer.spotify.com/dashboard"
URL_GOOGLE = "https://console.cloud.google.com/"


def _abrir_datos():
    try:
        os.startfile(rutas.DATOS)
    except OSError:
        print(f"  La carpeta es: {rutas.DATOS}")


def _estado():
    spotify = "conectado" if spotify_api.configurado() else "sin conectar"
    contactos = len(agenda.cargar())
    return f"Spotify: {spotify} | Contactos leídos: {contactos}"


def guardar_client_id(texto):
    """Guarda el client_id de Spotify. Devuelve False si no parece válido."""
    client_id = texto.strip()
    if not re.fullmatch(r"[0-9a-zA-Z]{20,64}", client_id):
        return False
    rutas.DATOS.mkdir(exist_ok=True)
    spotify_api.ARCHIVO_CONFIG.write_text(
        json.dumps({"client_id": client_id}, indent=2), encoding="utf-8"
    )
    return True


def configurar_spotify():
    print("\n--- Spotify ---")
    print("Necesitas una cuenta de Spotify y crear tu propia app (gratis):")
    print(f"  1. Entra a {URL_SPOTIFY} e inicia sesión.")
    print("  2. 'Create app'. Nombre y descripción: lo que quieras.")
    print(f"  3. En 'Redirect URI' escribe exactamente:  {spotify_api.REDIRECT_URI}")
    print("  4. En 'APIs used' marca 'Web API' y guarda.")
    print("  5. En 'Settings' copia el 'Client ID'.")
    if input("¿Abro la página de Spotify ahora? [S/n] ").strip().lower() in ("", "s", "si", "sí"):
        webbrowser.open(URL_SPOTIFY)

    while True:
        texto = input("\nPega aquí el Client ID (Enter para cancelar): ")
        if not texto.strip():
            return
        if guardar_client_id(texto):
            break
        print("Eso no parece un Client ID (son letras y números, sin espacios). Intenta de nuevo.")

    print("Se abrirá el navegador para que autorices a Corbat...")
    try:
        spotify_api.iniciar_sesion()
        print("Spotify conectado.")
    except spotify_api.ErrorSpotify as error:
        print("Error:", error)


def configurar_google():
    print("\n--- Contactos de Google ---")
    print(f"  1. Entra a {URL_GOOGLE} y crea un proyecto.")
    print("  2. 'APIs y servicios' > 'Biblioteca': activa 'People API'.")
    print("  3. 'Pantalla de consentimiento de OAuth': tipo Externo; agrega tu correo como usuario")
    print("     de prueba y luego pulsa 'Publicar app' (así la sesión no vence a los 7 días).")
    print("  4. 'Credenciales' > 'Crear credenciales' > 'ID de cliente de OAuth' > 'App de escritorio'.")
    print("  5. Descarga el JSON y cópialo a la carpeta datos (se abre ahora).")
    webbrowser.open(URL_GOOGLE)
    _abrir_datos()
    input("\nCuando el archivo client_secret....json esté en datos, pulsa Enter... ")

    try:
        google.iniciar_sesion()
        print(f"{google.sincronizar()} contactos sincronizados.")
    except google.ErrorGoogle as error:
        print("Error:", error)


def contactos_de_archivo():
    print("\n--- Contactos desde un archivo ---")
    print("Exporta tus contactos como .vcf (iPhone, Android, Google) o como CSV de Google")
    print("y copia el archivo a la carpeta datos (se abre ahora).")
    print("Los CSV deben llamarse contactos*.csv")
    _abrir_datos()
    input("\nCuando el archivo esté en datos, pulsa Enter... ")
    print(f"Contactos leídos: {len(agenda.cargar())}")


OPCIONES = (
    ("Conectar Spotify", configurar_spotify),
    ("Conectar contactos de Google", configurar_google),
    ("Importar contactos desde un archivo (.vcf o .csv)", contactos_de_archivo),
)


def main():
    while True:
        print("\n=== Configuración de Corbat ===")
        print(_estado())
        for numero, (texto, _) in enumerate(OPCIONES, 1):
            print(f"  {numero}. {texto}")
        print("  0. Salir")

        eleccion = input("Elige una opción: ").strip()
        if eleccion == "0" or not eleccion:
            return
        if eleccion.isdigit() and 0 < int(eleccion) <= len(OPCIONES):
            try:
                OPCIONES[int(eleccion) - 1][1]()
            except KeyboardInterrupt:
                print("\nCancelado.")
        else:
            print("Opción no válida.")


if __name__ == "__main__":
    main()
