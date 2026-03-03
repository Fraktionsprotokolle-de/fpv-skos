from pathlib import Path
from rdflib import Graph, RDF, Namespace, Literal
from collections import defaultdict

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent

TTL_PATH = REPO_ROOT / "src" / "fpv.ttl"
OUTPUT_DIR = REPO_ROOT / "docs"
OUTPUT_DIR.mkdir(exist_ok=True)

OUTPUT_FILE = OUTPUT_DIR / "index.html"

g = Graph()
g.parse(TTL_PATH, format="turtle")

SKOS = Namespace("http://www.w3.org/2004/02/skos/core#")

concepts = []

for concept in set(g.subjects(RDF.type, SKOS.Concept)):

    pref_label = None
    for label in g.objects(concept, SKOS.prefLabel):
        if isinstance(label, Literal) and label.language == "de":
            pref_label = str(label)
            break

    if not pref_label:
        continue

    alt_labels = [str(a) for a in g.objects(concept, SKOS.altLabel)]
    notation = next(g.objects(concept, SKOS.notation), None)
    notation_value = str(notation) if notation else ""

    concepts.append({
        "uri": str(concept),
        "pref": pref_label,
        "alts": alt_labels,
        "type": notation_value,
        "initial": pref_label[0].upper()
    })

# Alphabetisch sortieren
concepts = sorted(concepts, key=lambda x: x["pref"].lower())

# Alphabet-Index erzeugen
alphabet = sorted(set(c["initial"] for c in concepts if c["initial"].isalpha()))

# ------------------------------------
# HTML erzeugen
# ------------------------------------

html = f"""
<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<title>Fraktionsprotokolle Vokabular (FPV)</title>

<style>
body {{
    font-family: Georgia, serif;
    max-width: 1000px;
    margin: 40px auto;
    line-height: 1.5;
}}

h1 {{
    border-bottom: 2px solid #000;
    padding-bottom: 10px;
}}

.index a {{
    margin-right: 8px;
    text-decoration: none;
}}

.filter button {{
    margin-right: 5px;
}}

.concept {{
    padding: 10px 0;
    border-bottom: 1px solid #ddd;
}}

.uri {{
    font-size: 0.85em;
    color: #666;
}}
</style>

<script>
function filterType(type) {{
    let items = document.querySelectorAll(".concept");
    items.forEach(item => {{
        if (type === "all") {{
            item.style.display = "block";
        }} else {{
            item.style.display = item.dataset.type === type ? "block" : "none";
        }}
    }});
}}

function searchConcept() {{
    let input = document.getElementById("search").value.toLowerCase();
    let items = document.querySelectorAll(".concept");

    items.forEach(item => {{
        let text = item.innerText.toLowerCase();
        item.style.display = text.includes(input) ? "block" : "none";
    }});
}}
</script>

</head>
<body>

<h1>Fraktionsprotokolle Vokabular (FPV)</h1>

<div>
<input type="text" id="search" placeholder="Suche..." onkeyup="searchConcept()" style="width: 300px;">
</div>

<h2>Alphabetischer Index</h2>
<div class="index">
"""

for letter in alphabet:
    html += f'<a href="#{letter}">{letter}</a>'

html += "</div>"

html += """
<h2>Filter nach Entitätstyp</h2>
<div class="filter">
<button onclick="filterType('all')">Alle</button>
<button onclick="filterType('org')">org</button>
<button onclick="filterType('com')">com</button>
<button onclick="filterType('news')">news</button>
<button onclick="filterType('topic')">topic</button>
<button onclick="filterType('law')">law</button>
<button onclick="filterType('pol')">pol</button>
</div>

<hr>
"""

current_letter = None

for c in concepts:
    if c["initial"] != current_letter:
        current_letter = c["initial"]
        html += f'<h2 id="{current_letter}">{current_letter}</h2>'

    html += f"""
<div class="concept" data-type="{c['type']}">
    <div class="uri">{c['uri']}</div>
    <strong>{c['pref']}</strong><br>
    <em>Typ:</em> {c['type']}<br>
"""

    if c["alts"]:
        html += "<em>AltLabel:</em> " + ", ".join(c["alts"]) + "<br>"

    html += "</div>"

html += """
</body>
</html>
"""

OUTPUT_FILE.write_text(html, encoding="utf-8")

print("HTML successfully generated.")