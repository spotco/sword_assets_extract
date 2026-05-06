from __future__ import annotations

import argparse
import re
from pathlib import Path


DEFAULT_GAME_ROOT = Path(r"C:\Program Files (x86)\Steam\steamapps\common\Sword of Convallaria")
DEFAULT_OUT = Path("extracted/unity_images")


def is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def safe_name(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._")
    return cleaned or "unnamed"


def load_unitypy():
    try:
        import UnityPy  # type: ignore
    except ImportError as exc:
        raise SystemExit(
            "UnityPy is not installed. Install it with: python -m pip install UnityPy\n"
            "No files were written."
        ) from exc
    return UnityPy


def main() -> int:
    parser = argparse.ArgumentParser(description="Export Texture2D/Sprite PNGs from UnityFS .unity3d bundles.")
    parser.add_argument("--game-root", type=Path, default=DEFAULT_GAME_ROOT)
    parser.add_argument("--source", type=Path, default=None, help="Source directory or single .unity3d file.")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--include", action="append", default=[], help="Only process bundle paths containing this text.")
    parser.add_argument("--limit", type=int, default=0, help="Process at most this many bundles. 0 means all.")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    UnityPy = load_unitypy()
    game_root = args.game_root.resolve()
    source = (args.source or (game_root / "assets")).resolve()
    out = args.out.resolve()

    if is_relative_to(out, game_root):
        raise SystemExit(f"Refusing to write inside game folder: {out}")
    if not source.exists():
        raise SystemExit(f"Missing source: {source}")

    if source.is_file():
        bundles = [source]
        source_root = source.parent
    else:
        bundles = sorted(source.rglob("*.unity3d"))
        source_root = source

    if args.include:
        needles = [item.lower() for item in args.include]
        bundles = [p for p in bundles if any(needle in str(p.relative_to(source_root)).lower() for needle in needles)]
    if args.limit:
        bundles = bundles[: args.limit]

    exported = 0
    processed = 0
    for bundle in bundles:
        rel_bundle = bundle.relative_to(source_root)
        try:
            env = UnityPy.load(str(bundle))
        except Exception as exc:
            print(f"skip {rel_bundle}: load failed: {exc}")
            continue

        processed += 1
        for obj in env.objects:
            type_name = obj.type.name
            if type_name not in {"Texture2D", "Sprite"}:
                continue
            try:
                data = obj.read()
                image = getattr(data, "image", None)
                if image is None:
                    continue
                object_name = safe_name(getattr(data, "name", type_name))
                stem = safe_name(bundle.stem)
                dest = out / rel_bundle.parent / f"{stem}__{object_name}__{obj.path_id}.png"
                if dest.exists() and not args.overwrite:
                    continue
                dest.parent.mkdir(parents=True, exist_ok=True)
                image.save(dest)
                exported += 1
                if exported <= 20:
                    print(f"exported {dest}")
            except Exception as exc:
                print(f"skip object {rel_bundle}:{obj.path_id}: {exc}")

    print(f"Processed bundles: {processed}")
    print(f"Exported images: {exported}")
    print(f"Output: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
