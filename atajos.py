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
from mensajes import enviar_whatsapp, llamar_whatsapp
from musica import (
    cancion_actual,
    cancion_anterior,
    continuar_musica,
    pausar_musica,
    reproducir_me_gusta,
    reproducir_musica,
    reproducir_playlist,
    siguiente_cancion,
)

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

# Música
PATRON_REPRODUCIR_SPOTIFY = re.compile(
    r"^(?:reproduce|reproduceme|reproducir|reproduzca|pon|ponme|ponla|toca|tocame|coloca|"
    r"busca|buscame|escucha|quiero\s+(?:escuchar|oir))\s+(.+?)\s+en\s+spotify$"
)
PATRON_CONTINUAR = re.compile(
    r"^(?:reproduce|reproducir|reanuda|reanudar|continua|continuar|sigue|dale\s+play|play)"
    r"(?:\s+(?:la\s+)?(?:musica|cancion))?$"
)
# "pon" solo cuenta como pedir una canción si no va seguido de otras órdenes (volumen, pausa...).
PATRON_REPRODUCIR = re.compile(
    r"^(?:(?:reproduce|reproduceme|reproducir|reproduzca|ponme|toca|tocame|coloca|colocame|play)"
    r"|quiero\s+(?:escuchar|oir)"
    r"|pon(?!\s+(?:(?:el|la|lo)\s+)?"
    r"(?:volumen|sonido|silencio|pausa|alarma|temporizador|recordatorio|siguiente|anterior|proxima)\b))"
    r"\s+(.+)$"
)
# "Tus me gusta" / "canciones que me gustan" / "mis favoritas"
PATRON_ME_GUSTA = re.compile(
    r"^(?:(?:todas?\s+)?(?:mis|tus|las|los)\s+)?(?:canciones\s+)?"
    r"(?:que\s+(?:me|te)\s+gustan|me\s+gusta|favoritas|likes)(?:\s+de\s+spotify)?$"
)
# "mi playlist Gym" / "la lista de reproducción Para estudiar"
PATRON_PLAYLIST = re.compile(
    r"^(?:(?:mi|mis|la|el|tu|una)\s+)*(?:playlist|lista\s+de\s+reproduccion|lista)"
    r"\s+(?:llamada\s+|que\s+se\s+llama\s+|de\s+)?(.+)$"
)
PATRON_PAUSAR = re.compile(
    r"^(?:pausa|pausar|deten|detener|para|parar|stop)"
    r"(?:\s+(?:la\s+)?(?:musica|cancion|spotify|reproduccion))?$"
)
PATRON_SIGUIENTE = re.compile(
    r"^(?:(?:pasa|salta|cambia)\s+(?:(?:de|a|la|el)\s+)*(?:siguiente\s+)?(?:cancion|musica|tema)"
    r"|siguiente(?:\s+(?:cancion|tema))?|proxima(?:\s+cancion)?|next)$"
)
PATRON_ANTERIOR = re.compile(
    r"^(?:(?:vuelve|regresa|retrocede)\s+(?:(?:a|de|la|el)\s+)*(?:anterior\s+)?(?:cancion|musica|tema)"
    r"|(?:cancion\s+|tema\s+)?anterior|previous)$"
)
PATRON_QUE_SUENA = re.compile(
    r"^(?:que\s+(?:cancion|musica|tema)\s+(?:esta\s+sonando|suena|es\s+esta)"
    r"|que\s+suena|que\s+esta\s+sonando)$"
)
PREFIJO_BUSQUEDA = re.compile(
    r"^(?:algo\s+de\s+(?:la\s+)?"
    r"|(?:(?:la|el|una|un)\s+)?(?:cancion|musica|tema)\s+"
    r"(?:(?:de\s+la|del|de)\s+|llamada\s+|llamado\s+|titulada\s+|que\s+se\s+llama\s+)?)"
)

# WhatsApp: "manda un mensaje a mamá por whatsapp que ya voy"
PATRON_WHATSAPP = re.compile(
    r"^(?:manda|mandale|envia|enviale|escribe|escribele)\s+"
    r"(?:un\s+)?(?:mensaje\s+|whatsapp\s+)?(?:de\s+whatsapp\s+)?(?:a\s+)?"
    r"(?P<contacto>.+?)\s+"
    r"(?:por\s+whatsapp\s+)?"
    r"(?:que|diciendo|dile\s+que|con\s+el\s+mensaje|el\s+mensaje)\s+"
    r"(?P<mensaje>.+)$"
)

# Llamadas: "llama a Mario por whatsapp", "hazle una videollamada a mamá"
PATRON_VIDEOLLAMADA = re.compile(
    r"^(?:(?:haz|hazle|hacer)\s+(?:una\s+)?)?(?:videollamada|video\s+llamada)\s+(?:a|con)\s+"
    r"(?:mi\s+)?(?P<contacto>.+?)(?:\s+por\s+whatsapp)?$"
    r"|^(?:llama|llamale|llamar)\s+(?:a\s+)?(?:mi\s+)?(?P<contacto2>.+?)\s+(?:por\s+)?"
    r"(?:video|videollamada)(?:\s+por\s+whatsapp)?$"
)
PATRON_LLAMAR = re.compile(
    r"^(?:llama|llamale|llamar|marca|marcale)\s+(?:a\s+)?(?:mi\s+)?"
    r"(?P<contacto>.+?)(?:\s+por\s+whatsapp)?$"
)


def _limpiar(comando):
    limpio = normalizar(comando)
    limpio = re.sub(r"\b(?:por favor|porfa|ahora|ya)\b", " ", limpio)
    limpio = re.sub(r"^(?:me\s+)?(?:puedes|podrias)\s+", "", limpio)
    return re.sub(r"\s+", " ", limpio).strip()


def _consulta_musica(texto):
    return PREFIJO_BUSQUEDA.sub("", texto).strip()


def decir_fecha_hora():
    ahora = datetime.now()
    return (
        f"Hoy es {DIAS[ahora.weekday()]} {ahora.day} de {MESES[ahora.month - 1]} "
        f"de {ahora.year}, y son las {ahora:%H:%M}."
    )


def _atajo_whatsapp(comando):
    coincidencia = PATRON_WHATSAPP.match(normalizar(comando))
    if not coincidencia:
        return None

    contacto = coincidencia.group("contacto")
    cantidad = len(coincidencia.group("mensaje").split())

    # El mensaje se toma del texto original para conservar tildes y signos.
    palabras = list(re.finditer(r"\w+", comando))
    if cantidad > len(palabras):
        return None

    mensaje = comando[palabras[-cantidad].start():].strip()
    return enviar_whatsapp(contacto, mensaje)


def intentar_atajo(comando):
    """Resuelve órdenes comunes sin usar el modelo.

    Devuelve el texto de respuesta, o None si la orden debe ir al modelo.
    """
    respuesta = _atajo_whatsapp(comando)
    if respuesta is not None:
        return respuesta

    limpio = _limpiar(comando)
    if not limpio:
        return None

    coincidencia = PATRON_VIDEOLLAMADA.match(limpio)
    if coincidencia:
        return llamar_whatsapp(coincidencia.group("contacto") or coincidencia.group("contacto2"), video=True)

    coincidencia = PATRON_LLAMAR.match(limpio)
    if coincidencia:
        return llamar_whatsapp(coincidencia.group("contacto"))

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

    if PATRON_QUE_SUENA.match(limpio):
        return cancion_actual()

    if PATRON_PAUSAR.match(limpio):
        return pausar_musica()

    if PATRON_SIGUIENTE.match(limpio):
        return siguiente_cancion()

    if PATRON_ANTERIOR.match(limpio):
        return cancion_anterior()

    if PATRON_CONTINUAR.match(limpio):
        return continuar_musica()

    coincidencia = PATRON_REPRODUCIR_SPOTIFY.match(limpio) or PATRON_REPRODUCIR.match(limpio)
    if coincidencia:
        pedido = coincidencia.group(1)
        if PATRON_ME_GUSTA.match(pedido):
            return reproducir_me_gusta()
        lista = PATRON_PLAYLIST.match(pedido)
        if lista:
            return reproducir_playlist(lista.group(1))
        consulta = _consulta_musica(pedido)
        if consulta:
            return reproducir_musica(consulta)

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