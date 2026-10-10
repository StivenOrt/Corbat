@echo off
title Corbat
cd /d "%~dp0"
echo Esperando a que Windows termine de iniciar...
timeout /t 15 /nobreak >nul
python asistente.py
echo.
echo Corbat se cerro. Presiona una tecla para salir.
pause >nul
