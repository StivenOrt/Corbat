"""Arranque de Corbat:  python main.py"""
import traceback
from datetime import datetime
from pathlib import Path

try:
    from corbat.asistente import main
except Exception:
    # Sin consola (pythonw) un error al arrancar pasaría en silencio: se deja anotado.
    datos = Path(__file__).resolve().parent / "datos"
    datos.mkdir(exist_ok=True)
    with open(datos / "error_arranque.log", "a", encoding="utf-8") as archivo:
        archivo.write(f"--- {datetime.now():%Y-%m-%d %H:%M:%S} ---\n{traceback.format_exc()}\n")
    raise

if __name__ == "__main__":
    main()
