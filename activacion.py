import collections
import difflib
import re
import unicodedata

import numpy as np
import sounddevice as sd

FRECUENCIA = 16000
BLOQUE = int(0.1 * FRECUENCIA)  # bloques de 0.1 segundos
SILENCIO_FINAL = 0.9  # segundos de silencio para dar por terminada una frase
MAX_SEGUNDOS = 15
MIN_SEGUNDOS = 0.4
BLOQUES_PREVIOS = 3  # conserva el inicio de la frase
DISPOSITIVO = None  # Cambia por el número de tu micrófono si hace falta

def _rms(bloque):
    return float(np.sqrt(np.mean(np.square(bloque))))


def calibrar_ruido(segundos=1.5):
    audio = sd.rec(
        int(segundos * FRECUENCIA),
        samplerate=FRECUENCIA,
        channels=1,
        dtype="float32",
        device=DISPOSITIVO,
    )
    sd.wait()
    ruido = _rms(audio.flatten())
    umbral = max(ruido * 3, 0.01)
    print(f"[Ruido ambiente: {ruido:.4f} | Umbral de voz: {umbral:.4f}]")
    return umbral


def capturar_frase(umbral, espera_maxima=None):
    """Espera a que alguien hable y devuelve el audio de la frase.

    Si espera_maxima tiene un valor (segundos) y nadie habla en ese tiempo,
    devuelve None. Si es None, espera indefinidamente.
    """
    previos = collections.deque(maxlen=BLOQUES_PREVIOS)
    grabados = []
    hablando = False
    silencio = 0
    esperados = 0

    with sd.InputStream(
        samplerate=FRECUENCIA,
        channels=1,
        dtype="float32",
        blocksize=BLOQUE,
        device=DISPOSITIVO,
    ) as flujo:
        while True:
            datos, _ = flujo.read(BLOQUE)
            bloque = datos.flatten()
            nivel = _rms(bloque)

            if not hablando:
                if nivel >= umbral:
                    hablando = True
                    grabados = list(previos) + [bloque]
                    silencio = 0
                else:
                    previos.append(bloque)
                    esperados += 1
                    if espera_maxima and esperados * 0.1 >= espera_maxima:
                        return None
                continue

            grabados.append(bloque)
            silencio = silencio + 1 if nivel < umbral else 0

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

def _parece_nombre(palabra, umbral):
    return difflib.SequenceMatcher(None, palabra, NOMBRE).ratio() >= umbral


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