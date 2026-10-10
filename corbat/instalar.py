"""Instalación guiada de Corbat: voz, modelos y arranque automático.

Normalmente se ejecuta desde instalar.bat, que antes prepara Python y las
dependencias. También se puede repetir a mano:  python -m corbat.instalar
Es seguro ejecutarlo varias veces: lo que ya está instalado se omite.
"""
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

from corbat import rutas

MODELO_LLM = "qwen2.5:7b"
MODELOS_WHISPER = ("tiny", "small")
URL_VOZ = "https://huggingface.co/rhasspy/piper-voices/resolve/main/es/es_MX/claude/high/"
ARCHIVOS_VOZ = ("es_MX-claude-high.onnx", "es_MX-claude-high.onnx.json")
URL_OLLAMA = "https://ollama.com/download"


def preguntar(texto, defecto=True):
    sufijo = "[S/n]" if defecto else "[s/N]"
    respuesta = input(f"{texto} {sufijo} ").strip().lower()
    if not respuesta:
        return defecto
    return respuesta in ("s", "si", "sí", "y", "yes")


def _descargar(url, destino):
    parcial = destino.with_suffix(destino.suffix + ".parte")
    with urllib.request.urlopen(url, timeout=60) as respuesta, open(parcial, "wb") as archivo:
        total = int(respuesta.headers.get("Content-Length") or 0)
        leido = 0
        while True:
            bloque = respuesta.read(1024 * 256)
            if not bloque:
                break
            archivo.write(bloque)
            leido += len(bloque)
            if total:
                print(f"\r  {destino.name}: {leido * 100 // total}%", end="", flush=True)
    print()
    parcial.replace(destino)  # solo queda el archivo si la descarga terminó


def instalar_voz(url_base=URL_VOZ):
    rutas.VOCES.mkdir(exist_ok=True)
    for nombre in ARCHIVOS_VOZ:
        destino = rutas.VOCES / nombre
        if destino.exists():
            print(f"  {nombre}: ya estaba.")
            continue
        _descargar(url_base + nombre, destino)
    return True


def buscar_ollama():
    ruta = shutil.which("ollama")
    if ruta:
        return ruta
    local = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama" / "ollama.exe"
    return str(local) if local.exists() else None


def instalar_ollama():
    ruta = buscar_ollama()
    if ruta:
        print("  Ollama ya está instalado.")
    elif shutil.which("winget") and preguntar("  Ollama no está instalado. ¿Instalarlo ahora con winget?"):
        subprocess.run(["winget", "install", "-e", "--id", "Ollama.Ollama"])
        ruta = buscar_ollama()

    if not ruta:
        print(f"  Instala Ollama desde {URL_OLLAMA} y vuelve a ejecutar la instalación.")
        return False

    listado = subprocess.run([ruta, "list"], capture_output=True, text=True, errors="replace")
    if MODELO_LLM in listado.stdout:
        print(f"  El modelo {MODELO_LLM} ya estaba descargado.")
        return True

    print(f"  Descargando {MODELO_LLM} (unos 4.7 GB, solo la primera vez)...")
    if subprocess.run([ruta, "pull", MODELO_LLM]).returncode != 0:
        print(f"  No se pudo descargar. Abre la aplicación Ollama y ejecuta:  ollama pull {MODELO_LLM}")
        return False
    return True


def descargar_whisper():
    from faster_whisper.utils import download_model

    for nombre in MODELOS_WHISPER:
        print(f"  Whisper {nombre}...")
        download_model(nombre)
    return True


def comando_acceso_directo(vbs, carpeta):
    """Comando de PowerShell que crea el acceso directo en el inicio de Windows."""
    def comillas(ruta):
        return str(ruta).replace("'", "''")

    return (
        "$s=(New-Object -ComObject WScript.Shell).CreateShortcut("
        "$env:APPDATA+'\\Microsoft\\Windows\\Start Menu\\Programs\\Startup\\Corbat.lnk');"
        f"$s.TargetPath='{comillas(vbs)}';$s.WorkingDirectory='{comillas(carpeta)}';$s.Save()"
    )


def acceso_inicio():
    vbs = rutas.RAIZ / "scripts" / "corbat_oculto.vbs"
    if not preguntar("  ¿Quieres que Corbat arranque solo al iniciar Windows?"):
        print("  Omitido. Puedes arrancarlo con scripts\\iniciar_corbat.bat.")
        return True
    resultado = subprocess.run(
        ["powershell", "-NoProfile", "-Command", comando_acceso_directo(vbs, rutas.RAIZ)]
    )
    return resultado.returncode == 0


PASOS = (
    ("Voz de Corbat (Piper)", instalar_voz),
    ("Modelo de lenguaje (Ollama)", instalar_ollama),
    ("Modelos de reconocimiento de voz (Whisper)", descargar_whisper),
    ("Arranque automático", acceso_inicio),
)


def main():
    print("=== Instalación de Corbat ===")
    fallidos = []

    for numero, (titulo, funcion) in enumerate(PASOS, 1):
        print(f"\n[{numero}/{len(PASOS)}] {titulo}")
        try:
            ok = funcion()
        except (OSError, urllib.error.URLError, subprocess.SubprocessError, ImportError) as error:
            print(f"  Error: {error}")
            ok = False
        if not ok:
            fallidos.append(titulo)

    print()
    if fallidos:
        print("Quedó pendiente:", ", ".join(fallidos))
        print("Corrige lo que indica arriba y vuelve a ejecutar instalar.bat.")
        return 1

    print("Todo listo.")
    print("Opcional: conecta Spotify y tus contactos con configurar.bat")
    print("Para iniciar Corbat: scripts\\iniciar_corbat.bat")
    return 0


if __name__ == "__main__":
    sys.exit(main())
