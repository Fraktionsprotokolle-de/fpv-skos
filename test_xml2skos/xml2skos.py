import os
from lxml import etree
from rdflib import Graph, Literal, RDF, URIRef, Namespace
from rdflib.namespace import SKOS

# Konfiguration
INPUT_FILE = 'test_xml2skos/2026-02-02_Organisationen.xml'
OUTPUT_FILE = 'src/fpv.ttl'
BASE_URI = "[https://vokabular.fraktionsprotokolle.de/](https://vokabular.fraktionsprotokolle.de/)"

ROLE_MAP = {
    "com": "Unternehmen",
    "pol": "Politische Organisationen",
    "soc": "Gesellschaftliche Organisationen",
    "news": "Medien"
}

def is_valid_uri(text):
    if not text:
        return False
    text = text.strip()
    return text.startswith("http")

def convert():
    if not os.path.exists(INPUT_FILE):
        return

    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    
    parser = etree.XMLParser(remove_comments=True)
    tree = etree.parse(INPUT_FILE, parser=parser)
    ns = {'tei': '[http://www.tei-c.org/ns/1.0](http://www.tei-c.org/ns/1.0)'}

    g = Graph()
    ORG_NS = Namespace(BASE_URI + "org/")
    COLL_NS = Namespace(BASE_URI + "collection/")
    g.bind("skos", SKOS)
    g.bind("org", ORG_NS)
    g.bind("coll", COLL_NS)

    collections = {}
    organizations = tree.xpath('//tei:org', namespaces=ns)

    for org in organizations:
        org_id = org.xpath('./@xml:id', namespaces=ns)
        if not org_id:
            continue
        
        subject = URIRef(ORG_NS[org_id[0]])
        g.add((subject, RDF.type, SKOS.Concept))
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
            g.add((subject, SKOS.prefLabel, Literal(pref[0].strip(), lang="de")))

        # AltLabel
        alt = org.xpath('./tei:orgName[@full="abb"]/text()', namespaces=ns)
        if alt and alt[0].strip() not in ["", "/", "–"]:
            g.add((subject, SKOS.altLabel, Literal(alt[0].strip(), lang="de")))

        # Matches
        for idno in org.xpath('./tei:idno', namespaces=ns):
            val = idno.text.strip() if idno.text else ""
            if is_valid_uri(val):
                u = URIRef(val)
                itype = idno.get('type').lower()
                if itype in ["gnd", "viaf"]:
                    g.add((subject, SKOS.exactMatch, u))
                elif itype == "wikipedia":
                    g.add((subject, SKOS.closeMatch, u))

    g.serialize(destination=OUTPUT_FILE, format='turtle')

if __name__ == "__main__":
    convert()
