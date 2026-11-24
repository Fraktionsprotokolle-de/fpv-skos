@echo off
setlocal enabledelayedexpansion
set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

echo === FPV-Editor: Windows-Build ===
echo Verzeichnis: %SCRIPT_DIR%
echo.

rem ------------------------------------------------------------------
rem 1) Python 3.14 (64-Bit) suchen
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
echo Bitte Python 3.14 x64 installieren ^(python.org^) und erneut versuchen,
echo oder die Variable PYEXE am Anfang dieses Skripts manuell setzen.
goto :error

:found_python
echo Verwende Python-Start: %PYEXE%
echo.

rem ------------------------------------------------------------------
rem 2) .venv anlegen, falls nicht vorhanden
rem ------------------------------------------------------------------
if not exist ".venv\Scripts\python.exe" (
    echo Lege virtuelle Umgebung .venv an ...
    %PYEXE% -m venv .venv
    if errorlevel 1 (
        echo FEHLER: Erstellen der .venv fehlgeschlagen.
        goto :error
    )
) else (
    echo Verwende vorhandene .venv.
)
echo.

rem ------------------------------------------------------------------
rem 3) Offline-Installation ausschließlich aus wheels\
rem ------------------------------------------------------------------
if not exist "wheels\" (
    echo FEHLER: Ordner wheels\ fehlt. Offline-Installation nicht moeglich.
    goto :error
)

echo Aktualisiere pip offline aus wheels\ ...
".venv\Scripts\python.exe" -m pip install --no-index --find-links="wheels" --upgrade pip
if errorlevel 1 (
    echo FEHLER: pip-Aktualisierung aus wheels\ fehlgeschlagen.
    goto :error
)

echo Installiere Laufzeit-Abhaengigkeiten ^(requirements.txt^) offline aus wheels\ ...
".venv\Scripts\python.exe" -m pip install --no-index --find-links="wheels" -r requirements.txt
if errorlevel 1 (
    echo FEHLER: Installation aus requirements.txt fehlgeschlagen.
    goto :error
)

echo Installiere Build-Abhaengigkeiten ^(PyInstaller, pefile, pywin32-ctypes^) offline aus wheels\ ...
".venv\Scripts\python.exe" -m pip install --no-index --find-links="wheels" "pyinstaller>=6,<7" pefile pywin32-ctypes
if errorlevel 1 (
    echo FEHLER: Installation der Build-Abhaengigkeiten fehlgeschlagen.
    goto :error
)
echo.

rem ------------------------------------------------------------------
rem 4) Vorherigen Build vollstaendig entfernen (inkl. altem .spec!)
rem ------------------------------------------------------------------
rem WICHTIG: Nicht nur dist\FPV-Editor, sondern auch build\ UND das alte
rem .spec loeschen, und jeden Schritt auf Erfolg pruefen. Grund: Ein
rem fruehrer Build ist hier schon einmal MITTEN im Kopieren von
rem static\index.html abgestuerzt (siehe Uebergabe-Historie). Wenn danach
rem einer dieser Aufraeumschritte lautlos fehlschlaegt (z. B. weil ein
rem Virenscanner oder ein noch laufender FPV-Editor.exe-Prozess eine Datei
rem kurz sperrt), kann der naechste Build auf einem TEILWEISE alten Stand
rem aufsetzen -- mit genau dem Ergebnis, dass eine Datei wie
rem static\index.html im fertigen Bundle fehlt, ohne dass der Build selbst
rem einen Fehler meldet. Deshalb hier: alles weg, und zwar nachweislich.
echo Entferne alte Build-Artefakte ^(build\, dist\FPV-Editor, altes .spec^) ...
if exist "build" (
    rmdir /s /q "build"
    if exist "build" (
        echo FEHLER: Ordner build\ konnte nicht vollstaendig geloescht werden.
        echo Moegliche Ursache: eine Datei darin ist noch gesperrt ^(z. B. von
        echo einem Virenscanner oder einem noch laufenden FPV-Editor-Prozess^).
        echo Bitte FPV-Editor.exe beenden, kurz warten, und erneut versuchen.
        goto :error
    )
)
if exist "dist\FPV-Editor" (
    rmdir /s /q "dist\FPV-Editor"
    if exist "dist\FPV-Editor" (
        echo FEHLER: Ordner dist\FPV-Editor konnte nicht vollstaendig geloescht werden.
        echo Moegliche Ursache: eine Datei darin ist noch gesperrt ^(z. B. von
        echo einem Virenscanner oder einem noch laufenden FPV-Editor-Prozess^).
        echo Bitte FPV-Editor.exe beenden, kurz warten, und erneut versuchen.
        goto :error
    )
)
if exist "FPV-Editor.spec" del /f /q "FPV-Editor.spec"

rem ------------------------------------------------------------------
rem 5) PyInstaller-Build: --onedir --noconsole
rem ------------------------------------------------------------------
echo Baue EXE mit PyInstaller ^(--onedir --noconsole^) ...
".venv\Scripts\python.exe" -m PyInstaller --onedir --noconsole --name FPV-Editor ^
    --add-data "static;static" --collect-submodules rdflib.plugins launcher.py
if errorlevel 1 (
    echo FEHLER: PyInstaller-Build fehlgeschlagen.
    goto :error
)

rem ------------------------------------------------------------------
rem 6) Nachweis statt Behauptung: pruefen, dass die kritischen Dateien
rem    im fertigen Bundle TATSAECHLICH vorhanden sind, statt nur "Build
rem    erfolgreich" zu melden, weil PyInstaller mit Exitcode 0 endete.
rem    Genau das Fehlen von static\index.html im Bundle blieb zuvor
rem    unentdeckt, bis die EXE zur Laufzeit einen 500-Fehler zeigte.
rem ------------------------------------------------------------------
if not exist "dist\FPV-Editor\FPV-Editor.exe" (
    echo FEHLER: dist\FPV-Editor\FPV-Editor.exe fehlt nach dem Build.
    goto :error
)
if not exist "dist\FPV-Editor\_internal\static\index.html" (
    echo FEHLER: dist\FPV-Editor\_internal\static\index.html fehlt im gebauten Bundle.
    echo Die EXE wuerde zur Laufzeit mit "Internal Server Error" scheitern.
    echo Bitte diesen Ordner pruefen und diese Meldung an den Entwickler weitergeben.
    goto :error
)
if not exist "dist\FPV-Editor\_internal\static\app.js" (
    echo FEHLER: dist\FPV-Editor\_internal\static\app.js fehlt im gebauten Bundle.
    goto :error
)

rem ------------------------------------------------------------------
rem 7) Manifest (Groesse + SHA-256 jeder Datei) schreiben, ZIP bauen und
rem    das ZIP gegen das Manifest nachpruefen. Der Launcher vergleicht beim
rem    Start den Ordner mit diesem Manifest und meldet fehlende Dateien.
rem ------------------------------------------------------------------
echo Schreibe Manifest und erstelle ZIP ...
".venv\Scripts\python.exe" make_release.py "dist\FPV-Editor" "dist\FPV-Editor.zip"
if errorlevel 1 (
    echo FEHLER: Manifest/ZIP konnte nicht erstellt oder nicht nachgewiesen werden.
    goto :error
)

echo.
echo === Build erfolgreich UND geprueft ===
echo Ergebnis liegt vollstaendig unter: dist\FPV-Editor\
echo Zum Weitergeben: dist\FPV-Editor.zip ^(enthaelt den ganzen Ordner samt
echo Pruefliste^). Nie nur FPV-Editor.exe allein weitergeben ^(siehe README.md^).
echo.
echo Naechster Schritt zur Fehlersuche auf diesem Rechner:
echo   diagnose_windows.bat  ^(baut zusaetzlich eine Variante MIT Konsole
echo   und startet sie sofort, damit Fehlermeldungen sichtbar bleiben^).
echo.
pause
exit /b 0

:error
echo.
echo === Build fehlgeschlagen. Siehe Meldungen oben. ===
echo.
pause
exit /b 1
