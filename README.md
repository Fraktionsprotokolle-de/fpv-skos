# fpv-skos
Dieses Repository dient der Entwicklung eines kontrollierten (Schlagwort-)Vokabulars (Fraktionsprotokolle Vocabulary, FPV) für die wissenschaftliche Edition »Fraktionen im Deutschen Bundestag 1949-2005«. Es soll in Zukunft als zentrale Referenzinstanz für die semantische Erschließung der Protokolle und die Optimierung der webbasierten Suche dienen.

## Zweck des Vokabulars

Das Vokabular wird als **SKOS (Turtle)** gepflegt und dient in Zukunft als Single Source of Truth für:

- Organisationsnamen
- politische Begriffe
- Institutionen
- Gesetze
- Medien
- Themen
- Synonyme für Suchindexe
- Entity-Typen für die Webdarstellung

## Datenstruktur und Formate

Das Vokabular wird nach dem **SKOS-Standard (Simple Knowledge Organization System)** verwaltet.

- **Source of Truth:** `src/fpv.ttl` (Turtle-Format). **Alle Änderungen am Vokabular erfolgen ausschließlich in dieser Datei**.
- **TEI-Export:** `dist/xml/tei-fpv.xml`. Eine automatisch generierte TEI-Taxonomie zur Einbindung als Authority File in Oxygen XML.
- **Typesense-Export:** `dist/json/synonyms-fpv.jsonl`. Eine flache Liste von Synonymgruppen für die Indizierung der digitalen Edition.

## Technischer Workflow (in Entwicklung)

Die Verarbeitung der Daten soll automatisiert über GitHub Actions erfolgen:

1. **Validierung:** Bei jedem Commit wird die `src/fpv.ttl` auf syntaktische Korrektheit (RDF/SKOS) geprüft (geplant, derzeit manuell.
2. **Transformation:** Python-Skripte (`scripts/`) generieren die XML- und JSON-Artefakte im Verzeichnis `dist/`. Diese sind Grundlage für die Erstellung der Register in der Edition fraktionsprotokolle.de
3. **Publikation:** Zur besseren Lesbarkeit wird das Vokabular zugleich als einfache Webseite ausgeliefert: `https://fraktionsprotokolle-de.github.io/fpv-skos/index.html`.

## Struktur des Repositoriums

```
/
├── .github/ 	-- Workflow für die GH-Actions
├── dist/		-- TEI-XML für die Edition und JSONL für die Suche in der Edition
├── docs/		-- Verzeichnis für HTML für Webseite mit dem Vokabular
├── scripts/	-- Verzeichnis sämtlicher genutzter Scripte
├── src/		-- Vokabular im Turtle-Format (RDF/SKOS).
├── README.md
```

