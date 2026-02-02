import os
import logging
from urllib.parse import urlparse, quote
from lxml import etree
from rdflib import Graph, Literal, URIRef, Namespace, RDF
from rdflib.namespace import SKOS, DCTERMS

# Konfiguration
INPUT_FILE = 'test_xml2skos/2026-02-02_Organisationen.xml'
OUTPUT_FILE = 'src/fpv.ttl'
BASE_URI = "https://vokabular.fraktionsprotokolle.de/"

# Mapping für Rollen zur Konsistenzprüfung
ROLE_MAP = {
    "com": "Unternehmen",
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
    
    # Bindings (replace=True statt dem ungültigen override=True)
    g.bind("skos", SKOS)
    g.bind("rdf", RDF)
    g.bind("org", ORG_NS, replace=True)
    g.bind("coll", COLL_NS, replace=True)
    g.bind("dct", DCTERMS)

    # 1. Concept Scheme initialisieren
    scheme_uri = URIRef(BASE_URI + "scheme/fpv")
    g.add((scheme_uri, RDF.type, SKOS.ConceptScheme))
    g.add((scheme_uri, SKOS.prefLabel, Literal("Organisationen der Fraktionsprotokolle", lang="de")))
    g.add((scheme_uri, DCTERMS.description, Literal("SKOS-Vokabular generiert aus TEI-Organisationenverzeichnis.", lang="de")))

    collections = {}
    organizations = tree.xpath('//tei:org', namespaces=ns)
    logger.info('%d Organisationen im XML gefunden.', len(organizations))

    for org in organizations:
        # ID extrahieren (xml:id)
        org_id = org.get('{%s}id' % XML_NS)
        if not org_id:
            continue

        # Lokalen Teil sicher in eine IRI-kodierte Form bringen
        safe_local = quote(org_id, safe='')
        subject = URIRef(str(ORG_NS) + safe_local)
        
        # Grunddaten des Konzepts
        g.add((subject, RDF.type, SKOS.Concept))
        g.add((subject, SKOS.inScheme, scheme_uri))
        g.add((subject, SKOS.note, Literal("tbd", lang="de")))

        # Rollen & Collections
        role_attr = org.get('role')
        if role_attr:
            role_key = role_attr.lower().strip()
            display_name = ROLE_MAP.get(role_key, role_key.capitalize())
            
            if role_key not in collections:
                coll_uri = URIRef(str(COLL_NS) + quote(role_key, safe=''))
                g.add((coll_uri, RDF.type, SKOS.Collection))
                g.add((coll_uri, SKOS.prefLabel, Literal(display_name, lang="de")))
                # Collection in das Scheme setzen (semantisch sinnvoll)
                g.add((coll_uri, SKOS.inScheme, scheme_uri))
                collections[role_key] = coll_uri
            
            g.add((collections[role_key], SKOS.member, subject))

        # Namen (Labels)
        names = org.xpath('./tei:orgName', namespaces=ns)
        preflabel_set = False
        first_name_text = None
        for name in names:
            full_type = name.get('full')
            text = (name.text or "").strip()
            if not text or text in ["/", "–"]:
                continue

            if first_name_text is None:
                first_name_text = text  # fallback

            if full_type == "yes":
                g.add((subject, SKOS.prefLabel, Literal(text, lang="de")))
                preflabel_set = True
            elif full_type == "abb":
                g.add((subject, SKOS.altLabel, Literal(text, lang="de")))
            else:
                # unknown 'full' attribute: treat as altLabel unless no prefLabel exists
                if not preflabel_set:
                    g.add((subject, SKOS.prefLabel, Literal(text, lang="de")))
                    preflabel_set = True
                else:
                    g.add((subject, SKOS.altLabel, Literal(text, lang="de")))

        # Fallback: falls kein prefLabel gesetzt wurde, nutze den ersten Namenstext
        if not preflabel_set and first_name_text:
            g.add((subject, SKOS.prefLabel, Literal(first_name_text, lang="de")))

        # Identifikatoren & Matches
        idnos = org.xpath('./tei:idno', namespaces=ns)
        for idno in idnos:
            val = (idno.text or "").strip()
            if not val:
                continue

            # Falls eine bare GND/VIAF-ID vorkommt, kann man hier evtl. Canonical-URIs erzeugen.
            # Der Code hier akzeptiert nur gültige http(s)-URIs als Matches.
            if not is_valid_uri(val):
                continue
            
            match_uri = URIRef(val)
            id_type = (idno.get('type') or "").lower()
            
            if id_type in ["gnd", "viaf"]:
                g.add((subject, SKOS.exactMatch, match_uri))
            elif id_type == "wikipedia":
                g.add((subject, SKOS.closeMatch, match_uri))
            else:
                # generischer closeMatch für unbekannte Typen, falls erwünscht
                g.add((subject, SKOS.closeMatch, match_uri))

    # Serialisierung
    try:
        data = g.serialize(format='turtle')  # liefert einen str
        with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
            f.write(data)
        logger.info('SKOS-Datei erfolgreich geschrieben: %s (%d Tripel)', OUTPUT_FILE, len(g))
    except Exception as e:
        logger.error('Fehler bei der Serialisierung: %s', e)

if __name__ == "__main__":
    convert()