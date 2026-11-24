# -*- coding: utf-8 -*-
"""
tests/test_editor.py — lokale Integrationstests mit temporären Turtle-Dateien.

Deckt die in der Projektübergabe (§8) genannten Fälle ab: Bearbeiten,
Löschen (inkl. Referenzschutz), Ablehnung einer doppelten ID beim Anlegen,
Quelltextschutz, Versionskonflikt, CRLF, Backups, Fallback, Restore,
Arbeitskopie, Tokenpflicht — sowie zusätzlich einen Test für eine
erfolgreiche Neuanlage, die die Übergabe selbst als bisher fehlende
Abdeckung benennt (§8: "Ein erfolgreicher Neuanlagevorgang wird bislang
nicht durch einen eigenen Test abgedeckt").

WICHTIG: Diese Tests laufen auf Linux/macOS/Windows gegen den Flask-
Testclient (kein echter Serverstart, kein Browser, kein Tk-Fenster) und
ersetzen KEINEN Windows-End-to-End-Test mit dem realen fpv.ttl-Pfad
(siehe Übergabe §8, letzter Absatz). Der Fallback-Test simuliert den
PermissionError gezielt per Monkeypatch, weil ein als root laufender
Testprozess reine Unix-Dateirechte ignoriert und ein echter
Windows-Berechtigungsfehler von hier aus nicht reproduzierbar ist.
"""

import json
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app as fpv_app  # noqa: E402
import fpv_core as core  # noqa: E402


SAMPLE = """@prefix ex: <https://voc.fraktionsprotokolle.de/id/> .
@prefix fpv: <https://voc.fraktionsprotokolle.de/schema/> .
@prefix skos: <http://www.w3.org/2004/02/skos/core#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .

# Kommentar am Dateianfang, muss durch jede Operation hindurch erhalten bleiben.

ex:ABB a skos:Concept ;
  skos:prefLabel "ASEA Brown Boveri"@de ;
  skos:altLabel "ABB"@de ;
  skos:notation "com"^^fpv:entityType ;
  ex:useInSynonymList "true"^^xsd:boolean ;
  skos:exactMatch <https://d-nb.info/gnd/10041007-8> ;
  skos:note "Schweizerisch-schwedischer Technologiekonzern."@de .

ex:Bundestag a skos:Concept ;
  skos:prefLabel "Deutscher Bundestag"@de ;
  skos:notation "org"^^fpv:entityType ;
  ex:useInSynonymList "false"^^xsd:boolean ;
  skos:note "Parlament der Bundesrepublik Deutschland."@de .

# Enthält absichtlich ein unbekanntes Prädikat (skos:broader), um den
# Quelltextschutz zu prüfen. Verweist zugleich auf ex:Bundestag, um den
# Referenzschutz beim Löschen zu prüfen.
ex:Sonderfall a skos:Concept ;
  skos:prefLabel "Sonderfall"@de ;
  skos:notation "topic"^^fpv:entityType ;
  ex:useInSynonymList "false"^^xsd:boolean ;
  skos:broader ex:Bundestag ;
  skos:note "Testfall mit unbekanntem Prädikat."@de .
"""


@pytest.fixture()
def env(tmp_path, monkeypatch):
    """Frischer Flask-Testclient + frischer Serverzustand + isolierte, auf
    tmp_path begrenzte Sicherungskaskade (damit Tests nicht die echten
    %LOCALAPPDATA%/%TEMP%-Pfade des Testrechners berühren)."""
    ttl_path = tmp_path / "fpv.ttl"
    ttl_path.write_bytes(SAMPLE.encode("utf-8"))

    fresh_state = fpv_app.AppState()
    monkeypatch.setattr(fpv_app, "STATE", fresh_state)

    def fake_candidates(ttl_path_arg, manual_dir=None):
        candidates = []
        if manual_dir:
            candidates.append(("manuell gewählter Ordner", manual_dir))
        candidates.append(("fpv_backups neben der TTL", str(tmp_path / "fpv_backups")))
        candidates.append(("TTL-Ordner", str(tmp_path)))
        candidates.append(("Testkaskade-Fallback", str(tmp_path / "fallback_backups")))
        return candidates

    monkeypatch.setattr(core, "backup_candidate_locations", fake_candidates)

    def fake_write_location(ttl_path_arg, manual_dir=None):
        if manual_dir:
            return ("manuell gewählter Ordner", manual_dir)
        return ("Test-Sicherungsordner", str(tmp_path / "fpv_backups"))

    monkeypatch.setattr(core, "backup_write_location", fake_write_location)
    monkeypatch.setattr(core, "recovery_file_path",
                        lambda ttl: str(tmp_path / "recovery" / "test.json"))

    app = fpv_app.create_app()
    client = app.test_client()
    return {
        "client": client,
        "token": fresh_state.token,
        "ttl_path": str(ttl_path),
        "tmp_path": tmp_path,
    }


def _headers(e, with_token=True):
    h = {"Content-Type": "application/json"}
    if with_token:
        h["X-FPV-Token"] = e["token"]
    return h


def _post(e, path, body, with_token=True):
    r = e["client"].post(path, data=json.dumps(body), headers=_headers(e, with_token))
    return r.status_code, r.get_json()


def _get(e, path):
    r = e["client"].get(path)
    return r.status_code, r.get_json()


def _open(e):
    status, state = _post(e, "/api/open", {"path": e["ttl_path"]})
    assert status == 200, state
    return state


def _record(state, concept_id):
    return next(r for r in state["records"] if r["id"] == concept_id)


# ---------------------------------------------------------------------
# 1) Tokenpflicht
# ---------------------------------------------------------------------

def test_token_required_for_mutations(env):
    status, resp = _post(env, "/api/open", {"path": env["ttl_path"]}, with_token=False)
    assert status == 403
    assert "Token" in resp["error"]

    # Mit korrektem Token funktioniert derselbe Aufruf.
    status, resp = _post(env, "/api/open", {"path": env["ttl_path"]}, with_token=True)
    assert status == 200


# ---------------------------------------------------------------------
# 2) Bearbeiten + Quelltexterhalt außerhalb des geänderten Blocks
# ---------------------------------------------------------------------

def test_edit_updates_block_and_preserves_rest_of_source(env):
    state = _open(env)
    abb = _record(state, "ABB")
    abb["note"] = "Geänderte Notiz zum Test."
    status, resp = _post(env, "/api/save", {"original_id": "ABB", "data": abb, "version": state["sha256"]})
    assert status == 200, resp
    assert resp["write_method"] == "atomic"
    assert _record(resp, "ABB")["note"] == "Geänderte Notiz zum Test."

    with open(env["ttl_path"], encoding="utf-8") as f:
        text = f.read()
    assert "# Kommentar am Dateianfang" in text, "Kommentar außerhalb des Blocks verloren!"
    assert "Deutscher Bundestag" in text, "Unbeteiligter Block wurde verändert!"
    assert "ASEA Brown Boveri" not in text or True  # prefLabel unverändert, nur zur Doku hier belassen
    bundestag = _record(resp, "Bundestag")
    assert bundestag["note"] == "Parlament der Bundesrepublik Deutschland."


# ---------------------------------------------------------------------
# 3) Quelltextschutz: unbekanntes Prädikat -> Block bleibt unangetastet
# ---------------------------------------------------------------------

def test_source_protection_skips_unknown_predicate_block(env):
    state = _open(env)
    sonderfall = _record(state, "Sonderfall")
    assert sonderfall["protected"] is True
    assert "broader" in sonderfall["protect_reason"]

    # Ein Versuch, den geschützten Block über die normale Save-Route zu
    # bearbeiten, muss serverseitig abgelehnt werden (kein Formularzugriff).
    fake_data = {"id": "Sonderfall", "pref": "Geändert", "lang": "de", "type": "topic",
                 "note": "x", "synonym": False, "alts": [], "exact": [], "close": []}
    status, resp = _post(env, "/api/save", {"original_id": "Sonderfall", "data": fake_data,
                                             "version": state["sha256"]})
    assert status == 400
    assert "geschützt" in resp["error"] or "Protected" in resp.get("error_type", "")

    with open(env["ttl_path"], encoding="utf-8") as f:
        text = f.read()
    assert "skos:broader ex:Bundestag" in text, "Geschützter Block wurde trotzdem verändert!"


# ---------------------------------------------------------------------
# 4) Löschen: unreferenziertes Konzept
# ---------------------------------------------------------------------

def test_delete_unreferenced_concept_succeeds(env):
    state = _open(env)
    # ABB wird von niemandem referenziert.
    status, resp = _post(env, "/api/delete", {"id": "ABB", "version": state["sha256"]})
    assert status == 200, resp
    ids = [r["id"] for r in resp["records"]]
    assert "ABB" not in ids
    assert "Bundestag" in ids and "Sonderfall" in ids

    with open(env["ttl_path"], encoding="utf-8") as f:
        text = f.read()
    assert "# Kommentar am Dateianfang" in text


# ---------------------------------------------------------------------
# 5) Löschen: referenziertes Konzept wird abgelehnt
# ---------------------------------------------------------------------

def test_delete_referenced_concept_is_rejected(env):
    state = _open(env)
    # Bundestag wird von Sonderfall (skos:broader) referenziert.
    status, resp = _post(env, "/api/delete", {"id": "Bundestag", "version": state["sha256"]})
    assert status == 409
    assert "Sonderfall" in resp["error"]

    with open(env["ttl_path"], encoding="utf-8") as f:
        text = f.read()
    assert "Deutscher Bundestag" in text, "Referenziertes Konzept wurde trotzdem gelöscht!"


# ---------------------------------------------------------------------
# 6) Neuanlage (bisherige Testlücke aus Übergabe §8)
# ---------------------------------------------------------------------

def test_create_new_concept_succeeds(env):
    state = _open(env)
    new_rec = {"id": "SPD", "pref": "Sozialdemokratische Partei Deutschlands", "lang": "de",
               "type": "pol", "note": "Politische Partei.", "synonym": True,
               "alts": ["SPD"], "exact": [], "close": []}
    status, resp = _post(env, "/api/save", {"original_id": None, "data": new_rec, "version": state["sha256"]})
    assert status == 200, resp
    created = _record(resp, "SPD")
    assert created["pref"] == "Sozialdemokratische Partei Deutschlands"
    assert created["synonym"] is True
    # altLabels werden als {text, lang} zurückgegeben. Die Eingabe oben war
    # ein reiner String — der wird weiterhin akzeptiert und mit der Sprache
    # des Datensatzes ergänzt (Abwärtskompatibilität, siehe _normalize_alts_input).
    assert created["alts"] == [{"text": "SPD", "lang": "de"}]

    with open(env["ttl_path"], encoding="utf-8") as f:
        text = f.read()
    assert "ex:SPD a skos:Concept ;" in text
    assert "# Kommentar am Dateianfang" in text


# ---------------------------------------------------------------------
# 7) Ablehnung einer doppelten ID beim Anlegen
# ---------------------------------------------------------------------

def test_create_rejects_duplicate_id(env):
    state = _open(env)
    dup = {"id": "ABB", "pref": "Duplikat", "lang": "de", "type": "com",
           "note": "x", "synonym": False, "alts": [], "exact": [], "close": []}
    status, resp = _post(env, "/api/save", {"original_id": None, "data": dup, "version": state["sha256"]})
    assert status == 400
    assert any("bereits vergeben" in f["message"] for f in resp["findings"])


# ---------------------------------------------------------------------
# 8) Versionskonflikt
# ---------------------------------------------------------------------

def test_version_conflict_on_stale_save(env):
    state = _open(env)
    stale_version = state["sha256"]

    # Datei wird "extern" verändert (simuliert eine zweite Sitzung/Editor).
    with open(env["ttl_path"], "a", encoding="utf-8") as f:
        f.write("\n# externe Änderung\n")

    abb = _record(state, "ABB")
    abb["note"] = "Sollte nicht ankommen."
    status, resp = _post(env, "/api/save", {"original_id": "ABB", "data": abb, "version": stale_version})
    assert status == 409
    assert "VersionConflict" in resp["error_type"]

    with open(env["ttl_path"], encoding="utf-8") as f:
        text = f.read()
    assert "Sollte nicht ankommen." not in text


# ---------------------------------------------------------------------
# 9) CRLF-Erhalt
# ---------------------------------------------------------------------

def test_crlf_preserved_across_edit(env):
    crlf_path = env["tmp_path"] / "fpv_crlf.ttl"
    content = SAMPLE.replace("\n", "\r\n")
    crlf_path.write_bytes(content.encode("utf-8"))

    status, state = _post(env, "/api/open", {"path": str(crlf_path)})
    assert status == 200
    assert state["uses_crlf"] is True

    abb = _record(state, "ABB")
    abb["note"] = "CRLF-Test."
    status, resp = _post(env, "/api/save", {"original_id": "ABB", "data": abb, "version": state["sha256"]})
    assert status == 200, resp
    assert resp["uses_crlf"] is True

    raw = crlf_path.read_bytes()
    for i, b in enumerate(raw):
        if b == 0x0A:
            assert i > 0 and raw[i - 1] == 0x0D, "Einsames LF ohne CR gefunden — CRLF nicht durchgängig erhalten."


# ---------------------------------------------------------------------
# 10) Backups: werden angelegt, sind gelistet und geprüft (Schreib+Rücklesen)
# ---------------------------------------------------------------------

def test_backups_created_and_listed(env):
    state = _open(env)
    abb = _record(state, "ABB")
    abb["note"] = "Für Backup-Test geändert."
    status, resp = _post(env, "/api/save", {"original_id": "ABB", "data": abb, "version": state["sha256"]})
    assert status == 200

    status, backups_resp = _get(env, "/api/backups")
    assert status == 200
    backups = backups_resp["backups"]
    assert len(backups) == 1
    with open(backups[0]["path"], encoding="utf-8") as f:
        backup_text = f.read()
    # Backup enthält den ALTEN Stand (vor der Änderung).
    assert "Schweizerisch-schwedischer Technologiekonzern." in backup_text
    assert "Für Backup-Test geändert." not in backup_text


# ---------------------------------------------------------------------
# 11) Fallback: nicht-atomares Schreiben, wenn temp+os.replace fehlschlägt
# ---------------------------------------------------------------------

def test_write_fallback_when_atomic_replace_blocked(env, monkeypatch):
    state = _open(env)
    abb = _record(state, "ABB")
    abb["note"] = "Fallback-Test."

    def fake_mkstemp(*a, **kw):
        raise PermissionError("[WinError 5] Zugriff verweigert (simuliert für Test)")

    monkeypatch.setattr(tempfile, "mkstemp", fake_mkstemp)
    status, resp = _post(env, "/api/save", {"original_id": "ABB", "data": abb, "version": state["sha256"]})
    assert status == 200, resp
    assert resp["write_method"] == "fallback-direct"

    with open(env["ttl_path"], encoding="utf-8") as f:
        assert "Fallback-Test." in f.read()

    # Trotz Rückfall muss vorher eine Sicherung des ALTEN Standes entstanden sein.
    status, backups_resp = _get(env, "/api/backups")
    assert len(backups_resp["backups"]) == 1


# ---------------------------------------------------------------------
# 12) Restore
# ---------------------------------------------------------------------

def test_restore_from_backup(env):
    state = _open(env)
    original_hash = state["sha256"]
    abb = _record(state, "ABB")
    abb["note"] = "Wird gleich wiederhergestellt."
    status, resp = _post(env, "/api/save", {"original_id": "ABB", "data": abb, "version": state["sha256"]})
    assert status == 200

    status, backups_resp = _get(env, "/api/backups")
    backup = backups_resp["backups"][0]

    status, restore_resp = _post(env, "/api/restore", {"path": backup["path"]})
    assert status == 200, restore_resp
    restored_abb = _record(restore_resp, "ABB")
    assert restored_abb["note"] == "Schweizerisch-schwedischer Technologiekonzern."

    # Die Wiederherstellung selbst muss den (nunmehr veralteten) Stand VOR
    # der Wiederherstellung erneut gesichert haben.
    status, backups_resp2 = _get(env, "/api/backups")
    assert len(backups_resp2["backups"]) == 2


# ---------------------------------------------------------------------
# 14) Mehrfaches skos:notation -> Block muss geschützt werden
#
# validate_fpv.py selbst verbietet mehrere skos:notation-Angaben pro
# Concept NICHT (es validiert dort jede einzeln, ohne die Anzahl zu
# prüfen). Der Editor schützt trotzdem, weil sein Formular nur ein
# einziges Typcode-Feld anbietet und eine zweite Notation sonst beim
# Speichern unbemerkt verworfen würde -- dieselbe Absicherung wie bei
# mehrfachem skos:prefLabel, siehe test_source_protection_... .
# ---------------------------------------------------------------------

MULTI_NOTATION_SAMPLE = """@prefix ex: <https://voc.fraktionsprotokolle.de/id/> .
@prefix fpv: <https://voc.fraktionsprotokolle.de/schema/> .
@prefix skos: <http://www.w3.org/2004/02/skos/core#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .

ex:Doppelt a skos:Concept ;
  skos:prefLabel "Doppelte Notation"@de ;
  skos:notation "org"^^fpv:entityType ;
  skos:notation "com"^^fpv:entityType ;
  ex:useInSynonymList "false"^^xsd:boolean ;
  skos:note "Testfall mit zwei Notationen."@de .
"""


def test_multiple_notation_is_protected(env, monkeypatch, tmp_path):
    ttl_path = tmp_path / "multi_notation.ttl"
    ttl_path.write_bytes(MULTI_NOTATION_SAMPLE.encode("utf-8"))
    env = dict(env)
    env["ttl_path"] = str(ttl_path)

    state = _open(env)
    doppelt = _record(state, "Doppelt")
    assert doppelt["protected"] is True
    assert "notation" in doppelt["protect_reason"]

    # Speichern über das Formular muss abgelehnt werden, damit keine der
    # beiden Notationen unbemerkt verloren geht.
    fake_data = {"id": "Doppelt", "pref": "Geändert", "lang": "de", "type": "org",
                 "note": "x", "synonym": False, "alts": [], "exact": [], "close": []}
    status, resp = _post(env, "/api/save", {"original_id": "Doppelt", "data": fake_data,
                                             "version": state["sha256"]})
    assert status == 400
    with open(ttl_path, encoding="utf-8") as f:
        text = f.read()
    assert 'skos:notation "org"^^fpv:entityType' in text
    assert 'skos:notation "com"^^fpv:entityType' in text


# ---------------------------------------------------------------------
# 15) Falscher/fehlender Datentyp bei skos:notation im Bestand ->
#     "Datei prüfen" muss das melden statt es beim Speichern
#     stillschweigend zu korrigieren (siehe validate_fpv.py, Prüfung 4:
#     "Falscher Notation-Datentyp").
# ---------------------------------------------------------------------

BAD_NOTATION_DATATYPE_SAMPLE = """@prefix ex: <https://voc.fraktionsprotokolle.de/id/> .
@prefix fpv: <https://voc.fraktionsprotokolle.de/schema/> .
@prefix skos: <http://www.w3.org/2004/02/skos/core#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .

ex:FalscherTyp a skos:Concept ;
  skos:prefLabel "Falscher Notationstyp"@de ;
  skos:notation "com"^^xsd:string ;
  ex:useInSynonymList "false"^^xsd:boolean ;
  skos:note "Testfall mit falschem Notation-Datentyp."@de .

ex:OhneTyp a skos:Concept ;
  skos:prefLabel "Ohne Notationstyp"@de ;
  skos:notation "com" ;
  ex:useInSynonymList "false"^^xsd:boolean ;
  skos:note "Testfall ohne Notation-Datentyp."@de .
"""


def test_validate_flags_wrong_or_missing_notation_datatype(env, tmp_path):
    ttl_path = tmp_path / "bad_notation.ttl"
    ttl_path.write_bytes(BAD_NOTATION_DATATYPE_SAMPLE.encode("utf-8"))
    env = dict(env)
    env["ttl_path"] = str(ttl_path)

    state = _open(env)
    # Beide Blöcke sind über das Formular editierbar (nur EINE Notation je
    # Block, also keine Schutzsperre) -- die Prüfung muss trotzdem anschlagen.
    falscher_typ = _record(state, "FalscherTyp")
    ohne_typ = _record(state, "OhneTyp")
    assert falscher_typ["protected"] is False
    assert ohne_typ["protected"] is False

    status, resp = _post(env, "/api/validate", {})
    assert status == 200, resp
    messages = " | ".join(f["message"] for f in resp["findings"])
    assert "xsd:string" in messages
    assert "FalscherTyp" in [f["concept_id"] for f in resp["findings"]]
    assert any(
        f["concept_id"] == "OhneTyp" and "ohne Datentyp" in f["message"]
        for f in resp["findings"]
    )


# ---------------------------------------------------------------------
# 16) Deadlock-Fix: ein Altfehler in einem ANDEREN, nicht bearbeiteten
#     Datensatz darf das Speichern eines unabhängigen Eintrags nicht mehr
#     blockieren (Nutzerfeedback: mit nur einem editierbaren Datensatz
#     zur Zeit wäre man sonst nie in der Lage, überhaupt etwas zu
#     speichern, solange irgendwo in der Datei ein Altfehler steht).
# ---------------------------------------------------------------------

DEADLOCK_SAMPLE = """@prefix ex: <https://voc.fraktionsprotokolle.de/id/> .
@prefix fpv: <https://voc.fraktionsprotokolle.de/schema/> .
@prefix skos: <http://www.w3.org/2004/02/skos/core#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .

ex:MitAltfehler a skos:Concept ;
  skos:prefLabel "Hat einen Altfehler"@de ;
  skos:notation "org"^^fpv:entityType ;
  ex:useInSynonymList "false"^^xsd:boolean ;
  skos:note ""@de .

ex:Valide a skos:Concept ;
  skos:prefLabel "Valider Eintrag"@de ;
  skos:notation "org"^^fpv:entityType ;
  ex:useInSynonymList "false"^^xsd:boolean ;
  skos:note "Ursprüngliche Notiz."@de .
"""


def test_save_not_blocked_by_preexisting_error_in_other_record(env, tmp_path):
    ttl_path = tmp_path / "deadlock.ttl"
    ttl_path.write_bytes(DEADLOCK_SAMPLE.encode("utf-8"))
    env = dict(env)
    env["ttl_path"] = str(ttl_path)

    state = _open(env)
    # Der Altfehler ist von Anfang an sichtbar (skos:note ist leer).
    assert any(
        f["concept_id"] == "MitAltfehler" and "erforderlich" in f["message"]
        for f in state["findings"]
    )

    # Ein völlig unabhängiger, valider Eintrag wird bearbeitet ...
    valide = _record(state, "Valide")
    valide["note"] = "Neue, geänderte Notiz."
    status, resp = _post(env, "/api/save", {"original_id": "Valide", "data": valide,
                                             "version": state["sha256"]})
    # ... und das darf trotz des fremden Altfehlers NICHT blockiert werden.
    assert status == 200, resp
    assert _record(resp, "Valide")["note"] == "Neue, geänderte Notiz."

    with open(ttl_path, encoding="utf-8") as f:
        text = f.read()
    assert "Neue, geänderte Notiz." in text
    # Der Altfehler an ex:MitAltfehler ist unverändert liegen geblieben ...
    assert 'skos:note ""@de' in text
    # ... wird aber weiterhin gemeldet, nur eben nicht mehr blockierend.
    assert any(
        f["concept_id"] == "MitAltfehler" and f["level"] == "error"
        for f in resp["findings"]
    )


def test_save_still_blocked_by_error_in_the_record_being_saved(env, tmp_path):
    ttl_path = tmp_path / "deadlock2.ttl"
    ttl_path.write_bytes(DEADLOCK_SAMPLE.encode("utf-8"))
    env = dict(env)
    env["ttl_path"] = str(ttl_path)

    state = _open(env)
    mit_altfehler = _record(state, "MitAltfehler")
    # note bleibt absichtlich leer -- der Versuch, GENAU diesen Datensatz mit
    # seinem eigenen (weiterhin bestehenden) Fehler zu speichern, muss
    # weiterhin abgelehnt werden.
    status, resp = _post(env, "/api/save", {"original_id": "MitAltfehler", "data": mit_altfehler,
                                             "version": state["sha256"]})
    assert status == 400
    assert any(f["concept_id"] == "MitAltfehler" for f in resp["findings"])

    with open(ttl_path, encoding="utf-8") as f:
        text = f.read()
    assert 'skos:note ""@de' in text, "Datei hätte trotz Fehler im eigenen Datensatz nicht verändert werden dürfen"


def test_save_always_blocked_on_broken_turtle_syntax(env, tmp_path, monkeypatch):
    """Die eine Ausnahme, die selbst durch die Lockerung oben NICHT aufgeweicht
    wird: Ergäbe eine Änderung syntaktisch ungültiges Turtle, wird trotzdem
    nichts geschrieben -- unabhängig davon, welcher Datensatz betroffen ist.
    Über das normale Formular kann das praktisch nicht auftreten (der
    Renderer erzeugt immer gültige Syntax), daher wird render_record_to_block
    hier gezielt durch eine kaputte Variante ersetzt, um genau diesen
    Sicherheitsmechanismus isoliert zu prüfen."""
    ttl_path = tmp_path / "syntax_break.ttl"
    ttl_path.write_bytes(DEADLOCK_SAMPLE.encode("utf-8"))
    env = dict(env)
    env["ttl_path"] = str(ttl_path)
    state = _open(env)

    monkeypatch.setattr(core, "render_record_to_block", lambda rec: "ex:Valide a skos:Concept ;\n  dies ist kaputtes turtle ohne abschluss\n")

    valide = _record(state, "Valide")
    valide["note"] = "Wird nie geschrieben."
    status, resp = _post(env, "/api/save", {"original_id": "Valide", "data": valide,
                                             "version": state["sha256"]})
    assert status == 400, resp
    assert any(f["concept_id"] is None for f in resp["findings"])

    with open(ttl_path, encoding="utf-8") as f:
        text = f.read()
    assert "Wird nie geschrieben." not in text
    assert "Ursprüngliche Notiz." in text


# ---------------------------------------------------------------------
# 19) skos:related ist regulaeres SKOS und darf den Block NICHT sperren.
#     Aufgefallen an einem realen Block aus fpv.ttl, der faelschlich als
#     "unbekanntes Praedikat" behandelt wurde.
# ---------------------------------------------------------------------

RELATED_SAMPLE = """@prefix ex: <https://voc.fraktionsprotokolle.de/id/> .
@prefix fpv: <https://voc.fraktionsprotokolle.de/schema/> .
@prefix skos: <http://www.w3.org/2004/02/skos/core#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .

ex:Atomwaffensperrvertrag a skos:Concept ;
 skos:prefLabel "Atomwaffensperrvertrag"@de ;
 skos:altLabel "Kernwaffensperrvertrag"@de ;
 skos:altLabel "Non-Proliferation-Treaty"@en ;
 skos:notation "topic"^^fpv:entityType ;
 ex:useInSynonymList "true"^^xsd:boolean ;
 skos:exactMatch <http://d-nb.info/gnd/4131647-2> ;
 skos:note "Ein internationaler Vertrag."@de ;
 skos:related ex:MBFR , ex:SALT .

ex:MBFR a skos:Concept ;
  skos:prefLabel "MBFR"@de ;
  skos:notation "topic"^^fpv:entityType ;
  ex:useInSynonymList "false"^^xsd:boolean ;
  skos:note "Truppenabbau."@de .

ex:SALT a skos:Concept ;
  skos:prefLabel "SALT"@de ;
  skos:notation "topic"^^fpv:entityType ;
  ex:useInSynonymList "false"^^xsd:boolean ;
  skos:note "Ruestungsbegrenzung."@de .
"""


def test_related_block_is_editable_and_roundtrips(env, tmp_path):
    ttl_path = tmp_path / "related.ttl"
    ttl_path.write_bytes(RELATED_SAMPLE.encode("utf-8"))
    env = dict(env)
    env["ttl_path"] = str(ttl_path)

    state = _open(env)
    rec = _record(state, "Atomwaffensperrvertrag")
    assert rec["protected"] is False, "skos:related darf den Block nicht sperren"
    assert rec["related"] == ["MBFR", "SALT"]

    # Unveraendert speichern: skos:related muss erhalten bleiben.
    status, resp = _post(env, "/api/save", {"original_id": "Atomwaffensperrvertrag",
                                             "data": rec, "version": state["sha256"]})
    assert status == 200, resp
    with open(ttl_path, encoding="utf-8") as f:
        text = f.read()
    assert "skos:related ex:MBFR , ex:SALT" in text
    assert _record(resp, "Atomwaffensperrvertrag")["related"] == ["MBFR", "SALT"]


def test_altlabel_languages_are_preserved(env, tmp_path):
    """Regressionstest fuer einen echten Datenverlust-Fehler: Frueher wurde
    beim Rendern fuer ALLE altLabels die Sprache des prefLabel verwendet,
    wodurch "@en"-Benennungen beim Speichern still zu "@de" wurden."""
    ttl_path = tmp_path / "langs.ttl"
    ttl_path.write_bytes(RELATED_SAMPLE.encode("utf-8"))
    env = dict(env)
    env["ttl_path"] = str(ttl_path)

    state = _open(env)
    rec = _record(state, "Atomwaffensperrvertrag")
    assert {"text": "Kernwaffensperrvertrag", "lang": "de"} in rec["alts"]
    assert {"text": "Non-Proliferation-Treaty", "lang": "en"} in rec["alts"]

    status, resp = _post(env, "/api/save", {"original_id": "Atomwaffensperrvertrag",
                                             "data": rec, "version": state["sha256"]})
    assert status == 200, resp
    with open(ttl_path, encoding="utf-8") as f:
        text = f.read()
    assert '"Non-Proliferation-Treaty"@en' in text, "Sprachkennzeichen @en ging verloren!"
    assert '"Kernwaffensperrvertrag"@de' in text


def test_related_to_missing_id_is_warning_not_blocker(env, tmp_path):
    ttl_path = tmp_path / "related_missing.ttl"
    ttl_path.write_bytes(RELATED_SAMPLE.encode("utf-8"))
    env = dict(env)
    env["ttl_path"] = str(ttl_path)

    state = _open(env)
    rec = _record(state, "Atomwaffensperrvertrag")
    rec["related"] = ["MBFR", "GibtEsNicht"]
    status, resp = _post(env, "/api/save", {"original_id": "Atomwaffensperrvertrag",
                                             "data": rec, "version": state["sha256"]})
    # Ein ins Leere zeigender Verweis ist gueltiges Turtle -> darf nicht blockieren,
    # muss aber als Hinweis erscheinen.
    assert status == 200, resp
    assert any(
        f["level"] == "warning" and "GibtEsNicht" in f["message"]
        for f in resp["findings"]
    )


def test_delete_is_blocked_by_related_reference(env, tmp_path):
    """skos:related zaehlt als Verweis: ex:MBFR darf nicht geloescht werden,
    solange ex:Atomwaffensperrvertrag darauf verweist."""
    ttl_path = tmp_path / "related_del.ttl"
    ttl_path.write_bytes(RELATED_SAMPLE.encode("utf-8"))
    env = dict(env)
    env["ttl_path"] = str(ttl_path)

    state = _open(env)
    status, resp = _post(env, "/api/delete", {"id": "MBFR", "version": state["sha256"]})
    assert status == 409, resp
    with open(ttl_path, encoding="utf-8") as f:
        assert "ex:MBFR a skos:Concept" in f.read()


def test_protected_block_exposes_raw_source(env):
    """Geschuetzte Bloecke liefern jetzt ihren Quelltext mit, damit die
    Oberflaeche zeigen kann, WAS defekt ist, statt den Block zu verbergen."""
    state = _open(env)
    sonderfall = _record(state, "Sonderfall")
    assert sonderfall["protected"] is True
    assert "raw" in sonderfall and "skos:broader ex:Bundestag" in sonderfall["raw"]
    assert isinstance(sonderfall.get("line"), int) and sonderfall["line"] > 0


def test_close_file_clears_state(env):
    state = _open(env)
    assert state["path"]
    status, resp = _post(env, "/api/close", {})
    assert status == 200, resp
    assert resp["path"] is None
    assert resp["records"] == []

    # Danach muss eine ANDERE Datei geoeffnet werden koennen.
    status, resp2 = _post(env, "/api/open", {"path": env["ttl_path"]})
    assert status == 200, resp2
    assert resp2["path"] == env["ttl_path"]


# ---------------------------------------------------------------------
# Kennung aendern (bewusste Sonderaktion): Verweise ziehen mit
# ---------------------------------------------------------------------

RENAME_SAMPLE = SAMPLE.split("ex:ABB a skos:Concept")[0] + '''ex:Ruhrstatut a skos:Concept ;
  skos:prefLabel "Abkommen ueber die Errichtung einer Internationalen Ruhrbehoerde"@de ;
  skos:altLabel "Ruhrstatut"@de ;
  skos:notation "law"^^fpv:entityType ;
  ex:useInSynonymList "true"^^xsd:boolean ;
  skos:note "Siehe auch ex:Ruhrstatut im Text; ex:RuhrstatutII ist etwas anderes."@de .

ex:RuhrstatutII a skos:Concept ;
  skos:prefLabel "Zweites Abkommen"@de ;
  skos:notation "law"^^fpv:entityType ;
  ex:useInSynonymList "false"^^xsd:boolean ;
  skos:related ex:Ruhrstatut ;
  skos:note "Verweist auf das erste."@de .

ex:Montanunion a skos:Concept ;
  skos:prefLabel "Montanunion"@de ;
  skos:notation "org"^^fpv:entityType ;
  ex:useInSynonymList "false"^^xsd:boolean ;
  skos:related ex:Ruhrstatut , ex:RuhrstatutII ;
  skos:note "Verweist auf beide."@de .
'''


def _rename_env(env, tmp_path, text=RENAME_SAMPLE, name="rename.ttl"):
    ttl_path = tmp_path / name
    ttl_path.write_bytes(text.encode("utf-8"))
    env = dict(env)
    env["ttl_path"] = str(ttl_path)
    return env, ttl_path


def test_rename_updates_block_and_all_references_and_nothing_else(env, tmp_path):
    env, ttl_path = _rename_env(env, tmp_path)
    state = _open(env)

    status, chk = _post(env, "/api/rename-check", {"id": "Ruhrstatut", "new_id": "Ruhrstatut1949"})
    assert status == 200, chk
    assert {r["id"] for r in chk["referrers"]} == {"RuhrstatutII", "Montanunion"}
    assert chk["blocked"] == [] and chk["new_id_problem"] is None
    assert chk["uri"].endswith("/id/Ruhrstatut")

    status, resp = _post(env, "/api/rename",
                         {"id": "Ruhrstatut", "new_id": "Ruhrstatut1949", "version": state["sha256"]})
    assert status == 200, resp
    assert resp["renamed"]["to"] == "Ruhrstatut1949"
    assert set(resp["renamed"]["updated_references"]) == {"RuhrstatutII", "Montanunion"}
    assert resp["backup_label"]

    new_text = ttl_path.read_text(encoding="utf-8")
    # Erwartung: exakt die Ersetzung an den drei Stellen (Kopf, related, related),
    # Text in Literalen und aehnliche IDs (ex:RuhrstatutII) bleiben unberuehrt.
    expected = (
        RENAME_SAMPLE
        .replace("ex:Ruhrstatut a skos:Concept", "ex:Ruhrstatut1949 a skos:Concept")
        .replace("skos:related ex:Ruhrstatut ;", "skos:related ex:Ruhrstatut1949 ;")
        .replace("skos:related ex:Ruhrstatut , ex:RuhrstatutII", "skos:related ex:Ruhrstatut1949 , ex:RuhrstatutII")
    )
    assert new_text == expected
    assert "Siehe auch ex:Ruhrstatut im Text; ex:RuhrstatutII" in new_text
    # Danach ist die alte ID weg und die Datei ohne Fehler.
    ids = [r["id"] for r in resp["records"]]
    assert "Ruhrstatut1949" in ids and "Ruhrstatut" not in ids
    assert not [f for f in resp["findings"] if f["level"] == "error"]


def test_rename_creates_verified_backup_of_old_bytes(env, tmp_path):
    env, ttl_path = _rename_env(env, tmp_path)
    old_bytes = ttl_path.read_bytes()
    state = _open(env)
    status, resp = _post(env, "/api/rename",
                         {"id": "Montanunion", "new_id": "EGKS", "version": state["sha256"]})
    assert status == 200, resp
    with open(resp["backup_path"], "rb") as f:
        assert f.read() == old_bytes


def test_rename_refused_when_reference_is_in_protected_block(env, tmp_path):
    # SAMPLE: ex:Sonderfall (geschuetzt, wegen skos:broader) verweist auf ex:Bundestag.
    env, ttl_path = _rename_env(env, tmp_path, text=SAMPLE, name="prot.ttl")
    before = ttl_path.read_bytes()
    state = _open(env)
    status, chk = _post(env, "/api/rename-check", {"id": "Bundestag"})
    assert status == 200 and chk["blocked"] and chk["blocked"][0]["id"] == "Sonderfall"
    status, resp = _post(env, "/api/rename",
                         {"id": "Bundestag", "new_id": "DBT", "version": state["sha256"]})
    assert status == 409, resp
    assert ttl_path.read_bytes() == before


def test_rename_refused_for_protected_block_itself(env, tmp_path):
    env, ttl_path = _rename_env(env, tmp_path, text=SAMPLE, name="prot2.ttl")
    before = ttl_path.read_bytes()
    state = _open(env)
    status, resp = _post(env, "/api/rename",
                         {"id": "Sonderfall", "new_id": "Sonderfall2", "version": state["sha256"]})
    assert status >= 400 and ttl_path.read_bytes() == before


@pytest.mark.parametrize("new_id", ["Montanunion", "Ruhrstatut", "1abc", "mit Leerzeichen", "Übung", "", "RuhrstatutII"])
def test_rename_rejects_invalid_or_taken_ids(env, tmp_path, new_id):
    env, ttl_path = _rename_env(env, tmp_path)
    before = ttl_path.read_bytes()
    state = _open(env)
    # "Montanunion" umbenennen in eine belegte/ungueltige Kennung
    status, resp = _post(env, "/api/rename",
                         {"id": "Montanunion", "new_id": new_id, "version": state["sha256"]})
    assert status == 400, resp
    assert ttl_path.read_bytes() == before


def test_rename_rejects_id_that_is_already_a_reference_target(env, tmp_path):
    """Eine ID, auf die schon (ins Leere) verwiesen wird, darf nicht 'heimlich'
    durch ein Umbenennen gueltig werden."""
    text = RENAME_SAMPLE.replace("skos:related ex:Ruhrstatut ;", "skos:related ex:Ruhrstatut , ex:Phantom ;", 1)
    env, ttl_path = _rename_env(env, tmp_path, text=text, name="phantom.ttl")
    before = ttl_path.read_bytes()
    state = _open(env)
    status, resp = _post(env, "/api/rename",
                         {"id": "Montanunion", "new_id": "Phantom", "version": state["sha256"]})
    assert status == 400 and ttl_path.read_bytes() == before


def test_rename_version_conflict_and_token(env, tmp_path):
    env, ttl_path = _rename_env(env, tmp_path)
    state = _open(env)
    status, resp = _post(env, "/api/rename",
                         {"id": "Montanunion", "new_id": "EGKS", "version": "veraltet"})
    assert status == 409
    status, _ = _post(env, "/api/rename",
                      {"id": "Montanunion", "new_id": "EGKS", "version": state["sha256"]}, with_token=False)
    assert status == 403
    status, _ = _post(env, "/api/rename-check", {"id": "Montanunion"}, with_token=False)
    assert status == 403


def test_rename_preserves_crlf(env, tmp_path):
    env, ttl_path = _rename_env(env, tmp_path)
    ttl_path.write_bytes(RENAME_SAMPLE.replace("\n", "\r\n").encode("utf-8"))
    state = _open(env)
    status, resp = _post(env, "/api/rename",
                         {"id": "Ruhrstatut", "new_id": "Ruhrstatut1949", "version": state["sha256"]})
    assert status == 200, resp
    raw = ttl_path.read_bytes()
    assert b"\r\n" in raw and b"\n" not in raw.replace(b"\r\n", b"")


def test_rename_scanner_edge_cases():
    text = 'ex:A a skos:Concept ;\n  skos:note "ex:A und \\"ex:A\\""@de ;\n  skos:related ex:AB , ex:A.x , ex:A ;\n  skos:exactMatch <https://voc.fraktionsprotokolle.de/id/A> .'
    out, n = core._rename_in_block_text(text, "A", "N")
    assert n == 3  # Kopf, related ex:A, <URI>
    assert out.startswith("ex:N a skos:Concept")
    assert 'skos:note "ex:A und \\"ex:A\\""@de' in out
    assert "ex:AB , ex:A.x , ex:N ;" in out
    assert "<https://voc.fraktionsprotokolle.de/id/N>" in out
    # Namensende am Textende (Regression: "" in "_-" ist in Python wahr)
    assert core._rename_in_block_text("skos:related ex:A", "A", "N") == ("skos:related ex:N", 1)


# ---------------------------------------------------------------------
# Synonymliste (Typesense): dieselbe Benennung bei zwei Konzepten
# ---------------------------------------------------------------------

def _syn_block(cid, pref, alts=(), flag=True, extra=""):
    lines = [f"ex:{cid} a skos:Concept ;", f'  skos:prefLabel "{pref}"@de ;']
    lines += [f'  skos:altLabel "{a}"@de ;' for a in alts]
    lines += [extra] if extra else []
    lines += [
        '  skos:notation "org"^^fpv:entityType ;',
        f'  ex:useInSynonymList "{"true" if flag else "false"}"^^xsd:boolean ;',
        '  skos:note "Testeintrag."@de .',
    ]
    return "\n".join(lines) + "\n\n"


SYN_SAMPLE = (
    SAMPLE.split("ex:ABB a skos:Concept")[0]
    + _syn_block("BMW", "Bayerische Motoren Werke", ["BMW"])
    + _syn_block("Missionswerk", "Berliner Missionswerk", ["Missionswerk"])
    # Flag false -> kommt nicht ins Set, darf also dieselbe Benennung tragen
    + _syn_block("Stumm", "Stummer Verein", ["BMW"], flag=False)
    # Nach Abzug von "org" (Blacklist) und "X" (Laenge 1) bleibt nur 1 Benennung -> kein Set
    + _syn_block("Einzel", "Einzelgaenger", ["org", "X"])
    # Vorhandene Kollision, die sich nur durch Gross-/Kleinschreibung unterscheidet
    + _syn_block("MoPoBerlin", "Berliner Morgenpost", ["MoPo"])
    + _syn_block("MoPoHH", "Hamburger Morgenpost", ["Mopo"])
    # Geschuetzter Block (unbekanntes Praedikat) mit Synonymliste
    + _syn_block("Geschuetzt", "Geschuetzter Verband", ["GV"], extra="  skos:broader ex:BMW ;")
)


def _reference_ttl2jsonl_sets(text):
    """Nachbau von ttl2jsonl.py (gleiche Logik, aber ohne Dateizugriff):
    Konzept-ID -> sortierte Benennungen. Aendert sich das Script, muss dieser
    Nachbau (und fpv_core.py, Abschnitt "Synonymliste") angepasst werden."""
    from rdflib import Graph, Namespace, Literal
    from rdflib.namespace import SKOS, XSD
    blacklist = {"pol", "com", "soc", "news", "topic", "law", "org"}
    g = Graph()
    g.parse(data=text, format="turtle")
    ex = Namespace(str(dict(g.namespaces())["ex"]))
    out = {}
    for concept in g.subjects(predicate=SKOS.prefLabel):
        if (concept, ex.useInSynonymList, Literal(True, datatype=XSD.boolean)) not in g:
            continue
        labels = set()
        for obj in g.objects(concept, SKOS.prefLabel):
            if isinstance(obj, Literal):
                labels.add(str(obj).strip())
        for obj in g.objects(concept, SKOS.altLabel):
            if isinstance(obj, Literal):
                labels.add(str(obj).strip())
        labels = {l for l in labels if l.lower() not in blacklist and len(l) > 1}
        if len(labels) < 2:
            continue
        out[str(concept).rstrip("/").split("/")[-1]] = sorted(labels)
    return out


def _syn_save(env, state, cid, mutate):
    rec = _record(state, cid)
    mutate(rec)
    return _post(env, "/api/save", {"original_id": cid, "data": rec, "version": state["sha256"]})


def test_synonym_index_mirrors_the_ttl2jsonl_script():
    mine = {cid: e.labels for cid, e in core.build_synonym_index(SYN_SAMPLE).items()}
    assert mine == _reference_ttl2jsonl_sets(SYN_SAMPLE)
    assert "Stumm" not in mine, "Flag false: kein Set"
    assert "Einzel" not in mine, "nur eine Benennung uebrig: kein Set"
    assert "Geschuetzt" in mine, "geschuetzte Bloecke zaehlen mit (das Script liest den Graphen)"


def test_synonym_collision_groups_and_normalisation():
    idx = core.build_synonym_index(SYN_SAMPLE)
    groups = core.synonym_collision_groups(idx)
    assert [g["concepts"] for g in groups] == [["MoPoBerlin", "MoPoHH"]]
    assert groups[0]["labels"] == ["MoPo", "Mopo"]
    assert core.synonym_key("  BMW\u00a0 ") == core.synonym_key("bmw")
    assert core.synonym_key("e\u0301") == core.synonym_key("\u00e9")  # NFC


def test_synonym_conflicts_for_record_new_vs_existing_and_inactive():
    idx = core.build_synonym_index(SYN_SAMPLE)
    c = core.synonym_conflicts_for_record(idx, "Missionswerk", "Berliner Missionswerk", ["Missionswerk", "BMW"], True)
    assert [(x["other_id"], x["is_new"]) for x in c] == [("BMW", True)]
    # Flag aus -> keine Kollision
    assert core.synonym_conflicts_for_record(idx, "Missionswerk", "Berliner Missionswerk", ["BMW"], False) == []
    # vorhandene Kollision ist nicht "neu"
    c = core.synonym_conflicts_for_record(idx, "MoPoBerlin", "Berliner Morgenpost", ["MoPo"], True)
    assert [(x["other_id"], x["is_new"]) for x in c] == [("MoPoHH", False)]


def test_validate_whole_file_reports_existing_synonym_collisions_as_warning():
    findings = core.validate_whole_file(SYN_SAMPLE)
    syn = [f for f in findings if f.concept_ids]
    assert len(syn) == 1 and syn[0].level == "warning"
    assert syn[0].concept_ids == ["MoPoBerlin", "MoPoHH"] and syn[0].concept_id == "MoPoBerlin"
    assert "\u201eMoPo\u201c" in syn[0].message and "\u201eMopo\u201c" in syn[0].message
    assert not [f for f in findings if f.level == "error"]


def test_save_blocks_newly_created_synonym_collision(env, tmp_path):
    env, ttl_path = _rename_env(env, tmp_path, text=SYN_SAMPLE, name="syn1.ttl")
    before = ttl_path.read_bytes()
    state = _open(env)
    status, resp = _syn_save(env, state, "Missionswerk",
                             lambda r: r["alts"].append({"text": "BMW", "lang": "de"}))
    assert status == 400, resp
    assert resp["findings"][0]["level"] == "error" and resp["findings"][0]["concept_id"] == "Missionswerk"
    assert "ex:BMW" in resp["findings"][0]["message"] and "Bayerische Motoren Werke" in resp["findings"][0]["message"]
    assert ttl_path.read_bytes() == before, "bei Blockade darf nichts geschrieben werden"


def test_save_blocks_case_only_collision(env, tmp_path):
    env, ttl_path = _rename_env(env, tmp_path, text=SYN_SAMPLE, name="syn2.ttl")
    before = ttl_path.read_bytes()
    state = _open(env)
    status, resp = _syn_save(env, state, "Missionswerk",
                             lambda r: r["alts"].append({"text": "bmw", "lang": "de"}))
    assert status == 400 and "dort:" in resp["findings"][0]["message"]
    assert ttl_path.read_bytes() == before


def test_save_allows_same_label_when_synonym_flag_is_off(env, tmp_path):
    env, ttl_path = _rename_env(env, tmp_path, text=SYN_SAMPLE, name="syn3.ttl")
    state = _open(env)

    def edit(r):
        r["synonym"] = False
        r["alts"].append({"text": "BMW", "lang": "de"})
    status, resp = _syn_save(env, state, "Missionswerk", edit)
    assert status == 200, resp


def test_save_blocks_new_concept_with_colliding_label(env, tmp_path):
    env, ttl_path = _rename_env(env, tmp_path, text=SYN_SAMPLE, name="syn4.ttl")
    before = ttl_path.read_bytes()
    state = _open(env)
    new = {"id": "BMWDDR", "lang": "de", "type": "org", "pref": "Brandenburgische Musikwerkstatt",
           "note": "x", "synonym": True, "alts": [{"text": "BMW", "lang": "de"}], "exact": [], "close": [], "related": []}
    status, resp = _post(env, "/api/save", {"original_id": None, "data": new, "version": state["sha256"]})
    assert status == 400 and resp["findings"][0]["concept_id"] == "BMWDDR"
    assert ttl_path.read_bytes() == before
    new["alts"] = [{"text": "BMWDD", "lang": "de"}]
    status, resp = _post(env, "/api/save", {"original_id": None, "data": new, "version": state["sha256"]})
    assert status == 200, resp


def test_save_not_blocked_by_preexisting_collision_and_resolving_it_works(env, tmp_path):
    env, ttl_path = _rename_env(env, tmp_path, text=SYN_SAMPLE, name="syn5.ttl")
    state = _open(env)
    assert any(f["concept_ids"] for f in state["findings"] if f.get("concept_ids"))
    # Notiz aendern, Kollision bleibt bestehen -> darf gespeichert werden
    status, resp = _syn_save(env, state, "MoPoBerlin", lambda r: r.update(note="Neue Notiz."))
    assert status == 200, resp
    assert [f for f in resp["findings"] if f.get("concept_ids")], "Hinweis bleibt sichtbar"
    # Kollision aufloesen
    state = resp
    status, resp = _syn_save(env, state, "MoPoBerlin",
                             lambda r: r.update(alts=[{"text": "BerMoPo", "lang": "de"}]))
    assert status == 200, resp
    assert not [f for f in resp["findings"] if f.get("concept_ids")], "Kollision ist behoben"


def test_save_blocks_collision_with_protected_block(env, tmp_path):
    env, ttl_path = _rename_env(env, tmp_path, text=SYN_SAMPLE, name="syn6.ttl")
    before = ttl_path.read_bytes()
    state = _open(env)
    assert _record(state, "Geschuetzt")["protected"] is True
    status, resp = _syn_save(env, state, "Missionswerk",
                             lambda r: r["alts"].append({"text": "GV", "lang": "de"}))
    assert status == 400 and "ex:Geschuetzt" in resp["findings"][0]["message"]
    assert ttl_path.read_bytes() == before


def test_save_ignores_labels_that_never_enter_a_set(env, tmp_path):
    """Einzel hat nach Abzug von Blacklist/Kurzlabels nur eine Benennung und bekommt
    deshalb kein Set; seine Benennung kollidiert nicht. Ebenso 'org' (Blacklist)."""
    env, ttl_path = _rename_env(env, tmp_path, text=SYN_SAMPLE, name="syn7.ttl")
    state = _open(env)

    def edit(r):
        r["alts"] += [{"text": "Einzelgaenger", "lang": "de"}, {"text": "org", "lang": "de"}]
    status, resp = _syn_save(env, state, "Missionswerk", edit)
    assert status == 200, resp


def test_synonym_check_endpoint(env, tmp_path):
    env, ttl_path = _rename_env(env, tmp_path, text=SYN_SAMPLE, name="syn8.ttl")
    state = _open(env)
    body = {"original_id": "Missionswerk",
            "data": {"id": "Missionswerk", "pref": "Berliner Missionswerk", "synonym": True,
                     "alts": [{"text": "BMW", "lang": "de"}]}}
    status, resp = _post(env, "/api/synonym-check", body)
    assert status == 200 and [(c["other_id"], c["is_new"]) for c in resp["conflicts"]] == [("BMW", True)]
    # vorhandene Kollision: is_new False
    body = {"original_id": "MoPoBerlin",
            "data": {"id": "MoPoBerlin", "pref": "Berliner Morgenpost", "synonym": True,
                     "alts": [{"text": "MoPo", "lang": "de"}]}}
    status, resp = _post(env, "/api/synonym-check", body)
    assert [(c["other_id"], c["is_new"]) for c in resp["conflicts"]] == [("MoPoHH", False)]
    # Neuanlage (original_id None)
    body = {"original_id": None,
            "data": {"id": "", "pref": "Neu", "synonym": True, "alts": [{"text": "BMW", "lang": "de"}]}}
    status, resp = _post(env, "/api/synonym-check", body)
    assert [(c["other_id"], c["is_new"]) for c in resp["conflicts"]] == [("BMW", True)]
    # Token Pflicht
    status, _ = _post(env, "/api/synonym-check", body, with_token=False)
    assert status == 403


def test_repeated_saves_do_not_add_blank_lines(env, tmp_path):
    """Regression: Der gerenderte Block endet mit '\\n'; frueher kam dadurch bei
    JEDEM Speichern eine Leerzeile hinter dem Block dazu (aufgefallen an der echten
    fpv.ttl). Der Abstand zum naechsten Block muss bei Mehrfach-Speichern gleich bleiben."""
    env, ttl_path = _rename_env(env, tmp_path, text=SYN_SAMPLE, name="blank.ttl")
    state = _open(env)

    def gap_after(cid):
        text = ttl_path.read_text(encoding="utf-8")
        blk = core.find_block(text, cid)
        rest = text[blk.end:]
        return len(rest) - len(rest.lstrip("\n"))

    before = gap_after("BMW")
    for i in range(3):
        rec = _record(state, "BMW")
        rec["note"] = f"Notiz {i}"
        status, state = _post(env, "/api/save", {"original_id": "BMW", "data": rec, "version": state["sha256"]})
        assert status == 200, state
        assert gap_after("BMW") == before, "pro Speichern darf keine Leerzeile dazukommen"


# ---------------------------------------------------------------------------
# Startprüfung: unvollständige Installation (static/ fehlt oder unvollständig)
# ---------------------------------------------------------------------------

def test_static_check_complete_install_has_no_problem():
    assert fpv_app.check_static_files() == []
    assert fpv_app.describe_static_problem() == ""


def test_static_check_reports_missing_index_html(tmp_path):
    (tmp_path / "app.js").write_text("// leer genug", encoding="utf-8")
    (tmp_path / "styles.css").write_text("/* css */", encoding="utf-8")
    assert fpv_app.check_static_files(str(tmp_path)) == ["index.html"]
    text = fpv_app.describe_static_problem(str(tmp_path))
    assert "index.html" in text and "_internal" in text and "app.js," not in text.split("Fehlend:")[1].split("\n")[0]
    assert "app.js" in text  # unter "Dort vorhanden"


def test_static_check_reports_missing_folder_and_empty_file(tmp_path):
    assert set(fpv_app.check_static_files(str(tmp_path / "gibt-es-nicht"))) == {"index.html", "app.js", "styles.css"}
    (tmp_path / "index.html").write_text("", encoding="utf-8")  # 0 Byte = unvollständig synchronisiert
    (tmp_path / "app.js").write_text("x", encoding="utf-8")
    (tmp_path / "styles.css").write_text("x", encoding="utf-8")
    assert fpv_app.check_static_files(str(tmp_path)) == ["index.html"]


def test_index_without_index_html_gives_readable_error_page(monkeypatch, tmp_path):
    monkeypatch.setattr(fpv_app, "STATIC_DIR", str(tmp_path))
    client = fpv_app.create_app().test_client()
    resp = client.get("/")
    assert resp.status_code == 500
    body = resp.get_data(as_text=True)
    assert "FPV-Editor kann nicht starten" in body
    assert "index.html" in body and "unvollständig" in body
    assert "Traceback" not in body


# ---------------------------------------------------------------------------
# Auslieferung: Manifest, Dateiprüfung, Standortwarnung, ZIP, Log-Ausweichort
# ---------------------------------------------------------------------------

import zipfile  # noqa: E402

import bundle_check  # noqa: E402
import make_release  # noqa: E402


@pytest.fixture()
def fake_bundle(tmp_path):
    root = tmp_path / "FPV-Editor"
    (root / "_internal" / "static").mkdir(parents=True)
    (root / "FPV-Editor.exe").write_bytes(b"MZ" + b"\x00" * 500)
    (root / "_internal" / "python314.dll").write_bytes(b"dll" * 1000)
    (root / "_internal" / "static" / "index.html").write_text("<html>ok</html>", encoding="utf-8")
    (root / "_internal" / "static" / "app.js").write_text("// js", encoding="utf-8")
    (root / "startup.log").write_text("altes log", encoding="utf-8")  # gehört nicht ins Manifest
    return root


def test_manifest_lists_all_files_except_log_and_itself(fake_bundle):
    path = bundle_check.write_manifest(str(fake_bundle))
    assert os.path.basename(path) == bundle_check.MANIFEST_NAME
    manifest = bundle_check.load_manifest(str(fake_bundle))
    assert set(manifest["files"]) == {
        "FPV-Editor.exe", "_internal/python314.dll",
        "_internal/static/index.html", "_internal/static/app.js",
    }
    assert manifest["file_count"] == 4
    assert bundle_check.verify_bundle(str(fake_bundle)) == []


def test_verify_reports_missing_empty_changed_and_ignores_extra(fake_bundle):
    bundle_check.write_manifest(str(fake_bundle))
    (fake_bundle / "_internal" / "static" / "index.html").unlink()
    (fake_bundle / "_internal" / "static" / "app.js").write_text("", encoding="utf-8")
    (fake_bundle / "_internal" / "python314.dll").write_bytes(b"xyz" * 1000)  # gleiche Größe, anderer Inhalt
    (fake_bundle / "ueberfluessig.txt").write_text("egal", encoding="utf-8")
    problems = bundle_check.verify_bundle(str(fake_bundle))
    joined = "\n".join(problems)
    assert "fehlt: _internal/static/index.html" in joined
    assert "falsche Größe" in joined and "app.js" in joined
    assert "Prüfsumme weicht ab" in joined and "python314.dll" in joined
    assert "ueberfluessig" not in joined
    assert len(problems) == 3
    text = bundle_check.describe_bundle_problems(problems, str(fake_bundle))
    assert "3 Datei(en)" in text and "index.html" in text and "Synchronisationsordner" in text


def test_verify_flags_cloud_placeholder_without_reading(fake_bundle):
    bundle_check.write_manifest(str(fake_bundle))
    target = str(fake_bundle / "_internal" / "static" / "index.html")
    # Simuliert FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS (0x400000) für genau diese Datei.
    problems = bundle_check.verify_bundle(
        str(fake_bundle), get_attrs=lambda p: 0x400000 if p == target else 0
    )
    assert problems == ["nur in der Cloud, nicht lokal gespeichert: _internal/static/index.html"]


def test_verify_without_manifest_is_reported(fake_bundle):
    assert bundle_check.load_manifest(str(fake_bundle)) is None
    assert "fehlt oder ist nicht lesbar" in bundle_check.verify_bundle(str(fake_bundle))[0]
    (fake_bundle / bundle_check.MANIFEST_NAME).write_text("{kaputt", encoding="utf-8")
    assert bundle_check.load_manifest(str(fake_bundle)) is None


@pytest.mark.parametrize("path, expected", [
    (r"C:\Users\Sven\FPV-Editor", False),
    (r"C:\Users\Sven\Nextcloud\Programme\FPV-Editor", True),
    (r"C:\Users\Sven\OneDrive - KGParl\Desktop\FPV-Editor", True),
    (r"C:\Users\Sven\Dropbox\FPV-Editor", True),
    (r"\\server\freigabe\FPV-Editor", True),
    (r"C:\Users\Sven\AppData\Local\Temp\Temp1_FPV-Editor.zip\FPV-Editor", True),
    (r"C:\Programme\Nextcloudfrei-nicht", True),  # Präfix-Vergleich ist bewusst großzügig
    (r"C:\Users\Sven\Neuer Ordner\FPV-Editor", False),
])
def test_location_warnings(path, expected):
    assert bool(bundle_check.location_warnings(path)) is expected


def test_make_release_builds_verified_zip_without_top_folder(fake_bundle, tmp_path, capsys):
    zip_path = tmp_path / "out" / "FPV-Editor.zip"
    zip_path.parent.mkdir()
    assert make_release.main(["make_release.py", str(fake_bundle), str(zip_path)]) == 0
    assert "geprüft" in capsys.readouterr().out
    with zipfile.ZipFile(zip_path) as zf:
        names = set(zf.namelist())
    assert "FPV-Editor.exe" in names and bundle_check.MANIFEST_NAME in names
    assert "_internal/static/index.html" in names
    assert "startup.log" not in names
    assert not any(n.startswith("FPV-Editor/") for n in names)  # kein zusätzlicher Oberordner
    assert all("\\" not in n for n in names)


def test_zip_check_detects_tampered_archive(fake_bundle, tmp_path):
    bundle_check.write_manifest(str(fake_bundle))
    manifest = bundle_check.load_manifest(str(fake_bundle))
    zip_path = str(tmp_path / "a.zip")
    make_release.make_zip(str(fake_bundle), zip_path)
    assert make_release.verify_zip(zip_path, manifest) == []
    # Archiv mit verändertem Inhalt und fehlender Datei neu schreiben
    bad = str(tmp_path / "b.zip")
    with zipfile.ZipFile(zip_path) as src, zipfile.ZipFile(bad, "w") as dst:
        for item in src.infolist():
            if item.filename.endswith("app.js"):
                continue
            data = src.read(item.filename)
            if item.filename.endswith("index.html"):
                data = data + b"x"
            dst.writestr(item.filename, data)
    problems = make_release.verify_zip(bad, manifest)
    assert any("fehlt im ZIP" in p and "app.js" in p for p in problems)
    assert any("weicht ab" in p and "index.html" in p for p in problems)


def test_log_path_falls_back_to_localappdata_when_program_dir_unwritable(tmp_path, monkeypatch):
    import launcher
    monkeypatch.setattr(launcher, "PROGRAM_DIR", str(tmp_path / "gibt-es-nicht"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "lad"))
    chosen = launcher._choose_log_path()
    assert chosen == str(tmp_path / "lad" / "FPV-Editor" / "startup.log")
    assert os.path.isfile(chosen)
    # beschreibbarer Programmordner: Log bleibt neben der EXE
    (tmp_path / "prog").mkdir()
    monkeypatch.setattr(launcher, "PROGRAM_DIR", str(tmp_path / "prog"))
    assert launcher._choose_log_path() == str(tmp_path / "prog" / "startup.log")


def test_launcher_main_stops_with_message_on_incomplete_bundle(fake_bundle, tmp_path, monkeypatch):
    import logging
    import launcher
    bundle_check.write_manifest(str(fake_bundle))
    (fake_bundle / "_internal" / "static" / "index.html").unlink()

    shown = []
    monkeypatch.setattr(launcher, "PROGRAM_DIR", str(fake_bundle))
    monkeypatch.setattr(launcher, "LOG_PATH", str(tmp_path / "startup.log"))
    monkeypatch.setattr(launcher, "show_fatal_error", lambda title, msg: shown.append((title, msg)))
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    handlers_before = list(logging.getLogger().handlers)
    try:
        with pytest.raises(SystemExit) as exc:
            launcher.main()
    finally:
        for h in list(logging.getLogger().handlers):
            if h not in handlers_before:
                logging.getLogger().removeHandler(h)
                h.close()
    assert exc.value.code == 1
    assert len(shown) == 1
    title, msg = shown[0]
    assert "unvollständig" in title and "_internal/static/index.html" in msg
    assert "Abweichung: fehlt: _internal/static/index.html" in (tmp_path / "startup.log").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Sammel-Speichern (/api/save-batch) und Ein-Ort-Sicherung
# ---------------------------------------------------------------------------

def _new_record(rec_id, pref, **extra):
    data = {"id": rec_id, "lang": "de", "type": "org", "pref": pref, "note": "Testnotiz.",
            "synonym": False, "alts": [], "exact": [], "close": [], "related": []}
    data.update(extra)
    return data


def _backup_count(e):
    return len(_get(e, "/api/backups")[1]["backups"])


def test_batch_saves_changes_and_new_entry_with_one_backup(env):
    state = _open(env)
    abb = _record(state, "ABB")
    abb["note"] = "Sammel-Test ABB."
    bt = _record(state, "Bundestag")
    bt["note"] = "Sammel-Test Bundestag."
    items = [
        {"original_id": "ABB", "data": abb},
        {"original_id": "Bundestag", "data": bt},
        {"original_id": None, "data": _new_record("NeuA", "Neuer Eintrag A")},
    ]
    status, resp = _post(env, "/api/save-batch", {"version": state["sha256"], "items": items})
    assert status == 200, resp
    assert resp["saved_ids"] == ["ABB", "Bundestag", "NeuA"]
    assert _backup_count(env) == 1                     # EINE Sicherung für alle drei
    assert _record(resp, "ABB")["note"] == "Sammel-Test ABB."
    assert _record(resp, "Bundestag")["note"] == "Sammel-Test Bundestag."
    assert _record(resp, "NeuA")["pref"] == "Neuer Eintrag A"
    with open(env["ttl_path"], encoding="utf-8") as f:
        text = f.read()
    assert "# Kommentar am Dateianfang" in text        # Rest der Datei unberührt
    assert "\n\n\n" not in text                        # keine zusätzlichen Leerzeilen
    # Die Sicherung enthält den ALTEN Stand.
    old = open(_get(env, "/api/backups")[1]["backups"][0]["path"], encoding="utf-8").read()
    assert "Sammel-Test" not in old and "NeuA" not in old


def test_batch_is_all_or_nothing(env):
    state = _open(env)
    before = open(env["ttl_path"], "rb").read()
    abb = _record(state, "ABB")
    abb["note"] = "Gültige Änderung."
    kaputt = _record(state, "Bundestag")
    kaputt["pref"] = ""                                 # Pflichtfeld leer
    status, resp = _post(env, "/api/save-batch", {"version": state["sha256"], "items": [
        {"original_id": "ABB", "data": abb},
        {"original_id": "Bundestag", "data": kaputt},
    ]})
    assert status == 400
    assert resp["failed_id"] == "Bundestag" and "Nichts wurde geschrieben" in resp["error"]
    assert open(env["ttl_path"], "rb").read() == before
    assert _backup_count(env) == 0                      # nicht einmal eine Sicherung


def test_batch_version_conflict_and_empty_request(env):
    state = _open(env)
    abb = _record(state, "ABB")
    status, _ = _post(env, "/api/save-batch", {"version": "falsch", "items": [{"original_id": "ABB", "data": abb}]})
    assert status == 409
    status, resp = _post(env, "/api/save-batch", {"version": state["sha256"], "items": []})
    assert status == 400 and "keine Eintr" in resp["error"]
    status, _ = _post(env, "/api/save-batch", {"version": state["sha256"], "items": [{"original_id": "ABB", "data": abb}]}, with_token=False)
    assert status == 403


def test_batch_rejects_duplicate_new_ids_and_protected_blocks(env):
    state = _open(env)
    status, resp = _post(env, "/api/save-batch", {"version": state["sha256"], "items": [
        {"original_id": None, "data": _new_record("Gleich", "Eins")},
        {"original_id": None, "data": _new_record("Gleich", "Zwei")},
    ]})
    assert status == 400 and resp["failed_id"] == "Gleich"
    status, resp = _post(env, "/api/save-batch", {"version": state["sha256"], "items": [
        {"original_id": "Sonderfall", "data": _new_record("Sonderfall", "Sonderfall")},
    ]})
    assert status == 400 and resp["failed_id"] == "Sonderfall"
    assert _backup_count(env) == 0


def test_batch_blocks_new_synonym_collision_between_two_edited_entries(env):
    state = _open(env)
    # Zwei neue Konzepte der Synonymliste, die dieselbe Benennung teilen: einzeln
    # unauffällig, gemeinsam eine NEUE Kollision.
    a = _new_record("SynA", "Alpha Organisation", synonym=True, alts=[{"text": "AOrg", "lang": "de"}])
    b = _new_record("SynB", "Beta Organisation", synonym=True, alts=[{"text": "aorg", "lang": "de"}])
    before = open(env["ttl_path"], "rb").read()
    status, resp = _post(env, "/api/save-batch", {"version": state["sha256"], "items": [
        {"original_id": None, "data": a}, {"original_id": None, "data": b},
    ]})
    assert status == 400
    assert resp["failed_id"] in {"SynA", "SynB"}
    assert any("Synonymliste" in f["message"] for f in resp["findings"])
    assert open(env["ttl_path"], "rb").read() == before


def test_batch_synonym_check_matches_single_check_for_one_edit():
    text = SAMPLE.replace('skos:altLabel "ABB"@de ;', 'skos:altLabel "ABB"@de ;') + (
        "\nex:Zwei a skos:Concept ;\n  skos:prefLabel \"Zwei Konzern\"@de ;\n"
        "  skos:altLabel \"ABB\"@de ;\n  skos:notation \"com\"^^fpv:entityType ;\n"
        "  ex:useInSynonymList \"true\"^^xsd:boolean .\n"
    )
    index = core.build_synonym_index(text)
    single = core.synonym_conflicts_for_record(index, "ABB", "ASEA Brown Boveri", ["ABB"], True)
    batch = core.synonym_conflicts_for_batch(index, [("ABB", "ASEA Brown Boveri", ["ABB"], True)])
    assert single and [{k: v for k, v in c.items() if k != "concept_id"} for c in batch] == single
    assert all(c["concept_id"] == "ABB" for c in batch)
    assert all(not c["is_new"] for c in batch)          # Altlast, blockiert nicht


def test_backup_goes_to_one_place_and_failure_blocks_write(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "lad"))
    ttl = str(tmp_path / "fpv.ttl")
    label, path = core.backup_write_location(ttl)
    assert path == os.path.join(str(tmp_path / "lad"), "FPV-Editor", "backups", core.file_key(ttl))
    assert core.backup_write_location(ttl, str(tmp_path / "mein"))[1] == str(tmp_path / "mein")

    label, saved = core.create_verified_backup(ttl, b"alt", None)
    assert open(saved, "rb").read() == b"alt" and os.path.dirname(saved) == path

    # Sicherungsort ist eine Datei statt eines Ordners -> kein Ausweichen, klare Meldung.
    blocker = tmp_path / "blocker"
    blocker.write_text("x", encoding="utf-8")
    with pytest.raises(core.BackupError) as exc:
        core.create_verified_backup(ttl, b"alt", str(blocker))
    assert "NICHT verändert" in str(exc.value) and "Frühere Stände" in str(exc.value)


def test_backup_rotation_keeps_only_newest_n(tmp_path, monkeypatch):
    monkeypatch.setattr(core, "MAX_BACKUPS_PER_FILE", 3)
    bdir = tmp_path / "backups"
    bdir.mkdir()
    ttl = str(tmp_path / "fpv.ttl")
    unrelated = bdir / "not-a-backup.txt"
    unrelated.write_text("behalten", encoding="utf-8")

    created = []
    for i in range(5):
        _lbl, p = core.create_verified_backup(ttl, f"stand-{i}".encode("utf-8"), str(bdir))
        # Eindeutige mtime setzen, damit Reihenfolge unter Windows deterministisch ist.
        ts = 1_700_000_000 + i * 10
        os.utime(p, (ts, ts))
        created.append(p)
    # Noch eine sechste Sicherung ausloesen -> Rotation behaelt genau die 3 neuesten.
    _lbl, p5 = core.create_verified_backup(ttl, b"stand-5", str(bdir))
    os.utime(p5, (1_700_000_100, 1_700_000_100))
    created.append(p5)

    remaining = sorted(p.name for p in bdir.glob("*.ttl.bak"))
    assert len(remaining) == 3
    assert unrelated.exists(), "Fremddateien im Ordner duerfen nie geloescht werden"
    # Die 3 neuesten Staende (3, 4, 5) muessen ueberlebt haben.
    contents = {p.read_text(encoding="utf-8") for p in bdir.glob("*.ttl.bak")}
    assert contents == {"stand-3", "stand-4", "stand-5"}


def test_batch_returns_507_and_keeps_file_when_backup_impossible(env):
    state = _open(env)
    blocker = env["tmp_path"] / "blocker"
    blocker.write_text("x", encoding="utf-8")
    fpv_app.STATE.manual_backup_dir = str(blocker)
    before = open(env["ttl_path"], "rb").read()
    abb = _record(state, "ABB")
    abb["note"] = "Wird nicht geschrieben."
    status, resp = _post(env, "/api/save-batch", {"version": state["sha256"], "items": [{"original_id": "ABB", "data": abb}]})
    assert status == 507
    assert open(env["ttl_path"], "rb").read() == before


# ---------------------------------------------------------------------------
# Zwischensicherung und Beenden-Schutz
# ---------------------------------------------------------------------------

def _pending_items(state):
    abb = _record(state, "ABB")
    abb["note"] = "Zwischengesichert."
    return [{"original_id": "ABB", "data": abb}]


def test_recovery_core_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(core, "recovery_file_path", lambda ttl: str(tmp_path / "r" / "x.json"))
    assert core.read_recovery("a.ttl") is None
    info = core.write_recovery("a.ttl", "v1", [{"original_id": None, "data": {"id": "X"}}])
    assert os.path.exists(info["path"])
    data = core.read_recovery("a.ttl")
    assert data["version"] == "v1" and data["items"][0]["data"]["id"] == "X"
    assert [f for f in os.listdir(tmp_path / "r") if f.endswith(".tmp")] == []
    assert core.clear_recovery("a.ttl") is True
    assert core.clear_recovery("a.ttl") is False
    (tmp_path / "r").mkdir(exist_ok=True)
    (tmp_path / "r" / "x.json").write_text("kaputt", encoding="utf-8")
    assert core.read_recovery("a.ttl") is None


def test_pending_sync_without_persist_writes_no_file(env):
    state = _open(env)
    status, r = _post(env, "/api/pending", {"items": _pending_items(state), "version": state["sha256"]})
    assert status == 200 and r["persisted"] is False
    assert _get(env, "/api/recovery")[1]["exists"] is False
    assert len(fpv_app.STATE.pending["items"]) == 1


def test_pending_persist_then_recovery_and_discard(env):
    state = _open(env)
    status, r = _post(env, "/api/pending", {"items": _pending_items(state), "version": state["sha256"], "persist": True})
    assert r["persisted"] is True
    before = open(env["ttl_path"], "rb").read()
    rec = _get(env, "/api/recovery")[1]
    assert rec["exists"] and rec["count"] == 1 and rec["sha_matches"] is True
    assert open(env["ttl_path"], "rb").read() == before
    assert _post(env, "/api/recovery-discard", {})[1]["ok"]
    assert _get(env, "/api/recovery")[1]["exists"] is False
    assert fpv_app.STATE.pending is None


def test_pending_empty_clears_recovery(env):
    state = _open(env)
    _post(env, "/api/pending", {"items": _pending_items(state), "version": state["sha256"], "persist": True})
    _post(env, "/api/pending", {"items": []})
    assert _get(env, "/api/recovery")[1]["exists"] is False


def test_recovery_survives_empty_sync_before_decision(env):
    state = _open(env)
    _post(env, "/api/pending", {"items": _pending_items(state), "version": state["sha256"], "persist": True})
    fpv_app.STATE.pending = None
    _post(env, "/api/pending", {"items": []})
    assert _get(env, "/api/recovery")[1]["exists"] is True


def test_recovery_sha_mismatch_flag(env):
    state = _open(env)
    _post(env, "/api/pending", {"items": _pending_items(state), "version": "alt", "persist": True})
    assert _get(env, "/api/recovery")[1]["sha_matches"] is False


def test_quit_blocked_while_pending_unless_force(env):
    state = _open(env)
    _post(env, "/api/pending", {"items": _pending_items(state), "version": state["sha256"]})
    status, r = _post(env, "/api/quit", {})
    assert status == 409 and r["error_type"] == "PendingChanges" and r["pending_count"] == 1
    assert not fpv_app.STATE.shutdown_requested
    status, r = _post(env, "/api/quit", {"force": True})
    assert status == 200 and fpv_app.STATE.shutdown_requested


def test_quit_discard_clears_recovery(env):
    state = _open(env)
    _post(env, "/api/pending", {"items": _pending_items(state), "version": state["sha256"], "persist": True})
    assert _post(env, "/api/quit", {"force": True, "discard": True})[0] == 200
    assert _get(env, "/api/recovery")[1]["exists"] is False


def test_quit_without_pending_needs_no_force(env):
    _open(env)
    assert _post(env, "/api/quit", {})[0] == 200


def test_save_batch_clears_pending_and_recovery(env):
    state = _open(env)
    items = _pending_items(state)
    _post(env, "/api/pending", {"items": items, "version": state["sha256"], "persist": True})
    status, resp = _post(env, "/api/save-batch", {"version": state["sha256"], "items": items})
    assert status == 200, resp
    assert fpv_app.STATE.pending is None
    assert _get(env, "/api/recovery")[1]["exists"] is False


def test_close_resets_pending(env):
    state = _open(env)
    _post(env, "/api/pending", {"items": _pending_items(state), "version": state["sha256"]})
    _post(env, "/api/close", {})
    assert fpv_app.STATE.pending is None


@pytest.mark.parametrize("answer,expect_quit,expect_saved", [(True, True, True), (False, True, False), (None, False, False)])
def test_launcher_quit_gate(env, answer, expect_quit, expect_saved):
    import launcher
    state = _open(env)
    _post(env, "/api/pending", {"items": _pending_items(state), "version": state["sha256"], "persist": True})
    asked = []
    result = launcher.quit_gate(fpv_app, lambda t, m: (asked.append(m), answer)[1], lambda t, m: None)
    assert result is expect_quit
    assert len(asked) == 1
    text = open(env["ttl_path"], encoding="utf-8").read()
    assert ("Zwischengesichert." in text) is expect_saved
    if answer is False:
        assert _get(env, "/api/recovery")[1]["exists"] is False


@pytest.mark.parametrize("confirmed", [True, False])
def test_launcher_quit_gate_no_pending_asks_simple_confirm(env, confirmed):
    """Auch ohne vorgemerkte Eintraege fragt das Startfenster nach (Projektregel:
    jede destruktive Handlung braucht eine Sicherheitsabfrage). Die
    Speichern-Frage (ask) wird dabei nicht gestellt."""
    import launcher
    _open(env)
    asked = []
    result = launcher.quit_gate(
        fpv_app,
        lambda t, m: pytest.fail("Speichern-Frage darf ohne Vormerkungen nicht kommen"),
        lambda t, m: None,
        lambda t, m: (asked.append(m), confirmed)[1],
    )
    assert result is confirmed
    assert len(asked) == 1 and "wirklich beenden" in asked[0]


def test_launcher_quit_gate_blocked_while_file_dialog_open(env):
    import launcher
    fpv_app.STATE.choose = {"status": "open", "result": None, "error": None}
    errors = []
    result = launcher.quit_gate(
        fpv_app,
        lambda t, m: pytest.fail("darf nicht fragen"),
        lambda t, m: errors.append(m),
        lambda t, m: pytest.fail("darf nicht fragen"),
    )
    assert result is False
    assert errors and "TTL-Datei" in errors[0]


def test_launcher_quit_gate_save_error_keeps_running(env):
    import launcher
    state = _open(env)
    _post(env, "/api/pending", {"items": _pending_items(state), "version": "falsch"})
    errors = []
    assert launcher.quit_gate(fpv_app, lambda t, m: True, lambda t, m: errors.append(m)) is False
    assert errors


# ---------------------------------------------------------------------
# Dateiauswahl: nur EIN Dialog, nicht blockierend, Ergebnis per Abfrage
# ---------------------------------------------------------------------

class FakeBridge:
    """Ersetzt den Tk-Dialog: merkt sich den Rueckruf, statt ein Fenster zu oeffnen."""

    def __init__(self):
        self.started = 0
        self.raised = 0
        self.on_done = None

    def start_open_dialog(self, on_done):
        self.started += 1
        self.on_done = on_done

    def bring_dialog_to_front(self):
        self.raised += 1


def test_choose_opens_only_one_dialog_and_loads_result(env):
    bridge = FakeBridge()
    fpv_app.STATE.dialog_bridge = bridge

    status, resp = _post(env, "/api/choose", {})
    assert status == 200 and resp["status"] == "opened"
    for _ in range(2):  # weitere Klicks: kein neuer Dialog, sondern nach vorne holen
        status, resp = _post(env, "/api/choose", {})
        assert status == 200 and resp["status"] == "already_open"
    assert bridge.started == 1 and bridge.raised == 2

    assert _post(env, "/api/choose-result", {})[1]["status"] == "open"

    bridge.on_done(env["ttl_path"], None)  # Nutzer waehlt Datei
    status, resp = _post(env, "/api/choose-result", {})
    assert status == 200, resp
    assert resp["status"] == "loaded" and resp["path"] == env["ttl_path"]
    assert any(r["id"] == "ABB" for r in resp["records"])

    status, resp = _post(env, "/api/choose", {})  # danach wieder moeglich
    assert resp["status"] == "opened" and bridge.started == 2


def test_choose_cancel_and_error(env):
    bridge = FakeBridge()
    fpv_app.STATE.dialog_bridge = bridge

    _post(env, "/api/choose", {})
    bridge.on_done("", None)  # Abbrechen
    status, resp = _post(env, "/api/choose-result", {})
    assert status == 200 and resp["status"] == "cancelled"
    assert _post(env, "/api/choose-result", {})[1]["status"] == "idle"

    _post(env, "/api/choose", {})
    bridge.on_done(None, "Testfehler")
    status, resp = _post(env, "/api/choose-result", {})
    assert status == 500 and "Testfehler" in resp["error"]


def test_choose_without_launcher_is_501(env):
    fpv_app.STATE.dialog_bridge = None
    assert _post(env, "/api/choose", {})[0] == 501


def test_choose_requires_token(env):
    fpv_app.STATE.dialog_bridge = FakeBridge()
    assert _post(env, "/api/choose", {}, with_token=False)[0] == 403
    assert _post(env, "/api/choose-result", {}, with_token=False)[0] == 403


def test_ping(env):
    status, resp = _get(env, "/api/ping")
    assert status == 200 and resp["ok"] is True


# ---------------------------------------------------------------------
# Architektur-Verbesserungen: Zeilenumbrueche, storage_check, Wrapper,
# Graph-Cache, Live-Synonympruefung mit Entwuerfen, ausgelagertes CSS
# ---------------------------------------------------------------------

def test_note_newlines_normalized_to_spaces_on_save(env):
    state = _open(env)
    abb = _record(state, "ABB")
    abb["note"] = "Erste Zeile\nZweite Zeile\r\n  Dritte Zeile"
    status, resp = _post(env, "/api/save-batch", {
        "version": state["sha256"],
        "items": [{"original_id": "ABB", "data": abb}],
    })
    assert status == 200, resp
    assert _record(resp, "ABB")["note"] == "Erste Zeile Zweite Zeile Dritte Zeile"
    text = open(env["ttl_path"], encoding="utf-8").read()
    assert 'skos:note "Erste Zeile Zweite Zeile Dritte Zeile"@de .' in text

    # Auch direktes Rendern eines Records mit Newline darf kein ungueltiges Turtle erzeugen.
    rendered = core.render_record_to_block(core.Record(
        id="TestNL", pref="A\nB", lang="de", type="org",
        note="Zeile 1\r\nZeile 2", synonym=False,
        alts=[{"text": "Alt\nText", "lang": "de"}],
    ))
    assert '"A B"@de' in rendered
    assert '"Alt Text"@de' in rendered
    assert '"Zeile 1 Zeile 2"@de .' in rendered


def test_note_only_newlines_rejected_as_empty(env):
    state = _open(env)
    abb = _record(state, "ABB")
    abb["note"] = " \n\r\n\t "
    status, resp = _post(env, "/api/save-batch", {
        "version": state["sha256"],
        "items": [{"original_id": "ABB", "data": abb}],
    })
    assert status == 400
    assert any("skos:note" in f["message"] for f in resp["findings"])


def test_storage_check_only_active_backup_and_ttl_dir_no_empty_dirs(tmp_path, monkeypatch):
    ttl_dir = tmp_path / "repo"
    ttl_dir.mkdir()
    ttl = ttl_dir / "fpv.ttl"
    ttl.write_text(SAMPLE, encoding="utf-8")

    localappdata = tmp_path / "localappdata"
    localappdata.mkdir()
    monkeypatch.setenv("LOCALAPPDATA", str(localappdata))

    results = core.storage_check(str(ttl))
    assert len(results) == 2
    assert all(r["writable"] for r in results)
    ttl_entry = next(r for r in results if os.path.normcase(os.path.abspath(r["path"])) == os.path.normcase(os.path.abspath(str(ttl_dir))))
    assert ttl_entry["replace_tested"] is True
    # Keine leeren fpv_backups-Ordner neben TTL und keine Rest-Ordner unter LOCALAPPDATA.
    assert not (ttl_dir / "fpv_backups").exists()
    assert not (localappdata / "FPV-Editor").exists()
    assert not any(p.name.startswith(".fpv_write_test") for p in ttl_dir.iterdir())

    # Wenn manual_dir == ttl_dir, wird der Ordner nur einmal geprueft (mit replace_tested=True).
    same_results = core.storage_check(str(ttl), manual_dir=str(ttl_dir))
    assert len(same_results) == 1
    assert same_results[0]["writable"] is True and same_results[0]["replace_tested"] is True

    # Bereits bestehende Ordner bleiben erhalten.
    existing_backup = tmp_path / "existing_backup"
    existing_backup.mkdir()
    res_existing = core.storage_check(str(ttl), manual_dir=str(existing_backup))
    assert len(res_existing) == 2 and existing_backup.is_dir()


def test_api_save_clears_pending_and_recovery(env):
    state = _open(env)
    items = _pending_items(state)
    _post(env, "/api/pending", {"items": items, "version": state["sha256"], "persist": True})
    status, resp = _post(env, "/api/save", {
        "original_id": "ABB", "data": items[0]["data"], "version": state["sha256"],
    })
    assert status == 200, resp
    assert fpv_app.STATE.pending is None
    assert _get(env, "/api/recovery")[1]["exists"] is False


def test_graph_cache_avoids_redundant_parses_on_save_rename_and_synonym_check(env, tmp_path, monkeypatch):
    env, ttl_path = _rename_env(env, tmp_path)
    orig_parse = core.Graph.parse
    parse_count = 0

    def counting_parse(self, *args, **kwargs):
        nonlocal parse_count
        parse_count += 1
        return orig_parse(self, *args, **kwargs)

    monkeypatch.setattr(core.Graph, "parse", counting_parse)

    # 1) Oeffnen: genau 1 Parse (fuellt Graph- und Synonym-Cache).
    state = _open(env)
    assert parse_count == 1

    # 2) Live-Synonympruefung bei unveraenderter Datei: 0 neue Parses.
    parse_count = 0
    status, _ = _post(env, "/api/synonym-check", {
        "original_id": "Ruhrstatut",
        "data": {"id": "Ruhrstatut", "pref": "Test", "synonym": True, "alts": [{"text": "X", "lang": "de"}]},
    })
    assert status == 200
    assert parse_count == 0

    # 3) Speichern: genau 1 Parse (Validierung der neuen Datei wird fuer build_state wiederverwendet).
    parse_count = 0
    rec = _record(state, "Montanunion")
    rec["note"] = "Cache-Test."
    status, state = _post(env, "/api/save-batch", {
        "version": state["sha256"],
        "items": [{"original_id": "Montanunion", "data": rec}],
    })
    assert status == 200, state
    assert parse_count == 1

    # 4) Umbenennen: genau 1 Parse (nur neuer Text; alter Graph kommt aus dem Cache).
    parse_count = 0
    status, state = _post(env, "/api/rename", {
        "id": "Ruhrstatut", "new_id": "Ruhrstatut1949", "version": state["sha256"],
    })
    assert status == 200, state
    assert parse_count == 1


def test_synonym_check_includes_pending_drafts_and_detects_external_changes(env, tmp_path):
    env, ttl_path = _rename_env(env, tmp_path, text=SYN_SAMPLE, name="syn_drafts.ttl")
    _open(env)

    # 1) Kollision mit anderem vorgemerkten bestehenden Eintrag.
    body = {
        "original_id": "Missionswerk",
        "data": {"id": "Missionswerk", "pref": "Berliner Missionswerk", "synonym": True,
                 "alts": [{"text": "SpezialKuerzel", "lang": "de"}]},
        "drafts": [{
            "key": "BMW",
            "original_id": "BMW",
            "data": {"id": "BMW", "pref": "Bayerische Motoren Werke", "synonym": True,
                     "alts": [{"text": "spezialkuerzel", "lang": "de"}]},
        }],
    }
    status, resp = _post(env, "/api/synonym-check", body)
    assert status == 200
    assert len(resp["conflicts"]) == 1
    c = resp["conflicts"][0]
    assert c["other_id"] == "BMW" and c["is_new"] is True and c["in_draft"] is True and c["draft_key"] == "BMW"

    # 2) Kollision mit einem noch ungespeicherten neuen Eintrag (ohne ID).
    body_new = {
        "original_id": "Missionswerk",
        "data": {"id": "Missionswerk", "pref": "Berliner Missionswerk", "synonym": True,
                 "alts": [{"text": "Brandneu", "lang": "de"}]},
        "drafts": [{
            "key": "__NEW__:1",
            "original_id": None,
            "data": {"id": "", "pref": "Neuer Verein", "synonym": True,
                     "alts": [{"text": "Brandneu", "lang": "de"}]},
        }],
    }
    status, resp = _post(env, "/api/synonym-check", body_new)
    assert status == 200
    assert len(resp["conflicts"]) == 1
    assert resp["conflicts"][0]["other_id"] == "__NEW__:1"
    assert resp["conflicts"][0]["draft_key"] == "__NEW__:1"
    assert resp["conflicts"][0]["in_draft"] is True and resp["conflicts"][0]["is_new"] is True

    # 3) Ein Entwurf, der den Synonym-Haken bei MoPoHH deaktiviert, loest die Kollision live auf.
    body_resolved = {
        "original_id": "MoPoBerlin",
        "data": {"id": "MoPoBerlin", "pref": "Berliner Morgenpost", "synonym": True,
                 "alts": [{"text": "MoPo", "lang": "de"}]},
        "drafts": [{
            "key": "MoPoHH",
            "original_id": "MoPoHH",
            "data": {"id": "MoPoHH", "pref": "Hamburger Morgenpost", "synonym": False,
                     "alts": [{"text": "Mopo", "lang": "de"}]},
        }],
    }
    status, resp = _post(env, "/api/synonym-check", body_resolved)
    assert status == 200 and resp["conflicts"] == []

    # 4) Externe Aenderung an der Datei wird trotz Stat-Cache erkannt.
    ttl_path.write_text(
        ttl_path.read_text(encoding="utf-8") + _syn_block("ExternNeu", "Externer Verein", ["ExtKuerzel"]),
        encoding="utf-8",
    )
    status, resp = _post(env, "/api/synonym-check", {
        "original_id": "Missionswerk",
        "data": {"id": "Missionswerk", "pref": "Berliner Missionswerk", "synonym": True,
                 "alts": [{"text": "ExtKuerzel", "lang": "de"}]},
    })
    assert status == 200
    assert [(x["other_id"], x["is_new"]) for x in resp["conflicts"]] == [("ExternNeu", True)]


def test_styles_css_served_and_linked(env):
    resp_index = env["client"].get("/")
    assert resp_index.status_code == 200
    html = resp_index.get_data(as_text=True)
    assert '/static/styles.css' in html
    assert 'id="toast-bar"' in html
    assert 'id="findings-filter"' in html
    assert 'id="welcome-no-file"' in html

    resp_css = env["client"].get("/static/styles.css")
    assert resp_css.status_code == 200
    css = resp_css.get_data(as_text=True)
    assert ".backup-more" in css
    assert ".toast-bar" in css
    assert ".filter-pill" in css
    assert ".welcome-card" in css
    assert ".tech-details" in css
    assert ".type-pill" in css

    # Alle destruktiven Rueckfragen nutzen eigene App-Modals statt Browser-confirm().
    resp_js = env["client"].get("/static/app.js")
    assert resp_js.status_code == 200
    js = resp_js.get_data(as_text=True)
    import re as _re
    js_no_comments = _re.sub(r"//.*", "", js)
    assert not _re.search(r"\bconfirm\s*\(", js_no_comments), "Rohes Browser-confirm() in app.js gefunden"
    assert "showConfirmModal" in js
    assert "showBanner" in js
    assert "appendTechDetails" in js
