from __future__ import annotations

import argparse
import csv
import hashlib
from pathlib import Path


DEFAULT_GAME_ROOT = Path(r"C:\Program Files (x86)\Steam\steamapps\common\Sword of Convallaria")
DEFAULT_AUDIO_NAMES = Path("reports/audio_name_report.csv")
DEFAULT_CANDIDATES = Path("reports/unnamed_music_name_candidates.csv")
DEFAULT_OUT = Path("reports/unnamed_music_hash_matches.csv")
KEY = b"XD_Audio"


def decoded_hash(path: Path) -> str:
    digest = hashlib.sha1()
    offset = 0
    with path.open("rb") as handle:
        first = handle.read(8)
        handle.seek(0)
        plain = first.startswith(b"RIFF")
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            if plain:
                digest.update(chunk)
            else:
                digest.update(bytes(byte ^ KEY[(offset + index) % len(KEY)] for index, byte in enumerate(chunk)))
            offset += len(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="Find exact decoded-audio hash matches for unnamed music candidates.")
    parser.add_argument("--game-root", type=Path, default=DEFAULT_GAME_ROOT)
    parser.add_argument("--audio-names", type=Path, default=DEFAULT_AUDIO_NAMES)
    parser.add_argument("--candidates", type=Path, default=DEFAULT_CANDIDATES)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    with args.candidates.open("r", newline="", encoding="utf-8") as handle:
        missing = [row for row in csv.DictReader(handle) if row["confidence"] == "missing"]
    missing_paths = {row["relative_path"] for row in missing}
    missing_hashes = {}
    missing_sizes = set()
    for row in missing:
        path = args.game_root / "assets" / row["relative_path"]
        missing_sizes.add(str(path.stat().st_size))
        missing_hashes[row["relative_path"]] = decoded_hash(path)

    with args.audio_names.open("r", newline="", encoding="utf-8") as handle:
        audio_rows = [
            row
            for row in csv.DictReader(handle)
            if row["extension"] == ".wem" and row["status"] == "event_name" and row["size"] in missing_sizes
        ]

    rows = []
    by_hash: dict[str, list[dict[str, str]]] = {}
    for index, row in enumerate(audio_rows, start=1):
        rel = row["relative_path"]
        if rel in missing_paths:
            continue
        path = args.game_root / "assets" / rel
        try:
            digest = decoded_hash(path)
        except OSError:
            continue
        if digest in set(missing_hashes.values()):
            by_hash.setdefault(digest, []).append(row)
        if index % 5000 == 0:
            print(f"Hashed named WEMs: {index}/{len(audio_rows)}")

    for rel, digest in missing_hashes.items():
        for match in by_hash.get(digest, []):
            rows.append(
                {
                    "unnamed_relative_path": rel,
                    "matched_relative_path": match["relative_path"],
                    "matched_title": match["suggested_title"],
                    "matched_filename": match["suggested_filename"],
                    "matched_events": match["event_names"],
                    "sha1_decoded": digest,
                }
            )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="", encoding="utf-8") as handle:
        fieldnames = [
            "unnamed_relative_path",
            "matched_relative_path",
            "matched_title",
            "matched_filename",
            "matched_events",
            "sha1_decoded",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {args.out}")
    print(f"Matches: {len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
