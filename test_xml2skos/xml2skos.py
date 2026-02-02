"""Fixed xml2skos.py: correct BASE_URI and TEI namespace, safer xml:id handling, improved URI validation, defensive checks and logging.
"""
import os
import logging
from urllib.parse import urlparse
from lxml import etree
from rdflib import Graph, Literal, RDF, URIRef, Namespace
from rdflib.namespace import SKOS

# Konfiguration
INPUT_FILE = 'test_xml2skos/2026-02-02_Organisationen.xml'
OUTPUT_FILE = 'src/fpv.ttl'
BASE_URI = "https://vokabular.fraktionsprotokolle.de/"

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
    except Exception:
        return False
    return p.scheme in ("http", "https") and bool(p.netloc)

def convert(input_file=INPUT_FILE, output_file=OUTPUT_FILE):
    if not os.path.exists(input_file):
        logger.warning('Input file does not exist: %s', input_file)
        return

    os.makedirs(os.path.dirname(output_file), exist_ok=True)

    parser = etree.XMLParser(remove_comments=True)
    try:
        tree = etree.parse(input_file, parser=parser)
    except (etree.XMLSyntaxError, OSError) as e:
        logger.error('Failed to parse input XML: %s', e)
        return

    ns = {'tei': 'http://www.tei-c.org/ns/1.0'}

    g = Graph()
    ORG_NS = Namespace(BASE_URI + "org/")
    COLL_NS = Namespace(BASE_URI + "collection/")
    g.bind("skos", SKOS)
    g.bind("org", ORG_NS)
    g.bind("coll", COLL_NS)

    collections = {}
    organizations = tree.xpath('//tei:org', namespaces=ns)
    logger.info('Found %d <org> elements', len(organizations))

    for org in organizations:
        # Try to get xml:id via the XML namespace, fallback to XPath attribute lookup
        org_id = org.get('{%s}id' % XML_NS)
        if not org_id:
            ids = org.xpath('./@xml:id', namespaces={'xml': XML_NS})
            org_id = ids[0] if ids else None
        if not org_id:
            logger.debug('Skipping <org> without xml:id')
            continue

        subject = URIRef(ORG_NS[org_id])
        g.add((subject, RDF.type, SKOS.Concept))
        # Add a note only if desired; keep placeholder
        g.add((subject, SKOS.note, Literal("tbd", lang="de")))

        role_key = org.get('role')
        if role_key:
            if role_key not in collections:
                coll_uri = URIRef(COLL_NS[role_key])
                g.add((coll_uri, RDF.type, SKOS.Collection))
                g.add((coll_uri, SKOS.prefLabel, Literal(ROLE_MAP.get(role_key, role_key), lang="de")))
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
            if alt_text not in ["", "/", "–"]:
                g.add((subject, SKOS.altLabel, Literal(alt_text, lang="de")))

        # Matches
        for idno in org.xpath('./tei:idno', namespaces=ns):
            val = idno.text.strip() if idno.text else ""
            if not val:
                continue
            if is_valid_uri(val):
                try:
                    u = URIRef(val)
                except Exception:
                    logger.debug('Skipping invalid URI in <idno>: %s', val)
                    continue
                itype_raw = idno.get('type') or ''
                itype = itype_raw.lower()
                if itype in ["gnd", "viaf"]:
                    g.add((subject, SKOS.exactMatch, u))
                elif itype == "wikipedia":
                    g.add((subject, SKOS.closeMatch, u))

    try:
        g.serialize(destination=output_file, format='turtle')
        logger.info('Wrote Turtle output to %s', output_file)
    except Exception as e:
        logger.error('Failed to serialize graph: %s', e)


if __name__ == "__main__":
    convert()
