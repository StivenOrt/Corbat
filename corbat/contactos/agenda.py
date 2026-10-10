"""Lee tus contactos sin que tengas que escribirlos uno por uno.

Fuentes (todas opcionales, se combinan):
  - Cualquier archivo .vcf en la carpeta datos (exportación de Google Contactos, iPhone, Android...).
  - Cualquier archivo contactos*.csv en la carpeta datos (exportación CSV de Google Contactos).
  - Tus contactos de Google, sincronizados con corbat.contactos.google (google_contactos.json).

Los archivos se leen cada vez que cambian; no hay que reiniciar Corbat.
El código de país se toma de la variable CORBAT_CODIGO_PAIS (57 = Colombia por defecto).

Uso para revisar:
    python -m corbat.contactos.agenda                 cuántos contactos se leyeron y de dónde
    python -m corbat.contactos.agenda buscar Juan     a quién encontraría Corbat
"""
import csv
import difflib
import json
import logging
import os
import quopri
import re
import sys

from corbat import registro  # noqa: F401
from corbat import rutas
from corbat.audio.activacion import normalizar

CARPETA = rutas.DATOS
ARCHIVO_GOOGLE = CARPETA / "google_contactos.json"
CODIGO_PAIS = os.environ.get("CORBAT_CODIGO_PAIS", "57")

_cache = {"firma": None, "contactos": []}


def _numero(texto):
    """Deja solo dígitos y agrega el código de país a los números locales de 10 dígitos."""
    original = str(texto).strip()
    digitos = re.sub(r"\D", "", original)
    if not digitos:
        return ""
    if original.startswith("+"):
        return digitos
    if digitos.startswith("00"):
        return digitos[2:]
    if len(digitos) == 10:
        return CODIGO_PAIS + digitos
    return digitos


# ---------- Lectores ----------

def _leer_vcf(ruta):
    texto = ruta.read_text(encoding="utf-8", errors="replace")

    lineas = []
    for linea in texto.splitlines():
        if linea[:1] in (" ", "\t") and lineas:
            lineas[-1] += linea[1:]  # línea continuada
        elif (
            lineas
            and lineas[-1].endswith("=")
            and "QUOTED-PRINTABLE" in lineas[-1].upper()
        ):
            lineas[-1] = lineas[-1][:-1] + linea  # salto suave de quoted-printable
        else:
            lineas.append(linea)

    contactos, actual = [], None
    for linea in lineas:
        mayus = linea.upper()
        if mayus == "BEGIN:VCARD":
            actual = {"fn": "", "n": "", "tels": []}
            continue
        if mayus == "END:VCARD":
            if actual:
                nombre = actual["fn"] or actual["n"]
                celulares = [t for t, es_cel in actual["tels"] if es_cel]
                numeros = celulares or [t for t, _ in actual["tels"]]
                if nombre and numeros:
                    contactos.append((nombre, numeros[0]))
            actual = None
            continue
        if actual is None or ":" not in linea:
            continue

        propiedad, valor = linea.split(":", 1)
        if "QUOTED-PRINTABLE" in propiedad.upper():
            valor = quopri.decodestring(valor.encode("ascii", "ignore")).decode("utf-8", "replace")
        campo = propiedad.split(";")[0].split(".")[-1].upper()

        if campo == "FN":
            actual["fn"] = valor.strip()
        elif campo == "N":
            partes = valor.split(";") + ["", ""]
            actual["n"] = f"{partes[1]} {partes[0]}".strip()
        elif campo == "TEL":
            numero = _numero(valor)
            if numero:
                actual["tels"].append((numero, "CELL" in propiedad.upper()))
    return contactos


def _leer_csv(ruta):
    contactos = []
    with open(ruta, encoding="utf-8-sig", newline="") as archivo:
        for fila in csv.DictReader(archivo):
            fila = {(k or "").strip(): (v or "").strip() for k, v in fila.items()}

            nombre = fila.get("Name") or fila.get("Nombre") or ""
            if not nombre:
                trozos = [
                    fila.get("First Name") or fila.get("Given Name") or fila.get("Nombre de pila") or "",
                    fila.get("Middle Name") or "",
                    fila.get("Last Name") or fila.get("Family Name") or fila.get("Apellidos") or "",
                ]
                nombre = " ".join(t for t in trozos if t)

            numeros = []
            for columna, valor in fila.items():
                if (
                    valor
                    and re.search(r"phone|tel[eé]fono|m[oó]vil|mobile|celular", columna, re.I)
                    and not re.search(r"label|type|tipo", columna, re.I)
                ):
                    numeros += [_numero(v) for v in valor.split(":::")]
            numeros = [n for n in numeros if n]

            if nombre and numeros:
                contactos.append((nombre, numeros[0]))
    return contactos


def _leer_google():
    try:
        datos = json.loads(ARCHIVO_GOOGLE.read_text(encoding="utf-8"))
        return [(n, _numero(v)) for n, v in datos.get("contactos", []) if n and _numero(v)]
    except (OSError, ValueError, TypeError):
        return []


# ---------- Carga ----------

def _archivos():
    return sorted(CARPETA.glob("*.vcf")) + sorted(CARPETA.glob("contactos*.csv"))


def cargar():
    """Devuelve [(nombre, numero, fuente), ...] con todos los contactos disponibles."""
    fuentes = _archivos() + ([ARCHIVO_GOOGLE] if ARCHIVO_GOOGLE.exists() else [])
    firma = tuple((str(f), f.stat().st_mtime) for f in fuentes)
    if firma == _cache["firma"]:
        return _cache["contactos"]

    contactos = []
    for archivo in _archivos():
        try:
            lector = _leer_vcf if archivo.suffix.lower() == ".vcf" else _leer_csv
            contactos += [(n, num, archivo.name) for n, num in lector(archivo)]
        except (OSError, csv.Error, ValueError) as error:
            logging.warning("contactos: no pude leer %s (%s)", archivo.name, error)

    contactos += [(n, num, "Google") for n, num in _leer_google()]

    vistos, unicos = set(), []
    for nombre, numero, fuente in contactos:
        if (normalizar(nombre), numero) not in vistos:
            vistos.add((normalizar(nombre), numero))
            unicos.append((nombre, numero, fuente))

    _cache.update(firma=firma, contactos=unicos)
    logging.info("contactos: %d contactos cargados", len(unicos))
    return unicos


# ---------- Búsqueda ----------

def buscar(nombre):
    """Devuelve [(nombre, numero), ...] con los contactos que encajan con lo que se dijo."""
    consulta = re.sub(r"^(?:mi|mis|el|la|a)\s+", "", normalizar(nombre)).strip()
    contactos = [(normalizar(n), n, num) for n, num, _ in cargar()]
    if not consulta or not contactos:
        return []

    def resultado(lista):
        vistos, salida = set(), []
        for _, n, num in lista:
            if num not in vistos:
                vistos.add(num)
                salida.append((n, num))
        return salida

    # Todos los que encajan: si dices "Mario" y tienes "Mario" y "Mario Valdez",
    # salen los dos para que Corbat te pregunte a cuál te refieres.
    palabras = consulta.split()
    parciales = [
        c for c in contactos
        if all(any(p.startswith(w) for p in c[0].split()) for w in palabras)
    ]
    if parciales:
        return resultado(sorted(parciales, key=lambda c: c[0] != consulta))

    # Aproximado: el reconocimiento de voz a veces escribe mal los nombres.
    puntuados = []
    for c in contactos:
        puntaje = max(
            [difflib.SequenceMatcher(None, consulta, c[0]).ratio()]
            + [difflib.SequenceMatcher(None, consulta, p).ratio() for p in c[0].split()]
        )
        puntuados.append((puntaje, c))
    mejor = max((p for p, _ in puntuados), default=0.0)
    if mejor < 0.8:
        return []
    return resultado([c for p, c in puntuados if p >= mejor - 0.02])


if __name__ == "__main__":
    todos = cargar()
    if len(sys.argv) > 2 and sys.argv[1] == "buscar":
        for n, num in buscar(" ".join(sys.argv[2:])):
            print(f" - {n}  (termina en ...{num[-3:]})")
    else:
        origenes = {}
        for _, _, fuente in todos:
            origenes[fuente] = origenes.get(fuente, 0) + 1
        print(f"{len(todos)} contactos cargados")
        for fuente, cantidad in origenes.items():
            print(f" - {fuente}: {cantidad}")
        if not todos:
            print("Copia un archivo .vcf (o contactos.csv) de tus contactos a la carpeta datos.")
