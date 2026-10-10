"""Control del orbe flotante desde el proceso principal.

Si el orbe no se puede abrir (por ejemplo, falta tkinter), Corbat sigue
funcionando igual, solo que sin la bolita.
"""
import subprocess
import sys
from pathlib import Path

SCRIPT_ORBE = Path(__file__).with_name("orbe.py")

_proceso = None
_actual = None


def iniciar():
    global _proceso, _actual

    if _proceso is not None and _proceso.poll() is None:
        return
    try:
        _proceso = subprocess.Popen(
            [sys.executable, str(SCRIPT_ORBE)],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except OSError:
        _proceso = None
    _actual = None


def estado(nombre):
    """nombre: oculto, escuchando, pensando o hablando."""
    global _proceso, _actual

    if _proceso is None or nombre == _actual:
        return
    try:
        _proceso.stdin.write(nombre + "\n")
        _proceso.stdin.flush()
        _actual = nombre
    except (BrokenPipeError, OSError):
        _proceso = None


def cerrar():
    global _proceso

    proceso, _proceso = _proceso, None
    if proceso is None:
        return
    try:
        proceso.stdin.close()  # el orbe se cierra solo al quedarse sin entrada
        proceso.wait(timeout=2)
    except (OSError, subprocess.TimeoutExpired):
        proceso.kill()
