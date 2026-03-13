import re
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

from rdflib import Graph, Literal, Namespace, RDF
from rdflib.term import URIRef


# --------------------------------------------------
# Konfiguration
# --------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
DEFAULT_TTL_PATH = REPO_ROOT / "data" / "fpv.ttl"

SKOS = Namespace("http://www.w3.org/2004/02/skos/core#")
FPV = Namespace("https://voc.fraktionsprotokolle.de/schema/")

ALLOWED_ENTITY_TYPES = {"org", "com", "news", "topic", "law", "pol"}

# Dokumentations-/Metaknoten, die absichtlich kein skos:notation brauchen.
EXEMPT_FROM_NOTATION_CHECK = {
    str(FPV.entityTypeNote),
}

# Projektregel: ASCII-only für lokale IDs; Hyphen, Unterstrich und Punkt sind erlaubt.
PROJECT_ID_RE = re.compile(r"^[A-Za-z0-9._-]+$")


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

        # Nur die für die Validierung relevanten Prädikate zeilenweise indizieren.
        if re.match(r"^\s*skos:prefLabel\b", line) and "@de" in line:
            index.pref_label_de_lines_by_uri[current_uri].append(lineno)

        if re.match(r"^\s*skos:notation\b", line):
            index.notation_lines_by_uri[current_uri].append(lineno)

        # Blockende erkennen.
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


def parse_with_rdflib(ttl_path: Path) -> Graph:
    g = Graph()
    try:
        g.parse(ttl_path, format="turtle")
        return g
    except Exception as exc:
        msg = str(exc)
        line_match = re.search(r"line\s+(\d+)", msg, flags=re.IGNORECASE)
        print("❌ RDF parsing error")
        if line_match:
            print(f"   Zeile: {line_match.group(1)}")
        print(f"   Detail: {msg}")
        sys.exit(1)


def is_xml_name_start_char(ch: str) -> bool:
    return ch == "_" or unicodedata.category(ch).startswith("L")


def is_xml_name_char(ch: str) -> bool:
    cat = unicodedata.category(ch)
    return (
        is_xml_name_start_char(ch)
        or cat in {"Mn", "Mc", "Nd", "Pc"}
        or ch in {"-", ".", "·"}
    )


def is_valid_xml_id(local_id: str) -> bool:
    # xml:id-Werte müssen der NCName-Lexik entsprechen.
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
# Hauptlogik
# --------------------------------------------------


def main() -> None:
    ttl_path = resolve_ttl_path()

    if not ttl_path.exists():
        print(f"ERROR: Turtle file not found at {ttl_path}")
        sys.exit(1)

    print(f"Validating file: {ttl_path}\n")

    source_index = build_source_index(ttl_path)
    graph = parse_with_rdflib(ttl_path)

    errors: list[str] = []

    # --------------------------------------------------
    # 1) Doppelte Concept-Definitionen / doppelte IDs im Quelltext
    # --------------------------------------------------
    for uri_str, lines in sorted(source_index.concept_lines_by_uri.items()):
        if len(lines) > 1:
            subject_label = format_subject(uri_str, source_index)
            line_list = ", ".join(str(x) for x in lines)
            errors.append(
                f"Zeilen {line_list}: Duplicate skos:Concept definition for {subject_label}"
            )

    for local_id, lines in sorted(source_index.local_id_lines.items()):
        if len(lines) > 1:
            line_list = ", ".join(str(x) for x in lines)
            tokens = ", ".join(dict.fromkeys(source_index.local_id_tokens[local_id]))
            errors.append(
                f"Zeilen {line_list}: Duplicate ID '{local_id}' in {tokens}"
            )

    # --------------------------------------------------
    # 2) ID-Format-Prüfungen
    # --------------------------------------------------
    for local_id, lines in sorted(source_index.local_id_lines.items()):
        line = lines[0]
        token = source_index.local_id_tokens[local_id][0]

        if not is_valid_xml_id(local_id):
            errors.append(
                f"Zeile {line}: ID '{local_id}' in {token} is not a valid xml:id / NCName"
            )

        if has_non_ascii_or_special_chars(local_id):
            errors.append(
                f"Zeile {line}: ID '{local_id}' in {token} contains umlauts or disallowed special characters"
            )

    # --------------------------------------------------
    # 3) prefLabel@de
    # --------------------------------------------------
    for concept in sorted(set(graph.subjects(RDF.type, SKOS.Concept)), key=str):
        pref_de = [
            label
            for label in graph.objects(concept, SKOS.prefLabel)
            if isinstance(label, Literal) and label.language == "de"
        ]

        subject_label = format_subject(concept, source_index)
        concept_line = first_line_for(concept, source_index)
        pref_lines = property_lines_for(concept, source_index, "prefLabel@de")

        if len(pref_de) == 0:
            if concept_line is not None:
                errors.append(
                    f"Zeile {concept_line}: Missing skos:prefLabel@de in {subject_label}"
                )
            else:
                errors.append(f"Missing skos:prefLabel@de in {subject_label}")

        if len(pref_de) > 1:
            if pref_lines:
                line_list = ", ".join(str(x) for x in pref_lines)
                errors.append(
                    f"Zeilen {line_list}: Multiple skos:prefLabel@de in {subject_label}"
                )
            elif concept_line is not None:
                errors.append(
                    f"Zeile {concept_line}: Multiple skos:prefLabel@de in {subject_label}"
                )
            else:
                errors.append(f"Multiple skos:prefLabel@de in {subject_label}")

    # --------------------------------------------------
    # 4) skos:notation / entityType
    # --------------------------------------------------
    for concept in sorted(set(graph.subjects(RDF.type, SKOS.Concept)), key=str):
        concept_uri = str(concept)
        if concept_uri in EXEMPT_FROM_NOTATION_CHECK:
            continue

        subject_label = format_subject(concept, source_index)
        concept_line = first_line_for(concept, source_index)
        notation_lines = property_lines_for(concept, source_index, "notation")
        notations = list(graph.objects(concept, SKOS.notation))

        if len(notations) == 0:
            if concept_line is not None:
                errors.append(
                    f"Zeile {concept_line}: Missing skos:notation in {subject_label}"
                )
            else:
                errors.append(f"Missing skos:notation in {subject_label}")
            continue

        fallback_line = notation_lines[0] if notation_lines else concept_line

        for n in notations:
            if not isinstance(n, Literal):
                if fallback_line is not None:
                    errors.append(
                        f"Zeile {fallback_line}: Invalid notation (not literal) in {subject_label}"
                    )
                else:
                    errors.append(f"Invalid notation (not literal) in {subject_label}")
                continue

            if n.datatype != FPV.entityType:
                if fallback_line is not None:
                    errors.append(
                        f"Zeile {fallback_line}: Invalid notation datatype in {subject_label} "
                        f"(expected ^^fpv:entityType, got ^^<{n.datatype}>)"
                    )
                else:
                    errors.append(
                        f"Invalid notation datatype in {subject_label} "
                        f"(expected ^^fpv:entityType, got ^^<{n.datatype}>)"
                    )

            if str(n) not in ALLOWED_ENTITY_TYPES:
                if fallback_line is not None:
                    errors.append(
                        f"Zeile {fallback_line}: Invalid entityType code '{n}' in {subject_label}"
                    )
                else:
                    errors.append(
                        f"Invalid entityType code '{n}' in {subject_label}"
                    )

    # --------------------------------------------------
    # Ergebnis
    # --------------------------------------------------
    if errors:
        print("❌ VALIDATION FAILED\n")
        for err in errors:
            print(f" - {err}")
        sys.exit(1)

    print("✅ Validation erfolgreich. Keine strukturellen fehler gefunden.")


if __name__ == "__main__":
    main()