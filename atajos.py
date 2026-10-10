import re
from datetime import datetime

from acciones import (
    _resolver_aplicacion,
    abrir_aplicacion,
    apagar_equipo,
    bajar_volumen,
    cerrar_aplicacion,
    silenciar_volumen,
    subir_volumen,
)
from activacion import normalizar

DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MESES = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]

ARTICULOS = r"(?:(?:el|la|los|las|mi|un|una|aplicacion|programa|app)\s+)*"

PATRON_ABRIR = re.compile(rf"^(?:abre|abrir|abreme|inicia|ejecuta|lanza)\s+{ARTICULOS}(.+)$")
PATRON_CERRAR = re.compile(rf"^(?:cierra|cerrar|cierrame|termina)\s+{ARTICULOS}(.+)$")
PATRON_FORZAR = re.compile(
    rf"^(?:fuerza|forzar)\s+(?:el\s+)?(?:cierre\s+)?(?:de\s+)?{ARTICULOS}(.+)$"
)
PATRON_SUBIR = re.compile(r"^(?:sube|subir|aumenta|aumentar)\s+(?:el\s+)?volumen(?:\s+un\s+poco)?$")
PATRON_BAJAR = re.compile(r"^(?:baja|bajar|disminuye|reduce)\s+(?:el\s+)?volumen(?:\s+un\s+poco)?$")
PATRON_SILENCIO = re.compile(
    r"^(?:silencia|silenciar|mutea)(?:\s+(?:el\s+)?(?:volumen|sonido|audio))?$"
)
PATRON_HORA = re.compile(
    r"^(?:(?:que|cual)\s+(?:hora|fecha|dia)\s+es(?:\s+hoy)?|(?:dime\s+)?la\s+(?:hora|fecha))$"
)
PATRON_APAGAR = re.compile(
    r"^(?:apaga|apagar)\s+(?:el\s+)?(?:equipo|computador|computadora|pc|ordenador)$"
)


def _limpiar(comando):
    limpio = normalizar(comando)
    limpio = re.sub(r"\b(?:por favor|porfa|ahora|ya)\b", " ", limpio)
    limpio = re.sub(r"^(?:me\s+)?(?:puedes|podrias)\s+", "", limpio)
    return re.sub(r"\s+", " ", limpio).strip()


def decir_fecha_hora():
    ahora = datetime.now()
    return (
        f"Hoy es {DIAS[ahora.weekday()]} {ahora.day} de {MESES[ahora.month - 1]} "
        f"de {ahora.year}, y son las {ahora:%H:%M}."
    )


def intentar_atajo(comando):
    """Resuelve órdenes comunes sin usar el modelo.

    Devuelve el texto de respuesta, o None si la orden debe ir al modelo.
    """
    limpio = _limpiar(comando)
    if not limpio:
        return None

    if PATRON_HORA.match(limpio):
        return decir_fecha_hora()

    if PATRON_SUBIR.match(limpio):
        return subir_volumen()

    if PATRON_BAJAR.match(limpio):
        return bajar_volumen()

    if PATRON_SILENCIO.match(limpio):
        return silenciar_volumen()

    if PATRON_APAGAR.match(limpio):
        return apagar_equipo()

    coincidencia = PATRON_FORZAR.match(limpio)
    if coincidencia:
        nombre = coincidencia.group(1)
        if _resolver_aplicacion(nombre):
            return cerrar_aplicacion(nombre, forzar=True)
        return None

    coincidencia = PATRON_CERRAR.match(limpio)
    if coincidencia:
        nombre = coincidencia.group(1)
        if _resolver_aplicacion(nombre):
            return cerrar_aplicacion(nombre)
        return None

    coincidencia = PATRON_ABRIR.match(limpio)
    if coincidencia:
        nombre = coincidencia.group(1)
        if _resolver_aplicacion(nombre):
            return abrir_aplicacion(nombre)
        return None

    return None