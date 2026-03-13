from __future__ import annotations

from pathlib import Path
import os
import subprocess

from flask import Flask, render_template, request, redirect, url_for, flash

from fpv_store import load_store, save_store, validate_entry, Entry


BASE_DIR = Path(__file__).resolve().parent
DATA_FILE = BASE_DIR / "data" / "fpv.ttl"
BACKUP_DIR = BASE_DIR / "backups"
VALIDATION_SCRIPT = os.environ.get(
    "FPV_VALIDATION_SCRIPT",
    "python .\\scripts\\validate_fpv.py"
)

app = Flask(__name__)
app.secret_key = "fpv-editor-local-dev"


def get_store():
    return load_store(DATA_FILE)


def run_external_validation() -> tuple[bool, str]:
    if not VALIDATION_SCRIPT:
        return True, "Kein externes Validierungsskript konfiguriert."

    try:
        result = subprocess.run(
            VALIDATION_SCRIPT,
            capture_output=True,
            text=True,
            shell=True,
            cwd=str(BASE_DIR),
        )
        output = (result.stdout or "") + (("\n" + result.stderr) if result.stderr else "")
        return result.returncode == 0, output.strip() or "Validierung ohne Ausgabe beendet."
    except Exception as exc:
        return False, f"Fehler beim Ausführen des Validierungsskripts: {exc}"


@app.route("/")
def index():
    store = get_store()
    q = request.args.get("q", "").strip().lower()
    starts_with = request.args.get("starts_with", "").strip().upper()

    entries = store.entries

    if q:
        def matches(entry: Entry) -> bool:
            haystack = " ".join(
                [
                    entry.id,
                    entry.pref_label,
                    entry.note,
                    " ".join(value for value, _lang in entry.alt_labels),
                    " ".join(entry.raw_extra_lines),
                ]
            ).lower()
            return q in haystack

        entries = [entry for entry in entries if matches(entry)]

    if starts_with:
        entries = [
            entry for entry in entries
            if entry.pref_label and entry.pref_label[:1].upper() == starts_with
        ]

    letters = sorted(
        {
            (entry.pref_label[:1].upper() if entry.pref_label else "#")
            for entry in store.entries
        }
    )

    return render_template(
        "index.html",
        entries=entries,
        q=q,
        starts_with=starts_with,
        letters=letters,
    )


@app.route("/entry/new", methods=["GET", "POST"])
def entry_new():
    if request.method == "POST":
        store = get_store()
        entry = entry_from_form(request.form)
        errors = validate_entry(entry, existing_ids={e.id for e in store.entries})
        if errors:
            for err in errors:
                flash(err, "error")
            return render_template("entry_form.html", entry=entry, is_new=True)

        store.entries.append(entry)
        save_store(store, DATA_FILE, BACKUP_DIR)
        flash("Eintrag angelegt.", "success")
        return redirect(url_for("index"))

    empty = Entry(
        id="",
        pref_label="",
        pref_label_lang="de",
        alt_labels=[],
        notation="topic",
        use_in_synonym_list=False,
        exact_match="",
        close_match="",
        note="",
        note_lang="de",
        raw_extra_lines=[],
    )
    return render_template("entry_form.html", entry=empty, is_new=True)


@app.route("/entry/<entry_id>", methods=["GET", "POST"])
def entry_edit(entry_id: str):
    store = get_store()
    entry = next((e for e in store.entries if e.id == entry_id), None)

    if not entry:
        flash("Eintrag nicht gefunden.", "error")
        return redirect(url_for("index"))

    if request.method == "POST":
        updated = entry_from_form(request.form)
        other_ids = {e.id for e in store.entries if e.id != entry_id}
        errors = validate_entry(updated, existing_ids=other_ids)

        if errors:
            for err in errors:
                flash(err, "error")
            return render_template(
                "entry_form.html",
                entry=updated,
                is_new=False,
                original_id=entry_id,
            )

        idx = next(i for i, e in enumerate(store.entries) if e.id == entry_id)
        store.entries[idx] = updated
        save_store(store, DATA_FILE, BACKUP_DIR)
        flash("Eintrag gespeichert.", "success")
        return redirect(url_for("entry_edit", entry_id=updated.id))

    return render_template(
        "entry_form.html",
        entry=entry,
        is_new=False,
        original_id=entry_id,
    )


@app.route("/entry/<entry_id>/delete", methods=["POST"])
def entry_delete(entry_id: str):
    store = get_store()
    before = len(store.entries)
    store.entries = [e for e in store.entries if e.id != entry_id]

    if len(store.entries) == before:
        flash("Eintrag nicht gefunden.", "error")
    else:
        save_store(store, DATA_FILE, BACKUP_DIR)
        flash("Eintrag gelöscht.", "success")

    return redirect(url_for("index"))


@app.route("/validate", methods=["POST"])
def validate_all():
    ok, output = run_external_validation()
    flash(output, "success" if ok else "error")
    return redirect(url_for("index"))


def entry_from_form(form) -> Entry:
    alt_values = form.getlist("alt_label[]")
    alt_langs = form.getlist("alt_lang[]")
    alt_labels: list[tuple[str, str]] = []

    for value, lang in zip(alt_values, alt_langs):
        value = value.strip()
        lang = (lang or "de").strip()
        if value:
            alt_labels.append((value, lang))

    raw_extra = form.get("raw_extra_lines", "")
    raw_extra_lines = [line.rstrip() for line in raw_extra.splitlines() if line.strip()]

    return Entry(
        id=form.get("id", "").strip(),
        pref_label=form.get("pref_label", "").strip(),
        pref_label_lang=form.get("pref_label_lang", "de").strip() or "de",
        alt_labels=alt_labels,
        notation=form.get("notation", "").strip(),
        use_in_synonym_list=form.get("use_in_synonym_list") == "true",
        exact_match=form.get("exact_match", "").strip(),
        close_match=form.get("close_match", "").strip(),
        note=form.get("note", "").strip(),
        note_lang=form.get("note_lang", "de").strip() or "de",
        raw_extra_lines=raw_extra_lines,
    )


if __name__ == "__main__":
    app.run(debug=True)