from __future__ import annotations

import argparse
from collections import Counter, defaultdict

import UnityPy

from pathlib import Path

from common import ensure_reports, flatten_value, iter_unity_bundles, rel, resolve_asset_path, write_csv, write_json


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarize MonoBehaviour scripts and field payloads in likely level bundles.")
    parser.add_argument("--bundle", action="append", type=Path, help="Specific bundle to inspect. Accepts full paths or paths relative to the assets folder.")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--pattern", action="append", default=["battle/map"])
    parser.add_argument("--dump-fields", action="store_true")
    args = parser.parse_args()

    if args.bundle:
        bundles = [resolve_asset_path(path) for path in args.bundle]
    else:
        bundles = list(iter_unity_bundles(args.pattern or None))
    if args.limit:
        bundles = bundles[: args.limit]

    script_counts: Counter[str] = Counter()
    rows = []
    field_dumps = []

    for bundle in bundles:
        try:
            env = UnityPy.load(str(bundle))
        except Exception as exc:
            rows.append({"bundle": rel(bundle), "script": "<load_error>", "count": 0, "error": str(exc)})
            continue
        scripts = {}
        for obj in env.objects:
            if obj.type.name == "MonoScript":
                try:
                    data = obj.read()
                    scripts[obj.path_id] = getattr(data, "m_ClassName", "") or getattr(data, "m_Name", "") or str(obj.path_id)
                except Exception:
                    scripts[obj.path_id] = str(obj.path_id)
        local_counts: Counter[str] = Counter()
        for obj in env.objects:
            if obj.type.name != "MonoBehaviour":
                continue
            try:
                data = obj.read()
            except Exception:
                continue
            script_ref = getattr(data, "m_Script", None)
            script_name = scripts.get(getattr(script_ref, "path_id", None), f"script:{getattr(script_ref, 'path_id', '')}")
            local_counts[script_name] += 1
            script_counts[script_name] += 1
            if args.dump_fields:
                field_dumps.append({"bundle": rel(bundle), "path_id": obj.path_id, "script": script_name, "fields": flatten_value(data)})
        for script_name, count in local_counts.most_common():
            rows.append({"bundle": rel(bundle), "script": script_name, "count": count, "error": ""})

    reports = ensure_reports()
    write_csv(reports / "monobehaviour_scripts_by_bundle.csv", rows, ["bundle", "script", "count", "error"])
    write_csv(
        reports / "monobehaviour_script_totals.csv",
        [{"script": script, "count": count} for script, count in script_counts.most_common()],
        ["script", "count"],
    )
    if args.dump_fields:
        write_json(reports / "monobehaviour_field_samples.json", field_dumps[:1000])
    print(f"Wrote MonoBehaviour reports to {reports}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
