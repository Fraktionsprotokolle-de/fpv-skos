# Validierung der FPV-Vokabulardatei (`fpv.ttl`)

Dieses Dokument beschreibt das Validierungsscript `validate_fpv.py`, erklärt was es prüft und wie man es einrichtet und ausführt – auch ohne Programmiererfahrung, unter Windows 11 mit VS Code.

---

## Inhaltsverzeichnis

1. [Wofür ist die Validierung?](#1-wofür-ist-die-validierung)
2. [Was wird geprüft?](#2-was-wird-geprüft)
3. [Python unter Windows 11 installieren](#3-python-unter-windows-11-installieren)
4. [rdflib installieren](#4-rdflib-installieren)
5. [Das Script in VS Code ausführen](#5-das-script-in-vs-code-ausführen)
6. [Die Ausgabe verstehen](#6-die-ausgabe-verstehen)
7. [Häufige Fehler und ihre Behebung](#7-häufige-fehler-und-ihre-behebung)
8. [Hinweise zur Turtle-Syntax](#8-hinweise-zur-turtle-syntax)

---

## 1. Wofür ist die Validierung?

Die Datei `fpv.ttl` ist ein SKOS-Vokabular im Turtle-Format. Sie enthält mehrere hundert Einträge (`skos:Concept`), die Organisationen, Parteien, Medien und andere Entitäten beschreiben. Da die Datei von Hand gepflegt wird, können sich Tippfehler einschleichen – vergessene Semikolons, fehlende Sprachkennzeichen (`@de`), doppelte IDs oder falsche Typangaben.

Das Script `validate_fpv.py` prüft die Datei automatisch und meldet Fehler mit der **genauen Zeilennummer** und dem **Kontext** im Quelltext, sodass man den Fehler sofort in der Datei finden und beheben kann.

---

## 2. Was wird geprüft?

Die Validierung läuft in zwei Phasen.

### Phase 1 – Syntaxprüfung

Jeder `skos:Concept`-Block wird einzeln mit der RDF-Bibliothek rdflib geparst. Dadurch werden **alle** fehlerhaften Blöcke in einem Durchlauf gefunden – nicht nur der erste. Erkannte Fehlerarten:

| Fehlermeldung | Bedeutung | Beispiel |
|---|---|---|
| `Fehlendes ';' oder '.' nach URI` | Semikolon nach einer URL vergessen | `skos:exactMatch <https://...>` ← kein `;` |
| `Fehlendes ';' oder '.' nach Sprachkennzeichen` | Semikolon nach `@de` o. ä. vergessen | `skos:altLabel "Abkürzung"@de` ← kein `;` |
| `Fehlendes ';' oder '.' nach Literal` | Semikolon nach einem Textwert vergessen, oder `@de` fehlt ganz | `skos:altLabel "Langname"` ← kein `@de ;` |

Die Strukturvalidierung (Phase 2) wird übersprungen, bis alle Syntaxfehler behoben sind.

### Phase 2 – Strukturvalidierung

Sobald die Datei syntaktisch korrekt ist, werden inhaltliche Regeln geprüft:

**1) Doppelte Concept-Definitionen**
Jede lokale ID (z. B. `ex:AA`) darf nur einmal als `skos:Concept` definiert sein.

**2) ID-Format**
Lokale IDs müssen gültige XML-NCNames sein und dürfen nur ASCII-Zeichen, Ziffern, Punkt, Bindestrich und Unterstrich enthalten. Umlaute in IDs (nicht in Labels) sind nicht erlaubt.

**3) Pflichtfeld `skos:prefLabel@de`**
Jeder Eintrag muss genau ein deutschsprachiges Vorzugsbezeichnung haben. Fehlt sie oder ist sie mehrfach vorhanden, wird das gemeldet. Einträge, die nur ein englisches Label haben (z. B. internationale Organisationen), lösen ebenfalls eine Meldung aus.

**4) Pflichtfeld `skos:notation` mit korrektem Typ**
Jeder Eintrag (außer dem internen Dokumentationsknoten `fpv:entityTypeNote`) muss eine Notation vom Typ `^^fpv:entityType` mit einem der folgenden Codes haben:

| Code | Bedeutung |
|---|---|
| `org` | Organisation, Institution, Verband, Gremium |
| `com` | Unternehmen, Wirtschaft |
| `news` | Presse, Zeitung, Medium |
| `topic` | Sachbegriff, Thema |
| `law` | Gesetz, Rechtsnorm |
| `pol` | Partei, politische Gruppierung |

**5) Nicht-ASCII-Zeichen in IRIs (Hinweis, kein Fehler)**
URIs in `skos:closeMatch`, `skos:exactMatch` usw. dürfen laut Standard (RFC 3987) Unicode-Zeichen direkt enthalten. Das Script gibt einen Hinweis aus, wenn solche Zeichen vorkommen, und nennt die percent-encodierte Alternative – behandelt das aber nicht als Fehler, da die Daten korrekt sind.

---

## 3. Python unter Windows 11 installieren

### Schritt 1: Python herunterladen

Öffne [python.org/downloads](https://www.python.org/downloads/) und klicke auf den großen Button **„Download Python 3.x.x"** (die neueste stabile Version).

### Schritt 2: Installieren

Starte den Installer. **Wichtig:** Setze ganz unten im ersten Fenster den Haken bei **„Add Python to PATH"**, bevor du auf „Install Now" klickst. Ohne diesen Haken findet Windows Python später nicht automatisch.

![Python Installer – Add to PATH](https://docs.python.org/3/_images/win_installer.png)

Klicke dann auf „Install Now" und bestätige die UAC-Abfrage.

### Schritt 3: Installation prüfen

Öffne die **Windows-Eingabeaufforderung** (`Win + R` → `cmd` → Enter) und gib ein:

```
python --version
```

Die Ausgabe sollte etwa `Python 3.12.x` zeigen. Erscheint stattdessen eine Fehlermeldung, wurde Python nicht korrekt in PATH eingetragen – deinstalliere und wiederhole Schritt 2 mit dem PATH-Haken.

---

## 4. rdflib installieren

Das Script benötigt die Python-Bibliothek **rdflib** zum Parsen von Turtle-Dateien. Sie wird einmalig über den Python-Paketmanager `pip` installiert.

Öffne die Eingabeaufforderung (`cmd`) und führe aus:

```
pip install rdflib
```

Die Installation dauert etwa eine Minute. Abschließend erscheint `Successfully installed rdflib-...`. Die Bibliothek muss nur einmal installiert werden; sie bleibt dauerhaft verfügbar.

**Prüfen:**

```
python -c "import rdflib; print(rdflib.__version__)"
```

Gibt diese Zeile eine Versionsnummer aus (z. B. `7.1.1`), ist alles bereit.

---

## 5. Das Script in VS Code ausführen

### VS Code installieren (falls noch nicht vorhanden)

Lade VS Code von [code.visualstudio.com](https://code.visualstudio.com/) herunter und installiere es.

### Python-Erweiterung installieren

Öffne VS Code, klicke links auf das Erweiterungs-Symbol (vier Quadrate) oder drücke `Strg+Shift+X`, suche nach **„Python"** (Herausgeber: Microsoft) und klicke auf „Installieren".

### Dateien öffnen

Öffne den Ordner, der `validate_fpv.py` und `fpv.ttl` enthält, über **Datei → Ordner öffnen**.

### Script ausführen – Methode A: Terminal in VS Code

Öffne das integrierte Terminal mit `Strg+ö` (oder über **Terminal → Neues Terminal**) und gib ein:

```
python validate_fpv.py fpv.ttl
```

Wenn `fpv.ttl` und `validate_fpv.py` im gleichen Ordner liegen und das Terminal in diesem Ordner geöffnet ist, funktioniert das direkt.

Mit einem optionalen zweiten Argument kann man einen eigenen Pfad für die Logdatei angeben:

```
python validate_fpv.py fpv.ttl C:\Users\Name\Desktop\bericht.log
```

### Script ausführen – Methode B: Run-Button

Öffne `validate_fpv.py` in VS Code. Oben rechts erscheint ein **Dreieck-Symbol (▶)**. Klicke darauf.

**Hinweis:** Der Run-Button übergibt kein Argument für die TTL-Datei. Das Script sucht dann nach dem Standardpfad `../src/fpv.ttl` relativ zum Script. Wenn deine Datei woanders liegt, ist Methode A zuverlässiger.

### Script ausführen – Methode C: Aufgabe konfigurieren (empfohlen für regelmäßigen Einsatz)

Für häufige Nutzung lässt sich eine VS Code-Aufgabe einrichten, die per Tastenkürzel auslöst:

1. Drücke `Strg+Shift+P` und wähle **„Tasks: Configure Task"**.
2. Wähle **„Create tasks.json file from template"** → **„Others"**.
3. Ersetze den Inhalt der `tasks.json` durch:

```json
{
  "version": "2.0.0",
  "tasks": [
    {
      "label": "FPV validieren",
      "type": "shell",
      "command": "python",
      "args": [
        "${workspaceFolder}/validate_fpv.py",
        "${workspaceFolder}/src/fpv.ttl"
      ],
      "group": {
        "kind": "build",
        "isDefault": true
      },
      "presentation": {
        "reveal": "always",
        "panel": "shared"
      }
    }
  ]
}
```

Passe den Pfad zu `fpv.ttl` bei Bedarf an. Danach startet `Strg+Shift+B` die Validierung direkt.

---

## 6. Die Ausgabe verstehen

### Bei Syntaxfehlern

```
❌ SYNTAXFEHLER GEFUNDEN (2 Blöcke betroffen)

FEHLER  Zeile 1565  [ex:BritPet, Block 1560–1567]
        Fehlendes ';' oder '.' nach URI

        1562    skos:altLabel "BP"@en ;
        1563    skos:notation "com"^^fpv:entityType ;
        1564   ex:useInSynonymList "false"^^xsd:boolean ;
  >>>   1565    skos:exactMatch <https://d-nb.info/gnd/2005982-6>
        1566    skos:closeMatch <https://de.wikipedia.org/wiki/BP> ;
        1567    skos:note "Erläuterungen können jetzt hier stehen."@de .
```

- **`Zeile 1565`** – die genaue Zeile mit dem Fehler
- **`[ex:BritPet, Block 1560–1567]`** – welcher Concept-Eintrag betroffen ist und wo sein Block beginnt und endet
- **`Fehlendes ';' oder '.' nach URI`** – die Diagnose: hier fehlt ein Semikolon nach der URL in Zeile 1565
- **`>>>`** – Pfeil auf die Fehlerzeile; drei Zeilen Kontext davor und zwei danach

### Bei Strukturfehlern

```
❌ STRUKTURVALIDIERUNG FEHLGESCHLAGEN (3 Fehler)

  - Zeile 76: Fehlendes skos:prefLabel@de in ex:ABC <...>
  - Zeile 3124: Mehrfaches skos:prefLabel@de in ex:DSoz <...>
  - Zeile 890: Ungültiger entityType-Code 'xyz' in ex:XYZ <...>
```

### Bei Hinweisen (kein Fehler)

```
⚠️  HINWEISE (2)

  - Zeile 5049: Nicht-ASCII-Zeichen in IRI (laut RFC 3987 erlaubt, aber rdflib warnt).
          Percent-encoded Alternative: <https://de.wikipedia.org/wiki/Meeresbodenbeh%C3%B6rde>
```

Hinweise blockieren die Validierung nicht. Der Exit-Code ist trotzdem `0` (Erfolg), sofern keine echten Fehler vorliegen.

### Logdatei

Neben der Konsolenausgabe schreibt das Script eine Logdatei. Standardmäßig liegt sie im gleichen Verzeichnis wie `fpv.ttl` und heißt `fpv.errors.log`. Sie enthält denselben Inhalt wie die Konsolenausgabe und kann als Referenz gespeichert oder per Mail weitergegeben werden.

### Erfolgsmeldung

```
✅ Validierung erfolgreich. Keine Fehler gefunden.
```

---

## 7. Häufige Fehler und ihre Behebung

### `python` wird nicht erkannt

```
'python' is not recognized as an internal or external command
```

Python wurde nicht zu PATH hinzugefügt. Lösung: Python deinstallieren und neu installieren, diesmal **mit** dem Haken bei „Add Python to PATH" (siehe Abschnitt 3).

Alternativ: `py` statt `python` eintippen – auf manchen Windows-Systemen funktioniert das als Fallback.

### `ModuleNotFoundError: No module named 'rdflib'`

rdflib ist nicht installiert. Lösung:

```
pip install rdflib
```

Falls pip selbst nicht gefunden wird:

```
python -m pip install rdflib
```

### `ERROR: Turtle file not found at ...`

Das Script findet die TTL-Datei nicht. Entweder wurde kein Pfad übergeben und der Standardpfad (`../src/fpv.ttl`) stimmt nicht, oder der angegebene Pfad ist falsch. Lösung: Pfad explizit angeben:

```
python validate_fpv.py C:\Pfad\zur\fpv.ttl
```

### Umlaute im Terminal werden falsch dargestellt

Unter Windows kann das Terminal `cmd` Umlaute falsch anzeigen. Lösung: VS Code's integriertes Terminal verwenden (PowerShell oder Git Bash), das UTF-8 korrekt unterstützt. Alternativ in `cmd`:

```
chcp 65001
```

Das schaltet `cmd` auf UTF-8 um.

---

## 8. Hinweise zur Turtle-Syntax

Für alle, die Einträge in `fpv.ttl` manuell bearbeiten, hier die wichtigsten Syntaxregeln:

**Semikolon vs. Punkt:** Innerhalb eines Blocks trennt `;` die Eigenschaften. Der letzte Eintrag des Blocks endet mit `.`:

```turtle
ex:AA a skos:Concept ;
  skos:prefLabel "Auswärtiges Amt"@de ;
  skos:notation "org"^^fpv:entityType ;
  skos:note "Erläuterungen hier."@de .
```

**Sprachkennzeichen:** Deutsche Textwerte müssen `@de` am Ende tragen, englische `@en`. Das Semikolon kommt danach:

```turtle
skos:prefLabel "Auswärtiges Amt"@de ;
```

**Kommentare:** Kommentare beginnen mit `#` und gelten bis zum Zeilenende. Ein `#` innerhalb einer URL (`<https://...#Fragment>`) ist dagegen Teil der URL und kein Kommentar:

```turtle
# Das ist ein Kommentar
skos:closeMatch <https://de.wikipedia.org/wiki/Seite#Abschnitt> ;  # auch das ist ein Kommentar
```

**Notation:** Der entityType-Code muss als typisiertes Literal angegeben werden:

```turtle
skos:notation "org"^^fpv:entityType ;
```

Erlaubte Werte: `org`, `com`, `news`, `topic`, `law`, `pol`.

**IDs:** Die lokale ID in `ex:XYZ` darf nur ASCII-Buchstaben, Ziffern, Punkt, Bindestrich und Unterstrich enthalten. Umlaute in IDs (nicht in Labels oder URLs) sind nicht erlaubt.
