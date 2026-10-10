@echo off
chcp 65001 >nul
title Configuracion de Corbat
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -m corbat.configurar
) else (
    python -m corbat.configurar
)
pause
