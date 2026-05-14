from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

import UnityPy
from UnityPy.helpers.MeshHelper import MeshHandler

from common import ASSETS_ROOT, rel, resolve_asset_path, safe_name, write_json
from export_level_index import build_index


OUT_ROOT = Path("extracted/web_levels")
ASSET_DEP_BUNDLE = ASSETS_ROOT / "asset_dep.unity3d"

MAIN_TEX_SLOTS = {"_MainTex", "_BaseMap", "_AlbedoMap", "_DiffuseMap"}

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


def save_texture_png(path_id: str, tex_data: Any, textures_dir: Path) -> dict[str, Any] | None:
    raw_name = object_name(tex_data)
    file_stem = safe_name(raw_name or "tex")
    file_name = f"{path_id}_{file_stem}.png"
    file_path = textures_dir / file_name
    width = int(getattr(tex_data, "m_Width", 0) or 0)
    height = int(getattr(tex_data, "m_Height", 0) or 0)

    if not file_path.exists():
        try:
            image = tex_data.image
            if image is None:
                return None
            textures_dir.mkdir(parents=True, exist_ok=True)
            image.save(str(file_path))
        except Exception:
            return None

    return {
        "id": path_id,
        "name": raw_name,
        "path": f"textures/{file_name}",
        "width": width,
        "height": height,
    }


def build_materials_payload(
    map_name: str,
    instances: list[dict[str, Any]],
    objects: dict[ObjectKey, Any],
    types: dict[ObjectKey, str],
    out_dir: Path,
) -> dict[str, Any]:
    mat_by_path_id: dict[str, tuple[ObjectKey, Any]] = {}
    for key, data in objects.items():
        if types.get(key) == "Material":
            pid = str(key[1])
            if pid not in mat_by_path_id:
                mat_by_path_id[pid] = (key, data)

    referenced_ids = {mid for inst in instances for mid in inst.get("materialIds", [])}

    textures_dir = out_dir / "textures"
    exported_textures: dict[str, dict[str, Any]] = {}
    skipped_textures = 0
    materials = []

    for mat_id in sorted(referenced_ids):
        entry = mat_by_path_id.get(mat_id)
        if entry is None:
            continue
        _mat_key, mat_data = entry

        shader_ref = getattr(mat_data, "m_Shader", None)
        shader_name = ""
        if shader_ref is not None:
            try:
                shader_obj = shader_ref.read()
                shader_name = object_name(shader_obj)
            except Exception:
                pass

        saved = getattr(mat_data, "m_SavedProperties", None)
        tex_envs = getattr(saved, "m_TexEnvs", []) if saved else []
        colors_raw = getattr(saved, "m_Colors", []) if saved else []

        main_texture: dict[str, Any] | None = None
        all_textures: dict[str, Any] = {}
        for item in tex_envs:
            if not (isinstance(item, (list, tuple)) and len(item) == 2):
                continue
            slot, tex_env = item
            tex_pptr = getattr(tex_env, "m_Texture", None)
            if tex_pptr is None or getattr(tex_pptr, "m_PathID", 0) == 0:
                continue
            tex_id = str(tex_pptr.m_PathID)
            if tex_id not in exported_textures:
                try:
                    tex_data = tex_pptr.read()
                    record = save_texture_png(tex_id, tex_data, textures_dir)
                    if record:
                        exported_textures[tex_id] = record
                    else:
                        skipped_textures += 1
                except Exception:
                    skipped_textures += 1
            tex_record = exported_textures.get(tex_id)
            if tex_record:
                all_textures[str(slot)] = tex_record
                if str(slot) in MAIN_TEX_SLOTS and main_texture is None:
                    main_texture = tex_record

        colors: dict[str, list[float]] = {}
        for item in colors_raw:
            if isinstance(item, (list, tuple)) and len(item) == 2:
                slot, color = item
                if all(hasattr(color, attr) for attr in ("r", "g", "b", "a")):
                    colors[str(slot)] = [
                        round(float(color.r), 4),
                        round(float(color.g), 4),
                        round(float(color.b), 4),
                        round(float(color.a), 4),
                    ]

        materials.append({
            "id": mat_id,
            "name": object_name(mat_data),
            "shader": shader_name,
            "mainTexture": main_texture,
            "textures": all_textures,
            "colors": colors,
        })

    return {
        "schemaVersion": 1,
        "mapName": map_name,
        "stats": {
            "materialCount": len(materials),
            "textureCount": len(exported_textures),
            "skippedTextureCount": skipped_textures,
        },
        "materials": materials,
    }


def asset_file_names(bundle: Path) -> set[str]:
    env = UnityPy.load(str(bundle))
    return {asset.name for asset in env.assets}


def load_asset_dependency_table() -> dict[str, list[str]]:
    if not ASSET_DEP_BUNDLE.exists():
        return {}
    env = UnityPy.load(str(ASSET_DEP_BUNDLE))
    for obj in env.objects:
        if obj.type.name != "TextAsset":
            continue
        data = obj.read()
        if getattr(data, "m_Name", "") == "asset_dep":
            return json.loads(data.m_Script)
    return {}


def dependency_paths(bundle: Path) -> list[Path]:
    key = rel(bundle)
    if key.lower().endswith(".unity3d"):
        key = key[:-8]
    deps = load_asset_dependency_table().get(key, [])
    paths = []
    for dep in deps:
        path = ASSETS_ROOT / f"{dep}.unity3d"
        if path.exists():
            paths.append(path)
    return paths


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
    uvs: list[float] = []
    raw_uvs = handler.m_UV0 or []
    has_uvs = len(raw_uvs) >= handler.m_VertexCount
    for old_index in used_indices:
        point = handler.m_Vertices[old_index]
        vertices.extend(round_vec3(transform_point(matrix, (float(point[0]), float(point[1]), float(point[2])))))
        if has_uvs:
            uv = raw_uvs[old_index]
            uvs.extend([round(float(uv[0]), 5), round(float(uv[1]), 5)])

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
        "materialIds": [
            str(pptr_id(pptr))
            for pptr in (getattr(renderer, "m_Materials", []) or [])
            if pptr_id(pptr) is not None
        ] if renderer else [],
        "sourceVertexCount": handler.m_VertexCount,
        "vertexCount": len(used_indices),
        "triangleCount": len(indices) // 3,
        "submeshes": submeshes,
        "vertices": vertices,
        "uvs": uvs,
        "indices": indices,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Export readable MeshFilter geometry from one Unity map bundle to web JSON.")
    parser.add_argument("--map", dest="map_name", default="stage_city-ca-da00101", help="Map stem under assets/battle/map.")
    parser.add_argument("--bundle", type=Path, help="Full path or path relative to the game assets folder.")
    parser.add_argument("--out-root", type=Path, default=OUT_ROOT, help="Output root for web level folders.")
    parser.add_argument("--visible-only", action="store_true", help="Skip MeshFilter objects without an enabled MeshRenderer.")
    parser.add_argument("--no-dependencies", action="store_true", help="Do not load dependency bundles from asset_dep.unity3d.")
    args = parser.parse_args()

    map_name = safe_name(args.map_name)
    bundle = resolve_asset_path(args.bundle or Path("battle/map") / f"{map_name}.unity3d")

    main_asset_names = asset_file_names(bundle)
    deps = [] if args.no_dependencies else dependency_paths(bundle)
    env = UnityPy.load(*[str(path) for path in [bundle, *deps]])
    target_asset_ids = {id(asset) for asset in env.assets if asset.name in main_asset_names}
    objects = read_objects(env)
    types = {object_key(obj): obj.type.name for obj in env.objects}
    game_objects, transforms, transform_by_go, mesh_filters, mesh_renderers_by_go = build_indexes(env, objects)

    instances = []
    skipped = []
    skipped_reasons: Counter[str] = Counter()
    for go_key, (mesh_filter_key, mesh_filter) in mesh_filters.items():
        if mesh_filter_key[0] not in target_asset_ids:
            continue
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
        "source": {
            "bundle": rel(bundle),
            "resolvedBundle": str(bundle),
            "dependencyBundles": [rel(path) for path in deps],
        },
        "stats": {
            "meshFilterCount": len([key for key in mesh_filters if key[0] in target_asset_ids]),
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
    write_json(args.out_root / "index.json", build_index(args.out_root))
    print(
        f"Wrote {out_dir / 'meshes.json'} with {payload['stats']['meshInstanceCount']} readable "
        f"mesh instances, {payload['stats']['triangleCount']} triangles, "
        f"{payload['stats']['skippedCount']} skipped"
    )
    print(f"Updated {args.out_root / 'index.json'}")

    materials_payload = build_materials_payload(map_name, instances, objects, types, out_dir)
    write_json(out_dir / "materials.json", materials_payload)
    print(
        f"Wrote {out_dir / 'materials.json'} with {materials_payload['stats']['materialCount']} materials, "
        f"{materials_payload['stats']['textureCount']} textures "
        f"({materials_payload['stats']['skippedTextureCount']} skipped)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
