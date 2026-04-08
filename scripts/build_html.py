from pathlib import Path
from rdflib import Graph, RDF, Namespace, Literal
from collections import defaultdict
from urllib.parse import quote
from html import escape

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent

TTL_PATH = REPO_ROOT / "src" / "fpv.ttl"
DOCS_DIR = REPO_ROOT / "docs"
ID_DIR = DOCS_DIR / "id"

DOCS_DIR.mkdir(exist_ok=True)
ID_DIR.mkdir(exist_ok=True)

g = Graph()
g.parse(TTL_PATH, format="turtle")

SKOS = Namespace("http://www.w3.org/2004/02/skos/core#")


def get_local_id(uri: str) -> str:
    """
    Extract local ID from URI. Assumes your IDs are the last path segment.
    Example: https://voc.fraktionsprotokolle.de/id/AEG -> AEG
    """
    # strip trailing slash
    u = uri.rstrip("/")
    return u.split("/")[-1]


def get_pref_label_de(concept) -> str | None:
    """Return the German prefLabel for a concept, or None."""
    for label in g.objects(concept, SKOS.prefLabel):
        if isinstance(label, Literal) and label.language == "de":
            return str(label)
    # Fallback: any prefLabel
    for label in g.objects(concept, SKOS.prefLabel):
        if isinstance(label, Literal):
            return str(label)
    return None


def lang_sorted_literals(lits):
    """Return list of (lang, text) sorted by lang then text."""
    out = []
    for l in lits:
        if isinstance(l, Literal):
            out.append((l.language or "", str(l)))
    return sorted(out, key=lambda x: (x[0], x[1].lower()))


def write_detail_page(concept):
    uri = str(concept)
    cid = get_local_id(uri)

    pref = list(g.objects(concept, SKOS.prefLabel))
    alts = list(g.objects(concept, SKOS.altLabel))
    notes = list(g.objects(concept, SKOS.note))
    notations = list(g.objects(concept, SKOS.notation))
    exact = list(g.objects(concept, SKOS.exactMatch))
    close = list(g.objects(concept, SKOS.closeMatch))
    related = list(g.objects(concept, SKOS.related))

    pref_de = None
    for p in pref:
        if isinstance(p, Literal) and p.language == "de":
            pref_de = str(p)
            break
    if not pref_de and pref:
        pref_de = str(pref[0])

    # output directory: docs/id/<ID>/index.html
    out_dir = ID_DIR / cid
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "index.html"

    def render_lit_list(title, lits):
        items = lang_sorted_literals(lits)
        if not items:
            return ""
        rows = []
        for lang, text in items:
            lang_disp = escape(lang) if lang else "-"
            rows.append(f"<li><span class='lang'>{lang_disp}</span> {escape(text)}</li>")
        return f"""
        <section>
          <h2>{escape(title)}</h2>
          <ul class="kv">{''.join(rows)}</ul>
        </section>
        """

    def render_uri_list(title, uris):
        if not uris:
            return ""
        rows = []
        for u in sorted({str(x) for x in uris}):
            eu = escape(u)
            rows.append(f"<li><a href='{eu}'>{eu}</a></li>")
        return f"""
        <section>
          <h2>{escape(title)}</h2>
          <ul class="kv">{''.join(rows)}</ul>
        </section>
        """

    def render_related_list(title, related_uris):
        """Render skos:related as internal links with prefLabel."""
        if not related_uris:
            return ""
        rows = []
        for rel in sorted(related_uris, key=lambda r: str(r)):
            rel_id = get_local_id(str(rel))
            rel_label = get_pref_label_de(rel) or rel_id
            rel_href = f"../{quote(rel_id)}/"
            rows.append(
                f"<li><a href='{escape(rel_href)}'>{escape(rel_label)}</a>"
                f" <span class='uri'>{escape(rel_id)}</span></li>"
            )
        return f"""
        <section>
          <h2>{escape(title)}</h2>
          <ul class="kv">{''.join(rows)}</ul>
        </section>
        """

    notation_text = ""
    if notations:
        # keep first as display, but list all if multiple
        notation_text = ", ".join(sorted({str(n) for n in notations}))

    page = f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(pref_de or cid)} – FPV</title>
<style>
  body {{
    font-family: Georgia, serif;
    max-width: 980px;
    margin: 40px auto;
    line-height: 1.55;
    padding: 0 16px;
  }}
  header {{
    border-bottom: 2px solid #000;
    padding-bottom: 12px;
    margin-bottom: 18px;
  }}
  a {{ color: inherit; }}
  .meta {{ color: #444; font-size: 0.95em; }}
  .uri {{ font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 0.9em; color: #555; }}
  .badge {{
    display: inline-block;
    border: 1px solid #000;
    padding: 2px 8px;
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    font-size: 0.9em;
    margin-left: 8px;
  }}
  section {{ margin: 18px 0; }}
  h1 {{ margin: 0; }}
  h2 {{ font-size: 1.05em; margin: 0 0 8px 0; }}
  ul.kv {{ margin: 0; padding-left: 18px; }}
  ul.kv li {{ margin: 4px 0; }}
  .lang {{
    display: inline-block;
    min-width: 38px;
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    color: #666;
  }}
  nav {{ margin-top: 10px; }}
  nav a {{ text-decoration: none; border-bottom: 1px dotted #000; }}
  footer {{
    margin-top: 40px;
    padding-top: 10px;
    border-top: 1px solid #ccc;
    font-size: 0.85em;
    color: #666;
  }}
  footer a {{ color: #666; text-decoration: none; border-bottom: 1px dotted #666; }}
</style>
</head>
<body>
<header>
  <h1>{escape(pref_de or cid)} <span class="badge">{escape(notation_text)}</span></h1>
  <div class="meta">
    <div><span class="uri">{escape(uri)}</span></div>
    <nav><a href="{escape('../../index.html')}">← Zur Übersicht</a></nav>
  </div>
</header>

{render_lit_list("Bevorzugte Benennung (prefLabel)", pref)}
{render_lit_list("Alternative Benennungen (altLabel)", alts)}
{render_lit_list("Anmerkung (note)", notes)}
{render_uri_list("exactMatch", exact)}
{render_uri_list("closeMatch", close)}
{render_related_list("Verwandte Konzepte (related)", related)}

<footer>
  <a href="https://kgparl.de/impressum/">Impressum</a>
</footer>
</body>
</html>
"""
    out_file.write_text(page, encoding="utf-8")


# -----------------------------
# Build concept list for index
# -----------------------------
concept_rows = []
for concept in sorted(set(g.subjects(RDF.type, SKOS.Concept)), key=lambda s: str(s)):
    uri = str(concept)
    cid = get_local_id(uri)

    # prefLabel@de for sorting/display
    pref_de = None
    for label in g.objects(concept, SKOS.prefLabel):
        if isinstance(label, Literal) and label.language == "de":
            pref_de = str(label)
            break
    if not pref_de:
        # skip concepts without prefLabel@de (or fallback if you prefer)
        continue

    # get entityType code from notation literal value
    notation = next(g.objects(concept, SKOS.notation), None)
    etype = str(notation) if notation else ""

    # create detail page
    write_detail_page(concept)

    concept_rows.append({
        "id": cid,
        "uri": uri,
        "pref": pref_de,
        "type": etype,
        "initial": pref_de[0].upper() if pref_de else "#",
    })

# sort by label
concept_rows.sort(key=lambda x: x["pref"].lower())

alphabet = sorted({c["initial"] for c in concept_rows if c["initial"].isalpha()})

# -----------------------------
# Build index.html
# -----------------------------
def link_to_detail(cid: str) -> str:
    # Use pretty URL: /id/<ID>/  (works as /id/<ID> typically via redirect)
    # Escape URL path segments
    return f"id/{quote(cid)}/"

index_parts = []
index_parts.append("""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Fraktionsprotokolle Vokabular (FPV)</title>
<style>
  body {
    font-family: Georgia, serif;
    max-width: 1100px;
    margin: 40px auto;
    line-height: 1.55;
    padding: 0 16px;
  }
  header {
    border-bottom: 2px solid #000;
    padding-bottom: 12px;
    margin-bottom: 18px;
  }
  .controls {
    display: flex;
    flex-wrap: wrap;
    gap: 12px;
    align-items: center;
    margin: 14px 0 10px 0;
  }
  input[type="search"] {
    width: min(520px, 100%);
    padding: 8px 10px;
    font-size: 1rem;
    border: 1px solid #444;
  }
  .filter button {
    border: 1px solid #000;
    background: transparent;
    padding: 6px 10px;
    cursor: pointer;
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    font-size: 0.95em;
  }
  .filter button.active {
    background: #000;
    color: #fff;
  }
  .index a {
    margin-right: 10px;
    text-decoration: none;
    border-bottom: 1px dotted #000;
  }
  .group {
    margin-top: 18px;
  }
  .concept {
    padding: 10px 0;
    border-bottom: 1px solid #ddd;
  }
  .concept a {
    text-decoration: none;
    border-bottom: 1px dotted #000;
  }
  .meta {
    color: #555;
    font-size: 0.9em;
    margin-top: 3px;
  }
  .badge {
    display: inline-block;
    border: 1px solid #000;
    padding: 2px 8px;
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    font-size: 0.9em;
    margin-left: 8px;
  }
  .intro {
    margin: 12px 0 0 0;
    font-size: 0.97em;
    max-width: 820px;
    line-height: 1.6;
  }
  footer {
    margin-top: 40px;
    padding-top: 10px;
    border-top: 1px solid #ccc;
    font-size: 0.85em;
    color: #666;
  }
  footer a { color: #666; text-decoration: none; border-bottom: 1px dotted #666; }
</style>

<script>
let activeType = "all";

function setActiveButton(type) {
  document.querySelectorAll(".filter button").forEach(btn => {
    btn.classList.toggle("active", btn.dataset.type === type);
  });
}

function applyFilters() {
  const q = document.getElementById("q").value.toLowerCase().trim();
  const items = document.querySelectorAll(".concept");

  items.forEach(item => {
    const typeOk = (activeType === "all") || (item.dataset.type === activeType);
    const text = item.dataset.search;
    const queryOk = !q || text.includes(q);
    item.style.display = (typeOk && queryOk) ? "block" : "none";
  });
}

function setType(type) {
  activeType = type;
  setActiveButton(type);
  applyFilters();
}

window.addEventListener("DOMContentLoaded", () => {
  setActiveButton("all");
  applyFilters();
});
</script>

</head>
<body>
<header>
  <h1>Fraktionsprotokolle Vokabular (FPV)</h1>
  <p class="intro">Diese Webseite dient der einfacheren Darstellung des kontrollierten (Schlagwort-)Vokabulars
  (<a href="https://github.com/Fraktionsprotokolle-de/fpv-skos/">Fraktionsprotokolle Vocabulary, FPV</a>)
  der wissenschaftlichen Edition
  <a href="https://fraktionsprotokolle.de/">&#x00BB;Fraktionen im Deutschen Bundestag 1949&#x2013;2005&#x00AB;</a>.
  Die Webseite wird &#xFC;ber einen Github-Workflow automatisch aus der Vokabulardatei
  <a href="https://github.com/Fraktionsprotokolle-de/fpv-skos/blob/main/src/fpv.ttl">fpv.ttl</a> erzeugt.</p>
  <div class="controls">
    <input id="q" type="search" placeholder="Suche (prefLabel, ID) …" oninput="applyFilters()">
    <div class="filter" aria-label="Filter nach entityType">
      <button data-type="all"  onclick="setType('all')">Alle</button>
      <button data-type="org"  onclick="setType('org')">org</button>
      <button data-type="com"  onclick="setType('com')">com</button>
      <button data-type="news" onclick="setType('news')">news</button>
      <button data-type="topic" onclick="setType('topic')">topic</button>
      <button data-type="law"  onclick="setType('law')">law</button>
      <button data-type="pol"  onclick="setType('pol')">pol</button>
    </div>
  </div>

  <div class="index"><strong>A–Z:</strong>
""")

for letter in alphabet:
    index_parts.append(f"<a href='#{escape(letter)}'>{escape(letter)}</a>")

index_parts.append("</div></header>")

current_letter = None
for c in concept_rows:
    letter = c["initial"]
    if letter != current_letter and letter.isalpha():
        current_letter = letter
        index_parts.append(f"<div class='group'><h2 id='{escape(letter)}'>{escape(letter)}</h2></div>")

    cid = c["id"]
    href = link_to_detail(cid)
    search_blob = f"{c['pref']} {cid}".lower()

    index_parts.append(
        f"""<div class="concept" data-type="{escape(c['type'])}" data-search="{escape(search_blob)}">
  <div><a href="{escape(href)}">{escape(c['pref'])}</a><span class="badge">{escape(c['type'])}</span></div>
  <div class="meta">{escape(cid)} · <span class="meta">{escape(c['uri'])}</span></div>
</div>"""
    )

index_parts.append("""<footer>
  <a href="https://kgparl.de/impressum/">Impressum</a>
</footer>
</body></html>""")

(DOCS_DIR / "index.html").write_text("\n".join(index_parts), encoding="utf-8")

print("Build complete: docs/index.html and docs/id/<ID>/index.html")