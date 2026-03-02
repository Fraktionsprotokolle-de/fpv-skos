import json
import re
from rdflib import Graph
from rdflib.namespace import SKOS
from rdflib.term import Literal

TTL_FILE = "src/fpv.ttl"
OUT_FILE = "dist/json/synonyms-fpv.jsonl"

# Diese Tokens sollen niemals als Synonyme auftauchen
BLACKLIST = {"pol", "com", "soc", "news", "topic", "law", "org"}

def uri_to_id(uri: str) -> str:
    last = uri.rstrip("/").split("/")[-1]
    return re.sub(r"[^A-Za-z0-9_-]", "-", last)

def clean_label(label: str) -> str:
    return label.strip()

g = Graph()
g.parse(TTL_FILE, format="turtle")

count = 0

with open(OUT_FILE, "w", encoding="utf-8") as out:
    for concept in g.subjects(predicate=SKOS.prefLabel):

        labels = set()

        # prefLabel
        for obj in g.objects(concept, SKOS.prefLabel):
            if isinstance(obj, Literal):
                labels.add(clean_label(str(obj)))

        # altLabel
        for obj in g.objects(concept, SKOS.altLabel):
            if isinstance(obj, Literal):
                labels.add(clean_label(str(obj)))

        # Artefakte entfernen
        labels = {
            l for l in labels
            if l.lower() not in BLACKLIST
            and len(l) > 1
        }

        if len(labels) < 2:
            continue

        item = {
            "id": uri_to_id(str(concept)),
            "synonyms": sorted(labels)
        }

        out.write(json.dumps(item, ensure_ascii=False) + "\n")
        count += 1

print(f"Wrote {count} synonym sets to {OUT_FILE}")