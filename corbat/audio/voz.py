import hashlib
import json
import os
import shutil
import sys
import tempfile
import wave
import winsound

from corbat import rutas

MODELO = rutas.VOCES / "es_MX-claude-high.onnx"
CARPETA = tempfile.gettempdir()

VELOCIDAD = 0.92  # length_scale de Piper: menos de 1 habla un poco más rápido
CACHE = rutas.DATOS / "cache_voz"  # frases ya sintetizadas: la segunda vez suenan al instante
MAX_CARACTERES_CACHE = 80
MAX_ARCHIVOS_CACHE = 300


def enviar(mensaje):
    sys.stdout.write(json.dumps(mensaje) + "\n")
    sys.stdout.flush()


def cargar_motor():
    if MODELO.exists():
        try:
            from piper import PiperVoice

            voz = PiperVoice.load(str(MODELO))
            ajustes = {"usar": True}

            try:
                from piper import SynthesisConfig

                configuracion = SynthesisConfig(length_scale=VELOCIDAD)
            except (ImportError, TypeError):
                configuracion = None

            def sintetizar(texto, ruta):
                with wave.open(ruta, "wb") as archivo:
                    if configuracion is not None and ajustes["usar"]:
                        try:
                            voz.synthesize_wav(texto, archivo, syn_config=configuracion)
                            return
                        except TypeError:  # versión de Piper sin ese parámetro
                            ajustes["usar"] = False
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


def ruta_en_cache(texto):
    clave = hashlib.sha1(f"{MODELO.name}|{VELOCIDAD}|{texto}".encode("utf-8")).hexdigest()
    return CACHE / f"{clave}.wav"


def guardar_en_cache(origen, destino):
    try:
        CACHE.mkdir(parents=True, exist_ok=True)
        archivos = sorted(CACHE.glob("*.wav"), key=lambda a: a.stat().st_mtime)
        for viejo in archivos[: max(0, len(archivos) - MAX_ARCHIVOS_CACHE + 1)]:
            viejo.unlink(missing_ok=True)
        parcial = destino.with_suffix(".parte")
        shutil.copyfile(origen, parcial)
        os.replace(parcial, destino)
    except OSError:
        pass  # la caché es solo una ayuda: si falla, se habla igual


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

        en_cache = ruta_en_cache(texto)

        try:
            if en_cache.exists():
                ruta = str(en_cache)
            else:
                # Se alternan dos archivos para no pisar el que aún está sonando.
                ruta = os.path.join(CARPETA, f"corbat_voz_{indice}.wav")
                indice = 1 - indice
                sintetizar(texto, ruta)
                if len(texto) <= MAX_CARACTERES_CACHE:
                    guardar_en_cache(ruta, en_cache)
            duracion = duracion_wav(ruta)
            winsound.PlaySound(ruta, winsound.SND_FILENAME | winsound.SND_ASYNC)
        except Exception as error:
            print(f"[Error al hablar: {error}]", file=sys.stderr)
            enviar({"duracion": 0})
            continue

        enviar({"duracion": duracion})


if __name__ == "__main__":
    main()