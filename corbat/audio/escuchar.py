import gc
import os
import threading

from faster_whisper import WhisperModel

# "tiny" siempre está cargado (ligero) y solo detecta el nombre.
# "small" es el preciso: se carga al despertar y se libera al dormir.
LIGERO = "tiny"
PRECISO = "medium"

# Solo vocabulario: si el prompt trae frases de órdenes, Whisper las "inventa"
# cuando oye ruido (una silla, un golpe) y Corbat las ejecuta.
PROMPT = (
    "Spotify, Brave, Discord, WhatsApp, Steam, MySQL Workbench, "
    "Visual Studio Code, Kris R, Bobadita, Don Omar."
)

# Un segmento se descarta si Whisper duda de que haya voz o de lo que dijo.
MAX_SIN_VOZ = 0.6
MIN_CONFIANZA = -1.2
MAX_COMPRESION = 2.4

# Hilos de CPU: núcleos físicos (los lógicos casi no ayudan con Whisper).
HILOS = max(4, min(8, (os.cpu_count() or 8) // 2))

_cerrojo = threading.Lock()
_modelos = {}


def _modelo(nombre):
    with _cerrojo:
        if nombre not in _modelos:
            hilos = 2 if nombre == LIGERO else HILOS
            ajustes = dict(device="cpu", compute_type="int8", cpu_threads=hilos)
            try:  # ya descargado: no consulta internet (ahorra 1-2 s en cada carga)
                _modelos[nombre] = WhisperModel(nombre, local_files_only=True, **ajustes)
            except Exception:  # primera vez: lo descarga
                _modelos[nombre] = WhisperModel(nombre, **ajustes)
        return _modelos[nombre]


def precargar(nombre=PRECISO):
    """Carga el modelo (si no estaba cargado) para que la primera frase no espere."""
    _modelo(nombre)


def liberar():
    """Descarta el modelo preciso para devolver su memoria al sistema."""
    with _cerrojo:
        _modelos.pop(PRECISO, None)
    gc.collect()


def _texto(modelo, audio, prompt, **opciones):
    segmentos, _ = modelo.transcribe(
        audio,
        language="es",
        beam_size=1,  # decodificación voraz: mucho más rápida y casi igual de precisa
        temperature=0.0,  # sin reintentos con otras temperaturas (cada uno repite el trabajo)
        without_timestamps=True,
        vad_filter=True,
        condition_on_previous_text=False,
        initial_prompt=prompt,
        **opciones,
    )
    confiables = [
        segmento.text.strip()
        for segmento in segmentos
        if segmento.no_speech_prob < MAX_SIN_VOZ
        and segmento.avg_logprob > MIN_CONFIANZA
        and segmento.compression_ratio < MAX_COMPRESION
    ]
    return " ".join(confiables)


def detectar(audio):
    """Transcripción rápida y ligera, solo para saber si dijeron 'Corbat'."""
    return _texto(_modelo(LIGERO), audio, None)


def transcribir(audio):
    return _texto(_modelo(PRECISO), audio, PROMPT)
