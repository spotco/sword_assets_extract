from __future__ import annotations

import argparse
import re
from pathlib import Path

import UnityPy

from common import ASSETS_ROOT, ensure_reports, rel, write_csv


DEFAULT_BUNDLES = [
    "asset_bundle.unity3d",
    "asset_dep.unity3d",
    "db_template.unity3d",
    "asset_not_bundle.unity3d",
    "game_conf.unity3d",
]


def get_textasset_bytes(data) -> bytes:
    raw = getattr(data, "m_Script", b"") or getattr(data, "script", b"")
    if isinstance(raw, str):
        return raw.encode("utf-8", "ignore")
    return bytes(raw)


def main() -> int:
    parser = argparse.ArgumentParser(description="Search Unity TextAssets and db_lua.bytes for map/stage/layout terms.")
    parser.add_argument("--terms", nargs="+", default=["stage", "map", "grid", "spawn", "birth", "terrain", "walk", "obstacle", "mission"])
    parser.add_argument("--bundle", action="append", default=[])
    args = parser.parse_args()

    bundles = [ASSETS_ROOT / item for item in (args.bundle or DEFAULT_BUNDLES)]
    rows = []
    term_re = re.compile("|".join(re.escape(term) for term in args.terms), re.IGNORECASE)

    for bundle in bundles:
        if not bundle.exists():
            continue
        try:
            env = UnityPy.load(str(bundle))
        except Exception as exc:
            rows.append({"source": rel(bundle), "asset": "<load_error>", "term": "", "context": str(exc)})
            continue
        for obj in env.objects:
            if obj.type.name != "TextAsset":
                continue
            try:
                data = obj.read()
            except Exception:
                continue
            name = getattr(data, "m_Name", "") or f"TextAsset_{obj.path_id}"
            text = get_textasset_bytes(data).decode("utf-8", "ignore")
            for match in term_re.finditer(text):
                start = max(0, match.start() - 80)
                end = min(len(text), match.end() + 160)
                rows.append(
                    {
                        "source": rel(bundle),
                        "asset": name,
                        "term": match.group(0),
                        "context": text[start:end].replace("\n", "\\n").replace("\r", ""),
                    }
                )
                if len(rows) > 20000:
                    break

    db_lua = ASSETS_ROOT / "db_lua.bytes"
    if db_lua.exists():
        text = db_lua.read_bytes().decode("utf-8", "ignore")
        for match in term_re.finditer(text):
            start = max(0, match.start() - 80)
            end = min(len(text), match.end() + 160)
            rows.append({"source": "db_lua.bytes", "asset": "db_lua", "term": match.group(0), "context": text[start:end].replace("\n", "\\n").replace("\r", "")})

    reports = ensure_reports()
    write_csv(reports / "level_textasset_search.csv", rows, ["source", "asset", "term", "context"])
    print(f"Wrote {reports / 'level_textasset_search.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

