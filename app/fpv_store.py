from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
import re
import shutil
from typing import Iterable


ENTRY_START_RE = re.compile(r"^ex:([A-Za-z0-9_-]+)\s+a\s+skos:Concept\s*;\s*$")
PREFLABEL_RE = re.compile(r'^skos:prefLabel\s+"(.*)"@([a-zA-Z-]+)\s*;\s*$')
ALTLABEL_RE = re.compile(r'^skos:altLabel\s+"(.*)"@([a-zA-Z-]+)\s*;\s*$')
NOTATION_RE = re.compile(r'^skos:notation\s+"(org|com|news|topic|law|pol)"\^\^fpv:entityType\s*;\s*$')
BOOLEAN_RE = re.compile(r'^ex:useInSynonymList\s+"(true|false)"\^\^xsd:boolean\s*;\s*$')
EXACT_RE = re.compile(r'^skos:exactMatch\s+<([^>]+)>\s*;\s*$')
CLOSE_RE = re.compile(r'^skos:closeMatch\s+<([^>]+)>\s*;\s*$')
NOTE_RE = re.compile(r'^skos:note\s+"(.*)"@([a-zA-Z-]+)\s*\.\s*$')
ID_RE = re.compile(r'^[A-Za-z0-9_-]+$')

ALLOWED_NOTATIONS = {"org", "com", "news", "topic", "law", "pol"}


@dataclass
class Entry:
    id: str
    pref_label: str
    pref_label_lang: str = "de"
    alt_labels: list[tuple[str, str]] = field(default_factory=list)
    notation: str = ""
    use_in_synonym_list: bool = False
    exact_match: str = ""
    close_match: str = ""
    note: str = ""
    note_lang: str = "de"
    raw_extra_lines: list[str] = field(default_factory=list)


@dataclass
class Store:
    header_lines: list[str]
    entries: list[Entry]


def load_store(path: Path) -> Store:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()

    header_lines: list[str] = []
    entries: list[Entry] = []
    i = 0
    found_first_entry = False

    while i < len(lines):
        line = lines[i]
        if ENTRY_START_RE.match(line.strip()):
            found_first_entry = True
            entry, i = _parse_entry(lines, i)
            entries.append(entry)
        else:
            if not found_first_entry:
                header_lines.append(line)
            i += 1

    entries.sort(key=lambda e: (e.pref_label.lower(), e.id.lower()))
    return Store(header_lines=header_lines, entries=entries)


def _parse_entry(lines: list[str], start_index: int) -> tuple[Entry, int]:
    start_line = lines[start_index].strip()
    m = ENTRY_START_RE.match(start_line)
    if not m:
        raise ValueError(f"Ungültiger Eintragsanfang in Zeile {start_index + 1}: {lines[start_index]}")

    entry_id = m.group(1)
    entry = Entry(id=entry_id, pref_label="")
    i = start_index + 1

    while i < len(lines):
        raw = lines[i].strip()

        if not raw:
            i += 1
            break

        if ENTRY_START_RE.match(raw):
            break

        if m2 := PREFLABEL_RE.match(raw):
            entry.pref_label = _unescape_literal(m2.group(1))
            entry.pref_label_lang = m2.group(2)
        elif m2 := ALTLABEL_RE.match(raw):
            entry.alt_labels.append((_unescape_literal(m2.group(1)), m2.group(2)))
        elif m2 := NOTATION_RE.match(raw):
            entry.notation = m2.group(1)
        elif m2 := BOOLEAN_RE.match(raw):
            entry.use_in_synonym_list = (m2.group(1) == "true")
        elif m2 := EXACT_RE.match(raw):
            entry.exact_match = m2.group(1)
        elif m2 := CLOSE_RE.match(raw):
            entry.close_match = m2.group(1)
        elif m2 := NOTE_RE.match(raw):
            entry.note = _unescape_literal(m2.group(1))
            entry.note_lang = m2.group(2)
        else:
            entry.raw_extra_lines.append(raw)

        i += 1

    return entry, i


def save_store(store: Store, target_path: Path, backup_dir: Path | None = None) -> None:
    if backup_dir is not None and target_path.exists():
        backup_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        shutil.copy2(target_path, backup_dir / f"fpv_{timestamp}.ttl")

    store.entries.sort(key=lambda e: (e.pref_label.lower(), e.id.lower()))

    output_lines = list(store.header_lines)
    if output_lines and output_lines[-1].strip() != "":
        output_lines.append("")

    for idx, entry in enumerate(store.entries):
        output_lines.extend(_serialize_entry(entry))
        if idx != len(store.entries) - 1:
            output_lines.append("")

    target_path.write_text("\n".join(output_lines) + "\n", encoding="utf-8")


def _serialize_entry(entry: Entry) -> list[str]:
    lines = [f"ex:{entry.id} a skos:Concept ;"]
    lines.append(f' skos:prefLabel "{_escape_literal(entry.pref_label)}"@{entry.pref_label_lang} ;')

    for value, lang in entry.alt_labels:
        lines.append(f' skos:altLabel "{_escape_literal(value)}"@{lang} ;')

    lines.append(f' skos:notation "{entry.notation}"^^fpv:entityType ;')

    bool_value = "true" if entry.use_in_synonym_list else "false"
    lines.append(f' ex:useInSynonymList "{bool_value}"^^xsd:boolean ;')

    if entry.exact_match:
        lines.append(f' skos:exactMatch <{entry.exact_match}> ;')

    if entry.close_match:
        lines.append(f' skos:closeMatch <{entry.close_match}> ;')

    for raw in entry.raw_extra_lines:
        lines.append(f" {raw.lstrip()}")

    lines.append(f' skos:note "{_escape_literal(entry.note)}"@{entry.note_lang} .')
    return lines


def validate_entry(entry: Entry, existing_ids: Iterable[str] = ()) -> list[str]:
    errors: list[str] = []
    existing_ids_set = set(existing_ids)

    if not entry.id:
        errors.append("ID fehlt.")
    elif not ID_RE.match(entry.id):
        errors.append("ID ist formal unzulässig. Erlaubt sind Buchstaben, Ziffern, Unterstrich und Bindestrich.")
    elif entry.id in existing_ids_set:
        errors.append("ID existiert bereits.")

    if not entry.pref_label:
        errors.append("prefLabel fehlt.")

    if entry.notation not in ALLOWED_NOTATIONS:
        errors.append("notation/entityType ist ungültig.")

    if not entry.note:
        errors.append("note fehlt.")

    return errors


def _escape_literal(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _unescape_literal(value: str) -> str:
    return value.replace('\\"', '"').replace("\\\\", "\\")