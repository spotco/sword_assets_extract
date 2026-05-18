from __future__ import annotations

from pathlib import Path
from typing import Any

import UnityPy

Vec3 = tuple[float, float, float]
ObjectKey = tuple[int, int]
ExportFrame = dict[str, Vec3]


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


def vec3_dict(value: Any) -> dict[str, float] | None:
    if value is None or not all(hasattr(value, attr) for attr in ("x", "y", "z")):
        return None
    return {"x": float(value.x), "y": float(value.y), "z": float(value.z)}


def quat_dict(value: Any) -> dict[str, float] | None:
    if value is None or not all(hasattr(value, attr) for attr in ("x", "y", "z", "w")):
        return None
    return {"x": float(value.x), "y": float(value.y), "z": float(value.z), "w": float(value.w)}


def round_float(value: float) -> float:
    return round(float(value), 6)


def round_vec3_dict(value: Vec3) -> dict[str, float]:
    return {"x": round_float(value[0]), "y": round_float(value[1]), "z": round_float(value[2])}


def vec3_tuple_from_dict(value: dict[str, float] | None) -> Vec3 | None:
    if value is None:
        return None
    try:
        return (float(value["x"]), float(value["y"]), float(value["z"]))
    except (KeyError, TypeError, ValueError):
        return None


def rotate_quat(q: dict[str, float], vec: Vec3) -> dict[str, float]:
    x, y, z, w = q["x"], q["y"], q["z"], q["w"]
    xx, yy, zz = x * x, y * y, z * z
    xy, xz, yz = x * y, x * z, y * z
    wx, wy, wz = w * x, w * y, w * z
    matrix = [
        [1 - 2 * (yy + zz), 2 * (xy - wz), 2 * (xz + wy)],
        [2 * (xy + wz), 1 - 2 * (xx + zz), 2 * (yz - wx)],
        [2 * (xz - wy), 2 * (yz + wx), 1 - 2 * (xx + yy)],
    ]
    return {
        "x": sum(matrix[0][i] * vec[i] for i in range(3)),
        "y": sum(matrix[1][i] * vec[i] for i in range(3)),
        "z": sum(matrix[2][i] * vec[i] for i in range(3)),
    }


def dot(left: Vec3, right: Vec3) -> float:
    return left[0] * right[0] + left[1] * right[1] + left[2] * right[2]


def cross(left: Vec3, right: Vec3) -> Vec3:
    return (
        left[1] * right[2] - left[2] * right[1],
        left[2] * right[0] - left[0] * right[2],
        left[0] * right[1] - left[1] * right[0],
    )


def negate(value: Vec3) -> Vec3:
    return (-value[0], -value[1], -value[2])


def normalize(value: Vec3 | None) -> Vec3 | None:
    if value is None:
        return None
    length = dot(value, value) ** 0.5
    if length <= 1e-8:
        return None
    return (value[0] / length, value[1] / length, value[2] / length)


def transform_vec3(value: Vec3, frame: ExportFrame) -> Vec3:
    return (
        dot(value, frame["right"]),
        dot(value, frame["up"]),
        dot(value, frame["forward"]),
    )


def transform_vec3_dict(value: dict[str, float] | None, frame: ExportFrame | None) -> dict[str, float] | None:
    if value is None or frame is None:
        return value
    point = vec3_tuple_from_dict(value)
    if point is None:
        return value
    return round_vec3_dict(transform_vec3(point, frame))


def camera_from_bundle(bundle_path: Path) -> dict[str, Any] | None:
    try:
        env = UnityPy.load(str(bundle_path))
    except Exception:
        return None

    objects = {}
    types = {}
    for obj in env.objects:
        key = object_key(obj)
        types[key] = obj.type.name
        try:
            objects[key] = obj.read()
        except Exception:
            continue

    camera_key = None
    selected_from_map_property = False
    for key, data in objects.items():
        if types.get(key) != "MonoBehaviour" or not hasattr(data, "camera"):
            continue
        camera_key = ref_key(getattr(data, "camera", None))
        if camera_key:
            selected_from_map_property = True
            break
    if camera_key is None:
        for key, type_name in types.items():
            if type_name == "Camera":
                camera_key = key
                break
    if camera_key is None:
        return None

    camera = objects.get(camera_key)
    go_key = ref_key(getattr(camera, "m_GameObject", None))
    transform = None
    transform_key = None
    for key, data in objects.items():
        if types.get(key) in {"Transform", "RectTransform"} and ref_key(getattr(data, "m_GameObject", None)) == go_key:
            transform = data
            transform_key = key
            break
    if transform is None:
        return None

    position = vec3_dict(getattr(transform, "m_LocalPosition", None))
    rotation = quat_dict(getattr(transform, "m_LocalRotation", None))
    if position is None or rotation is None:
        return None

    forward = rotate_quat(rotation, (0.0, 0.0, 1.0))
    right = rotate_quat(rotation, (1.0, 0.0, 0.0))
    up = rotate_quat(rotation, (0.0, 1.0, 0.0))
    return {
        "source": "MapProperty.camera" if selected_from_map_property else "Camera",
        "cameraId": str(camera_key[1]),
        "gameObjectId": str(go_key[1]) if go_key else "",
        "transformId": str(transform_key[1]) if transform_key else "",
        "position": position,
        "rotation": rotation,
        "forward": forward,
        "right": right,
        "up": up,
        "orthographic": bool(getattr(camera, "orthographic", False)),
        "orthographicSize": float(getattr(camera, "orthographic_size", 0.0) or 0.0),
        "fieldOfView": float(getattr(camera, "field_of_view", 0.0) or 0.0),
    }


def build_export_frame(camera: dict[str, Any] | None) -> ExportFrame | None:
    if camera is None:
        return None
    raw_forward = normalize(vec3_tuple_from_dict(camera.get("forward")))
    raw_up = normalize(vec3_tuple_from_dict(camera.get("up")))
    raw_right = normalize(vec3_tuple_from_dict(camera.get("right")))
    if raw_forward is None or raw_up is None:
        return None

    right = normalize(cross(raw_up, raw_forward))
    if right is None:
        right = raw_right
    if right is None:
        return None
    if raw_right is not None and dot(right, raw_right) < 0:
        right = negate(right)

    up = normalize(cross(raw_forward, right))
    if up is None:
        return None
    if dot(up, raw_up) < 0:
        right = negate(right)
        up = negate(up)

    # The previous viewer mirrored the orthographic X projection to match the
    # in-game view. Negate the export X axis here so the data itself carries
    # that handedness correction and the viewport can stay non-mirrored.
    right = negate(right)

    return {
        "right": right,
        "up": up,
        "forward": raw_forward,
    }


def transform_camera(camera: dict[str, Any], frame: ExportFrame | None) -> dict[str, Any]:
    if frame is None:
        return camera
    transformed = dict(camera)
    transformed["position"] = transform_vec3_dict(camera.get("position"), frame)
    transformed["rotation"] = {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0}
    transformed["right"] = {"x": 1.0, "y": 0.0, "z": 0.0}
    transformed["up"] = {"x": 0.0, "y": 1.0, "z": 0.0}
    transformed["forward"] = {"x": 0.0, "y": 0.0, "z": 1.0}
    return transformed


def describe_export_frame(frame: ExportFrame | None) -> dict[str, Any] | None:
    if frame is None:
        return None
    return {
        "type": "camera_aligned_world",
        "pointFormula": "export = (dot(world,right), dot(world,up), dot(world,forward))",
        "basis": {
            "right": round_vec3_dict(frame["right"]),
            "up": round_vec3_dict(frame["up"]),
            "forward": round_vec3_dict(frame["forward"]),
        },
    }
