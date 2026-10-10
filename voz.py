import os
import sys
import tempfile
import wave
import winsound
from pathlib import Path

import pyttsx3

MODELO = Path(__file__).with_name("voces") / "es_MX-claude-high.onnx"
ARCHIVO_AUDIO = os.path.join(tempfile.gettempdir(), "corbat_voz.wav")


def hablar_piper(texto):
    from piper import PiperVoice

    voz = PiperVoice.load(str(MODELO))

    with wave.open(ARCHIVO_AUDIO, "wb") as archivo:
        voz.synthesize_wav(texto, archivo)

    winsound.PlaySound(ARCHIVO_AUDIO, winsound.SND_FILENAME)


def hablar_windows(texto):
    motor = pyttsx3.init()

    for voz in motor.getProperty("voices"):
        identificador = voz.id.lower()
        nombre = voz.name.lower()
        if "_es-" in identificador or "spanish" in nombre or "español" in nombre:
            motor.setProperty("voice", voz.id)
            break

    motor.setProperty("rate", 170)
    motor.say(texto)
    motor.runAndWait()


def main():
    sys.stdin.reconfigure(encoding="utf-8")
    texto = sys.stdin.read().strip()
    if not texto:
        return

    if MODELO.exists():
        try:
            hablar_piper(texto)
            return
        except Exception as error:
            print(f"[Piper falló, uso la voz de Windows: {error}]", file=sys.stderr)

    hablar_windows(texto)


if __name__ == "__main__":
    main()