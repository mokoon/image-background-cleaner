@echo off
rem Character cutout app launcher: starts the Gradio server and opens http://127.0.0.1:7860
rem (Messages are ASCII on purpose: non-ASCII text inside .bat files can break cmd line parsing.)
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
set URL=http://127.0.0.1:7860

rem Already running? Just open the page instead of starting a second server.
netstat -ano | findstr /R /C:"127\.0\.0\.1:7860 .*LISTENING" /C:"0\.0\.0\.0:7860 .*LISTENING" >nul
if not errorlevel 1 (
    echo Server is already running on port 7860. Opening %URL%
    start "" "%URL%"
    exit /b 0
)

where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python was not found in PATH. Install Python 3.10+ and try again.
    pause
    exit /b 1
)

python -c "import gradio, rembg, cv2" >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Required packages are missing. Run this once in this folder:
    echo     pip install -r requirements.txt
    pause
    exit /b 1
)

echo Starting server... the browser will open %URL% automatically when it is ready.
echo Close this window to stop the server.
echo.
python app.py --inbrowser
if errorlevel 1 (
    echo.
    echo [ERROR] The app exited with an error. See the messages above.
    pause
)
