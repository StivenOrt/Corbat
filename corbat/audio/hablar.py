import collections
import json
import subprocess
import sys
import threading
import time

import numpy as np

from corbat import rutas
from corbat.audio import microfono
from corbat.audio.activacion import BLOQUES_PREVIOS, MAX_SEGUNDOS, SILENCIO_FINAL
from corbat.interfaz import indicador

BLOQUES_PARA_INTERRUMPIR = 3  # 0.3 segundos seguidos por encima del umbral
MARGEN_FINAL = 0.2  # segundos extra para no cortar el final de la frase
SALUDO = "Hola, soy Corbat. Dime oye Corbat para llamarme."

_proceso = None
_cerrojo = threading.Lock()


def _rms(bloque):
    return float(np.sqrt(np.mean(np.square(bloque))))


def _enviar(proceso, orden):
    try:
        proceso.stdin.write(json.dumps(orden) + "\n")
        proceso.stdin.flush()
    except (BrokenPipeError, OSError):
        pass


def _leer_json(proceso):
    while True:
        linea = proceso.stdout.readline()
        if not linea:
            return None
        try:
            datos = json.loads(linea)
        except ValueError:
            continue
        if isinstance(datos, dict):
            return datos


def _worker():
    global _proceso

    with _cerrojo:
        if _proceso is None or _proceso.poll() is not None:
            _proceso = subprocess.Popen(
                [sys.executable, "-m", "corbat.audio.voz"],
                cwd=str(rutas.RAIZ),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                bufsize=1,
            )
            _leer_json(_proceso)  # espera el mensaje de "listo"

        return _proceso


def precargar_voz():
    """Arranca el proceso de voz (tarda unos segundos) sin decir nada."""
    _worker()


def liberar_voz():
    """Cierra el proceso de voz para liberar su memoria; se reabre al hablar."""
    global _proceso

    with _cerrojo:
        proceso, _proceso = _proceso, None

    if proceso is None or proceso.poll() is not None:
        return
    proceso.terminate()
    try:
        proceso.wait(timeout=3)
    except subprocess.TimeoutExpired:
        proceso.kill()


def _decir(texto):
    """Pide al proceso de voz que hable. Devuelve la duración en segundos."""
    proceso = _worker()
    _enviar(proceso, {"cmd": "hablar", "texto": texto})
    respuesta = _leer_json(proceso)

    if not respuesta or "duracion" not in respuesta:
        return None
    return float(respuesta["duracion"])


def _parar():
    if _proceso is not None and _proceso.poll() is None:
        _enviar(_proceso, {"cmd": "parar"})


def calibrar_interrupcion(umbral_voz):
    """Dice el saludo y mide cuánto de su propia voz capta el micrófono.

    Devuelve el umbral que debe superar tu voz para interrumpirlo.
    """
    duracion = _decir(SALUDO)

    if duracion is None:
        print("[No se pudo iniciar la voz]")
        return max(umbral_voz * 3, 0.03)

    microfono.vaciar()
    fin = time.monotonic() + duracion + MARGEN_FINAL
    niveles = []

    while time.monotonic() < fin:
        bloque = microfono.leer()
        if bloque is not None:
            niveles.append(_rms(bloque))

    eco = float(np.percentile(niveles, 95)) if niveles else 0.0
    umbral = max(eco * 1.8, umbral_voz * 2)
    print(f"[Eco de Corbat: {eco:.4f} | Umbral para interrumpirlo: {umbral:.4f}]")
    return umbral


def _escuchar_interrupcion(fin, umbral_voz, umbral_interrupcion):
    previos = collections.deque(maxlen=BLOQUES_PREVIOS + BLOQUES_PARA_INTERRUMPIR)
    grabados = []
    seguidos = 0
    silencio = 0
    interrumpido = False

    while True:
        if not interrumpido and time.monotonic() >= fin:
            return None

        bloque = microfono.leer(0.2)
        if bloque is None:
            continue
        nivel = _rms(bloque)

        if not interrumpido:
            previos.append(bloque)
            seguidos = seguidos + 1 if nivel >= umbral_interrupcion else 0
            if seguidos >= BLOQUES_PARA_INTERRUMPIR:
                interrumpido = True
                _parar()
                grabados = list(previos)
                silencio = 0
            continue

        grabados.append(bloque)
        silencio = silencio + 1 if nivel < umbral_voz else 0

        if silencio * 0.1 >= SILENCIO_FINAL or len(grabados) * 0.1 >= MAX_SEGUNDOS:
            return np.concatenate(grabados)


def hablar(texto, umbral_voz=None, umbral_interrupcion=None):
    indicador.estado("hablando")
    try:
        return _hablar(texto, umbral_voz, umbral_interrupcion)
    finally:
        indicador.estado("escuchando")


def _hablar(texto, umbral_voz, umbral_interrupcion):
    """Dice el texto en voz alta.

    Sin umbrales, espera a que termine y devuelve None.
    Con umbrales, vigila el micrófono: si lo interrumpes, se calla y devuelve
    el audio de lo que dijiste. Si termina sin interrupción, devuelve None.
    """
    duracion = _decir(texto)
    if duracion is None:
        return None

    fin = time.monotonic() + duracion + MARGEN_FINAL
    microfono.vaciar()  # lo que se oyó mientras Corbat pensaba ya no sirve

    if umbral_interrupcion is None:
        restante = fin - time.monotonic()
        if restante > 0:
            time.sleep(restante)
        microfono.vaciar()  # así no se "oye" a sí mismo
        return None

    try:
        return _escuchar_interrupcion(fin, umbral_voz, umbral_interrupcion)
    finally:
        _parar()