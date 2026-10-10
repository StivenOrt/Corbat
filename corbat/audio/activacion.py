import collections
import difflib
import re
import time
import unicodedata

import numpy as np

from corbat.audio import microfono
from corbat.audio.microfono import BLOQUE, DISPOSITIVO, FRECUENCIA  # noqa: F401  (los usa hablar)

SILENCIO_FINAL = 1.2  # segundos de silencio para dar por terminada una frase
MAX_SEGUNDOS = 15
MIN_SEGUNDOS = 0.4
BLOQUES_PREVIOS = 6  # conserva 0.6 s antes de que empieces a hablar
HISTERESIS = 0.7  # para cortar una frase el nivel debe caer por debajo de umbral * 0.7


def _rms(bloque):
    return float(np.sqrt(np.mean(np.square(bloque))))


def calibrar_ruido(segundos=1.5):
    microfono.abrir()
    time.sleep(0.3)  # el primer instante después de abrir suele traer un chasquido
    microfono.vaciar()

    bloques = []
    fin = time.monotonic() + segundos
    while time.monotonic() < fin:
        bloque = microfono.leer()
        if bloque is not None:
            bloques.append(bloque)

    ruido = _rms(np.concatenate(bloques)) if bloques else 0.0
    umbral = max(ruido * 2.5, 0.008)
    print(f"[Ruido ambiente: {ruido:.4f} | Umbral de voz: {umbral:.4f}]")
    return umbral


def capturar_frase(umbral, espera_maxima=None):
    """Espera a que alguien hable y devuelve el audio de la frase.

    Si espera_maxima tiene un valor (segundos) y nadie habla en ese tiempo,
    devuelve None. Si es None, espera indefinidamente.

    Lee del micrófono compartido: también se oye lo que dijiste mientras
    Corbat estaba ocupado transcribiendo o pensando.
    """
    previos = collections.deque(maxlen=BLOQUES_PREVIOS)
    grabados = []
    hablando = False
    silencio = 0
    limite = None if not espera_maxima else time.monotonic() + espera_maxima

    while True:
        bloque = microfono.leer()

        if bloque is None:
            if not hablando and limite is not None and time.monotonic() >= limite:
                return None
            continue

        nivel = _rms(bloque)

        if not hablando:
            if nivel >= umbral:
                hablando = True
                grabados = list(previos) + [bloque]
                silencio = 0
            else:
                previos.append(bloque)
                if limite is not None and time.monotonic() >= limite:
                    return None
            continue

        grabados.append(bloque)
        silencio = silencio + 1 if nivel < umbral * HISTERESIS else 0

        terminada = (
            silencio * 0.1 >= SILENCIO_FINAL
            or len(grabados) * 0.1 >= MAX_SEGUNDOS
        )
        if not terminada:
            continue

        voz = (len(grabados) - silencio) * 0.1
        if voz >= MIN_SEGUNDOS:
            return np.concatenate(grabados)

        # Fue solo un ruido corto: se descarta y se sigue esperando.
        grabados, hablando, silencio = [], False, 0


def normalizar(texto):
    texto = unicodedata.normalize("NFD", texto.lower())
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    texto = re.sub(r"[^\w\s]", " ", texto)
    return re.sub(r"\s+", " ", texto).strip()

NOMBRE = "corbat"
UMBRAL_NOMBRE = 0.8

def _fonetica(palabra):
    """En español b/v y d/t finales suenan casi igual: 'Corvad' = 'Corbat'."""
    palabra = palabra.replace("v", "b").replace("w", "b")
    return re.sub(r"d$", "t", re.sub(r"(.)\1+", r"\1", palabra))


def _parece_nombre(palabra, umbral):
    return difflib.SequenceMatcher(None, _fonetica(palabra), NOMBRE).ratio() >= umbral


def extraer_comando(texto, umbral=UMBRAL_NOMBRE):
    """Devuelve la orden que sigue al nombre del asistente, tal como se dijo.

    Devuelve None si no se dijo el nombre, o "" si se dijo solo.
    Un umbral más bajo acepta nombres peor pronunciados o mal transcritos.
    """
    palabras = list(re.finditer(r"\w+", texto))

    for posicion, palabra in enumerate(palabras):
        if not _parece_nombre(normalizar(palabra.group()), umbral):
            continue

        siguiente = posicion + 1
        while siguiente < len(palabras) and _parece_nombre(
            normalizar(palabras[siguiente].group()), umbral
        ):
            siguiente += 1

        if siguiente >= len(palabras):
            return ""

        return texto[palabras[siguiente].start():].strip()

    return None