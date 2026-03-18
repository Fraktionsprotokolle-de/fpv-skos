import re

INPUT_FILE = "fpv_in_Bearbeitung_cg.ttl"
OUTPUT_FILE = "fpv_sorted.ttl"


def split_header_and_blocks(lines):
    header = []
    blocks = []

    current_block = []
    in_block = False

    for line in lines:
        # Start eines Blocks erkennen
        if re.match(r'^\s*ex:[^\s]+\s+a\s+skos:Concept', line):
            in_block = True
            if current_block:
                blocks.append(current_block)
                current_block = []

        if in_block:
            current_block.append(line)

            # Blockende erkennen (Zeile mit Punkt)
            if re.match(r'^\s*\.\s*$', line):
                blocks.append(current_block)
                current_block = []
                in_block = False
        else:
            header.append(line)

    # Falls Datei nicht sauber endet
    if current_block:
        blocks.append(current_block)

    return header, blocks


def extract_id(block):
    first_line = block[0]
    match = re.search(r'ex:([^\s]+)', first_line)
    if match:
        return match.group(1).lower()
    return ""


def sort_blocks(blocks):
    return sorted(blocks, key=extract_id)


def write_output(header, blocks, output_file):
    with open(output_file, "w", encoding="utf-8", newline="\n") as f:
        f.writelines(header)

        if header and not header[-1].endswith("\n"):
            f.write("\n")

        for block in blocks:
            f.writelines(block)
            if not block[-1].endswith("\n"):
                f.write("\n")
            f.write("\n")  # Leerzeile zwischen Blöcken


def main():
    print(f"Lese Datei: {INPUT_FILE}")

    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        lines = f.readlines()

    header, blocks = split_header_and_blocks(lines)

    print(f"Gefundene Concept-Blöcke: {len(blocks)}")

    sorted_blocks = sort_blocks(blocks)

    write_output(header, sorted_blocks, OUTPUT_FILE)

    print(f"Fertig. Sortierte Datei: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()