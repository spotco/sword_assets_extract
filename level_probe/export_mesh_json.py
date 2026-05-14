from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path
from typing import Any

import UnityPy
from UnityPy.helpers.MeshHelper import MeshHandler

from common import rel, resolve_asset_path, safe_name, write_json


OUT_ROOT = Path("extracted/web_levels")

ObjectKey = tuple[int, int]
Vec3 = tuple[float, float, float]
Mat4 = list[list[float]]


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


def object_name(data: Any) -> str:
    return getattr(data, "m_Name", "") or getattr(data, "name", "") or ""


def vec3(value: Any, default: Vec3 = (0.0, 0.0, 0.0)) -> Vec3:
    if value is None:
        return default
    if all(hasattr(value, attr) for attr in ("x", "y", "z")):
        return (float(value.x), float(value.y), float(value.z))
    return default


def quat(value: Any) -> tuple[float, float, float, float]:
    if value is None:
        return (0.0, 0.0, 0.0, 1.0)
    if all(hasattr(value, attr) for attr in ("x", "y", "z", "w")):
        return (float(value.x), float(value.y), float(value.z), float(value.w))
    return (0.0, 0.0, 0.0, 1.0)


def identity() -> Mat4:
    return [
        [1.0, 0.0, 0.0, 0.0],
        [0.0, 1.0, 0.0, 0.0],
        [0.0, 0.0, 1.0, 0.0],
        [0.0, 0.0, 0.0, 1.0],
    ]


def mat_mul(left: Mat4, right: Mat4) -> Mat4:
    return [
        [sum(left[row][k] * right[k][col] for k in range(4)) for col in range(4)]
        for row in range(4)
    ]


def trs_matrix(position: Vec3, rotation: tuple[float, float, float, float], scale: Vec3) -> Mat4:
    x, y, z, w = rotation
    sx, sy, sz = scale
    xx, yy, zz = x * x, y * y, z * z
    xy, xz, yz = x * y, x * z, y * z
    wx, wy, wz = w * x, w * y, w * z

    return [
        [(1 - 2 * (yy + zz)) * sx, (2 * (xy - wz)) * sy, (2 * (xz + wy)) * sz, position[0]],
        [(2 * (xy + wz)) * sx, (1 - 2 * (xx + zz)) * sy, (2 * (yz - wx)) * sz, position[1]],
        [(2 * (xz - wy)) * sx, (2 * (yz + wx)) * sy, (1 - 2 * (xx + yy)) * sz, position[2]],
        [0.0, 0.0, 0.0, 1.0],
    ]


def transform_point(matrix: Mat4, point: Vec3) -> Vec3:
    x, y, z = point
    return (
        matrix[0][0] * x + matrix[0][1] * y + matrix[0][2] * z + matrix[0][3],
        matrix[1][0] * x + matrix[1][1] * y + matrix[1][2] * z + matrix[1][3],
        matrix[2][0] * x + matrix[2][1] * y + matrix[2][2] * z + matrix[2][3],
    )


def read_objects(env: Any) -> dict[ObjectKey, Any]:
    objects = {}
    for obj in env.objects:
        try:
            objects[object_key(obj)] = obj.read()
        except Exception:
            continue
    return objects


def build_indexes(env: Any, objects: dict[ObjectKey, Any]):
    types = {object_key(obj): obj.type.name for obj in env.objects}
    game_objects = {}
    transforms = {}
    transform_by_go = {}
    mesh_filters = {}
    mesh_renderers_by_go = {}

    for key, data in objects.items():
        type_name = types.get(key)
        if type_name == "GameObject":
            game_objects[key] = data
        elif type_name in {"Transform", "RectTransform"}:
            transforms[key] = data
            go_key = ref_key(getattr(data, "m_GameObject", None))
            if go_key:
                transform_by_go[go_key] = key
        elif type_name == "MeshFilter":
            go_key = ref_key(getattr(data, "m_GameObject", None))
            if go_key:
                mesh_filters[go_key] = (key, data)
        elif type_name == "MeshRenderer":
            go_key = ref_key(getattr(data, "m_GameObject", None))
            if go_key:
                mesh_renderers_by_go[go_key] = (key, data)

    return game_objects, transforms, transform_by_go, mesh_filters, mesh_renderers_by_go


def transform_path(
    go_key: ObjectKey,
    game_objects: dict[ObjectKey, Any],
    transforms: dict[ObjectKey, Any],
    transform_by_go: dict[ObjectKey, ObjectKey],
) -> str:
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


def world_matrix(
    go_key: ObjectKey,
    transforms: dict[ObjectKey, Any],
    transform_by_go: dict[ObjectKey, ObjectKey],
) -> Mat4:
    chain = []
    transform_key = transform_by_go.get(go_key)
    seen = set()
    while transform_key and transform_key not in seen:
        seen.add(transform_key)
        transform = transforms.get(transform_key)
        if transform is None:
            break
        chain.append(transform)
        transform_key = ref_key(getattr(transform, "m_Father", None))

    matrix = identity()
    for transform in reversed(chain):
        local = trs_matrix(
            vec3(getattr(transform, "m_LocalPosition", None)),
            quat(getattr(transform, "m_LocalRotation", None)),
            vec3(getattr(transform, "m_LocalScale", None), (1.0, 1.0, 1.0)),
        )
        matrix = mat_mul(matrix, local)
    return matrix


def round_vec3(point: Vec3) -> list[float]:
    return [round(point[0], 5), round(point[1], 5), round(point[2], 5)]


def export_mesh_instance(
    go_key: ObjectKey,
    mesh_filter_key: ObjectKey,
    mesh_filter: Any,
    renderer: Any,
    game_objects: dict[ObjectKey, Any],
    transforms: dict[ObjectKey, Any],
    transform_by_go: dict[ObjectKey, ObjectKey],
) -> dict[str, Any]:
    mesh_ref = getattr(mesh_filter, "m_Mesh", None)
    mesh = mesh_ref.read()
    handler = MeshHandler(mesh)
    handler.process()

    if handler.m_VertexCount <= 0 or not handler.m_Vertices:
        raise ValueError("mesh has no vertices")

    triangle_groups = handler.get_triangles()
    static_info = getattr(renderer, "m_StaticBatchInfo", None) if renderer else None
    static_first = int(getattr(static_info, "firstSubMesh", 0) or 0)
    static_count = int(getattr(static_info, "subMeshCount", 0) or 0)
    is_static_batch_slice = static_count > 0
    if is_static_batch_slice:
        selected_groups = triangle_groups[static_first : static_first + static_count]
        coordinate_space = "static_batch_world"
        matrix = identity()
    else:
        selected_groups = triangle_groups
        coordinate_space = "local_transformed_to_world"
        matrix = world_matrix(go_key, transforms, transform_by_go)

    if not selected_groups:
        raise ValueError("renderer has no selected submeshes")

    used_indices = sorted({int(index) for triangles in selected_groups for tri in triangles for index in tri})
    if not used_indices:
        raise ValueError("selected submeshes have no indices")

    remap = {old: new for new, old in enumerate(used_indices)}
    vertices = []
    for old_index in used_indices:
        point = handler.m_Vertices[old_index]
        vertices.extend(round_vec3(transform_point(matrix, (float(point[0]), float(point[1]), float(point[2])))))

    indices: list[int] = []
    submeshes = []
    offset = 0
    for selected_index, triangles in enumerate(selected_groups):
        submesh_index = static_first + selected_index if is_static_batch_slice else selected_index
        for a, b, c in triangles:
            indices.extend([remap[int(a)], remap[int(b)], remap[int(c)]])
        submeshes.append({"index": submesh_index, "triangleCount": len(triangles), "start": offset})
        offset += len(triangles) * 3

    go = game_objects.get(go_key)
    return {
        "id": str(go_key[1]),
        "name": object_name(go),
        "path": transform_path(go_key, game_objects, transforms, transform_by_go),
        "layer": getattr(go, "m_Layer", ""),
        "meshFilterId": str(mesh_filter_key[1]),
        "meshId": str(pptr_id(mesh_ref) or ""),
        "meshName": object_name(mesh),
        "coordinateSpace": coordinate_space,
        "staticBatch": {
            "firstSubMesh": static_first,
            "subMeshCount": static_count,
        },
        "rendererEnabled": getattr(renderer, "m_Enabled", "") if renderer else "",
        "sourceVertexCount": handler.m_VertexCount,
        "vertexCount": len(used_indices),
        "triangleCount": len(indices) // 3,
        "submeshes": submeshes,
        "vertices": vertices,
        "indices": indices,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Export readable MeshFilter geometry from one Unity map bundle to web JSON.")
    parser.add_argument("--map", dest="map_name", default="stage_city-ca-da00101", help="Map stem under assets/battle/map.")
    parser.add_argument("--bundle", type=Path, help="Full path or path relative to the game assets folder.")
    parser.add_argument("--out-root", type=Path, default=OUT_ROOT, help="Output root for web level folders.")
    parser.add_argument("--visible-only", action="store_true", help="Skip MeshFilter objects without an enabled MeshRenderer.")
    args = parser.parse_args()

    map_name = safe_name(args.map_name)
    bundle = resolve_asset_path(args.bundle or Path("battle/map") / f"{map_name}.unity3d")

    env = UnityPy.load(str(bundle))
    objects = read_objects(env)
    game_objects, transforms, transform_by_go, mesh_filters, mesh_renderers_by_go = build_indexes(env, objects)

    instances = []
    skipped = []
    skipped_reasons: Counter[str] = Counter()
    for go_key, (mesh_filter_key, mesh_filter) in mesh_filters.items():
        renderer_pair = mesh_renderers_by_go.get(go_key)
        renderer = renderer_pair[1] if renderer_pair else None
        if args.visible_only and (renderer is None or not getattr(renderer, "m_Enabled", False)):
            skipped_reasons["no_enabled_renderer"] += 1
            continue
        try:
            instances.append(
                export_mesh_instance(
                    go_key,
                    mesh_filter_key,
                    mesh_filter,
                    renderer,
                    game_objects,
                    transforms,
                    transform_by_go,
                )
            )
        except Exception as exc:
            reason = type(exc).__name__
            skipped_reasons[reason] += 1
            mesh_ref = getattr(mesh_filter, "m_Mesh", None)
            skipped.append(
                {
                    "gameObjectId": str(go_key[1]),
                    "path": transform_path(go_key, game_objects, transforms, transform_by_go),
                    "meshId": str(pptr_id(mesh_ref) or ""),
                    "reason": reason,
                    "detail": str(exc),
                }
            )

    payload = {
        "schemaVersion": 1,
        "mapName": map_name,
        "source": {"bundle": rel(bundle), "resolvedBundle": str(bundle)},
        "stats": {
            "meshFilterCount": len(mesh_filters),
            "meshInstanceCount": len(instances),
            "skippedCount": len(skipped),
            "skippedReasons": dict(skipped_reasons.most_common()),
            "vertexCount": sum(item["vertexCount"] for item in instances),
            "triangleCount": sum(item["triangleCount"] for item in instances),
        },
        "instances": instances,
        "skipped": skipped[:100],
    }

    out_dir = args.out_root / map_name
    write_json(out_dir / "meshes.json", payload)
    print(
        f"Wrote {out_dir / 'meshes.json'} with {payload['stats']['meshInstanceCount']} readable "
        f"mesh instances, {payload['stats']['triangleCount']} triangles, "
        f"{payload['stats']['skippedCount']} skipped"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
