import gc
import threading

from faster_whisper import WhisperModel

# "tiny" siempre está cargado (ligero) y solo detecta el nombre.
# "small" es el preciso: se carga al despertar y se libera al dormir.
LIGERO = "tiny"
PRECISO = "small"

PROMPT = (
    "Oye Corbat, abre el bloc de notas. Oye Corbat, cierra Spotify. "
    "Oye Corbat, busca el archivo prueba. Oye Corbat, sube el volumen. "
    "Oye Corbat, ¿qué hora es? Brave, Discord, WhatsApp, Steam, "
    "MySQL Workbench, Visual Studio Code. "
    "Oye Corbat, reproduce algo de Kris R. Reproduce Bobadita en Spotify. "
    "Pon Virtual Diva de Don Omar."
)

_cerrojo = threading.Lock()
_modelos = {}


def _modelo(nombre):
    with _cerrojo:
        if nombre not in _modelos:
            _modelos[nombre] = WhisperModel(nombre, device="cpu", compute_type="int8")
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
        vad_filter=True,
        condition_on_previous_text=False,
        initial_prompt=prompt,
        **opciones,
    )
    return " ".join(segmento.text.strip() for segmento in segmentos)


def detectar(audio):
    """Transcripción rápida y ligera, solo para saber si dijeron 'Corbat'."""
    return _texto(_modelo(LIGERO), audio, "Oye Corbat.", beam_size=1)


def transcribir(audio):
    return _texto(_modelo(PRECISO), audio, PROMPT)
