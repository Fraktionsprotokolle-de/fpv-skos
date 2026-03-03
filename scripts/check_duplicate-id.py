import sys
from pathlib import Path
from rdflib import Graph, RDF, Namespace

# -------------------------------
# Pfade robust relativ bestimmen
# -------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
TTL_PATH = REPO_ROOT / "src" / "fpv.ttl"

if not TTL_PATH.exists():
    print(f"ERROR: Turtle file not found at {TTL_PATH}")
    sys.exit(1)

print(f"Validating file: {TTL_PATH}")

# -------------------------------
# RDF einlesen
# -------------------------------

g = Graph()

try:
    g.parse(TTL_PATH, format="turtle")
except Exception as e:
    print("RDF parsing error:")
    print(e)
    sys.exit(1)

# -------------------------------
# Duplicate Concept Check
# -------------------------------

SKOS = Namespace("http://www.w3.org/2004/02/skos/core#")

concept_counts = {}

for subject in g.subjects(RDF.type, SKOS.Concept):
    concept_counts[subject] = concept_counts.get(subject, 0) + 1

duplicates = [uri for uri, count in concept_counts.items() if count > 1]

if duplicates:
    print("\n❌ Duplicate skos:Concept definitions detected:\n")
    for uri in duplicates:
        print(uri)
    sys.exit(1)
else:
    print("\n✅ No duplicate skos:Concept definitions found.")