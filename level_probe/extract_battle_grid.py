from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path
from typing import Any

import UnityPy

from common import ensure_reports, flatten_value, rel, resolve_asset_path, safe_name, write_csv, write_json


ObjectKey = tuple[int, int]


def pptr_id(value: Any) -> int | None:
    return getattr(value, "path_id", None) or getattr(value, "m_PathID", None)


def object_key(obj: Any) -> ObjectKey:
    return (id(obj.assets_file), int(obj.path_id))


def ref_key(ref: Any) -> ObjectKey | None:
    path_id = pptr_id(ref)
    assets_file = getattr(ref, "assetsfile", None)
    if path_id is None or assets_file is None:
        return None
    return (id(assets_file), int(path_id))


def vec3(value: Any) -> tuple[float, float, float] | None:
    if value is None:
        return None
    if all(hasattr(value, attr) for attr in ("x", "y", "z")):
        return (float(value.x), float(value.y), float(value.z))
    return None


def vec3_text(value: tuple[float, float, float] | None) -> str:
    if value is None:
        return ""
    return ",".join(f"{item:g}" for item in value)


def add_vec3(left: tuple[float, float, float] | None, right: tuple[float, float, float] | None) -> tuple[float, float, float] | None:
    if left is None:
        return right
    if right is None:
        return left
    return (left[0] + right[0], left[1] + right[1], left[2] + right[2])


def object_name(data: Any) -> str:
    return getattr(data, "m_Name", "") or getattr(data, "name", "") or ""


def read_objects(env: Any) -> dict[ObjectKey, Any]:
    objects = {}
    for obj in env.objects:
        try:
            objects[object_key(obj)] = obj.read()
        except Exception:
            continue
    return objects


def build_scene_indexes(env: Any, objects: dict[int, Any]):
    types = {object_key(obj): obj.type.name for obj in env.objects}
    scripts = {}
    game_objects = {}
    transforms = {}
    transform_by_go = {}
    colliders_by_go: dict[int, list[tuple[int, str, Any]]] = {}
    mono_by_go: dict[int, list[tuple[int, str, Any]]] = {}

    for key, data in objects.items():
        type_name = types.get(key)
        if type_name == "MonoScript":
            scripts[key] = getattr(data, "m_ClassName", "") or object_name(data) or str(key[1])
        elif type_name == "GameObject":
            game_objects[key] = data
        elif type_name in {"Transform", "RectTransform"}:
            transforms[key] = data
            go_key = ref_key(getattr(data, "m_GameObject", None))
            if go_key:
                transform_by_go[go_key] = key

    for key, data in objects.items():
        type_name = types.get(key)
        go_key = ref_key(getattr(data, "m_GameObject", None))
        if not go_key:
            continue
        if type_name in {"BoxCollider", "MeshCollider", "SphereCollider", "CapsuleCollider"}:
            colliders_by_go.setdefault(go_key, []).append((key, type_name, data))
        elif type_name == "MonoBehaviour":
            script_ref = getattr(data, "m_Script", None)
            script_key = ref_key(script_ref)
            script_id = script_key[1] if script_key else pptr_id(getattr(data, "m_Script", None))
            script_name = scripts.get(script_key)
            if not script_name and script_ref is not None:
                try:
                    script_data = script_ref.read()
                    script_name = getattr(script_data, "m_ClassName", "") or object_name(script_data)
                except Exception:
                    script_name = None
            mono_by_go.setdefault(go_key, []).append((key, script_name or f"script:{script_id}", data))

    return types, game_objects, transforms, transform_by_go, colliders_by_go, mono_by_go


def transform_path(go_key: ObjectKey, game_objects: dict[ObjectKey, Any], transforms: dict[ObjectKey, Any], transform_by_go: dict[ObjectKey, ObjectKey]) -> str:
    names = []
    transform_key = transform_by_go.get(go_key)
    seen = set()
    while transform_key and transform_key not in seen:
        seen.add(transform_key)
        transform = transforms.get(transform_key)
        if transform is None:
            break
        current_go_key = ref_key(getattr(transform, "m_GameObject", None))
        if current_go_key:
            names.append(object_name(game_objects.get(current_go_key, "")) or str(current_go_key[1]))
        transform_key = ref_key(getattr(transform, "m_Father", None))
    return "/".join(reversed(names))


def world_position(go_key: ObjectKey, transforms: dict[ObjectKey, Any], transform_by_go: dict[ObjectKey, ObjectKey]) -> tuple[float, float, float] | None:
    total = None
    transform_key = transform_by_go.get(go_key)
    seen = set()
    while transform_key and transform_key not in seen:
        seen.add(transform_key)
        transform = transforms.get(transform_key)
        if transform is None:
            break
        total = add_vec3(vec3(getattr(transform, "m_LocalPosition", None)), total)
        transform_key = ref_key(getattr(transform, "m_Father", None))
    return total


def int3_text(value: Any) -> str:
    if value is None:
        return ""
    if all(hasattr(value, attr) for attr in ("x", "y", "z")):
        return f"{value.x},{value.y},{value.z}"
    return repr(value)


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract grid/block-like layout markers from one battle map bundle.")
    parser.add_argument("--bundle", type=Path, required=True, help="Full path or path relative to the game assets folder.")
    args = parser.parse_args()

    bundle = resolve_asset_path(args.bundle)
    env = UnityPy.load(str(bundle))
    objects = read_objects(env)
    _, game_objects, transforms, transform_by_go, colliders_by_go, mono_by_go = build_scene_indexes(env, objects)

    block_rows = []
    metadata = []
    block_type_counts: Counter[str] = Counter()

    for go_key, behaviours in mono_by_go.items():
        go = game_objects.get(go_key)
        name = object_name(go)
        path = transform_path(go_key, game_objects, transforms, transform_by_go)
        local_pos = None
        transform_key = transform_by_go.get(go_key)
        if transform_key:
            local_pos = vec3(getattr(transforms.get(transform_key), "m_LocalPosition", None))

        block_behaviours = [(mono_id, data) for mono_id, script, data in behaviours if script == "BlockProperty"]
        if block_behaviours:
            collider = (colliders_by_go.get(go_key) or [(None, "", None)])[0]
            collider_data = collider[2]
            for mono_key, data in block_behaviours:
                block_type = str(getattr(data, "type", ""))
                block_type_counts[block_type] += 1
                block_rows.append(
                    {
                        "bundle": rel(bundle),
                        "game_object_id": go_key[1],
                        "mono_id": mono_key[1],
                        "path": path,
                        "name": name,
                        "layer": getattr(go, "m_Layer", ""),
                        "local_position": vec3_text(local_pos),
                        "world_position": vec3_text(world_position(go_key, transforms, transform_by_go)),
                        "block_type": block_type,
                        "is_gamepad_cursor_movable": getattr(data, "isGamepadCursorMovable", ""),
                        "collider_type": collider[1],
                        "is_trigger": getattr(collider_data, "m_IsTrigger", "") if collider_data else "",
                        "collider_center": vec3_text(vec3(getattr(collider_data, "m_Center", None))) if collider_data else "",
                        "collider_size": vec3_text(vec3(getattr(collider_data, "m_Size", None))) if collider_data else "",
                    }
                )

        for mono_key, script, data in behaviours:
            if script in {"MapProperty", "MapTool", "BattleGrassData"}:
                fields = flatten_value(data, max_depth=5)
                if script == "BattleGrassData" and isinstance(fields, dict) and isinstance(fields.get("infos"), list):
                    fields["infos_count"] = len(fields["infos"])
                    fields["infos"] = fields["infos"][:10]
                metadata.append(
                    {
                        "script": script,
                        "mono_id": mono_key[1],
                        "game_object_id": go_key[1],
                        "path": path,
                        "fields": fields,
                    }
                )

    reports = ensure_reports()
    stem = safe_name(bundle.stem)
    write_csv(
        reports / f"{stem}_grid_blocks.csv",
        block_rows,
        [
            "bundle",
            "game_object_id",
            "mono_id",
            "path",
            "name",
            "layer",
            "local_position",
            "world_position",
            "block_type",
            "is_gamepad_cursor_movable",
            "collider_type",
            "is_trigger",
            "collider_center",
            "collider_size",
        ],
    )
    write_csv(
        reports / f"{stem}_block_type_counts.csv",
        [{"block_type": key, "count": value} for key, value in block_type_counts.most_common()],
        ["block_type", "count"],
    )
    write_json(
        reports / f"{stem}_map_metadata.json",
        {
            "bundle": rel(bundle),
            "resolved_bundle": str(bundle),
            "block_count": len(block_rows),
            "block_type_counts": dict(block_type_counts.most_common()),
            "metadata": metadata,
        },
    )
    print(f"Wrote grid reports for {bundle}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
