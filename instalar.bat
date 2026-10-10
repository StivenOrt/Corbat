@echo off
chcp 65001 >nul
title Instalador de Corbat
cd /d "%~dp0"
echo === Instalador de Corbat ===

set "PY="
for %%V in (3.12 3.11) do (
    if not defined PY (
        py -%%V -c "import sys" >nul 2>&1 && set "PY=py -%%V"
    )
)
if not defined PY goto sinpython

if not exist ".venv\Scripts\python.exe" (
    echo Creando entorno virtual...
    %PY% -m venv .venv || goto error
)

echo Instalando dependencias, puede tardar unos minutos...
".venv\Scripts\python.exe" -m pip install --upgrade pip >nul
".venv\Scripts\python.exe" -m pip install -r requirements.txt || goto error

".venv\Scripts\python.exe" -m corbat.instalar
goto fin

:sinpython
echo.
echo No encontre Python 3.12 ni 3.11.
where winget >nul 2>&1
if errorlevel 1 goto manual
choice /c SN /m "Quieres instalar Python 3.12 ahora con winget"
if errorlevel 2 goto manual
winget install -e --id Python.Python.3.12
echo.
echo Cierra esta ventana y vuelve a ejecutar instalar.bat.
goto fin

:manual
echo Descargalo de https://www.python.org/downloads/ (version 3.12)
echo y marca la casilla "Add python.exe to PATH". Luego vuelve a ejecutar instalar.bat.
goto fin

:error
echo.
echo Algo fallo. Revisa el mensaje de arriba.

:fin
echo.
pause
