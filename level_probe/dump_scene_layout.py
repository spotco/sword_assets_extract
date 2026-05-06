from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import UnityPy

from common import ensure_reports, rel, resolve_asset_path, safe_name, write_csv, write_json


def vec3(value: Any) -> str:
    if value is None:
        return ""
    attrs = ["x", "y", "z"]
    if all(hasattr(value, attr) for attr in attrs):
        return ",".join(str(getattr(value, attr)) for attr in attrs)
    return repr(value)


def get_name(obj_data: Any) -> str:
    return getattr(obj_data, "m_Name", "") or getattr(obj_data, "name", "")


def main() -> int:
    parser = argparse.ArgumentParser(description="Dump GameObject/Transform/collider hints from one Unity level bundle.")
    parser.add_argument("--bundle", type=Path, required=True)
    args = parser.parse_args()

    bundle = resolve_asset_path(args.bundle)
    env = UnityPy.load(str(bundle))
    objects: dict[int, Any] = {}
    rows = []
    collider_rows = []
    mono_rows = []

    for obj in env.objects:
        try:
            data = obj.read()
        except Exception:
            continue
        objects[obj.path_id] = data

    for obj in env.objects:
        try:
            data = objects.get(obj.path_id) or obj.read()
        except Exception:
            continue
        type_name = obj.type.name
        if type_name == "GameObject":
            rows.append(
                {
                    "path_id": obj.path_id,
                    "type": type_name,
                    "name": get_name(data),
                    "tag": getattr(data, "m_TagString", ""),
                    "layer": getattr(data, "m_Layer", ""),
                    "component_count": len(getattr(data, "m_Component", []) or []),
                }
            )
        elif type_name in {"Transform", "RectTransform"}:
            game_object = getattr(getattr(data, "m_GameObject", None), "path_id", "")
            rows.append(
                {
                    "path_id": obj.path_id,
                    "type": type_name,
                    "name": "",
                    "tag": "",
                    "layer": "",
                    "component_count": "",
                    "game_object": game_object,
                    "local_position": vec3(getattr(data, "m_LocalPosition", None)),
                    "local_scale": vec3(getattr(data, "m_LocalScale", None)),
                }
            )
        elif type_name in {"BoxCollider", "MeshCollider", "SphereCollider", "CapsuleCollider"}:
            collider_rows.append(
                {
                    "path_id": obj.path_id,
                    "type": type_name,
                    "game_object": getattr(getattr(data, "m_GameObject", None), "path_id", ""),
                    "enabled": getattr(data, "m_Enabled", ""),
                    "is_trigger": getattr(data, "m_IsTrigger", ""),
                    "center": vec3(getattr(data, "m_Center", None)),
                    "size": vec3(getattr(data, "m_Size", None)),
                }
            )
        elif type_name == "MonoBehaviour":
            script = getattr(data, "m_Script", None)
            mono_rows.append(
                {
                    "path_id": obj.path_id,
                    "game_object": getattr(getattr(data, "m_GameObject", None), "path_id", ""),
                    "script_path_id": getattr(script, "path_id", ""),
                    "name": get_name(data),
                    "enabled": getattr(data, "m_Enabled", ""),
                }
            )

    reports = ensure_reports()
    stem = safe_name(bundle.stem)
    write_csv(reports / f"{stem}_scene_objects.csv", rows, ["path_id", "type", "name", "tag", "layer", "component_count", "game_object", "local_position", "local_scale"])
    write_csv(reports / f"{stem}_colliders.csv", collider_rows, ["path_id", "type", "game_object", "enabled", "is_trigger", "center", "size"])
    write_csv(reports / f"{stem}_monobehaviours.csv", mono_rows, ["path_id", "game_object", "script_path_id", "name", "enabled"])
    write_json(
        reports / f"{stem}_summary.json",
        {
            "bundle": rel(bundle),
            "resolved_bundle": str(bundle),
            "game_objects": len([r for r in rows if r["type"] == "GameObject"]),
            "transforms": len([r for r in rows if r["type"] in {"Transform", "RectTransform"}]),
            "colliders": len(collider_rows),
            "monobehaviours": len(mono_rows),
        },
    )
    print(f"Wrote scene dumps for {bundle}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
