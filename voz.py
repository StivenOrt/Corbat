import sys

import pyttsx3


def main():
    sys.stdin.reconfigure(encoding="utf-8")
    texto = sys.stdin.read().strip()
    if not texto:
        return

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


if __name__ == "__main__":
    main()