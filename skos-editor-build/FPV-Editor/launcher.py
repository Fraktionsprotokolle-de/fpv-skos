# -*- coding: utf-8 -*-
"""
launcher.py — EXE-Einstiegspunkt des FPV-Editors.

Verantwortlich für:
  * Start des Flask-Servers (über app.make_wsgi_server) in einem Hintergrund-
    thread; Tk-Ereignisschleife bleibt im Hauptthread (Voraussetzung für
    Dateidialoge, siehe DialogBridge unten).
  * kleines Tk-Startfenster mit URL, "Im Browser öffnen", "App beenden".
  * HTTP-Bereitschaftstest, bevor ein Browser gestartet wird.
  * bevorzugt direkter Start einer gefundenen Edge-/Chrome-/Firefox-EXE per
    subprocess.Popen([browser, url]); URL bleibt in jedem Fall im Fenster
    sichtbar und kopierbar, falls die Übergabe fehlschlägt.
  * Startfehler als Windows-Meldung anzeigen und in `startup.log` schreiben
    (auch dann, wenn Tk selbst nicht mehr aufgebaut werden kann).

Bekannte, in der Übergabe explizit benannte frühere Fehlerquelle: die
Browserübergabe hat laut Nutzerbericht "nie funktioniert". Diese Fassung
härtet das ab, indem sie (a) mehrere konkrete Installationspfade prüft statt
sich auf PATH/Registry zu verlassen, (b) bei jedem einzelnen Schritt
Ausnahmen einzeln abfängt und protokolliert statt beim ersten Fehler
stillschweigend aufzugeben, und (c) zusätzlich `webbrowser.open()` und
`os.startfile()` als Rückfallversuche nutzt. **Ob das den ursprünglichen
Fehler auf dem betroffenen Windows-Rechner tatsächlich behebt, ist von
hier aus nicht überprüfbar** — das kann nur ein echter Test auf diesem
Rechner zeigen (siehe Übergabe §7/§9). `startup.log` protokolliert deshalb
jeden einzelnen Versuch mit Erfolg/Fehlschlag.
"""

from __future__ import annotations

import ctypes
import os
import queue
import sys
import threading
import time
import traceback
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

PROGRAM_DIR = os.path.dirname(sys.executable if getattr(sys, "frozen", False) else os.path.abspath(__file__))


def _choose_log_path() -> str:
    """startup.log liegt neben der EXE. Ist dieser Ordner nicht beschreibbar
    (z. B. Programmordner mit Schreibschutz), weicht das Log nach
    %LOCALAPPDATA%\\FPV-Editor aus, statt stillschweigend nichts zu
    protokollieren."""
    primary = os.path.join(PROGRAM_DIR, "startup.log")
    try:
        with open(primary, "a", encoding="utf-8"):
            pass
        return primary
    except OSError:
        pass
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    fallback_dir = os.path.join(base, "FPV-Editor")
    try:
        os.makedirs(fallback_dir, exist_ok=True)
        fallback = os.path.join(fallback_dir, "startup.log")
        with open(fallback, "a", encoding="utf-8"):
            pass
        return fallback
    except OSError:
        return primary  # Letzte Möglichkeit; log() fängt den Fehler weiter ab.


LOG_PATH = _choose_log_path()


def log(message: str):
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}"
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass  # Wenn selbst das Log nicht geschrieben werden kann, bleibt nur die MessageBox.
    print(line, file=sys.stderr)


def show_fatal_error(title: str, message: str):
    """Zeigt einen Startfehler als Windows-Meldung, unabhängig davon, ob Tk
    selbst funktioniert. Fällt auf stderr zurück, wenn auch das fehlschlägt."""
    log(f"FATAL: {title}: {message}")
    try:
        if sys.platform.startswith("win"):
            ctypes.windll.user32.MessageBoxW(0, message, title, 0x10)  # MB_ICONERROR
            return
    except Exception:
        pass
    try:
        import tkinter
        from tkinter import messagebox
        root = tkinter.Tk()
        root.withdraw()
        messagebox.showerror(title, message)
        root.destroy()
        return
    except Exception:
        pass
    print(f"{title}: {message}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Browserstart
# ---------------------------------------------------------------------------

def _candidate_browser_paths():
    """Bekannte Installationspfade für Edge, Chrome, Firefox unter Windows,
    in der von der Übergabe vorgegebenen Reihenfolge. Registry-Auflösung wird
    NICHT genutzt, da sie in der Vergangenheit ("Kein Objekt für Moniker!")
    bereits an anderer Stelle Probleme gemacht hat; feste Pfade sind robuster
    gegen COM-/Moniker-Fehler."""
    pf = os.environ.get("ProgramFiles", r"C:\Program Files")
    pf86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    lad = os.environ.get("LOCALAPPDATA", "")

    candidates = [
        os.path.join(pf, "Microsoft", "Edge", "Application", "msedge.exe"),
        os.path.join(pf86, "Microsoft", "Edge", "Application", "msedge.exe"),
        os.path.join(pf, "Google", "Chrome", "Application", "chrome.exe"),
        os.path.join(pf86, "Google", "Chrome", "Application", "chrome.exe"),
        os.path.join(lad, "Google", "Chrome", "Application", "chrome.exe") if lad else None,
        os.path.join(pf, "Mozilla Firefox", "firefox.exe"),
        os.path.join(pf86, "Mozilla Firefox", "firefox.exe"),
    ]
    return [c for c in candidates if c]


def open_browser(url: str) -> tuple[bool, str]:
    """Versucht, `url` in einem Browser zu öffnen. Reihenfolge: (1) bekannte
    Edge-/Chrome-/Firefox-EXE-Pfade per subprocess.Popen, (2) webbrowser.open,
    (3) os.startfile (nur Windows). Gibt (erfolg, protokolltext) zurück; die
    URL bleibt unabhängig vom Ergebnis im Startfenster sichtbar."""
    import subprocess

    attempts = []
    for path in _candidate_browser_paths():
        if os.path.isfile(path):
            try:
                subprocess.Popen([path, url], close_fds=True)
                attempts.append(f"OK: {path}")
                return True, " | ".join(attempts)
            except OSError as exc:
                attempts.append(f"Fehlschlag {path}: {exc}")
        else:
            attempts.append(f"nicht vorhanden: {path}")

    try:
        if webbrowser.open(url):
            attempts.append("OK: webbrowser.open()")
            return True, " | ".join(attempts)
        attempts.append("webbrowser.open() lieferte False")
    except Exception as exc:
        attempts.append(f"webbrowser.open() Fehlschlag: {exc}")

    if sys.platform.startswith("win"):
        try:
            os.startfile(url)  # type: ignore[attr-defined]
            attempts.append("OK: os.startfile()")
            return True, " | ".join(attempts)
        except OSError as exc:
            attempts.append(f"os.startfile() Fehlschlag: {exc}")

    return False, " | ".join(attempts)


def wait_for_server_ready(url: str, timeout_s: float = 8.0) -> tuple[bool, str]:
    """Echter HTTP-GET-Test auf `/`, statt nur den Port zu prüfen — ein
    offener Port bedeutet nicht, dass Flask schon Antworten liefert.
    Gibt (bereit, letzter_befund) zurück. Der letzte Befund unterscheidet
    ausdrücklich zwischen "gar keine Verbindung" (Server-Thread nie
    tatsächlich aktiv) und "Verbindung ja, aber Fehlerantwort" (Server läuft,
    aber irgendetwas in der Anfrageverarbeitung schlägt fehl, z. B. ein
    Pfadproblem beim Laden von static/index.html im gebauten EXE) — beides
    sah vorher gleich aus ("Timeout"), was die Diagnose unmöglich machte."""
    last_detail = "kein einziger Verbindungsversuch unternommen"
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1.0) as resp:
                if resp.status == 200:
                    return True, "HTTP 200"
                last_detail = f"HTTP {resp.status} (Verbindung klappt, aber keine 200er-Antwort)"
        except urllib.error.HTTPError as exc:
            last_detail = f"HTTP {exc.code} {exc.reason} (Verbindung klappt, Server antwortet mit Fehler)"
            if exc.code >= 500:
                # Eine Fehlerantwort des laufenden Servers wird durch
                # Wiederholen nicht besser (z. B. fehlende Datei) -- sofort
                # abbrechen statt 8 Sekunden lang denselben Fehler zu erzeugen.
                return False, last_detail
        except urllib.error.URLError as exc:
            last_detail = f"Keine Verbindung möglich: {exc.reason}"
        except Exception as exc:
            last_detail = f"Unerwarteter Fehler beim Bereitschaftstest: {exc!r}"
        time.sleep(0.15)
    return False, last_detail


# ---------------------------------------------------------------------------
# Bridge für Dateidialoge: Flask-Worker-Threads dürfen keine Tk-Dialoge
# öffnen. Anfragen werden über eine Queue an den Tk-Hauptthread übergeben
# und dort per root.after()-Polling ausgeführt.
# ---------------------------------------------------------------------------

OPEN_DIALOG_TITLE = "TTL-Datei öffnen"


class DialogBridge:
    """Fuehrt den Dateiauswahldialog auf dem Tk-Hauptthread aus, OHNE dass
    der aufrufende Flask-Thread darauf wartet; das Ergebnis wird ueber einen
    Rueckruf gemeldet (siehe /api/choose und /api/choose-result in app.py).

    Gegen mehrfach geoeffnete Dialoge: Laeuft bereits ein Dialog, wird die
    Warteschlange nicht weiter abgearbeitet (`_busy`), auch falls Tk waehrend
    des modalen Windows-Dialogs Zeitgeber bedient."""

    def __init__(self, root, status_callback=None):
        self.root = root
        self._requests: queue.Queue = queue.Queue()
        self._busy = False
        self._status_callback = status_callback
        self._schedule_poll()

    def _schedule_poll(self):
        self.root.after(50, self._poll)

    def _poll(self):
        try:
            if not self._busy:
                while True:
                    func, on_done = self._requests.get_nowait()
                    self._busy = True
                    try:
                        value = func()
                    except Exception as exc:
                        log(f"Dateidialog-Fehler: {traceback.format_exc()}")
                        on_done(None, str(exc))
                    else:
                        on_done(value, None)
                    finally:
                        self._busy = False
        except queue.Empty:
            pass
        self._schedule_poll()

    def start_open_dialog(self, on_done):
        """Stellt den Dialog in die Warteschlange und kehrt sofort zurueck.
        `on_done(pfad_oder_leer, fehlertext_oder_None)` wird auf dem
        Tk-Hauptthread aufgerufen, sobald der Dialog geschlossen ist."""
        from tkinter import filedialog

        root = self.root

        def _dialog():
            self._set_status("Dateiauswahl geöffnet – bitte dort eine .ttl-Datei wählen.")
            # Startfenster voruebergehend "immer im Vordergrund" und als
            # Besitzer des Dialogs angeben. Unter Windows liegt ein Fenster
            # immer ueber seinem Besitzer; ist der Besitzer "topmost", sollte
            # der Dialog damit auch ueber einem Vollbild-Browser erscheinen.
            # (Ohne parent= hing der Dialog an keinem sichtbaren Fenster und
            # landete hinter dem Browser.) Auf Windows NICHT geprueft.
            try:
                root.deiconify()
                root.lift()
                root.attributes("-topmost", True)
                root.focus_force()
            except Exception as exc:
                log(f"Startfenster konnte nicht nach vorne geholt werden: {exc}")
            try:
                return filedialog.askopenfilename(
                    parent=root,
                    title=OPEN_DIALOG_TITLE,
                    filetypes=[("Turtle-Dateien", "*.ttl"), ("Alle Dateien", "*.*")],
                )
            finally:
                try:
                    root.attributes("-topmost", False)
                except Exception:
                    pass
                self._set_status("Bereit.")

        self._requests.put((_dialog, on_done))

    def bring_dialog_to_front(self):
        """Holt einen bereits offenen Dateidialog nach vorne. Laeuft im
        Flask-Thread, deshalb nur ueber die Win32-API, nicht ueber Tk. Auf
        anderen Systemen ohne Wirkung. Auf Windows NICHT geprueft."""
        if not sys.platform.startswith("win"):
            return
        try:
            from ctypes import wintypes
            user32 = ctypes.windll.user32
            user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
            user32.FindWindowW.restype = wintypes.HWND
            user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
            user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
            user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                                            ctypes.c_int, ctypes.c_int, wintypes.UINT]
            user32.SetForegroundWindow.argtypes = [wintypes.HWND]
            hwnd = user32.FindWindowW("#32770", OPEN_DIALOG_TITLE)
            if not hwnd:
                log("Dateidialog nach vorne holen: Fenster nicht gefunden")
                return
            pid = wintypes.DWORD(0)
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value != os.getpid():
                log("Dateidialog nach vorne holen: Fenster gehoert zu anderem Prozess")
                return
            SW_RESTORE = 9
            SWP_NOSIZE, SWP_NOMOVE, SWP_SHOWWINDOW = 0x0001, 0x0002, 0x0040
            user32.ShowWindow(hwnd, SW_RESTORE)
            user32.SetWindowPos(hwnd, wintypes.HWND(-1), 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW)
            user32.SetForegroundWindow(hwnd)
        except Exception as exc:
            log(f"Dateidialog nach vorne holen fehlgeschlagen: {exc}")

    def _set_status(self, text):
        if self._status_callback:
            try:
                self._status_callback(text)
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Beenden mit Schutz vor Datenverlust
# ---------------------------------------------------------------------------

def quit_gate(fpv_app, ask, show_error, confirm=None) -> bool:
    """Prueft vor dem Beenden ueber das Startfenster, ob die Oberflaeche noch
    nicht gespeicherte Eintraege gemeldet hat (STATE.pending, siehe
    /api/pending). Rueckgabe True = Beenden darf weitergehen.

    `ask(titel, text)` liefert True (speichern und beenden), False (beenden
    ohne Speichern) oder None (abbrechen); `show_error(titel, text)` zeigt einen
    Fehler. Beides wird uebergeben, damit die Logik ohne Tk testbar ist.

    `confirm(titel, text)` -> True/False: einfache Sicherheitsabfrage, wenn
    NICHTS vorgemerkt ist (Projektregel: jede destruktive Handlung braucht
    eine Rueckfrage). Ohne `confirm` wird in diesem Fall nicht gefragt.
    Ist der Dateiauswahldialog noch offen, wird nicht beendet."""
    with fpv_app.STATE.lock:
        dialog_open = getattr(fpv_app.STATE, "choose", {}).get("status") == "open"
    if dialog_open:
        show_error(
            "FPV-Editor",
            "Das Fenster \u201eTTL-Datei \u00f6ffnen\u201c ist noch ge\u00f6ffnet.\n\n"
            "Bitte dieses Fenster zuerst schlie\u00dfen (Datei w\u00e4hlen oder "
            "\u201eAbbrechen\u201c) und dann erneut beenden.",
        )
        return False
    with fpv_app.STATE.lock:
        pending = fpv_app.STATE.pending
        items = list(pending["items"]) if pending and pending.get("items") else []
        version = pending.get("version") if pending else None
    if not items:
        if confirm is None:
            return True
        ok = bool(confirm(
            "FPV-Editor beenden?",
            "Den FPV-Editor wirklich beenden?\n\n"
            "Danach funktioniert die Seite im Browser nicht mehr; das "
            "Browserfenster kann anschlie\u00dfend geschlossen werden.",
        ))
        if not ok:
            log("Beenden im Startfenster abgebrochen")
        return ok

    names = []
    for item in items[:6]:
        data = (item or {}).get("data") or {}
        names.append((data.get("pref") or data.get("id") or "(ohne Bezeichnung)") + ("" if item.get("original_id") else " (neu)"))
    more = len(items) - len(names)
    n = len(items)
    answer = ask(
        "FPV-Editor beenden",
        (f"{n} Eintrag ist" if n == 1 else f"{n} Eintr\u00e4ge sind") + " noch nicht gespeichert:\n\n"
        + "\n".join("  \u2022 " + x for x in names)
        + (f"\n  \u2026 und {more} weitere" if more > 0 else "")
        + "\n\nJetzt speichern und beenden?\n\n"
        "Ja = speichern und beenden\nNein = beenden ohne Speichern\nAbbrechen = zur\u00fcck zum Editor",
    )
    if answer is None:
        log("Beenden abgebrochen (nicht gespeicherte Eintr\u00e4ge)")
        return False
    if answer:
        body, status = fpv_app.save_batch(items, version)
        if status != 200:
            log(f"Speichern vor dem Beenden fehlgeschlagen: HTTP {status}: {body.get('error')}")
            show_error(
                "FPV-Editor \u2013 Speichern fehlgeschlagen",
                f"{body.get('error', 'Unbekannter Fehler')}\n\nDas Programm wurde NICHT beendet und es wurde nichts "
                "geschrieben. Bitte im Browserfenster pr\u00fcfen und speichern.",
            )
            return False
        log(f"Vor dem Beenden gespeichert: {', '.join(body.get('saved_ids', []))}")
        return True
    with fpv_app.STATE.lock:
        if fpv_app.STATE.loaded is not None:
            fpv_app.core.clear_recovery(fpv_app.STATE.loaded.path)
        fpv_app.STATE.pending = None
    log("Beenden ohne Speichern gew\u00e4hlt; Zwischensicherung gel\u00f6scht")
    return True


# ---------------------------------------------------------------------------
# Hauptprogramm
# ---------------------------------------------------------------------------

def main():
    log("Start von launcher.py")

    # Pythons eigenes logging-Modul (das Flask/Werkzeug intern für
    # unbehandelte Ausnahmen in Anfragen nutzt) schreibt ohne eigene
    # Konfiguration nur an stderr — in der --noconsole-EXE geht das
    # komplett ins Leere. Ab hier landet jede WARNING/ERROR-Meldung
    # zusätzlich in startup.log, damit z. B. ein 500-Fehler beim Laden
    # von static/index.html im gebauten EXE nicht mehr unsichtbar bleibt.
    try:
        import logging

        file_handler = logging.FileHandler(LOG_PATH, encoding="utf-8")
        file_handler.setLevel(logging.WARNING)
        file_handler.setFormatter(logging.Formatter("[%(asctime)s] [%(name)s] %(levelname)s: %(message)s"))
        logging.getLogger().addHandler(file_handler)
        logging.getLogger().setLevel(logging.WARNING)
    except Exception:
        log(f"Konnte Python-Logging nicht zusätzlich in startup.log umleiten: {traceback.format_exc()}")

    # Vollständigkeitsprüfung des gesamten Programmordners anhand des beim
    # Build erzeugten Manifests (nur im gebauten Programm). Sie läuft VOR dem
    # Import der App, damit auch ein beschädigter Ordner verständlich gemeldet
    # wird statt mit einem Python-Traceback. Fehlt das Manifest selbst, wird
    # nur protokolliert; die Oberflächenprüfung unten bleibt dann bestehen.
    location_note = ""
    try:
        import bundle_check

        location_hints = bundle_check.location_warnings(PROGRAM_DIR)
        for hint in location_hints:
            log(f"Standorthinweis: {hint}")
        location_note = " ".join(location_hints)

        if getattr(sys, "frozen", False):
            manifest = bundle_check.load_manifest(PROGRAM_DIR)
            if manifest is None:
                log(f"Kein lesbares {bundle_check.MANIFEST_NAME} in {PROGRAM_DIR}; Dateiprüfung übersprungen.")
            else:
                started = time.time()
                problems = bundle_check.verify_bundle(PROGRAM_DIR, manifest)
                log(
                    f"Dateiprüfung: {manifest.get('file_count', '?')} Dateien, "
                    f"{len(problems)} Abweichung(en), {time.time() - started:.2f} s "
                    f"(Build vom {manifest.get('created', '?')})"
                )
                if problems:
                    for p in problems:
                        log(f"Abweichung: {p}")
                    text = bundle_check.describe_bundle_problems(problems, PROGRAM_DIR)
                    if location_note:
                        text += f"\n\nHinweis: {location_note}"
                    show_fatal_error(
                        "FPV-Editor – Programm unvollständig",
                        text + f"\n\nDetails in: {LOG_PATH}",
                    )
                    sys.exit(1)
    except SystemExit:
        raise
    except Exception:
        # Die Prüfung ist eine Hilfe, kein Startvoraussetzung: ein Fehler darin
        # darf den Start nicht verhindern.
        log(f"Dateiprüfung selbst fehlgeschlagen (Start wird fortgesetzt): {traceback.format_exc()}")

    try:
        import app as fpv_app
    except Exception:
        show_fatal_error(
            "FPV-Editor – Startfehler",
            "Der Server konnte nicht initialisiert werden (Modul app.py/fpv_core.py).\n\n"
            + traceback.format_exc()
            + f"\n\nDetails in: {LOG_PATH}",
        )
        sys.exit(1)

    # Vollständigkeitsprüfung der Oberfläche VOR dem Serverstart: Fehlt z. B.
    # static\index.html (Ordner unvollständig kopiert/synchronisiert), gäbe es
    # sonst nur wiederholte "Internal Server Error"-Antworten ohne erkennbare
    # Ursache. Stattdessen: verständliche Meldung, Eintrag im Log, Ende.
    problem = fpv_app.describe_static_problem()
    if problem:
        try:
            internal = os.path.join(os.path.dirname(sys.executable), "_internal")
            if getattr(sys, "frozen", False) and os.path.isdir(internal):
                log("Inhalt von _internal: " + ", ".join(sorted(os.listdir(internal))[:80]))
        except OSError as exc:
            log(f"_internal nicht lesbar: {exc}")
        show_fatal_error(
            "FPV-Editor – Programm unvollständig",
            problem + f"\n\nDetails in: {LOG_PATH}",
        )
        sys.exit(1)
    log("Oberflächendateien vollständig (index.html, app.js)")

    try:
        server, port = fpv_app.make_wsgi_server()
    except Exception:
        show_fatal_error(
            "FPV-Editor – Startfehler",
            "Der lokale Server konnte nicht gestartet werden (Port belegt? "
            "Firewall?).\n\n" + traceback.format_exc() + f"\n\nDetails in: {LOG_PATH}",
        )
        sys.exit(1)

    url = f"http://127.0.0.1:{port}/"
    log(f"Server-Objekt erstellt für {url}")

    def run_server():
        # serve_forever() lief bisher OHNE jede Absicherung in diesem Thread:
        # eine Ausnahme darin hätte den Thread lautlos beendet (Python
        # schreibt unbehandelte Thread-Ausnahmen nur nach stderr, das in der
        # --noconsole-EXE nirgendwo ankommt) — der Tk-Bereitschaftstest hätte
        # dann ewig "Timeout" gemeldet, ohne jeden Hinweis auf die Ursache.
        try:
            server.serve_forever()
        except Exception:
            log(f"Server-Thread abgestürzt: {traceback.format_exc()}")

    server_thread = threading.Thread(target=run_server, daemon=True, name="fpv-flask")
    server_thread.start()

    try:
        import tkinter as tk
    except Exception:
        show_fatal_error(
            "FPV-Editor – Startfehler",
            "Tkinter ist in dieser Python-Umgebung nicht verfügbar. Der Server "
            f"läuft trotzdem unter {url} — bitte diese Adresse manuell im "
            f"Browser öffnen.\n\nDetails in: {LOG_PATH}",
        )
        # Server bewusst NICHT beenden: Notlösung, damit zumindest ohne
        # Startfenster weitergearbeitet werden kann.
        server_thread.join()
        return

    root = tk.Tk()
    root.title("FPV-Editor")
    root.geometry("560x290" if location_note else "560x230")
    root.resizable(False, False)

    frame = tk.Frame(root, padx=16, pady=16)
    frame.pack(fill="both", expand=True)

    tk.Label(frame, text="FPV-Editor läuft lokal.", font=("Segoe UI", 11, "bold")).pack(anchor="w")
    tk.Label(
        frame,
        text="Dieses Fenster muss während der Arbeit geöffnet bleiben.",
        font=("Segoe UI", 9),
        fg="#555555",
    ).pack(anchor="w", pady=(0, 10))

    url_var = tk.StringVar(value=url)
    url_entry = tk.Entry(frame, textvariable=url_var, font=("Consolas", 10), justify="center")
    url_entry.pack(fill="x", pady=(0, 4))
    url_entry.configure(state="readonly")

    status_var = tk.StringVar(value="Server wird gestartet …")
    tk.Label(frame, textvariable=status_var, font=("Segoe UI", 9), fg="#145d4d").pack(anchor="w", pady=(0, 10))
    if location_note:
        tk.Label(
            frame, text="Hinweis: " + location_note, font=("Segoe UI", 8), fg="#8a6d1a",
            wraplength=520, justify="left",
        ).pack(anchor="w", pady=(0, 6))

    fpv_app.STATE.dialog_bridge = DialogBridge(root, status_callback=status_var.set)

    button_row = tk.Frame(frame)
    button_row.pack(fill="x")

    def do_open_browser():
        status_var.set("Öffne Browser …")
        root.update_idletasks()
        ok, detail = open_browser(url)
        log(f"Browserstart (manuell ausgelöst): erfolg={ok}; {detail}")
        status_var.set("Browser geöffnet." if ok else "Browser konnte nicht automatisch geöffnet werden — Adresse oben kopieren.")

    def ask_save_quit(title, text):
        from tkinter import messagebox
        return messagebox.askyesnocancel(title, text, icon="warning", default="cancel", parent=root)

    def confirm_quit(title, text):
        from tkinter import messagebox
        return messagebox.askyesno(title, text, icon="question", default="no", parent=root)

    def show_error_box(title, text):
        from tkinter import messagebox
        messagebox.showerror(title, text, parent=root)

    def do_quit(*_args, ask=True):
        # ask=False nur, wenn die Browserseite das Beenden bereits selbst
        # (mit Rueckfrage) entschieden hat (STATE.shutdown_requested).
        if ask and not quit_gate(fpv_app, ask_save_quit, show_error_box, confirm_quit):
            return
        status_var.set("Wird beendet …")
        root.update_idletasks()
        log("Beenden angefordert (Fensterschaltfläche/Schließen)")
        try:
            server.shutdown()
        except Exception as exc:
            log(f"Fehler beim Server-Shutdown: {exc}")
        root.after(150, root.destroy)

    tk.Button(button_row, text="Im Browser öffnen", command=do_open_browser).pack(side="left")
    tk.Button(button_row, text="App beenden …", command=do_quit).pack(side="right")

    root.protocol("WM_DELETE_WINDOW", do_quit)

    def poll_shutdown_flag():
        if fpv_app.STATE.shutdown_requested:
            do_quit(ask=False)
            return
        root.after(300, poll_shutdown_flag)

    root.after(300, poll_shutdown_flag)

    def start_sequence():
        ready, detail = wait_for_server_ready(url, timeout_s=8.0)
        if not ready:
            status_var.set("Server antwortet nicht — siehe startup.log.")
            log(f"HTTP-Bereitschaftstest fehlgeschlagen: {detail}")
            show_fatal_error(
                "FPV-Editor – Server antwortet nicht richtig",
                "Der lokale Server läuft, liefert aber die Startseite nicht aus.\n\n"
                f"Befund: {detail}\n\n"
                f"Näheres steht in: {LOG_PATH}\n"
                "Bitte diese Datei an die Betreuung des Programms weitergeben.",
            )
            return
        status_var.set("Server bereit. Öffne Browser …")
        ok, detail = open_browser(url)
        log(f"Browserstart (automatisch): erfolg={ok}; {detail}")
        status_var.set(
            "Bereit — Browserfenster sollte offen sein."
            if ok
            else "Bereit — Browser konnte nicht automatisch geöffnet werden. Adresse oben markieren und kopieren."
        )

    threading.Thread(target=start_sequence, daemon=True).start()

    try:
        root.mainloop()
    finally:
        try:
            server.shutdown()
        except Exception:
            pass
        log("launcher.py beendet")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        show_fatal_error(
            "FPV-Editor – unerwarteter Fehler",
            traceback.format_exc() + f"\n\nDetails in: {LOG_PATH}",
        )
        sys.exit(1)
