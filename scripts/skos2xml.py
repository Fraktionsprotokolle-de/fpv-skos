import os
from rdflib import Graph, Namespace, URIRef
from rdflib.namespace import SKOS, RDF, RDFS
import xml.etree.ElementTree as ET
from xml.dom import minidom

# Namespaces definieren
TEI_NS = "http://www.tei-c.org/ns/1.0"
XML_NS = "http://www.w3.org/XML/1998/namespace"
EX = Namespace("https://voc.fraktionsprotokolle.de/id/")
FPV = Namespace("https://voc.fraktionsprotokolle.de/schema/")

# Namespaces für ElementTree registrieren
ET.register_namespace('', TEI_NS)

def create_tei_header():
    """Erzeugt den statischen TEI-Header gemäß Vorlage."""
    tei = ET.Element(f"{{{TEI_NS}}}TEI")
    header = ET.SubElement(tei, f"{{{TEI_NS}}}teiHeader")
    file_desc = ET.SubElement(header, f"{{{TEI_NS}}}fileDesc")
    
    title_stmt = ET.SubElement(file_desc, f"{{{TEI_NS}}}titleStmt")
    title = ET.SubElement(title_stmt, f"{{{TEI_NS}}}title")
    title.text = "FPV – Kontrolliertes Vokabular"
    
    pub_stmt = ET.SubElement(file_desc, f"{{{TEI_NS}}}publicationStmt")
    p_pub = ET.SubElement(pub_stmt, f"{{{TEI_NS}}}p")
    p_pub.text = "Generiert aus fpv.ttl"
    
    src_desc = ET.SubElement(file_desc, f"{{{TEI_NS}}}sourceDesc")
    p_src = ET.SubElement(src_desc, f"{{{TEI_NS}}}p")
    p_src.text = "Single Source of Truth: SKOS TTL"
    
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
    
    # Alle skos:Concept extrahieren (außer Dokumentations-Items)
    concepts = []
    for s in g.subjects(RDF.type, SKOS.Concept):
        # Dokumentations-Konzepte wie entityTypeNote ausschließen
        if "entityTypeNote" in str(s):
            continue
        concepts.append(s)
    
    # Sortierung für konsistente Ausgabe
    concepts.sort()
    
    for concept in concepts:
        # Lokale ID aus URI extrahieren
        local_id = str(concept).split('/')[-1]
        
        item = ET.SubElement(list_fpv, f"{{{TEI_NS}}}item")
        item.set(f"{{{XML_NS}}}id", local_id)
        
        # prefLabel
        for label in g.objects(concept, SKOS.prefLabel):
            term = ET.SubElement(item, f"{{{TEI_NS}}}term", type="pref")
            term.set(f"{{{XML_NS}}}lang", label.language if label.language else "de")
            term.text = str(label)
            
        # altLabel
        for label in g.objects(concept, SKOS.altLabel):
            term = ET.SubElement(item, f"{{{TEI_NS}}}term", type="alt")
            term.set(f"{{{XML_NS}}}lang", label.language if label.language else "de")
            term.text = str(label)
            
        # entityType (skos:notation)
        for notation in g.objects(concept, SKOS.notation):
            note = ET.SubElement(item, f"{{{TEI_NS}}}note", type="entityType")
            note.text = str(notation)
            
        # exactMatch
        for match in g.objects(concept, SKOS.exactMatch):
            if str(match) != "/": # Leere Platzhalter ignorieren
                ET.SubElement(item, f"{{{TEI_NS}}}ref", type="exactMatch", target=str(match))
            
        # closeMatch
        for match in g.objects(concept, SKOS.closeMatch):
            ET.SubElement(item, f"{{{TEI_NS}}}ref", type="closeMatch", target=str(match))

    # XML formatieren und speichern
    xml_str = ET.tostring(root, encoding='utf-8')
    parsed_xml = minidom.parseString(xml_str)
    pretty_xml = parsed_xml.toprettyxml(indent="\t", encoding="utf-8")
    
    with open(output_path, "wb") as f:
        f.write(pretty_xml)

if __name__ == "__main__":
    input_file = "fpv.ttl"
    output_file = "Termliste.xml"
    
    if os.path.exists(input_file):
        convert_ttl_to_xml(input_file, output_file)
        print(f"Konvertierung abgeschlossen: {output_file}")
    else:
        print(f"Fehler: {input_file} nicht gefunden.")