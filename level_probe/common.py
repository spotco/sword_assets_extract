from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any


GAME_ROOT = Path(r"C:\Program Files (x86)\Steam\steamapps\common\Sword of Convallaria")
ASSETS_ROOT = GAME_ROOT / "assets"
REPORTS = Path("level_probe/reports")


LEVEL_PATTERNS = [
    "battle/map",
    "scenario",
    "scenario/scene",
    "scene",
    "capital/map",
    "capital/setting_group",
    "dreamlands/map",
    "dreamlands/prefab",
    "minisandbox/map",
    "worldboss/map",
    "infinitechallenge/map",
]


def ensure_reports() -> Path:
    REPORTS.mkdir(parents=True, exist_ok=True)
    return REPORTS


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ASSETS_ROOT)).replace("\\", "/")
    except ValueError:
        return str(path)


def safe_name(text: str) -> str:
    text = re.sub(r"[^A-Za-z0-9._-]+", "_", text)
    return text.strip("._") or "unnamed"


def resolve_asset_path(path: Path) -> Path:
    if path.exists():
        return path
    normalized = Path(str(path).replace("/", "\\"))
    if str(normalized).lower().startswith("assets\\"):
        candidate = GAME_ROOT / normalized
    else:
        candidate = ASSETS_ROOT / normalized
    return candidate


def iter_unity_bundles(patterns: list[str] | None = None):
    patterns = patterns or LEVEL_PATTERNS
    lowered = [item.lower().replace("\\", "/") for item in patterns]
    for path in ASSETS_ROOT.rglob("*.unity3d"):
        relative = rel(path).lower()
        if any(relative.startswith(pattern) or f"/{pattern}" in relative for pattern in lowered):
            yield path


def flatten_value(value: Any, max_depth: int = 4):
    if max_depth <= 0:
        return repr(value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, bytes):
        return f"<bytes:{len(value)}>"
    if isinstance(value, (list, tuple)):
        return [flatten_value(item, max_depth - 1) for item in value[:20]]
    if isinstance(value, dict):
        return {str(k): flatten_value(v, max_depth - 1) for k, v in list(value.items())[:40]}
    if hasattr(value, "__dict__"):
        return {
            str(k): flatten_value(v, max_depth - 1)
            for k, v in list(value.__dict__.items())[:40]
            if not str(k).startswith("_") and str(k) != "object_reader"
        }
    return repr(value)


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
