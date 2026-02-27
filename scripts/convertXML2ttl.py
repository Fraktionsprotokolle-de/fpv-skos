import sys
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape

# --- Namespaces ---
NS = {
    "tei": "http://www.tei-c.org/ns/1.0"
}

def get_text(elem):
    """Safely extract text and strip whitespace."""
    if elem is not None and elem.text:
        return elem.text.strip()
    return None

def convert_org_to_turtle(org_elem):
    # xml:id (TEI namespace-aware)
    xml_id = org_elem.get("{http://www.w3.org/XML/1998/namespace}id")
    role = org_elem.get("role")

    if not xml_id:
        raise ValueError("org element without xml:id")

    # prefLabel
    pref_label_elem = org_elem.find("tei:orgName[@full='yes']", NS)
    pref_label = get_text(pref_label_elem)

    # altLabel
    alt_label_elem = org_elem.find("tei:orgName[@full='abb']", NS)
    alt_label = get_text(alt_label_elem)

    # GND
    gnd_elem = org_elem.find("tei:idno[@type='gnd']", NS)
    gnd = get_text(gnd_elem)

    # Wikipedia
    wiki_elem = org_elem.find("tei:idno[@type='wikipedia']", NS)
    wiki = get_text(wiki_elem)

    # --- Build Turtle ---
    lines = []
    lines.append(f"ex:{xml_id} a skos:Concept ;")

    if pref_label:
        lines.append(f'  skos:prefLabel "{escape(pref_label)}"@de ;')

    if alt_label:
        lines.append(f'  skos:altLabel "{escape(alt_label)}"@de ;')

    if role:
        lines.append(f'  skos:notation "{escape(role)}"^^ex:legacyCategory ;')

    if gnd:
        lines.append(f"  skos:exactMatch <{gnd}> ;")

    if wiki:
        lines.append(f"  skos:closeMatch <{wiki}> ;")

    # letzte Property mit Punkt abschließen
    lines.append('  skos:note "Erläuterungen können jetzt hier stehen."@de .')

    return "\n".join(lines)


def main(xml_input_path, ttl_output_path):
    tree = ET.parse(xml_input_path)
    root = tree.getroot()

    # Falls <org> direkt Root ist
    if root.tag.endswith("org"):
        org_elements = [root]
    else:
        org_elements = root.findall(".//tei:org", NS)

    ttl_blocks = []
    for org in org_elements:
        ttl_blocks.append(convert_org_to_turtle(org))

    with open(ttl_output_path, "w", encoding="utf-8") as f:
        f.write("\n\n".join(ttl_blocks))


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python convert_org_to_skos.py input.xml output.ttl")
        sys.exit(1)

    main(sys.argv[1], sys.argv[2])