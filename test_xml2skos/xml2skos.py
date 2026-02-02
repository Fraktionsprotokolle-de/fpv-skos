import os
import logging
from urllib.parse import urlparse
from lxml import etree
from rdflib import Graph, Literal, RDF, URIRef, Namespace
from rdflib.namespace import SKOS, DCTERMS

# Konfiguration
INPUT_FILE = 'test_xml2skos/2026-02-02_Organisationen.xml'
OUTPUT_FILE = 'src/fpv.ttl'
BASE_URI = "https://vokabular.fraktionsprotokolle.de/"

# Erweitertes Mapping zur Vermeidung von Dubletten/Fehlern
ROLE_MAP = {
    "com": "Unternehmen",
    "pol": "Politische Organisationen",
    "soc": "Gesellschaftliche Organisationen",
    "news": "Medien"
}

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

XML_NS = 'http://www.w3.org/XML/1998/namespace'

def is_valid_uri(text):
    if not text:
        return False
    text = text.strip()
    try:
        p = urlparse(text)
        return p.scheme in ("http", "https") and bool(p.netloc)
    except Exception:
        return False

def convert(input_file=INPUT_FILE, output_file=OUTPUT_FILE):
    if not os.path.exists(input_file):
        logger.warning('Input file does not exist: %s', input_file)
        return

    os.makedirs(os.path.dirname(output_file), exist_ok=True)

    parser = etree.XMLParser(remove_comments=True, recover=True)
    try:
        tree = etree.parse(input_file, parser=parser)
    except (etree.XMLSyntaxError, OSError) as e:
        logger.error('Failed to parse input XML: %s', e)
        return

    ns = {'tei': 'http://www.tei-c.org/ns/1.0'}
    
    g = Graph()
    # Definition der Namespaces
    ORG_NS = Namespace(BASE_URI + "org/")
    COLL_NS = Namespace(BASE_URI + "collection/")
    SCHEME_NS = Namespace(BASE_URI + "scheme/")
    
    g.bind("skos", SKOS)
    g.bind("org", ORG_NS)
    g.bind("coll", COLL_NS)
    g.bind("dct", DCTERMS)

    # Concept Scheme Initialisierung
    scheme_uri = URIRef(BASE_URI + "scheme/fpv")
    g.add((scheme_uri, RDF.type, SKOS.ConceptScheme))
    g.add((scheme_uri, SKOS.prefLabel, Literal("Organisationen der Fraktionsprotokolle", lang="de")))
    g.add((scheme_uri, DCTERMS.description, Literal("Automatisch generiertes SKOS-Vokabular aus TEI-Daten.", lang="de")))

    collections = {}
    organizations = tree.xpath('//tei:org', namespaces=ns)
    logger.info('Processing %d <org> elements', len(organizations))

    for org in organizations:
        org_id = org.get('{%s}id' % XML_NS)
        if not org_id:
            ids = org.xpath('./@xml:id', namespaces={'xml': XML_NS})
            org_id = ids[0] if ids else None
        
        if not org_id:
            continue

        # URI Bereinigung: IDs, die auf Punkte enden, verursachen Probleme in Turtle-Präfixen
        subject = URIRef(ORG_NS[org_id])
        
        g.add((subject, RDF.type, SKOS.Concept))
        g.add((subject, SKOS.inScheme, scheme_uri))
        g.add((subject, SKOS.note, Literal("tbd", lang="de")))

        # Role / Collection Handling
        role_key = org.get('role')
        if role_key:
            role_key = role_key.lower().strip()
            # Mapping auflösen oder Originalschlüssel verwenden
            display_label = ROLE_MAP.get(role_key, role_key)
            
            if role_key not in collections:
                coll_uri = URIRef(COLL_NS[role_key])
                g.add((coll_uri, RDF.type, SKOS.Collection))
                g.add((coll_uri, SKOS.prefLabel, Literal(display_label, lang="de")))
                collections[role_key] = coll_uri
            
            g.add((collections[role_key], SKOS.member, subject))

        # PrefLabel
        pref = org.xpath('./tei:orgName[@full="yes"]/text()', namespaces=ns)
        if pref:
            text = pref[0].strip()
            if text:
                g.add((subject, SKOS.prefLabel, Literal(text, lang="de")))

        # AltLabel
        alt = org.xpath('./tei:orgName[@full="abb"]/text()', namespaces=ns)
        if alt:
            alt_text = alt[0].strip()
            if alt_text and alt_text not in ["", "/", "–"]:
                g.add((subject, SKOS.altLabel, Literal(alt_text, lang="de")))

        # Matches (GND, VIAF, Wikipedia)
        for idno in org.xpath('./tei:idno', namespaces=ns):
            val = (idno.text or "").strip()
            if not val or not is_valid_uri(val):
                continue
            
            u = URIRef(val)
            itype = (idno.get('type') or "").lower()
            if itype in ["gnd", "viaf"]:
                g.add((subject, SKOS.exactMatch, u))
            elif itype == "wikipedia":
                g.add((subject, SKOS.closeMatch, u))

    try:
        # Serialisierung mit expliziter Sortierung für stabilere Diffs in Git
        g.serialize(destination=output_file, format='turtle', encoding='utf-8')
        logger.info('Successfully wrote SKOS to %s', output_file)
    except Exception as e:
        logger.error('Serialization failed: %s', e)

if __name__ == "__main__":
    convert()
