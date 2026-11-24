# FPV-Editor

Lokaler Editor für die kontrollierte Vokabular-Datei `fpv.ttl` der Edition
*Fraktionen im Deutschen Bundestag 1949–2005*. Neuaufbau auf Basis der
Projektübergabe `FPV-Editor_Projektuebergabe.md`, nachdem die ursprüngliche
(mit ChatGPT erstellte) Version zwei bekannte Defekte hatte:

1. Sie konnte keine TTL-Datei ins Dateisystem zurückschreiben
   (PermissionError beim Anlegen der Sicherung).
2. Der Browser öffnete sich beim Start nie automatisch.

Dieser Neuaufbau adressiert beide Punkte (siehe Abschnitt „Bekannte
Einschränkungen“ für das, was davon *tatsächlich getestet* werden konnte und
was nicht).

## Was die App tut

- Rein lokale Anwendung: ein Flask-Server bindet ausschließlich an
  `127.0.0.1` auf einem zufälligen freien Port, keine Internet-/Cloud-Anbindung.
- Öffnet eine statische HTML/CSS/JS-Oberfläche im Standardbrowser zur
  Bearbeitung einzelner SKOS-Concept-Blöcke in `fpv.ttl`.
- Bearbeitung erfolgt **textbasiert am einzelnen Block**, nicht durch
  Neuserialisierung der gesamten Datei — Kommentare, Formatierung und
  Blöcke außerhalb der bearbeiteten ID bleiben unverändert erhalten.
- Blöcke mit unbekannten Prädikaten, eigenen Kommentaren, dreifach
  zitierten Literalen oder mehr als einem `skos:prefLabel` bzw.
  `skos:notation` werden als **geschützt/nur lesbar** angezeigt statt
  (möglicherweise verlustreich) bearbeitbar gemacht. Ihr Quelltext wird
  dabei unverändert eingeblendet, damit erkennbar bleibt, was das Problem
  verursacht. Welche Prädikate unterstützt werden, steht unten unter
  „Unterstützte Prädikate".
- Vor jedem Schreibvorgang: Versionsprüfung (SHA-256) → Validierung der
  resultierenden Gesamtdatei → verifizierte Sicherung der *alten* Bytes
  (schreiben + flush + fsync + Rücklesen + Vergleich) → erst danach die
  eigentliche Änderung. Wenn an keinem der möglichen Sicherungsorte eine
  Sicherung gelingt, wird die TTL-Datei **nicht angefasst**.

## Schnellstart für die Entwicklung (ohne Build)

Voraussetzung: Python 3.14 (64-Bit) unter Windows, oder eine beliebige
Python-3.x-Umgebung zum bloßen Testen der Serverlogik (Linux/macOS
funktioniert für `app.py`/`fpv_core.py`, aber `launcher.py` benötigt
`tkinter` und ist windowsspezifisch, siehe unten).

```bat
py -3.14-64 -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python launcher.py
```

Für einen schnellen Start ohne Neubau der EXE gibt es `start_mit_python.bat`
— es prüft, ob `.venv` existiert, und startet `launcher.py` direkt darüber.
Das Konsolenfenster bleibt offen und zeigt Ausgaben/Fehler unmittelbar an.

Alternativ headless zum reinen API-Test (ohne Tk-Startfenster):

```bat
.venv\Scripts\python app.py
```

Die Tests laufen mit:

```bat
.venv\Scripts\python -m pytest tests\test_editor.py -v
```

## Windows-Build (Auslieferung als EXE)

`build_windows.bat` baut die App **offline** aus den mitgelieferten Wheels
im Ordner `wheels/` (kein Internetzugriff beim Build nötig):

1. Sucht Python 3.14 (64-Bit) über `py -3.14-64`, dann `py -3.14`, dann
   `python` als Fallback.
2. Legt `.venv` an, falls noch nicht vorhanden.
3. Installiert `requirements.txt` sowie `pyinstaller`, `pefile` und
   `pywin32-ctypes` ausschließlich aus `wheels/` (`--no-index
   --find-links=wheels`).
4. Entfernt alte Build-Artefakte (`build\`, `dist\FPV-Editor`, altes
   `.spec`) und **prüft nach, ob das Löschen wirklich geklappt hat** —
   bricht sonst mit klarer Meldung ab (ein gesperrter Rest-Ordner konnte
   zuvor zu einem unvollständigen Bundle führen).
5. Ruft PyInstaller mit
   `--onedir --noconsole --name FPV-Editor --add-data "static;static"
   --collect-submodules rdflib.plugins launcher.py` auf.
6. **Weist nach dem Build nach**, dass `FPV-Editor.exe` und
   `_internal\static\index.html` im Ergebnis tatsächlich vorhanden sind.
   Erst dann meldet das Skript „Build erfolgreich UND geprüft". Ein
   Exitcode 0 von PyInstaller allein genügt als Erfolgsnachweis nicht —
   genau dadurch blieb zuvor eine fehlende `index.html` unentdeckt, bis
   die EXE zur Laufzeit „Internal Server Error" zeigte.

**Wichtig:** Ausgeliefert wird immer der **gesamte Ordner**
`dist\FPV-Editor\`, nicht nur `FPV-Editor.exe` allein — PyInstaller legt im
`--onedir`-Modus alle Abhängigkeiten (Python-Laufzeit, DLLs, `static/`) in
einen Unterordner `_internal\` neben die EXE.

**Vor dem Bauen** alle noch laufenden `FPV-Editor`-Fenster schließen,
sonst kann das Aufräumen an gesperrten Dateien scheitern. Falls ein
Virenscanner den Build stört (Symptom: `OSError: [Errno 22] Invalid
argument` beim Kopieren einer Datei), hilft es, den Projektordner in den
Ausschlüssen von Windows Defender einzutragen.

Wenn der normale (`--noconsole`) Build startet, aber nichts sichtbar
passiert oder er sofort wieder verschwindet, liefert `diagnose_windows.bat`
eine zweite Build-Variante **mit** Konsolenfenster
(`dist\FPV-Editor-Diagnose\FPV-Editor-Diagnose.exe`), die sofort nach dem
Bauen gestartet wird, sodass Tracebacks und Log-Zeilen direkt sichtbar sind.
Dieser Diagnose-Build ist komplett getrennt vom normalen Build und
überschreibt ihn nicht.

Beide Build-Skripte setzen voraus, dass `wheels/` vorhanden ist; sie
installieren nichts aus dem Internet.

### Verteilung als ZIP und Prüfung beim Start

Schritt 7 von `build_windows.bat` (und gleichlautend in `diagnose_windows.bat`)
ruft `make_release.py` auf. Ergebnis: `dist\FPV-Editor.zip`.

- Der gebaute Ordner erhält `manifest.sha256.json` (Größe und SHA-256 jeder
  Datei, ohne `startup.log`) und `LIES-MICH.txt`.
- Das ZIP enthält den **Ordnerinhalt ohne zusätzlichen obersten Ordner**; der
  Zielordner wird beim Entpacken gewählt (Empfehlung in `LIES-MICH.txt`:
  `C:\Users\<Name>\FPV-Editor`, kein Synchronisationsordner, keine
  Administratorrechte nötig).
- Das ZIP wird nach dem Bauen wieder eingelesen und Datei für Datei gegen das
  Manifest verglichen; nur dann meldet der Build Erfolg.
- Beim Start der gebauten EXE vergleicht `launcher.py` den Ordner mit dem
  Manifest, **bevor** `app.py` importiert wird. Bei Abweichungen erscheint
  „Programm unvollständig" mit der Liste der betroffenen Dateien
  (höchstens 12 im Dialog, alle in `startup.log`), und das Programm endet.
  Dateien, die Windows als Cloud-Platzhalter kennzeichnet
  (`FILE_ATTRIBUTE_OFFLINE`, `…RECALL_ON_OPEN`, `…RECALL_ON_DATA_ACCESS`),
  werden gemeldet und nicht gelesen. Ein fehlendes oder unlesbares Manifest
  stoppt den Start nicht (nur Logeintrag; die Prüfung von `index.html` und
  `app.js` bleibt bestehen), ebenso wenig ein Fehler in der Prüfung selbst.
- Liegt der Ordner in einem erkennbaren Sync-Ordner (Nextcloud, ownCloud,
  OneDrive, Dropbox, Google Drive, iCloud, pCloud, MEGA), auf einem UNC-Pfad
  oder im Entpackordner der ZIP-Vorschau, erscheint ein Hinweis im Startfenster
  und im Log; das ist eine Warnung, kein Startverbot.
- `startup.log` liegt neben der EXE; ist dieser Ordner nicht beschreibbar,
  weicht das Log nach `%LOCALAPPDATA%\FPV-Editor\startup.log` aus.

**Nicht auf Windows geprüft** (nur die Logik per Tests unter Linux): Dauer der
Startprüfung bei vollem Bundle, Verhalten mit echten Cloud-Platzhaltern,
Anzeige der Hinweiszeile im Tk-Fenster, „Zulassen"-Haken und SmartScreen-
Ablauf aus `LIES-MICH.txt`, Entpacken mit „Alle extrahieren".

## Rollen der Dateien

| Datei | Rolle |
|---|---|
| `app.py` | Flask-App-Factory (`create_app()`), alle `/api/...`-Routen, Prozesszustand (`AppState`/`STATE`), Server-Erzeugung/-Start |
| `fpv_core.py` | TTL-Parsing auf Blockebene, Validierung, quellenerhaltende Bearbeitung, Sicherungskaskade, atomares Schreiben mit Fallback |
| `launcher.py` | EXE-Einstiegspunkt: Tk-Startfenster mit URL-Feld, Datei-Öffnen-Dialog (Hauptthread-sicher über eine Queue-Bridge), robuster Browser-Start mit mehreren Fallback-Strategien, `startup.log`, native Windows-Fehlerdialoge bei Absturz |
| `bundle_check.py` | Manifest schreiben/laden, Programmordner gegen das Manifest prüfen (fehlend, falsche Größe, abweichende Prüfsumme, Cloud-Platzhalter), Standortwarnungen (Sync-Ordner, Netzpfad, ZIP-Vorschau) |
| `make_release.py` | Letzter Build-Schritt: Manifest + `LIES-MICH.txt` in den Ordner, ZIP bauen, ZIP gegen das Manifest nachprüfen |
| `LIES-MICH.txt` | Installationsanleitung für die Nutzer*innen (wird in den Programmordner/ZIP kopiert) |
| `static/index.html` | Drei-Spalten-Oberfläche (Baum / Formular / Validierung) inkl. eingebettetem CSS |
| `static/app.js` | Gesamte Frontend-Logik: Baum, Suche/Filter, Formular, Modals, alle API-Aufrufe |
| `requirements.txt` | `Flask>=3.1,<4`, `rdflib>=7.1,<8` |
| `build_windows.bat` | Offline-Build der EXE aus `wheels/` |
| `diagnose_windows.bat` | Zusätzlicher Build **mit** Konsole zur Fehlersuche, startet die EXE sofort |
| `start_mit_python.bat` | Startet `launcher.py` direkt über die vorhandene `.venv`, ohne Neubau |
| `tests/test_editor.py` | Integrationstests (Stand Phase 3: 102) |
| `wheels/` | Offline-Wheels für Windows/Python 3.14 (u. a. `pefile`, `pywin32-ctypes` für PyInstaller) |

## Sicherung (ein Ort, seit Phase 3)

Vor jedem Schreibvorgang wird die *alte* Datei **einmal** an **einem** Ort
gesichert und geprüft (Schreiben, `fsync`, Zurücklesen, Bytevergleich):

- standardmäßig `%LOCALAPPDATA%\FPV-Editor\backups\<Dateischlüssel>`
  (ohne Administratorrechte beschreibbar, außerhalb eines Git-Arbeitsordners;
  ohne `LOCALAPPDATA`: `~\.fpv-editor\backups\<Dateischlüssel>`),
- oder, wenn über „Sicherungsort wählen“ gesetzt, dem gewählten Ordner
  (nur für die laufende Sitzung).

Die frühere zehnstufige Ausweichkaskade ist **entfernt** (Entscheidung des
Nutzers, da die `fpv.ttl` in Git liegt). Folge: Scheitert dieser eine Ort,
bleibt die TTL unverändert, der Server antwortet mit HTTP 507, und die Meldung
nennt Ort und Grund; als Ausweg dient „Sicherungsort wählen“. Beim Auflisten
(„Frühere Stände wiederherstellen“) werden weiterhin **alle** früheren Orte
durchsucht, damit ältere Sicherungen auffindbar bleiben
(`backup_candidate_locations`). Der `<Dateischlüssel>` ist ein Hash des
TTL-Pfads; Dateinamen enthalten Zeitstempel und einen zufälligen Hex-Suffix.

**Nicht auf Windows geprüft:** ob `%LOCALAPPDATA%` auf allen Kollegenrechnern
beschreibbar ist (Gruppenrichtlinien, umgeleitete Profile).

## Sammel-Speichern (seit Phase 3)

Die Oberfläche merkt Änderungen mehrerer Einträge vor (Wechsel zu einem
anderen Eintrag übernimmt das Formular in `App.drafts`; ●-Markierung im Baum,
Liste „Noch nicht gespeichert“ in der Eintragsleiste). „Alle Änderungen
speichern“ sendet alles an `POST /api/save-batch`
(`{version, items: [{original_id, data}, …]}`):

- eine Versionsprüfung (SHA-256), alle Einträge nacheinander in den Text
  eingesetzt, Feldprüfung je Eintrag, dann **eine** Gesamtprüfung,
  **eine** Synonymprüfung über alle geänderten Konzepte gemeinsam
  (`synonym_conflicts_for_batch`; Kollisionen der Einträge untereinander
  zählen als neu), **eine** Sicherung, **ein** Schreibvorgang.
- Alles oder nichts: Scheitert ein Eintrag, wird nichts geschrieben; die
  Antwort enthält `failed_id` und `findings`.
- Blockierend sind Fehler, die die ganze Datei betreffen, oder Fehler in einem
  der gerade gespeicherten Einträge (wie bisher beim Einzelspeichern).
- „Kennung ändern“ und „Eintrag löschen“ sind gesperrt, solange andere
  Einträge vorgemerkt sind (Umbenennen ändert Verweise in anderen Einträgen;
  eine Vormerkung würde sie überschreiben).
- Die Live-Synonymprüfung im Formular prüft weiter nur gegen den gespeicherten
  Stand; Kollisionen zwischen zwei vorgemerkten Einträgen meldet erst das
  Speichern.
- `/api/save` bleibt als Einzelspeichern erhalten (die Oberfläche nutzt es
  nicht mehr).

## Beenden-Schutz und Zwischensicherung (seit Phase 3)

Nicht gespeicherte (vorgemerkte) Einträge gehen beim Beenden nicht mehr
stillschweigend verloren.

- **Abfrage beim Beenden.** „App beenden“ im Browser zeigt bei vorgemerkten
  Einträgen die Wahl *Speichern und beenden* / *Beenden ohne Speichern* /
  *Zurück zum Editor*. Dasselbe fragt das kleine Startfenster (Knopf und
  Fensterkreuz) per Tk-Dialog (`launcher.quit_gate`, Ja/Nein/Abbrechen);
  „Ja“ speichert über dieselbe Funktion wie der Browser (`save_batch`). Scheitert
  das Speichern, wird nicht beendet und nichts geschrieben. Ist **nichts**
  vorgemerkt, fragt das Startfenster trotzdem „wirklich beenden?“ (Ja/Nein,
  Standard Nein). Solange der Dateiauswahldialog offen ist, wird nicht beendet.
- **Anzeige „beendet“.** Die Oberfläche fragt alle 4 s `GET /api/ping` ab;
  bleibt die Antwort zweimal aus, legt sie eine nicht wegklickbare Meldung
  „Der FPV-Editor ist beendet“ über die Seite.
- **Meldung der Oberfläche an den Server.** Die Oberfläche schickt ihre
  vorgemerkten Einträge ca. 1,5 s nach jeder Änderung per `POST /api/pending`
  (`{items, version, persist}`) an den Server (nur im Speicher; deshalb kann
  das Startfenster fragen).
- **Zwischensicherung auf der Platte.** Alle 10 Minuten (Konstante
  `AUTOSAVE_INTERVAL_MS` in `static/app.js`) wird mit `persist=true` eine Datei
  `%LOCALAPPDATA%\FPV-Editor\recovery\<Dateischlüssel>.json` geschrieben (atomar,
  `fpv_core.write_recovery`). Sie enthält nur die vorgemerkten Formularstände,
  die TTL wird nie verändert. Gelöscht wird sie nach dem Speichern, beim
  bewussten Verwerfen und bei „Beenden ohne Speichern“.
- **Wiederherstellen.** Nach dem Öffnen der Datei fragt `GET /api/recovery`;
  gibt es eine Zwischensicherung, bietet ein Dialog *Wiederherstellen* /
  *Verwerfen* / *Später entscheiden* an. Wiederhergestellte Einträge sind
  wieder „vorgemerkt“, geschrieben wird erst durch „Alle Änderungen speichern“.
  `sha_matches=false` (Datei zwischenzeitlich geändert) wird im Dialog genannt.
- **Sicherheitsnetz.** `POST /api/quit` antwortet mit 409
  (`error_type: PendingChanges`), solange Einträge vorgemerkt sind, außer mit
  `force: true` (optional `discard: true` löscht die Zwischensicherung).
  `POST /api/recovery-discard` löscht sie ohne Beenden.

**Nicht auf Windows geprüft:** das Aussehen/Verhalten des Tk-Dialogs
(`askyesnocancel`), Schreibrechte auf `%LOCALAPPDATA%` und das Verhalten nach
einem echten Absturz oder Stromausfall. Höchstens die letzten 10 Minuten
Arbeit können bei einem Absturz fehlen.

## Schreibverhalten

- Normalfall: Schreiben in eine temporäre Datei im selben Verzeichnis,
  danach `os.replace()` (atomarer Austausch).
- Falls das auf dem konkreten Windows-System mit `PermissionError`
  fehlschlägt (das im Übergabedokument beschriebene, auf dem Originalrechner
  nicht diagnostizierte Verhalten): Fallback auf direktes Schreiben in die
  bestehende Datei (`r+b`, Trunkierung, `flush`, `fsync`). Dieser Fallback
  ist **nicht atomar** — bei einem Absturz mitten im Schreibvorgang kann die
  Datei in einem inkonsistenten Zustand zurückbleiben. Die Oberfläche weist
  nach einem solchen Fallback-Speichern explizit auf dieses Risiko hin.
- Der Fallback wird **nur** versucht, nachdem die Sicherung der alten Datei
  bereits erfolgreich verifiziert wurde.

## Validierung beim Speichern: was blockiert das Schreiben, was nicht

**Diese Regel wurde nach echtem Praxiseinsatz mit der realen `fpv.ttl`
geändert** und weicht damit von der ursprünglichen, wörtlichen Lesart der
Übergabe ab („neue Gesamtdatei syntaktisch und strukturell validieren" vor
jeder Änderung). Das Problem in der Praxis: Der Editor lässt immer nur
**einen** Datensatz gleichzeitig bearbeiten. Hätte *jeder* strukturelle
Fehler irgendwo in der Datei das Speichern blockiert, hätte ein Bestand mit
mehreren vorbestehenden Altfehlern (z. B. mehrere Einträge mit leerem
`skos:note`, ein Link mit Tippfehler wie `hhttps://…`) zu einem Deadlock
geführt: Man hätte nie irgendetwas speichern können, weil man die Altfehler
nur nacheinander über genau den Speichervorgang beheben kann, der dafür
blockiert wäre.

Seit diesem Patch blockiert ein Speichervorgang **nur noch**, wenn:

1. die resultierende Datei **syntaktisch ungültiges Turtle** wäre (darf nie
   passieren — das würde die Datei für jedes Werkzeug, nicht nur diesen
   Editor, kaputt machen), oder
2. der Fehler **genau den gerade bearbeiteten Datensatz** betrifft (den kann
   man im offenen Formular sofort korrigieren, bevor man erneut speichert).

Fehler in **anderen, nicht bearbeiteten** Datensätzen blockieren das
Speichern nicht mehr. Sie werden nach dem Speichern weiterhin ganz normal
im rechten Prüfungspanel (und im Erfolgs-Dialog, falls vorhanden) als
Befunde angezeigt — nur eben nicht mehr als Blockade für einen unabhängigen
Bearbeitungsvorgang. „Datei prüfen" (`/api/validate`) zeigt ohnehin immer
**alle** Befunde der ganzen Datei, unabhängig davon, was zuletzt bearbeitet
wurde — das ist unverändert.

`/api/delete` prüfte schon vorher nicht die gesamte Datei erneut (nur den
Referenzschutz), war von diesem Deadlock also nicht betroffen.

## API (lokal, token-geschützt)

Alle mutierenden Endpunkte verlangen den Header `X-FPV-Token`, dessen Wert
beim Laden von `GET /` einmalig in die Seite eingebettet wird.

`GET /api/state`, `GET /api/backups`, `GET /api/ping`, `POST /api/open`,
`POST /api/choose` (startet den Dateidialog und antwortet sofort mit
`opened` oder `already_open`; es gibt höchstens einen Dialog),
`POST /api/choose-result` (`open`/`cancelled`/`idle` oder geladener Zustand
mit `status: "loaded"`),
`POST /api/validate`, `POST /api/save`, `POST /api/delete`,
`POST /api/backup-directory`, `POST /api/storage-check`,
`POST /api/restore`, `POST /api/close`,
`POST /api/quit`.

**Kennung ändern** (`POST /api/rename-check`, `POST /api/rename`): Eine
bestehende ID ist im Formular und in `/api/save` gesperrt (`Eine bestehende ID
darf nicht geändert werden.`). Umbenannt wird nur über die eigene Aktion
„Kennung ändern …“. `rename-check` schreibt nichts und liefert die
verweisenden Konzepte, blockierende Verweise und ein Urteil über die neue ID.
`rename` zieht den Block und alle Verweise in *bearbeitbaren* Blöcken per
gezieltem Textersatz mit (Literale und ähnliche IDs wie `ex:OLDER` bleiben
unberührt), beweist danach per RDF-Isomorphie, dass sich nur die URI der ID
geändert hat, und schreibt mit derselben Schutzreihenfolge wie `/api/save`
(Version → Validierung → verifizierte Sicherung → Schreiben). Verweise aus
geschützten Blöcken führen zur Ablehnung (409); der Editor verändert
geschützte Blöcke nie. Verwendungen außerhalb der Datei (Editions-XML,
Typesense) kann der Editor nicht finden oder ändern.

**Synonymliste / Kollisionsprüfung** (`POST /api/synonym-check`, außerdem in
`/api/save` und `validate_whole_file`): Konzepte mit `ex:useInSynonymList
"true"^^xsd:boolean` gehen mit allen ihren Benennungen in die Typesense-
Synonymliste (Script `ttl2jsonl.py`). Steht dieselbe Benennung bei zwei solchen
Konzepten, würde die Suche beide finden. Der Abschnitt „Synonymliste" in
`fpv_core.py` **spiegelt die Regeln des Scripts** (Graph-basiert, auch geschützte
Blöcke; nur Konzepte mit Wert true; Benennungen aller Sprachen; Blacklist
`pol/com/soc/news/topic/law/org` und Länge ≤ 1 entfallen; ein Set entsteht erst
ab 2 verbleibenden Benennungen). Verglichen wird NFC, Leerraum zusammengefasst,
Groß-/Kleinschreibung ignoriert. **Neu entstehende** Kollisionen blockieren das
Speichern des bearbeiteten Konzepts (HTTP 400, Datei unverändert); **bereits
vorhandene** erscheinen nur als Hinweis (je Konzeptpaarung ein Befund mit
`concept_ids`), sonst ließe sich ein Konzept mit Altlast nicht mehr speichern.
Ändert sich `ttl2jsonl.py`, muss dieser Abschnitt (und
`_reference_ttl2jsonl_sets` in den Tests) mitgezogen werden.

Größenbegrenzungen: zu öffnende TTL-Dateien max. 15 MiB, Flask-Request-Body
max. 2 MiB.

Das JSON-Formularmodell umfasst `id`, `pref`, `lang`, `type`, `note`,
`synonym`, `alts`, `exact`, `close` und `related`. **`alts` hat sich
geändert:** Es ist jetzt eine Liste von Objekten `{"text": …, "lang": …}`
statt reiner Strings, damit jedes altLabel sein eigenes Sprachkennzeichen
behält (siehe „Unterstützte Prädikate" unten). Ein reiner String wird beim
Speichern weiterhin akzeptiert und mit der Sprache des Datensatzes ergänzt.
Geschützte Blöcke liefern zusätzlich `raw` (ihren unveränderten Quelltext)
und `line` (Zeilennummer des Blockanfangs) mit.

## Unterstützte Prädikate

Über das Formular bearbeitbar sind Blöcke, die ausschließlich diese
Prädikate verwenden: `skos:prefLabel` (genau eines), `skos:altLabel`
(beliebig oft, je mit eigenem Sprachkennzeichen), `skos:notation` (genau
eine, Datentyp `^^fpv:entityType`), `ex:useInSynonymList`,
`skos:exactMatch`, `skos:closeMatch`, `skos:note` und `skos:related`.

`skos:related` verweist auf andere Konzepte **derselben** Datei als
präfixierte Namen und darf kommagetrennt mehrfach auftreten:

```turtle
skos:related ex:MBFR , ex:SALT .
```

Im Formular werden diese Verweise als reine IDs ohne `ex:` eingetragen; das
Präfix ergänzt der Editor beim Schreiben. Zeigt ein Verweis auf eine ID, die
es in der Datei nicht gibt, ist das ein **Hinweis**, kein Fehler — es
blockiert das Speichern nicht. Ein `skos:related`, dessen Objekt keine
`ex:ID` ist (etwa eine vollständige URI), sperrt den Block hingegen, weil
das Formular es nicht verlustfrei zurückschreiben könnte. Umgekehrt zählt
`skos:related` als Verweis beim Löschschutz: Ein Konzept, auf das ein
anderes per `skos:related` zeigt, lässt sich nicht löschen.

## Tests

`tests/test_editor.py` enthält 24 Integrationstests, alle aktuell grün
(`python -m pytest tests/test_editor.py -v`):

Token-Pflicht für mutierende Endpunkte, Bearbeitung erhält den Rest der
Quelldatei, Blöcke mit unbekanntem Prädikat werden nicht angetastet,
Löschen eines unreferenzierten Konzepts, Ablehnung des Löschens eines
referenzierten Konzepts, erfolgreiches Neuanlegen, Ablehnung doppelter IDs,
Versionskonflikt bei veraltetem Speichern, Erhalt von CRLF-Zeilenenden,
Anlegen und Auflisten von Sicherungen, Fallback-Schreiben bei simuliertem
`PermissionError`, Wiederherstellung aus einer Sicherung, Schutz bei mehrfacher `skos:notation`,
Meldung falscher/fehlender Notation-Datentypen, **Speichern wird durch
einen Altfehler in einem fremden Datensatz nicht mehr blockiert**,
Speichern bleibt blockiert, wenn der Fehler den gerade bearbeiteten
Datensatz selbst betrifft, Speichern bleibt in jedem Fall blockiert, wenn
das Ergebnis syntaktisch ungültiges Turtle wäre (per Monkeypatch simuliert,
da über das normale Formular praktisch nicht erreichbar), `skos:related`
sperrt den Block nicht und überlebt einen Speichervorgang,
Sprachkennzeichen einzelner altLabels bleiben erhalten, ein ins Leere
zeigender `skos:related`-Verweis ist nur ein Hinweis und kein Blocker,
`skos:related` verhindert das Löschen des Ziels, geschützte Blöcke liefern
ihren Quelltext mit, Schließen einer Datei leert den Zustand.

Die Tests isolieren die Sicherungskaskade in ein temporäres Verzeichnis
(`monkeypatch` von `fpv_core.backup_candidate_locations`), sodass beim
Testen nie echte `%LOCALAPPDATA%`- oder `%TEMP%`-Ordner berührt werden.

## Bekannte Einschränkungen und offene Punkte

Der Stand hat sich durch echte Testläufe auf dem Zielrechner (Windows,
Python 3.14 x64, 25.09.2026) geändert. Was inzwischen tatsächlich auf
Windows lief und was weiterhin ungeprüft ist, steht getrennt unten.

### Im Praxiseinsatz gefundene Fehler (behoben)

Diese Fehler traten erst beim Arbeiten mit der echten `fpv.ttl` zutage:

1. **`skos:related` galt fälschlich als unbekanntes Prädikat.** Es fehlte
   schlicht in der Liste der bekannten Prädikate, wodurch jeder Block mit
   dieser völlig regulären SKOS-Beziehung unnötig gesperrt wurde. Behoben
   inklusive Parsen der kommagetrennten `ex:`-Objekte, Zurückschreiben,
   Formularfeld, Löschschutz und Validierung.
2. **Sprachkennzeichen von altLabels gingen beim Speichern verloren.**
   Der Renderer verwendete für *alle* `skos:altLabel` die Sprache des
   `skos:prefLabel`, und der Parser verwarf die einzelnen Angaben. Ein Block
   mit `"Non-Proliferation-Treaty"@en` wäre beim Speichern still zu `@de`
   geworden — stiller Datenverlust in mehrsprachigen Einträgen. Jede
   Benennung führt ihre Sprache jetzt einzeln, mit eigenem Eingabefeld im
   Formular. **Das ändert das JSON-Feld `alts`** (siehe API-Abschnitt).
3. **Die Schaltflächen in der Kopfzeile sahen deaktiviert aus.** Sie waren
   nie deaktiviert und alle Klick-Handler waren korrekt verdrahtet — aber
   `.header-actions button` setzte einen dunkelgrünen Hintergrund, während
   `button.secondary` weiterhin dunkle Schriftfarbe setzte. Dunkle Schrift
   auf dunklem Grund ist optisch von „ausgegraut" nicht zu unterscheiden.
   Behoben durch explizite helle Schriftfarbe und Rahmen.

### Ergänzungen aus dem Praxiseinsatz

- **Befunde im rechten Prüfungspanel sind anklickbar.** Ein Klick (oder
  Enter/Leertaste) springt zum betroffenen Eintrag, klappt dessen
  Buchstabengruppe auf, setzt aktive Such- und Typfilter zurück und scrollt
  den Eintrag in den Blick.
- **„Datei schließen"** in der Kopfzeile schließt die aktuelle TTL, ohne die
  App zu beenden, damit anschließend eine andere geöffnet werden kann. Dabei
  wird auch ein manuell gewählter Sicherungsort zurückgesetzt, damit er
  nicht unbemerkt für eine andere Datei weitergilt.
- **Geschützte Blöcke zeigen ihren Quelltext.** Statt den Block ganz zu
  verbergen, zeigt der Editor ihn jetzt unverändert und nur lesbar an, mit
  Zeilennummer und Begründung — so ist erkennbar, *was* das Problem ist.
- **„Suche zurücksetzen"** im Konzeptverzeichnis leert Suchfeld und
  Typfilter in einem Schritt.

### Auf echtem Windows bestätigt (nicht mehr nur Vermutung)

- **`launcher.py` läuft**: Tk-Startfenster, Server-Start und Browser-Start
  funktionieren. Der Browserstart über den direkten EXE-Pfad hat gegriffen
  (`C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe`) — der in
  der Übergabe beschriebene Fehler „Browserübergabe hat nie funktioniert"
  ist damit auf diesem Rechner behoben. Der erste Kandidatenpfad existierte
  dort nicht; die Fallback-Kette hat wie vorgesehen den zweiten genommen.
- **Drei echte Fehler wurden erst im realen Windows-Betrieb sichtbar und
  sind behoben:**
  1. **Zeilenenden der `.bat`-Dateien**: Sie wurden mit reinem LF statt
     CRLF erzeugt; `cmd.exe` verschluckte dadurch Zeichen am Zeilenanfang
     (`setlocal` → `etlocal`). Alle drei Skripte sind jetzt durchgängig
     CRLF.
  2. **Fehlende Diagnosemöglichkeit**: Ein Absturz im Server-Thread und
     Flasks eigene Fehler-Tracebacks gingen ausschließlich nach `stderr`,
     das im `--noconsole`-Build nirgendwo ankommt — ein 500-Fehler sah im
     Log identisch aus wie „Server gar nicht erreichbar". Jetzt schreibt
     Pythons `logging` (das Flask/Werkzeug intern nutzt) zusätzlich in
     `startup.log`, der Server-Thread ist gegen Ausnahmen abgesichert, und
     der Bereitschaftstest unterscheidet „keine Verbindung" von „Verbindung
     ja, aber Fehlerantwort".
  3. **Unvollständiger Build ohne Fehlermeldung**: Nach einem Build, der
     mitten im Kopieren von `static\index.html` abgestürzt war
     (`OSError: [Errno 22]`, mutmaßlich Virenscanner-Zugriff auf die Datei),
     fehlte `_internal\static\index.html` im fertigen Bundle. Der nächste
     Build meldete trotzdem „erfolgreich", weil PyInstaller mit Exitcode 0
     endete — der Fehler fiel erst zur Laufzeit als „Internal Server Error"
     auf. `build_windows.bat` und `diagnose_windows.bat` prüfen das
     Aufräumen jetzt auf Erfolg, löschen die alte `.spec` mit, und weisen
     nach dem Build ausdrücklich nach, dass `FPV-Editor.exe` **und**
     `_internal\static\index.html` vorhanden sind, bevor sie Erfolg melden.

  4. **Unvollständig installierter Ordner auf einem anderen Rechner**
     (`startup.log`: `FileNotFoundError … _internal\static\index.html`,
     wiederholte „HTTP 500“-Meldungen). `launcher.py` prüft jetzt vor dem
     Serverstart, ob `static\index.html` und `static\app.js` vorhanden und
     nicht leer sind. Fehlt etwas, erscheint eine verständliche Meldung („Programm
     unvollständig“, mit fehlenden Dateien und Hinweis, den GESAMTEN Ordner
     inkl. `_internal` neu zu kopieren bzw. die Cloud-Synchronisation
     abzuwarten); der Inhalt von `_internal` wird in `startup.log` protokolliert.
     Der Bereitschaftstest bricht bei einer 5xx-Antwort sofort ab, und die
     Startseite zeigt statt eines Tracebacks eine lesbare Fehlerseite. Die Build-
     Skripte prüfen zusätzlich `_internal\static\app.js`. **Die Ursache, warum
     die Datei auf dem betroffenen Rechner fehlte, ist damit nicht geklärt** —
     nur, dass sie jetzt sofort und verständlich auffällt.

### Weiterhin ungeprüft oder offen

- **Die eigentliche Ursache des ursprünglichen `PermissionError` /
  `WinError 5` beim Anlegen von Sicherungen ist weiterhin nicht
  diagnostiziert.** Der Neuaufbau macht den Schreibpfad robuster
  (verifizierte Sicherung vor jeder Änderung, atomares Schreiben mit
  dokumentiertem Fallback, zehn Kandidatenorte statt einem, Deduplizierung),
  aber ein erfolgreicher Speicher-/Sicherungsvorgang auf dem betroffenen
  Rechner ist bislang **nicht nachgewiesen** — die Testläufe kamen bisher
  nur bis zum Start der Oberfläche. Nächster sinnvoller Schritt: „Schreibzugriff
  prüfen" in der laufenden App und ein Speicherversuch auf einer **Kopie**
  der echten `fpv.ttl`.
- **Windows Defender meldet beim Entpacken des Projekt-ZIPs mitunter
  `Trojan:Win32/MalUri.A!cl`.** Betroffen sind ausschließlich die
  mitgelieferten Wheels in `wheels/`, die kompilierte Windows-Binaries
  enthalten (`pyinstaller` mit seinen Bootloader-Stubs `run.exe`/`runw.exe`,
  `setuptools` mit `cli.exe`/`gui.exe`, `markupsafe` mit einer `.pyd`).
  Der SHA256 des mitgelieferten `pyinstaller`-Wheels
  (`500bd58c7bf7e584a8435adccbd763a0b918d5c12b08d74ff50fd79b2915458b`)
  stimmt exakt mit dem von PyPI veröffentlichten Hash für diese Version
  überein — die Dateien sind unverändert. PyInstaller-Bootloader sind einer
  der bekanntesten Fälle von AV-Fehlalarmen überhaupt; Microsofts eigene
  Beschreibung dieser Kennung enthält keine technischen Details, es handelt
  sich um eine generische Heuristik-Kategorie. Eine abschließende
  Beurteilung kann nur ein Scan der konkreten Datei liefern.
- **`start_mit_python.bat` ist weiterhin nicht auf Windows ausgeführt
  worden** (im Gegensatz zu den beiden anderen Skripten).
- **Verhalten bei sehr großen Vokabularen (~1000+ Concepts) ist ungetestet**
  — die Testdaten decken nur kleine Beispieldateien ab. Die
  Baum-Rendering-Logik im Frontend ist nicht auf diesem Maßstab profiliert.
- **Abgleich mit `validate_fpv.py`** (nachträglich hochgeladen und geprüft,
  siehe unten). **`Readme-fuer-fpv.md` wurde nie hochgeladen** und ist damit
  weiterhin nicht einbezogen — falls sie zusätzliche Regeln enthält, sind die
  nicht berücksichtigt.

### Abgleich mit `validate_fpv.py` und `check_duplicate-id.py`

Beide Original-Scripte wurden inzwischen bereitgestellt und mit `fpv_core.py`
verglichen (Codelesung, kein Lauf auf der echten `fpv.ttl`, die nie
hochgeladen wurde). Ergebnis:

- **`skos:prefLabel`-Regeldifferenz** (bereits in der Übergabe §4 selbst
  benannt): `validate_fpv.py` prüft *höchstens eine* `prefLabel` und erlaubt
  für „Sonderfälle" auch keine; der Editor verlangt für jeden von ihm
  bearbeiteten Block *genau eine*. Naheliegende Erklärung: Die
  „Sonderfälle" ohne `prefLabel`, die `validate_fpv.py` toleriert, dürften
  Schema-Ressourcen außerhalb des `ex:`-Namensraums sein (z. B. eine
  Ressource wie `fpv:entityTypeNote`, die im Script von der
  Notation-Pflicht ausgenommen ist). Der Editor erkennt als Concept-Block
  ohnehin nur Subjekte mit `ex:`-Präfix — solche Sonderfälle wären ihm
  also gar nicht sichtbar und blieben unangetastet. Das ist meine
  plausibelste Deutung anhand des Codes, aber **unverifiziert**, da mir die
  echte `fpv.ttl` nicht vorliegt. Die Editor-Regel („genau eine") bleibt
  bestehen.
- **Zwei echte Lücken gefunden und behoben** (in `fpv_core.py`,
  mit je einem neuen Test in `tests/test_editor.py` #14/#15 abgedeckt):
  1. Ein Block mit **mehr als einer `skos:notation`** wurde bisher nicht
     geschützt — anders als bei `prefLabel` gab es dafür keine Zählung.
     Beim Speichern über das Formular (nur ein Typcode-Feld) wäre eine
     zweite Notation unbemerkt verworfen worden. **Wichtig:**
     `validate_fpv.py` selbst verbietet mehrere Notationen pro Concept
     nicht (es validiert dort jede einzeln, ohne die Anzahl zu prüfen) —
     dieser Schutz ist also keine Anlehnung an dessen Regelwerk, sondern
     eine eigenständige, zusätzliche Absicherung des Editors gegen seine
     eigene Formularbeschränkung.
  2. Der **Datentyp von `skos:notation`** (`^^fpv:entityType`) wurde beim
     Parsen bisher ignoriert — ein Bestandswert wie `skos:notation
     "com"^^xsd:string` oder ganz ohne `^^`-Angabe wäre unbemerkt
     akzeptiert und beim nächsten Speichern stillschweigend auf
     `^^fpv:entityType` normalisiert worden. `validate_fpv.py` meldet das
     explizit als Fehler ("Falscher Notation-Datentyp"). „Datei prüfen"
     meldet das jetzt ebenfalls als Fehler, statt es zu verschweigen.
- **Echter, verifizierter Fehler in `check_duplicate-id.py` gefunden** (nicht
  behoben, da nicht Teil dieses Projekts — nur zur Kenntnis): Das Script
  zählt `skos:Concept`-Subjekte über `g.subjects(RDF.type, SKOS.Concept)`
  auf einem `rdflib.Graph`. Ein `Graph` ist aber eine **Menge** von
  Tripeln — identische Tripel werden beim Parsen automatisch
  zusammengeführt, egal wie oft ein Subjekt im Quelltext als
  `a skos:Concept` deklariert ist. Ein direkter Test (zwei identische
  `ex:ABB a skos:Concept .`-Deklarationen) ergab `0` gemeldete Duplikate.
  Das Script kann eine solche Dopplung strukturell nicht finden. Der
  Editor selbst verwendet dafür bewusst einen Rohtext-Scan
  (`validate_whole_file`, Abschnitt „Doppelte IDs im Quelltext") statt
  RDFLib-Tripelzählung, aus genau diesem Grund.
- Alle anderen geprüften Regeln (ID-Format/NCName, erlaubte
  `entityType`-Codes, http/https-Pflicht für Links) stimmen inhaltlich
  überein; keine weiteren Abweichungen gefunden. Nicht übernommen wurde
  die Warnung von `validate_fpv.py` zu Nicht-ASCII-Zeichen in
  `exactMatch`/`closeMatch`-URIs (mit Vorschlag einer Percent-Encoding-
  Alternative) — das ist im Original nur eine Warnung, keine Fehlermeldung,
  und wurde hier bewusst nicht nachgebaut, um den Umfang dieser Korrektur
  nicht ohne Rückfrage auszuweiten.

## Bewusste Entwurfsentscheidungen (keine Fehler)

- **BOM wird nicht unterstützt** (wie in der Übergabe spezifiziert) — Dateien
  mit UTF-8-BOM werden beim Öffnen mit einer entsprechenden Fehlermeldung
  abgewiesen statt geraten zu werden.
- **„Sicherungsort wählen" verwendet bewusst kein natives Dialogfenster**,
  sondern ein Textfeld für einen eingefügten Pfad — laut Übergabe hatte ein
  nativer Ordnerdialog auf dem Originalrechner den Fehler „Kein Objekt für
  Moniker!" ausgelöst. Der Datei-**Öffnen**-Dialog dagegen nutzt weiterhin
  einen nativen `tkinter.filedialog.askopenfilename`-Dialog (laut
  Spezifikation nur dort vorgesehen).

## Auslieferung zukünftiger Korrekturen

Für spätere, punktuelle Korrekturen gilt die von Sven festgelegte
Präferenz: nur die geänderten einzelnen Dateien liefern, keinen erneuten
Gesamtzip. Diese erste Gesamtauslieferung ist davon eine bewusste Ausnahme,
da beim allerersten Aufbau naturgemäß alle Dateien neu entstehen.
