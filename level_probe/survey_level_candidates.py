from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from common import ASSETS_ROOT, LEVEL_PATTERNS, ensure_reports, rel, write_csv


def main() -> int:
    rows = []
    grouped: dict[str, dict[str, int]] = defaultdict(lambda: {"count": 0, "bytes": 0})
    for path in ASSETS_ROOT.rglob("*"):
        if not path.is_file():
            continue
        relative = rel(path)
        low = relative.lower()
        if not any(pattern in low for pattern in LEVEL_PATTERNS) and not any(
            word in low for word in ["map", "stage", "scene", "mission", "grid", "tile", "terrain"]
        ):
            continue
        stat = path.stat()
        parent = str(Path(relative).parent).replace("\\", "/")
        grouped[parent]["count"] += 1
        grouped[parent]["bytes"] += stat.st_size
        rows.append(
            {
                "relative_path": relative,
                "parent": parent,
                "extension": path.suffix.lower() or "<none>",
                "size": stat.st_size,
            }
        )

    reports = ensure_reports()
    write_csv(reports / "level_candidate_files.csv", rows, ["relative_path", "parent", "extension", "size"])
    summary = [
        {"parent": parent, "count": data["count"], "bytes": data["bytes"]}
        for parent, data in sorted(grouped.items(), key=lambda item: (-item[1]["count"], item[0]))
    ]
    write_csv(reports / "level_candidate_dirs.csv", summary, ["parent", "count", "bytes"])
    print(f"Wrote {reports / 'level_candidate_files.csv'}")
    print(f"Wrote {reports / 'level_candidate_dirs.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

