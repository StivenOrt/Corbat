"""Micrófono compartido.

Hay una sola entrada de audio abierta todo el tiempo. Mientras Corbat transcribe
o piensa, el audio se guarda en una cola: no se pierde lo que digas y tampoco se
gasta tiempo abriendo y cerrando el micrófono en cada frase.
"""
import logging
import queue
import threading
import time

import sounddevice as sd

FRECUENCIA = 16000
BLOQUE = int(0.1 * FRECUENCIA)  # bloques de 0.1 segundos
DISPOSITIVO = None  # Cambia por el número de tu micrófono si hace falta
MAX_BLOQUES = 100  # como máximo se guardan 10 segundos de audio

_cola = queue.Queue(maxsize=MAX_BLOQUES)
_cerrojo = threading.Lock()
_flujo = None


def _recibir(datos, frames, tiempo, estado):
    bloque = datos[:, 0].copy()
    try:
        _cola.put_nowait(bloque)
    except queue.Full:  # si nadie lee, se descarta lo más viejo
        try:
            _cola.get_nowait()
            _cola.put_nowait(bloque)
        except (queue.Empty, queue.Full):
            pass


def abrir():
    """Abre el micrófono si no está abierto (se vuelve a abrir si se desconectó)."""
    global _flujo

    with _cerrojo:
        if _flujo is not None and _flujo.active:
            return
        if _flujo is not None:
            try:
                _flujo.close()
            except sd.PortAudioError:
                pass
        _flujo = sd.InputStream(
            samplerate=FRECUENCIA,
            channels=1,
            dtype="float32",
            blocksize=BLOQUE,
            device=DISPOSITIVO,
            callback=_recibir,
        )
        _flujo.start()


def leer(espera=0.5):
    """Siguiente bloque de 0.1 s, o None si no llegó ninguno en `espera` segundos."""
    try:
        abrir()
    except sd.PortAudioError as error:
        logging.warning("Micrófono no disponible (%s); reintento en un segundo", error)
        time.sleep(1)
        return None

    try:
        return _cola.get(timeout=espera)
    except queue.Empty:
        return None


def vaciar():
    """Descarta el audio guardado (por ejemplo, la propia voz de Corbat)."""
    try:
        while True:
            _cola.get_nowait()
    except queue.Empty:
        pass


def cerrar():
    global _flujo

    with _cerrojo:
        flujo, _flujo = _flujo, None
    if flujo is not None:
        try:
            flujo.stop()
            flujo.close()
        except sd.PortAudioError:
            pass
