# FPV Editor MVP

Kleine lokale Flask-Anwendung zur Pflege einer `fpv.ttl` mit SKOS-Concept-Einträgen.

## Eigenschaften

- keine Datenbank
- `fpv.ttl` bleibt die maßgebliche Datei
- Übersicht mit Suche und alphabetischem Einstieg
- Einträge anlegen, bearbeiten, löschen
- einfache Pflichtfeldvalidierung
- Backup vor jedem Speichern
- optionaler Hook für externes Validierungsskript

## Projektstruktur

```text
fpv_editor_mvp/
├─ app.py
├─ fpv_store.py
├─ requirements.txt
├─ README.md
├─ data/
│  └─ fpv.ttl
├─ templates/
│  ├─ base.html
│  ├─ index.html
│  └─ entry_form.html
└─ static/
|  └─ style.css
├─ scripts
```

## Installation

- Python 3.11 oder neuer
- Flask
- rdflib

Wichtig:

- `app.py` und `fpv_store.py` müssen im selben Ordner liegen.
- Die zu bearbeitende Turtle-Datei muss als `data/fpv.ttl` vorliegen.
- Der Ordner `backups` wird für Sicherungskopien verwendet und kann bei Bedarf automatisch angelegt werden.
- Der Ordner `scripts` ist für optionale Validierungsskripte gedacht.



Unter Windows notwendige Pakete installieren:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```



Anwendung im Projektordner starten (Windows-Powershell):

```powershell
.\.venv\Scripts\Activate.ps1
python .\app.py
```

Die Anwendung findet sich unter http://127.0.0.1:5000

Sie kann unter Windows im Powershell-Fenster mit Strg + C beendet werden.