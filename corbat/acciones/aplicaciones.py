"""Descubre las aplicaciones instaladas en Windows y las abre o cierra por su nombre.

No hay listas que mantener: se leen del menú Inicio (Get-StartApps), así que funciona
igual en cualquier computador con las apps que tenga instaladas.

Uso para revisar:
    python -m corbat.acciones.aplicaciones              lista las apps detectadas
    python -m corbat.acciones.aplicaciones buscar spotify   muestra qué app entendería Corbat
"""
import json
import logging
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

from corbat import registro  # noqa: F401
from corbat.audio.activacion import normalizar

# Grupos de nombres que significan lo mismo (según el idioma de Windows o cómo lo dicte la voz).
SINONIMOS = [
    ("bloc de notas", "notepad", "blog de notas", "block de notas", "bloc"),
    ("calculadora", "calculator"),
    ("explorador de archivos", "explorador", "file explorer"),
    ("configuracion", "ajustes", "settings"),
    ("visual studio code", "vs code", "vscode", "code"),
    ("google chrome", "chrome"),
    ("microsoft edge", "edge"),
    ("windows terminal", "terminal"),
    ("administrador de tareas", "task manager"),
    ("paint", "pintura"),
    ("simbolo del sistema", "command prompt", "cmd"),
]
NAVEGADORES = ["brave", "google chrome", "microsoft edge", "firefox", "opera"]

# "abre el archivo X", "abre la carpeta X"... no piden una aplicación.
NO_SON_APPS = {
    "archivo", "carpeta", "documento", "pagina", "sitio", "web", "url", "internet",
    "enlace", "link", "video", "foto", "imagen", "cancion", "musica",
}

# Nunca se cierran, aunque se pidan.
PROTEGIDOS = {
    "explorer", "dwm", "winlogon", "csrss", "lsass", "services", "svchost", "system",
    "smss", "wininit", "searchhost", "startmenuexperiencehost", "shellexperiencehost",
    "textinputhost", "applicationframehost", "ctfmon", "python", "pythonw", "py",
    "cmd", "conhost", "openconsole", "powershell", "pwsh",
}

CARPETAS_INICIO = [
    Path(os.environ.get("ProgramData", r"C:\ProgramData")) / "Microsoft/Windows/Start Menu/Programs",
    Path(os.environ.get("APPDATA", "")) / "Microsoft/Windows/Start Menu/Programs",
]

_cache = {"apps": None, "hora": 0.0}
_bloqueo = threading.Lock()


def _powershell(script, tiempo=20):
    resultado = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "[Console]::OutputEncoding=[Text.Encoding]::UTF8;" + script],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=tiempo,
    )
    return resultado.stdout.strip()


def _json_lista(texto):
    if not texto:
        return []
    datos = json.loads(texto)
    return datos if isinstance(datos, list) else [datos]


# ---------- Descubrimiento ----------

def _apps_desde_inicio_alterno():
    """Respaldo si PowerShell falla: lee los accesos directos del menú Inicio."""
    encontradas = []
    for carpeta in CARPETAS_INICIO:
        if not carpeta.is_dir():
            continue
        for acceso in carpeta.rglob("*.lnk"):
            encontradas.append((acceso.stem, str(acceso)))
    return encontradas


def _leer_apps():
    try:
        datos = _json_lista(_powershell("Get-StartApps | ConvertTo-Json -Compress"))
        apps = [(d["Name"], d["AppID"]) for d in datos if d.get("Name") and d.get("AppID")]
    except (subprocess.SubprocessError, OSError, ValueError, KeyError) as error:
        logging.warning("aplicaciones: Get-StartApps falló (%s); leo el menú Inicio", error)
        apps = _apps_desde_inicio_alterno()

    limpias, vistos = [], set()
    for nombre, appid in apps:
        norm = normalizar(nombre)
        if re.search(r"\b(?:desinstal\w*|uninstall\w*)\b", norm) or norm in vistos:
            continue
        vistos.add(norm)
        limpias.append((nombre, appid))
    logging.info("aplicaciones: %d aplicaciones detectadas", len(limpias))
    return limpias


def listar_apps(refrescar=False):
    """Devuelve [(nombre, appid), ...] de las aplicaciones instaladas."""
    with _bloqueo:
        vieja = time.monotonic() - _cache["hora"] > 60
        if _cache["apps"] is None or (refrescar and vieja):
            _cache["apps"] = _leer_apps()
            _cache["hora"] = time.monotonic()
        return _cache["apps"]


def precargar():
    """Lee las aplicaciones en segundo plano para que la primera orden no espere."""
    threading.Thread(target=listar_apps, daemon=True).start()


# ---------- Búsqueda por nombre ----------

def _limpiar(texto):
    consulta = normalizar(texto)
    return re.sub(r"^(?:(?:el|la|los|las|mi|un|una|aplicacion|programa|app)\s+)+", "", consulta).strip()


def _variantes(consulta):
    if consulta in ("navegador", "el navegador"):
        return NAVEGADORES
    for grupo in SINONIMOS:
        if consulta in grupo:
            return [consulta] + [g for g in grupo if g != consulta]
    return [consulta]


def _emparejar(consulta, apps):
    nombres = [(normalizar(n), n, i) for n, i in apps]
    variantes = _variantes(consulta)

    for v in variantes:  # 1. nombre exacto
        for norm, n, i in nombres:
            if norm == v:
                return n, i

    for v in variantes:  # 2. todas las palabras dichas están en el nombre de la app
        palabras = set(v.split())
        contienen = [x for x in nombres if palabras <= set(x[0].split())]
        if contienen:
            elegida = min(contienen, key=lambda x: len(x[0]))
            return elegida[1], elegida[2]

    for v in variantes:  # 3. el nombre de la app está dentro de lo dicho ("brave browser")
        palabras = set(v.split())
        dentro = [
            x for x in nombres
            if len(x[0].replace(" ", "")) >= 4 and set(x[0].split()) <= palabras
        ]
        if dentro:
            elegida = max(dentro, key=lambda x: len(x[0]))
            return elegida[1], elegida[2]

    import difflib  # 4. parecido (la voz escribe mal algunos nombres)

    mejor, puntaje = None, 0.0
    for norm, n, i in nombres:
        p = difflib.SequenceMatcher(None, consulta, norm).ratio()
        if p > puntaje:
            mejor, puntaje = (n, i), p
    return mejor if puntaje >= 0.8 else None


def buscar_app(nombre):
    """Devuelve (nombre, appid) de la app instalada que se pidió, o None."""
    consulta = _limpiar(nombre)
    if not consulta or consulta.split()[0] in NO_SON_APPS:
        return None

    encontrada = _emparejar(consulta, listar_apps())
    if encontrada is None:
        encontrada = _emparejar(consulta, listar_apps(refrescar=True))  # quizá la instalaron hace poco
    return encontrada


# ---------- Abrir ----------

def abrir(nombre, appid):
    if appid.lower().endswith(".lnk") and Path(appid).exists():
        os.startfile(appid)
    else:
        subprocess.Popen(["explorer.exe", f"shell:AppsFolder\\{appid}"])


# ---------- Cerrar ----------

def _compacto(texto):
    return re.sub(r"[^a-z0-9]", "", normalizar(texto))


def _procesos_con_ventana():
    return _json_lista(_powershell(
        "Get-Process | Where-Object {$_.MainWindowHandle -ne 0} | "
        "Select-Object Id,ProcessName,MainWindowTitle | ConvertTo-Json -Compress"
    ))


def _ancestros():
    """PID de este programa y de los procesos que lo lanzaron (la terminal, VS Code...)."""
    try:
        salida = _powershell(
            f"$p={os.getpid()}; while($p){{ $p; "
            "$p=(Get-CimInstance Win32_Process -Filter ('ProcessId='+$p)).ParentProcessId }"
        )
        return {int(x) for x in salida.split() if x.isdigit()}
    except (subprocess.SubprocessError, OSError):
        return {os.getpid()}


def _procesos_de(nombre, appid, procesos):
    app = _compacto(nombre)
    exe = _compacto(Path(appid).stem) if appid.lower().endswith(".exe") else ""

    por_nombre = []
    for p in procesos:
        proceso = _compacto(p.get("ProcessName", ""))
        if (exe and exe == proceso) or (
            len(proceso) >= 4 and app and (proceso in app or app in proceso)
        ):
            por_nombre.append(p)
    if por_nombre:
        return por_nombre

    # Sin coincidencia por nombre: la ventana debe terminar con el nombre de la app
    # (así una pestaña del navegador que diga "Spotify" no cuenta).
    return [
        p for p in procesos
        if app and len(app) >= 4 and _compacto(p.get("MainWindowTitle", "")).endswith(app)
    ]


def cerrar(nombre, appid, forzar=False):
    try:
        procesos = _procesos_con_ventana()
    except (subprocess.SubprocessError, OSError, ValueError) as error:
        logging.warning("aplicaciones: no pude leer los procesos (%s)", error)
        return f"No pude revisar si {nombre} está abierta."

    candidatos = _procesos_de(nombre, appid, procesos)
    if not candidatos:
        return f"No encontré {nombre} abierta."

    propios = _ancestros()
    cerrables = [
        p for p in candidatos
        if p["Id"] not in propios and _compacto(p["ProcessName"]) not in PROTEGIDOS
    ]
    if not cerrables:
        return f"No cierro {nombre} porque Corbat se está ejecutando desde ahí o es parte del sistema."

    exito = False
    for p in cerrables:
        comando = ["taskkill", "/PID", str(p["Id"])]
        if forzar:
            comando.append("/F")
        if subprocess.run(comando, capture_output=True).returncode == 0:
            exito = True

    if not exito:
        return (
            f"Le pedí a {nombre} que se cierre, pero sigue abierta. "
            "Si quieres, pídeme que fuerce el cierre."
        )
    return f"Se envió la orden de cierre a {nombre}."


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "buscar":
        print(buscar_app(" ".join(sys.argv[2:])) or "Sin coincidencia")
    else:
        aplicaciones = listar_apps()
        print(f"{len(aplicaciones)} aplicaciones detectadas:")
        for app_nombre, _ in sorted(aplicaciones, key=lambda x: x[0].lower()):
            print(" -", app_nombre)
