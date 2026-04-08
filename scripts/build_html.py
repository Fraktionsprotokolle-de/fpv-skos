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

# ---------------------------------------------------------------------------
# Shared CSS fragments
# ---------------------------------------------------------------------------

BADGE_CSS = """
  .badge {
    display: inline-block;
    padding: 2px 8px;
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    font-size: 0.78em;
    border-radius: 3px;
    margin-left: 8px;
    font-weight: 500;
    vertical-align: middle;
  }
  .badge-org   { background: #E6F1FB; color: #0C447C; }
  .badge-com   { background: #E1F5EE; color: #085041; }
  .badge-news  { background: #FAEEDA; color: #633806; }
  .badge-topic { background: #EEEDFE; color: #3C3489; }
  .badge-law   { background: #FAECE7; color: #712B13; }
  .badge-pol   { background: #EAF3DE; color: #27500A; }
"""

FOOTER_HTML = """<footer>
  <div class="footer-inner">
    <a href="https://kgparl.de/impressum/">Impressum</a>
  </div>
</footer>"""

FOOTER_CSS = """
  footer {
    margin-top: 48px;
    background: #f5f5f2;
    padding: 14px 0;
  }
  .footer-inner {
    max-width: 980px;
    margin: 0 auto;
    padding: 0 16px;
    font-size: 0.85em;
    color: #666;
    font-family: system-ui, -apple-system, sans-serif;
  }
  footer a { color: #555; text-decoration: none; border-bottom: 1px dotted #aaa; }
  footer a:hover { color: #000; }
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_local_id(uri: str) -> str:
    """Extract local ID from URI (last path segment)."""
    u = uri.rstrip("/")
    return u.split("/")[-1]


def get_pref_label_de(concept) -> str | None:
    """Return the German prefLabel for a concept, or None."""
    for label in g.objects(concept, SKOS.prefLabel):
        if isinstance(label, Literal) and label.language == "de":
            return str(label)
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


# ---------------------------------------------------------------------------
# Detail page builder
# ---------------------------------------------------------------------------

def write_detail_page(concept):
    uri = str(concept)
    cid = get_local_id(uri)

    pref      = list(g.objects(concept, SKOS.prefLabel))
    alts      = list(g.objects(concept, SKOS.altLabel))
    notes     = list(g.objects(concept, SKOS.note))
    notations = list(g.objects(concept, SKOS.notation))
    exact     = list(g.objects(concept, SKOS.exactMatch))
    close     = list(g.objects(concept, SKOS.closeMatch))
    related   = list(g.objects(concept, SKOS.related))

    pref_de = None
    for p in pref:
        if isinstance(p, Literal) and p.language == "de":
            pref_de = str(p)
            break
    if not pref_de and pref:
        pref_de = str(pref[0])

    out_dir = ID_DIR / cid
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "index.html"

    notation_text = ""
    badge_class = ""
    if notations:
        notation_text = ", ".join(sorted({str(n) for n in notations}))
        badge_class = f"badge-{escape(notation_text.split(',')[0].strip())}"

    # ------------------------------------------------------------------
    # Section renderers – two-column table layout
    # ------------------------------------------------------------------

    def render_section(title, body_html):
        return f"""
<section>
  <div class="dl-label">{escape(title)}</div>
  <table class="dl-table">{body_html}</table>
</section>"""

    def render_lit_list(title, lits):
        items = lang_sorted_literals(lits)
        if not items:
            return ""
        rows = []
        for lang, text in items:
            lang_disp = escape(lang) if lang else "\u2013"
            rows.append(f"<tr><td class='lang'>{lang_disp}</td><td>{escape(text)}</td></tr>")
        return render_section(title, "".join(rows))

    def render_uri_list(title, uris):
        if not uris:
            return ""
        rows = []
        for u in sorted({str(x) for x in uris}):
            eu = escape(u)
            rows.append(
                f"<tr><td colspan='2'><a class='ext-link' href='{eu}'>{eu}</a></td></tr>"
            )
        return render_section(title, "".join(rows))

    def render_related_list(title, related_uris):
        if not related_uris:
            return ""
        rows = []
        for rel in sorted(related_uris, key=lambda r: str(r)):
            rel_id    = get_local_id(str(rel))
            rel_label = get_pref_label_de(rel) or rel_id
            rel_href  = f"../{quote(rel_id)}/"
            rel_not   = next(g.objects(rel, SKOS.notation), None)
            rel_type  = str(rel_not) if rel_not else ""
            rel_badge = (
                f"<span class='badge badge-{escape(rel_type)}'>{escape(rel_type)}</span>"
                if rel_type else ""
            )
            rows.append(
                f"<tr><td colspan='2'>"
                f"<a href='{escape(rel_href)}'>{escape(rel_label)}</a>{rel_badge}"
                f" <span class='id-mono'>{escape(rel_id)}</span>"
                f"</td></tr>"
            )
        return render_section(title, "".join(rows))

    page = f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(pref_de or cid)} \u2013 FPV</title>
<style>
  * {{ box-sizing: border-box; }}
  body {{
    font-family: system-ui, -apple-system, Segoe UI, sans-serif;
    max-width: 980px;
    margin: 40px auto;
    line-height: 1.6;
    padding: 0 16px;
    color: #111;
    background: #fff;
  }}
  header {{
    border-bottom: 2px solid #111;
    padding-bottom: 20px;
    margin-bottom: 28px;
  }}
  a {{ color: inherit; }}
  h1 {{
    font-family: Georgia, serif;
    font-size: 1.65rem;
    font-weight: normal;
    margin: 0 0 8px 0;
    line-height: 1.3;
  }}
  .header-uri {{
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    font-size: 0.8em;
    color: #999;
    margin-bottom: 10px;
    word-break: break-all;
  }}
  nav a {{
    font-size: 0.9em;
    color: #555;
    text-decoration: none;
    border-bottom: 1px dotted #aaa;
  }}
  nav a:hover {{ color: #000; }}
  section {{ margin: 20px 0; }}
  .dl-label {{
    font-size: 0.72em;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.07em;
    color: #999;
    margin-bottom: 8px;
  }}
  .dl-table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 0.95em;
  }}
  .dl-table td {{
    padding: 6px 0;
    border-bottom: 1px solid #f0f0f0;
    vertical-align: top;
  }}
  .dl-table td.lang {{
    width: 40px;
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    font-size: 0.85em;
    color: #bbb;
    padding-right: 14px;
  }}
  .ext-link {{
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    font-size: 0.85em;
    color: #185FA5;
    text-decoration: none;
    border-bottom: 1px solid #B5D4F4;
    word-break: break-all;
  }}
  .ext-link:hover {{ color: #0C447C; }}
  .id-mono {{
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    font-size: 0.82em;
    color: #bbb;
    margin-left: 6px;
  }}
{BADGE_CSS}
{FOOTER_CSS}
</style>
</head>
<body>
<header>
  <h1>{escape(pref_de or cid)} <span class="badge {badge_class}">{escape(notation_text)}</span></h1>
  <div class="header-uri">{escape(uri)}</div>
  <nav><a href="{escape('../../index.html')}">&#x2190; Zur \u00dcbersicht</a></nav>
</header>

{render_lit_list("Bevorzugte Benennung (prefLabel)", pref)}
{render_lit_list("Alternative Benennungen (altLabel)", alts)}
{render_lit_list("Anmerkung (note)", notes)}
{render_uri_list("exactMatch", exact)}
{render_uri_list("closeMatch", close)}
{render_related_list("Verwandte Konzepte (related)", related)}

{FOOTER_HTML}
</body>
</html>
"""
    out_file.write_text(page, encoding="utf-8")


# ---------------------------------------------------------------------------
# Build concept list for index
# ---------------------------------------------------------------------------

concept_rows = []
for concept in sorted(set(g.subjects(RDF.type, SKOS.Concept)), key=lambda s: str(s)):
    uri = str(concept)
    cid = get_local_id(uri)

    pref_de = None
    for label in g.objects(concept, SKOS.prefLabel):
        if isinstance(label, Literal) and label.language == "de":
            pref_de = str(label)
            break
    if not pref_de:
        continue

    notation = next(g.objects(concept, SKOS.notation), None)
    etype = str(notation) if notation else ""

    write_detail_page(concept)

    concept_rows.append({
        "id":      cid,
        "uri":     uri,
        "pref":    pref_de,
        "type":    etype,
        "initial": pref_de[0].upper() if pref_de else "#",
    })

concept_rows.sort(key=lambda x: x["pref"].lower())
alphabet = sorted({c["initial"] for c in concept_rows if c["initial"].isalpha()})


# ---------------------------------------------------------------------------
# Build index.html
# ---------------------------------------------------------------------------

def link_to_detail(cid: str) -> str:
    return f"id/{quote(cid)}/"


index_parts = []
index_parts.append(f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Fraktionsprotokolle Vokabular (FPV)</title>
<style>
  * {{ box-sizing: border-box; }}
  body {{
    font-family: system-ui, -apple-system, Segoe UI, sans-serif;
    max-width: 1100px;
    margin: 0 auto;
    line-height: 1.6;
    padding: 0 16px;
    color: #111;
    background: #fff;
  }}
  header {{
    border-bottom: 2px solid #111;
    padding: 32px 0 24px 0;
    margin-bottom: 0;
  }}
  h1 {{
    font-family: Georgia, serif;
    font-size: 1.9rem;
    font-weight: normal;
    margin: 0 0 14px 0;
  }}
  .intro {{
    font-family: Georgia, serif;
    font-size: 0.97em;
    color: #444;
    max-width: 780px;
    line-height: 1.65;
    margin-bottom: 22px;
  }}
  .intro a {{
    color: #185FA5;
    text-decoration: none;
    border-bottom: 1px solid #B5D4F4;
  }}
  .intro a:hover {{ color: #0C447C; }}
  .controls {{
    display: flex;
    flex-wrap: wrap;
    gap: 12px;
    align-items: center;
    margin-bottom: 14px;
  }}
  input[type="search"] {{
    width: min(380px, 100%);
    padding: 8px 12px;
    font-size: 0.95rem;
    border: 1px solid #ccc;
    border-radius: 4px;
    font-family: inherit;
    background: #fafafa;
  }}
  input[type="search"]:focus {{
    outline: none;
    border-color: #888;
    background: #fff;
  }}
  .filter {{
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
  }}
  .filter button {{
    border: 1px solid transparent;
    padding: 5px 11px;
    cursor: pointer;
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    font-size: 0.82em;
    border-radius: 4px;
    font-weight: 500;
    background: #f0f0ec;
    color: #555;
  }}
  .filter button.active {{
    background: #111 !important;
    color: #fff !important;
    border-color: #111 !important;
  }}
  .filter button[data-type="org"]   {{ background: #E6F1FB; color: #0C447C; }}
  .filter button[data-type="com"]   {{ background: #E1F5EE; color: #085041; }}
  .filter button[data-type="news"]  {{ background: #FAEEDA; color: #633806; }}
  .filter button[data-type="topic"] {{ background: #EEEDFE; color: #3C3489; }}
  .filter button[data-type="law"]   {{ background: #FAECE7; color: #712B13; }}
  .filter button[data-type="pol"]   {{ background: #EAF3DE; color: #27500A; }}
  .az-nav {{
    font-size: 0.88em;
    color: #888;
    margin-top: 4px;
  }}
  .az-nav strong {{ color: #555; margin-right: 6px; }}
  .az-nav a {{
    margin-right: 7px;
    text-decoration: none;
    color: #555;
    border-bottom: 1px dotted #bbb;
  }}
  .az-nav a:hover {{ color: #000; }}
  .letter-group {{ margin-top: 28px; }}
  .letter-heading {{
    font-family: Georgia, serif;
    font-size: 1.3rem;
    font-weight: normal;
    color: #111;
    border-bottom: 1px solid #e0e0e0;
    padding-bottom: 4px;
    margin-bottom: 2px;
  }}
  .concept {{
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    gap: 16px;
    padding: 10px 0;
    border-bottom: 1px solid #eee;
  }}
  .concept-main {{ flex: 1; min-width: 0; }}
  .concept a {{
    font-size: 0.97em;
    color: #111;
    text-decoration: none;
    border-bottom: 1px dotted #ccc;
  }}
  .concept a:hover {{ border-bottom-color: #111; }}
  .concept-id {{
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    font-size: 0.78em;
    color: #ccc;
    margin-top: 3px;
  }}
  .concept-uri {{
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    font-size: 0.75em;
    color: #ccc;
    opacity: 0;
    transition: opacity 0.15s;
    flex-shrink: 0;
    max-width: 45%;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }}
  .concept:hover .concept-uri {{ opacity: 1; }}
{BADGE_CSS}
{FOOTER_CSS.replace('max-width: 980px', 'max-width: 1100px')}
</style>

<script>
let activeType = "all";

function setActiveButton(type) {{
  document.querySelectorAll(".filter button").forEach(btn => {{
    btn.classList.toggle("active", btn.dataset.type === type);
  }});
}}

function applyFilters() {{
  const q = document.getElementById("q").value.toLowerCase().trim();
  const items = document.querySelectorAll(".concept");
  const visibleByLetter = {{}};

  items.forEach(item => {{
    const typeOk = (activeType === "all") || (item.dataset.type === activeType);
    const queryOk = !q || item.dataset.search.includes(q);
    const show = typeOk && queryOk;
    item.style.display = show ? "flex" : "none";
    if (show) visibleByLetter[item.dataset.letter] = true;
  }});

  document.querySelectorAll(".letter-group").forEach(grp => {{
    grp.style.display = visibleByLetter[grp.dataset.letter] ? "block" : "none";
  }});
}}

function setType(type) {{
  activeType = type;
  setActiveButton(type);
  applyFilters();
}}

window.addEventListener("DOMContentLoaded", () => {{
  setActiveButton("all");
  applyFilters();
}});
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
    <input id="q" type="search" placeholder="Suche (prefLabel, ID)\u2009\u2026" oninput="applyFilters()">
    <div class="filter" aria-label="Filter nach entityType">
      <button data-type="all"   onclick="setType('all')">Alle</button>
      <button data-type="org"   onclick="setType('org')">org</button>
      <button data-type="com"   onclick="setType('com')">com</button>
      <button data-type="news"  onclick="setType('news')">news</button>
      <button data-type="topic" onclick="setType('topic')">topic</button>
      <button data-type="law"   onclick="setType('law')">law</button>
      <button data-type="pol"   onclick="setType('pol')">pol</button>
    </div>
  </div>
  <div class="az-nav"><strong>A\u2013Z:</strong>
""")

for letter in alphabet:
    index_parts.append(f"<a href='#{escape(letter)}'>{escape(letter)}</a>")

index_parts.append("</div>\n</header>")

current_letter = None
for c in concept_rows:
    letter = c["initial"]
    if letter != current_letter and letter.isalpha():
        if current_letter is not None:
            index_parts.append("</div>")  # close previous letter-group
        current_letter = letter
        index_parts.append(
            f"<div class='letter-group' data-letter='{escape(letter)}'>"
            f"<h2 class='letter-heading' id='{escape(letter)}'>{escape(letter)}</h2>"
        )

    cid = c["id"]
    href = link_to_detail(cid)
    search_blob = f"{c['pref']} {cid}".lower()
    badge_cls = f"badge badge-{escape(c['type'])}" if c["type"] else "badge"

    index_parts.append(
        f"""<div class="concept" data-type="{escape(c['type'])}" data-search="{escape(search_blob)}" data-letter="{escape(letter)}">
  <div class="concept-main">
    <div><a href="{escape(href)}">{escape(c['pref'])}</a><span class="{badge_cls}">{escape(c['type'])}</span></div>
    <div class="concept-id">{escape(cid)}</div>
  </div>
  <span class="concept-uri">{escape(c['uri'])}</span>
</div>"""
    )

if current_letter is not None:
    index_parts.append("</div>")  # close last letter-group

index_parts.append(f"""
{FOOTER_HTML}
</body></html>""")

(DOCS_DIR / "index.html").write_text("\n".join(index_parts), encoding="utf-8")

print("Build complete: docs/index.html and docs/id/<ID>/index.html")