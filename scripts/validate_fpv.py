import sys
from pathlib import Path
from rdflib import Graph, RDF, Namespace, Literal

# --------------------------------------------------
# Pfade robust relativ bestimmen
# --------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
TTL_PATH = REPO_ROOT / "src" / "fpv.ttl"

if not TTL_PATH.exists():
    print(f"ERROR: Turtle file not found at {TTL_PATH}")
    sys.exit(1)

print(f"Validating file: {TTL_PATH}\n")

# --------------------------------------------------
# RDF einlesen
# --------------------------------------------------

g = Graph()

try:
    g.parse(TTL_PATH, format="turtle")
except Exception as e:
    print("❌ RDF parsing error:")
    print(e)
    sys.exit(1)

SKOS = Namespace("http://www.w3.org/2004/02/skos/core#")
FPV = Namespace("https://voc.fraktionsprotokolle.de/schema/")

allowed_entity_types = {"org", "com", "news", "topic", "law", "pol"}

errors = []

# --------------------------------------------------
# 1️⃣ Duplicate Concept definitions
# --------------------------------------------------

concept_counts = {}

for subject in g.subjects(RDF.type, SKOS.Concept):
    concept_counts[subject] = concept_counts.get(subject, 0) + 1

for uri, count in concept_counts.items():
    if count > 1:
        errors.append(f"Duplicate skos:Concept definition: {uri}")

# --------------------------------------------------
# 2️⃣ PrefLabel checks
# --------------------------------------------------

for concept in g.subjects(RDF.type, SKOS.Concept):

    pref_de = [
        label for label in g.objects(concept, SKOS.prefLabel)
        if isinstance(label, Literal) and label.language == "de"
    ]

    if len(pref_de) == 0:
        errors.append(f"Missing skos:prefLabel@de: {concept}")

    if len(pref_de) > 1:
        errors.append(f"Multiple skos:prefLabel@de: {concept}")

# --------------------------------------------------
# 3️⃣ Notation checks
# --------------------------------------------------

for concept in g.subjects(RDF.type, SKOS.Concept):

    notations = list(g.objects(concept, SKOS.notation))

    if len(notations) == 0:
        errors.append(f"Missing skos:notation: {concept}")
        continue

    for n in notations:
        if not isinstance(n, Literal):
            errors.append(f"Invalid notation (not literal): {concept}")
            continue

        if n.datatype != FPV.entityType:
            errors.append(f"Invalid notation datatype: {concept}")

        if str(n) not in allowed_entity_types:
            errors.append(f"Invalid entityType code '{n}' in {concept}")

# --------------------------------------------------
# Ergebnis
# --------------------------------------------------

if errors:
    print("❌ VALIDATION FAILED\n")
    for e in errors:
        print(" -", e)
    sys.exit(1)
else:
    print("✅ Validation successful. No structural errors found.")