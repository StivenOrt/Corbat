import collections
import subprocess
import sys
from pathlib import Path

import numpy as np
import sounddevice as sd

from activacion import (
    BLOQUE,
    BLOQUES_PREVIOS,
    DISPOSITIVO,
    FRECUENCIA,
    MAX_SEGUNDOS,
    SILENCIO_FINAL,
)

SCRIPT_VOZ = Path(__file__).with_name("voz.py")
BLOQUES_PARA_INTERRUMPIR = 3  # 0.3 segundos seguidos por encima del umbral
SALUDO = "Hola, soy Corbat. Dime oye Corbat para llamarme."


def _rms(bloque):
    return float(np.sqrt(np.mean(np.square(bloque))))


def _iniciar_voz(texto):
    proceso = subprocess.Popen(
        [sys.executable, str(SCRIPT_VOZ)],
        stdin=subprocess.PIPE,
        text=True,
        encoding="utf-8",
    )
    proceso.stdin.write(texto)
    proceso.stdin.close()
    return proceso


def calibrar_interrupcion(umbral_voz):
    """Dice el saludo y mide cuánto de su propia voz capta el micrófono.

    Devuelve el umbral que debe superar tu voz para interrumpirlo.
    """
    proceso = _iniciar_voz(SALUDO)
    niveles = []

    with sd.InputStream(
        samplerate=FRECUENCIA,
        channels=1,
        dtype="float32",
        blocksize=BLOQUE,
        device=DISPOSITIVO,
    ) as flujo:
        while proceso.poll() is None:
            datos, _ = flujo.read(BLOQUE)
            niveles.append(_rms(datos.flatten()))

    proceso.wait()

    eco = float(np.percentile(niveles, 95)) if niveles else 0.0
    umbral = max(eco * 1.8, umbral_voz * 2)
    print(f"[Eco de Corbat: {eco:.4f} | Umbral para interrumpirlo: {umbral:.4f}]")
    return umbral


def _escuchar_interrupcion(proceso, umbral_voz, umbral_interrupcion):
    previos = collections.deque(maxlen=BLOQUES_PREVIOS + BLOQUES_PARA_INTERRUMPIR)
    grabados = []
    seguidos = 0
    silencio = 0
    interrumpido = False

    with sd.InputStream(
        samplerate=FRECUENCIA,
        channels=1,
        dtype="float32",
        blocksize=BLOQUE,
        device=DISPOSITIVO,
    ) as flujo:
        while True:
            if not interrumpido and proceso.poll() is not None:
                return None

            datos, _ = flujo.read(BLOQUE)
            bloque = datos.flatten()
            nivel = _rms(bloque)

            if not interrumpido:
                previos.append(bloque)
                seguidos = seguidos + 1 if nivel >= umbral_interrupcion else 0
                if seguidos >= BLOQUES_PARA_INTERRUMPIR:
                    interrumpido = True
                    proceso.kill()
                    grabados = list(previos)
                    silencio = 0
                continue

            grabados.append(bloque)
            silencio = silencio + 1 if nivel < umbral_voz else 0

            if silencio * 0.1 >= SILENCIO_FINAL or len(grabados) * 0.1 >= MAX_SEGUNDOS:
                return np.concatenate(grabados)


def hablar(texto, umbral_voz=None, umbral_interrupcion=None):
    """Dice el texto en voz alta.

    Sin umbrales, espera a que termine y devuelve None.
    Con umbrales, vigila el micrófono: si lo interrumpes, se calla y devuelve
    el audio de lo que dijiste. Si termina sin interrupción, devuelve None.
    """
    proceso = _iniciar_voz(texto)

    try:
        if umbral_interrupcion is None:
            proceso.wait()
            return None
        return _escuchar_interrupcion(proceso, umbral_voz, umbral_interrupcion)
    finally:
        if proceso.poll() is None:
            proceso.kill()
        proceso.wait()