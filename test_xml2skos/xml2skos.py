import os
import logging
from urllib.parse import urlparse
from lxml import etree
from rdflib import Graph, Literal, RDF, URIRef, Namespace
from rdflib.namespace import SKOS

# Konfiguration der Pfade und Basis-URIs
INPUT_FILE = 'test_xml2skos/2026-02-02_Organisationen.xml'
OUTPUT_FILE = 'src/fpv.ttl'
# Basis-URI fuer Konzepte gemäss Vorgabe
BASE_URI = "https://voc.fraktionsprotokolle.de/concept/"

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

# Namensraum-Definitionen
XML_NS = 'http://www.w3.org/XML/1998/namespace'
TEI_NS = 'http://www.tei-c.org/ns/1.0'

def is_valid_uri(text):
    """Prüft, ob eine Zeichenfolge eine valide absolute URL ist."""
    if not text:
        return False
    text = text.strip()
    try:
        p = urlparse(text)
        return p.scheme in ("http", "https") and bool(p.netloc)
    except Exception:
        return False

def convert():
    """Transformiert TEI-XML Organisationen in SKOS-Turtle."""
    if not os.path.exists(INPUT_FILE):
        logger.error('Eingabedatei nicht gefunden: %s', INPUT_FILE)
        return

    # Sicherstellen, dass das Zielverzeichnis existiert
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)

    # XML-Parsing mit lxml
    parser = etree.XMLParser(remove_comments=True, recover=True)
    try:
        tree = etree.parse(INPUT_FILE, parser=parser)
    except Exception as e:
        logger.error('Fehler beim Parsen der XML-Datei: %s', e)
        return

    ns = {'tei': TEI_NS, 'xml': XML_NS}
    g = Graph()
    
    # Namespaces binden
    EX = Namespace(BASE_URI)
    g.bind("ex", EX)
    g.bind("skos", SKOS)

    organizations = tree.xpath('//tei:org', namespaces=ns)
    logger.info('%d Organisationen werden verarbeitet.', len(organizations))

    for org in organizations:
        # Extraktion der xml:id
        org_id = org.get('{%s}id' % XML_NS)
        if not org_id:
            # Fallback für lxml-Attributzugriff ohne Namespace-Key
            ids = org.xpath('./@xml:id', namespaces={'xml': XML_NS})
            org_id = ids[0] if ids else None
        
        if not org_id:
            continue

        # Subjekt-URI erstellen
        subject = URIRef(EX[org_id])
        
        # Grundtypisierung
        g.add((subject, RDF.type, SKOS.Concept))

        # 1. Bevorzugtes Label (skos:prefLabel)
        pref_names = org.xpath('./tei:orgName[@full="yes"]/text()', namespaces=ns)
        if pref_names:
            name_text = pref_names[0].strip()
            if name_text:
                g.add((subject, SKOS.prefLabel, Literal(name_text, lang="de")))

        # 2. Alternatives Label (skos:altLabel)
        alt_names = org.xpath('./tei:orgName[@full="abb"]/text()', namespaces=ns)
        if alt_names:
            alt_text = alt_names[0].strip()
            # Filterung von Leerzeichen und Platzhaltern
            if alt_text and alt_text not in ["", "/", "–"]:
                g.add((subject, SKOS.altLabel, Literal(alt_text, lang="de")))

        # 3. Klassifikation (@role -> skos:note)
        role = org.get('role')
        if role:
            g.add((subject, SKOS.note, Literal(role.strip(), lang="de")))

        # 4. Externe Identifikatoren
        idnos = org.xpath('./tei:idno', namespaces=ns)
        for idno in idnos:
            val = (idno.text or "").strip()
            if not val or not is_valid_uri(val):
                continue
            
            ref_uri = URIRef(val)
            id_type = (idno.get('type') or "").lower()
            
            if id_type in ["gnd", "viaf"]:
                g.add((subject, SKOS.exactMatch, ref_uri))
            elif id_type == "wikipedia":
                g.add((subject, SKOS.closeMatch, ref_uri))

    # Serialisierung als Turtle
    try:
        # rdflib sortiert Prädikate standardmäßig alphabetisch.
        # prefLabel (p) folgt auf altLabel (a). Für eine striktere Sortierung 
        # müsste ein spezialisierter Serializer genutzt werden.
        data = g.serialize(format='turtle', encoding='utf-8')
        with open(OUTPUT_FILE, 'wb') as f:
            f.write(data)
        logger.info('Konversion erfolgreich. Datei erstellt: %s', OUTPUT_FILE)
    except Exception as e:
        logger.error('Fehler bei der Serialisierung: %s', e)

if __name__ == "__main__":
    convert()