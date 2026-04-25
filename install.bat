@echo off
setlocal
set "SCRIPT_DIR=%~dp0"
set "APP_DIR=%SCRIPT_DIR%"

for %%I in ("%SCRIPT_DIR%..") do set "PARENT_NAME=%%~nxI"
for %%I in ("%SCRIPT_DIR%.") do set "CURRENT_NAME=%%~nxI"
if /I "%CURRENT_NAME%"=="install_files" if /I "%PARENT_NAME%"=="Data" (
    for %%I in ("%SCRIPT_DIR%..\..") do set "APP_DIR=%%~fI\"
)

pushd "%APP_DIR%"
set "INSTALL_FILES=Data\install_files"
set "SOURCE_PY=voice_input.py"
if not exist "%SOURCE_PY%" if exist "%INSTALL_FILES%\voice_input.py" set "SOURCE_PY=%INSTALL_FILES%\voice_input.py"

echo ================================================
echo  Voice Input for Windows - Install and Build
echo ================================================
echo.

if not exist Data\ (
    echo [1/3] Creating virtual environment...
    py -3.12 -m venv Data
) else (
    echo [1/3] Data\ already exists, skipping...
)

echo.
echo [2/3] Installing packages into Data\...
Data\Scripts\pip.exe install --no-user faster-whisper sounddevice scipy numpy pyperclip pyautogui pystray pillow keyboard opencc-python-reimplemented pyinstaller

echo.
echo [3/3] Building VoiceInput.exe...
Data\Scripts\pyinstaller ^
  --noconsole ^
  --onefile ^
  --name "VoiceInput" ^
  --distpath "." ^
  --collect-data opencc ^
  --collect-data faster_whisper ^
  --hidden-import "scipy.signal" ^
  --hidden-import "scipy.io.wavfile" ^
  "%SOURCE_PY%"

echo.
echo ================================================
if exist VoiceInput.exe (
    echo  Done! VoiceInput.exe is ready here.
    echo  Cleaning up build files...
    rmdir /s /q build
    if exist dist rmdir /s /q dist
    del /q VoiceInput.spec 2>nul
    if not exist config.json (
        echo  Creating default config.json...
        > config.json echo {
        >> config.json echo   "model": "large-v3",
        >> config.json echo   "language": "auto",
        >> config.json echo   "paste_mode": "clipboard",
        >> config.json echo   "device": "cpu",
        >> config.json echo   "compute_type": "auto",
        >> config.json echo   "hotkey_mode": "hold",
        >> config.json echo   "hotkey": "ctrl+f9",
        >> config.json echo   "chinese_output": "traditional",
        >> config.json echo   "cpu_threads": 0,
        >> config.json echo   "start_at_login": false,
        >> config.json echo   "app_language": "en"
        >> config.json echo }
    ) else (
        echo  config.json already exists, keeping current settings.
    )
    echo  Moving install files into %INSTALL_FILES%...
    if not exist "%INSTALL_FILES%" mkdir "%INSTALL_FILES%"
    if exist voice_input.py move /Y voice_input.py "%INSTALL_FILES%\" >nul
    if exist install_mac.sh move /Y install_mac.sh "%INSTALL_FILES%\" >nul
    if exist launch_mac.command move /Y launch_mac.command "%INSTALL_FILES%\" >nul
    if /I not "%~f0"=="%APP_DIR%%INSTALL_FILES%\install.bat" move /Y "%~f0" "%APP_DIR%%INSTALL_FILES%\" >nul
    echo  Cleanup complete.
) else (
    echo  Something went wrong. Check the output above.
)
echo ================================================
popd
pause
