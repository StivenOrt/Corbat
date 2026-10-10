import numpy as np
import sounddevice as sd
from faster_whisper import WhisperModel

FRECUENCIA = 16000
SEGUNDOS = 5

modelo = WhisperModel("small", device="cpu", compute_type="int8")


def grabar(segundos):
    print("Escuchando...")
    audio = sd.rec(
        int(segundos * FRECUENCIA),
        samplerate=FRECUENCIA,
        channels=1,
        dtype="float32",
    )
    sd.wait()
    return audio.flatten()


def transcribir(audio):
    segmentos, _ = modelo.transcribe(
        audio,
        language="es",
        vad_filter=True,
        condition_on_previous_text=False,
        initial_prompt=(
            "Oye Corbat, abre el bloc de notas. Oye Corbat, cierra Spotify. "
            "Oye Corbat, busca el archivo prueba. Oye Corbat, sube el volumen. "
            "Oye Corbat, ¿qué hora es? Brave, Discord, WhatsApp, Steam, "
            "MySQL Workbench, Visual Studio Code. "
            "Oye Corbat, reproduce algo de Kris R. Reproduce Bobadita en Spotify. "
            "Pon Virtual Diva de Don Omar."
        ),
    )
    return " ".join(segmento.text.strip() for segmento in segmentos)


if __name__ == "__main__":
    audio = grabar(SEGUNDOS)
    texto = transcribir(audio)
    print("Dijiste:", texto)