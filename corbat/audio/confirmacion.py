"""Confirmaciones por voz: Corbat pregunta y tú respondes hablando.

Si todavía no se han calibrado los micrófonos (por ejemplo, al probar un módulo
suelto), las preguntas se hacen por escrito en la terminal.
"""
import difflib
import logging
import re

from corbat import registro  # noqa: F401
from corbat.audio.activacion import capturar_frase, normalizar
from corbat.audio.hablar import hablar

ESPERA_RESPUESTA = 8  # segundos que espera tu respuesta
INTENTOS = 2

PALABRAS_SI = {
    "si", "claro", "confirmo", "confirmado", "confirma", "dale", "adelante", "ok", "okay",
    "vale", "hazlo", "correcto", "afirmativo", "seguro", "envialo", "enviala", "llamalo",
    "llamala", "listo", "exacto", "efectivamente",
}
PALABRAS_NO = {
    "no", "cancela", "cancelar", "cancelalo", "detente", "para", "negativo", "nada",
    "olvidalo", "nunca", "ninguno", "ninguna", "nadie", "alto",
}
ORDINALES = {
    "primero": 0, "primera": 0, "uno": 0, "1": 0,
    "segundo": 1, "segunda": 1, "dos": 1, "2": 1,
    "tercero": 2, "tercera": 2, "tres": 2, "3": 2,
    "cuarto": 3, "cuarta": 3, "cuatro": 3, "4": 3,
    "ultimo": -1, "ultima": -1,
}
RELLENO = {
    "solo", "el", "la", "los", "las", "a", "de", "del", "al", "ese", "esa", "pues", "mejor",
    "quiero", "es", "con", "al", "para", "por", "favor", "porfa", "que", "se", "llama",
}

_estado = {"umbral": None, "interrupcion": None}


def configurar(umbral, umbral_interrupcion):
    """Se llama una vez, después de calibrar el micrófono."""
    _estado.update(umbral=umbral, interrupcion=umbral_interrupcion)


def disponible():
    return _estado["umbral"] is not None


def decible(texto):
    """Quita emojis y símbolos para que la voz no los lea."""
    limpio = re.sub(r"[^\w\s&'.,-]", "", texto).strip()
    return limpio or texto


def _preguntar(texto):
    """Dice el texto y devuelve lo que respondas ('' si nadie habla)."""
    from corbat.audio.escuchar import transcribir  # se carga aquí para no cargar Whisper al importar

    print(f"[Corbat pregunta: {texto}]")
    audio = hablar(texto, _estado["umbral"], _estado["interrupcion"])
    if audio is None:  # si lo interrumpiste, esa interrupción ya es tu respuesta
        audio = capturar_frase(_estado["umbral"], espera_maxima=ESPERA_RESPUESTA)
    if audio is None:
        return ""

    respuesta = transcribir(audio)
    print(f"[Oí: {respuesta}]")
    return respuesta


def interpretar_si_no(texto):
    """True si es un sí, False si es un no, None si no se entiende."""
    palabras = set(normalizar(texto).split())
    if palabras & PALABRAS_NO:
        return False  # ante la duda ("no, sí...") se cancela
    if palabras & PALABRAS_SI:
        return True
    return None


def confirmar(descripcion):
    """Pregunta '¿Confirmas?' y devuelve True solo si respondes que sí."""
    if not disponible():
        respuesta = input(f"\n[Confirmación] {descripcion} ¿Confirmas? (s/n): ")
        return respuesta.strip().lower() in ("s", "si", "sí")

    pregunta = f"{decible(descripcion)} ¿Confirmas?"
    for intento in range(INTENTOS):
        respuesta = _preguntar(pregunta if intento == 0 else "No te entendí. Responde sí o no.")
        decision = interpretar_si_no(respuesta)
        if decision is not None:
            logging.info("confirmación por voz: %s", "sí" if decision else "no")
            return decision

    logging.info("confirmación por voz: sin respuesta clara, se cancela")
    return False


def interpretar_eleccion(texto, opciones):
    """Índice de la opción que se dijo, o None si no se entiende."""
    palabras = normalizar(texto).split()
    limpio = [p for p in palabras if p not in RELLENO]
    if not limpio:
        return None

    nombres = [normalizar(decible(o)) for o in opciones]
    dicho = " ".join(limpio)

    exactos = [i for i, n in enumerate(nombres) if n == dicho]
    if len(exactos) == 1:
        return exactos[0]

    # Palabras que solo tiene una opción ("Valdez" distingue a Mario Valdez de Mario).
    candidatos = []
    for i, nombre in enumerate(nombres):
        de_otros = {w for j, n in enumerate(nombres) if j != i for w in n.split()}
        distintivas = set(nombre.split()) - de_otros
        if distintivas and distintivas <= set(limpio):
            candidatos.append(i)
    if len(candidatos) == 1:
        return candidatos[0]

    for p in palabras:
        if p in ORDINALES:
            indice = ORDINALES[p]
            indice = len(opciones) - 1 if indice == -1 else indice
            if indice < len(opciones):
                return indice

    puntajes = sorted(
        ((difflib.SequenceMatcher(None, dicho, n).ratio(), i) for i, n in enumerate(nombres)),
        reverse=True,
    )
    if puntajes[0][0] >= 0.8 and (len(puntajes) == 1 or puntajes[0][0] - puntajes[1][0] > 0.1):
        return puntajes[0][1]
    return None


def elegir(pregunta, opciones):
    """Pide que elijas entre varias opciones. Devuelve su índice, o None si cancelas."""
    if not disponible():
        print(f"\n[Corbat] {pregunta}")
        for numero, opcion in enumerate(opciones, 1):
            print(f"  {numero}. {opcion}")
        respuesta = input("Elige un número (Enter para cancelar): ").strip()
        return int(respuesta) - 1 if respuesta.isdigit() and 0 < int(respuesta) <= len(opciones) else None

    lista = ", ".join(decible(o) for o in opciones[:-1]) + f", o {decible(opciones[-1])}"
    for intento in range(INTENTOS):
        texto = (
            f"{pregunta} ¿Cuál es: {lista}?"
            if intento == 0
            else f"No te entendí. ¿Cuál: {lista}? O di cancelar."
        )
        respuesta = _preguntar(texto)

        if set(normalizar(respuesta).split()) & {"cancela", "cancelar", "ninguno", "ninguna", "nadie", "olvidalo"}:
            logging.info("elección por voz: cancelada")
            return None
        indice = interpretar_eleccion(respuesta, opciones)
        if indice is not None:
            logging.info("elección por voz: opción %d de %d", indice + 1, len(opciones))
            return indice

    logging.info("elección por voz: sin respuesta clara, se cancela")
    return None
