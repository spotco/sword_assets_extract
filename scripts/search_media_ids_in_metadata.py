from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path


DEFAULT_GAME_ROOT = Path(r"C:\Program Files (x86)\Steam\steamapps\common\Sword of Convallaria")
DEFAULT_CANDIDATES = Path("reports/unnamed_music_name_candidates.csv")
DEFAULT_OUT = Path("reports/unnamed_music_metadata_search.csv")
KEY = b"XD_Audio"


def candidate_ids(path: Path) -> dict[int, str]:
    with path.open("r", newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    return {int(row["media_id"]): row["relative_path"] for row in rows if row["confidence"] == "missing"}


def maybe_decode(data: bytes) -> bytes:
    if data.startswith((b"BKHD", b"RIFF", b"UnityFS")):
        return data
    decoded = bytes(byte ^ KEY[index % len(KEY)] for index, byte in enumerate(data[: min(len(data), 1024 * 1024)]))
    if decoded.startswith((b"BKHD", b"RIFF")):
        return decoded + data[len(decoded) :]
    return data


def strings_near(data: bytes, pos: int, radius: int = 256) -> str:
    start = max(0, pos - radius)
    end = min(len(data), pos + radius)
    nearby = data[start:end]
    strings = [m.group(0).decode("ascii", "ignore") for m in re.finditer(rb"[ -~]{4,}", nearby)]
    return " | ".join(strings[:12])


def main() -> int:
    parser = argparse.ArgumentParser(description="Search non-Media metadata for unnamed media ids.")
    parser.add_argument("--game-root", type=Path, default=DEFAULT_GAME_ROOT)
    parser.add_argument("--candidates", type=Path, default=DEFAULT_CANDIDATES)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    ids = candidate_ids(args.candidates)
    needles: dict[bytes, tuple[int, str]] = {}
    for media_id in ids:
        needles[media_id.to_bytes(4, "little")] = (media_id, "le32")
        needles[media_id.to_bytes(4, "big")] = (media_id, "be32")
        needles[str(media_id).encode("ascii")] = (media_id, "decimal")

    roots = [args.game_root / "assets"]
    allowed_exts = {".unity3d", ".bytes", ".txt", ".ini", ".json", ".proto", ".bnk", ".bin"}
    rows = []
    for root in roots:
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            rel = path.relative_to(args.game_root / "assets")
            rel_text = str(rel).replace("\\", "/")
            if rel_text.startswith("audio/Media/"):
                continue
            if path.suffix.lower() not in allowed_exts:
                continue
            try:
                data = maybe_decode(path.read_bytes())
            except OSError:
                continue
            for needle, (media_id, kind) in needles.items():
                pos = data.find(needle)
                if pos == -1:
                    continue
                rows.append(
                    {
                        "media_id": media_id,
                        "relative_path": ids[media_id],
                        "hit_file": rel_text,
                        "hit_kind": kind,
                        "offset": f"0x{pos:x}",
                        "nearby_strings": strings_near(data, pos),
                    }
                )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="", encoding="utf-8") as handle:
        fieldnames = ["media_id", "relative_path", "hit_file", "hit_kind", "offset", "nearby_strings"]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {args.out}")
    print(f"Hits: {len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
