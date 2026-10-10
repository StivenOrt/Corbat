@echo off
title Corbat
cd /d "%~dp0.."
if exist ".venv\Scripts\python.exe" (set "PY=.venv\Scripts\python.exe") else (set "PY=python")
echo Esperando a que Windows termine de iniciar...
timeout /t 15 /nobreak >nul
"%PY%" main.py
echo.
echo Corbat se cerro. Presiona una tecla para salir.
pause >nul
