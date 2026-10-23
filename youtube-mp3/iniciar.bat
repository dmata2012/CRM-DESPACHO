@echo off
setlocal
chcp 65001 >nul
title Convertidor YouTube a MP3
cd /d "%~dp0"

set "URL=http://127.0.0.1:5000"

rem --- Python ---------------------------------------------------------------
set "PY="
py -3 --version >nul 2>&1 && set "PY=py -3"
if not defined PY python --version >nul 2>&1 && set "PY=python"
if not defined PY (
    echo [ERROR] No se encontro Python.
    echo Instalalo con:  winget install Python.Python.3.12
    echo o desde https://www.python.org/downloads/ marcando "Add python.exe to PATH".
    goto :fin
)

rem --- ffmpeg ---------------------------------------------------------------
where ffmpeg >nul 2>&1
if errorlevel 1 (
    echo [ERROR] No se encontro ffmpeg.
    echo Instalalo con:  winget install ffmpeg
    echo Despues cierra esta ventana y vuelve a abrir el script.
    goto :fin
)

rem --- Entorno virtual (solo la primera vez) --------------------------------
if not exist ".venv\Scripts\python.exe" (
    echo Preparando la aplicacion por primera vez, espera un momento...
    %PY% -m venv .venv || goto :error
    ".venv\Scripts\python.exe" -m pip install -q --upgrade pip
    ".venv\Scripts\python.exe" -m pip install -q -r requirements.txt || goto :error
)

rem --- Mantener yt-dlp al dia (si no hay internet, continua) ----------------
echo Buscando actualizaciones de yt-dlp...
".venv\Scripts\python.exe" -m pip install -q -U yt-dlp >nul 2>&1

rem --- Abrir el navegador cuando el servidor este listo ---------------------
start "" /min cmd /c "timeout /t 3 >nul & start "" %URL%"

echo.
echo La aplicacion esta corriendo en %URL%
echo Para cerrarla, cierra esta ventana o presiona Ctrl+C.
echo.
set "HOST=127.0.0.1"
".venv\Scripts\python.exe" app.py
goto :fin

:error
echo.
echo [ERROR] No se pudo instalar la aplicacion. Revisa tu conexion a internet
echo y vuelve a intentarlo. Si el problema sigue, borra la carpeta .venv.

:fin
echo.
pause
