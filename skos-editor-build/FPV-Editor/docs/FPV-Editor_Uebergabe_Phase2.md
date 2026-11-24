# FPV-Editor – Übergabe Phase 2 (Stand 2026-10-07)

Ergänzt `FPV-Editor_Uebergabe_GUI-Phase.md` (enthalten) – dort stehen Architektur und Grundregeln. Dieses Dokument beschreibt, was seitdem geschehen ist und was offen ist.

## Nutzer und Arbeitsweise
Sven (Historiker, KGParl, DH-Experte, Deutsch). Vorgabe: Rückfragen bei Unklarheit, präzise Antworten, reale Quellen, nichts erfinden, Unwissen offen sagen. Weitere Regeln: nur geänderte Einzeldateien liefern; vor Lieferung `python -m pytest tests/test_editor.py -q` und `node --check static/app.js`; keine Erfolgsbehauptung ohne Beleg; Windows-/Browserverhalten als ungeprüft kennzeichnen (kein Windows hier); `.bat` immer CRLF, ohne BOM; Python auf fremden Dateien mit `-I`.

## Projekt
Lokale Windows-App (Flask + RDFLib, statisches HTML/JS, Tk-Launcher, PyInstaller `--onedir`) zur Bearbeitung des SKOS/Turtle-Vokabulars `fpv.ttl` (fraktionsprotokolle.de, 858 Konzepte). Mehrere Kolleg*innen mit geringer SKOS-Kenntnis nutzen sie – der Editor soll ihnen Arbeit abnehmen.

## Seit Phase 1 umgesetzt (alles getestet: 56 pytest-Tests grün)
- GUI: gruppierte Toolbar (Datei / Sicherung), Eintragsleiste (Neu, Speichern, Speicherstatus, Löschen), Rückmeldungsdialog bei jeder Aktion, eine Prüftaste, größere Schrift, deutsche Feldbezeichnungen + Hilfetexte, Trennlinien, technische Namen immer sichtbar, Hilfe-Dialog, Sicherungsstatus, verständliche Meldungen für geschützte Blöcke.
- Related-Concepts-Auswahl mit Namenssuche.
- „Kennung ändern …“: ID-Umbenennung inkl. Verweise (gezielter Textersatz + RDF-Isomorphiebeweis; verweigert bei Verweisen in geschützten Blöcken). Die ID-Sperre stammt aus dem Original.
- Synonymlisten-Kollisionsprüfung für Typesense (`ex:useInSynonymList "true"^^xsd:boolean`): bildet die Regeln von `ttl2jsonl.py` nach (strip, Blacklist {pol,com,soc,news,topic,law,org}, Länge>1, ≥2 Labels). Gleiches Label in zwei Synonymsets → NEUE Kollision blockiert Speichern (HTTP 400), bestehende sind Warnungen. Vergleich NFC/Whitespace/casefold. Endpunkte `/api/synonym-check`, `/api/rename-check`, `/api/rename`.
- Bugfix Original: jedes Speichern fügte eine Leerzeile hinzu (`rstrip("\n")`, Regressionstest).
- Startprüfung (neu): `launcher.py` prüft vor Serverstart `static/index.html` und `static/app.js` (vorhanden, nicht leer); sonst Meldung „Programm unvollständig“ + Log (inkl. Inhalt von `_internal`), Ende. Bereitschaftstest bricht bei 5xx sofort ab und zeigt Dialog. `index()` zeigt lesbare Fehlerseite. Build-Skripte prüfen auch `_internal\static\app.js`.

## Offener Fall: Start auf fremdem Rechner
`startup.log` (2026-10-07 09:52): `FileNotFoundError … FPV-Editor\_internal\static\index.html` bei `GET /` (Traceback `app.py` Zeile 110 = neue Fassung), danach 500er-Schleife. Ordner wurde per Nextcloud kopiert (dist\FPV-Editor auf dem Entwicklungsrechner gebaut; auf dem Zielrechner ist kein Python). Svens Befund später: `index.html` und `app.js` sind in `_internal\static` vorhanden, Synchronisation ist durchgelaufen. Pfadlogik ist `__file__`-relativ, also kein Pfadfehler. **Ursache ungeklärt.** Hypothesen (unbelegt): Start vor Ende der Synchronisation; Nextcloud-Platzhalterdateien; Virenscanner. Empfehlung an Sven: Ordner lokal (z. B. `C:\FPV-Editor`) statt im Nextcloud-Ordner ausführen, mit neu gebauter Fassung erneut testen, bei Fehler neue `startup.log` schicken. Offene Rückfrage an Sven: Dateigröße von `index.html` dort (soll ≈ 23985 Byte sein), Wolken-Symbol im Explorer?

## Weitere offene Punkte
- 23 bestehende Synonym-Kollisionen (`kollisionen-synonymliste.md`) – Bereinigungsvorschlag gewünscht?
- Verweise (`skos:related`) beidseitig schreiben? – unbeantwortet.
- Typesense: Groß-/Kleinschreibung bei Synonymen? Editor vergleicht casefold. – ungeprüft.
- Datenfehler: `ex:WaffenSS` closeMatch `hhttps://…`; `ex:IDA` `skos:altLabelLabel` (Tippfehler).
- Ansprechperson-Text für geschützte Blöcke?
- Alles auf echtem Windows unverifiziert.

## Dateien (siehe ZIP `FPV-Editor-Quellen_Phase2.zip`)
app.py, fpv_core.py, launcher.py, static/index.html, static/app.js, tests/test_editor.py, build_windows.bat, diagnose_windows.bat, start_mit_python.bat, requirements.txt, README.md, kollisionen-synonymliste.md, beide Übergabedokumente. Nicht enthalten (liegen bei Sven): fpv.ttl, ttl2jsonl.py, synonyms-fpv.jsonl, wheels/.
