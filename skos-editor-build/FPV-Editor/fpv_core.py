# -*- coding: utf-8 -*-
"""
fpv_core.py — Kernlogik des FPV-Editors.

Verantwortlich für:
  * Einlesen und Erkennen editierbarer Turtle-Blöcke (ohne die Datei
    komplett neu zu serialisieren, damit Kommentare, Formatierung und
    nicht bearbeitete Abschnitte unverändert bleiben),
  * Parsing eines Blocks in ein einfaches JSON-taugliches Formularmodell,
  * Validierung einzelner Datensätze und der gesamten Datei,
  * Ermittlung eines funktionierenden Sicherungsortes nach fester
    Kaskade und Erstellung einer geprüften (verifizierten) Sicherung,
  * atomisches Schreiben der geänderten Gesamtdatei mit nicht-atomarem
    Rückfall bei PermissionError, ausschließlich NACH erfolgreicher
    Sicherung.

Wichtig: Dieses Modul erhebt NICHT den Anspruch, das eigenständige
Referenzskript ``validate_fpv.py`` der Redaktion zu ersetzen oder
auszuführen. Es implementiert eine eigene, im Projekt-Übergabedokument
beschriebene Regelmenge, die an mehreren Stellen enger ist (z. B.
„genau ein prefLabel“ statt „höchstens eines“) und in anderen Punkten
weniger differenzierte Diagnosen liefert. Ein Abgleich beider
Regelwerke vor einem produktiven Release steht noch aus.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import shutil
import tempfile
import time
import unicodedata
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

try:
    import rdflib
    from rdflib import Graph, URIRef, Literal
    from rdflib.namespace import Namespace, XSD as XSD_NS
except ImportError as exc:  # pragma: no cover - Startfehler wird von app.py/launcher.py gemeldet
    raise ImportError(
        "rdflib ist nicht installiert. Siehe requirements.txt / build_windows.bat."
    ) from exc


# --------------------------------------------------------------------------
# Konstanten / Vokabular
# --------------------------------------------------------------------------

EX = "https://voc.fraktionsprotokolle.de/id/"
FPV = "https://voc.fraktionsprotokolle.de/schema/"
SKOS = "http://www.w3.org/2004/02/skos/core#"
XSD = "http://www.w3.org/2001/XMLSchema#"

EX_NS = Namespace(EX)
FPV_NS = Namespace(FPV)
SKOS_NS = Namespace(SKOS)

# Bekannte, im Formular unterstützte Prädikate innerhalb eines regulären Blocks.
# "a skos:Concept" wird separat als Typaussage behandelt.
KNOWN_PREDICATES = {
    "skos:prefLabel",
    "skos:altLabel",
    "skos:notation",
    "ex:useInSynonymList",
    "skos:exactMatch",
    "skos:closeMatch",
    "skos:note",
    # skos:related ist regulaeres SKOS (symmetrische assoziative Beziehung
    # zwischen zwei Concepts) und wurde urspruenglich faelschlich als
    # "unbekanntes Praedikat" behandelt, wodurch solche Bloecke unnoetig
    # gesperrt wurden. Die Objekte sind hier praefixierte Namen (ex:ID),
    # keine <URI>-Literale, und duerfen kommagetrennt mehrfach auftreten:
    #   skos:related ex:MBFR , ex:SALT .
    "skos:related",
}

TYPE_CODES = {"org", "com", "news", "topic", "law", "pol"}

ID_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9._-]*$")

MAX_OPEN_BYTES = 15 * 1024 * 1024  # 15 MiB Obergrenze beim Öffnen

# Sichtbare Datenschlüssel im JSON-Formularmodell (Dokumentation/Referenz).
RECORD_FIELDS = ("id", "pref", "lang", "type", "note", "synonym", "alts", "exact", "close", "related")


class FpvError(Exception):
    """Fachlicher Fehler, der dem Formular / der API als Meldung angezeigt werden soll."""


class VersionConflict(FpvError):
    """Die Datei wurde seit dem letzten Laden extern verändert (SHA-256 weicht ab)."""


class ProtectedBlockError(FpvError):
    """Der Block enthält unbekannte Prädikate, Kommentare oder mehrzeilige Literale
    und wird zum Schutz vor Informationsverlust nicht über das Formular bearbeitet."""


class ReferencedError(FpvError):
    """Löschen abgelehnt, weil andere Knoten auf die ID verweisen."""


class BackupError(FpvError):
    """An keinem Kandidatenort konnte eine geprüfte Sicherung erstellt werden."""


# --------------------------------------------------------------------------
# Datei einlesen: Zeilenenden, BOM, Rohtext
# --------------------------------------------------------------------------

@dataclass
class LoadedFile:
    path: str
    raw_bytes: bytes
    text: str          # intern immer mit "\n" normalisiert
    uses_crlf: bool
    sha256: str


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_ttl_file(path: str) -> LoadedFile:
    """Liest eine TTL-Datei ein. Erkennt CRLF/LF; lehnt UTF-8-BOM ab (siehe Übergabe §5)."""
    p = Path(path)
    if not p.exists() or not p.is_file():
        raise FpvError(f"Datei nicht gefunden: {path}")
    size = p.stat().st_size
    if size > MAX_OPEN_BYTES:
        raise FpvError(
            f"Datei ist {size / (1024*1024):.1f} MiB groß und überschreitet die "
            f"Obergrenze von {MAX_OPEN_BYTES // (1024*1024)} MiB zum Öffnen."
        )
    raw = p.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        raise FpvError(
            "Die Datei beginnt mit einer UTF-8-BOM. Das wird vom Editor derzeit "
            "nicht unterstützt (siehe Übergabe §5). Bitte BOM extern entfernen."
        )
    try:
        text_raw = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise FpvError(f"Datei ist nicht gültiges UTF-8: {exc}") from exc

    uses_crlf = "\r\n" in text_raw
    text_norm = text_raw.replace("\r\n", "\n")
    return LoadedFile(
        path=str(p),
        raw_bytes=raw,
        text=text_norm,
        uses_crlf=uses_crlf,
        sha256=_sha256_bytes(raw),
    )


def _renormalize_line_endings(text_lf: str, uses_crlf: bool) -> str:
    text_lf = text_lf.replace("\r\n", "\n")
    if uses_crlf:
        return text_lf.replace("\n", "\r\n")
    return text_lf


# --------------------------------------------------------------------------
# Block-Erkennung im Rohtext (kein Re-Serialisieren der ganzen Datei)
# --------------------------------------------------------------------------

@dataclass
class Block:
    id: str
    start: int      # Index in `text` (LF-normalisiert), Blockanfang
    end: int         # Index direkt NACH dem abschließenden "."
    raw: str         # text[start:end]
    protected: bool  # unbekannte Prädikate / Kommentar / dreifach zitiertes Literal
    protect_reason: Optional[str] = None


_BLOCK_START_RE = re.compile(
    r"(?m)^ex:([A-Za-z_][A-Za-z0-9._\-]*)[ \t]+a[ \t]+skos:Concept[ \t]*;"
)


def _find_statement_end(text: str, search_from: int) -> int:
    """Findet das Ende der Turtle-Aussage (Index nach dem terminierenden '.'),
    beginnend bei `search_from`. Berücksichtigt einfache doppelte Anführungszeichen
    (mit Backslash-Escaping) und spitze Klammern <...> als String- bzw. URI-Bereiche,
    damit ein '.' *innerhalb* eines Literals oder einer URI nicht fälschlich als
    Aussagenende erkannt wird. Erkennt außerdem dreifach zitierte Literale, meldet
    deren Vorhandensein aber über eine Ausnahme, da solche Blöcke ohnehin geschützt
    werden (siehe `parse_block_for_protection`)."""
    i = search_from
    n = len(text)
    in_string = False
    in_uri = False
    while i < n:
        ch = text[i]
        if in_string:
            if ch == "\\":
                i += 2
                continue
            if ch == '"':
                in_string = False
            i += 1
            continue
        if in_uri:
            if ch == ">":
                in_uri = False
            i += 1
            continue
        if ch == '"':
            # Dreifach zitiertes Literal? Wird separat als "protected" erkannt;
            # hier robust überspringen bis zum schließenden """.
            if text[i:i + 3] == '"""':
                end_triple = text.find('"""', i + 3)
                if end_triple == -1:
                    # Kein Ende gefunden -> Block bis Dateiende als potentiell
                    # unsauber behandeln; Aufrufer erkennt das über die fehlende
                    # gültige Terminierung.
                    return n
                i = end_triple + 3
                continue
            in_string = True
            i += 1
            continue
        if ch == "<":
            in_uri = True
            i += 1
            continue
        if ch == ".":
            nxt = text[i + 1:i + 2]
            if nxt == "" or nxt.isspace():
                return i + 1
            i += 1
            continue
        i += 1
    raise FpvError("Kein abschließender Punkt für den Block gefunden (Datei evtl. unvollständig).")


def find_block(text: str, concept_id: str) -> Optional[Block]:
    """Sucht den Block einer bestimmten ID im (LF-normalisierten) Volltext."""
    pattern = re.compile(
        r"(?m)^ex:" + re.escape(concept_id) + r"[ \t]+a[ \t]+skos:Concept[ \t]*;"
    )
    m = pattern.search(text)
    if not m:
        return None
    start = m.start()
    end = _find_statement_end(text, m.end())
    raw = text[start:end]
    protected, reason = _classify_protection(raw)
    return Block(id=concept_id, start=start, end=end, raw=raw, protected=protected, protect_reason=reason)


def iter_all_blocks(text: str):
    """Iteriert über alle regulären Konzept-Blöcke im Volltext (in Dateireihenfolge)."""
    for m in _BLOCK_START_RE.finditer(text):
        cid = m.group(1)
        start = m.start()
        # Nur Blöcke berücksichtigen, deren Start wir noch nicht überholt haben
        # (falls sich Suchbereiche durch vorige _find_statement_end überlappen könnten).
        end = _find_statement_end(text, m.end())
        raw = text[start:end]
        protected, reason = _classify_protection(raw)
        yield Block(id=cid, start=start, end=end, raw=raw, protected=protected, protect_reason=reason)


def _split_top_level_statements(body: str):
    """Zerlegt den Blockkörper (NACH 'ex:ID a skos:Concept ;') an Top-Level-';'
    bzw. dem abschließenden '.', ohne ';'/'.' innerhalb von Strings oder URIs
    zu berücksichtigen. Liefert eine Liste von Segment-Strings (ohne den
    trennenden ';' bzw. abschließenden '.')."""
    segments = []
    buf = []
    in_string = False
    in_uri = False
    i = 0
    n = len(body)
    while i < n:
        ch = body[i]
        if in_string:
            buf.append(ch)
            if ch == "\\" and i + 1 < n:
                buf.append(body[i + 1])
                i += 2
                continue
            if ch == '"':
                in_string = False
            i += 1
            continue
        if in_uri:
            buf.append(ch)
            if ch == ">":
                in_uri = False
            i += 1
            continue
        if ch == '"':
            in_string = True
            buf.append(ch)
            i += 1
            continue
        if ch == "<":
            in_uri = True
            buf.append(ch)
            i += 1
            continue
        if ch == ";":
            segments.append("".join(buf))
            buf = []
            i += 1
            continue
        if ch == ".":
            nxt = body[i + 1:i + 2]
            if nxt == "" or nxt.isspace():
                segments.append("".join(buf))
                buf = []
                i += 1
                break
            buf.append(ch)
            i += 1
            continue
        buf.append(ch)
        i += 1
    tail = "".join(buf).strip()
    if tail:
        segments.append(tail)
    return [s.strip() for s in segments if s.strip()]


_LITERAL_RE = re.compile(
    r'^"((?:[^"\\]|\\.)*)"(?:@([A-Za-z\-]+)|\^\^([A-Za-z0-9:._\-]+))?$'
)
_URI_RE = re.compile(r"^<([^<>]*)>$")

# Objekte von skos:related sind praefixierte Namen (ex:ID), kommagetrennt
# mehrfach erlaubt. Turtle laesst dabei beliebigen Leerraum um das Komma zu.
_EX_REF_RE = re.compile(r"^ex:([A-Za-z_][A-Za-z0-9._\-]*)$")


def _parse_related_objects(value: str) -> list:
    """Zerlegt den Objektteil einer skos:related-Aussage in reine IDs.
    "ex:MBFR , ex:SALT" -> ["MBFR", "SALT"].
    Gibt None zurueck, wenn irgendein Objekt NICHT dem Muster ex:ID
    entspricht (z. B. eine volle <URI> oder ein fremdes Praefix) — dann
    darf der Block nicht ueber das Formular bearbeitet werden, weil das
    Formular solche Objekte nicht verlustfrei abbilden kann."""
    ids = []
    for part in value.split(","):
        part = part.strip()
        if not part:
            return None
        m = _EX_REF_RE.match(part)
        if not m:
            return None
        ids.append(m.group(1))
    return ids or None

# Erkennt eine einzelne skos:notation-Angabe im Rohtext eines Blocks, um ihren
# Datentyp zu prüfen — unabhängig vom Formularmodell, das den Datentyp beim
# Parsen verwirft und beim Rendern immer stillschweigend auf ^^fpv:entityType
# normalisiert (siehe render_record_to_block). validate_fpv.py prüft genau
# das explizit als Fehler ("Falscher Notation-Datentyp"), unser Parser bislang
# nicht — diese Lücke wird hier nachgezogen, siehe validate_whole_file.
_NOTATION_RE = re.compile(
    r'skos:notation\s+"((?:[^"\\]|\\.)*)"(?:\^\^([A-Za-z0-9:._\-]+))?'
)


def _classify_protection(raw_block: str):
    """Prüft, ob ein Block über das Formular sicher bearbeitbar ist.
    Gibt (protected: bool, reason: str|None) zurück."""
    if '"""' in raw_block or "'''" in raw_block:
        return True, "Der Block enthält ein dreifach zitiertes mehrzeiliges Literal."

    # '#' außerhalb von URIs/Strings gilt als Kommentar -> Block geschützt.
    in_string = False
    in_uri = False
    i = 0
    n = len(raw_block)
    while i < n:
        ch = raw_block[i]
        if in_string:
            if ch == "\\":
                i += 2
                continue
            if ch == '"':
                in_string = False
            i += 1
            continue
        if in_uri:
            if ch == ">":
                in_uri = False
            i += 1
            continue
        if ch == '"':
            in_string = True
        elif ch == "<":
            in_uri = True
        elif ch == "#":
            return True, "Der Block enthält ein '#' außerhalb von URI/Literal (Kommentar)."
        i += 1

    header_m = _BLOCK_START_RE.match(raw_block)
    if not header_m:
        return True, "Der Blockkopf entspricht nicht dem erwarteten Muster 'ex:ID a skos:Concept ;'."
    body = raw_block[header_m.end():]
    try:
        segments = _split_top_level_statements(body)
    except Exception:
        return True, "Der Blockkörper konnte nicht sicher in Einzelaussagen zerlegt werden."

    pref_count = 0
    notation_count = 0
    for seg in segments:
        seg = seg.strip()
        if not seg:
            continue
        parts = seg.split(None, 1)
        if not parts:
            continue
        predicate = parts[0]
        if predicate not in KNOWN_PREDICATES:
            return True, f"Unbekanntes Prädikat im Block: {predicate!r}."
        if predicate == "skos:prefLabel":
            pref_count += 1
        elif predicate == "skos:notation":
            notation_count += 1
        elif predicate == "skos:related":
            # Nur Objekte der Form ex:ID kann das Formular verlustfrei
            # darstellen und zurueckschreiben. Eine volle <URI> oder ein
            # fremdes Praefix wuerde beim Speichern still verschwinden —
            # deshalb in dem Fall lieber den Block schuetzen.
            value = parts[1].strip() if len(parts) > 1 else ""
            if _parse_related_objects(value) is None:
                return True, (
                    "skos:related enthält ein Objekt, das nicht dem Muster "
                    "ex:ID entspricht (z. B. eine vollständige URI); der Editor "
                    "bearbeitet solche Blöcke nicht, um die Angabe nicht zu verlieren."
                )

    # Der Editor verlangt für jeden von ihm bearbeiteten Block GENAU EIN
    # prefLabel (anders als das Referenzskript validate_fpv.py, das "höchstens
    # eines" prüft — siehe Übergabe §4). Bei mehr als einem Vorkommen würde ein
    # Speichern über das Formular eines der Labels klanglos verwerfen, da das
    # Formular nur ein einziges Eingabefeld anbietet. Um das zu verhindern,
    # wird ein solcher Block hier wie ein unbekanntes Prädikat behandelt und
    # NICHT über das Formular bearbeitet. Fehlt prefLabel ganz (0×), bleibt
    # der Block hingegen editierbar, damit genau diese Lücke behoben werden
    # kann; das wird stattdessen als Pflichtfeld-Fehler gemeldet.
    if pref_count > 1:
        return True, f"Block enthält {pref_count} skos:prefLabel-Angaben; der Editor bearbeitet nur Blöcke mit genau einer."

    # Dieselbe Absicherung für skos:notation, aus demselben Grund: Das Formular
    # bietet nur EIN Typcode-Feld an. validate_fpv.py selbst verbietet mehrere
    # skos:notation-Angaben pro Concept NICHT (es validiert dort jede einzeln,
    # ohne die Anzahl zu prüfen) — das ist also keine Anlehnung an dessen
    # Regelwerk, sondern eine eigenständige Schutzmaßnahme des Editors: Ohne
    # sie würde eine zweite Notation beim Speichern über das Formular
    # unbemerkt verworfen. Bei 0 Notationen bleibt der Block editierbar
    # (Pflichtfeld-Fehler wird stattdessen gemeldet).
    if notation_count > 1:
        return True, f"Block enthält {notation_count} skos:notation-Angaben; der Editor bearbeitet nur Blöcke mit genau einer."

    return False, None


# --------------------------------------------------------------------------
# Block-Text <-> Formularmodell (Record)
# --------------------------------------------------------------------------

@dataclass
class Record:
    id: str
    pref: str = ""
    lang: str = "de"
    type: str = ""
    note: str = ""
    synonym: bool = False
    alts: list = field(default_factory=list)
    # Jedes Element ist {"text": str, "lang": str}. Frueher war das eine reine
    # Stringliste, wobei beim Rendern fuer ALLE altLabels die Sprache des
    # prefLabel verwendet wurde — dadurch wurden z. B. "@en"-Benennungen beim
    # Speichern stillschweigend zu "@de" umgeschrieben (echter Datenverlust,
    # aufgefallen an einem realen Block mit deutschen UND englischen Labels).
    # Deshalb wird die Sprache jetzt je altLabel einzeln gefuehrt.
    exact: list = field(default_factory=list)
    close: list = field(default_factory=list)
    # Verweise auf ANDERE Concepts derselben Datei, als reine IDs ohne
    # "ex:"-Praefix (z. B. ["MBFR", "SALT"]). Das Praefix wird erst beim
    # Rendern wieder ergaenzt.
    related: list = field(default_factory=list)

    def to_json(self):
        return asdict(self)


def _unescape_literal(s: str) -> str:
    return s.replace('\\"', '"').replace("\\\\", "\\")


def _escape_literal(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


def parse_block_to_record(block: Block) -> Record:
    """Parst einen (nicht geschützten) Block in ein Formularmodell.
    Wirft ProtectedBlockError, falls der Block geschützt ist."""
    if block.protected:
        raise ProtectedBlockError(block.protect_reason or "Block ist geschützt.")

    header_m = _BLOCK_START_RE.match(block.raw)
    body = block.raw[header_m.end():]
    segments = _split_top_level_statements(body)

    rec = Record(id=block.id)
    pref_count = 0
    for seg in segments:
        parts = seg.strip().split(None, 1)
        if len(parts) != 2:
            continue
        predicate, value = parts[0], parts[1].strip()

        lit = _LITERAL_RE.match(value)
        uri = _URI_RE.match(value)

        if predicate == "skos:prefLabel":
            if lit:
                rec.pref = _unescape_literal(lit.group(1))
                if lit.group(2):
                    rec.lang = lit.group(2)
            pref_count += 1
        elif predicate == "skos:altLabel":
            if lit:
                rec.alts.append({
                    "text": _unescape_literal(lit.group(1)),
                    # Sprachkennzeichen des EINZELNEN altLabel bewahren.
                    # None heisst "im Quelltext nicht angegeben" und wird
                    # unten, nach dem Durchlauf aller Aussagen, auf die
                    # Sprache des Datensatzes gesetzt — erst dann steht
                    # rec.lang zuverlaessig fest (ein altLabel kann im
                    # Quelltext vor dem prefLabel stehen).
                    "lang": lit.group(2),
                })
        elif predicate == "skos:notation":
            if lit:
                rec.type = _unescape_literal(lit.group(1))
        elif predicate == "ex:useInSynonymList":
            if lit:
                rec.synonym = lit.group(1).strip().lower() == "true"
        elif predicate == "skos:exactMatch":
            if uri:
                rec.exact.append(uri.group(1))
        elif predicate == "skos:closeMatch":
            if uri:
                rec.close.append(uri.group(1))
        elif predicate == "skos:note":
            if lit:
                rec.note = _unescape_literal(lit.group(1))
        elif predicate == "skos:related":
            ids = _parse_related_objects(value)
            if ids:
                rec.related.extend(ids)
    for alt in rec.alts:
        if not alt.get("lang"):
            alt["lang"] = rec.lang
    return rec


def _alt_parts(alt, default_lang: str):
    """Normalisiert einen altLabel-Eintrag zu (text, lang).
    Akzeptiert sowohl das aktuelle Format {"text":..., "lang":...} als auch
    einen reinen String (aeltere Clients / aeltere gespeicherte Formulardaten),
    damit ein alter Frontend-Stand nicht stillschweigend Sprachen verliert."""
    if isinstance(alt, dict):
        text = str(alt.get("text", "")).strip()
        lang = str(alt.get("lang") or "").strip() or default_lang
        return text, lang
    return str(alt).strip(), default_lang


def render_record_to_block(rec: Record) -> str:
    """Rendert ein Formularmodell zurück in Turtle-Blocktext (LF-Zeilenenden,
    2-Leerzeichen-Einrückung wie im Bestand üblich)."""
    lines = [f"ex:{rec.id} a skos:Concept ;"]
    lines.append(f'  skos:prefLabel "{_escape_literal(rec.pref)}"@{rec.lang} ;')
    for alt in rec.alts:
        text, lang = _alt_parts(alt, rec.lang)
        lines.append(f'  skos:altLabel "{_escape_literal(text)}"@{lang} ;')
    lines.append(f'  skos:notation "{rec.type}"^^fpv:entityType ;')
    lines.append(f'  ex:useInSynonymList "{"true" if rec.synonym else "false"}"^^xsd:boolean ;')
    for uri in rec.exact:
        lines.append(f"  skos:exactMatch <{uri}> ;")
    for uri in rec.close:
        lines.append(f"  skos:closeMatch <{uri}> ;")
    if rec.related:
        # Kommagetrennte Objektliste, wie in Turtle üblich und wie im
        # Bestand vorgefunden: "skos:related ex:MBFR , ex:SALT ;"
        refs = " , ".join(f"ex:{rid}" for rid in rec.related)
        lines.append(f"  skos:related {refs} ;")
    # letzte Zeile: note, mit abschließendem Punkt statt Semikolon
    lines.append(f'  skos:note "{_escape_literal(rec.note)}"@de .')
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------
# Validierung
# --------------------------------------------------------------------------

@dataclass
class Finding:
    level: str   # "error" | "warning"
    message: str
    concept_id: Optional[str] = None
    # Nur bei Befunden, die MEHRERE Konzepte betreffen (z. B. dieselbe Benennung
    # in der Synonymliste): alle beteiligten IDs. `concept_id` ist dann das erste.
    concept_ids: Optional[list] = None

    def to_json(self):
        return asdict(self)


def validate_record_fields(rec: Record, *, is_new: bool, existing_ids: set) -> list:
    """Feldvalidierung eines einzelnen Datensatzes (wie sie das Formular vor dem
    Speichern durchsetzt). Gibt eine Liste von Finding zurück."""
    findings = []

    if not ID_PATTERN.match(rec.id or ""):
        findings.append(Finding(
            "error",
            "ID muss dem Muster [A-Za-z_][A-Za-z0-9._-]* entsprechen "
            "(keine Umlaute, keine Leerzeichen).",
            rec.id,
        ))
    if is_new and rec.id in existing_ids:
        findings.append(Finding("error", f"ID '{rec.id}' ist bereits vergeben.", rec.id))

    if not rec.pref or not rec.pref.strip():
        findings.append(Finding("error", "skos:prefLabel ist erforderlich (genau eines).", rec.id))

    if rec.type not in TYPE_CODES:
        findings.append(Finding(
            "error",
            f"Typcode '{rec.type}' ist ungültig. Erlaubt: {', '.join(sorted(TYPE_CODES))}.",
            rec.id,
        ))

    if not rec.note or not rec.note.strip():
        findings.append(Finding("error", "skos:note ist erforderlich und darf nicht leer sein.", rec.id))

    if not isinstance(rec.synonym, bool):
        findings.append(Finding("error", "ex:useInSynonymList muss ein Wahrheitswert sein.", rec.id))

    for uri in rec.exact:
        if not (uri.startswith("http://") or uri.startswith("https://")):
            findings.append(Finding("error", f"exactMatch-Link ungültig (kein http/https): {uri}", rec.id))
    for uri in rec.close:
        if not (uri.startswith("http://") or uri.startswith("https://")):
            findings.append(Finding("error", f"closeMatch-Link ungültig (kein http/https): {uri}", rec.id))

    for rid in rec.related:
        if not ID_PATTERN.match(rid):
            findings.append(Finding(
                "error",
                f"skos:related verweist auf eine ungültige ID: {rid}",
                rec.id,
            ))
        elif rid == rec.id:
            findings.append(Finding(
                "error",
                "skos:related verweist auf den Eintrag selbst.",
                rec.id,
            ))
        elif existing_ids and rid not in existing_ids:
            # Nur als Warnung: Ein Verweis auf eine (noch) nicht vorhandene ID
            # ist inhaltlich fragwuerdig, aber syntaktisch gueltiges Turtle und
            # darf das Speichern nicht blockieren.
            findings.append(Finding(
                "warning",
                f"skos:related verweist auf '{rid}', wozu es in dieser Datei keinen Eintrag gibt.",
                rec.id,
            ))

    return findings


def validate_whole_file(text: str) -> list:
    """Prüft die gesamte Datei: doppelte IDs im Quelltext (auch wenn RDF-Set-
    Semantik identische Tripel zusammenfassen und eine reine Tripelzählung sie
    übersehen würde — siehe Übergabe §2), strukturelle Turtle-Gültigkeit via
    RDFLib, sowie Feldregeln je nicht geschütztem Block."""
    findings = []

    # 1) Doppelte IDs im Quelltext (Regex-Scan, unabhängig vom RDF-Graph).
    seen = {}
    for m in _BLOCK_START_RE.finditer(text):
        cid = m.group(1)
        seen.setdefault(cid, 0)
        seen[cid] += 1
    for cid, count in seen.items():
        if count > 1:
            findings.append(Finding(
                "error",
                f"ID '{cid}' kommt {count}-mal als Blockanfang im Quelltext vor "
                "(Duplikat im Text; durch RDF-Set-Semantik ggf. bei reiner "
                "Tripelzählung nicht sichtbar).",
                cid,
            ))

    # 2) Strukturelle Gültigkeit via RDFLib.
    g = Graph()
    try:
        g.parse(data=text, format="turtle")
    except Exception as exc:
        findings.append(Finding("error", f"Turtle ist syntaktisch ungültig: {exc}"))
        return findings  # Feldprüfung ohne gültiges Parsing wenig sinnvoll

    # 3) Feldregeln je Block.
    existing_ids = set(seen.keys())
    for block in iter_all_blocks(text):
        if block.protected:
            findings.append(Finding(
                "warning",
                f"Block wird zum Schutz vor Informationsverlust nicht geprüft: {block.protect_reason}",
                block.id,
            ))
            continue
        try:
            rec = parse_block_to_record(block)
        except ProtectedBlockError as exc:
            findings.append(Finding("warning", str(exc), block.id))
            continue
        findings.extend(validate_record_fields(rec, is_new=False, existing_ids=existing_ids))

        # Datentyp von skos:notation prüfen (siehe _NOTATION_RE oben). Das
        # Formularmodell (Record.type) kennt nur den reinen Wert, nicht das
        # ^^-Suffix; ein falscher/fehlender Datentyp im BESTEHENDEN Rohtext
        # würde also sonst unbemerkt bleiben und beim nächsten Speichern
        # stillschweigend auf ^^fpv:entityType korrigiert, statt dem Nutzer
        # gemeldet zu werden.
        for m in _NOTATION_RE.finditer(block.raw):
            datatype = m.group(2)
            if datatype is None:
                findings.append(Finding(
                    "error",
                    f"skos:notation \"{m.group(1)}\" ohne Datentyp-Angabe "
                    "(erwartet ^^fpv:entityType).",
                    block.id,
                ))
            elif datatype != "fpv:entityType":
                findings.append(Finding(
                    "error",
                    f"skos:notation \"{m.group(1)}\" hat den Datentyp "
                    f"^^{datatype} statt des erwarteten ^^fpv:entityType.",
                    block.id,
                ))

    # 4) Synonymliste: dieselbe Benennung bei mehreren Konzepten. Als HINWEIS,
    #    nicht als Fehler: vorhandene Altlasten duerfen das Speichern anderer
    #    Aenderungen nicht blockieren. NEU entstehende Kollisionen blockiert
    #    api_save gesondert (siehe synonym_conflicts_for_record).
    try:
        syn_index = build_synonym_index_from_graph(g)
    except Exception:  # pragma: no cover - defensiv, Graph wurde oben schon geparst
        syn_index = {}
    for group in synonym_collision_groups_by_concepts(syn_index):
        findings.append(Finding(
            "warning",
            synonym_group_message(group, syn_index),
            group["concepts"][0],
            list(group["concepts"]),
        ))

    return findings


# --------------------------------------------------------------------------
# Synonymliste (Typesense): dieselbe Benennung bei zwei Konzepten
# --------------------------------------------------------------------------
#
# Hintergrund: Ein externes Script (ttl2jsonl.py) baut aus jedem Konzept mit
#   ex:useInSynonymList "true"^^xsd:boolean
# ein Synonymset {id, synonyms: [alle prefLabel + altLabel]} fuer Typesense.
# Steht dieselbe Benennung (z. B. eine Abkuerzung) in den Sets zweier Konzepte,
# findet die Suche danach beide ("BMW" -> Autobauer UND Missionswerk). Das soll
# nicht passieren.
#
# Die Regeln unten SPIEGELN ttl2jsonl.py, damit der Editor genau das prueft,
# was spaeter in Typesense landet (gelesen wird der RDF-Graph, also auch
# geschuetzte Bloecke):
#   - nur Konzepte mit dem Wahrheitswert true,
#   - Benennungen aller Sprachen, nur strip()-bereinigt,
#   - Benennungen in SYNONYM_BLACKLIST oder mit Laenge <= 1 entfallen,
#   - ein Set entsteht erst ab 2 verbleibenden Benennungen.
# Zusaetzlich beim VERGLEICH (nicht im Set): Unicode NFC, Leerraum
# zusammengefasst, Gross-/Kleinschreibung ignoriert. Nicht geprueft ist, wie
# Typesense Gross-/Kleinschreibung bei Synonymen behandelt; der vorsichtige
# Vergleich ist die sichere Seite ("mopo" soll nicht beide Zeitungen finden).
# Aendert sich das Script, muss dieser Abschnitt mitgezogen werden.

SYNONYM_BLACKLIST = frozenset({"pol", "com", "soc", "news", "topic", "law", "org"})
EX_USE_IN_SYNONYM_LIST = EX_NS.useInSynonymList


@dataclass
class SynonymEntry:
    pref: str
    labels: list


def synonym_effective_labels(labels, active: bool) -> list:
    """Die Benennungen, die tatsaechlich im Synonymset landen (leer, wenn keines
    entsteht)."""
    if not active:
        return []
    cleaned = {str(l).strip() for l in labels}
    cleaned = {l for l in cleaned if l.lower() not in SYNONYM_BLACKLIST and len(l) > 1}
    return sorted(cleaned) if len(cleaned) >= 2 else []


def synonym_key(label: str) -> str:
    """Vergleichsschluessel: NFC, Leerraum zusammengefasst, casefold."""
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", label)).strip().casefold()


def build_synonym_index_from_graph(g) -> dict:
    """Konzept-ID -> SynonymEntry fuer alle Konzepte, die ein Synonymset bekaeme."""
    index = {}
    active = Literal(True, datatype=XSD_NS.boolean)
    for concept in set(g.subjects(SKOS_NS.prefLabel, None)):
        if (concept, EX_USE_IN_SYNONYM_LIST, active) not in g:
            continue
        prefs = sorted(str(o) for o in g.objects(concept, SKOS_NS.prefLabel) if isinstance(o, Literal))
        alts = [str(o) for o in g.objects(concept, SKOS_NS.altLabel) if isinstance(o, Literal)]
        labels = synonym_effective_labels(prefs + alts, True)
        if not labels:
            continue
        uri = str(concept)
        cid = uri[len(EX):] if uri.startswith(EX) else uri
        index[cid] = SynonymEntry(pref=prefs[0] if prefs else cid, labels=labels)
    return index


def build_synonym_index(text: str) -> dict:
    g = Graph()
    g.parse(data=text, format="turtle")
    return build_synonym_index_from_graph(g)


def _synonym_members(index: dict) -> dict:
    """Vergleichsschluessel -> {Konzept-ID: {Schreibweisen}}."""
    by_key = {}
    for cid, entry in index.items():
        for label in entry.labels:
            by_key.setdefault(synonym_key(label), {}).setdefault(cid, set()).add(label)
    return by_key


def _by_id(ids):
    return sorted(ids, key=lambda c: (c.casefold(), c))


def synonym_collision_groups(index: dict) -> list:
    """Alle Benennungen, die in mehr als einem Synonymset vorkommen."""
    groups = []
    for key, members in sorted(_synonym_members(index).items()):
        if len(members) > 1:
            groups.append({
                "key": key,
                "labels": sorted({l for spellings in members.values() for l in spellings}),
                "concepts": _by_id(members),
            })
    return groups


def synonym_collision_groups_by_concepts(index: dict) -> list:
    """Wie synonym_collision_groups, aber je Konzept-Paarung EIN Eintrag: Teilen
    zwei Konzepte mehrere Benennungen (z. B. Abkuerzung und Langform bei einer
    Doppelanlage), erscheinen sie gemeinsam statt mehrfach."""
    merged = {}
    for group in synonym_collision_groups(index):
        entry = merged.setdefault(
            tuple(group["concepts"]),
            {"concepts": group["concepts"], "labels": [], "keys": 0},
        )
        entry["labels"] = sorted(set(entry["labels"]) | set(group["labels"]))
        entry["keys"] += 1
    return sorted(merged.values(), key=lambda g: (g["concepts"][0].casefold(), g["concepts"]))


def synonym_group_message(group: dict, index: dict) -> str:
    """Kurztext fuer die Befundliste; die IDs stehen dort als Links daneben."""
    quoted = " / ".join(f"\u201e{l}\u201c" for l in group["labels"])
    verb = "stehen" if group.get("keys", 1) > 1 else "steht"
    names = "; ".join(index[c].pref for c in group["concepts"])
    return (
        f"{quoted} {verb} bei {len(group['concepts'])} Konzepten der Synonymliste "
        f"(die Suche findet alle): {names}."
    )


def _synonym_pairs(index: dict, concept_id: str) -> set:
    entry = index.get(concept_id)
    if not entry:
        return set()
    members = _synonym_members(index)
    pairs = set()
    for label in entry.labels:
        key = synonym_key(label)
        for other in members.get(key, {}):
            if other != concept_id:
                pairs.add((key, other))
    return pairs


def synonym_conflicts_for_record(base_index: dict, concept_id: str, pref: str, alt_texts, active: bool) -> list:
    """Kollisionen eines (bearbeiteten) Konzepts mit anderen. `base_index` ist der
    gespeicherte Stand der Datei; das Konzept wird darin durch die neuen Werte
    ersetzt. `is_new` = die Kollision besteht im gespeicherten Stand noch nicht
    (nur diese blockieren das Speichern; Altlasten nicht)."""
    new_labels = synonym_effective_labels([pref] + list(alt_texts), active)
    new_index = {c: e for c, e in base_index.items() if c != concept_id}
    if new_labels:
        new_index[concept_id] = SynonymEntry(pref=pref, labels=new_labels)
    old_pairs = _synonym_pairs(base_index, concept_id)
    members = _synonym_members(new_index)

    result, seen = [], set()
    for label in new_labels:
        key = synonym_key(label)
        for other_id in _by_id(members.get(key, {})):
            if other_id == concept_id or (key, other_id) in seen:
                continue
            seen.add((key, other_id))
            spellings = members[key][other_id]
            result.append({
                "label": label,
                "other_id": other_id,
                "other_pref": new_index[other_id].pref,
                "other_label": label if label in spellings else sorted(spellings)[0],
                "is_new": (key, other_id) not in old_pairs,
            })
    return result


def synonym_conflicts_for_batch(base_index: dict, edits: list) -> list:
    """Wie synonym_conflicts_for_record, aber für mehrere gleichzeitig
    geänderte Konzepte. `edits` = Liste von (concept_id, pref, alt_texts,
    active). Alle Änderungen werden gemeinsam in den gespeicherten Stand
    (`base_index`) eingesetzt; so fallen auch Kollisionen der geänderten
    Konzepte untereinander auf. Jede Kollision nennt das geänderte Konzept
    (`concept_id`); `is_new` = im gespeicherten Stand noch nicht vorhanden."""
    edited_ids = {cid for cid, _p, _a, _act in edits}
    new_index = {c: e for c, e in base_index.items() if c not in edited_ids}
    new_labels_by_id = {}
    for cid, pref, alt_texts, active in edits:
        labels = synonym_effective_labels([pref] + list(alt_texts), active)
        new_labels_by_id[cid] = labels
        if labels:
            new_index[cid] = SynonymEntry(pref=pref, labels=labels)
    members = _synonym_members(new_index)

    result = []
    for cid, _pref, _alts, _active in edits:
        old_pairs = _synonym_pairs(base_index, cid)
        seen = set()
        for label in new_labels_by_id[cid]:
            key = synonym_key(label)
            for other_id in _by_id(members.get(key, {})):
                if other_id == cid or (key, other_id) in seen:
                    continue
                seen.add((key, other_id))
                spellings = members[key][other_id]
                result.append({
                    "concept_id": cid,
                    "label": label,
                    "other_id": other_id,
                    "other_pref": new_index[other_id].pref,
                    "other_label": label if label in spellings else sorted(spellings)[0],
                    "is_new": (key, other_id) not in old_pairs,
                })
    return result


def synonym_conflict_message(c: dict) -> str:
    """Einzelmeldung je Kollision; die Handlungsanweisung steht einmal in der
    Gesamtmeldung (app.py), nicht bei jeder Kollision."""
    text = f"\u201e{c['label']}\u201c steht auch bei ex:{c['other_id']} ({c['other_pref']})"
    if c["other_label"] != c["label"]:
        text += f" (dort: \u201e{c['other_label']}\u201c; Gro\u00df-/Kleinschreibung z\u00e4hlt nicht als Unterschied)"
    return text + ", das ebenfalls in der Synonymliste verwendet wird."


def find_referencing_subjects(text: str, concept_id: str) -> list:
    """Findet andere RDF-Knoten, die per URI <.../id/CONCEPT_ID> auf die ID
    verweisen (z. B. exactMatch/closeMatch anderer Konzepte, oder ein
    zukünftiges skos:broader). Nutzt den geparsten Graphen, nicht nur den
    eigenen Block, damit Verweise aus der GESAMTEN Datei erkannt werden."""
    g = Graph()
    g.parse(data=text, format="turtle")
    target = URIRef(EX + concept_id)
    own_subject = target
    refs = []
    for s, p, o in g.triples((None, None, target)):
        if s == own_subject:
            continue
        refs.append(f"{s} {p}")
    return refs


# --------------------------------------------------------------------------
# ID umbenennen (bewusste Sonderaktion, siehe app.py /api/rename)
# --------------------------------------------------------------------------
#
# Eine ID ist Teil der URI des Konzepts (EX + ID). Beim Umbenennen muessen
# deshalb der Block selbst UND alle Verweise in anderen Bloecken mitgezogen
# werden. Das geschieht bewusst per gezieltem Textersatz (nicht durch neues
# Rendern), damit Formatierung und Reihenfolge aller Bloecke erhalten bleiben.
# Verweise, die in geschuetzten Bloecken stehen, werden NICHT angefasst; dann
# wird das Umbenennen abgelehnt (der Editor veraendert geschuetzte Bloecke nie).
# Verwendungen AUSSERHALB dieser Datei (Edition, Typesense, ...) sind fuer den
# Editor weder sichtbar noch aenderbar.

def _rename_in_block_text(raw: str, old_id: str, new_id: str):
    """Ersetzt `ex:OLD` (ausserhalb von Literalen und <URIs>) sowie die
    vollstaendige URI `<EX+OLD>` durch die neue ID. Gibt (neuer_text, anzahl)
    zurueck. Namensgrenzen: `ex:OLD` darf nicht Praefix von `ex:OLDER` sein."""
    old_tok = "ex:" + old_id
    old_uri = EX + old_id
    new_uri = EX + new_id
    out = []
    i = 0
    n = len(raw)
    count = 0
    in_string = False
    while i < n:
        ch = raw[i]
        if in_string:
            out.append(ch)
            if ch == "\\" and i + 1 < n:
                out.append(raw[i + 1])
                i += 2
                continue
            if ch == '"':
                in_string = False
            i += 1
            continue
        if ch == '"':
            in_string = True
            out.append(ch)
            i += 1
            continue
        if ch == "<":
            j = raw.find(">", i + 1)
            if j == -1:
                out.append(raw[i:])
                break
            if raw[i + 1:j] == old_uri:
                out.append("<" + new_uri + ">")
                count += 1
            else:
                out.append(raw[i:j + 1])
            i = j + 1
            continue
        if raw.startswith(old_tok, i):
            prev = raw[i - 1] if i > 0 else ""
            after = raw[i + len(old_tok):i + len(old_tok) + 2]
            n1, n2 = after[:1], after[1:2]
            # Achtung: "" in "abc" ist in Python wahr; leere Zeichen (Textanfang/-ende)
            # muessen deshalb ausdruecklich als "kein Namenszeichen" behandelt werden.
            def _name_char(c):
                return bool(c) and (c.isalnum() or c in "_-")
            prev_ok = not (_name_char(prev) or prev in (".", ":"))
            next_ok = not (_name_char(n1) or (n1 == "." and _name_char(n2)))
            if prev_ok and next_ok:
                out.append("ex:" + new_id)
                count += 1
                i += len(old_tok)
                continue
        out.append(ch)
        i += 1
    return "".join(out), count


def plan_rename(text: str, old_id: str):
    """Ermittelt, was ein Umbenennen betrifft. Rueckgabe: (block, referrers,
    blocked). `referrers` = bearbeitbare Bloecke, die auf die ID verweisen;
    `blocked` = Liste {id, reason} fuer Verweise, die nicht sicher angepasst
    werden koennen (geschuetzter Block oder Verweis ausserhalb eines Blocks)."""
    block = find_block(text, old_id)
    if block is None:
        raise FpvError(f"Block '{old_id}' nicht gefunden.")
    if block.protected:
        raise ProtectedBlockError(
            "Der Eintrag ist geschützt; die Kennung kann nur in einem Texteditor geändert werden. "
            + (block.protect_reason or "")
        )
    g = Graph()
    g.parse(data=text, format="turtle")
    target = URIRef(EX + old_id)
    subjects = {str(s) for s, _p, _o in g.triples((None, None, target)) if s != target}
    referrers = []
    blocked = []
    for subj in sorted(subjects):
        if subj.startswith(EX):
            cid = subj[len(EX):]
            b = find_block(text, cid)
        else:
            cid, b = subj, None
        if b is None:
            blocked.append({"id": cid, "reason": "Der Verweis steht nicht in einem regulären Konzept-Block."})
        elif b.protected:
            blocked.append({"id": cid, "reason": b.protect_reason or "Der Block ist geschützt."})
        else:
            referrers.append(b)
    return block, referrers, blocked


def check_new_id(text: str, old_id: str, new_id: str) -> Optional[str]:
    """Gibt eine Fehlermeldung zurueck, wenn `new_id` nicht verwendbar ist."""
    if not ID_PATTERN.match(new_id or ""):
        return "Die neue Kennung darf nur Buchstaben (ohne Umlaute), Ziffern sowie . _ - enthalten und muss mit Buchstabe oder _ beginnen."
    if new_id == old_id:
        return "Die neue Kennung ist gleich der bisherigen."
    existing = {m.group(1) for m in _BLOCK_START_RE.finditer(text)}
    if new_id in existing:
        return f"Die Kennung '{new_id}' ist bereits vergeben."
    g = Graph()
    g.parse(data=text, format="turtle")
    uri = URIRef(EX + new_id)
    if (uri, None, None) in g or (None, None, uri) in g:
        return f"Die Kennung '{new_id}' wird in der Datei bereits verwendet (z. B. als Verweisziel)."
    return None


def rename_concept(text: str, old_id: str, new_id: str):
    """Benennt ein Konzept um und zieht alle Verweise in bearbeitbaren Bloecken
    mit. Gibt (neuer_volltext, [ids der angepassten Verweis-Bloecke]) zurueck.
    Vor der Rueckgabe wird bewiesen, dass der RDF-Graph des neuen Textes exakt
    dem alten Graphen entspricht, in dem nur die URI der ID ersetzt wurde."""
    problem = check_new_id(text, old_id, new_id)
    if problem:
        raise FpvError(problem)
    block, referrers, blocked = plan_rename(text, old_id)
    if blocked:
        listing = "; ".join(f"{b['id']} ({b['reason']})" for b in blocked[:5])
        raise ReferencedError(
            f"Umbenennen abgelehnt: {len(blocked)} Verweis(e) stehen in Blöcken, die der Editor nicht ändert: "
            + listing + (" …" if len(blocked) > 5 else "")
        )
    edits = []
    for b in [block] + referrers:
        new_raw, count = _rename_in_block_text(b.raw, old_id, new_id)
        if count == 0:
            raise FpvError(f"Interner Fehler: in Block '{b.id}' wurde kein Vorkommen der ID gefunden.")
        edits.append((b.start, b.end, new_raw))
    new_text = text
    for start, end, new_raw in sorted(edits, key=lambda e: -e[0]):
        new_text = new_text[:start] + new_raw + new_text[end:]

    # Beweis: nur die ID hat sich geaendert.
    from rdflib.compare import isomorphic
    g_old = Graph()
    g_old.parse(data=text, format="turtle")
    g_new = Graph()
    g_new.parse(data=new_text, format="turtle")
    old_uri, new_uri = URIRef(EX + old_id), URIRef(EX + new_id)

    def mapped(term):
        return new_uri if term == old_uri else term

    expected = Graph()
    for s_, p_, o_ in g_old:
        expected.add((mapped(s_), p_, mapped(o_)))
    if not isomorphic(expected, g_new):
        raise FpvError("Interne Prüfung fehlgeschlagen: Das Umbenennen hätte mehr als die Kennung verändert. Es wurde nichts geschrieben.")
    if find_block(new_text, old_id) is not None or find_referencing_subjects(new_text, old_id):
        raise FpvError("Interne Prüfung fehlgeschlagen: Die alte Kennung kommt noch vor. Es wurde nichts geschrieben.")
    return new_text, [b.id for b in referrers]


# --------------------------------------------------------------------------
# Sicherungsorte (Kaskade) und geprüfte Sicherung
# --------------------------------------------------------------------------

def file_key(ttl_path: str) -> str:
    """Stabiler kurzer Schlüssel aus dem Pfad der TTL-Datei, für Sicherungs-
    Unterordner und Dateinamen."""
    norm = os.path.normcase(os.path.abspath(ttl_path))
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()[:12]


def _env_dir(name: str) -> Optional[str]:
    val = os.environ.get(name)
    return val if val else None


def _downloads_dir() -> Optional[str]:
    home = os.environ.get("USERPROFILE") or os.environ.get("HOME")
    if not home:
        return None
    return os.path.join(home, "Downloads")


def _program_dir() -> str:
    """Ordner der laufenden Anwendung (EXE-Ordner im PyInstaller-Build,
    sonst Ordner dieses Quellcode-Moduls)."""
    import sys
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def backup_candidate_locations(ttl_path: str, manual_dir: Optional[str] = None) -> list:
    """Liefert die Kandidatenorte für Sicherungen IN DER FESTEN REIHENFOLGE
    aus Übergabe §5: manuell gewählt -> fpv_backups neben TTL -> TTL-Ordner
    -> %LOCALAPPDATA%\\FPV-Editor\\backups\\<key> -> %LOCALAPPDATA%
    -> Downloads -> fpv_backups im Programmordner -> Programmordner
    -> %TEMP%\\FPV-Editor\\backups\\<key> -> %TEMP%.
    Jeder Eintrag ist ein Tupel (label, path)."""
    ttl_dir = os.path.dirname(os.path.abspath(ttl_path))
    key = file_key(ttl_path)
    prog_dir = _program_dir()

    candidates = []
    if manual_dir:
        candidates.append(("manuell gewählter Ordner", manual_dir))
    candidates.append(("fpv_backups neben der TTL", os.path.join(ttl_dir, "fpv_backups")))
    candidates.append(("TTL-Ordner", ttl_dir))

    localappdata = _env_dir("LOCALAPPDATA")
    if localappdata:
        candidates.append((
            "%LOCALAPPDATA%\\FPV-Editor\\backups\\<Dateischlüssel>",
            os.path.join(localappdata, "FPV-Editor", "backups", key),
        ))
        candidates.append(("%LOCALAPPDATA%", localappdata))

    downloads = _downloads_dir()
    if downloads:
        candidates.append(("Downloads", downloads))

    candidates.append(("fpv_backups im Programmordner", os.path.join(prog_dir, "fpv_backups")))
    candidates.append(("Programmordner", prog_dir))

    temp = _env_dir("TEMP") or _env_dir("TMP") or tempfile.gettempdir()
    if temp:
        candidates.append((
            "%TEMP%\\FPV-Editor\\backups\\<Dateischlüssel>",
            os.path.join(temp, "FPV-Editor", "backups", key),
        ))
        candidates.append(("%TEMP%", temp))

    # Dedupliziert nach tatsächlichem (normalisiertem) Pfad, damit z. B. ein
    # manuell gewählter Ordner, der zufällig mit einem anderen Kandidaten
    # übereinstimmt, nicht doppelt versucht wird und Sicherungen später nicht
    # doppelt gelistet werden. Die erste (bevorzugte) Bezeichnung gewinnt.
    seen_paths = set()
    deduped = []
    for label, path in candidates:
        norm = os.path.normcase(os.path.abspath(path))
        if norm in seen_paths:
            continue
        seen_paths.add(norm)
        deduped.append((label, path))
    return deduped


def _try_write_readback(dir_path: str, data: bytes, filename: str, errors: Optional[list] = None) -> Optional[str]:
    """Versucht, `data` unter `dir_path/filename` zu schreiben, zu flushen,
    fsync'en und zurückzulesen; vergleicht Bytes. Gibt den vollen Pfad bei
    Erfolg zurück, sonst None (bei jedem OSError/PermissionError). Die
    Fehlerursache wird, falls `errors` übergeben ist, dort angehängt."""
    try:
        os.makedirs(dir_path, exist_ok=True)
        full_path = os.path.join(dir_path, filename)
        with open(full_path, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        with open(full_path, "rb") as f:
            readback = f.read()
        if readback != data:
            try:
                os.remove(full_path)
            except OSError:
                pass
            if errors is not None:
                errors.append("Rücklesen stimmte nicht mit den geschriebenen Bytes überein")
            return None
        return full_path
    except OSError as exc:
        if errors is not None:
            errors.append(f"{type(exc).__name__}: {exc}")
        return None


def app_data_dir() -> str:
    """Datenordner des Editors (Sicherungen, Zwischensicherung):
    %LOCALAPPDATA%\\FPV-Editor, sonst ~/.fpv-editor."""
    base = _env_dir("LOCALAPPDATA")
    if base:
        return os.path.join(base, "FPV-Editor")
    return os.path.join(os.path.expanduser("~"), ".fpv-editor")


# --------------------------------------------------------------------------
# Zwischensicherung (Autorecovery) nicht gespeicherter Eintraege
# --------------------------------------------------------------------------
# Enthaelt NUR die vorgemerkten Formularstaende ({original_id, data}), nie die
# TTL selbst. Sie liegt neben den Sicherungen im Datenordner, je TTL-Datei eine
# Datei, und wird nach dem Speichern, beim bewussten Verwerfen und beim
# Beenden ohne Speichern geloescht.

def recovery_file_path(ttl_path: str) -> str:
    return os.path.join(app_data_dir(), "recovery", f"{file_key(ttl_path)}.json")


def write_recovery(ttl_path: str, version: str, items: list) -> dict:
    """Schreibt die Zwischensicherung atomar (temp + os.replace). Gibt
    {"path", "saved_at"} zurueck oder wirft OSError."""
    import json as _json
    path = recovery_file_path(ttl_path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    payload = {
        "format": 1,
        "ttl_path": os.path.abspath(ttl_path),
        "version": version,
        "saved_at": time.time(),
        "items": items,
    }
    fd, tmp = tempfile.mkstemp(prefix=".recovery-", suffix=".tmp", dir=os.path.dirname(path))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            _json.dump(payload, f, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except OSError:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise
    return {"path": path, "saved_at": payload["saved_at"]}


def read_recovery(ttl_path: str) -> Optional[dict]:
    """Liest die Zwischensicherung dieser TTL; None, wenn es keine gibt oder sie
    nicht lesbar/ungueltig ist."""
    import json as _json
    try:
        with open(recovery_file_path(ttl_path), "r", encoding="utf-8") as f:
            data = _json.load(f)
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or not isinstance(data.get("items"), list):
        return None
    return data


def clear_recovery(ttl_path: str) -> bool:
    try:
        os.remove(recovery_file_path(ttl_path))
        return True
    except OSError:
        return False


def backup_write_location(ttl_path: str, manual_dir: Optional[str] = None) -> tuple:
    """Der EINE Ort, an dem eine neue Sicherung angelegt wird: der manuell
    gewählte Ordner, sonst %LOCALAPPDATA%\\FPV-Editor\\backups\\<Dateischlüssel>
    (beschreibbar ohne Administratorrechte, außerhalb eines Git-Arbeitsordners).
    Es gibt bewusst keine Ausweichkaskade mehr: Scheitert dieser Ort, bleibt die
    TTL unverändert und der Nutzer wählt über „Sicherungsort wählen“ einen
    anderen Ordner. Vorhandene ältere Sicherungen an den früheren Orten
    bleiben über list_backups() weiter auffindbar."""
    if manual_dir:
        return ("manuell gewählter Ordner", manual_dir)
    key = file_key(ttl_path)
    return (
        "%LOCALAPPDATA%\\FPV-Editor\\backups\\<Dateischlüssel>" if _env_dir("LOCALAPPDATA")
        else "Benutzerordner\\.fpv-editor\\backups\\<Dateischlüssel>",
        os.path.join(app_data_dir(), "backups", key),
    )


def create_verified_backup(ttl_path: str, raw_bytes: bytes, manual_dir: Optional[str] = None):
    """Erstellt eine geprüfte (schreib-lese-verglichene) Sicherung der ALTEN
    Bytes an EINEM Ort (siehe backup_write_location). Gibt (label, path)
    zurück oder wirft BackupError — dann darf die TTL nicht verändert werden."""
    import secrets as _secrets
    ts = time.strftime("%Y%m%d-%H%M%S")
    key = file_key(ttl_path)
    # Zufälliges Suffix, damit mehrere Sicherungen INNERHALB DERSELBEN SEKUNDE
    # sich nicht gegenseitig überschreiben.
    filename = f"fpv-{ts}-{_secrets.token_hex(4)}-{key}.ttl.bak"

    label, path = backup_write_location(ttl_path, manual_dir)
    errors: list = []
    result = _try_write_readback(path, raw_bytes, filename, errors)
    if result:
        return label, result
    raise BackupError(
        "Die Sicherung konnte nicht angelegt werden, die Datei wurde NICHT verändert.\n"
        f"Ort: {path}\nGrund: {errors[0] if errors else 'unbekannt'}\n\n"
        "Über „Sicherungsort wählen“ lässt sich ein anderer Ordner festlegen."
    )


def list_backups(ttl_path: str, manual_dir: Optional[str] = None) -> list:
    """Listet vorhandene Sicherungen für diese Datei über alle Kandidatenorte
    (nur die, die aktuell existieren/lesbar sind), neueste zuerst."""
    key = file_key(ttl_path)
    found = []
    for label, path in backup_candidate_locations(ttl_path, manual_dir):
        try:
            if not os.path.isdir(path):
                continue
            for name in os.listdir(path):
                if key in name and name.endswith(".ttl.bak"):
                    full = os.path.join(path, name)
                    try:
                        stat = os.stat(full)
                    except OSError:
                        continue
                    found.append({
                        "filename": name,
                        "path": full,
                        "location": label,
                        "size": stat.st_size,
                        "mtime": stat.st_mtime,
                    })
        except OSError:
            continue
    found.sort(key=lambda e: e["mtime"], reverse=True)
    return found


def storage_check(ttl_path: str, manual_dir: Optional[str] = None) -> list:
    """„Schreibzugriff prüfen“: versucht in jedem Kandidatenordner eine kleine
    Testdatei anzulegen (und im TTL-Ordner zusätzlich deren ERSATZ per
    os.replace, da das eigentliche Speichern genau das tut). Belegt NICHT,
    dass die TTL selbst geöffnet/ersetzt werden darf — nur, dass der Ordner
    grundsätzlich beschreibbar ist."""
    ttl_dir = os.path.dirname(os.path.abspath(ttl_path))
    results = []
    for label, path in backup_candidate_locations(ttl_path, manual_dir):
        entry = {"location": label, "path": path, "writable": False, "error": None, "replace_tested": False}
        try:
            os.makedirs(path, exist_ok=True)
            probe = os.path.join(path, ".fpv_write_test.tmp")
            with open(probe, "wb") as f:
                f.write(b"fpv-write-test")
                f.flush()
                os.fsync(f.fileno())
            entry["writable"] = True
            if os.path.normcase(os.path.abspath(path)) == os.path.normcase(os.path.abspath(ttl_dir)):
                probe2 = os.path.join(path, ".fpv_write_test2.tmp")
                with open(probe2, "wb") as f:
                    f.write(b"fpv-write-test-2")
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(probe2, probe)
                entry["replace_tested"] = True
            os.remove(probe)
        except OSError as exc:
            entry["error"] = f"{type(exc).__name__}: {exc}"
        results.append(entry)
    return results


# --------------------------------------------------------------------------
# Atomisches Schreiben mit nicht-atomarem Rückfall
# --------------------------------------------------------------------------

@dataclass
class WriteResult:
    method: str          # "atomic" | "fallback-direct"
    backup_label: str
    backup_path: str


def write_ttl_atomically(ttl_path: str, new_text_lf: str, uses_crlf: bool,
                          raw_bytes_before: bytes, manual_backup_dir: Optional[str] = None) -> WriteResult:
    """Reihenfolge zwingend (siehe Übergabe §5):
      1. geprüfte Sicherung der ALTEN Bytes (sonst: Abbruch, TTL bleibt unberührt)
      2. neue Gesamtdatei validieren (Aufgabe des Callers VOR dieser Funktion)
      3. neue Datei schreiben: bevorzugt temp+os.replace (atomar);
         bei PermissionError auf temp/replace -> Rückfall r+b direkt in die
         bestehende Datei (NICHT atomar; bei Absturz während des Schreibens
         ggf. Wiederherstellung aus der eben erstellten Sicherung nötig).
    """
    # 1) Sicherung zuerst, bedingungslos.
    backup_label, backup_path = create_verified_backup(ttl_path, raw_bytes_before, manual_backup_dir)

    new_text = _renormalize_line_endings(new_text_lf, uses_crlf)
    new_bytes = new_text.encode("utf-8")

    ttl_dir = os.path.dirname(os.path.abspath(ttl_path))

    # 3a) Bevorzugt: temp-Datei im selben Ordner + os.replace (atomar, gleicher Datenträger).
    tmp_path = None
    try:
        fd, tmp_path = tempfile.mkstemp(prefix=".fpv-tmp-", suffix=".ttl", dir=ttl_dir)
        with os.fdopen(fd, "wb") as f:
            f.write(new_bytes)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, ttl_path)
        return WriteResult(method="atomic", backup_label=backup_label, backup_path=backup_path)
    except PermissionError:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass
        # 3b) Rückfall: NICHT atomar. Nur weil die Sicherung (Schritt 1) bereits
        # erfolgreich und geprüft ist, ist dieser Schritt überhaupt vertretbar.
        try:
            with open(ttl_path, "r+b") as f:
                f.seek(0)
                f.write(new_bytes)
                f.truncate(len(new_bytes))
                f.flush()
                os.fsync(f.fileno())
            return WriteResult(method="fallback-direct", backup_label=backup_label, backup_path=backup_path)
        except OSError as exc:
            raise FpvError(
                f"Weder atomares Schreiben (temp+os.replace) noch der direkte "
                f"Rückfall (r+b) waren möglich: {exc}. Die zuletzt erstellte "
                f"Sicherung liegt unter: {backup_path} ({backup_label}). "
                f"Die TTL-Datei wurde NICHT verändert."
            ) from exc
    except OSError as exc:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass
        raise FpvError(f"Schreiben fehlgeschlagen: {exc}") from exc


def restore_backup(ttl_path: str, backup_full_path: str, manual_backup_dir: Optional[str] = None) -> WriteResult:
    """Stellt eine Sicherung wieder her. Sichert VORHER den aktuellen Stand
    (siehe Übergabe §5, letzter Satz)."""
    p = Path(ttl_path)
    current_bytes = p.read_bytes() if p.exists() else b""
    backup_bytes = Path(backup_full_path).read_bytes()
    uses_crlf = b"\r\n" in backup_bytes
    text = backup_bytes.decode("utf-8").replace("\r\n", "\n")
    return write_ttl_atomically(ttl_path, text, uses_crlf, current_bytes, manual_backup_dir)


# --------------------------------------------------------------------------
# Hilfsfunktionen für app.py: Gesamtoperationen
# --------------------------------------------------------------------------

def build_state(loaded: LoadedFile) -> dict:
    records = []
    findings = validate_whole_file(loaded.text)
    for block in iter_all_blocks(loaded.text):
        if block.protected:
            records.append({
                "id": block.id,
                "protected": True,
                "protect_reason": block.protect_reason,
                # Rohtext des Blocks mitliefern, damit die Oberfläche bei
                # geschützten Blöcken wenigstens ANZEIGEN kann, was drinsteht.
                # Vorher sah der Nutzer nur "geschützt" ohne jeden Hinweis
                # darauf, welche Zeile das Problem verursacht.
                "raw": block.raw,
                "line": loaded.text.count("\n", 0, block.start) + 1,
            })
            continue
        try:
            rec = parse_block_to_record(block)
            rj = rec.to_json()
            rj["protected"] = False
            rj["line"] = loaded.text.count("\n", 0, block.start) + 1
            records.append(rj)
        except ProtectedBlockError as exc:
            records.append({
                "id": block.id,
                "protected": True,
                "protect_reason": str(exc),
                "raw": block.raw,
                "line": loaded.text.count("\n", 0, block.start) + 1,
            })
    return {
        "path": loaded.path,
        "sha256": loaded.sha256,
        "uses_crlf": loaded.uses_crlf,
        "records": records,
        "findings": [f.to_json() for f in findings],
    }
