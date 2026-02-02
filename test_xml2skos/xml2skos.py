import os
import logging
from urllib.parse import urlparse
from lxml import etree
from rdflib import Graph, Literal, RDF, URIRef, Namespace
from rdflib.namespace import SKOS, DCTERMS, RDF as RDF_NS

# Konfiguration
INPUT_FILE = 'test_xml2skos/2026-02-02_Organisationen.xml'
OUTPUT_FILE = 'src/fpv.ttl'
BASE_URI = "https://vokabular.fraktionsprotokolle.de/"

# Mapping für Rollen zur Konsistenzprüfung
ROLE_MAP = {
    "com": "Unternehmen",
    "comm": "Unternehmen",
    "pol": "Politische Organisationen",
    "soc": "Gesellschaftliche Organisationen",
    "news": "Medien"
}

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

XML_NS = 'http://www.w3.org/XML/1998/namespace'
TEI_NS = 'http://www.tei-c.org/ns/1.0'

def is_valid_uri(text):
    if not text:
        return False
    text = text.strip()
    try:
        p = urlparse(text)
        return p.scheme in ("http", "https") and bool(p.netloc)
    except Exception:
        return False

def convert():
    if not os.path.exists(INPUT_FILE):
        logger.error('Eingabedatei existiert nicht: %s', INPUT_FILE)
        return

    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)

    # Parser mit Fehlerkorrektur für unsauberes XML
    parser = etree.XMLParser(remove_comments=True, recover=True)
    try:
        tree = etree.parse(INPUT_FILE, parser=parser)
    except Exception as e:
        logger.error('XML-Parsing fehlgeschlagen: %s', e)
        return

    ns = {'tei': TEI_NS, 'xml': XML_NS}
    
    g = Graph()
    
    # Namespaces definieren
    ORG_NS = Namespace(BASE_URI + "org/")
    COLL_NS = Namespace(BASE_URI + "collection/")
    SCHEME_NS = Namespace(BASE_URI + "scheme/")
    
    # Bindings erzwingen (override=True verhindert org1, org2)
    g.bind("skos", SKOS)
    g.bind("org", ORG_NS, override=True)
    g.bind("coll", COLL_NS, override=True)
    g.bind("dct", DCTERMS)

    # 1. Concept Scheme initialisieren
    scheme_uri = URIRef(BASE_URI + "scheme/fpv")
    g.add((scheme_uri, RDF_NS.type, SKOS.ConceptScheme))
    g.add((scheme_uri, SKOS.prefLabel, Literal("Organisationen der Fraktionsprotokolle", lang="de")))
    g.add((scheme_uri, DCTERMS.description, Literal("SKOS-Vokabular generiert aus TEI-Organisationenverzeichnis.", lang="de")))

    collections = {}
    organizations = tree.xpath('//tei:org', namespaces=ns)
    logger.info('%d Organisationen im XML gefunden.', len(organizations))

    for org in organizations:
        # ID extrahieren
        org_id = org.get('{%s}id' % XML_NS)
        if not org_id:
            continue

        # URI bilden
        subject = URIRef(ORG_NS[org_id])
        
        # Grunddaten des Konzepts
        g.add((subject, RDF_NS.type, SKOS.Concept))
        g.add((subject, SKOS.inScheme, scheme_uri))
        g.add((subject, SKOS.note, Literal("tbd", lang="de")))

        # Rollen & Collections
        role_attr = org.get('role')
        if role_attr:
            role_key = role_attr.lower().strip()
            display_name = ROLE_MAP.get(role_key, role_key.capitalize())
            
            if role_key not in collections:
                coll_uri = URIRef(COLL_NS[role_key])
                g.add((coll_uri, RDF_NS.type, SKOS.Collection))
                g.add((coll_uri, SKOS.prefLabel, Literal(display_name, lang="de")))
                collections[role_key] = coll_uri
            
            g.add((collections[role_key], SKOS.member, subject))

        # Namen (Labels)
        names = org.xpath('./tei:orgName', namespaces=ns)
        for name in names:
            full_type = name.get('full')
            text = (name.text or "").strip()
            if not text or text in ["/", "–"]:
                continue
            
            if full_type == "yes":
                g.add((subject, SKOS.prefLabel, Literal(text, lang="de")))
            elif full_type == "abb":
                g.add((subject, SKOS.altLabel, Literal(text, lang="de")))

        # Identifikatoren & Matches
        idnos = org.xpath('./tei:idno', namespaces=ns)
        for idno in idnos:
            val = (idno.text or "").strip()
            if not val or not is_valid_uri(val):
                continue
            
            match_uri = URIRef(val)
            id_type = (idno.get('type') or "").lower()
            
            if id_type in ["gnd", "viaf"]:
                g.add((subject, SKOS.exactMatch, match_uri))
            elif id_type == "wikipedia":
                g.add((subject, SKOS.closeMatch, match_uri))

    # Serialisierung
    try:
        # Wir nutzen 'long' Format für bessere Lesbarkeit und explizite Kodierung
        data = g.serialize(format='turtle', encoding='utf-8')
        with open(OUTPUT_FILE, 'wb') as f:
            f.write(data)
        logger.info('SKOS-Datei erfolgreich geschrieben: %s (%d Tripel)', OUTPUT_FILE, len(g))
    except Exception as e:
        logger.error('Fehler bei der Serialisierung: %s', e)

if __name__ == "__main__":
    convert()