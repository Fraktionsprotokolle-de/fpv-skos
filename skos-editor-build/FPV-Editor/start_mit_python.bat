@echo off
setlocal
set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

echo === FPV-Editor: Start aus vorhandener .venv ===
echo (kein Neubau der EXE; fuer Aenderungen an .py/.js reicht dieser Start.)
echo.

if not exist ".venv\Scripts\python.exe" (
    echo FEHLER: .venv nicht gefunden. Bitte zuerst build_windows.bat ausfuehren.
    echo.
    pause
    exit /b 1
)

echo Starte launcher.py ueber .venv\Scripts\python.exe ...
echo Dieses Konsolenfenster bewusst OFFEN LASSEN - hier erscheinen Fehlermeldungen.
echo.
".venv\Scripts\python.exe" launcher.py
echo.
echo FPV-Editor wurde beendet (Exit-Code %errorlevel%).
echo Siehe bei Problemen auch: startup.log
echo.
pause
