@echo off
setlocal enabledelayedexpansion
set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

echo === FPV-Editor: Diagnose-Build (mit Konsole) ===
echo Verzeichnis: %SCRIPT_DIR%
echo.
echo Dieses Skript baut eine ZWEITE, separate Variante der App mit
echo sichtbarem Konsolenfenster (FPV-Editor-Diagnose.exe) und startet
echo sie sofort. Alle Fehlermeldungen, die im normalen --noconsole-Build
echo unsichtbar bleiben wuerden, erscheinen hier im Fenster.
echo.
echo Der normale Build (build_windows.bat, --noconsole) bleibt
echo unberuehrt und wird NICHT ueberschrieben.
echo.

rem ------------------------------------------------------------------
rem 1) Python 3.14 (64-Bit) suchen (identisch zu build_windows.bat)
rem ------------------------------------------------------------------
set "PYEXE="

py -3.14-64 -c "print(1)" >nul 2>nul
if not errorlevel 1 (
    set "PYEXE=py -3.14-64"
    goto :found_python
)
py -3.14 -c "print(1)" >nul 2>nul
if not errorlevel 1 (
    set "PYEXE=py -3.14"
    goto :found_python
)
python --version 2>nul | findstr /C:"3.14" >nul
if not errorlevel 1 (
    set "PYEXE=python"
    goto :found_python
)

echo FEHLER: Es wurde kein Python 3.14 ^(64-Bit^) gefunden.
echo Bitte zuerst build_windows.bat erfolgreich ausfuehren
echo ^(oder Python 3.14 x64 installieren^).
goto :error

:found_python
echo Verwende Python-Start: %PYEXE%
echo.

rem ------------------------------------------------------------------
rem 2) .venv muss bereits existieren (von build_windows.bat angelegt)
rem ------------------------------------------------------------------
if not exist ".venv\Scripts\python.exe" (
    echo FEHLER: .venv fehlt. Bitte zuerst build_windows.bat ausfuehren,
    echo damit die Abhaengigkeiten offline aus wheels\ installiert werden.
    goto :error
)

rem ------------------------------------------------------------------
rem 3) Vorherigen Diagnose-Build entfernen (normaler Build bleibt unberuehrt)
rem    Mit Fehlerpruefung UND altem .spec entfernen -- siehe ausfuehrliche
rem    Begruendung in build_windows.bat, Abschnitt 4: ein lautlos
rem    fehlgeschlagenes rmdir hier kann sonst dazu fuehren, dass eine
rem    Datei wie static\index.html im Bundle fehlt, ohne dass der Build
rem    selbst einen Fehler meldet.
rem ------------------------------------------------------------------
if exist "build\FPV-Editor-Diagnose" (
    rmdir /s /q "build\FPV-Editor-Diagnose"
    if exist "build\FPV-Editor-Diagnose" (
        echo FEHLER: build\FPV-Editor-Diagnose konnte nicht vollstaendig geloescht werden.
        echo Bitte FPV-Editor-Diagnose.exe beenden, falls sie noch laeuft, und erneut versuchen.
        goto :error
    )
)
if exist "dist\FPV-Editor-Diagnose" (
    rmdir /s /q "dist\FPV-Editor-Diagnose"
    if exist "dist\FPV-Editor-Diagnose" (
        echo FEHLER: dist\FPV-Editor-Diagnose konnte nicht vollstaendig geloescht werden.
        echo Bitte FPV-Editor-Diagnose.exe beenden, falls sie noch laeuft, und erneut versuchen.
        goto :error
    )
)
if exist "FPV-Editor-Diagnose.spec" del /f /q "FPV-Editor-Diagnose.spec"

rem ------------------------------------------------------------------
rem 4) PyInstaller-Build: --onedir, OHNE --noconsole
rem ------------------------------------------------------------------
echo Baue Diagnose-EXE mit PyInstaller ^(--onedir, MIT Konsole^) ...
".venv\Scripts\python.exe" -m PyInstaller --onedir --name FPV-Editor-Diagnose ^
    --add-data "static;static" --collect-submodules rdflib.plugins launcher.py
if errorlevel 1 (
    echo FEHLER: PyInstaller-Build fehlgeschlagen.
    goto :error
)

rem ------------------------------------------------------------------
rem 5) Nachweis statt Behauptung -- siehe build_windows.bat, Abschnitt 6.
rem ------------------------------------------------------------------
if not exist "dist\FPV-Editor-Diagnose\FPV-Editor-Diagnose.exe" (
    echo FEHLER: dist\FPV-Editor-Diagnose\FPV-Editor-Diagnose.exe fehlt nach dem Build.
    goto :error
)
if not exist "dist\FPV-Editor-Diagnose\_internal\static\index.html" (
    echo FEHLER: dist\FPV-Editor-Diagnose\_internal\static\index.html fehlt im gebauten Bundle.
    echo Die EXE wuerde zur Laufzeit mit "Internal Server Error" scheitern.
    goto :error
)
if not exist "dist\FPV-Editor-Diagnose\_internal\static\app.js" (
    echo FEHLER: dist\FPV-Editor-Diagnose\_internal\static\app.js fehlt im gebauten Bundle.
    goto :error
)

rem ------------------------------------------------------------------
rem 7) Manifest (Groesse + SHA-256 jeder Datei) schreiben, ZIP bauen und
rem    das ZIP gegen das Manifest nachpruefen. Der Launcher vergleicht beim
rem    Start den Ordner mit diesem Manifest und meldet fehlende Dateien.
rem ------------------------------------------------------------------
echo Schreibe Manifest und erstelle ZIP ...
".venv\Scripts\python.exe" make_release.py "dist\FPV-Editor-Diagnose" "dist\FPV-Editor-Diagnose.zip"
if errorlevel 1 (
    echo FEHLER: Manifest/ZIP konnte nicht erstellt oder nicht nachgewiesen werden.
    goto :error
)

echo.
echo === Diagnose-Build erfolgreich UND geprueft ===
echo Ergebnis liegt unter: dist\FPV-Editor-Diagnose\ ^(und als ZIP daneben^)
echo.
echo Starte FPV-Editor-Diagnose.exe jetzt. Das Konsolenfenster bleibt
echo offen und zeigt alle Ausgaben, Tracebacks und Log-Zeilen direkt an.
echo Zusaetzlich wird alles in startup.log neben der EXE protokolliert.
echo Zum Beenden: App-Fenster schliessen oder Strg+C im Konsolenfenster.
echo.
pause
start /wait "" "dist\FPV-Editor-Diagnose\FPV-Editor-Diagnose.exe"

echo.
echo === Diagnose-Programm wurde beendet. ===
echo Falls ein Fehler aufgetreten ist, steht er vermutlich oben in
echo diesem Fenster und zusaetzlich in:
echo   dist\FPV-Editor-Diagnose\startup.log
echo.
pause
exit /b 0

:error
echo.
echo === Diagnose-Build fehlgeschlagen. Siehe Meldungen oben. ===
echo.
pause
exit /b 1
