import ctypes
import difflib
import json
import logging
import os
import re
import time
from pathlib import Path
from urllib.parse import quote

import registro  # noqa: F401
from activacion import normalizar

ARCHIVO_CONTACTOS = Path(__file__).with_name("contactos.json")
ESPERA_WHATSAPP = 5  # segundos para que WhatsApp abra el chat con el texto
MAX_CARACTERES = 500
VK_ENTER = 0x0D


def _confirmar(descripcion: str) -> bool:
    respuesta = input(f"\n[Confirmación] {descripcion} ¿Confirmas? (s/n): ")
    return respuesta.strip().lower() in ("s", "si", "sí")


def _cargar_contactos() -> dict:
    if not ARCHIVO_CONTACTOS.exists():
        return {}

    try:
        with open(ARCHIVO_CONTACTOS, encoding="utf-8") as archivo:
            datos = json.load(archivo)
    except (OSError, ValueError):
        return {}

    return {
        normalizar(nombre): (nombre, re.sub(r"\D", "", str(numero)))
        for nombre, numero in datos.items()
    }


def _buscar_contacto(nombre: str):
    contactos = _cargar_contactos()
    clave = normalizar(nombre)
    sin_articulo = re.sub(r"^(?:mi|el|la)\s+", "", clave)

    for candidato in (clave, sin_articulo):
        if candidato in contactos:
            return contactos[candidato]

    parecidos = difflib.get_close_matches(sin_articulo, contactos.keys(), n=1, cutoff=0.75)
    if parecidos:
        return contactos[parecidos[0]]

    return None


def _pulsar_enter() -> None:
    ctypes.windll.user32.keybd_event(VK_ENTER, 0, 0, 0)
    ctypes.windll.user32.keybd_event(VK_ENTER, 0, 2, 0)


def enviar_whatsapp(contacto: str, mensaje: str) -> str:
    """Envía un mensaje de WhatsApp a un contacto guardado. Requiere confirmación escrita.

    Args:
        contacto: Nombre del contacto tal como está guardado, por ejemplo mamá o Juan.
        mensaje: Texto exacto que se enviará.

    Returns:
        Resultado de la acción.
    """
    encontrado = _buscar_contacto(contacto)

    if encontrado is None:
        nombres = ", ".join(nombre for nombre, _ in _cargar_contactos().values())
        if not nombres:
            return "No tengo contactos guardados. Agrégalos en el archivo contactos.json."
        return f"No encuentro a '{contacto}'. Tengo guardados: {nombres}."

    nombre, numero = encontrado
    texto = mensaje.strip()

    if not texto:
        return "El mensaje está vacío."
    if len(texto) > MAX_CARACTERES:
        return "El mensaje es demasiado largo."

    if not _confirmar(f'Enviar por WhatsApp a {nombre}: "{texto}".'):
        logging.info("enviar_whatsapp: cancelado por el usuario (%s)", nombre)
        return "El usuario no confirmó. No se envió el mensaje."

    try:
        os.startfile(f"whatsapp://send?phone={numero}&text={quote(texto)}")
    except OSError as error:
        logging.info("enviar_whatsapp: no se pudo abrir WhatsApp (%s)", error)
        return "No pude abrir WhatsApp. Revisa que esté instalado."

    time.sleep(ESPERA_WHATSAPP)
    _pulsar_enter()

    # Solo se registra a quién se escribió, no el contenido del mensaje.
    logging.info("enviar_whatsapp: enviado a %s", nombre)
    return f"Mensaje enviado a {nombre}."