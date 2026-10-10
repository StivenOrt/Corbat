import ctypes
import logging
import os
import time
from urllib.parse import quote

from corbat.audio import confirmacion
from corbat.contactos import agenda
from corbat import registro  # noqa: F401

ESPERA_VENTANA = 12  # segundos máximos para que WhatsApp quede al frente
ESPERA_CHAT = 3.5  # segundos para que el chat termine de cargar
MAX_CARACTERES = 500
MAX_OPCIONES = 4

VK_ENTER = 0x0D
VK_SHIFT = 0x10
VK_CONTROL = 0x11
VK_C = 0x43  # Ctrl+Mayús+C: llamada de voz en WhatsApp Desktop
VK_V = 0x56  # Ctrl+Mayús+V: videollamada


def _pulsar(*teclas) -> None:
    """Pulsa varias teclas a la vez (la última es la que se 'toca')."""
    for tecla in teclas:
        ctypes.windll.user32.keybd_event(tecla, 0, 0, 0)
    for tecla in reversed(teclas):
        ctypes.windll.user32.keybd_event(tecla, 0, 2, 0)


def _ventana_activa() -> str:
    usuario = ctypes.windll.user32
    ventana = usuario.GetForegroundWindow()
    largo = usuario.GetWindowTextLengthW(ventana)
    texto = ctypes.create_unicode_buffer(largo + 1)
    usuario.GetWindowTextW(ventana, texto, largo + 1)
    return texto.value


def _esperar_whatsapp() -> bool:
    """Espera a que WhatsApp esté al frente; así las teclas no caen en otra ventana."""
    limite = time.monotonic() + ESPERA_VENTANA
    while time.monotonic() < limite:
        if "whatsapp" in _ventana_activa().lower():
            return True
        time.sleep(0.5)
    return False


def _elegir_contacto(contacto: str):
    """Devuelve ((nombre, numero), None) o (None, texto de error)."""
    encontrados = agenda.buscar(contacto)

    if not encontrados:
        if not agenda.cargar():
            return None, (
                "No tengo contactos. Conecta Google con python -m corbat.contactos.google "
                "o copia un archivo .vcf a la carpeta datos."
            )
        return None, f"No encuentro a '{contacto}' entre tus contactos."

    if len(encontrados) == 1:
        return encontrados[0], None

    if len(encontrados) > MAX_OPCIONES:
        return None, f"Hay muchos contactos que coinciden con '{contacto}'. Dime el nombre completo."

    indice = confirmacion.elegir(
        f"Encontré varios contactos que coinciden con {contacto}.",
        [nombre for nombre, _ in encontrados],
    )
    if indice is None:
        return None, "No elegiste ningún contacto. No hice nada."
    return encontrados[indice], None


def _abrir_chat(numero: str, texto: str = "") -> bool:
    enlace = f"whatsapp://send?phone={numero}"
    if texto:
        enlace += f"&text={quote(texto)}"
    try:
        os.startfile(enlace)
    except OSError as error:
        logging.info("WhatsApp: no se pudo abrir (%s)", error)
        return False
    return True


def enviar_whatsapp(contacto: str, mensaje: str) -> str:
    """Envía un mensaje de WhatsApp a un contacto. Pide confirmación por voz.

    Args:
        contacto: Nombre del contacto, por ejemplo mamá, Juan o Juan Pérez.
        mensaje: Texto exacto que se enviará.

    Returns:
        Resultado de la acción.
    """
    texto = mensaje.strip()
    if not texto:
        return "El mensaje está vacío."
    if len(texto) > MAX_CARACTERES:
        return "El mensaje es demasiado largo."

    elegido, error = _elegir_contacto(contacto)
    if elegido is None:
        return error
    nombre, numero = elegido

    if not confirmacion.confirmar(f"Voy a enviar por WhatsApp a {nombre} el mensaje: {texto}."):
        logging.info("enviar_whatsapp: cancelado por el usuario (%s)", nombre)
        return "El usuario no confirmó. No se envió el mensaje."

    if not _abrir_chat(numero, texto):
        return "No pude abrir WhatsApp. Revisa que esté instalado."

    if not _esperar_whatsapp():
        logging.info("enviar_whatsapp: WhatsApp no quedó al frente (%s)", nombre)
        return "WhatsApp no apareció al frente, así que no envié el mensaje."

    time.sleep(ESPERA_CHAT)
    _pulsar(VK_ENTER)

    # Solo se registra a quién se escribió, no el contenido del mensaje.
    logging.info("enviar_whatsapp: enviado a %s", nombre)
    return f"Mensaje enviado a {nombre}."


def llamar_whatsapp(contacto: str, video: bool = False) -> str:
    """Hace una llamada de WhatsApp a un contacto. Pide confirmación por voz.

    Args:
        contacto: Nombre del contacto, por ejemplo mamá, Juan o Juan Pérez.
        video: Usar true solo si el usuario pide una videollamada.

    Returns:
        Resultado de la acción.
    """
    elegido, error = _elegir_contacto(contacto)
    if elegido is None:
        return error
    nombre, numero = elegido

    tipo = "videollamada" if video else "llamada"
    if not confirmacion.confirmar(f"Voy a hacer una {tipo} de WhatsApp a {nombre}."):
        logging.info("llamar_whatsapp: cancelado por el usuario (%s)", nombre)
        return "El usuario no confirmó. No hice la llamada."

    if not _abrir_chat(numero):
        return "No pude abrir WhatsApp. Revisa que esté instalado."

    if not _esperar_whatsapp():
        logging.info("llamar_whatsapp: WhatsApp no quedó al frente (%s)", nombre)
        return "WhatsApp no apareció al frente, así que no hice la llamada."

    time.sleep(ESPERA_CHAT)
    _pulsar(VK_CONTROL, VK_SHIFT, VK_V if video else VK_C)

    logging.info("llamar_whatsapp: %s a %s", tipo, nombre)
    return f"Iniciando la {tipo} a {nombre}. Si no empieza, revisa la ventana de WhatsApp."
