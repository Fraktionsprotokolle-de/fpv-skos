import logging
import re
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

from rdflib import Graph, Literal, Namespace, RDF
from rdflib.term import URIRef

# rdflib schreibt URI-Warnungen über Python-logging auf stderr.
# Wir unterdrücken das hier – unser Script behandelt IRI-Probleme selbst.
logging.getLogger("rdflib").setLevel(logging.ERROR)

def strip_comment(line: str) -> str:
    """Entfernt den Kommentarteil einer Turtle-Zeile (ab # außerhalb von <> und "").
    Berücksichtigt korrekt # in URIs (<...>) und Literalen ("...")."""
    i = 0
    n = len(line)
    while i < n:
        c = line[i]
        if c == "<":
            i = line.find(">", i + 1)
            if i == -1:
                return line
            i += 1
        elif c == '"':
            if line[i : i + 3] == '"""':
                end = line.find('"""', i + 3)
                i = end + 3 if end != -1 else n
            else:
                i += 1
                while i < n and line[i] != '"':
                    if line[i] == "\\":
                        i += 1
                    i += 1
                i += 1
        elif c == "#":
            return line[:i]
        else:
            i += 1
    return line



# --------------------------------------------------
# Konfiguration
# --------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
DEFAULT_TTL_PATH = REPO_ROOT / "src" / "fpv.ttl"

SKOS = Namespace("http://www.w3.org/2004/02/skos/core#")
FPV = Namespace("https://voc.fraktionsprotokolle.de/schema/")

ALLOWED_ENTITY_TYPES = {"org", "com", "news", "topic", "law", "pol"}

EXEMPT_FROM_NOTATION_CHECK = {
    str(FPV.entityTypeNote),
}

PROJECT_ID_RE = re.compile(r"^[A-Za-z0-9._-]+$")

# Kontextzeilen um Fehlerzeile (im Terminal und in der Logdatei)
CONTEXT_BEFORE = 3
CONTEXT_AFTER  = 2


# --------------------------------------------------
# Hilfsfunktionen
# --------------------------------------------------


def resolve_ttl_path() -> Path:
    if len(sys.argv) > 1:
        return Path(sys.argv[1]).expanduser().resolve()
    return DEFAULT_TTL_PATH


class SourceIndex:
    def __init__(self) -> None:
        self.prefixes: dict[str, str] = {}
        self.concept_lines_by_uri: dict[str, list[int]] = defaultdict(list)
        self.concept_qname_by_uri: dict[str, str] = {}
        self.pref_label_de_lines_by_uri: dict[str, list[int]] = defaultdict(list)
        self.notation_lines_by_uri: dict[str, list[int]] = defaultdict(list)
        self.local_id_lines: dict[str, list[int]] = defaultdict(list)
        self.local_id_tokens: dict[str, list[str]] = defaultdict(list)
        self.local_id_by_uri: dict[str, str] = {}

    def expand_subject(self, token: str) -> str | None:
        token = token.strip()
        if token.startswith("<") and token.endswith(">"):
            return token[1:-1]
        if ":" not in token:
            return None
        prefix, local = token.split(":", 1)
        ns = self.prefixes.get(prefix)
        if ns is None:
            return None
        return ns + local

    def extract_local_id(self, token: str) -> str | None:
        token = token.strip()
        if token.startswith("<") and token.endswith(">"):
            uri = token[1:-1]
            if "#" in uri:
                return uri.rsplit("#", 1)[1]
            tail = uri.rstrip("/").rsplit("/", 1)[-1]
            return tail or None
        if ":" not in token:
            return None
        _, local = token.split(":", 1)
        return local or None


def build_source_index(ttl_path: Path) -> SourceIndex:
    index = SourceIndex()

    prefix_re = re.compile(r"^\s*@prefix\s+([A-Za-z][\w-]*):\s*<([^>]+)>\s*\.\s*$")
    concept_start_re = re.compile(r"^\s*([^\s]+)\s+a\s+skos:Concept\s*;\s*(?:#.*)?$")

    current_uri = None
    lines = ttl_path.read_text(encoding="utf-8").splitlines()

    for lineno, line in enumerate(lines, start=1):
        stripped = line.strip()

        prefix_match = prefix_re.match(line)
        if prefix_match:
            prefix, iri = prefix_match.groups()
            index.prefixes[prefix] = iri
            continue

        concept_match = concept_start_re.match(line)
        if concept_match:
            subject_token = concept_match.group(1)
            subject_uri = index.expand_subject(subject_token)
            local_id = index.extract_local_id(subject_token)
            current_uri = subject_uri
            if subject_uri is not None:
                index.concept_lines_by_uri[subject_uri].append(lineno)
                index.concept_qname_by_uri[subject_uri] = subject_token
                if local_id is not None:
                    index.local_id_by_uri[subject_uri] = local_id
            if local_id is not None:
                index.local_id_lines[local_id].append(lineno)
                index.local_id_tokens[local_id].append(subject_token)
            continue

        if current_uri is None:
            continue

        if re.match(r"^\s*skos:prefLabel\b", line) and "@de" in line:
            index.pref_label_de_lines_by_uri[current_uri].append(lineno)

        if re.match(r"^\s*skos:notation\b", line):
            index.notation_lines_by_uri[current_uri].append(lineno)

        if stripped.endswith("."):
            current_uri = None

    return index


def format_subject(uri: URIRef | str, index: SourceIndex) -> str:
    uri_str = str(uri)
    qname = index.concept_qname_by_uri.get(uri_str)
    if qname:
        return f"{qname} <{uri_str}>"
    return f"<{uri_str}>"


def first_line_for(uri: URIRef | str, index: SourceIndex) -> int | None:
    uri_str = str(uri)
    lines = index.concept_lines_by_uri.get(uri_str, [])
    return lines[0] if lines else None


def property_lines_for(uri: URIRef | str, index: SourceIndex, prop: str) -> list[int]:
    uri_str = str(uri)
    if prop == "prefLabel@de":
        return index.pref_label_de_lines_by_uri.get(uri_str, [])
    if prop == "notation":
        return index.notation_lines_by_uri.get(uri_str, [])
    return []


def is_xml_name_start_char(ch: str) -> bool:
    return ch == "_" or unicodedata.category(ch).startswith("L")


def is_xml_name_char(ch: str) -> bool:
    cat = unicodedata.category(ch)
    return (
        is_xml_name_start_char(ch)
        or cat in {"Mn", "Mc", "Nd", "Pc"}
        or ch in {"-", ".", "\u00b7"}
    )


def is_valid_xml_id(local_id: str) -> bool:
    if not local_id:
        return False
    if ":" in local_id or " " in local_id:
        return False
    if not is_xml_name_start_char(local_id[0]):
        return False
    return all(is_xml_name_char(ch) for ch in local_id[1:])


def has_non_ascii_or_special_chars(local_id: str) -> bool:
    return PROJECT_ID_RE.fullmatch(local_id) is None


# --------------------------------------------------
# Syntaxprüfung: Block-für-Block mit präzisen Zeilennummern
# --------------------------------------------------

_PREFIX_BLOCK = """\
@prefix ex:  <https://voc.fraktionsprotokolle.de/id/> .
@prefix fpv: <https://voc.fraktionsprotokolle.de/schema/> .
@prefix skos: <http://www.w3.org/2004/02/skos/core#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix dcterms: <http://purl.org/dc/terms/> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
"""
_PREFIX_LINE_COUNT = _PREFIX_BLOCK.count("\n")  # 6


class SyntaxError_:
    def __init__(self, lineno: int, block_start: int, block_end: int,
                 raw_msg: str, diagnosis: str) -> None:
        self.lineno = lineno
        self.block_start = block_start
        self.block_end = block_end
        self.raw_msg = raw_msg
        self.diagnosis = diagnosis


def _diagnose_line(line: str, prev_line: str | None) -> str:
    content = strip_comment(line).rstrip()

    if content.endswith(">"):
        return "Fehlendes ';' oder '.' nach URI"
    if re.search(r'@[a-z]{2,3}(-[A-Za-z0-9]+)?$', content):
        return "Fehlendes ';' oder '.' nach Sprachkennzeichen"
    if re.search(r'"[^"]*"\^\^[\w:]+$', content):
        return "Fehlendes ';' oder '.' nach typisiertem Literal"
    if re.search(r'"[^"]*"$', content) and not content.strip().startswith("#"):
        return "Fehlendes ';' oder '.' nach Literal (oder fehlendes Sprachkennzeichen, z. B. @de)"

    return "Syntaxfehler – Zeile oben prüfen"


def check_syntax_block_by_block(ttl_path: Path) -> list[SyntaxError_]:
    lines = ttl_path.read_text(encoding="utf-8").splitlines(keepends=True)
    concept_start_re = re.compile(r"^\s*\S+\s+a\s+skos:Concept\s*;")

    blocks: list[tuple[int, int, str]] = []
    block_start: int | None = None
    block_acc: list[str] = []
    in_multiline = False

    for i, line in enumerate(lines):
        lineno = i + 1
        triple_count = line.count('"""')
        if triple_count % 2 == 1:
            in_multiline = not in_multiline

        if block_start is None:
            if concept_start_re.match(line):
                block_start = lineno
                block_acc = [line]
        else:
            block_acc.append(line)
            if not in_multiline:
                content = strip_comment(line).rstrip()
                if content.rstrip().endswith("."):
                    blocks.append((block_start, lineno, "".join(block_acc)))
                    block_start = None
                    block_acc = []

    syntax_errors: list[SyntaxError_] = []

    for (start, end, text) in blocks:
        g = Graph()
        try:
            g.parse(data=_PREFIX_BLOCK + text, format="turtle")
        except Exception as exc:
            raw_msg = str(exc)
            line_match = re.search(r"line\s+(\d+)", raw_msg, re.IGNORECASE)
            if line_match:
                relative_line = int(line_match.group(1))
                actual_line = start + relative_line - _PREFIX_LINE_COUNT - 1
                actual_line = max(start, min(end, actual_line))
            else:
                actual_line = start

            block_lines = text.splitlines()
            err_idx = actual_line - start
            err_idx = max(0, min(len(block_lines) - 1, err_idx))
            err_line = block_lines[err_idx]
            prev_line = block_lines[err_idx - 1] if err_idx > 0 else None

            diagnosis = _diagnose_line(err_line, prev_line)
            # Wenn Diagnose auf der gemeldeten Zeile nichts ergibt, Vorgänger prüfen
            if (
                diagnosis == "Syntaxfehler – Zeile oben prüfen"
                and prev_line is not None
            ):
                prev_diag = _diagnose_line(prev_line, None)
                if prev_diag != "Syntaxfehler – Zeile oben prüfen":
                    actual_line -= 1
                    diagnosis = prev_diag

            syntax_errors.append(
                SyntaxError_(actual_line, start, end, raw_msg, diagnosis)
            )

    return syntax_errors


def parse_with_rdflib_tolerant(ttl_path: Path) -> Graph | None:
    g = Graph()
    try:
        g.parse(ttl_path, format="turtle")
        return g
    except Exception:
        return None


# --------------------------------------------------
# Ausgabe: Fehlerblock mit Kontextzeilen formatieren
# --------------------------------------------------


def format_syntax_error(se: SyntaxError_, raw_lines: list[str]) -> list[str]:
    """Gibt einen formatierten Fehlerblock als Zeilenliste zurück (Terminal + Log)."""
    block_first = raw_lines[se.block_start - 1] if se.block_start <= len(raw_lines) else ""
    m = re.match(r"^\s*(\S+)\s+a\s+skos:Concept", block_first)
    concept_id = m.group(1) if m else "?"

    out: list[str] = []
    out.append(f"FEHLER  Zeile {se.lineno}  [{concept_id}, Block {se.block_start}–{se.block_end}]")
    out.append(f"        {se.diagnosis}")
    out.append("")

    ctx_start = max(0, se.lineno - 1 - CONTEXT_BEFORE)
    ctx_end   = min(len(raw_lines), se.lineno - 1 + CONTEXT_AFTER + 1)
    for i in range(ctx_start, ctx_end):
        lineno_here = i + 1
        marker = ">>>" if lineno_here == se.lineno else "   "
        out.append(f"  {marker} {lineno_here:6}  {raw_lines[i]}")
    out.append("")
    return out


def format_structural_error(msg: str) -> list[str]:
    """Strukturfehler: eine Zeile, eingerückt."""
    return [f"  - {msg}"]


# --------------------------------------------------
# Hauptlogik
# --------------------------------------------------


def main() -> None:
    ttl_path = resolve_ttl_path()

    if not ttl_path.exists():
        print(f"ERROR: Turtle file not found at {ttl_path}")
        sys.exit(1)

    print(f"Validating file: {ttl_path}\n")

    source_index = build_source_index(ttl_path)
    _log_path = (
        Path(sys.argv[2]).expanduser().resolve()
        if len(sys.argv) > 2
        else ttl_path.with_name(ttl_path.stem + ".errors.log")
    )
    # Wenn Log-Pfad nicht schreibbar, Fallback auf cwd
    try:
        _log_path.touch(exist_ok=True)
    except OSError:
        _log_path = Path.cwd() / (ttl_path.stem + ".errors.log")

    # --------------------------------------------------
    # Phase 1: Syntaxprüfung (Block-für-Block)
    # --------------------------------------------------
    syntax_errors = check_syntax_block_by_block(ttl_path)

    if syntax_errors:
        raw_lines = ttl_path.read_text(encoding="utf-8").splitlines()
        log_path = _log_path

        print(f"❌ SYNTAXFEHLER GEFUNDEN ({len(syntax_errors)} Blöcke betroffen)\n")

        log_lines: list[str] = [
            f"Validierungsbericht: {ttl_path}",
            f"Syntaxfehler gesamt: {len(syntax_errors)}",
            "=" * 72,
            "",
        ]

        for se in syntax_errors:
            block = format_syntax_error(se, raw_lines)
            for line in block:
                print(line)
            log_lines.extend(block)

        log_lines.append("Bitte alle Syntaxfehler beheben und erneut validieren.")
        log_path.write_text("\n".join(log_lines), encoding="utf-8")

        print(f"Logdatei: {log_path}")
        print()
        print("Strukturvalidierung übersprungen – zuerst Syntaxfehler beheben.")
        sys.exit(1)

    # --------------------------------------------------
    # Phase 2: Strukturvalidierung via rdflib
    # --------------------------------------------------
    graph = parse_with_rdflib_tolerant(ttl_path)
    if graph is None:
        print("❌ RDF-Parsing fehlgeschlagen (trotz bestandener Syntaxprüfung).")
        print("   Das sollte nicht passieren – bitte melden.")
        sys.exit(1)

    errors: list[str] = []

    # 1) Doppelte Concept-Definitionen / doppelte IDs
    for uri_str, lines in sorted(source_index.concept_lines_by_uri.items()):
        if len(lines) > 1:
            subject_label = format_subject(uri_str, source_index)
            line_list = ", ".join(str(x) for x in lines)
            errors.append(f"Zeilen {line_list}: Doppelte skos:Concept-Definition für {subject_label}")

    for local_id, lines in sorted(source_index.local_id_lines.items()):
        if len(lines) > 1:
            line_list = ", ".join(str(x) for x in lines)
            tokens = ", ".join(dict.fromkeys(source_index.local_id_tokens[local_id]))
            errors.append(f"Zeilen {line_list}: Doppelte ID '{local_id}' in {tokens}")

    # 2) ID-Format
    for local_id, lines in sorted(source_index.local_id_lines.items()):
        line = lines[0]
        token = source_index.local_id_tokens[local_id][0]
        if not is_valid_xml_id(local_id):
            errors.append(f"Zeile {line}: ID '{local_id}' in {token} ist kein gültiger xml:id / NCName")
        if has_non_ascii_or_special_chars(local_id):
            errors.append(f"Zeile {line}: ID '{local_id}' in {token} enthält Umlaute oder unerlaubte Sonderzeichen")

    # 3) prefLabel@de – maximal eines erlaubt, keines ist okay
    # ACHTUNG: rdflib dedupliziert identische Tripel (Mengenlehre) – zwei mal
    # dasselbe prefLabel@de landet im Graph als ein Tripel und würde nicht erkannt.
    # Deshalb zählen wir Vorkommen direkt im Quelltext (SourceIndex).
    for concept in sorted(set(graph.subjects(RDF.type, SKOS.Concept)), key=str):
        pref_lines = property_lines_for(concept, source_index, "prefLabel@de")
        if len(pref_lines) > 1:
            subject_label = format_subject(concept, source_index)
            errors.append(
                f"Zeilen {', '.join(str(x) for x in pref_lines)}: "
                f"Mehrfaches skos:prefLabel@de ({len(pref_lines)}×) in {subject_label}"
            )

    # 4) skos:notation / entityType
    for concept in sorted(set(graph.subjects(RDF.type, SKOS.Concept)), key=str):
        concept_uri = str(concept)
        if concept_uri in EXEMPT_FROM_NOTATION_CHECK:
            continue
        subject_label = format_subject(concept, source_index)
        concept_line = first_line_for(concept, source_index)
        notation_lines = property_lines_for(concept, source_index, "notation")
        notations = list(graph.objects(concept, SKOS.notation))
        fallback_line = notation_lines[0] if notation_lines else concept_line
        loc = f"Zeile {fallback_line}" if fallback_line else "Unbekannte Zeile"

        if len(notations) == 0:
            errors.append(f"Zeile {concept_line}: Fehlendes skos:notation in {subject_label}")
            continue
        for n in notations:
            if not isinstance(n, Literal):
                errors.append(f"{loc}: Ungültige Notation (kein Literal) in {subject_label}")
                continue
            if n.datatype != FPV.entityType:
                errors.append(
                    f"{loc}: Falscher Notation-Datentyp in {subject_label} "
                    f"(erwartet ^^fpv:entityType, erhalten ^^<{n.datatype}>)"
                )
            if str(n) not in ALLOWED_ENTITY_TYPES:
                errors.append(f"{loc}: Ungültiger entityType-Code '{n}' in {subject_label}")


    # 5) Nicht-ASCII-Zeichen in IRIs (closeMatch, exactMatch etc.)
    #    Turtle/IRI (RFC 3987) erlaubt Unicode direkt; rdflib ist hier strenger
    #    als die Spezifikation. Wir geben daher nur eine Warnung aus, keinen Fehler.
    uri_pred_re = re.compile(
        r"skos:(?:closeMatch|exactMatch|broadMatch|narrowMatch|seeAlso)\s+<([^>]+)>"
    )
    iri_warnings: list[str] = []
    raw_lines_for_uri = ttl_path.read_text(encoding="utf-8").splitlines()
    for i, raw_line in enumerate(raw_lines_for_uri):
        m = uri_pred_re.search(raw_line)
        if not m:
            continue
        uri = m.group(1)
        bad = [c for c in uri if ord(c) > 127 or c in ' "{}|\\^`<>']
        if bad:
            from urllib.parse import quote
            fixed = quote(uri, safe='/:@?#=&%._~!$&\'()*+,;-')
            iri_warnings.append(
                f"Zeile {i + 1}: Nicht-ASCII-Zeichen in IRI (laut RFC 3987 erlaubt, "
                f"aber rdflib warnt).\n"
                f"          Percent-encoded Alternative: <{fixed}>"
            )

    if iri_warnings:
        print(f"\u26a0\ufe0f  HINWEISE ({len(iri_warnings)})\n")
        for w in iri_warnings:
            print(f"  - {w}")
        print()

    # --------------------------------------------------
    # Ergebnis
    # --------------------------------------------------
    if errors:
        log_path = _log_path
        print(f"❌ STRUKTURVALIDIERUNG FEHLGESCHLAGEN ({len(errors)} Fehler)\n")

        log_lines: list[str] = [
            f"Validierungsbericht: {ttl_path}",
            f"Strukturfehler gesamt: {len(errors)}",
            "=" * 72,
            "",
        ]
        for err in errors:
            line = format_structural_error(err)
            for l in line:
                print(l)
            log_lines.extend(line)

        log_path.write_text("\n".join(log_lines), encoding="utf-8")
        print(f"\nLogdatei: {log_path}")
        sys.exit(1)

    print("✅ Validierung erfolgreich. Keine Fehler gefunden.")


if __name__ == "__main__":
    main()