# -*- coding: utf-8 -*-
"""
app.py — Flask-Server des FPV-Editors.

Bindet ausschließlich an 127.0.0.1 auf einem freien, zufällig gewählten
Port. Keine externen Laufzeitdienste. Ein Sitzungstoken (pro Prozessstart,
in die HTML-Seite injiziert) schützt alle verändernden POST-Endpunkte.

Dieser Server ist als Werkzeug für EINE bearbeitende Person gedacht,
keine Mehrbenutzerplattform (siehe Übergabe §6).
"""

from __future__ import annotations

import os
import secrets
import socket
import threading
from pathlib import Path

from flask import Flask, jsonify, request, Response, render_template_string, abort

import fpv_core as core

APP_ROOT = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(APP_ROOT, "static")

# Dateien der Oberfläche, ohne die der Editor nicht funktioniert. Fehlt eine,
# ist die Installation unvollständig (z. B. Ordner nur teilweise kopiert oder
# synchronisiert) -- das wird beim Start geprüft und verständlich gemeldet.
REQUIRED_STATIC_FILES = ("index.html", "app.js")


def check_static_files(static_dir: str | None = None) -> list[str]:
    """Gibt die Namen der fehlenden (oder leeren) Pflichtdateien der
    Oberfläche zurück; leere Liste = alles vorhanden."""
    base = static_dir or STATIC_DIR
    missing = []
    for name in REQUIRED_STATIC_FILES:
        path = os.path.join(base, name)
        try:
            if not os.path.isfile(path) or os.path.getsize(path) == 0:
                missing.append(name)
        except OSError:
            missing.append(name)
    return missing


def describe_static_problem(static_dir: str | None = None) -> str:
    """Verständliche Beschreibung für Meldung und Log, falls Oberflächen-
    dateien fehlen; leerer String, wenn alles in Ordnung ist."""
    base = static_dir or STATIC_DIR
    missing = check_static_files(base)
    if not missing:
        return ""
    try:
        if os.path.isdir(base):
            content = ", ".join(sorted(os.listdir(base))) or "(Ordner ist leer)"
        else:
            content = "(Ordner existiert nicht)"
    except OSError as exc:
        content = f"(nicht lesbar: {exc})"
    return (
        "Das Programm ist unvollständig installiert: Es fehlen Dateien der Oberfläche.\n\n"
        f"Fehlend: {', '.join(missing)}\n"
        f"Erwartet in: {base}\n"
        f"Dort vorhanden: {content}\n\n"
        "Bitte den GESAMTEN Ordner des Programms (nicht nur FPV-Editor.exe, "
        "sondern auch den Unterordner _internal mit allen Dateien) vollständig "
        "und erneut kopieren. Liegt der Ordner in einem Cloud-Ordner "
        "(z. B. Nextcloud), zuerst abwarten, bis die Synchronisation "
        "vollständig abgeschlossen ist und alle Dateien lokal vorliegen."
    )

MAX_CONTENT_LENGTH = 2 * 1024 * 1024  # 2 MiB Flask-Anfragegröße (Übergabe §6)

# ---------------------------------------------------------------------------
# Prozessweiter Zustand (bewusst einfach: EIN Nutzer, EIN Server-Prozess)
# ---------------------------------------------------------------------------


class AppState:
    def __init__(self):
        self.lock = threading.RLock()
        self.token = secrets.token_hex(16)
        self.loaded: core.LoadedFile | None = None
        self.manual_backup_dir: str | None = None  # nur für die laufende Sitzung
        # launcher.py pollt dieses Flag auf dem Tk-Hauptthread (root.after)
        # und fährt Server + Fenster erst DORT herunter. So werden keine
        # Tk-Aufrufe aus einem Flask-Worker-Thread heraus nötig.
        self.shutdown_requested = False
        # Wird von launcher.py gesetzt, damit /api/choose den nativen Dateidialog
        # auf dem Tk-Hauptthread ausführen kann (siehe launcher.py).
        self.dialog_bridge = None
        # Zustand des nativen Dateiauswahldialogs. Es darf immer nur EIN
        # Dialog offen sein; weitere Klicks auf "Datei öffnen …" holen den
        # vorhandenen nach vorne, statt einen zweiten zu öffnen.
        #   status: "idle" | "open" | "done"; result: Pfad ("" = abgebrochen)
        self.choose = {"status": "idle", "result": None, "error": None}
        # (sha256 des Dateistands, Synonym-Index): der Graph der Datei muss fuer
        # die Live-Pruefung der Synonymliste nicht bei jedem Tastendruck neu
        # geparst werden (ca. 0,3 s bei 860 Konzepten).
        self.synonym_cache = None
        # Vorgemerkte, noch nicht gespeicherte Eintraege, wie sie die
        # Oberflaeche zuletzt gemeldet hat: {"items": [...], "version": sha}
        # oder None. Dient dem Startfenster (Warnung/Speichern beim Beenden).
        self.pending = None


STATE = AppState()


def _normalize_alts_input(raw, default_lang: str) -> list:
    """Bringt die altLabel-Angaben aus dem Formular in die Form
    [{"text": ..., "lang": ...}] und verwirft leere Einträge. Akzeptiert
    sowohl Objekte als auch reine Strings, damit ein älterer Frontend-Stand
    nicht stillschweigend Sprachkennzeichen verliert."""
    out = []
    for item in (raw or []):
        if isinstance(item, dict):
            text = str(item.get("text", "")).strip()
            lang = str(item.get("lang") or "").strip() or default_lang
        else:
            text = str(item).strip()
            lang = default_lang
        if text:
            out.append({"text": text, "lang": lang})
    return out


def _synonym_index(fresh):
    """Synonym-Index des Dateistands `fresh` (mit Cache pro sha256)."""
    cache = STATE.synonym_cache
    if cache and cache[0] == fresh.sha256:
        return cache[1]
    index = core.build_synonym_index(fresh.text)
    STATE.synonym_cache = (fresh.sha256, index)
    return index


def _alt_texts(alts) -> list:
    return [a["text"] if isinstance(a, dict) else str(a) for a in (alts or [])]


def _record_from_data(data: dict) -> "core.Record":
    """Formulardaten (JSON) -> Record; gemeinsame Grundlage von /api/save und
    /api/save-batch."""
    lang = str(data.get("lang", "de")).strip() or "de"
    return core.Record(
        id=str(data.get("id", "")).strip(),
        pref=str(data.get("pref", "")).strip(),
        lang=lang,
        type=str(data.get("type", "")).strip(),
        note=str(data.get("note", "")).strip(),
        synonym=bool(data.get("synonym", False)),
        # altLabels kommen als {text, lang}-Objekte; ein reiner String wird
        # zur Sicherheit weiterhin akzeptiert (siehe _normalize_alts_input).
        alts=_normalize_alts_input(data.get("alts"), lang),
        exact=[str(a).strip() for a in (data.get("exact") or []) if str(a).strip()],
        close=[str(a).strip() for a in (data.get("close") or []) if str(a).strip()],
        related=[str(a).strip() for a in (data.get("related") or []) if str(a).strip()],
    )


def save_batch(items, version):
    """Speichert mehrere Eintraege (neu oder geaendert) in EINEM Vorgang:
    eine Versionspruefung, eine Gesamtpruefung, EINE Sicherung, EIN
    Schreibvorgang. Alles oder nichts: scheitert ein Eintrag, wird nichts
    geschrieben und der Fehler nennt den Eintrag (`failed_id`).
    Rueckgabe: (antwort_dict, http_status). Wird vom Endpunkt /api/save-batch
    UND vom Startfenster ("Speichern und beenden") benutzt."""
    if not isinstance(items, list) or not items:
        return {"error": "Es wurden keine Eintr\u00e4ge zum Speichern \u00fcbergeben.", "error_type": "FpvError"}, 400

    with STATE.lock:
        if STATE.loaded is None:
            return {"error": "Keine Datei geladen.", "error_type": "FpvError"}, 400
        ttl_path = STATE.loaded.path
        fresh = core.read_ttl_file(ttl_path)
        if version != fresh.sha256:
            return {
                "error": (
                    "Die Datei wurde seit dem Laden extern ver\u00e4ndert. "
                    "Nichts wurde geschrieben. Bitte neu laden (\u201eDatei pr\u00fcfen\u201c) und erneut speichern."
                ),
                "error_type": "VersionConflict",
            }, 409

        def fail(message, rec_id, findings=None, status=400):
            body = {"error": f"Eintrag \u201e{rec_id}\u201c: {message} Nichts wurde geschrieben.", "failed_id": rec_id}
            if findings:
                body["findings"] = findings
            return body, status

        text = fresh.text
        records = []  # (rec, is_new) in Reihenfolge
        for item in items:
            original_id = (item or {}).get("original_id")
            data = (item or {}).get("data") or {}
            is_new = not original_id
            rec = _record_from_data(data)
            label = rec.id or "(ohne Kennung)"

            if not is_new and rec.id != original_id:
                return fail("Eine bestehende ID darf nicht ge\u00e4ndert werden.", original_id)
            if any(r.id == rec.id for r, _n in records):
                return fail("Dieser Eintrag kommt in der Sammlung mehrfach vor.", label)

            existing_ids = {m.group(1) for m in core._BLOCK_START_RE.finditer(text)}
            field_findings = core.validate_record_fields(rec, is_new=is_new, existing_ids=existing_ids)
            if any(f.level == "error" for f in field_findings):
                return fail("Validierung fehlgeschlagen.", label, [f.to_json() for f in field_findings])

            block_text = core.render_record_to_block(rec)
            if is_new:
                sep = "" if text.endswith("\n\n") else ("\n" if text.endswith("\n") else "\n\n")
                text = text + sep + block_text
            else:
                block = core.find_block(text, original_id)
                if block is None:
                    return fail("Der Eintrag wurde in der Datei nicht gefunden.", original_id)
                if block.protected:
                    return fail(
                        block.protect_reason or "Block ist gesch\u00fctzt und wird nicht \u00fcber das Formular bearbeitet.",
                        original_id,
                    )
                text = text[:block.start] + block_text.rstrip("\n") + text[block.end:]
            records.append((rec, is_new))

        edited_ids = {r.id for r, _n in records}
        whole_findings = core.validate_whole_file(text)
        blocking_errors = [
            f for f in whole_findings
            if f.level == "error" and (f.concept_id is None or f.concept_id in edited_ids)
        ]
        if blocking_errors:
            first = next((f.concept_id for f in blocking_errors if f.concept_id), None)
            return {
                "error": "Die resultierende Gesamtdatei w\u00e4re ung\u00fcltig; nichts wurde geschrieben.",
                "failed_id": first,
                "findings": [f.to_json() for f in blocking_errors],
            }, 400

        try:
            syn_conflicts = core.synonym_conflicts_for_batch(
                _synonym_index(fresh),
                [(r.id, r.pref, _alt_texts(r.alts), r.synonym) for r, _n in records],
            )
        except Exception:
            syn_conflicts = []  # nicht parsbarer Altstand: faengt die Gesamtpruefung ab
        new_conflicts = [c for c in syn_conflicts if c["is_new"]]
        if new_conflicts:
            return {
                "error": (
                    "Nichts wurde geschrieben: Eine Benennung steht schon bei einem anderen Konzept der "
                    "Synonymliste, die Suche w\u00fcrde beide finden. Bitte die Benennung bei einem der "
                    "Konzepte entfernen oder bei einem den Haken \u201eIn Synonymliste verwenden\u201c wegnehmen."
                ),
                "failed_id": new_conflicts[0]["concept_id"],
                "findings": [
                    core.Finding("error", core.synonym_conflict_message(c), c["concept_id"]).to_json()
                    for c in new_conflicts
                ],
            }, 400

        try:
            wr = core.write_ttl_atomically(
                ttl_path, text, fresh.uses_crlf, fresh.raw_bytes, STATE.manual_backup_dir
            )
        except core.BackupError as exc:
            return {"error": str(exc), "error_type": type(exc).__name__}, 507
        except core.FpvError as exc:
            return {"error": str(exc), "error_type": type(exc).__name__}, 500

        STATE.loaded = core.read_ttl_file(ttl_path)
        # Gespeichert: nichts ist mehr vorgemerkt, die Zwischensicherung entfaellt.
        STATE.pending = None
        core.clear_recovery(ttl_path)
        result = core.build_state(STATE.loaded)
        result["write_method"] = wr.method
        result["backup_label"] = wr.backup_label
        result["backup_path"] = wr.backup_path
        result["saved_ids"] = [r.id for r, _n in records]
        return result, 200


def create_app() -> Flask:
    app = Flask(__name__, static_folder=STATIC_DIR, static_url_path="/static")
    app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH

    # -----------------------------------------------------------------
    # Token-Prüfung für verändernde Endpunkte
    # -----------------------------------------------------------------
    def require_token():
        token = request.headers.get("X-FPV-Token", "")
        if not secrets.compare_digest(token, STATE.token):
            abort(403, description="Ungültiges oder fehlendes X-FPV-Token.")

    def error_response(exc: Exception, status: int = 400):
        return jsonify({"error": str(exc), "error_type": type(exc).__name__}), status

    # -----------------------------------------------------------------
    # GET /
    # -----------------------------------------------------------------
    @app.get("/")
    def index():
        index_path = os.path.join(STATIC_DIR, "index.html")
        try:
            with open(index_path, "r", encoding="utf-8") as f:
                html = f.read()
        except OSError:
            problem = describe_static_problem() or f"Die Datei {index_path} kann nicht gelesen werden."
            app.logger.error("index.html nicht lesbar: %s", problem.replace("\n", " "))
            body = (
                "<!doctype html><meta charset='utf-8'><title>FPV-Editor – Startfehler</title>"
                "<body style='font-family:Segoe UI,Arial,sans-serif;max-width:46rem;margin:3rem auto;'>"
                "<h1>FPV-Editor kann nicht starten</h1><pre style='white-space:pre-wrap;font:inherit'>"
                + problem.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                + "</pre></body>"
            )
            return Response(body, status=500, mimetype="text/html")
        html = html.replace("__FPV_TOKEN__", STATE.token)
        return Response(html, mimetype="text/html")

    # -----------------------------------------------------------------
    # GET /api/state
    # -----------------------------------------------------------------
    @app.get("/api/state")
    def api_state():
        with STATE.lock:
            if STATE.loaded is None:
                return jsonify({"path": None, "records": [], "findings": [], "sha256": None})
            return jsonify(core.build_state(STATE.loaded))

    # -----------------------------------------------------------------
    # GET /api/backups
    # -----------------------------------------------------------------
    @app.get("/api/backups")
    def api_backups():
        with STATE.lock:
            if STATE.loaded is None:
                return jsonify({"backups": []})
            backups = core.list_backups(STATE.loaded.path, STATE.manual_backup_dir)
            return jsonify({"backups": backups})

    # -----------------------------------------------------------------
    # Gemeinsame Ladefunktion für /api/open und /api/choose
    # -----------------------------------------------------------------
    def _load_path(path: str):
        loaded = core.read_ttl_file(path)
        with STATE.lock:
            STATE.loaded = loaded
            STATE.pending = None
        return core.build_state(loaded)

    # -----------------------------------------------------------------
    # POST /api/open  { path }
    # -----------------------------------------------------------------
    @app.post("/api/open")
    def api_open():
        require_token()
        payload = request.get_json(silent=True) or {}
        path = payload.get("path", "")
        if not path:
            return error_response(core.FpvError("Kein Pfad angegeben."))
        try:
            state = _load_path(path)
        except core.FpvError as exc:
            return error_response(exc)
        return jsonify(state)

    # -----------------------------------------------------------------
    # POST /api/choose  -> nativen Dateiauswahldialog STARTEN (nicht
    # blockierend). Das Ergebnis holt die Oberflaeche per /api/choose-result.
    #
    # Frueher blockierte dieser Aufruf, bis der Dialog geschlossen war (mit
    # 120-s-Zeitgrenze, danach unbehandelter TimeoutError/HTTP 500), und
    # jeder weitere Klick oeffnete einen weiteren Dialog.
    # -----------------------------------------------------------------
    @app.post("/api/choose")
    def api_choose():
        require_token()
        bridge = STATE.dialog_bridge
        if bridge is None:
            return error_response(
                core.FpvError(
                    "Der native Dateiauswahldialog ist nur im per launcher.py "
                    "gestarteten Programm verfügbar (nicht bei einem reinen "
                    "'flask run' ohne Tk-Startfenster)."
                ),
                status=501,
            )
        with STATE.lock:
            already_open = STATE.choose["status"] == "open"
            if not already_open:
                STATE.choose = {"status": "open", "result": None, "error": None}
        if already_open:
            # Kein zweiter Dialog: den vorhandenen nach vorne holen.
            try:
                bridge.bring_dialog_to_front()
            except Exception:
                pass
            return jsonify({"status": "already_open"})

        def on_done(path, error):
            with STATE.lock:
                STATE.choose = {"status": "done", "result": path or "", "error": error}

        try:
            bridge.start_open_dialog(on_done)
        except Exception as exc:
            with STATE.lock:
                STATE.choose = {"status": "idle", "result": None, "error": None}
            return error_response(core.FpvError(f"Dateiauswahl konnte nicht geöffnet werden: {exc}"), status=500)
        return jsonify({"status": "opened"})

    # -----------------------------------------------------------------
    # POST /api/choose-result -> Stand des Dateiauswahldialogs; ist eine
    # Datei gewaehlt, wird sie hier geladen.
    #   {"status": "idle"|"open"|"cancelled"} oder Zustandsobjekt mit
    #   "status": "loaded" oder Fehlerantwort
    # -----------------------------------------------------------------
    @app.post("/api/choose-result")
    def api_choose_result():
        require_token()
        with STATE.lock:
            choose = dict(STATE.choose)
            if choose["status"] == "done":
                STATE.choose = {"status": "idle", "result": None, "error": None}
        if choose["status"] != "done":
            return jsonify({"status": choose["status"]})
        if choose["error"]:
            return error_response(core.FpvError(f"Dateiauswahl fehlgeschlagen: {choose['error']}"), status=500)
        if not choose["result"]:
            return jsonify({"status": "cancelled"})
        try:
            state = _load_path(choose["result"])
        except core.FpvError as exc:
            return error_response(exc)
        state["status"] = "loaded"
        return jsonify(state)

    # -----------------------------------------------------------------
    # GET /api/ping -> Lebenszeichen fuer die Oberflaeche. Bleibt die
    # Antwort aus, wurde das Programm beendet; die Seite zeigt das dann an,
    # statt weiter aktiv auszusehen.
    # -----------------------------------------------------------------
    @app.get("/api/ping")
    def api_ping():
        return jsonify({"ok": True})

    # -----------------------------------------------------------------
    # POST /api/close  -> aktuelle Datei schließen, ohne den Server zu beenden
    # -----------------------------------------------------------------
    @app.post("/api/close")
    def api_close():
        require_token()
        with STATE.lock:
            previous = STATE.loaded.path if STATE.loaded else None
            STATE.loaded = None
            STATE.pending = None
            # Der manuell gewählte Sicherungsort gilt laut Übergabe §5 nur für
            # die laufende Sitzung und bezieht sich auf EINE bestimmte Datei;
            # beim Schließen wird er deshalb mit zurückgesetzt, damit er nicht
            # unbemerkt für eine ganz andere TTL weiterverwendet wird.
            STATE.manual_backup_dir = None
            return jsonify({
                "closed": previous,
                "path": None,
                "records": [],
                "findings": [],
                "sha256": None,
            })

    # -----------------------------------------------------------------
    # POST /api/validate  -> validiert die aktuell geladene Gesamtdatei neu
    # -----------------------------------------------------------------
    @app.post("/api/validate")
    def api_validate():
        require_token()
        with STATE.lock:
            if STATE.loaded is None:
                return error_response(core.FpvError("Keine Datei geladen."))
            # Frisch von der Platte lesen, damit "Datei prüfen" auch externe
            # Änderungen seit dem Laden erkennt.
            fresh = core.read_ttl_file(STATE.loaded.path)
            STATE.loaded = fresh
            return jsonify(core.build_state(fresh))

    # -----------------------------------------------------------------
    # POST /api/save  { original_id, data, version }
    # -----------------------------------------------------------------
    @app.post("/api/save")
    def api_save():
        require_token()
        payload = request.get_json(silent=True) or {}
        original_id = payload.get("original_id")  # None/"" => Neuanlage
        data = payload.get("data") or {}
        version = payload.get("version")

        with STATE.lock:
            if STATE.loaded is None:
                return error_response(core.FpvError("Keine Datei geladen."))
            ttl_path = STATE.loaded.path

            # Version gegen den TATSÄCHLICHEN Stand auf der Platte prüfen,
            # nicht nur gegen den zuletzt im Speicher gehaltenen Stand.
            fresh = core.read_ttl_file(ttl_path)
            if version != fresh.sha256:
                return error_response(
                    core.VersionConflict(
                        "Die Datei wurde seit dem Laden extern verändert. "
                        "Bitte neu laden und Änderungen erneut vornehmen."
                    ),
                    status=409,
                )

            is_new = not original_id
            rec = _record_from_data(data)

            existing_ids = {m.group(1) for m in core._BLOCK_START_RE.finditer(fresh.text)}
            if not is_new and rec.id != original_id:
                return error_response(core.FpvError("Eine bestehende ID darf nicht geändert werden."))

            field_findings = core.validate_record_fields(rec, is_new=is_new, existing_ids=existing_ids)
            field_errors = [f for f in field_findings if f.level == "error"]
            if field_errors:
                return jsonify({
                    "error": "Validierung fehlgeschlagen.",
                    "findings": [f.to_json() for f in field_findings],
                }), 400

            new_block_text = core.render_record_to_block(rec)

            if is_new:
                sep = "" if fresh.text.endswith("\n\n") else ("\n" if fresh.text.endswith("\n") else "\n\n")
                new_full_text = fresh.text + sep + new_block_text
            else:
                block = core.find_block(fresh.text, original_id)
                if block is None:
                    return error_response(core.FpvError(f"Block '{original_id}' nicht gefunden."))
                if block.protected:
                    return error_response(core.ProtectedBlockError(
                        block.protect_reason or "Block ist geschützt und wird nicht über das Formular bearbeitet."
                    ))
                # block.end liegt direkt NACH dem abschliessenden "."; der Abstand zum
                # naechsten Block steht noch im Rest der Datei. Der gerenderte Block
                # endet mit "\n" und muss deshalb ohne dieses Ende eingesetzt werden,
                # sonst kommt bei jedem Speichern eine Leerzeile dazu.
                new_full_text = fresh.text[:block.start] + new_block_text.rstrip("\n") + fresh.text[block.end:]

            whole_findings = core.validate_whole_file(new_full_text)
            # Nur Fehler blockieren das Schreiben, die entweder die Datei als
            # Ganzes betreffen (Turtle-Syntax nicht parsbar; kein konkreter
            # concept_id zuordenbar) oder GENAU den gerade bearbeiteten
            # Datensatz. Vorbestehende Fehler in ANDEREN Datensätzen blockieren
            # nicht mehr — sonst entsteht ein Deadlock: Der Editor erlaubt nur
            # das Bearbeiten eines Datensatzes zur Zeit, könnte also nie
            # gespeichert werden, solange irgendwo sonst in der Datei ein
            # (unabhängiger) Altfehler existiert. Diese Änderung geht auf
            # ausdrückliches Nutzerfeedback zurück: "besser mit Fehler
            # speichern als stundenlange Arbeit verlieren". Die reine
            # Turtle-Syntaxgültigkeit bleibt dabei weiterhin eine harte
            # Voraussetzung zum Schreiben — nur strukturelle/Feld-Befunde zu
            # FREMDEN Datensätzen werden nicht mehr als Blocker behandelt.
            blocking_errors = [
                f for f in whole_findings
                if f.level == "error" and (f.concept_id is None or f.concept_id == rec.id)
            ]
            if blocking_errors:
                return jsonify({
                    "error": "Die resultierende Gesamtdatei wäre ungültig; nichts wurde geschrieben.",
                    "findings": [f.to_json() for f in blocking_errors],
                }), 400

            # Synonymliste: Eine Benennung darf nicht bei zwei Konzepten stehen, die
            # beide in die Typesense-Synonymliste gehen. Blockiert werden nur NEU
            # entstehende Kollisionen dieses Konzepts; bereits vorhandene
            # (Altlasten) erscheinen nur als Hinweis, sonst waere dieses Konzept
            # nicht mehr speicherbar (gleiche Begruendung wie oben).
            try:
                syn_conflicts = core.synonym_conflicts_for_record(
                    _synonym_index(fresh), "__NEU__" if is_new else rec.id,
                    rec.pref, _alt_texts(rec.alts), rec.synonym,
                )
            except Exception:
                syn_conflicts = []  # nicht parsbarer Altstand: faengt die Gesamtpruefung ab
            new_conflicts = [c for c in syn_conflicts if c["is_new"]]
            if new_conflicts:
                return jsonify({
                    "error": (
                        "Nichts wurde geschrieben: Eine Benennung steht schon bei einem anderen Konzept der "
                        "Synonymliste, die Suche w\u00fcrde beide finden. Bitte die Benennung bei einem der "
                        "Konzepte entfernen oder bei einem den Haken \u201eIn Synonymliste verwenden\u201c wegnehmen."
                    ),
                    "findings": [
                        core.Finding("error", core.synonym_conflict_message(c), rec.id).to_json()
                        for c in new_conflicts
                    ],
                }), 400

            try:
                wr = core.write_ttl_atomically(
                    ttl_path, new_full_text, fresh.uses_crlf, fresh.raw_bytes, STATE.manual_backup_dir
                )
            except core.BackupError as exc:
                return error_response(exc, status=507)
            except core.FpvError as exc:
                return error_response(exc, status=500)

            STATE.loaded = core.read_ttl_file(ttl_path)
            result = core.build_state(STATE.loaded)
            result["write_method"] = wr.method
            result["backup_label"] = wr.backup_label
            result["backup_path"] = wr.backup_path
            return jsonify(result)

    # -----------------------------------------------------------------
    # POST /api/save-batch  { version, items: [{original_id, data}, ...] }
    #   Siehe save_batch() (Modulebene): alles oder nichts, EINE Sicherung.
    # -----------------------------------------------------------------
    @app.post("/api/save-batch")
    def api_save_batch():
        require_token()
        payload = request.get_json(silent=True) or {}
        body, status = save_batch(payload.get("items") or [], payload.get("version"))
        return jsonify(body), status

    # -----------------------------------------------------------------
    # POST /api/pending  { items, version, persist }
    #   Die Oberflaeche meldet ihre vorgemerkten (noch nicht gespeicherten)
    #   Eintraege. Der Server haelt sie im Speicher, damit das Startfenster
    #   beim Beenden warnen und speichern kann, und schreibt sie bei
    #   persist=true zusaetzlich als Zwischensicherung auf die Platte.
    #   Die TTL-Datei wird dabei NIE veraendert.
    # -----------------------------------------------------------------
    @app.post("/api/pending")
    def api_pending():
        require_token()
        payload = request.get_json(silent=True) or {}
        items = payload.get("items") or []
        version = payload.get("version")
        if not isinstance(items, list):
            return error_response(core.FpvError("items muss eine Liste sein."))
        with STATE.lock:
            if STATE.loaded is None:
                STATE.pending = None
                return jsonify({"ok": True, "persisted": False})
            ttl_path = STATE.loaded.path
            had_pending = bool(STATE.pending and STATE.pending["items"])
            if not items:
                STATE.pending = None
                # Zwischensicherung nur loeschen, wenn zuvor wirklich etwas
                # vorgemerkt war (nicht schon beim Start, bevor ueber eine
                # vorhandene Zwischensicherung entschieden wurde).
                if had_pending:
                    core.clear_recovery(ttl_path)
                return jsonify({"ok": True, "persisted": False})
            STATE.pending = {"items": items, "version": version}
            result = {"ok": True, "persisted": False}
            if payload.get("persist"):
                try:
                    info = core.write_recovery(ttl_path, version, items)
                    result.update(persisted=True, saved_at=info["saved_at"])
                except OSError as exc:
                    result.update(persist_error=f"{type(exc).__name__}: {exc}")
            return jsonify(result)

    # -----------------------------------------------------------------
    # GET /api/recovery -> Zwischensicherung der geoeffneten Datei (falls vorhanden)
    # -----------------------------------------------------------------
    @app.get("/api/recovery")
    def api_recovery():
        with STATE.lock:
            if STATE.loaded is None:
                return jsonify({"exists": False})
            data = core.read_recovery(STATE.loaded.path)
            if not data or not data["items"]:
                return jsonify({"exists": False})
            return jsonify({
                "exists": True,
                "saved_at": data.get("saved_at"),
                "count": len(data["items"]),
                "items": data["items"],
                "sha_matches": data.get("version") == STATE.loaded.sha256,
            })

    # -----------------------------------------------------------------
    # POST /api/recovery-discard
    # -----------------------------------------------------------------
    @app.post("/api/recovery-discard")
    def api_recovery_discard():
        require_token()
        with STATE.lock:
            if STATE.loaded is not None:
                core.clear_recovery(STATE.loaded.path)
            STATE.pending = None
        return jsonify({"ok": True})

    # -----------------------------------------------------------------
    # POST /api/delete  { id, version }
    # -----------------------------------------------------------------
    @app.post("/api/delete")
    def api_delete():
        require_token()
        payload = request.get_json(silent=True) or {}
        concept_id = payload.get("id")
        version = payload.get("version")

        with STATE.lock:
            if STATE.loaded is None:
                return error_response(core.FpvError("Keine Datei geladen."))
            ttl_path = STATE.loaded.path
            fresh = core.read_ttl_file(ttl_path)
            if version != fresh.sha256:
                return error_response(
                    core.VersionConflict(
                        "Die Datei wurde seit dem Laden extern verändert. Bitte neu laden."
                    ),
                    status=409,
                )

            block = core.find_block(fresh.text, concept_id)
            if block is None:
                return error_response(core.FpvError(f"Block '{concept_id}' nicht gefunden."))

            refs = core.find_referencing_subjects(fresh.text, concept_id)
            if refs:
                return error_response(
                    core.ReferencedError(
                        f"Löschen abgelehnt: {len(refs)} andere Aussage(n) verweisen auf "
                        f"'{concept_id}': " + "; ".join(refs[:5]) + ("…" if len(refs) > 5 else "")
                    ),
                    status=409,
                )

            new_full_text = fresh.text[:block.start] + fresh.text[block.end:]
            # eine dadurch entstehende doppelte Leerzeile am Blockanfang glätten
            new_full_text = new_full_text[:block.start].rstrip("\n") + "\n\n" + new_full_text[block.start:].lstrip("\n")

            try:
                wr = core.write_ttl_atomically(
                    ttl_path, new_full_text, fresh.uses_crlf, fresh.raw_bytes, STATE.manual_backup_dir
                )
            except core.BackupError as exc:
                return error_response(exc, status=507)
            except core.FpvError as exc:
                return error_response(exc, status=500)

            STATE.loaded = core.read_ttl_file(ttl_path)
            result = core.build_state(STATE.loaded)
            result["write_method"] = wr.method
            result["backup_label"] = wr.backup_label
            result["backup_path"] = wr.backup_path
            return jsonify(result)

    # -----------------------------------------------------------------
    # POST /api/synonym-check  { original_id, data: {id, pref, alts, synonym} }
    #   Live-Pruefung im Formular: Kollisionen der Benennungen dieses Konzepts
    #   mit anderen Konzepten der Synonymliste. Schreibt nichts. `is_new`
    #   unterscheidet neue (blockierende) von bereits vorhandenen Kollisionen.
    # -----------------------------------------------------------------
    @app.post("/api/synonym-check")
    def api_synonym_check():
        require_token()
        payload = request.get_json(silent=True) or {}
        original_id = payload.get("original_id")
        data = payload.get("data") or {}
        with STATE.lock:
            if STATE.loaded is None:
                return error_response(core.FpvError("Keine Datei geladen."))
            fresh = core.read_ttl_file(STATE.loaded.path)
            try:
                index = _synonym_index(fresh)
            except Exception as exc:
                return error_response(core.FpvError(f"Datei nicht lesbar: {exc}"))
            default_lang = str(data.get("lang", "de")).strip() or "de"
            conflicts = core.synonym_conflicts_for_record(
                index,
                str(original_id) if original_id else "__NEU__",
                str(data.get("pref", "")).strip(),
                _alt_texts(_normalize_alts_input(data.get("alts"), default_lang)),
                bool(data.get("synonym", False)),
            )
            return jsonify({"conflicts": conflicts})

    # -----------------------------------------------------------------
    # POST /api/rename-check  { id, new_id? }
    #   Vorpruefung fuer "Kennung aendern": welche Konzepte verweisen auf die
    #   ID, was blockiert, ist die neue Kennung verwendbar? Schreibt nichts.
    # -----------------------------------------------------------------
    @app.post("/api/rename-check")
    def api_rename_check():
        require_token()
        payload = request.get_json(silent=True) or {}
        concept_id = str(payload.get("id") or "").strip()
        new_id = str(payload.get("new_id") or "").strip()
        with STATE.lock:
            if STATE.loaded is None:
                return error_response(core.FpvError("Keine Datei geladen."))
            fresh = core.read_ttl_file(STATE.loaded.path)
            try:
                _block, referrers, blocked = core.plan_rename(fresh.text, concept_id)
            except core.FpvError as exc:
                return error_response(exc)
            refs = []
            for b in referrers:
                try:
                    label = core.parse_block_to_record(b).pref
                except Exception:
                    label = ""
                refs.append({"id": b.id, "pref": label})
            return jsonify({
                "id": concept_id,
                "uri": core.EX + concept_id,
                "referrers": refs,
                "blocked": blocked,
                "new_id_problem": core.check_new_id(fresh.text, concept_id, new_id) if new_id else None,
            })

    # -----------------------------------------------------------------
    # POST /api/rename  { id, new_id, version }
    #   Benennt ein Konzept um und zieht Verweise in bearbeitbaren Bloecken
    #   mit. Gleiche Schutzreihenfolge wie beim Speichern: Version ->
    #   Validierung -> verifizierte Sicherung -> erst dann TTL aendern.
    # -----------------------------------------------------------------
    @app.post("/api/rename")
    def api_rename():
        require_token()
        payload = request.get_json(silent=True) or {}
        old_id = str(payload.get("id") or "").strip()
        new_id = str(payload.get("new_id") or "").strip()
        version = payload.get("version")

        with STATE.lock:
            if STATE.loaded is None:
                return error_response(core.FpvError("Keine Datei geladen."))
            ttl_path = STATE.loaded.path
            fresh = core.read_ttl_file(ttl_path)
            if version != fresh.sha256:
                return error_response(
                    core.VersionConflict(
                        "Die Datei wurde seit dem Laden extern verändert. Bitte neu laden und die Aktion erneut ausführen."
                    ),
                    status=409,
                )
            try:
                new_text, updated = core.rename_concept(fresh.text, old_id, new_id)
            except core.ReferencedError as exc:
                return error_response(exc, status=409)
            except core.FpvError as exc:
                return error_response(exc)

            whole_findings = core.validate_whole_file(new_text)
            blocking = [
                f for f in whole_findings
                if f.level == "error" and (f.concept_id is None or f.concept_id == new_id)
            ]
            if blocking:
                return jsonify({
                    "error": "Die resultierende Gesamtdatei wäre ungültig; nichts wurde geschrieben.",
                    "findings": [f.to_json() for f in blocking],
                }), 400

            try:
                wr = core.write_ttl_atomically(
                    ttl_path, new_text, fresh.uses_crlf, fresh.raw_bytes, STATE.manual_backup_dir
                )
            except core.BackupError as exc:
                return error_response(exc, status=507)
            except core.FpvError as exc:
                return error_response(exc, status=500)

            STATE.loaded = core.read_ttl_file(ttl_path)
            result = core.build_state(STATE.loaded)
            result["write_method"] = wr.method
            result["backup_label"] = wr.backup_label
            result["backup_path"] = wr.backup_path
            result["renamed"] = {"from": old_id, "to": new_id, "updated_references": updated}
            return jsonify(result)

    # -----------------------------------------------------------------
    # POST /api/backup-directory  { path }
    # -----------------------------------------------------------------
    @app.post("/api/backup-directory")
    def api_backup_directory():
        require_token()
        payload = request.get_json(silent=True) or {}
        path = (payload.get("path") or "").strip()
        if not path:
            with STATE.lock:
                STATE.manual_backup_dir = None
            return jsonify({"ok": True, "cleared": True})

        if not os.path.isdir(path):
            return error_response(core.FpvError(f"Ordner nicht gefunden: {path}"))
        probe = os.path.join(path, ".fpv_write_test.tmp")
        try:
            with open(probe, "wb") as f:
                f.write(b"test")
                f.flush()
                os.fsync(f.fileno())
            os.remove(probe)
        except OSError as exc:
            return error_response(core.FpvError(f"Ordner ist nicht beschreibbar: {exc}"))

        with STATE.lock:
            STATE.manual_backup_dir = path
        return jsonify({"ok": True, "path": path})

    # -----------------------------------------------------------------
    # POST /api/storage-check
    # -----------------------------------------------------------------
    @app.post("/api/storage-check")
    def api_storage_check():
        require_token()
        with STATE.lock:
            if STATE.loaded is None:
                return error_response(core.FpvError("Keine Datei geladen."))
            results = core.storage_check(STATE.loaded.path, STATE.manual_backup_dir)
        return jsonify({"results": results})

    # -----------------------------------------------------------------
    # POST /api/restore  { path } (voller Pfad einer Sicherungsdatei)
    # -----------------------------------------------------------------
    @app.post("/api/restore")
    def api_restore():
        require_token()
        payload = request.get_json(silent=True) or {}
        backup_path = payload.get("path")
        with STATE.lock:
            if STATE.loaded is None:
                return error_response(core.FpvError("Keine Datei geladen."))
            if not backup_path or not os.path.isfile(backup_path):
                return error_response(core.FpvError("Sicherungsdatei nicht gefunden."))
            ttl_path = STATE.loaded.path
            try:
                wr = core.restore_backup(ttl_path, backup_path, STATE.manual_backup_dir)
            except core.BackupError as exc:
                return error_response(exc, status=507)
            except core.FpvError as exc:
                return error_response(exc, status=500)

            STATE.loaded = core.read_ttl_file(ttl_path)
            result = core.build_state(STATE.loaded)
            result["write_method"] = wr.method
            result["backup_label"] = wr.backup_label
            result["backup_path"] = wr.backup_path
            return jsonify(result)

    # -----------------------------------------------------------------
    # POST /api/quit
    # -----------------------------------------------------------------
    @app.post("/api/quit")
    def api_quit():
        require_token()
        payload = request.get_json(silent=True) or {}
        with STATE.lock:
            pending = STATE.pending["items"] if STATE.pending else []
            # Sicherheitsnetz: Sind noch Eintraege vorgemerkt, beendet der
            # Server nur auf ausdrueckliche Anweisung (force). Die Oberflaeche
            # fragt vorher nach; das schuetzt auch vor veralteten Browserseiten.
            if pending and not payload.get("force"):
                return jsonify({
                    "error": f"{len(pending)} Eintrag/Eintr\u00e4ge sind noch nicht gespeichert.",
                    "error_type": "PendingChanges",
                    "pending_count": len(pending),
                }), 409
            if payload.get("discard") and STATE.loaded is not None:
                core.clear_recovery(STATE.loaded.path)
                STATE.pending = None
        # Nur das Flag setzen; das eigentliche Herunterfahren von Server und
        # Tk-Fenster übernimmt launcher.py auf dem Tk-Hauptthread.
        STATE.shutdown_requested = True
        return jsonify({"ok": True})

    @app.errorhandler(403)
    def handle_403(e):
        return jsonify({"error": "Ungültiges oder fehlendes X-FPV-Token."}), 403

    @app.errorhandler(413)
    def handle_413(e):
        return jsonify({"error": "Anfrage zu groß (Obergrenze 2 MiB)."}), 413

    return app


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def make_wsgi_server(port: int | None = None):
    """Erzeugt einen werkzeug-WSGI-Server mit sauberem `.shutdown()`, statt
    des blockierenden `app.run()`. Wird von launcher.py verwendet, damit das
    Tk-Startfenster den Server kontrolliert beenden kann. Gibt (server, port)
    zurück; `server.serve_forever()` muss in einem eigenen Thread laufen."""
    from werkzeug.serving import make_server

    app = create_app()
    if port is None:
        port = find_free_port()
    server = make_server("127.0.0.1", port, app, threaded=True)
    return server, port


def run_server(port: int | None = None):
    """Einfacher Standalone-Start ohne Tk-Startfenster (nur für Entwicklung/
    Diagnose per Kommandozeile, z. B. `python app.py`). Der reguläre Start
    läuft immer über launcher.py."""
    app = create_app()
    if port is None:
        port = find_free_port()
    app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False, threaded=True)


if __name__ == "__main__":
    # Direkter Start ohne Tk-Startfenster (Entwicklung/Diagnose). Für den
    # regulären Windows-Start siehe launcher.py bzw. start_mit_python.bat.
    p = find_free_port()
    print(f"FPV-Editor läuft auf http://127.0.0.1:{p}  (Token: {STATE.token})")
    run_server(p)
