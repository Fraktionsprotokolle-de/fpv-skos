# AGENTS.md – Arbeitsregeln für KI-Agenten im Projekt FPV-Editor

Diese Datei wird von Google Antigravity (und anderen Agenten-IDEs) beim
Sitzungsstart automatisch als Workspace-Regel geladen. Die ausführliche
Projektübergabe steht in `FPV-Editor_Uebergabe_Antigravity.md` –
**vor der ersten Änderung vollständig lesen.**

## Sprache und Haltung

- Arbeitssprache ist **Deutsch** (Antworten, Kommentare in der Oberfläche,
  Commit-Texte, Dokumentation).
- **Nachfragen, wenn etwas unklar ist.** Nichts erfinden. Unbekanntes als
  unbekannt benennen.
- **Keine Erfolgsbehauptung ohne Beleg.** Was nicht tatsächlich ausgeführt
  oder angesehen wurde, ausdrücklich als „ungeprüft“ kennzeichnen.
- Fehlerbeschreibungen des Nutzers (z. B. aus `startup.log`) sind in der
  Regel echte Befunde: erst im Code belegen, dann ändern.
- Gestaltungsentscheidungen (Rückmeldungskonzept, Layout, Texte) **mit dem
  Nutzer abstimmen**, nicht eigenmächtig festlegen.

## Produktregeln (aus den Projektvorgaben)

- Zielgruppe sind Kolleginnen und Kollegen **mit wenig Computer- und
  SKOS-Erfahrung**. Oberfläche klar, einfach, ohne Fachjargon.
- **Jede destruktive Handlung braucht eine Sicherheitsabfrage** (Beenden,
  Löschen, Verwerfen, Schließen mit offenen Änderungen, Wiederherstellen).
- **Jede Aktion muss sichtbare Rückmeldung geben** – bei Erfolg, bei Fehler
  und bei „nichts zu tun“. Kein stilles Zurückkehren.
- Rein lokal: Server nur an `127.0.0.1`, keine Internetzugriffe, keine CDNs,
  keine externen Schriften oder Bibliotheken im Frontend.
- Die TTL-Datei wird **blockweise textuell** bearbeitet, nie komplett neu
  serialisiert. Reihenfolge beim Schreiben ist fest: Versionsprüfung →
  Validierung → verifizierte Sicherung → erst dann Schreiben.

## Technische Pflichten vor jeder Lieferung

```
python -m pytest tests/test_editor.py -q
node --check static/app.js
```

Beides muss fehlerfrei sein. Neue Funktionen bekommen Tests in
`tests/test_editor.py`.

## Dateikonventionen

- `.bat`-Dateien **immer mit CRLF-Zeilenenden und ohne BOM** speichern
  (sonst verschluckt `cmd.exe` Zeichen – ist bereits passiert).
- Python-, JS-, HTML- und Markdown-Dateien: UTF-8 ohne BOM.
- In `static/app.js` werden Umlaute in Zeichenketten überwiegend als
  `ä` usw. geschrieben; diesen Stil beibehalten.
- Für Korrekturen dem Nutzer **nur die geänderten Einzeldateien** nennen bzw.
  liefern, keinen Gesamtumbau.

## Nicht anfassen ohne Rückfrage

- `fpv_core.py` (Parser, Schreib- und Sicherungslogik) – nur wenn eine
  Aufgabe es zwingend verlangt; jede Änderung mit Test absichern.
- `build_windows.bat`, `diagnose_windows.bat`, `bundle_check.py`,
  `make_release.py` (Auslieferung, auf Windows erprobt).
- Der Ordner `wheels/` (Offline-Abhängigkeiten für den Build) liegt nur beim
  Nutzer lokal vor und ist nicht Teil der Quellen.
