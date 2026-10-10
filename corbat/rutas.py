"""Rutas del proyecto y migración de archivos de versiones anteriores."""
import shutil
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DATOS = RAIZ / "datos"  # logs, tokens y contactos (no se sube a git)
VOCES = RAIZ / "voces"  # modelo de voz de Piper (no se sube a git)

_NOMBRES = (
    "acciones.log",
    "spotify_config.json",
    "spotify_token.json",
    "google_token.json",
    "google_contactos.json",
)
_PATRONES = ("*.vcf", "contactos*.csv", "client_secret*.json")


def _migrar():
    """Mueve a datos/ los archivos que antes vivían en la raíz del proyecto."""
    DATOS.mkdir(exist_ok=True)
    pendientes = [RAIZ / nombre for nombre in _NOMBRES]
    for patron in _PATRONES:
        pendientes.extend(RAIZ.glob(patron))

    for origen in pendientes:
        destino = DATOS / origen.name
        if origen.is_file() and not destino.exists():
            try:
                shutil.move(str(origen), str(destino))
            except OSError:
                pass  # por ejemplo, el archivo está abierto en otro programa


_migrar()
