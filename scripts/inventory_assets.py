from __future__ import annotations

import argparse
import csv
import os
from collections import Counter, defaultdict
from pathlib import Path


DEFAULT_GAME_ROOT = Path(r"C:\Program Files (x86)\Steam\steamapps\common\Sword of Convallaria")
DEFAULT_OUT = Path("reports")


def classify_header(path: Path) -> str:
    try:
        with path.open("rb") as handle:
            data = handle.read(32)
    except OSError as exc:
        return f"read_error:{exc.__class__.__name__}"

    if data.startswith(b"UnityFS\0"):
        return "UnityFS"
    if data.startswith(b"\x00asm"):
        return "wasm"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if data.startswith(b"RIFF"):
        return "riff"
    if data.startswith(b"BKHD"):
        return "wwise_bank"
    if data[:4] == bytes([ord("R") ^ ord("X"), ord("I") ^ ord("D"), ord("F") ^ ord("_"), ord("F") ^ ord("A")]):
        return "xor_XD_Audio_riff"
    if data[:4] == bytes([ord("B") ^ ord("X"), ord("K") ^ ord("D"), ord("H") ^ ord("_"), ord("D") ^ ord("A")]):
        return "xor_XD_Audio_bank"
    if len(data) >= 12 and data[4:8] == b"ftyp":
        return "mp4"
    return "unknown"


def safe_rel(path: Path, root: Path) -> str:
    return str(path.relative_to(root)).replace("\\", "/")


def iter_asset_files(root: Path, excluded_dirs: set[str]):
    for current, dirnames, filenames in os.walk(root):
        dirnames[:] = [name for name in dirnames if name.lower() not in excluded_dirs]
        current_path = Path(current)
        for filename in filenames:
            yield current_path / filename


def main() -> int:
    parser = argparse.ArgumentParser(description="Inventory Sword of Convallaria asset files.")
    parser.add_argument("--game-root", type=Path, default=DEFAULT_GAME_ROOT)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--header-limit", type=int, default=10000, help="Max files to header-classify.")
    parser.add_argument(
        "--exclude-dir",
        action="append",
        default=["Report"],
        help="Directory name to skip while walking assets. Repeatable. Defaults to Report.",
    )
    parser.add_argument("--include-report", action="store_true", help="Do not skip assets\\Report.")
    args = parser.parse_args()

    game_root = args.game_root.resolve()
    assets_root = game_root / "assets"
    if not assets_root.is_dir():
        raise SystemExit(f"Missing assets directory: {assets_root}")

    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, str | int]] = []
    ext_counts: Counter[str] = Counter()
    ext_bytes: Counter[str] = Counter()
    header_counts: Counter[str] = Counter()
    top_dirs: dict[str, Counter[str]] = defaultdict(Counter)

    scanned_files = 0
    missing_files = 0
    excluded_dirs = {item.lower() for item in args.exclude_dir if item}
    if args.include_report:
        excluded_dirs.discard("report")
    for index, path in enumerate(iter_asset_files(assets_root, excluded_dirs)):
        try:
            stat = path.stat()
        except FileNotFoundError:
            missing_files += 1
            continue
        scanned_files += 1
        rel = safe_rel(path, assets_root)
        ext = path.suffix.lower() or "<none>"
        header = classify_header(path) if index < args.header_limit else "not_scanned"

        ext_counts[ext] += 1
        ext_bytes[ext] += stat.st_size
        header_counts[header] += 1
        top = rel.split("/", 1)[0]
        top_dirs[top][ext] += 1

        rows.append(
            {
                "relative_path": rel,
                "size": stat.st_size,
                "extension": ext,
                "header": header,
                "mtime": int(stat.st_mtime),
            }
        )

    with (out / "asset_manifest.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["relative_path", "size", "extension", "header", "mtime"])
        writer.writeheader()
        writer.writerows(rows)

    with (out / "summary.txt").open("w", encoding="utf-8") as handle:
        handle.write(f"Game root: {game_root}\n")
        handle.write(f"Assets root: {assets_root}\n")
        handle.write(f"Files: {scanned_files}\n")
        handle.write(f"Skipped missing during scan: {missing_files}\n")
        handle.write(f"Excluded dirs: {', '.join(sorted(excluded_dirs)) or '<none>'}\n")
        handle.write(f"Bytes: {sum(ext_bytes.values())}\n\n")
        handle.write("Extensions:\n")
        for ext, count in ext_counts.most_common():
            handle.write(f"  {ext}: {count} files, {ext_bytes[ext]} bytes\n")
        handle.write("\nHeaders:\n")
        for header, count in header_counts.most_common():
            handle.write(f"  {header}: {count}\n")
        handle.write("\nTop directories by extension:\n")
        for directory in sorted(top_dirs):
            parts = ", ".join(f"{ext}={count}" for ext, count in top_dirs[directory].most_common())
            handle.write(f"  {directory}: {parts}\n")

    print(f"Scanned files: {scanned_files}")
    if missing_files:
        print(f"Skipped files that vanished during scan: {missing_files}")
    print(f"Wrote {out / 'asset_manifest.csv'}")
    print(f"Wrote {out / 'summary.txt'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
