"""Orbe de Corbat: una esfera de cristal con líquido que se mueve por dentro.

Corre como proceso aparte y recibe líneas por la entrada estándar:
oculto, escuchando, pensando, hablando.

Usa una ventana con transparencia por píxel (sin tkinter), que no toma el
foco ni captura clics, así que no molesta mientras juegas.
"""
import ctypes
import logging
import math
import sys
import threading
import time
from ctypes import wintypes

import numpy as np

import registro  # noqa: F401

TAM = 168  # lado de la ventana, en píxeles
MARGEN_INFERIOR = 70
FPS = 30
RADIO_BASE = 0.72  # del radio de la ventana; el resto es para el brillo exterior

# estado: (color de luz, velocidad del líquido, energía)
PALETA = {
    "escuchando": ((0.62, 0.86, 1.00), 0.45, 0.55),
    "pensando": ((0.80, 0.66, 1.00), 1.00, 0.85),
    "hablando": ((0.62, 1.00, 0.88), 0.80, 0.75),
}

_estado = {"nombre": "oculto"}

_eje = (np.arange(TAM) + 0.5) / TAM * 2 - 1
X, Y = np.meshgrid(_eje, _eje)
DIST = np.hypot(X, Y)
ANGULO = np.arctan2(Y, X)
BRILLO_FIJO = np.exp(-(((X + 0.30) ** 2 + (Y + 0.38) ** 2) / 0.03))


def fotograma(fase, giro, color, energia, radio, visibilidad):
    """Dibuja un cuadro. Devuelve bytes BGRA con alfa premultiplicado."""
    color = np.asarray(color, dtype=np.float32)
    blanco = np.ones(3, dtype=np.float32)

    rr = DIST / radio  # 1 justo en el borde de la esfera
    dentro = np.clip((1 - rr) / 0.02, 0, 1)
    x, y = X / radio, Y / radio

    # Líquido: hilos luminosos que se deforman y fluyen.
    u = x + 0.30 * np.sin(2.6 * y + fase * 1.1) + 0.12 * np.sin(5.1 * x - fase * 0.8)
    v = y + 0.30 * np.sin(2.4 * x - fase * 0.9) + 0.12 * np.sin(5.3 * y + fase * 1.2)
    f1 = np.sin(3.3 * u + 1.9 * np.sin(2.7 * v + fase * 0.7) + fase * 0.4)
    f2 = np.sin(4.1 * v - 1.6 * np.sin(2.2 * u - fase * 0.6) - fase * 0.3)
    nube = 0.5 + 0.5 * np.sin(1.7 * u + 2.1 * v + fase * 0.5)
    hilos = 0.50 * (1 - np.abs(f1)) ** 3.5 + 0.38 * (1 - np.abs(f2)) ** 5 + 0.20 * (1 - np.abs(f1)) ** 14
    humo = nube ** 2 * (0.5 + 0.5 * np.sin(2.3 * v - 1.4 * u + fase * 0.35))
    liquido = (hilos * (0.25 + 0.75 * nube) + 0.22 * humo) * (0.15 + 0.85 * np.clip(rr, 0, 1) ** 2)
    liquido *= dentro * (0.35 + 0.8 * energia)

    # Borde de cristal: un hilo de luz con partes más brillantes que giran.
    d = rr - 1
    fino = np.exp(-((d / 0.030) ** 2))
    variacion = (
        0.10
        + 0.95 * np.clip(np.cos(ANGULO - giro), 0, 1) ** 4
        + 0.45 * np.clip(np.cos(ANGULO - giro * 0.55 + 2.5), 0, 1) ** 5
    )
    borde = fino * variacion

    brillo_interior = np.exp(-(((rr - 0.88) / 0.16) ** 2)) * 0.10 * dentro
    halo = np.where(d > 0, np.exp(-np.maximum(d, 0) / 0.09), 0.0)
    halo *= 0.20 * (0.5 + 0.5 * energia) * np.clip((1 - DIST) / 0.12, 0, 1)
    reflejo = BRILLO_FIJO * 0.14 * dentro

    luz = (
        borde[..., None] * (0.70 * blanco + 0.30 * color)
        + (liquido + brillo_interior)[..., None] * (0.45 * blanco + 0.55 * color)
        + halo[..., None] * color
        + reflejo[..., None] * blanco
    ) * visibilidad

    # Cuerpo: cristal oscuro y translúcido, un poco más opaco hacia el borde.
    cuerpo = 0.48 * dentro * (0.65 + 0.35 * np.clip(rr, 0, 1) ** 2) * visibilidad
    cuerpo_rgb = np.array([0.02, 0.03, 0.07], dtype=np.float32)

    alfa = np.clip(cuerpo + luz.max(axis=-1), 0, 1)
    rgb = np.clip(luz + cuerpo[..., None] * cuerpo_rgb, 0, alfa[..., None])

    salida = np.empty((TAM, TAM, 4), dtype=np.uint8)
    salida[..., 0] = rgb[..., 2] * 255  # B
    salida[..., 1] = rgb[..., 1] * 255  # G
    salida[..., 2] = rgb[..., 0] * 255  # R
    salida[..., 3] = alfa * 255
    return salida.tobytes()


def _leer_estado():
    for linea in sys.stdin:
        nombre = linea.strip()
        if nombre:
            _estado["nombre"] = nombre
    _estado["nombre"] = "salir"  # el proceso principal se cerró


class _Mensaje(ctypes.Structure):
    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("mensaje", wintypes.UINT),
        ("wparam", wintypes.WPARAM),
        ("lparam", wintypes.LPARAM),
        ("tiempo", wintypes.DWORD),
        ("punto", wintypes.POINT),
    ]


class _Mezcla(ctypes.Structure):
    _fields_ = [
        ("operacion", ctypes.c_ubyte),
        ("banderas", ctypes.c_ubyte),
        ("alfa_global", ctypes.c_ubyte),
        ("formato", ctypes.c_ubyte),
    ]


class _CabeceraBitmap(ctypes.Structure):
    _fields_ = [
        ("tam", wintypes.DWORD),
        ("ancho", ctypes.c_long),
        ("alto", ctypes.c_long),
        ("planos", wintypes.WORD),
        ("bits", wintypes.WORD),
        ("compresion", wintypes.DWORD),
        ("tam_imagen", wintypes.DWORD),
        ("x_ppm", ctypes.c_long),
        ("y_ppm", ctypes.c_long),
        ("usados", wintypes.DWORD),
        ("importantes", wintypes.DWORD),
    ]


WS_POPUP = 0x80000000
WS_EX_TOPMOST = 0x00000008
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_LAYERED = 0x00080000
WS_EX_NOACTIVATE = 0x08000000
SW_HIDE = 0
SW_SHOWNOACTIVATE = 4
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOACTIVATE = 0x0010
HWND_TOPMOST = -1
ULW_ALPHA = 0x00000002


class _Ventana:
    """Ventana flotante con transparencia por píxel, sin foco y sin clics."""

    def __init__(self):
        usuario, grafico = ctypes.windll.user32, ctypes.windll.gdi32

        usuario.CreateWindowExW.argtypes = [
            wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
            ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
            wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID,
        ]
        usuario.CreateWindowExW.restype = wintypes.HWND
        usuario.GetDC.argtypes = [wintypes.HWND]
        usuario.GetDC.restype = wintypes.HDC
        usuario.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
        usuario.SetWindowPos.argtypes = [
            wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
            ctypes.c_int, ctypes.c_int, wintypes.UINT,
        ]
        usuario.UpdateLayeredWindow.argtypes = [
            wintypes.HWND, wintypes.HDC, ctypes.POINTER(wintypes.POINT),
            ctypes.POINTER(wintypes.SIZE), wintypes.HDC,
            ctypes.POINTER(wintypes.POINT), wintypes.COLORREF,
            ctypes.POINTER(_Mezcla), wintypes.DWORD,
        ]
        usuario.PeekMessageW.argtypes = [
            ctypes.POINTER(_Mensaje), wintypes.HWND, wintypes.UINT, wintypes.UINT, wintypes.UINT,
        ]
        usuario.DispatchMessageW.argtypes = [ctypes.POINTER(_Mensaje)]
        grafico.CreateCompatibleDC.argtypes = [wintypes.HDC]
        grafico.CreateCompatibleDC.restype = wintypes.HDC
        grafico.CreateDIBSection.argtypes = [
            wintypes.HDC, ctypes.c_void_p, wintypes.UINT,
            ctypes.POINTER(ctypes.c_void_p), wintypes.HANDLE, wintypes.DWORD,
        ]
        grafico.CreateDIBSection.restype = wintypes.HBITMAP
        grafico.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]

        self.usuario = usuario
        ancho = usuario.GetSystemMetrics(0)
        alto = usuario.GetSystemMetrics(1)
        self.posicion = wintypes.POINT((ancho - TAM) // 2, alto - TAM - MARGEN_INFERIOR)
        self.tamano = wintypes.SIZE(TAM, TAM)
        self.origen = wintypes.POINT(0, 0)
        self.mezcla = _Mezcla(0, 0, 255, 1)  # AC_SRC_OVER, alfa por píxel

        self.hwnd = usuario.CreateWindowExW(
            WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW
            | WS_EX_NOACTIVATE | WS_EX_TOPMOST,
            "Static", "Corbat", WS_POPUP,
            self.posicion.x, self.posicion.y, TAM, TAM,
            None, None, None, None,
        )
        if not self.hwnd:
            raise OSError("No se pudo crear la ventana del orbe")

        self.pantalla = usuario.GetDC(None)
        self.memoria = grafico.CreateCompatibleDC(self.pantalla)
        cabecera = _CabeceraBitmap(ctypes.sizeof(_CabeceraBitmap), TAM, -TAM, 1, 32, 0, 0, 0, 0, 0, 0)
        self.datos = ctypes.c_void_p()
        bitmap = grafico.CreateDIBSection(
            self.pantalla, ctypes.byref(cabecera), 0, ctypes.byref(self.datos), None, 0
        )
        grafico.SelectObject(self.memoria, bitmap)
        self.visible = False

    def mostrar(self):
        self.usuario.ShowWindow(self.hwnd, SW_SHOWNOACTIVATE)
        self.visible = True

    def ocultar(self):
        self.usuario.ShowWindow(self.hwnd, SW_HIDE)
        self.visible = False

    def al_frente(self):
        """Los juegos a veces se ponen encima: se vuelve a pedir estar al frente."""
        self.usuario.SetWindowPos(
            self.hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE
        )

    def dibujar(self, cuadro):
        ctypes.memmove(self.datos, cuadro, len(cuadro))
        self.usuario.UpdateLayeredWindow(
            self.hwnd, self.pantalla, ctypes.byref(self.posicion), ctypes.byref(self.tamano),
            self.memoria, ctypes.byref(self.origen), 0, ctypes.byref(self.mezcla), ULW_ALPHA,
        )

    def atender_mensajes(self):
        mensaje = _Mensaje()
        while self.usuario.PeekMessageW(ctypes.byref(mensaje), None, 0, 0, 1):
            self.usuario.TranslateMessage(ctypes.byref(mensaje))
            self.usuario.DispatchMessageW(ctypes.byref(mensaje))


def _acercar(actual, objetivo, paso):
    return actual + (objetivo - actual) * min(1.0, paso)


def main():
    ctypes.windll.user32.SetProcessDPIAware()
    ventana = _Ventana()
    threading.Thread(target=_leer_estado, daemon=True).start()

    visibilidad = 0.0
    fase = giro = 0.0
    nombre_visto = "escuchando"
    color, velocidad, energia = (np.array(PALETA[nombre_visto][0]), *PALETA[nombre_visto][1:])
    ultimo = ultimo_frente = time.monotonic()

    while True:
        ventana.atender_mensajes()
        nombre = _estado["nombre"]
        if nombre == "salir":
            break

        ahora = time.monotonic()
        dt = min(ahora - ultimo, 0.1)
        ultimo = ahora

        activo = nombre in PALETA
        if activo:
            nombre_visto = nombre
        visibilidad = _acercar(visibilidad, 1.0 if activo else 0.0, dt * 9)

        if visibilidad < 0.02 and not activo:
            if ventana.visible:
                ventana.ocultar()
            time.sleep(0.15)
            continue

        if not ventana.visible:
            ventana.mostrar()
        if ahora - ultimo_frente > 2:
            ventana.al_frente()
            ultimo_frente = ahora

        color_obj, velocidad_obj, energia_obj = PALETA[nombre_visto]
        color = color + (np.array(color_obj) - color) * min(1.0, dt * 5)
        velocidad = _acercar(velocidad, velocidad_obj, dt * 5)
        energia = _acercar(energia, energia_obj, dt * 5)

        fase += dt * (0.8 + 1.6 * velocidad)
        giro += dt * (0.5 + 0.8 * velocidad)

        radio = RADIO_BASE * (0.82 + 0.18 * visibilidad) * (1 + 0.015 * math.sin(ahora * 2.2))
        energia_viva = energia
        if nombre_visto == "hablando":
            pulso = 0.5 + 0.5 * math.sin(ahora * 11) * math.sin(ahora * 4.3)
            radio *= 1 + 0.04 * pulso
            energia_viva = energia * (0.8 + 0.6 * pulso)

        ventana.dibujar(fotograma(fase, giro, color, energia_viva, radio, visibilidad))

        sobra = 1 / FPS - (time.monotonic() - ahora)
        if sobra > 0:
            time.sleep(sobra)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        logging.exception("El orbe de Corbat falló")
