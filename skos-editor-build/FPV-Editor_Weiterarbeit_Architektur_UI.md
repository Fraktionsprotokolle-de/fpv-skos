# FPV-Editor – Weiterarbeit im neuen Workspace (Architektur & UI)

Stand: 24.11.2026 · Ergänzt `FPV-Editor_Uebergabe_Antigravity.md` um die
Ergebnisse der ersten Bestandsaufnahme sowie konkrete Architektur- und
UI-Vorschläge für die nächste Arbeitsphase im lokalen Git-Repository.

Verbindliche Grundlagen bleiben:
- `AGENTS.md` (Arbeitsregeln, Deutsch, nichts Unbelegtes behaupten, Design- und
  `fpv_core.py`-Änderungen vorab abstimmen)
- `FPV-Editor_Uebergabe_Antigravity.md` (Projektvorgaben, Datenmodell, Abläufe)

---

## 1. Aktueller Stand (neu gegenüber der Übergabe)

- **Windows-Funktionsstand:** Der Nutzer hat die App und den Build-Prozess
  ausprobiert (auf diesem Rechner sowie auf dem Dienstlaptop). Alles funktioniert
  soweit wie in `FPV-Editor_Uebergabe_Antigravity.md` beschrieben.
- **Umzug aus Nextcloud:** Der Projektordner wird aus Nextcloud in ein lokales
  Git-Repository verschoben, damit `.venv/`, `build/` und `dist/` nicht mehr
  durch Cloud-Sync gesperrt werden.
- **Bisher keine Code-Änderungen durchgeführt:** Alle Dateien entsprechen noch
  dem unveränderten Übergabestand vom 24.11.2026.

---

## 2. Einrichtung im neuen Workspace

### Voraussetzungen auf diesem Rechner
Bei der ersten Prüfung am 24.11.2026 wurde gefunden:
- `Python 3.13.14` (64-Bit, Microsoft Store), **kein** `py`-Launcher und **kein**
  Python 3.14 (wird von `build_windows.bat` und `diagnose_windows.bat` verlangt).
- **Kein** Node.js im `PATH` (wird laut `AGENTS.md` für `node --check static\app.js` benötigt).
- Noch keine `.venv`, kein `wheels/`-Ordner und keine Beispiel-`fpv.ttl` im Projektordner.

### Einrichtungsschritte
1. **Python 3.14 (64-Bit)** (von python.org, inkl. `py`-Launcher) und **Node.js**
   installieren (falls noch nicht geschehen). *(Alternativ zum reinen Testen ohne
   Build: `.venv` mit vorhandenem Python 3.13.14 anlegen.)*
2. `.gitignore` im Projektordner anlegen (Vorlage siehe Abschnitt 6).
3. Virtuelle Umgebung einrichten und Ausgangszustand prüfen:
   ```bat
   py -3.14-64 -m venv .venv
   .venv\Scripts\pip install -r requirements.txt pytest
   .venv\Scripts\python -m pytest tests\test_editor.py -q
   node --check static\app.js
   ```
   Erwartet: **102 passed** und fehlerfreier JS-Syntaxcheck.
4. *(Optional für UI-Arbeit)* Eine (gern gekürzte) Beispiel-`fpv.ttl` bereitstellen,
   um Änderungen realistisch im Browser prüfen zu können.

---

## 3. Architektur-Befunde & Verbesserungsvorschläge

Die Grundarchitektur ist sehr solide (blockweises, quellenerhaltendes Editieren;
feste Schreibkette SHA-256 → Validierung → verifizierte Sicherung mit `fsync` +
Readback → atomares `os.replace`; geschützte Blöcke; `127.0.0.1` + Token;
`DialogBridge`; testbares `quit_gate`; Manifestprüfung).

Folgende konkrete Punkte sind bei der Code-Durchsicht aufgefallen (alle vor
Umsetzung mit dem Nutzer abstimmen, insbesondere Änderungen in `fpv_core.py`
und Build-Skripten):

1. **Zeilenumbrüche in `skos:note` (`fpv_core.py:507–508, 607`):**
   - Im Formular ist `#f-note` ein `<textarea>`, aber `_escape_literal()` escaped
     nur `\` und `"`, nicht `\n`/`\r`.
   - Ein Druck auf Enter in der Kurzbeschreibung erzeugt ein rohes Newline in
     einem einfach zitierten Turtle-Literal (`"…"@de`) → ungültiges Turtle.
     `validate_whole_file()` blockiert das Schreiben zuverlässig, meldet aber
     einen für Anwenderinnen schwer verständlichen RDFLib-Syntaxfehler.
   - *Vorschlag:* Mit dem Nutzer klären, ob Zeilenumbrüche in `skos:note` zu
     Leerzeichen normalisiert oder als `\n` escaped werden sollen (Abgleich mit
     `fpv.ttl` / `validate_fpv.py`), plus Hinweis/Prüfung im Formular.

2. **Doppelte Speicherlogik in `app.py` (`api_save` vs. `save_batch`):**
   - `api_save()` (`app.py:493–616`) dupliziert ~120 Zeilen von `save_batch()`
     (`app.py:165–284`), obwohl das Frontend nur noch `/api/save-batch` aufruft.
   - Beide weichen bereits leicht ab (`api_save` leert `STATE.pending` und
     Recovery nicht).
   - *Vorschlag:* `api_save()` als dünnen Wrapper um `save_batch()` umbauen
     (Rückgabeformat für bestehende Tests beibehalten).

3. **Unbeabsichtigte Ordner-Erzeugung in `storage_check()` (`fpv_core.py:1445–1475`):**
   - Seit Phase 3 wird nur noch an einem Ort gesichert (`backup_write_location`),
     aber `storage_check()` iteriert weiter über alle 10 historischen Orte aus
     `backup_candidate_locations()` und ruft dort `os.makedirs(path, exist_ok=True)`
     auf. Dadurch entstehen leere `fpv_backups`-Ordner neben `fpv.ttl` (im
     Git-Repo) und im Programmordner.
   - *Vorschlag:* Nur den aktiven Sicherungsort + den TTL-Ordner prüfen und keine
     leeren Ordner zurücklassen.

4. **Mehrfaches RDFLib-Graph-Parsing & Live-Synonymprüfung:**
   - `rename_concept()` (`fpv_core.py:1141–1184`) parst den RDF-Graph 5× plus
     anschließende Gesamtvalidierung; `save_batch()` parst 2–3×; `/api/synonym-check`
     (`app.py:772`) liest die TTL-Datei bei jeder Eingabepause komplett von Platte.
   - *Vorschlag:* Graph/Synonym-Index pro `sha256` in `STATE` cachen bzw. intern
     weiterreichen. Zudem `/api/synonym-check` um die übrigen `App.drafts`
     erweitern (löst Punkt 10.6 aus der Übergabe).

5. **Frontend-Aufteilung (weiterhin ohne Build-Tool/npm) & kleiner CSS-Fund:**
   - `static/app.js` (2.367 Zeilen) und eingebettetes CSS in `static/index.html`
     (~340 Zeilen) lassen sich in `static/styles.css` + 4–5 kleine JS-Dateien
     (API, Dialoge, Baum, Formular, Steuerung) strukturieren.
     *Hinweis:* Erfordert nach Absprache Anpassung von `REQUIRED_STATIC_FILES`
     in `app.py` sowie ggf. den Vorhandenseins-Checks in `build_windows.bat` /
     `diagnose_windows.bat`.
   - Kleiner CSS-Fehler: `.backup-more` (`static/app.js:237`) hat aktuell keine
     CSS-Regel in `static/index.html` (die beiden Schaltflächen im
     Sicherungsdialog kleben ohne Abstand aneinander).

---

## 4. Vorschläge für die Nutzeroberfläche (mit Nutzer abstimmen)

Zielgruppe: Kolleginnen und Kollegen mit wenig SKOS- und Computererfahrung.

1. **Einheitliches Dialog- & Rückmeldungskonzept (offener Punkt 10.2):**
   - Die 7 rohen Browser-`confirm()`-Aufrufe (`app.js:258, 261, 455, 648, 2036,
     2221, 2256`) durch eigene Bestätigungs-Modals im App-Design ersetzen – mit
     eindeutigen Schaltflächen (*„Eintrag endgültig löschen“* statt *„OK“*).
   - Entscheidung klären: Fehler, Sicherheitsabfragen, Recovery und Umbenennen
     bleiben Modals; harmlose Routine-Erfolge und Abbrüche ggf. über ein gut
     sichtbares, oben fixiertes Status-Banner / Toast (mit Schließen-Knopf) statt
     blockierender Modals.

2. **Nativer Ordnerdialog statt Pfad-Eintippen bei „Sicherungsort wählen“:**
   - `doChooseBackupDir()` (`app.js:2009`) verlangt derzeit das Kopieren eines
     Explorer-Pfads in ein Textfeld. Über `DialogBridge` lässt sich ein nativer
     Windows-Ordnerdialog (`filedialog.askdirectory`) anbieten (wie bei „Datei
     öffnen …“).

3. **Formular-Bedienhilfen & Direkt-Feedback:**
   - Alle Pflichtfelder (`Kennung`, `Bevorzugte Benennung`, `Art des Konzepts`,
     `Kurzbeschreibung`) einheitlich kennzeichnen und inline vorprüfen (inkl.
     URL-Check für `exactMatch`/`closeMatch` wie `hhttps://…`).
   - Verknüpfte Einträge in `skos:related` anklickbar machen (`jumpToConcept`).
   - Optional: „Öffnen ↗“-Knopf neben `exactMatch`/`closeMatch`-URLs zur schnellen
     Prüfung im Browser.
   - Neu angelegte, noch nicht gespeicherte Einträge auch links im Verzeichnis
     sichtbar machen (nicht nur als Chip in der oberen Leiste).

4. **Übersichtlichkeit im Prüfungspanel & auf Laptop-Bildschirmen:**
   - Filter im Prüfungspanel rechts: `Alle` · `Fehler` · `Hinweise` (hilft bei
     den 23 bestehenden Synonym-Althinweisen in `fpv.ttl`).
   - Ruhigerer Leerzustand ohne geöffnete Datei (klare Startkarte + deaktivierte
     Datei-Aktionen statt „Nichts durchgeführt“-Modals).
   - Etwas kompakterer Kopfbereich für typische Laptop-Auflösungen (1366×768
     bzw. 150 %-Skalierung).
   - Optionale Tastaturkürzel: `Strg+S` (Speichern), Fokus-Kürzel für die Suche.

---

## 5. Weitere Aufgabe aus der Übergabe (Abschnitt 11)

- Veraltete Stellen in `README.md` bereinigen (Testanzahl 24 → 102, Windows-
  Speicherstatus aktualisieren, Platzierung von „Sicherungsort wählen“ anpassen).

---

## 6. Empfohlene `.gitignore`

```gitignore
# Virtuelle Python-Umgebung
.venv/
venv/

# Offline-Wheels (lokal für build_windows.bat, gehören nicht ins Repo)
wheels/

# PyInstaller-Build-Artefakte und Auslieferungs-ZIPs
build/
dist/
*.spec

# Python- und Test-Caches
__pycache__/
*.py[cod]
.pytest_cache/

# Laufzeitdateien, Logs und lokale Sicherungen
startup.log
fpv_backups/
*.ttl.bak

# Falls fpv.ttl testweise in den Projektordner kopiert wird (liegt sonst in eigenem Git-Repo)
fpv.ttl

# Windows / Editor
Thumbs.db
Desktop.ini
.vscode/
.idea/
```

---

## 7. Einstieg im neuen Workspace (Start-Nachricht für den neuen Chat)

> Lies bitte `AGENTS.md`, `FPV-Editor_Uebergabe_Antigravity.md` und
> `FPV-Editor_Weiterarbeit_Architektur_UI.md`. Richte zunächst `.gitignore` und
> die Testumgebung ein (102 Tests + `node --check`), danach stimmen wir ab,
> welche Architektur- und UI-Verbesserungen wir in welcher Reihenfolge umsetzen.
