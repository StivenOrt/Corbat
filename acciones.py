import ctypes
import logging
import os
import subprocess
import webbrowser
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from ddgs import DDGS
from confirmacion import confirmar
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

import aplicaciones
import registro  # noqa: F401  (configura acciones.log y los avisos en consola)

EXTENSIONES_PROHIBIDAS = {
    ".exe", ".bat", ".cmd", ".ps1", ".msi", ".vbs", ".js", ".lnk", ".scr", ".com",
}

VK_VOLUMEN_SILENCIO = 0xAD
VK_VOLUMEN_BAJAR = 0xAE
VK_VOLUMEN_SUBIR = 0xAF

SEGUNDOS_APAGADO = 10


def _resolver_aplicacion(nombre: str):
    """Nombre de la aplicación instalada que corresponde a lo dicho, o None."""
    app = aplicaciones.buscar_app(nombre)
    return app[0] if app else None



def _carpetas_usuario() -> list[Path]:
    casa = Path.home()
    nombres = ["Desktop", "Escritorio", "Documents", "Documentos", "Downloads", "Descargas"]
    bases = [casa, casa / "OneDrive"]
    carpetas = []
    for base in bases:
        for nombre in nombres:
            carpeta = base / nombre
            if carpeta.is_dir():
                carpetas.append(carpeta)
    return carpetas


def _pulsar_tecla(codigo: int, veces: int = 1) -> None:
    for _ in range(veces):
        ctypes.windll.user32.keybd_event(codigo, 0, 0, 0)
        ctypes.windll.user32.keybd_event(codigo, 0, 2, 0)


def obtener_fecha_hora() -> str:
    """Obtiene la fecha y la hora actuales del computador.

    Returns:
        Fecha y hora actuales.
    """
    return datetime.now().strftime("%d/%m/%Y %H:%M")


def abrir_aplicacion(nombre: str) -> str:
    """Abre una aplicación instalada en el computador.

    Args:
        nombre: Nombre de la aplicación, por ejemplo bloc de notas, calculadora, spotify o word.

    Returns:
        Resultado de la acción.
    """
    app = aplicaciones.buscar_app(nombre)

    if app is None:
        return f"No encontré ninguna aplicación instalada llamada '{nombre}'."

    try:
        aplicaciones.abrir(*app)
    except OSError as error:
        logging.warning("abrir_aplicacion: no se pudo abrir %s (%s)", app[0], error)
        return f"No pude abrir {app[0]}."

    logging.info("abrir_aplicacion: %s", app[0])
    return f"Se abrió {app[0]}."


def cerrar_aplicacion(nombre: str, forzar: bool = False) -> str:
    """Cierra una aplicación que está abierta.

    Args:
        nombre: Nombre de la aplicación, por ejemplo bloc de notas, spotify o brave.
        forzar: Usar true solo si el usuario pide forzar el cierre porque la aplicación no se cerró normalmente.

    Returns:
        Resultado de la acción.
    """
    app = aplicaciones.buscar_app(nombre)

    if app is None:
        return f"No encontré ninguna aplicación instalada llamada '{nombre}'."

    if forzar and not confirmar(
        f"Corbat quiere FORZAR el cierre de {app[0]}. Se puede perder trabajo sin guardar."
    ):
        logging.info("cerrar_aplicacion: forzado cancelado por el usuario (%s)", app[0])
        return "El usuario no confirmó. No se cerró la aplicación."

    resultado = aplicaciones.cerrar(*app, forzar=forzar)
    logging.info("cerrar_aplicacion: %s (forzar=%s) -> %s", app[0], forzar, resultado)
    return resultado


def abrir_pagina_web(url: str) -> str:
    """Abre una página web en el navegador predeterminado.

    Args:
        url: Dirección de la página, por ejemplo https://www.google.com.

    Returns:
        Resultado de la acción.
    """
    if "://" not in url:
        url = "https://" + url

    analizada = urlparse(url)
    if analizada.scheme not in ("http", "https") or not analizada.netloc:
        return "La dirección no es válida."

    webbrowser.open(url)
    logging.info("abrir_pagina_web: %s", url)
    return f"Se abrió {url}."


def buscar_archivo(nombre: str) -> str:
    """Busca archivos por nombre en Escritorio, Documentos y Descargas.

    Args:
        nombre: Parte del nombre del archivo a buscar.

    Returns:
        Rutas de los archivos encontrados.
    """
    texto = nombre.strip().lower()
    encontrados = []

    for carpeta in _carpetas_usuario():
        for raiz, _, archivos in os.walk(carpeta):
            for archivo in archivos:
                if texto in archivo.lower():
                    encontrados.append(str(Path(raiz) / archivo))
                    if len(encontrados) >= 5:
                        break
            if len(encontrados) >= 5:
                break
        if len(encontrados) >= 5:
            break

    logging.info("buscar_archivo: %s -> %d resultados", nombre, len(encontrados))

    if not encontrados:
        return "No se encontró ningún archivo con ese nombre."
    return "\n".join(encontrados)


def abrir_archivo(ruta: str) -> str:
    """Abre un archivo que esté en Escritorio, Documentos o Descargas.

    Args:
        ruta: Ruta completa del archivo, obtenida con buscar_archivo.

    Returns:
        Resultado de la acción.
    """
    archivo = Path(ruta).resolve()

    if not archivo.is_file():
        return "El archivo no existe."

    if archivo.suffix.lower() in EXTENSIONES_PROHIBIDAS:
        return "Por seguridad no puedo abrir ese tipo de archivo."

    permitido = any(
        carpeta.resolve() in archivo.parents for carpeta in _carpetas_usuario()
    )
    if not permitido:
        return "Solo puedo abrir archivos de Escritorio, Documentos o Descargas."

    os.startfile(archivo)
    logging.info("abrir_archivo: %s", archivo)
    return f"Se abrió {archivo.name}."


def subir_volumen(veces: int = 5) -> str:
    """Sube el volumen del computador. Cada paso equivale a un 2 por ciento.

    Args:
        veces: Cantidad de pasos a subir, de 1 a 50.

    Returns:
        Resultado de la acción.
    """
    veces = max(1, min(int(veces), 50))
    _pulsar_tecla(VK_VOLUMEN_SUBIR, veces)
    logging.info("subir_volumen: %d", veces)
    return f"Volumen subido {veces * 2} por ciento."


def bajar_volumen(veces: int = 5) -> str:
    """Baja el volumen del computador. Cada paso equivale a un 2 por ciento.

    Args:
        veces: Cantidad de pasos a bajar, de 1 a 50.

    Returns:
        Resultado de la acción.
    """
    veces = max(1, min(int(veces), 50))
    _pulsar_tecla(VK_VOLUMEN_BAJAR, veces)
    logging.info("bajar_volumen: %d", veces)
    return f"Volumen bajado {veces * 2} por ciento."


def silenciar_volumen() -> str:
    """Silencia o reactiva el sonido del computador.

    Returns:
        Resultado de la acción.
    """
    _pulsar_tecla(VK_VOLUMEN_SILENCIO)
    logging.info("silenciar_volumen")
    return "Se cambió el estado del silencio."


def apagar_equipo() -> str:
    """Apaga el computador en pocos segundos. Requiere confirmación del usuario.

    Returns:
        Resultado de la acción.
    """
    if not confirmar(f"Corbat quiere APAGAR el equipo en {SEGUNDOS_APAGADO} segundos."):
        logging.info("apagar_equipo: cancelado por el usuario")
        return "El usuario no confirmó. No se apagó el equipo."

    resultado = subprocess.run(
        ["shutdown", "/s", "/t", str(SEGUNDOS_APAGADO)],
        capture_output=True,
        text=True,
        errors="replace",
    )

    if resultado.returncode != 0:
        error = (resultado.stderr or resultado.stdout).strip()
        logging.info("apagar_equipo: falló (%s) %s", resultado.returncode, error)
        return f"No se pudo programar el apagado: {error}"

    logging.info("apagar_equipo: programado en %d segundos", SEGUNDOS_APAGADO)
    return f"El equipo se apagará en {SEGUNDOS_APAGADO} segundos."


def cancelar_apagado() -> str:
    """Cancela un apagado del computador que estaba programado.

    Returns:
        Resultado de la acción.
    """
    resultado = subprocess.run(["shutdown", "/a"], capture_output=True)

    if resultado.returncode != 0:
        logging.info("cancelar_apagado: no había apagado programado")
        return "No había ningún apagado programado."

    logging.info("cancelar_apagado")
    return "Se canceló el apagado."


def buscar_web(consulta: str) -> str:
    """Busca información actual en internet.

    Args:
        consulta: Texto a buscar en la web.

    Returns:
        Resumen de los resultados encontrados.
    """
    try:
        resultados = DDGS().text(consulta, max_results=4)
    except Exception as error:
        return f"No se pudo buscar en internet: {error}"

    if not resultados:
        return "No se encontraron resultados."

    return "\n".join(f"{r['title']}: {r['body']}" for r in resultados)


HERRAMIENTAS = {
    funcion.__name__: funcion
    for funcion in (
        obtener_fecha_hora,
        abrir_aplicacion,
        cerrar_aplicacion,
        abrir_pagina_web,
        buscar_archivo,
        abrir_archivo,
        subir_volumen,
        bajar_volumen,
        silenciar_volumen,
        apagar_equipo,
        buscar_web,
        reproducir_musica,
        reproducir_playlist,
        reproducir_me_gusta,
        pausar_musica,
        continuar_musica,
        siguiente_cancion,
        cancion_anterior,
        cancion_actual,
        enviar_whatsapp,
        llamar_whatsapp,
    )
}