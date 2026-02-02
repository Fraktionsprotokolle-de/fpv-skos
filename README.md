# fpv-skos
Dieses Repository dient der Entwicklung eines kontrollierten Schlagwortvokabulars (Fraktionsprotokolle Vocabulary, FPV) für die wissenschaftliche Edition »Fraktionen im Deutschen Bundestag 1949-2005«. Es soll in Zukunft als zentrale Referenzinstanz für die semantische Erschließung der Protokolle und die Optimierung der webbasierten Suche dienen.

## Zweck des Vokabulars

Das FPV konsolidiert Sachschlagworte sowie Bezeichnungen von Organisationen und Institutionen, die in den Editionsbänden und im Webauftritt Fraktionsprotkolle.de Erwähnung finden. 

Die Ziele des Repositories umfassen:

- **Semantische Annotation:** Bereitstellung stabiler Identifikatoren (URIs) für die Auszeichnung von Entitäten in den TEI-XML-Dokumenten der Edition.
- **Suchoptimierung:** Hinterlegung von Synonymen und Abkürzungen zur Anreicherung einer Typesense-Volltextsuche.
- **Interoperabilität:** Verknüpfung der Begriffe mit externen Normdaten (GND, Wikidata) im Sinne der Linked Open Data (LOD) Prinzipien.

## Datenstruktur und Formate

Das Vokabular wird nach dem **SKOS-Standard (Simple Knowledge Organization System)** verwaltet.

- **Source of Truth:** `src/fpv.ttl` (Turtle-Format). **Alle Änderungen am Vokabular erfolgen ausschließlich in dieser Datei**.
- **TEI-Export:** `dist/xml/taxonomy-fpv.xml`. Eine automatisch generierte TEI-Taxonomie zur Einbindung als Authority File in Oxygen XML.
- **Typesense-Export:** `dist/json/synonyms-fpv.jsonl`. Eine flache Liste von Synonymgruppen für die Indizierung der digitalen Edition.

## Technischer Workflow (in Entwicklung)

Die Verarbeitung der Daten soll automatisiert über GitHub Actions erfolgen:

1. **Validierung:** Bei jedem Commit wird die `src/fpv.ttl` auf syntaktische Korrektheit (RDF/SKOS) geprüft.
2. **Transformation:** Python-Skripte (`scripts/`) generieren die XML- und JSON-Artefakte im Verzeichnis `dist/`.
3. **Publikation:** Das Vokabular wird über [SkoHub](https://skohub.io/) als statische Weboberfläche sowie als JSON-LD Schnittstelle unter `https://fraktionsprotokolle.github.io/fpv-skos/` bereitgestellt.
