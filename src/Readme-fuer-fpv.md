# fpv.ttl

## Was ist diese Datei?

Die Datei `fpv.ttl` ist ein **kontrolliertes Vokabular** im Format **Turtle**. Turtle ist eine menschenlesbare Schreibweise für strukturierte Wissensdaten aus dem Bereich **RDF/SKOS**.

In dieser Datei werden Begriffe und Benennungen gesammelt, die in der Edition für die Annotierung der Protokolle genutzt werden:

- Parteien
- politische Gruppierungen
- Organisationen und Institutionen
- Unternehmen
- Medien
- Sachbegriffe
- Gesetze und Rechtsnormen

Das Ziel ist, dass dieselben Dinge **immer einheitlich benannt und eindeutig identifiziert** werden.
Die Datei dient also nicht der freien Beschreibung, sondern der **kontrollierten, konsistenten Erfassung**.

Ein Eintrag in dieser Datei ist daher nicht einfach nur ein Wort, sondern ein **normierter Begriff mit fester ID**.

------

## Wozu dient die Datei im Projekt?

Die Datei hat mehrere Funktionen:

- Sie sorgt für **einheitliche Benennungen**
- Sie verhindert unnötige Dubletten
- Sie erlaubt eine **saubere Referenzierung über IDs**
- Sie kann von Skripten, Webseiten und anderen Anwendungen weiterverarbeitet werden
- Sie hilft dabei, verschiedene Schreibweisen eines Begriffs zusammenzuführen

Beispiel:
Ein Unternehmen wie „ASEA Brown Boveri“ kann auch als „ABB“ bezeichnet werden.
Im Vokabular wird beides zusammengeführt: eine bevorzugte Form und eine oder mehrere Alternativformen.

## Was ist Turtle?

Turtle ist ein Textformat. Man kann es mit einem normalen Texteditor öffnen und bearbeiten (vorzugsweise VisualStudio Code). Jeder Eintrag besteht aus mehreren Aussagen über einen Begriff. Diese Aussagen werden Zeile für Zeile notiert.

Ein einfacher Eintrag sieht zum Beispiel so aus:

```ttl
ex:ABB a skos:Concept ;
  skos:prefLabel "ASEA Brown Boveri"@de ;
  skos:altLabel "ABB"@de ;
  skos:notation "com"^^fpv:entityType ;
  ex:useInSynonymList "true"^^xsd:boolean ;
  skos:exactMatch <https://d-nb.info/gnd/10041007-8> ;
  skos:closeMatch <https://de.wikipedia.org/wiki/ABB_(Unternehmen)> ;
  skos:note "Schweizerisch-schwedischer Technologiekonzern."@de .
```

Das sieht zunächst technisch aus, folgt aber einer klaren Ordnung. Diese Ordnung wird unten Schritt für Schritt erklärt.

------

## Grundprinzip der Datei

Die Datei besteht aus vielen einzelnen Einträgen.
Jeder Eintrag beschreibt **genau ein Konzept**.

Ein Konzept kann zum Beispiel sein:

- eine Partei
- eine Zeitung
- ein Unternehmen
- ein Verband
- ein Gesetz
- ein Thema

Jeder Eintrag hat dabei:

- eine **feste ID**
- eine **bevorzugte Benennung**
- gegebenenfalls **alternative Benennungen**
- eine **Typzuweisung**
- gegebenenfalls **Verweise auf externe Normdaten**
- eine kurze **Erläuterung**

------

## Aufbau der Datei im Überblick

Die Datei hat drei Ebenen:

### 1. Kopfbereich mit Präfixen

Am Anfang der Datei stehen technische Abkürzungen, sogenannte Präfixe. Diese müssen in der Regel nicht verändert werden.

Beispiel:

```ttl
@prefix ex:  <https://voc.fraktionsprotokolle.de/id/> .
@prefix fpv: <https://voc.fraktionsprotokolle.de/schema/> .
@prefix skos: <http://www.w3.org/2004/02/skos/core#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix dcterms: <http://purl.org/dc/terms/> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
```

Diese Zeilen schaffen die Grundlage für alles Weitere.
Wer nur Einträge pflegt, muss sie normalerweise nicht anfassen.

------

### 2. Dokumentierende Abschnitte

Die Datei kann zusätzlich einige erklärende oder dokumentierende Einträge enthalten, etwa zur Bedeutung der Typcodes. Auch diese werden normalerweise nicht laufend verändert.

------

### 3. Die eigentlichen Begriffseinträge

Der Hauptteil der Datei besteht aus den einzelnen Vokabulareinträgen.
Diese sind der Bereich, der im Arbeitsalltag gepflegt wird.

------

## Wie ist ein einzelner Eintrag aufgebaut?

Ein typischer Eintrag sieht so aus:

```ttl
ex:BeispielID a skos:Concept ;
  skos:prefLabel "Beispielbegriff"@de ;
  skos:altLabel "Alternative Bezeichnung"@de ;
  skos:notation "org"^^fpv:entityType ;
  ex:useInSynonymList "true"^^xsd:boolean ;
  skos:exactMatch <https://d-nb.info/gnd/...> ;
  skos:closeMatch <https://de.wikipedia.org/wiki/...> ;
  skos:note "Kurze Erläuterung des Begriffs."@de .
```

Im Folgenden wird jede Zeile erläutert.

------

## Erklärung der einzelnen Bestandteile

## 1. Die ID: `ex:BeispielID`

Beispiel:

```ttl
ex:ABB
```

Das ist die **interne Kennung** des Eintrags.
Die ID ist sehr wichtig, weil der Begriff im Projekt nicht nur über seinen Namen, sondern vor allem über diese ID referenziert werden kann.

Die ID muss:

- eindeutig sein
- stabil bleiben
- innerhalb der Datei nur ein einziges Mal vorkommen
- keine Leerzeichen enthalten

Die ID ist nicht einfach nur Dekoration, sondern der zentrale Identifikator des Eintrags.

**Sie muss den Regeln für XML:IDs entsprechen (z.B. nicht mit einer Zahl beginnen, keine Umlaute, keine Sonderzeichen, sie muss einzigartig sein in der Datei!)**

### Praktische Regel

Wenn ein Eintrag einmal produktiv genutzt wird, sollte seine ID **nicht geändert** werden, auch wenn das Label später angepasst wird.

------

## 2. `a skos:Concept`

Beispiel:

```ttl
a skos:Concept ;
```

Das bedeutet: Der Eintrag ist ein Begriff bzw. Konzept im kontrollierten Vokabular.

Diese Zeile ist bei allen regulären Einträgen gleich. Sie sollte nicht verändert oder weggelassen werden.

------

## 3. `skos:prefLabel`

Beispiel:

```ttl
skos:prefLabel "ASEA Brown Boveri"@de ;
```

Das ist die **bevorzugte Benennung** des Begriffs. Sie ist die Hauptform, unter der der Eintrag geführt wird.

Jeder Eintrag muss genau **ein** `prefLabel` haben.

### Was gehört hier hinein?

Hier steht die Form, die im Projekt als Hauptbenennung gelten soll.
Das ist in der Regel:

- der offizielle Name
- die etablierte Standardform
- diejenige Form, unter der der Begriff primär geführt werden soll

### Was gehört nicht hier hinein?

Nicht in `prefLabel` gehören bloße Kurzformen oder uneinheitliche Varianten, wenn eine klarere Hauptform vorhanden ist.

------

## 4. `skos:altLabel`

Beispiel:

```ttl
skos:altLabel "ABB"@de ;
```

Das sind **alternative Benennungen**. Dazu gehören etwa:

- Abkürzungen
- Kurzformen
- gebräuchliche Varianten
- andere Sprachformen
- historische Schreibweisen, falls sinnvoll

Ein Eintrag kann:

- kein `altLabel` haben
- ein `altLabel` haben
- mehrere `altLabel` haben

Wenn es mehrere Alternativformen gibt, bekommt jede eine eigene Zeile.

Beispiel:

```ttl
skos:altLabel "ABB"@de ;
skos:altLabel "Asea Brown Boveri"@de ;
```

### Wichtige Regel

Wenn kein alternatives Label vorhanden ist, wird `skos:altLabel` **nicht eingetragen**.
Leere Felder oder Platzhalter wie `/` sind nicht zulässig.

Also nicht:

```ttl
skos:altLabel "/"@de ;
```

und auch nicht:

```ttl
skos:altLabel ;
```

sondern einfach weglassen.

------

## 5. `skos:notation`

Beispiel:

```ttl
skos:notation "com"^^fpv:entityType ;
```

Dieses Feld gibt an, **welcher Art** der Eintrag ist.
Dazu wird ein kurzer Typcode verwendet.

In der Datei sind dafür folgende Werte vorgesehen:

- `org` = Organisation, Institution, Verband, Gremium
- `com` = Unternehmen, Wirtschaft
- `news` = Presse, Zeitung, Medium
- `topic` = Sachbegriff, Thema
- `law` = Gesetz, Rechtsnorm
- `pol` = Partei, politische Gruppierung

### Warum ist dieses Feld wichtig?

Die Typzuweisung hilft dabei,

- Einträge systematisch zu ordnen
- in Webseiten oder Filtern nach Typen zu unterscheiden
- die Datei konsistent auszuwerten

### Wie wählt man den richtigen Typ?

Die Typwahl soll sich am **inhaltlichen Charakter des Eintrags** orientieren.

Beispiele:

- CDU → `pol`
- Süddeutsche Zeitung → `news`
- Siemens → `com`
- Deutscher Gewerkschaftsbund → `org`
- Atomwaffensperrvertrag → `topic`
- Grundgesetz → `law`

### Wichtige Regel

Es dürfen nur die vorgesehenen Typcodes verwendet werden. Keine freien Neuschöpfungen wie etwa `institution`, `firma` oder `presse`.

------

## 6. `ex:useInSynonymList`

Beispiel:

```ttl
ex:useInSynonymList "true"^^xsd:boolean ;
```

Dieses Feld steuert, ob der Eintrag in eine Synonymliste übernommen werden soll.

Zulässig sind nur zwei Werte:

```ttl
"true"^^xsd:boolean
"false"^^xsd:boolean
```

### Wichtige Regel

Bitte nicht schreiben:

- `true`
- `false`
- `"ja"`
- `"nein"`
- `"True"`
- `"False"`

Verwendet werden darf nur die genaue Form mit `xsd:boolean`.

------

## 7. `skos:exactMatch`

Beispiel:

```ttl
skos:exactMatch <https://d-nb.info/gnd/10041007-8> ;
```

Hier kann ein **exakter externer Referenzwert** eingetragen werden.
In der Praxis ist das oft ein GND-Link. Viaf ist ebenfalls möglich.

Dieses Feld ist hilfreich, wenn sich ein Eintrag eindeutig mit einer Normdatei verknüpfen lässt.

### Wann sollte man dieses Feld benutzen?

Dann, wenn ein externer Datensatz wirklich **inhaltlich eindeutig und passend** ist.

### Wichtige Regel

Wenn kein solcher Link bekannt ist, wird das Feld einfach weggelassen.
Bitte keine Platzhalter wie `</>` eintragen.

Also nicht:

```ttl
skos:exactMatch </> ;
```

sondern gar nicht.

------

## 8. `skos:closeMatch`

Beispiel:

```ttl
skos:closeMatch <https://de.wikipedia.org/wiki/ABB_(Unternehmen)> ;
```

Dieses Feld dient für einen **nahen, aber nicht zwingend normativ exakten** externen Verweis.
Oft ist das ein Wikipedia-Artikel.

### Unterschied zu `exactMatch`

- `exactMatch` bedeutet: inhaltlich sehr genaue Entsprechung
- `closeMatch` bedeutet: inhaltlich naher Verweis, aber nicht unbedingt identisch im strengen Sinn

Wenn kein sinnvoller Verweis vorhanden ist, wird das Feld weggelassen.

------

## 9. `skos:note`

Beispiel:

```ttl
skos:note "Schweizerisch-schwedischer Technologiekonzern."@de .
```

Dies ist eine kurze Erläuterung zum Begriff.

Die `note` dient nicht der freien Essayform, sondern einer knappen Erklärung oder Einordnung.

Geeignet sind zum Beispiel:

- Funktionsbeschreibung
- kurze Identifikation
- sachliche Erläuterung
- editorische Einordnung

### Stil der Notiz

Die Notiz sollte:

- knapp
- sachlich
- informativ
- nicht redundant
- nicht zu lang

sein.

**`skos:note` soll als Grundlage für das Maus-Over in der Edition dienen.** 

------

## Welche Felder sind Pflicht, welche optional?

### Pflichtfelder

Jeder reguläre Eintrag muss mindestens diese Felder enthalten:

- `ex:ID`
- `a skos:Concept`
- `skos:prefLabel`
- `skos:notation`
- `ex:useInSynonymList`
- `skos:note`

### Optionale Felder

Nur bei Bedarf:

- `skos:altLabel`
- `skos:exactMatch`
- `skos:closeMatch`

### Grundsatz

Optionale Felder werden **nur dann eingetragen, wenn sie wirklich einen Inhalt haben**.
Leere Felder oder Platzhalter werden nicht verwendet.

------

## Formale Schreibregeln

Damit die Datei korrekt bleibt, müssen einige einfache Schreibregeln eingehalten werden.

### 1. Jede Aussage steht in einer eigenen Zeile

Beispiel:

```ttl
skos:prefLabel "Beispiel"@de ;
skos:altLabel "Abkürzung"@de ;
```

Das dient der Übersichtlichkeit.

------

### 2. Alle Zeilen eines Eintrags enden mit `;`, außer der letzten

Beispiel:

```ttl
ex:Beispiel a skos:Concept ;
  skos:prefLabel "Beispiel"@de ;
  skos:notation "org"^^fpv:entityType ;
  ex:useInSynonymList "true"^^xsd:boolean ;
  skos:note "Kurze Erläuterung."@de .
```

Die letzte Zeile endet mit einem Punkt `.` Das ist sehr wichtig.

------

### 3. Texte stehen in Anführungszeichen

Beispiel:

```ttl
"Beispielorganisation"@de
```

------

### 4. Sprachangaben bleiben erhalten

Für deutsche Bezeichnungen und Notizen wird in der Regel `@de` verwendet.

Beispiel:

```ttl
skos:prefLabel "Christlich Demokratische Union"@de ;
```

Falls ein alternatives Label bewusst englisch ist, kann auch `@en` sinnvoll sein.

------

### 5. URLs stehen in spitzen Klammern

Beispiel:

```ttl
<https://d-nb.info/gnd/1234567-8>
```

Nicht in Anführungszeichen schreiben.

------

### 6. Leere Werte sind nicht erlaubt

Nicht:

```ttl
skos:altLabel "/"@de ;
skos:exactMatch </> ;
```

Sondern: Feld weglassen.

------

## Wann sollte ein neuer Eintrag angelegt werden?

Ein neuer Eintrag sollte angelegt werden, wenn

- ein Begriff im Projekt wiederholt vorkommt
- er eindeutig identifizierbar ist
- er noch nicht in der Datei vorhanden ist
- eine konsistente Referenzierung sinnvoll ist

Vor dem Anlegen eines neuen Eintrags sollte immer geprüft werden, ob der Begriff nicht schon vorhanden ist, eventuell unter leicht abweichender Schreibweise.

------

## Vor dem Anlegen eines neuen Eintrags prüfen

Bevor ein neuer Eintrag hinzugefügt wird, bitte immer kontrollieren:

- Gibt es den Begriff bereits?
- Gibt es ihn in abweichender Schreibweise?
- Ist er vielleicht schon als `prefLabel` oder `altLabel` vorhanden?
- Welche Form soll die Hauptbenennung sein?
- Welcher Typcode passt?
- Gibt es einen GND-Link oder einen brauchbaren Wikipedia-Link?

Dazu kann auch die Webseite: https://voc.fraktionsprotokolle.de/ mit ihren Suchfunktionen genutzt werden.

Diese Vorprüfung ist wichtig, um Dubletten zu vermeiden.

------

## So legt man einen neuen Eintrag an

## Schritt 1: Eine eindeutige ID festlegen

Die ID muss neu sein und darf in der Datei nicht bereits vorkommen.

Beispiel:

```ttl
ex:BeispielInstitut
```

Die ID sollte möglichst kurz, eindeutig und stabil sein.

------

## Schritt 2: `prefLabel` eintragen

Beispiel:

```ttl
skos:prefLabel "Kommission für Geschichte des Parlamentarismus und der politischen Parteien"@de ;
```

------

## Schritt 3: Falls nötig `altLabel` ergänzen

Beispiel:

```ttl
skos:altLabel "KGParl"@de ;
skos:altLabel "Parlamentarismuskommission"@de ;
```

Nur eintragen, wenn es wirklich eine sinnvolle alternative Bezeichnung gibt.

------

## Schritt 4: Typcode setzen

Beispiel:

```ttl
skos:notation "org"^^fpv:entityType ;
```

------

## Schritt 5: Synonymlisten-Steuerung festlegen

Beispiel:

```ttl
ex:useInSynonymList "true"^^xsd:boolean ;
```

------

## Schritt 6: Falls vorhanden externe Verweise ergänzen

Beispiel:

```ttl
skos:exactMatch <https://d-nb.info/gnd/...> ;
skos:closeMatch <https://de.wikipedia.org/wiki/...> ;
```

Nur ergänzen, wenn tatsächlich ein sinnvoller Wert vorliegt.

------

## Schritt 7: Eine kurze `note` schreiben

Beispiel:

```ttl
skos:note "Wissenschaftliche Einrichtung mit Sitz in Berlin."@de .
```

------

## Komplettes Beispiel für einen neuen Eintrag

```ttl
ex:BeispielInstitut a skos:Concept ;
  skos:prefLabel "Kommission für Geschichte des Parlamentarismus und der politischen Parteien"@de ;
  skos:altLabel "KGParl"@de ;
  skos:altLabel "Parlamentarismuskommission"@de ;
  skos:notation "org"^^fpv:entityType ;
  ex:useInSynonymList "true"^^xsd:boolean ;
  skos:exactMatch <https://d-nb.info/gnd/123456789> ;
  skos:closeMatch <https://de.wikipedia.org/wiki/Beispiel-Institut> ;
  skos:note "Wissenschaftliche Einrichtung mit Sitz in Berlin."@de .
```

------

## So bearbeitet man einen bestehenden Eintrag

Ein bestehender Eintrag kann geändert werden, wenn

- das `prefLabel` korrigiert werden muss
- zusätzliche `altLabel` bekannt sind
- die `note` präzisiert werden soll
- externe Referenzen ergänzt werden
- der Typcode fehlerhaft war

### Dabei ist wichtig

- **Die ID möglichst nicht ändern**
- Die Struktur des Eintrags beibehalten
- Keine versehentlichen Syntaxfehler einführen
- Optionales nur ergänzen, wenn es tatsächlich sinnvoll ist

------

## Typische Fehler und wie man sie vermeidet

## 1. Doppelte IDs

Fehler:

Zwei Einträge verwenden dieselbe ID.

Warum problematisch?

Dann ist der Begriff nicht mehr eindeutig referenzierbar. Später XML-fehler!

Regel:

Vor dem Anlegen eines neuen Eintrags immer suchen, ob die ID schon existiert.

------

## 2. Uneinheitliche Benennungen

Fehler:

Dasselbe Objekt wird mehrfach mit leicht abweichenden Hauptbenennungen angelegt.

Beispiel:

- „Süddeutsche Zeitung“
- „SZ“
- „Sueddeutsche Zeitung“

Besser:

- eine Hauptform als `prefLabel`
- die anderen Formen als `altLabel`

------

## 3. Leere oder künstliche Platzhalter

Fehler:

```ttl
skos:altLabel "/"@de ;
skos:exactMatch </> ;
```

Warum problematisch?

Diese Werte tragen inhaltlich nichts bei und erschweren die Weiterverarbeitung.

Regel:

Wenn kein Wert vorhanden ist, Feld weglassen.

------

## 4. Falsche Typcodes

Fehler:

Ein Unternehmen erhält `org`, obwohl eigentlich `com` gemeint ist.

Regel:

Den Typ nicht nach Gefühl, sondern nach der Funktion des Eintrags wählen.

------

## 5. Falsche Boolean-Schreibweise

Fehler:

```ttl
ex:useInSynonymList "ja" ;
```

oder

```ttl
ex:useInSynonymList true ;
```

Regel:

Nur diese beiden Schreibweisen sind zulässig:

```ttl
"true"^^xsd:boolean
"false"^^xsd:boolean
```

------

## 6. Falsches Satzzeichen am Ende

Fehler:

Die letzte Zeile endet mit `;` statt mit `.`

Regel:

Der Eintrag endet immer mit Punkt.

------

## Entscheidungshilfe für die Typvergabe

### `pol`

Für Parteien und politische Gruppierungen.

Beispiele:

- CDU
- SPD
- CSU
- Bündnis 90/Die Grünen

### `org`

Für Organisationen, Institutionen, Behörden, Verbände, Ausschüsse oder Gremien.

Beispiele:

- Deutscher Gewerkschaftsbund
- Bundesverfassungsgericht
- NATO

### `com`

Für Unternehmen und wirtschaftliche Akteure.

Beispiele:

- Siemens
- ABB
- Volkswagen

### `news`

Für Medien, Zeitungen, Zeitschriften, Rundfunk und Presseorgane.

Beispiele:

- Frankfurter Allgemeine Zeitung
- Der Spiegel
- ARD

### `topic`

Für Themen und Sachbegriffe.

Beispiele:

- Mitbestimmung
- Umweltpolitik
- Nachrüstung

### `law`

Für Gesetze und Rechtsnormen.

Beispiele:

- Grundgesetz
- Betriebsverfassungsgesetz

------

## Stilregeln für wissenschaftliche Pflege

Die Datei ist kein freies Notizdokument, sondern ein normiertes Arbeitsinstrument. Deshalb gelten einige editorische Grundsätze.

### 1. Sachlich formulieren

Die Einträge sollen nüchtern und beschreibend bleiben.

### 2. Hauptbenennung vor Varianten

Das `prefLabel` soll die primäre, kontrollierte Form sein. Varianten gehören in `altLabel`.

### 3. Möglichst konsistent bleiben

Bei ähnlichen Fällen soll nach ähnlichen Prinzipien entschieden werden.

### 4. Lieber knapp und klar als zu ausführlich

Besonders in `skos:note`.

### 5. Bei Unsicherheit Rücksprache halten

Wenn unklar ist, ob ein Begriff neu angelegt, zusammengeführt oder anders klassifiziert werden soll, ist eine kurze redaktionelle Abstimmung besser als eine inkonsistente Einzelentscheidung.

------

## Empfohlener Arbeitsablauf bei manueller Pflege

Für die praktische Arbeit empfiehlt sich folgender Ablauf:

1. Datei öffnen
2. Nachsehen, ob der gesuchte Begriff schon vorhanden ist
3. Falls vorhanden: bestehenden Eintrag ergänzen oder korrigieren
4. Falls nicht vorhanden: neuen Eintrag anlegen
5. Typcode prüfen
6. Prüfen, ob sinnvolle alternative Bezeichnungen existieren
7. Externe Verweise nur eintragen, wenn sie wirklich passen
8. Kurze Note ergänzen
9. Syntax kontrollieren
10. Datei speichern und idealerweise validieren

------

## Kurze Checkliste für jeden Eintrag

Vor dem Speichern prüfen:

- Ist die ID eindeutig?
- Gibt es genau ein `prefLabel`?
- Passt der Typcode?
- Sind optionale Felder nur dann vorhanden, wenn sie befüllt sind?
- Wurden keine Platzhalter eingetragen?
- Ist der Boolean korrekt geschrieben?
- Endet die letzte Zeile mit `.`?

------

## Minimalbeispiel

Ein sehr einfacher, aber vollständiger Eintrag kann so aussehen:

```ttl
ex:BeispielPartei a skos:Concept ;
  skos:prefLabel "Beispiel-Partei"@de ;
  skos:notation "pol"^^fpv:entityType ;
  ex:useInSynonymList "true"^^xsd:boolean ;
  skos:note "Politische Gruppierung."@de .
```

Das ist vollkommen ausreichend, wenn noch keine Alternativbenennungen oder externen Verweise bekannt sind.

------

## Erweiterter Eintrag

```ttl
ex:BeispielZeitung a skos:Concept ;
  skos:prefLabel "Beispiel-Zeitung"@de ;
  skos:altLabel "BZ"@de ;
  skos:notation "news"^^fpv:entityType ;
  ex:useInSynonymList "true"^^xsd:boolean ;
  skos:exactMatch <https://d-nb.info/gnd/123456789> ;
  skos:closeMatch <https://de.wikipedia.org/wiki/Beispiel-Zeitung> ;
  skos:note "Überregionale Tageszeitung."@de .
```

------

## Was nicht in die Datei gehört

Nicht in diese Datei gehören:

- freie lange Beschreibungen
- persönliche Kommentare
- unsichere Platzhalter
- uneinheitliche Hilfskonstruktionen
- technische Experimente ohne Absprache
- mehrfach angelegte Begriffe mit nur leicht abweichenden Namen

------

## Zusammenfassung

Die Datei `fpv.ttl` ist ein kontrolliertes Vokabular.
Jeder Eintrag beschreibt einen normierten Begriff mit fester ID.
Für die manuelle Pflege sind vor allem fünf Dinge wichtig:

- konsequent dieselbe Struktur verwenden
- Hauptbenennung und Alternativbenennungen sauber unterscheiden
- den richtigen Typcode wählen
- optionale Felder nur bei tatsächlichem Inhalt verwenden
- keine Platzhalter oder leeren Felder eintragen

