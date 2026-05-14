from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Any

from common import ASSETS_ROOT, REPORTS, safe_name, write_json


OUT_ROOT = Path("extracted/web_levels")


def iter_battle_maps() -> list[dict[str, Any]]:
    battle_map_root = ASSETS_ROOT / "battle" / "map"
    if battle_map_root.exists():
        return [
            {
                "mapName": safe_name(path.stem),
                "bundle": str(path.relative_to(ASSETS_ROOT)).replace("\\", "/"),
                "size": path.stat().st_size,
            }
            for path in sorted(battle_map_root.glob("*.unity3d"))
        ]

    fallback = REPORTS / "level_candidate_files.csv"
    if not fallback.exists():
        return []

    maps = []
    with fallback.open("r", newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            relative = row.get("relative_path", "")
            if not relative.startswith("battle/map/") or not relative.endswith(".unity3d"):
                continue
            maps.append(
                {
                    "mapName": safe_name(Path(relative).stem),
                    "bundle": relative,
                    "size": int(row.get("size", "0") or 0),
                }
            )
    return sorted(maps, key=lambda item: item["mapName"])


def enrich_with_exports(level: dict[str, Any], out_root: Path) -> dict[str, Any]:
    level_dir = out_root / level["mapName"]
    files = {
        "grid": level_dir / "grid.json",
        "colliders": level_dir / "colliders.json",
        "meshes": level_dir / "meshes.json",
    }
    exported = {key: path.exists() for key, path in files.items()}
    return {
        **level,
        "exported": exported,
        "isExtracted": exported["grid"],
        "paths": {
            key: str(path).replace("\\", "/") if exported[key] else ""
            for key, path in files.items()
        },
    }


def build_index(out_root: Path) -> dict[str, Any]:
    levels = [enrich_with_exports(level, out_root) for level in iter_battle_maps()]
    return {
        "schemaVersion": 1,
        "levelCount": len(levels),
        "extractedCount": sum(1 for level in levels if level["isExtracted"]),
        "levels": levels,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build web viewer level index for all battle map bundles.")
    parser.add_argument("--out-root", type=Path, default=OUT_ROOT, help="Output root for web level folders.")
    args = parser.parse_args()

    payload = build_index(args.out_root)
    write_json(args.out_root / "index.json", payload)
    print(
        f"Wrote {args.out_root / 'index.json'} with "
        f"{payload['levelCount']} levels ({payload['extractedCount']} extracted)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

