# -*- coding: utf-8 -*-
"""
bundle_check.py — Vollständigkeits- und Standortprüfung des ausgelieferten
Programmordners (PyInstaller --onedir).

Zweck: Wird der Ordner ``FPV-Editor`` kopiert, entpackt oder synchronisiert,
kann er unvollständig ankommen (Datei fehlt, 0 Byte, nur als Cloud-Platzhalter
vorhanden, durch Virenscanner verändert). Der Build schreibt deshalb eine
Liste aller Dateien mit Größe und SHA-256 (``manifest.sha256.json``); der
Launcher vergleicht sie beim Start mit dem, was tatsächlich auf der Platte
liegt, und nennt konkret, was fehlt.

Dieses Modul ist reines Python ohne Flask/Tk und wird von drei Stellen
benutzt: ``make_release.py`` (Manifest schreiben, ZIP bauen), ``launcher.py``
(beim Start prüfen) und den Tests.

Grenzen (bewusst): Die Prüfung erkennt, DASS etwas nicht stimmt und WAS, aber
sie kann die Ursache (Sync-Client, Virenscanner, abgebrochenes Kopieren) nicht
belegen. Standortwarnungen sind Hinweise, keine Beweise.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from typing import Callable, Iterable

MANIFEST_NAME = "manifest.sha256.json"
MANIFEST_VERSION = 1

# Dateien, die zum Ordner gehören, aber nicht im Manifest stehen (werden zur
# Laufzeit erzeugt bzw. enthalten das Manifest selbst).
EXCLUDED_NAMES = {MANIFEST_NAME, "startup.log"}

# Windows-Dateiattribute, die auf eine nicht (vollständig) lokal gespeicherte
# Cloud-Datei hindeuten (Windows SDK: FILE_ATTRIBUTE_OFFLINE,
# FILE_ATTRIBUTE_RECALL_ON_OPEN, FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS).
_CLOUD_PLACEHOLDER_MASK = 0x1000 | 0x40000 | 0x400000

# Ordnernamen (Kleinschreibung, Präfix-Vergleich) typischer Synchronisations-
# ordner. "OneDrive - Firma" beginnt ebenfalls mit "onedrive".
_SYNC_FOLDER_PREFIXES = (
    "nextcloud", "owncloud", "onedrive", "dropbox", "google drive",
    "googledrive", "icloud", "pcloud", "mega", "sync.com",
)

_CHUNK = 1024 * 1024


def _sha256_of(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            block = f.read(_CHUNK)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def iter_bundle_files(root: str) -> Iterable[str]:
    """Relative Pfade (mit '/') aller Dateien unter ``root``, sortiert, ohne
    die ausgeschlossenen Namen."""
    found = []
    for dirpath, _dirnames, filenames in os.walk(root):
        for name in filenames:
            if name in EXCLUDED_NAMES and os.path.normpath(dirpath) == os.path.normpath(root):
                continue
            full = os.path.join(dirpath, name)
            found.append(os.path.relpath(full, root).replace(os.sep, "/"))
    return sorted(found)


def build_manifest(root: str) -> dict:
    files = {}
    for rel in iter_bundle_files(root):
        full = os.path.join(root, *rel.split("/"))
        files[rel] = {"size": os.path.getsize(full), "sha256": _sha256_of(full)}
    return {
        "manifest_version": MANIFEST_VERSION,
        "created": time.strftime("%Y-%m-%d %H:%M:%S"),
        "file_count": len(files),
        "files": files,
    }


def write_manifest(root: str) -> str:
    """Schreibt das Manifest nach ``root`` und gibt den Pfad zurück."""
    manifest = build_manifest(root)
    path = os.path.join(root, MANIFEST_NAME)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1, sort_keys=True)
        f.write("\n")
    return path


def load_manifest(root: str) -> dict | None:
    """Manifest laden; ``None``, wenn es fehlt oder nicht lesbar ist."""
    path = os.path.join(root, MANIFEST_NAME)
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or not isinstance(data.get("files"), dict):
        return None
    return data


def _default_attrs(path: str) -> int:
    # st_file_attributes gibt es nur unter Windows; sonst 0.
    return getattr(os.stat(path), "st_file_attributes", 0)


def verify_bundle(
    root: str,
    manifest: dict | None = None,
    get_attrs: Callable[[str], int] = _default_attrs,
) -> list[str]:
    """Vergleicht den Ordner mit dem Manifest. Rückgabe: Liste verständlicher
    Problembeschreibungen (leer = alles stimmt).

    Reihenfolge je Datei: vorhanden? -> Cloud-Platzhalter? (dann NICHT lesen,
    sonst würde das Lesen einen Download anstoßen) -> Größe -> SHA-256.
    Zusätzliche, nicht im Manifest stehende Dateien werden ignoriert.
    """
    if manifest is None:
        manifest = load_manifest(root)
    if manifest is None:
        return [f"{MANIFEST_NAME} fehlt oder ist nicht lesbar"]

    problems: list[str] = []
    for rel, meta in sorted(manifest["files"].items()):
        full = os.path.join(root, *rel.split("/"))
        if not os.path.isfile(full):
            problems.append(f"fehlt: {rel}")
            continue
        try:
            if get_attrs(full) & _CLOUD_PLACEHOLDER_MASK:
                problems.append(f"nur in der Cloud, nicht lokal gespeichert: {rel}")
                continue
            size = os.path.getsize(full)
            if size != meta["size"]:
                problems.append(f"falsche Größe ({size} statt {meta['size']} Byte): {rel}")
                continue
            if _sha256_of(full) != meta["sha256"]:
                problems.append(f"Inhalt verändert (Prüfsumme weicht ab): {rel}")
        except OSError as exc:
            problems.append(f"nicht lesbar ({exc.__class__.__name__}): {rel}")
    return problems


def describe_bundle_problems(problems: list[str], root: str, max_lines: int = 12) -> str:
    """Meldungstext für Dialog und Log."""
    shown = problems[:max_lines]
    more = len(problems) - len(shown)
    lines = "\n".join(f"  • {p}" for p in shown)
    if more > 0:
        lines += f"\n  … und {more} weitere"
    return (
        "Das Programm ist unvollständig oder wurde verändert. "
        f"{len(problems)} Datei(en) stimmen nicht mit dem ausgelieferten Stand überein.\n\n"
        f"{lines}\n\n"
        f"Ordner: {root}\n\n"
        "Bitte das ZIP-Archiv erneut vollständig entpacken (nicht nur einzelne "
        "Dateien kopieren) und den Ordner an einem lokalen Ort ablegen, z. B. "
        "C:\\Users\\<Ihr Name>\\FPV-Editor – nicht in einem "
        "Synchronisationsordner (Nextcloud, OneDrive …)."
    )


# ---------------------------------------------------------------------------
# Standortprüfung
# ---------------------------------------------------------------------------

def location_warnings(path: str) -> list[str]:
    """Hinweise, wenn ``path`` an einem Ort liegt, der erfahrungsgemäß Ärger
    macht. Das sind Verdachtsmomente, keine Fehler: Das Programm startet
    trotzdem, wenn die Dateiprüfung besteht."""
    warnings: list[str] = []
    norm = os.path.normpath(path)
    if norm.startswith("\\\\") and not norm.startswith("\\\\?\\"):
        warnings.append("Der Ordner liegt auf einem Netzlaufwerk (UNC-Pfad).")
    parts = [p.lower() for p in norm.replace("\\", "/").split("/") if p]
    for part in parts:
        if any(part.startswith(prefix) for prefix in _SYNC_FOLDER_PREFIXES):
            warnings.append(
                "Der Ordner liegt in einem Synchronisationsordner "
                f"(„{part}“). Dessen Dateien können unvollständig oder nur als "
                "Platzhalter vorliegen."
            )
            break
    if any(p.startswith("temp1_") and p.endswith(".zip") for p in parts):
        warnings.append(
            "Der Ordner liegt in einem temporären Entpackordner der ZIP-Vorschau. "
            "Bitte das ZIP ordentlich entpacken (Rechtsklick → Alle extrahieren)."
        )
    return warnings
