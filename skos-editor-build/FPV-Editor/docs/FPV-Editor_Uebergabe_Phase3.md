# FPV-Editor – Übergabe Phase 3

Stand: 14.10.2026 · Abgelöst durch `../FPV-Editor_Uebergabe_Antigravity.md`. Nachfolger von `FPV-Editor_Uebergabe_Phase2.md` und
`docs/FPV-Editor_Uebergabe_GUI-Phase.md` (beide bleiben als Hintergrund
erhalten; wo sie dem Folgenden widersprechen, gilt dieses Dokument).

## 1. Worum es geht
Lokale Windows-11-App (Flask + RDFLib, statisches HTML/JS, Tk-Startfenster,
PyInstaller `--onedir`) zum Bearbeiten der SKOS/Turtle-Datei `fpv.ttl`
(Vokabular von fraktionsprotokolle.de, ca. 857 Konzepte). Nutzer sind mehrere
Kolleginnen und Kollegen mit wenig SKOS-Kenntnis. Randbedingungen: keine
Adminrechte, kein installiertes Python, Verteilung als ZIP, lokal entpackt.
`fpv.ttl` liegt in Git.

## 2. Stand (alles per Test bzw. Linux-Browserlauf geprüft, NICHT auf Windows)
- 95 Tests grün (`python -m pytest tests/test_editor.py -q`), `node --check static/app.js` ok.
- **Verteilung:** `bundle_check.py` (Manifest Größe+SHA-256, Cloud-Platzhalter-
  und Ortswarnung), `make_release.py` (ZIP bauen und gegen Manifest prüfen),
  `LIES-MICH.txt`, Log-Fallback nach `%LOCALAPPDATA%\FPV-Editor`.
- **Oberfläche:** Baum füllt die Fensterhöhe; Kopfzeile mit „Datei öffnen …“,
  „Prüfen“, „Frühere Stände wiederherstellen …“; „Kopie zum Ausprobieren“
  entfernt (ebenso der Endpunkt `/api/working-copy`).
- **Sammel-Speichern:** Änderungen mehrerer Einträge werden vorgemerkt
  (`App.drafts`) und mit `POST /api/save-batch` gemeinsam gespeichert: alles
  oder nichts, eine Versionsprüfung, eine Gesamtprüfung, eine Synonymprüfung,
  **eine** Sicherung, ein Schreibvorgang.
- **Sicherung:** ein Ort, `%LOCALAPPDATA%\FPV-Editor\backups\<Dateischlüssel>`
  (oder manuell gewählter Ordner); scheitert er, bleibt die TTL unverändert.
- **Beenden-Schutz (neu):** Abfrage im Browser („Speichern und beenden“ /
  „Beenden ohne Speichern“ / „Zurück“) und im Tk-Startfenster
  (`launcher.quit_gate`, `askyesnocancel`); `/api/quit` liefert 409
  `PendingChanges`, solange etwas vorgemerkt ist (außer `force`).
- **Zwischensicherung (neu):** Oberfläche meldet Vormerkungen ca. 1,5 s nach
  Änderung per `POST /api/pending`; alle 10 Min. (`AUTOSAVE_INTERVAL_MS` in
  `static/app.js`) Schreiben nach `%LOCALAPPDATA%\FPV-Editor\recovery\<Schlüssel>.json`;
  beim Öffnen Dialog Wiederherstellen/Verwerfen/Später (`GET /api/recovery`,
  `POST /api/recovery-discard`). Die TTL wird dabei nie verändert.
- Details zu allem: `README.md`.

## 3. Arbeitsregeln (vom Nutzer vorgegeben)
- Bei Unklarheit nachfragen; präzise antworten, auf reale Quellen beziehen,
  nichts erfinden, Unbekanntes als unbekannt benennen.
- Windows-/Browserverhalten ist hier nicht geprüft; so kennzeichnen.
- Auslieferung: nur geänderte Einzeldateien (oder auf Wunsch ZIP). Vor jeder
  Lieferung `python -m pytest tests/test_editor.py -q` und `node --check static/app.js`.
- `.bat`-Dateien immer CRLF, ohne BOM. Python auf fremden Dateien mit `-I`.
- Jede Aktion der Oberfläche muss sichtbare Rückmeldung geben.
- UI-Tests: Playwright mit `/opt/pw-browsers/chromium` (nur Linux).

## 4. Offene Punkte
- **Alles auf echtem Windows ungeprüft**, besonders: Tk-Beendendialog,
  Schreibrechte auf `%LOCALAPPDATA%`, Verhalten nach echtem Absturz.
- Ursache des früheren Nextcloud-Fehlers (`index.html` FileNotFoundError) ist
  unbewiesen; Rückfragen zu Dateigröße 23985 Bytes/Cloud-Symbol blieben offen.
- 23 bestehende Synonymkollisionen (siehe `kollisionen-synonymliste.md`).
- Datenfehler in `fpv.ttl`: `ex:WaffenSS` `skos:closeMatch` mit `hhttps://…`;
  `ex:IDA` mit `skos:altLabelLabel`.
- Offene Fachfragen: bidirektionales `skos:related`, Groß-/Kleinschreibung bei
  Typesense, Kontakttext für geschützte Blöcke.
- Live-Synonymprüfung im Formular prüft nur gegen den gespeicherten Stand;
  Kollisionen zwischen zwei vorgemerkten Einträgen meldet erst das Speichern.

## 5. Dateien
`app.py` (Flask, `save_batch`, Endpunkte) · `fpv_core.py` (Parsing, Schreiben,
Sicherung, Zwischensicherung) · `launcher.py` (Tk, Start, `quit_gate`) ·
`bundle_check.py`, `make_release.py` · `static/index.html`, `static/app.js` ·
`tests/test_editor.py` · `build_windows.bat`, `diagnose_windows.bat`,
`start_mit_python.bat` · `LIES-MICH.txt`, `README.md`.
