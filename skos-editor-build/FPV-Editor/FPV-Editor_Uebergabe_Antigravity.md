# FPV-Editor – Projektübergabe für Google Antigravity

Stand: 24.11.2026 · Löst `docs/FPV-Editor_Uebergabe_Phase3.md` ab. Ältere
Übergaben liegen in `docs/` und dienen nur als Hintergrund; wo sie diesem
Dokument widersprechen, gilt dieses Dokument.

Die verbindlichen Arbeitsregeln für Agenten stehen in `AGENTS.md` (wird von
Antigravity automatisch geladen). Die technische Gesamtdokumentation ist
`README.md` (Hinweis zu veralteten Stellen darin: Abschnitt 11).

---

## 1. Worum es geht

Lokale Windows-11-Anwendung zum Bearbeiten der SKOS/Turtle-Datei `fpv.ttl`,
des kontrollierten Vokabulars der Edition *Fraktionen im Deutschen Bundestag
1949–2005* (fraktionsprotokolle.de, rund 857 Konzepte). `fpv.ttl` liegt in
Git (nicht in diesem Paket).

- **Nutzer:** Sven (Historiker am KGParl, Digital Humanities: TEI-XML,
  SKOS/RDF, Python; Arbeitssprache Deutsch) sowie Kolleginnen und Kollegen
  **mit wenig SKOS- und Computererfahrung**.
- **Randbedingungen bei den Anwendern:** keine Administratorrechte, kein
  installiertes Python, Verteilung als ZIP, lokal entpackt.
- **Technik:** Flask + RDFLib im Hintergrund, statisches HTML/CSS/Vanilla-JS
  im Standardbrowser, kleines Tk-Startfenster (`launcher.py`), Auslieferung
  als PyInstaller-`--onedir`-Build. Server bindet nur an `127.0.0.1` auf
  zufälligem Port, mutierende Aufrufe sind per Token (`X-FPV-Token`)
  geschützt. Keine Internetanbindung, keine CDNs.

## 2. Projektvorgaben (vom Nutzer, verbindlich)

1. Usability auch für wenig computergewandte Menschen.
2. Klares, einfach verständliches Design.
3. **Alle destruktiven Handlungen** (Programm schließen, Datensätze löschen
   usw.) brauchen **eine Sicherheitsabfrage**.
4. Jede Aktion gibt **sichtbare Rückmeldung**.
5. Bei Unklarheit nachfragen, nichts erfinden, nichts als erfolgreich
   ausgeben, was nicht belegt ist.

## 3. Einrichten in Antigravity (Windows)

Voraussetzung: Python 3.14 64-Bit (wie beim Build verwendet). Im Terminal
von Antigravity im Projektordner:

```bat
py -3.14-64 -m venv .venv
.venv\Scripts\pip install -r requirements.txt pytest
.venv\Scripts\python -m pytest tests\test_editor.py -q
```

Erwartet: **102 passed**. Außerdem, falls Node.js vorhanden:

```bat
node --check static\app.js
```

Starten zum Ausprobieren ohne EXE-Build:

```bat
.venv\Scripts\python launcher.py
```

oder per Doppelklick `start_mit_python.bat` (setzt `.venv` voraus; dieses
Skript wurde **noch nie auf Windows ausgeführt**).

Hinweise:
- `pytest` steht **nicht** in `requirements.txt` und wird oben zusätzlich
  installiert (braucht Internet oder ein passendes Wheel).
- Die EXE baut `build_windows.bat` **offline aus `wheels/`**. Dieser Ordner
  ist **nicht im Paket** (er löste bei Windows Defender den Fehlalarm
  `Trojan:Win32/MalUri.A!cl` aus, siehe README). Er liegt beim Nutzer vor
  und muss vor einem Build in den Projektordner kopiert werden.
- Vor einem Build alle laufenden FPV-Editor-Fenster schließen.

## 4. Dateien

| Datei | Rolle |
|---|---|
| `AGENTS.md` | Arbeitsregeln für Agenten (automatisch geladen) |
| `FPV-Editor_Uebergabe_Antigravity.md` | dieses Dokument |
| `app.py` | Flask-App (`create_app()`), alle `/api/…`-Routen, Prozesszustand `STATE`, `save_batch`, Server-Erzeugung |
| `fpv_core.py` | TTL-Blockparser, Validierung, quellenerhaltendes Schreiben, Sicherung, Zwischensicherung, atomares Schreiben |
| `launcher.py` | EXE-Einstieg: Tk-Startfenster, Browserstart, `startup.log`, `DialogBridge` (Dateidialog), `quit_gate` (Beenden-Schutz) |
| `bundle_check.py` | Prüfung des Programmordners beim Start (Manifest mit Größe + SHA-256, Warnung bei Cloud-/Netzorten) |
| `make_release.py` | Auslieferungs-ZIP bauen und gegen Manifest prüfen |
| `static/index.html` | gesamte Oberfläche inkl. eingebettetem CSS |
| `static/app.js` | gesamte Frontend-Logik (Baum, Formular, Vormerkungen, Dialoge, Hilfe, API-Aufrufe) |
| `tests/test_editor.py` | 102 Tests (Flask-Testclient, `quit_gate`, Dateiauswahl) |
| `build_windows.bat` | Offline-Build der EXE aus `wheels/`, mit Erfolgsnachweis |
| `diagnose_windows.bat` | zweiter Build **mit** Konsole zur Fehlersuche |
| `start_mit_python.bat` | Start aus `.venv` ohne Build (ungeprüft) |
| `requirements.txt` | `Flask>=3.1,<4`, `rdflib>=7.1,<8` |
| `LIES-MICH.txt` | Installationsanleitung für Anwender |
| `README.md` | ausführliche technische Doku (teils veraltet, Abschnitt 11) |
| `kollisionen-synonymliste.md` | 23 bestehende Synonymkollisionen in `fpv.ttl` (Datenbefund) |
| `docs/` | frühere Übergaben (GUI-Phase, Phase 2, Phase 3) |

Für reine Oberflächenarbeit genügen meist `static/index.html` und
`static/app.js`; `app.py` nur, wenn der Server neue Daten liefern muss.

## 5. Oberfläche (Ist-Stand)

- **Kopfzeile:** Titel, „Hilfe“ (ausführlicher Hilfetext in `showHelp()` in
  `app.js`), „App beenden“.
- **Werkzeugleiste in Gruppen:**
  - *Datei:* „Datei öffnen …“ (einziger Weg zum Öffnen, nativer
    Windows-Dialog), Anzeige des geöffneten Pfads, „Datei schließen“.
  - *Prüfen:* „Datei prüfen“.
  - *Sicherungen:* „Frühere Stände wiederherstellen …“ und Anzeige der
    neuesten vorhandenen Sicherung.
- **Links – Konzeptverzeichnis:** Suche, Typfilter, „Zurücksetzen“, „Alle
  öffnen“, „Alle schließen“, nach Anfangsbuchstaben gruppierter Baum
  (füllt die Fensterhöhe). Geschützte Einträge mit Schloss-Symbol.
- **Mitte – Eintrag:** „＋ Neuer Eintrag“, „Änderungen speichern“, „Diesen
  Eintrag zurücksetzen“, „Eintrag löschen …“, „Kennung ändern …“;
  Formularfelder für prefLabel, altLabels (je eigenes Sprachfeld), exactMatch,
  closeMatch, skos:related, Synonymliste, note. Leiste mit **vorgemerkten**
  (noch nicht gespeicherten) Einträgen.
- **Rechts – Prüfung:** Ampel mit Fehler-/Hinweiszahl, anklickbare Befunde
  („Zum Eintrag springen“).
- **Rückmeldungen** laufen über ein zentrales Modal (`showModal`,
  `showChoiceModal`, `showNothingDone`); Fehlerbehandlung zentral in
  `handleApiError`. Body-Texte werden per `textContent` gesetzt (kein HTML).
- **Design-Ausgangspunkt:** Grund `#f3f6f3`, Text `#1d302e`, Primär
  `#145d4d`, Kopfzeile `#163b31`, Fehler `#a43834`, Warnung `#8a6d1a`, OK
  `#1f7a4d`; Segoe UI für Bedienelemente, Georgia für Überschriften,
  Monospace für IDs. Änderungen sind erwünscht, aber mit dem Nutzer
  abzustimmen.

## 6. Zentrale Abläufe

### 6.1 Mehrere Einträge bearbeiten, gemeinsam speichern
Änderungen an mehreren Einträgen werden im Browser vorgemerkt
(`App.drafts`) und mit `POST /api/save-batch` gemeinsam geschrieben: alles
oder nichts, eine Versionsprüfung, eine Gesamtprüfung, eine Synonymprüfung,
**eine** Sicherung, ein Schreibvorgang.

### 6.2 Schreiben und Sicherung
Feste Reihenfolge: SHA-256-Versionsprüfung → Validierung der resultierenden
Gesamtdatei → **verifizierte Sicherung der alten Bytes** (schreiben, fsync,
zurücklesen, vergleichen) → erst dann die TTL ändern. Sicherungsort:
`%LOCALAPPDATA%\FPV-Editor\backups\<Dateischlüssel>` oder ein manuell
gewählter Ordner. Scheitert die Sicherung, bleibt die TTL unverändert.

Speichern blockiert nur, wenn die Datei kein gültiges Turtle mehr wäre oder
ein Fehler einen der **gerade gespeicherten** Einträge betrifft; Altfehler in
anderen Einträgen blockieren nicht.

### 6.3 Zwischensicherung (Absturzschutz)
Die Oberfläche meldet Vormerkungen ca. 1,5 s nach jeder Änderung per
`POST /api/pending` (nur Arbeitsspeicher). Alle 10 Minuten
(`AUTOSAVE_INTERVAL_MS` in `app.js`) zusätzlich nach
`%LOCALAPPDATA%\FPV-Editor\recovery\<Schlüssel>.json`. Beim Öffnen bietet
ein Dialog Wiederherstellen / Verwerfen / Später an. Die TTL wird dabei nie
verändert.

### 6.4 Datei öffnen (überarbeitet am 20.11.2026)
- `POST /api/choose` **startet** den nativen Dialog und antwortet sofort
  (`opened` bzw. `already_open`). Es gibt **höchstens einen** Dialog; jeder
  weitere Aufruf holt den offenen Dialog per Win32-API nach vorne
  (`DialogBridge.bring_dialog_to_front`).
- Die Oberfläche fragt alle 0,5 s `POST /api/choose-result` ab:
  `open`, `cancelled`, `idle` oder geladener Zustand mit `status: "loaded"`.
- Solange der Dialog offen ist, verdeckt ein Hinweis „Dateiauswahl
  geöffnet“ die Seite (ohne Schließen-Knopf, Escape wirkt nicht) mit dem
  Knopf „Fenster nach vorne holen“. Damit sind Mehrfachklicks ausgeschlossen.
- Der Tk-Dialog hat das Startfenster als `parent` und das Startfenster ist
  währenddessen `-topmost`, damit der Dialog vor einem Vollbild-Browser
  erscheint. Die Bridge-Sperre `_busy` verhindert einen zweiten Dialog.
- Behoben dabei: Früher blockierte `/api/choose` mit 120-s-Zeitgrenze und
  lieferte danach HTTP 500.

### 6.5 Beenden (überarbeitet am 20.11.2026)
- **Browser:** „App beenden“ fragt bei Vormerkungen „Speichern und beenden“ /
  „Beenden ohne Speichern“ / „Zurück zum Editor“.
- **Startfenster** (Knopf „App beenden …“ und Fensterkreuz, `quit_gate`):
  - mit Vormerkungen: Ja/Nein/Abbrechen („Ja“ speichert über `save_batch`;
    schlägt das fehl, wird nicht beendet);
  - **ohne** Vormerkungen: „Den FPV-Editor wirklich beenden?“ (Ja/Nein,
    vorausgewählt Nein) – neu, vorher wurde ohne Rückfrage beendet;
  - solange der Dateidialog offen ist, wird nicht beendet.
- `/api/quit` liefert 409 `PendingChanges`, solange etwas vorgemerkt ist
  (außer mit `force`).
- **Anzeige „beendet“:** Die Oberfläche fragt alle 4 s `GET /api/ping` ab.
  Bleibt die Antwort zweimal aus (oder schlägt ein API-Aufruf mit
  Netzwerkfehler fehl), erscheint eine nicht wegklickbare Meldung „Der
  FPV-Editor ist beendet“. So sieht die Seite nach dem Beenden nicht mehr
  aktiv aus.

## 7. Datenmodell und API

**Zustandsobjekt:** `{ path, sha256, uses_crlf, records: [...], findings: [...] }`

**Record (bearbeitbar):** `{ id, pref, lang, type, note, synonym,
alts: [{text, lang}], exact: [url], close: [url], related: [id],
protected: false, line }`

**Record (geschützt):** `{ id, protected: true, protect_reason, raw, line }`

**Finding:** `{ level: "error"|"warning", message, concept_id|null }`

**Fehlerantwort:** HTTP-Fehlercode mit `{ error, error_type }`, teils mit
`findings`.

**Endpunkte** (POST verlangt `X-FPV-Token`; `apiPost`/`apiGet` in `app.js`
erledigen das):
`GET /`, `GET /api/state`, `GET /api/backups`, `GET /api/ping`,
`GET /api/recovery`, `POST /api/open`, `/api/choose`, `/api/choose-result`,
`/api/close`, `/api/validate`, `/api/save`, `/api/save-batch`,
`/api/pending`, `/api/recovery-discard`, `/api/delete`,
`/api/synonym-check`, `/api/rename-check`, `/api/rename`,
`/api/backup-directory`, `/api/storage-check`, `/api/restore`, `/api/quit`.

## 8. Validierungs- und Schutzregeln

- Genau ein `skos:prefLabel` und genau eine `skos:notation` (Datentyp
  `^^fpv:entityType`) pro bearbeitbarem Block; mehr davon → geschützt.
- Geschützt (nur lesbar, Quelltext wird angezeigt, Löschen bleibt möglich)
  sind außerdem Blöcke mit unbekanntem Prädikat, `#`-Kommentar im Block oder
  dreifach zitiertem Literal.
- `skos:related`: nur `ex:ID`-Objekte, kommagetrennt; Verweis auf fehlende
  ID ist ein Hinweis, kein Fehler; zählt beim Löschschutz.
- Doppelte IDs werden per Rohtext-Scan gefunden (ein RDFLib-Graph kann das
  nicht, weil er Tripel zusammenführt).
- UTF-8 mit BOM wird bewusst abgewiesen.

## 9. Stand der Prüfung

- **Automatisch:** 102 Tests grün, `node --check static/app.js` ohne Fehler
  (Stand 24.11.2026, Linux).
- **Browserläufe:** mit Playwright/Chromium unter **Linux**, mit einem
  Ersatz für den Tk-Dialog. Geprüft: ein Dialog trotz Mehrfachklick,
  Escape schließt den Wartehinweis nicht, Laden, Abbrechen, Anzeige „beendet“.
- **Auf Windows bestätigt (laut Nutzer, Stand vor dem 20.11.):** Start und
  Speichern funktionieren.
- **Auf Windows NICHT geprüft:**
  - ob der Dateidialog jetzt wirklich vor einem Vollbild-Browser erscheint;
  - ob „Fenster nach vorne holen“ funktioniert (Win32-Aufrufe; Fehler werden
    in `startup.log` protokolliert);
  - die neue Rückfrage im Startfenster ohne Vormerkungen;
  - Tk-Beendendialog mit Vormerkungen, Schreibrechte auf `%LOCALAPPDATA%`,
    Verhalten nach echtem Absturz;
  - `start_mit_python.bat`;
  - Verhalten in Edge/Firefox (nur Chromium unter Linux getestet).

## 10. Offene Punkte und Ideen

1. **Windows-Prüfung** der Punkte aus Abschnitt 9 durch den Nutzer.
2. **Einheitliches Rückmeldungskonzept** (offen seit der GUI-Phase): Heute
   gibt es für fast alles Modal-Dialoge. Ob für Unwichtiges kurze,
   selbst verschwindende Meldungen besser wären, ist **nicht entschieden** –
   mit dem Nutzer klären.
3. Wunsch des Nutzers aus der GUI-Phase: Für Anwender ist das Eintippen von
   Pfaden ungeeignet; Öffnen läuft nur noch über „Datei öffnen …“.
4. Datenbefunde in `fpv.ttl` (nicht Aufgabe des Editors, nur zur Kenntnis):
   `ex:WaffenSS` hat `skos:closeMatch` mit `hhttps://…`; `ex:IDA` hat
   `skos:altLabelLabel`; 23 Synonymkollisionen (`kollisionen-synonymliste.md`).
5. Offene Fachfragen: bidirektionales `skos:related`, Groß-/Kleinschreibung
   bei Typesense, Kontakttext für geschützte Blöcke.
6. Die Live-Synonymprüfung im Formular prüft nur gegen den gespeicherten
   Stand; Kollisionen zwischen zwei vorgemerkten Einträgen meldet erst das
   Speichern.
7. Ursache des früheren Nextcloud-Fehlers (`index.html` FileNotFoundError)
   und des ursprünglichen Windows-`PermissionError` sind nie bewiesen.
8. Verhalten bei deutlich größeren Vokabularen (1000+ Konzepte) ungetestet.
9. `Readme-fuer-fpv.md` aus dem Originalprojekt wurde nie bereitgestellt;
   etwaige Regeln daraus sind nicht berücksichtigt.

## 11. Bekannte Ungenauigkeiten in `README.md`

Die README ist über mehrere Phasen gewachsen. Einige Abschnitte stammen
aus früheren Ständen und sind **veraltet** – bei Widerspruch gilt dieses
Dokument:
- Abschnitt „Tests“ nennt noch 24 Tests (aktuell 102) und beschreibt nur die
  ursprünglichen.
- Abschnitt „Weiterhin ungeprüft oder offen“ sagt, ein Speichervorgang auf
  Windows sei nicht nachgewiesen; laut Nutzer funktioniert Speichern
  inzwischen.
- „Sicherungsort wählen“ ist heute kein eigener Knopf in der Kopfzeile mehr;
  `app.js` ruft `/api/backup-directory` und `/api/storage-check` aber
  weiterhin auf (im Sicherungs-Ablauf). Die README beschreibt die frühere
  Platzierung.

Eine Bereinigung der README wäre eine sinnvolle, risikoarme erste Aufgabe –
vorher mit dem Nutzer abstimmen.

## 12. Verlauf in Kürze

- **Ursprung:** erste Fassung mit einem anderen KI-Werkzeug; konnte nicht
  speichern, Browser öffnete nicht.
- **Neuaufbau (Sept. 2026):** Flask/RDFLib/Tk/PyInstaller, sichere
  Schreibkette, Schutz verlustgefährdeter Blöcke, `skos:related`,
  Sprachkennzeichen je altLabel.
- **GUI-Phase / Phase 2:** Kontrast, anklickbare Befunde, Rohtextanzeige,
  Datei schließen, Verteilungsprüfung (`bundle_check.py`, `make_release.py`).
- **Phase 3 (14.10.2026):** Sammel-Speichern, ein Sicherungsort,
  Beenden-Schutz, Zwischensicherung, Hilfe, Kennung ändern.
- **20.11.2026:** Datei öffnen ohne Mehrfachdialoge und mit Hinweis,
  Rückfrage beim Beenden auch ohne Vormerkungen, Anzeige „beendet“ im
  Browser, Endpunkte `/api/choose-result` und `/api/ping`, 7 neue Tests.
  Wichtig: Ein Zwischenstand vom selben Tag beruhte versehentlich auf der
  älteren GUI-Phase-Fassung und ist **verworfen**; maßgeblich ist allein
  dieses Paket.

## 13. Empfohlener Einstieg für den Agenten

1. `AGENTS.md` und dieses Dokument lesen.
2. Umgebung wie in Abschnitt 3 einrichten, Tests laufen lassen (102 passed).
3. Den Nutzer fragen, was als Nächstes ansteht, und welche der
   Windows-Prüfungen aus Abschnitt 9 bereits erfolgt sind.
4. Bei Oberflächenarbeit: vor Änderungen Screenshots oder Beschreibung des
   Nutzers einholen und Varianten abstimmen.
5. Nach jeder Änderung: Tests, `node --check`, kurze Liste der geänderten
   Dateien und ehrliche Angabe, was geprüft wurde und was nicht.
