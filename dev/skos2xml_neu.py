import os
from datetime import datetime
from rdflib import Graph, Namespace
from rdflib.namespace import SKOS, RDF
import xml.etree.ElementTree as ET
from xml.dom import minidom

# Namespaces definieren
TEI_NS = "http://www.tei-c.org/ns/1.0"
XML_NS = "http://www.w3.org/XML/1998/namespace"
EX = Namespace("https://voc.fraktionsprotokolle.de/id/")
FPV = Namespace("https://voc.fraktionsprotokolle.de/schema/")

# Namespaces für ElementTree registrieren
ET.register_namespace('', TEI_NS)


def format_datetime_de():
    """Erzeugt Datum + Uhrzeit im gewünschten deutschen Format."""
    now = datetime.now()
    months = [
        "Januar", "Februar", "März", "April", "Mai", "Juni",
        "Juli", "August", "September", "Oktober", "November", "Dezember"
    ]
    return f"{now.day}. {months[now.month - 1]} {now.year}, {now.strftime('%H:%M')} Uhr", now.strftime("%Y-%m-%d")


def create_tei_header():
    """Erzeugt den TEI-Header gemäß validierter Struktur."""

    display_date, iso_date = format_datetime_de()

    tei = ET.Element(f"{{{TEI_NS}}}TEI")

    header = ET.SubElement(tei, f"{{{TEI_NS}}}teiHeader")
    file_desc = ET.SubElement(header, f"{{{TEI_NS}}}fileDesc")

    # --- titleStmt ---
    title_stmt = ET.SubElement(file_desc, f"{{{TEI_NS}}}titleStmt")
    title = ET.SubElement(title_stmt, f"{{{TEI_NS}}}title")
    title.text = "FPV - Kontrolliertes Vokabular der Edition Fraktionsprotokolle.de"

    # --- publicationStmt ---
    pub_stmt = ET.SubElement(file_desc, f"{{{TEI_NS}}}publicationStmt")

    publisher = ET.SubElement(pub_stmt, f"{{{TEI_NS}}}publisher")
    publisher.text = "Kommission für Geschichte des Parlamentarismus und der politischen Parteien e. V. (KGParl)"

    date_el = ET.SubElement(pub_stmt, f"{{{TEI_NS}}}date")
    date_el.set("when", iso_date)
    date_el.text = display_date

    availability = ET.SubElement(pub_stmt, f"{{{TEI_NS}}}availability")

    licence = ET.SubElement(availability, f"{{{TEI_NS}}}licence")
    licence.set("target", "https://creativecommons.org/licenses/by/4.0/")
    licence.text = "Creative Commons Attribution 4.0 International (CC BY 4.0)"

    # --- sourceDesc ---
    src_desc = ET.SubElement(file_desc, f"{{{TEI_NS}}}sourceDesc")
    p_src = ET.SubElement(src_desc, f"{{{TEI_NS}}}p")
    p_src.text = "XML-Schlagwortliste automatisch erzeugt aus https://github.com/Fraktionsprotokolle-de/fpv-skos/blob/main/src/fpv.ttl"

    # --- text ---
    text = ET.SubElement(tei, f"{{{TEI_NS}}}text")
    body = ET.SubElement(text, f"{{{TEI_NS}}}body")
    p_body = ET.SubElement(body, f"{{{TEI_NS}}}p")
    p_body.text = "Diese Datei wird ausschließlich automatisch erzeugt!"

    return tei


def convert_ttl_to_xml(input_path, output_path):

    # RDF-Graph laden
    g = Graph()
    g.parse(input_path, format="turtle")

    # XML-Grundstruktur erstellen
    root = create_tei_header()
    stand_off = ET.SubElement(root, f"{{{TEI_NS}}}standOff")
    list_fpv = ET.SubElement(stand_off, f"{{{TEI_NS}}}list", type="fpv")

    # Alle skos:Concept extrahieren (Dokumentations-Konzepte ausschließen)
    concepts = []
    for s in g.subjects(RDF.type, SKOS.Concept):
        if "entityTypeNote" in str(s):
            continue
        concepts.append(s)

    concepts = sorted(concepts)

    for concept in concepts:

        local_id = str(concept).split('/')[-1]

        item = ET.SubElement(list_fpv, f"{{{TEI_NS}}}item")
        item.set(f"{{{XML_NS}}}id", local_id)

        # prefLabel
        for label in g.objects(concept, SKOS.prefLabel):
            term = ET.SubElement(item, f"{{{TEI_NS}}}term", type="pref")
            term.set(
                f"{{{XML_NS}}}lang",
                label.language if label.language else "de"
            )
            term.text = str(label)

        # altLabel
        for label in g.objects(concept, SKOS.altLabel):
            term = ET.SubElement(item, f"{{{TEI_NS}}}term", type="alt")
            term.set(
                f"{{{XML_NS}}}lang",
                label.language if label.language else "de"
            )
            term.text = str(label)

        # skos:note → TEI note type="definition"
        for note_literal in g.objects(concept, SKOS.note):
            note_el = ET.SubElement(item, f"{{{TEI_NS}}}note", type="definition")
            if note_literal.language:
                note_el.set(f"{{{XML_NS}}}lang", note_literal.language)
            else:
                note_el.set(f"{{{XML_NS}}}lang", "de")
            note_el.text = str(note_literal)

        # entityType (skos:notation)
        for notation in g.objects(concept, SKOS.notation):
            note = ET.SubElement(item, f"{{{TEI_NS}}}note", type="entityType")
            note.text = str(notation)

        # exactMatch
        for match in g.objects(concept, SKOS.exactMatch):
            if str(match) != "/":
                ET.SubElement(
                    item,
                    f"{{{TEI_NS}}}ref",
                    type="exactMatch",
                    target=str(match)
                )

        # closeMatch
        for match in g.objects(concept, SKOS.closeMatch):
            ET.SubElement(
                item,
                f"{{{TEI_NS}}}ref",
                type="closeMatch",
                target=str(match)
            )

        # skos:related → TEI ref type="seeAlso"
        for related in sorted(g.objects(concept, SKOS.related)):
            related_id = str(related).split('/')[-1]
            ET.SubElement(
                item,
                f"{{{TEI_NS}}}ref",
                type="seeAlso",
                target=f"#{related_id}"
            )

    # XML formatieren
    xml_str = ET.tostring(root, encoding='utf-8')
    parsed_xml = minidom.parseString(xml_str)
    pretty_xml = parsed_xml.toprettyxml(indent="\t", encoding="utf-8")

    # Speichern
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "wb") as f:
        f.write(pretty_xml)


if __name__ == "__main__":

    input_file = "src/fpv.ttl"
    output_file = "dist/xml/tei-fpv.xml"

    if os.path.exists(input_file):
        convert_ttl_to_xml(input_file, output_file)
        print(f"Konvertierung abgeschlossen: {output_file}")
    else:
        print(f"Fehler: {input_file} nicht gefunden.")