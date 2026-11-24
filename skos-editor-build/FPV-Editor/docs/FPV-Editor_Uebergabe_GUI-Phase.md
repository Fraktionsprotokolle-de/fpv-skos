# FPV-Editor – Übergabe für die GUI-/Design-Phase

Stand: 25.09.2026 · Nachfolger von `FPV-Editor_Projektuebergabe.md` (der
ursprünglichen Übergabe zum Neuaufbau). Dieses Dokument beschreibt den
**jetzigen** Zustand der App, damit in einem frischen Chat direkt an
Oberfläche, Design und Rückmeldungen weitergearbeitet werden kann.

## 1. Worum es geht

Lokale Windows-App zum Bearbeiten der SKOS-/Turtle-Datei `fpv.ttl`
(kontrolliertes Vokabular der Edition *Fraktionen im Deutschen Bundestag
1949–2005*, fraktionsprotokolle.de). Flask + RDFLib im Hintergrund, statisches
HTML/CSS/Vanilla-JS im Browser, Tk-Startfenster (`launcher.py`), Auslieferung
als PyInstaller-`--onedir`-Build. Rein lokal: Bindung nur an `127.0.0.1`,
zufälliger Port, keine Internetanbindung, keine externen Dienste/CDNs.

Nutzer: Sven, Historiker am KGParl, Digital Humanities (TEI-XML, SKOS/RDF,
Python). Arbeitssprache Deutsch.

## 2. Stand in einem Satz

Kernlogik, API und Speichern sind **getestet (24 automatisierte Tests, alle
grün)**; laut Nutzer laufen **Start und Speichern auf seinem Windows-Rechner**.
Offen ist jetzt vor allem die **Qualität der Oberfläche und der
Rückmeldungen** – das ist das Thema der nächsten Phase.

## 3. Was in dieser Phase im Fokus stehen soll

Ausdrücklicher Wunsch: **Design, GUI, Rückmeldungen.** Konkret bekannt:

1. **„Datei prüfen" gibt keine sichtbare Rückmeldung.** Belegt im Code:
   `validateWholeFile()` in `static/app.js` ruft `/api/validate` auf und
   rendert danach nur still Baum und rechtes Panel neu – kein Dialog, keine
   Meldung, kein Ladezustand. Man sieht nicht, ob geprüft wurde, ob die Datei
   in Ordnung ist oder ob nichts passiert ist. Beide Buttons („Datei prüfen"
   in der Kopfzeile, „Gesamte Datei prüfen" rechts) rufen dieselbe Funktion.
2. **Weitere Aktionen ohne Rückmeldung** (aus dem Code ersichtlich, nicht
   visuell getestet): „Öffnen" bei leerem Pfadfeld kehrt stillschweigend
   zurück (`openFromPathField`); ein erfolgreiches Öffnen zeigt nur den
   neuen Zustand, keine Bestätigung; „Suche zurücksetzen" und
   „Alle öffnen/schließen" sind rein visuell. Speichern, Löschen,
   Schreibzugriff prüfen, Sicherungen, Arbeitskopie, Datei schließen nutzen
   dagegen Dialoge (`showModal`).
3. Allgemein: Es gibt **kein einheitliches Rückmeldungskonzept** (Dialoge nur
   für manche Aktionen, sonst nichts; zwischendurch ein `alert()` bzw.
   `confirm()` des Browsers). Naheliegend wären z. B. ein konsistenter
   Statusbereich/Toast plus Dialoge nur für Wichtiges – das ist ein
   **Vorschlag, keine Entscheidung**; Gestaltung bitte mit dem Nutzer klären.
4. Unbestätigt: Ob die zuletzt geänderte Darstellung im Browser wirklich gut
   aussieht (lesbare Kopfzeilen-Buttons nach dem Kontrast-Fix, schmales
   Sprachfeld je altLabel-Zeile, Sprung-Scrollen beim Klick auf einen
   Befund, Rohtext-Block bei geschützten Einträgen). Der Nutzer antwortete
   „Sehr gut", hat aber keine einzelnen Punkte visuell bestätigt.
   **Von der Sandbox aus ist die Darstellung nicht sichtbar** – Layout- und
   Designurteile brauchen Rückmeldung bzw. Screenshots des Nutzers.

## 4. Dateien

| Datei | Rolle |
|---|---|
| `static/index.html` | Gesamte Oberfläche inkl. eingebettetem CSS (drei Spalten, Kopfzeile, Pfadzeile, Modal-Overlay). **Hauptdatei für Designarbeit.** |
| `static/app.js` | Gesamte Frontend-Logik: Baum, Suche/Filter, Formular, Modals, alle API-Aufrufe. **Hauptdatei für Rückmeldungen.** |
| `app.py` | Flask-App (`create_app()`), alle `/api/…`-Routen, Prozesszustand `STATE`, Server-Erzeugung |
| `fpv_core.py` | TTL-Blockparser, Validierung, quellenerhaltendes Schreiben, Sicherungskaskade, atomares Schreiben |
| `launcher.py` | EXE-Einstieg: Tk-Startfenster, Browserstart mit Fallbacks, `startup.log`, Fehlerdialoge |
| `tests/test_editor.py` | 24 Integrationstests (Flask-Testclient) |
| `build_windows.bat` | Offline-Build der EXE aus `wheels/`, mit Erfolgsnachweis |
| `diagnose_windows.bat` | Zweiter Build **mit** Konsole zur Fehlersuche |
| `start_mit_python.bat` | Start ohne EXE-Build aus `.venv` (auf Windows **nicht** ausgeführt) |
| `requirements.txt` | `Flask>=3.1,<4`, `rdflib>=7.1,<8` |
| `README.md` | Ausführliche technische Doku |
| `wheels/` | Offline-Wheels Windows/Python 3.14 (**im Übergabe-ZIP nicht enthalten**, siehe §10) |

Für reine GUI-Arbeit genügen normalerweise **`static/index.html` und
`static/app.js`**; `app.py`/`fpv_core.py` nur, wenn neue Daten vom Server
gebraucht werden (z. B. ein Prüfergebnis mit Zählwerten).

## 5. Bedienoberfläche (Ist-Zustand)

Drei Spalten (Raster 290px / flexibel / 290px, 12px Abstand, max. ca.
1650px; Umbrüche bei 1130px und 690px).

- **Kopfzeile** (dunkelgrün): „Datei prüfen", „Sicherungen", „Sicherungsort
  wählen", „Arbeitskopie anlegen", „Datei schließen", „＋ Neuer Eintrag",
  „App beenden".
- **Pfadzeile**: Pfadfeld, „Durchsuchen …" (nativer Tk-Dateidialog),
  „Öffnen", Konzeptzähler.
- **Links – Konzeptverzeichnis**: A–Z / ÄÖÜ / #-Gruppen (einklappbar) nach
  Vorzugsbenennung; Suche (ID, Label, altLabel, Links, related), Typfilter,
  „Suche zurücksetzen", „Alle öffnen/schließen", Zähler.
- **Mitte – Formular**: ID (bei bestehenden read-only), Typ, Sprache,
  prefLabel, altLabels (je Zeile mit eigenem Sprachfeld), exactMatch,
  closeMatch, skos:related (IDs ohne `ex:`), Synonymlisten-Checkbox, note.
  „Eintrag löschen …" / „Änderungen speichern". Warnung bei ungespeicherten
  Änderungen. Geschützte Blöcke: Formular ausgeblendet, stattdessen Grund,
  Zeilennummer und **Quelltext** (nur lesbar); Löschen bleibt möglich.
- **Rechts – Prüfung**: Ampel (Punkt + „N Fehler, M Hinweise"), Befundliste
  (**anklickbar** → springt zum Eintrag), „Gesamte Datei prüfen",
  „Schreibzugriff prüfen", Erklärtext.
- **Modal-Overlay** für Speichern/Löschen/Speicherprüfung/Sicherungen/
  Wiederherstellen (`showModal(title, body, kind)`, `kind` = `info`/`ok`/
  `progress`/…; Body wird per `textContent` gesetzt, also **kein HTML**).

**Design-Vorgaben aus der Ursprungsübergabe:** Farben `#f3f6f3` (Grund),
`#1d302e` (Text), `#145d4d` (Primär), `#163b31` (Kopfzeile), `#a43834`
(Fehler); Segoe UI für Bedienelemente, Georgia für Überschriften,
Monospace für IDs. In `index.html` zusätzlich `--warn:#8a6d1a`,
`--ok:#1f7a4d`. Änderungen an der Gestaltung sind ausdrücklich erwünscht –
dies ist der Ausgangspunkt, keine Festlegung.

## 6. Datenmodell und API (für Frontend-Arbeit)

Alle POST-Endpunkte verlangen den Header `X-FPV-Token` (Token wird beim
Laden von `/` in `window.FPV_TOKEN` eingebettet; in `apiPost`/`apiGet`
bereits erledigt).

Endpunkte: `GET /`, `GET /api/state`, `GET /api/backups`, `POST /api/open`,
`/api/choose`, `/api/close`, `/api/validate`, `/api/save`, `/api/delete`,
`/api/backup-directory`, `/api/storage-check`, `/api/working-copy`,
`/api/restore`, `/api/quit`.

**Zustandsobjekt** (Antwort von open/validate/save/…):
`{ path, sha256, uses_crlf, records: [...], findings: [...] }`

**Record (bearbeitbar):** `{ id, pref, lang, type, note, synonym, alts:
[{text, lang}], exact: [url], close: [url], related: [id], protected:
false, line }`

**Record (geschützt):** `{ id, protected: true, protect_reason, raw, line }`

**Finding:** `{ level: "error"|"warning", message, concept_id|null }` –
Befunde ohne `concept_id` betreffen die ganze Datei (z. B. Turtle-Syntax).

**Fehlerantwort:** HTTP-Fehlercode mit `{ error, error_type }`, teils
zusätzlich `findings`. Fehlerbehandlung im Frontend zentral in
`handleApiError`.

Achtung bei Änderungen: `alts` ist seit dieser Phase eine Liste von
`{text, lang}` (früher reine Strings; der Server akzeptiert Strings weiter).

## 7. Validierung – was die Oberfläche wissen muss

- **Speichern blockiert nur**, wenn (a) die resultierende Datei kein gültiges
  Turtle wäre oder (b) ein Fehler den **gerade bearbeiteten** Datensatz
  betrifft. Fehler in **anderen** Datensätzen blockieren nicht (früher
  Deadlock, weil immer nur ein Datensatz editierbar ist). Nach dem Speichern
  weist der Erfolgsdialog auf verbleibende fremde Fehler hin.
- **Nur ein Vorzugslabel**: Der Editor verlangt genau ein `skos:prefLabel`
  (strenger als `validate_fpv.py`: „höchstens eines"). Blöcke mit mehr als
  einem prefLabel oder mehr als einer notation sind geschützt.
- **skos:related**: nur `ex:ID`-Objekte, kommagetrennt; Verweis auf fehlende
  ID = Hinweis (kein Blocker); zählt beim Löschschutz mit.
- Notation-Datentyp `^^fpv:entityType` wird bei „Datei prüfen" kontrolliert.
- Geschützt sind außerdem Blöcke mit unbekanntem Prädikat, `#`-Kommentar im
  Block oder dreifach zitiertem Literal.
- Reihenfolge beim Schreiben (fest): SHA-256-Versionsprüfung → Validierung →
  **verifizierte Sicherung der alten Bytes** → erst dann TTL ändern; ohne
  funktionierenden Sicherungsort bleibt die TTL unangetastet.

## 8. Arbeitsregeln des Nutzers (bitte einhalten)

- **Nachfragen, wenn etwas unklar ist.** Präzise antworten, auf reale Quellen
  stützen, **nichts erfinden**; Unwissen offen sagen.
- **Keine Erfolgsbehauptung ohne Beleg.** Was nicht ausgeführt/gesehen werden
  konnte (Windows, Browserdarstellung), ausdrücklich als ungeprüft benennen.
- **Für Korrekturen nur die geänderten Einzeldateien liefern**, keinen
  kompletten ZIP. Für `.js`-Dateien ggf. `app.js.txt` mit Umbenennungshinweis,
  falls der Browser den Download blockiert.
- `.bat`-Dateien **immer mit CRLF-Zeilenenden, ohne BOM** (sonst verschluckt
  `cmd.exe` Zeichen – bereits einmal passiert).
- Vor jeder Lieferung: `python -m pytest tests/test_editor.py -q` und
  `node --check static/app.js`.
- Fehlerbeschreibungen des Nutzers sind meist echte Befunde (`startup.log`,
  Tracebacks) – erst am Code belegen, dann ändern.

## 9. Bekannte Grenzen und offene Punkte

- **Nicht auf echtem Windows geprüft:** `start_mit_python.bat`.
- **Nicht visuell geprüft:** alle jüngsten GUI-Änderungen (siehe §3, Punkt 4).
- Ursache des ursprünglichen Windows-`PermissionError` bei Sicherungen nie
  diagnostiziert; Speichern funktioniert laut Nutzer inzwischen, die
  Ursache bleibt unbekannt.
- `Readme-fuer-fpv.md` aus dem Originalprojekt wurde **nie hochgeladen**;
  zusätzliche Regeln daraus sind nicht berücksichtigt.
- Verhalten bei sehr großen Vokabularen (~1000+ Concepts) ungetestet.
- Nicht übernommen aus `validate_fpv.py`: Warnung zu Nicht-ASCII-Zeichen in
  Match-URIs (nur Warnung im Original).
- `check_duplicate-id.py` (Originalprojekt) kann Doppeldeklarationen
  prinzipiell nicht finden (RDFLib-Graph ist eine Tripelmenge); der Editor
  scannt deshalb den Rohtext. Beleg per Test erbracht, Script nicht geändert.
- Windows Defender meldete beim ZIP `Trojan:Win32/MalUri.A!cl` – laut
  Analyse Fehlalarm wegen der PyInstaller-Bootloader in den Wheels
  (SHA256 des PyInstaller-Wheels stimmt mit PyPI überein); der Nutzer hält
  es ebenfalls für einen Fehlalarm.

## 10. So geht es im neuen Chat weiter

1. `FPV-Editor_Uebergabe_GUI-Phase.md` (dieses Dokument) und
   `FPV-Editor-Quellen.zip` in den neuen Chat hochladen. Das ZIP enthält den
   kompletten Code **ohne** `wheels/` (unverändert, beim Nutzer vorhanden,
   und ohne die Wheels entfällt die Defender-Meldung). Für Änderungen an
   `static/` und Tests werden die Wheels nicht gebraucht.
2. Zum Testen in der Sandbox genügt `pip install flask rdflib pytest`; die
   Tests laufen ohne Windows.
3. Zuerst den bekannten Rückmeldungsmangel beheben („Datei prüfen"), dabei
   **mit dem Nutzer vorher klären**, wie die Rückmeldung aussehen soll
   (Dialog? Statuszeile? Banner im rechten Panel?), statt selbst zu
   entscheiden.
4. Danach systematisch alle Aktionen durchgehen: Was sieht der Nutzer
   unmittelbar nach dem Klick, bei Erfolg, bei Fehler, bei „nichts zu tun"?
5. Design: Vorschläge als Screenshots/HTML-Varianten des Nutzers
   abstimmen; die Sandbox kann die Darstellung nicht selbst beurteilen.
6. Ausgeliefert werden nur die geänderten Einzeldateien (meist
   `static/index.html`, `static/app.js`, ggf. `tests/test_editor.py`).
