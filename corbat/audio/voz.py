import json
import os
import sys
import tempfile
import wave
import winsound

from corbat import rutas

MODELO = rutas.VOCES / "es_MX-claude-high.onnx"
CARPETA = tempfile.gettempdir()


def enviar(mensaje):
    sys.stdout.write(json.dumps(mensaje) + "\n")
    sys.stdout.flush()


def cargar_motor():
    if MODELO.exists():
        try:
            from piper import PiperVoice

            voz = PiperVoice.load(str(MODELO))

            def sintetizar(texto, ruta):
                with wave.open(ruta, "wb") as archivo:
                    voz.synthesize_wav(texto, archivo)

            return sintetizar
        except Exception as error:
            print(f"[Piper no disponible, uso la voz de Windows: {error}]", file=sys.stderr)

    import pyttsx3

    motor = pyttsx3.init()

    for voz in motor.getProperty("voices"):
        identificador = voz.id.lower()
        nombre = voz.name.lower()
        if "_es-" in identificador or "spanish" in nombre or "español" in nombre:
            motor.setProperty("voice", voz.id)
            break

    motor.setProperty("rate", 170)

    def sintetizar(texto, ruta):
        motor.save_to_file(texto, ruta)
        motor.runAndWait()

    return sintetizar


def duracion_wav(ruta):
    with wave.open(ruta, "rb") as archivo:
        return archivo.getnframes() / float(archivo.getframerate())


def main():
    sys.stdin.reconfigure(encoding="utf-8")
    sintetizar = cargar_motor()

    # Calentamiento: la primera síntesis siempre es la más lenta.
    try:
        sintetizar("Hola.", os.path.join(CARPETA, "corbat_calentamiento.wav"))
    except Exception as error:
        print(f"[Error en el calentamiento de la voz: {error}]", file=sys.stderr)

    enviar({"listo": True})

    indice = 0
    for linea in sys.stdin:
        try:
            orden = json.loads(linea)
        except ValueError:
            continue

        comando = orden.get("cmd")

        if comando == "parar":
            winsound.PlaySound(None, winsound.SND_PURGE)
            continue

        if comando != "hablar":
            continue

        texto = (orden.get("texto") or "").strip()
        if not texto:
            enviar({"duracion": 0})
            continue

        # Se alternan dos archivos para no pisar el que aún está sonando.
        ruta = os.path.join(CARPETA, f"corbat_voz_{indice}.wav")
        indice = 1 - indice

        try:
            sintetizar(texto, ruta)
            duracion = duracion_wav(ruta)
            winsound.PlaySound(ruta, winsound.SND_FILENAME | winsound.SND_ASYNC)
        except Exception as error:
            print(f"[Error al hablar: {error}]", file=sys.stderr)
            enviar({"duracion": 0})
            continue

        enviar({"duracion": duracion})


if __name__ == "__main__":
    main()