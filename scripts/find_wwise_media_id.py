from __future__ import annotations

import argparse
import re
from pathlib import Path


DEFAULT_GAME_ROOT = Path(r"C:\Program Files (x86)\Steam\steamapps\common\Sword of Convallaria")
KEY = b"XD_Audio"


def xor_data(data: bytes) -> bytes:
    return bytes(byte ^ KEY[index % len(KEY)] for index, byte in enumerate(data))


def decode_if_needed(data: bytes) -> bytes:
    if data.startswith(b"BKHD") or data.startswith(b"RIFF"):
        return data
    decoded = xor_data(data)
    if decoded.startswith(b"BKHD") or decoded.startswith(b"RIFF"):
        return decoded
    return data


def ascii_strings(data: bytes, min_len: int = 4) -> list[str]:
    return [match.group(0).decode("ascii", "ignore") for match in re.finditer(rb"[ -~]{%d,}" % min_len, data)]


def main() -> int:
    parser = argparse.ArgumentParser(description="Find Wwise banks or metadata containing a media id.")
    parser.add_argument("media_id", type=int)
    parser.add_argument("--root", type=Path, default=DEFAULT_GAME_ROOT / "assets" / "audio")
    parser.add_argument("--context", type=int, default=256)
    parser.add_argument("--ext", action="append", default=[".bnk"], help="Extension to scan. Repeatable. Defaults to .bnk.")
    args = parser.parse_args()

    root = args.root.resolve()
    needles = {
        "le32": args.media_id.to_bytes(4, "little", signed=False),
        "be32": args.media_id.to_bytes(4, "big", signed=False),
        "decimal": str(args.media_id).encode("ascii"),
    }

    hits = 0
    exts = {item if item.startswith(".") else f".{item}" for item in args.ext}
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in exts:
            continue
        try:
            raw = path.read_bytes()
        except OSError:
            continue
        data = decode_if_needed(raw)
        for label, needle in needles.items():
            pos = data.find(needle)
            if pos == -1:
                continue
            hits += 1
            rel = path.relative_to(root)
            start = max(0, pos - args.context)
            end = min(len(data), pos + len(needle) + args.context)
            strings = ascii_strings(data[start:end])
            print(f"{rel} hit={label} offset=0x{pos:x}")
            if strings:
                print("  strings: " + " | ".join(strings[:12]))
            break

    print(f"Hits: {hits}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
