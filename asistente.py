import logging
import os
import sys
import threading
from datetime import datetime

# Sin consola (pythonw) no hay salida estándar; se reemplaza para que nada falle.
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")

import ollama

import aplicaciones
import confirmacion
import escuchar
import google_contactos
import indicador
import registro  # noqa: F401
from acciones import HERRAMIENTAS, cancelar_apagado
from activacion import calibrar_ruido, capturar_frase, extraer_comando, normalizar
from atajos import intentar_atajo
from hablar import calibrar_interrupcion, hablar, liberar_voz, precargar_voz

MODELO = "qwen2.5:7b"
MAX_RONDAS = 3
MAX_TURNOS_HISTORIAL = 3
ESPERA_ORDEN = 6  # segundos que espera la orden después de "Dime"
REPOSO_SEGUNDOS = 10  # sin que nadie hable, Corbat se duerme
UMBRAL_NOMBRE_REPOSO = 0.65  # el modelo ligero oye peor: se acepta un nombre más "borroso"
SALIDAS = {"adios", "hasta luego", "salir", "cerrar asistente"}


def instrucciones():
    hoy = datetime.now().strftime("%d/%m/%Y")
    return (
        "Te llamas Corbat. Eres un asistente personal que responde por voz y "
        "controla el computador del usuario mediante herramientas. "
        "Responde siempre en español, de forma breve y natural, "
        "en una o dos frases, sin listas, sin símbolos y sin formato. "
        f"La fecha de hoy es {hoy}. Tu conocimiento propio termina en 2023, "
        "así que para noticias, precios o eventos recientes usa buscar_web. "
        "Cuando el usuario pida una acción en el computador, usa la herramienta "
        "correspondiente y luego confirma en una frase corta lo que se hizo. "
        "Para cerrar una aplicación usa cerrar_aplicacion, y usa forzar solo si "
        "el usuario lo pide expresamente. "
        "Si una herramienta dice que no pudo hacer algo, díselo al usuario con honestidad. "
        "Si el usuario confirma una acción que propusiste, llama a la herramienta "
        "inmediatamente. Nunca digas que realizaste una acción si no llamaste "
        "a la herramienta correspondiente."
    )


historial = [{"role": "system", "content": instrucciones()}]
llm_cargado = False


def rol(mensaje):
    return mensaje["role"] if isinstance(mensaje, dict) else mensaje.role


def recortar_historial():
    inicios = [i for i, m in enumerate(historial) if i > 0 and rol(m) == "user"]
    if len(inicios) > MAX_TURNOS_HISTORIAL:
        desde = inicios[-MAX_TURNOS_HISTORIAL]
        del historial[1:desde]


def ejecutar_herramienta(llamada):
    nombre = llamada.function.name
    argumentos = llamada.function.arguments
    funcion = HERRAMIENTAS.get(nombre)

    if funcion is None:
        return "Herramienta desconocida."

    print(f"[Acción: {nombre} {argumentos}]")
    try:
        resultado = str(funcion(**argumentos))
    except Exception as error:
        resultado = f"Error al ejecutar {nombre}: {error}"

    print(f"[Resultado: {resultado}]")
    visibles = {k: v for k, v in dict(argumentos).items() if k != "mensaje"}
    logging.info("Herramienta (modelo): %s %s -> %s", nombre, visibles, resultado)
    return resultado


def preguntar(texto):
    recortar_historial()
    historial[0]["content"] = instrucciones()
    historial.append({"role": "user", "content": texto})

    global llm_cargado
    llm_cargado = True

    mensaje = None
    for _ in range(MAX_RONDAS):
        respuesta = ollama.chat(
            model=MODELO,
            messages=historial,
            tools=list(HERRAMIENTAS.values()),
            keep_alive="5m",
        )
        mensaje = respuesta.message
        historial.append(mensaje)

        if not mensaje.tool_calls:
            break

        for llamada in mensaje.tool_calls:
            resultado = ejecutar_herramienta(llamada)
            historial.append(
                {
                    "role": "tool",
                    "tool_name": llamada.function.name,
                    "content": resultado,
                }
            )

    return (mensaje.content if mensaje else "") or "Listo."


def esperar_orden(umbral):
    audio = capturar_frase(umbral, espera_maxima=ESPERA_ORDEN)
    if audio is None:
        return ""
    return escuchar.transcribir(audio)


def es_cancelar_apagado(comando):
    limpio = normalizar(comando)
    return "cancel" in limpio and "apag" in limpio


def es_mensaje(comando):
    """Los mensajes (WhatsApp) no se guardan en el log."""
    primera = normalizar(comando).split(" ", 1)[0]
    return primera in {"manda", "mandale", "envia", "enviale", "escribe", "escribele"}


def despertar():
    """Carga los modelos pesados en segundo plano mientras sigues hablando."""
    for tarea in (escuchar.precargar, precargar_voz):
        threading.Thread(target=tarea, daemon=True).start()


def dormir():
    """Libera Whisper preciso, la voz y el modelo de lenguaje."""
    global llm_cargado

    indicador.estado("oculto")
    escuchar.liberar()
    liberar_voz()
    if llm_cargado:
        try:
            ollama.generate(model=MODELO, prompt="", keep_alive=0)
        except Exception as error:
            logging.info("No se pudo descargar el modelo de Ollama: %s", error)
        llm_cargado = False
    logging.info("Corbat en reposo")


def main():
    aplicaciones.precargar()
    google_contactos.sincronizar_en_segundo_plano()
    print("Calibrando ruido ambiente... guarda silencio un momento.")
    umbral = calibrar_ruido()

    print("Calibrando la voz de Corbat... guarda silencio mientras habla.")
    umbral_interrupcion = calibrar_interrupcion(umbral)
    confirmacion.configurar(umbral, umbral_interrupcion)

    escuchar.precargar(escuchar.LIGERO)
    indicador.iniciar()
    dormir()
    print("Corbat en reposo. Di 'oye Corbat' seguido de tu orden. Ctrl+C para salir.")
    pendiente = None  # audio de una interrupción por voz, aún sin procesar
    activo = False  # False: reposo (solo escucha ligera); True: modelos cargados
    recien = False  # despertó el modelo ligero y falta que el preciso confirme el nombre

    try:
        while True:
            if pendiente is not None:
                audio, pendiente = pendiente, None
            elif activo:
                audio = capturar_frase(umbral, espera_maxima=REPOSO_SEGUNDOS)
                if audio is None:
                    print("[Reposo]")
                    dormir()
                    activo = False
                    continue
            else:
                audio = capturar_frase(umbral)
                oido = escuchar.detectar(audio)
                if extraer_comando(oido, UMBRAL_NOMBRE_REPOSO) is None:
                    continue
                print("[Despertando]")
                indicador.estado("escuchando")
                despertar()
                activo = True
                recien = True

            texto = escuchar.transcribir(audio)

            comando = extraer_comando(texto) if texto else None
            if texto:
                print(f"[Oí: {texto}]")

            if comando is None:
                if recien:  # falsa alarma: no dijeron "Corbat"
                    print("[Falsa alarma]")
                    dormir()
                    activo = False
                recien = False
                continue
            recien = False

            if not comando:
                hablar("Dime.")
                comando = esperar_orden(umbral)
                if not comando:
                    print("No se detectó ninguna orden.")
                    continue
                print(f"[Oí: {comando}]")

            print("Tú:", comando)
            indicador.estado("pensando")
            privado = es_mensaje(comando)
            logging.info("Orden: %s", "(mensaje, texto omitido)" if privado else comando)

            if normalizar(comando) in SALIDAS:
                hablar("Hasta luego.")
                break

            if es_cancelar_apagado(comando):
                respuesta = cancelar_apagado()
            else:
                respuesta = intentar_atajo(comando)
                if respuesta is None:
                    logging.info("Ruta: modelo")
                    respuesta = preguntar(comando)
                else:
                    logging.info("Ruta: atajo")
                    print("[Atajo]")

            print("Corbat:", respuesta)
            if not privado:
                logging.info("Corbat: %s", respuesta)
            pendiente = hablar(respuesta, umbral, umbral_interrupcion)
    except KeyboardInterrupt:
        print("\nCorbat cerrado.")
    except Exception:
        logging.exception("Corbat se detuvo por un error")
        raise
    finally:
        indicador.cerrar()


if __name__ == "__main__":
    main()