from __future__ import annotations

import argparse
from collections import Counter

import UnityPy

from common import ensure_reports, iter_unity_bundles, rel, write_csv


def main() -> int:
    parser = argparse.ArgumentParser(description="Count Unity object types in likely level bundles.")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--pattern", action="append", default=[])
    args = parser.parse_args()

    bundles = list(iter_unity_bundles(args.pattern or None))
    if args.limit:
        bundles = bundles[: args.limit]

    rows = []
    for index, bundle in enumerate(bundles, start=1):
        try:
            env = UnityPy.load(str(bundle))
            counts = Counter(obj.type.name for obj in env.objects)
        except Exception as exc:
            rows.append({"bundle": rel(bundle), "type": "<load_error>", "count": 0, "error": str(exc)})
            continue
        for type_name, count in counts.most_common():
            rows.append({"bundle": rel(bundle), "type": type_name, "count": count, "error": ""})
        if index % 50 == 0:
            print(f"Processed {index}/{len(bundles)}")

    reports = ensure_reports()
    write_csv(reports / "bundle_object_inventory.csv", rows, ["bundle", "type", "count", "error"])
    print(f"Wrote {reports / 'bundle_object_inventory.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

