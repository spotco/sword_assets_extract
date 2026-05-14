from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

from common import safe_name, write_json


REPORTS = Path("level_probe/reports")
OUT_ROOT = Path("extracted/web_levels")


def parse_vec3(text: str) -> dict[str, float] | None:
    if not text:
        return None
    parts = [part.strip() for part in text.split(",")]
    if len(parts) != 3:
        return None
    try:
        x, y, z = (float(part) for part in parts)
    except ValueError:
        return None
    return {"x": x, "y": y, "z": z}


def walkability_from_path(path: str) -> str:
    marker = "/emptyblock/"
    if marker not in path:
        return "unknown"
    tail = path.split(marker, 1)[1]
    return tail.split("/", 1)[0] or "unknown"


def read_grid(path: Path) -> list[dict[str, Any]]:
    with path.open("r", newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    tiles = []
    for row in rows:
        world = parse_vec3(row.get("world_position", ""))
        local = parse_vec3(row.get("local_position", ""))
        position = world or local
        if position is None:
            continue

        collider_size = parse_vec3(row.get("collider_size", ""))
        collider_center = parse_vec3(row.get("collider_center", ""))
        path_text = row.get("path", "")
        block_type = row.get("block_type", "")

        tiles.append(
            {
                "id": row.get("game_object_id", ""),
                "monoId": row.get("mono_id", ""),
                "name": row.get("name", ""),
                "path": path_text,
                "walkability": walkability_from_path(path_text),
                "position": position,
                "localPosition": local,
                "blockType": int(block_type) if block_type.isdigit() else block_type,
                "isGamepadCursorMovable": row.get("is_gamepad_cursor_movable", ""),
                "layer": row.get("layer", ""),
                "collider": {
                    "type": row.get("collider_type", ""),
                    "isTrigger": row.get("is_trigger", ""),
                    "center": collider_center,
                    "size": collider_size,
                },
            }
        )
    return tiles


def read_metadata(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def read_scene_object_indexes(path: Path) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    if not path.exists():
        return {}, {}

    game_objects: dict[str, dict[str, Any]] = {}
    transforms_by_go: dict[str, dict[str, Any]] = {}
    with path.open("r", newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row.get("type") == "GameObject":
                game_objects[row.get("path_id", "")] = {
                    "name": row.get("name", ""),
                    "tag": row.get("tag", ""),
                    "layer": row.get("layer", ""),
                    "componentCount": row.get("component_count", ""),
                }
            elif row.get("type") in {"Transform", "RectTransform"}:
                game_object_id = row.get("game_object", "")
                transforms_by_go[game_object_id] = {
                    "pathId": row.get("path_id", ""),
                    "localPosition": parse_vec3(row.get("local_position", "")),
                    "localScale": parse_vec3(row.get("local_scale", "")),
                }
    return game_objects, transforms_by_go


def read_colliders(path: Path, scene_objects_path: Path, tiles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not path.exists():
        return []

    game_objects, transforms_by_go = read_scene_object_indexes(scene_objects_path)
    tiles_by_go = {str(tile["id"]): tile for tile in tiles}
    colliders = []
    with path.open("r", newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            game_object_id = row.get("game_object", "")
            transform = transforms_by_go.get(game_object_id, {})
            tile = tiles_by_go.get(game_object_id)
            position = None
            source = "scene_object_transform"
            if tile:
                position = tile.get("position")
                source = "grid_tile"
            elif transform.get("localPosition"):
                position = transform.get("localPosition")

            center = parse_vec3(row.get("center", ""))
            size = parse_vec3(row.get("size", ""))
            game_object = game_objects.get(game_object_id, {})
            colliders.append(
                {
                    "id": row.get("path_id", ""),
                    "type": row.get("type", ""),
                    "gameObjectId": game_object_id,
                    "gameObjectName": game_object.get("name", ""),
                    "layer": game_object.get("layer", ""),
                    "enabled": row.get("enabled", ""),
                    "isTrigger": row.get("is_trigger", ""),
                    "position": position,
                    "positionSource": source if position else "",
                    "center": center,
                    "size": size,
                    "tilePath": tile.get("path", "") if tile else "",
                    "walkability": tile.get("walkability", "") if tile else "",
                    "blockType": tile.get("blockType", "") if tile else "",
                }
            )
    return colliders


def useful_metadata(raw: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {
        "bundle": raw.get("bundle", ""),
        "resolvedBundle": raw.get("resolved_bundle", ""),
        "blockCount": raw.get("block_count", 0),
        "blockTypeCounts": raw.get("block_type_counts", {}),
    }
    for item in raw.get("metadata", []):
        script = item.get("script")
        fields = item.get("fields", {})
        if script == "MapTool":
            result["mapTool"] = {
                "width": fields.get("width"),
                "height": fields.get("height"),
                "path": item.get("path", ""),
            }
        elif script == "MapProperty":
            result["mapProperty"] = {
                "useBound": fields.get("useBound"),
                "useBattle": fields.get("useBattle"),
                "boundMin": fields.get("boundMin"),
                "boundMax": fields.get("boundMax"),
                "boundMinCamera": fields.get("boundMinCamera"),
                "boundMaxCamera": fields.get("boundMaxCamera"),
                "orthographicSize": fields.get("orthographicSize"),
                "path": item.get("path", ""),
            }
        elif script == "BattleGrassData":
            result["battleGrassData"] = {
                "infosCount": fields.get("infos_count"),
                "scenePath": fields.get("scenePath"),
                "path": item.get("path", ""),
            }
    return result


def extent_for_tiles(tiles: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    if not tiles:
        zero = {"x": 0.0, "y": 0.0, "z": 0.0}
        return {"min": zero, "max": zero, "center": zero}

    xs = [tile["position"]["x"] for tile in tiles]
    ys = [tile["position"]["y"] for tile in tiles]
    zs = [tile["position"]["z"] for tile in tiles]
    minimum = {"x": min(xs), "y": min(ys), "z": min(zs)}
    maximum = {"x": max(xs), "y": max(ys), "z": max(zs)}
    center = {
        "x": (minimum["x"] + maximum["x"]) / 2,
        "y": (minimum["y"] + maximum["y"]) / 2,
        "z": (minimum["z"] + maximum["z"]) / 2,
    }
    return {"min": minimum, "max": maximum, "center": center}


def build_payload(map_name: str, grid_path: Path, metadata_path: Path) -> dict[str, Any]:
    tiles = read_grid(grid_path)
    metadata = useful_metadata(read_metadata(metadata_path))
    walkability_counts: dict[str, int] = {}
    for tile in tiles:
        key = str(tile["walkability"])
        walkability_counts[key] = walkability_counts.get(key, 0) + 1

    return {
        "schemaVersion": 1,
        "mapName": map_name,
        "source": {
            "gridCsv": str(grid_path).replace("\\", "/"),
            "metadataJson": str(metadata_path).replace("\\", "/"),
        },
        "metadata": metadata,
        "stats": {
            "tileCount": len(tiles),
            "walkabilityCounts": walkability_counts,
            "extent": extent_for_tiles(tiles),
        },
        "tiles": tiles,
    }


def build_colliders_payload(
    map_name: str,
    colliders_path: Path,
    scene_objects_path: Path,
    tiles: list[dict[str, Any]],
) -> dict[str, Any]:
    colliders = read_colliders(colliders_path, scene_objects_path, tiles)
    type_counts: dict[str, int] = {}
    drawable_count = 0
    for collider in colliders:
        type_name = str(collider.get("type", "") or "unknown")
        type_counts[type_name] = type_counts.get(type_name, 0) + 1
        if collider.get("position") and collider.get("center") and collider.get("size"):
            drawable_count += 1

    return {
        "schemaVersion": 1,
        "mapName": map_name,
        "source": {
            "collidersCsv": str(colliders_path).replace("\\", "/"),
            "sceneObjectsCsv": str(scene_objects_path).replace("\\", "/"),
        },
        "stats": {
            "colliderCount": len(colliders),
            "drawableCount": drawable_count,
            "typeCounts": type_counts,
        },
        "colliders": colliders,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Export extracted battle grid reports to browser-ready JSON.")
    parser.add_argument("--map", dest="map_name", default="stage_city-ca-da00101", help="Report stem/map name to export.")
    parser.add_argument("--grid-csv", type=Path, help="Explicit *_grid_blocks.csv path.")
    parser.add_argument("--metadata-json", type=Path, help="Explicit *_map_metadata.json path.")
    parser.add_argument("--colliders-csv", type=Path, help="Explicit *_colliders.csv path.")
    parser.add_argument("--scene-objects-csv", type=Path, help="Explicit *_scene_objects.csv path.")
    parser.add_argument("--out-root", type=Path, default=OUT_ROOT, help="Output root for web level folders.")
    args = parser.parse_args()

    map_name = safe_name(args.map_name)
    grid_path = args.grid_csv or REPORTS / f"{map_name}_grid_blocks.csv"
    metadata_path = args.metadata_json or REPORTS / f"{map_name}_map_metadata.json"
    colliders_path = args.colliders_csv or REPORTS / f"{map_name}_colliders.csv"
    scene_objects_path = args.scene_objects_csv or REPORTS / f"{map_name}_scene_objects.csv"

    if not grid_path.exists():
        raise SystemExit(f"Missing grid CSV: {grid_path}")

    out_dir = args.out_root / map_name
    payload = build_payload(map_name, grid_path, metadata_path)
    write_json(out_dir / "grid.json", payload)
    colliders_payload = build_colliders_payload(map_name, colliders_path, scene_objects_path, payload["tiles"])
    write_json(out_dir / "colliders.json", colliders_payload)
    print(f"Wrote {out_dir / 'grid.json'} with {len(payload['tiles'])} tiles")
    print(
        f"Wrote {out_dir / 'colliders.json'} with "
        f"{colliders_payload['stats']['colliderCount']} colliders "
        f"({colliders_payload['stats']['drawableCount']} drawable)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
