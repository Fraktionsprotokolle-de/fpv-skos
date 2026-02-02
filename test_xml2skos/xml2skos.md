# xml2skos

Dokumentation des temporären Workflow zur Erzeugung einer SKOS-Datei zur Test- und Entwicklungszwecken

- `2026-02-02_Organisationen.xml` – Kopie des TEI-Authority-Files für Organisationen aus dem Arbeistsverzeichnis (intern) der Edition.
- `xml2skos.py` – Python-Script zur automatisierten Erzeugung/Konvertierung des SKOS-Voabulars (Turtle) `fpv.ttl` in `\src` aus `2026-02-02_Organisationen.xml`

Jede Veränderung von `2026-02-02_Organisationen.xml` stößt via Github-Actions das Script zur Konvertierung an.

# Mapping-Dokumentation: TEI-XML zu SKOS

Diese Dokumentation beschreibt die Transformation der Organisationsdaten aus dem TEI-XML-Format in ein SKOS-basiertes kontrolliertes Vokabular.

## Basis-Konfiguration

| **Parameter**           | **Wert**                                      |
| ----------------------- | --------------------------------------------- |
| **Basis-URI (Konzept)** | `https://voc.fraktionsprotokolle.de/concept/` |
| **RDF-Präfix**          | `ex:`                                         |
| **Standard-Sprachtag**  | `@de`                                         |

## Element-Mapping

| **TEI-XML Element / Attribut** | **SKOS / RDF Eigenschaft** | **Bemerkungen**                                              |
| ------------------------------ | -------------------------- | ------------------------------------------------------------ |
| `tei:org`                      | `skos:Concept`             | Jedes `<org>`-Element wird als ein individuelles Konzept instanziiert. |
| `tei:org/@xml:id`              | —                          | Dient als lokaler Identifikator für die Bildung der Subjekt-URI (`ex:{xml:id}`). Ggf. Normalisierung, falls in der ID Sonderzeichen enthalten sind. |
| `tei:orgName[@full="yes"]`     | `skos:prefLabel`           | Bevorzugte Bezeichnung der Organisation.                     |
| `tei:orgName[@full="abb"]`     | `skos:altLabel`            | Abkürzung oder alternative Bezeichnung. Wird ignoriert, wenn der Inhalt `/`, `–` oder leer ist. |
| `tei:org/@role`                | `skos:note`                | Der Attributwert (z. B. `pol`, `news`, `com`) wird direkt als Notiz übernommen. |
| `tei:idno[@type="gnd"]`        | `skos:exactMatch`          | Verknüpfung zur Gemeinsamen Normdatei (GND), sofern eine valide URI vorliegt. |
| `tei:idno[@type="viaf"]`       | `skos:exactMatch`          | Verknüpfung zu VIAF (Virtual International Authority File).  |
| `tei:idno[@type="wikipedia"]`  | `skos:closeMatch`          | Verknüpfung zum entsprechenden Wikipedia-Artikel.            |

## Verarbeitungshinweise

1. **Validierung:** Externe Identifikatoren in `<idno>` werden nur verarbeitet, wenn sie eine valide absolute URI (beginnend mit `http` oder `https`) enthalten.
2. **Datenbereinigung:** Führende und folgende Leerzeichen in den Textknoten werden während der Konvertierung entfernt.
3. **Struktur:** Jedes Konzept wird als eigenständiger Block im Turtle-Format serialisiert. Die alphabetische Sortierung der Prädikate durch die zugrunde liegende Bibliothek `rdflib` ist technisch bedingt; die semantische Priorisierung von `skos:prefLabel` bleibt erhalten.