"""Configuración única del registro de Corbat.

Todo lo que Corbat registra queda en acciones.log (junto a este archivo, sin
importar desde qué carpeta se ejecute). Los avisos y errores propios también
se muestran en la consola para no tener que abrir el archivo.

Se configura sola al importarse, así que basta con:  import registro
"""
import logging
import sys
from pathlib import Path

ARCHIVO_LOG = Path(__file__).with_name("acciones.log")


def configurar():
    raiz = logging.getLogger()
    if getattr(raiz, "_corbat_configurado", False):
        return

    raiz.setLevel(logging.INFO)

    archivo = logging.FileHandler(ARCHIVO_LOG, encoding="utf-8")
    archivo.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
    raiz.addHandler(archivo)

    # En consola solo salen los avisos de Corbat (no el ruido de otras librerías).
    consola = logging.StreamHandler(sys.stderr)
    consola.setLevel(logging.WARNING)
    consola.setFormatter(logging.Formatter("[Aviso] %(message)s"))
    consola.addFilter(lambda registro: registro.name == "root")
    raiz.addHandler(consola)

    raiz._corbat_configurado = True


configurar()
