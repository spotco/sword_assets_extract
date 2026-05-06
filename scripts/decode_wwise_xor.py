from __future__ import annotations

import argparse
from pathlib import Path


DEFAULT_GAME_ROOT = Path(r"C:\Program Files (x86)\Steam\steamapps\common\Sword of Convallaria")
DEFAULT_OUT = Path("extracted/audio_xor_decoded")
KEY = b"XD_Audio"
CHUNK_SIZE = 1024 * 1024


def source_mode(source: Path) -> str:
    with source.open("rb") as handle:
        data = handle.read(16)
    if not data:
        return "empty"
    if data.startswith(b"RIFF") and data[8:12] == b"WAVE":
        return "plain"
    if data.startswith(b"BKHD"):
        return "plain"
    if data[:4] == bytes([ord("R") ^ ord("X"), ord("I") ^ ord("D"), ord("F") ^ ord("_"), ord("F") ^ ord("A")]):
        return "xor"
    if data[:4] == bytes([ord("B") ^ ord("X"), ord("K") ^ ord("D"), ord("H") ^ ord("_"), ord("D") ^ ord("A")]):
        return "xor"
    return "unknown"


def is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def xor_chunk(data: bytes, offset: int) -> bytes:
    key_len = len(KEY)
    return bytes(byte ^ KEY[(offset + index) % key_len] for index, byte in enumerate(data))


def decode_file(source: Path, dest: Path, overwrite: bool) -> tuple[bool, str]:
    if dest.exists() and not overwrite:
        return False, "exists"

    dest.parent.mkdir(parents=True, exist_ok=True)
    mode = source_mode(source)
    if mode in {"plain", "empty", "unknown"}:
        with source.open("rb") as src, dest.open("wb") as dst:
            while True:
                chunk = src.read(CHUNK_SIZE)
                if not chunk:
                    break
                dst.write(chunk)
        return True, mode

    offset = 0
    with source.open("rb") as src, dest.open("wb") as dst:
        while True:
            chunk = src.read(CHUNK_SIZE)
            if not chunk:
                break
            dst.write(xor_chunk(chunk, offset))
            offset += len(chunk)
    return True, mode


def validate_decoded(path: Path) -> str:
    data = path.read_bytes()[:16]
    if data.startswith(b"RIFF") and data[8:12] == b"WAVE":
        return "wem:RIFF/WAVE"
    if data.startswith(b"BKHD"):
        return "bnk:BKHD"
    return f"unexpected:{data[:8].hex()}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Decode Sword of Convallaria XOR-obfuscated Wwise audio.")
    parser.add_argument("--game-root", type=Path, default=DEFAULT_GAME_ROOT)
    parser.add_argument("--source", type=Path, default=None, help="Source directory or single .wem/.bnk file.")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--limit", type=int, default=0, help="Decode at most this many files. 0 means all.")
    parser.add_argument("--ext", action="append", choices=[".wem", ".bnk", "wem", "bnk"], help="Extension to process. Repeatable.")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    game_root = args.game_root.resolve()
    source = (args.source or (game_root / "assets" / "audio")).resolve()
    out = args.out.resolve()

    if is_relative_to(out, game_root):
        raise SystemExit(f"Refusing to write inside game folder: {out}")
    if not source.exists():
        raise SystemExit(f"Missing source: {source}")

    if source.is_file():
        files = [source]
        source_root = source.parent
    else:
        wanted_exts = {".wem", ".bnk"}
        if args.ext:
            wanted_exts = {item if item.startswith(".") else f".{item}" for item in args.ext}
        files = sorted([p for p in source.rglob("*") if p.is_file() and p.suffix.lower() in wanted_exts])
        source_root = source

    if args.limit:
        files = files[: args.limit]

    decoded = 0
    skipped = 0
    for file_path in files:
        rel = file_path.relative_to(source_root)
        dest = out / rel
        if args.dry_run:
            print(f"{file_path} -> {dest}")
            continue
        did_write, mode = decode_file(file_path, dest, args.overwrite)
        if did_write:
            decoded += 1
            status = validate_decoded(dest)
            if decoded <= 10:
                print(f"wrote {rel}: source={mode}, output={status}")
        else:
            skipped += 1

    print(f"Decoded: {decoded}")
    print(f"Skipped existing: {skipped}")
    print(f"Output: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
