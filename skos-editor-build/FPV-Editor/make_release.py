# -*- coding: utf-8 -*-
"""
make_release.py — Schlussschritt des Windows-Builds.

Aufruf (aus build_windows.bat):
    python make_release.py dist\\FPV-Editor [dist\\FPV-Editor.zip]

1. Schreibt ``manifest.sha256.json`` (Größe + SHA-256 jeder Datei) in den
   gebauten Ordner und legt ``LIES-MICH.txt`` dazu.
2. Packt den Ordnerinhalt als ZIP OHNE zusätzlichen obersten Ordner. Der
   Zielordner wird beim Entpacken ("Alle extrahieren") gewählt; so entsteht
   kein doppelt verschachteltes FPV-Editor\\FPV-Editor.
3. Weist das ZIP nach: liest es wieder ein und vergleicht jede Datei mit dem
   Manifest. Nur bei vollständigem Treffer endet das Skript mit Exitcode 0.

Das Skript ist eigener Code, daher OHNE ``-I`` aufrufen (es importiert
``bundle_check`` aus dem eigenen Ordner).
"""

from __future__ import annotations

import hashlib
import os
import shutil
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import bundle_check  # noqa: E402



def make_zip(root: str, zip_path: str) -> int:
    """Packt ``root`` nach ``zip_path``; gibt die Zahl der Dateien zurück."""
    if os.path.exists(zip_path):
        os.remove(zip_path)
    names = list(bundle_check.iter_bundle_files(root)) + [bundle_check.MANIFEST_NAME]
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for rel in sorted(set(names)):
            zf.write(os.path.join(root, *rel.split("/")), arcname=rel)
    return len(set(names))


def verify_zip(zip_path: str, manifest: dict) -> list[str]:
    """Liest das ZIP wieder ein und vergleicht es mit dem Manifest."""
    problems: list[str] = []
    with zipfile.ZipFile(zip_path) as zf:
        bad = zf.testzip()
        if bad:
            problems.append(f"ZIP-Prüfsumme fehlerhaft: {bad}")
        members = {i.filename for i in zf.infolist()}
        for rel, meta in sorted(manifest["files"].items()):
            arc = rel
            if arc not in members:
                problems.append(f"fehlt im ZIP: {rel}")
                continue
            h = hashlib.sha256()
            size = 0
            with zf.open(arc) as f:
                for block in iter(lambda: f.read(1024 * 1024), b""):
                    h.update(block)
                    size += len(block)
            if size != meta["size"] or h.hexdigest() != meta["sha256"]:
                problems.append(f"Inhalt weicht ab: {rel}")
        if bundle_check.MANIFEST_NAME not in members:
            problems.append("Manifest fehlt im ZIP")
    return problems


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("Aufruf: python make_release.py <gebauter Ordner> [<ZIP-Ziel>]")
        return 2
    root = os.path.abspath(argv[1])
    zip_path = os.path.abspath(argv[2]) if len(argv) > 2 else root.rstrip("\\/") + ".zip"
    if not os.path.isdir(root):
        print(f"FEHLER: Ordner nicht gefunden: {root}")
        return 1

    readme_src = os.path.join(HERE, "LIES-MICH.txt")
    if os.path.isfile(readme_src):
        shutil.copyfile(readme_src, os.path.join(root, "LIES-MICH.txt"))
    else:
        print("WARNUNG: LIES-MICH.txt fehlt neben make_release.py und wird nicht mitgeliefert.")

    manifest_path = bundle_check.write_manifest(root)
    manifest = bundle_check.load_manifest(root)
    if manifest is None:
        print(f"FEHLER: Manifest nicht lesbar: {manifest_path}")
        return 1
    print(f"Manifest: {manifest['file_count']} Dateien")

    # Der Ordner selbst muss dem Manifest entsprechen (Gegenprobe der Prüfung,
    # die später beim Start läuft).
    problems = bundle_check.verify_bundle(root, manifest)
    if problems:
        print("FEHLER: Der gebaute Ordner stimmt nicht mit seinem eigenen Manifest überein:")
        for p in problems[:20]:
            print("  " + p)
        return 1

    count = make_zip(root, zip_path)
    problems = verify_zip(zip_path, manifest)
    if problems:
        print("FEHLER: ZIP-Nachweis fehlgeschlagen:")
        for p in problems[:20]:
            print("  " + p)
        return 1
    size_mb = os.path.getsize(zip_path) / (1024 * 1024)
    print(f"ZIP erstellt und gegen das Manifest geprüft: {zip_path} ({count} Dateien, {size_mb:.1f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
