from __future__ import annotations

import argparse
import re
from pathlib import Path


def safe_name(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._") or "unnamed"


def main() -> int:
    parser = argparse.ArgumentParser(description="Dump TextAsset payloads from Unity bundles.")
    parser.add_argument("source", type=Path)
    parser.add_argument("--out", type=Path, default=Path("extracted/unity_textassets"))
    parser.add_argument("--contains", default="")
    args = parser.parse_args()

    try:
        import UnityPy  # type: ignore
    except ImportError as exc:
        raise SystemExit("UnityPy is required.") from exc

    env = UnityPy.load(str(args.source))
    out = args.out.resolve()
    count = 0
    for obj in env.objects:
        if obj.type.name != "TextAsset":
            continue
        data = obj.read()
        name = safe_name(getattr(data, "m_Name", "") or getattr(data, "name", f"TextAsset_{obj.path_id}"))
        raw_script = getattr(data, "m_Script", b"") or getattr(data, "script", b"")
        if isinstance(raw_script, str):
            script = raw_script.encode("utf-8", "surrogateescape")
        else:
            script = bytes(raw_script)
        if args.contains and args.contains.lower().encode() not in script.lower() and args.contains.lower() not in name.lower():
            continue
        dest = out / f"{safe_name(args.source.stem)}__{name}__{obj.path_id}.bytes"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(script)
        print(dest)
        count += 1
    print(f"Dumped: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
