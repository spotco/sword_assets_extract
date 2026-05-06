from __future__ import annotations

import argparse
from pathlib import Path


DEFAULT_OUT = Path("extracted/carved")
SIGNATURES = {
    b"\x89PNG\r\n\x1a\n": (".png", b"IEND\xaeB`\x82"),
    b"\xff\xd8\xff": (".jpg", b"\xff\xd9"),
    b"OggS": (".ogg", None),
    b"RIFF": (".riff", None),
}


def iter_files(path: Path):
    if path.is_file():
        yield path
    else:
        yield from (p for p in path.rglob("*") if p.is_file())


def carve_file(source: Path, out_root: Path, base_root: Path) -> int:
    data = source.read_bytes()
    count = 0
    rel = source.relative_to(base_root) if source != base_root else Path(source.name)
    rel_safe = Path(*[part.replace(":", "_") for part in rel.parts])

    for sig, (ext, end_sig) in SIGNATURES.items():
        start = 0
        while True:
            pos = data.find(sig, start)
            if pos == -1:
                break
            if end_sig:
                end = data.find(end_sig, pos + len(sig))
                if end == -1:
                    start = pos + len(sig)
                    continue
                end += len(end_sig)
            elif sig == b"RIFF" and pos + 8 <= len(data):
                size = int.from_bytes(data[pos + 4 : pos + 8], "little")
                end = min(len(data), pos + 8 + size)
            else:
                next_positions = [data.find(other, pos + len(sig)) for other in SIGNATURES if other != sig]
                next_positions = [item for item in next_positions if item != -1]
                end = min(next_positions) if next_positions else len(data)

            dest = out_root / rel_safe.parent / f"{rel_safe.stem}_{pos:08x}{ext}"
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data[pos:end])
            count += 1
            start = end
    return count


def main() -> int:
    parser = argparse.ArgumentParser(description="Carve simple media signatures from copied/sample files.")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    source = args.input.resolve()
    out = args.out.resolve()
    if not source.exists():
        raise SystemExit(f"Missing input: {source}")

    base = source if source.is_dir() else source.parent
    total = 0
    for path in iter_files(source):
        count = carve_file(path, out, base)
        if count:
            print(f"{path}: carved {count}")
        total += count

    print(f"Carved files: {total}")
    print(f"Output: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
