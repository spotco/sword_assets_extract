from __future__ import annotations

import argparse
import csv
import json
import re
from collections import defaultdict, deque
from pathlib import Path


DEFAULT_GAME_ROOT = Path(r"C:\Program Files (x86)\Steam\steamapps\common\Sword of Convallaria")
DEFAULT_MANIFEST = Path("reports/asset_manifest.csv")
DEFAULT_EVENTS = Path("extracted/unity_textassets/bnk_events__bnk_events__1876318598449274942.bytes")
DEFAULT_OUT = Path("reports")
KEY = b"XD_Audio"


HIRC_TYPES = {
    2: "Sound",
    3: "Action",
    4: "Event",
}


def xor_data(data: bytes) -> bytes:
    return bytes(byte ^ KEY[index % len(KEY)] for index, byte in enumerate(data))


def decode_bank_if_needed(data: bytes) -> bytes:
    if data.startswith(b"BKHD"):
        return data
    decoded = xor_data(data)
    return decoded if decoded.startswith(b"BKHD") else data


def chunks(data: bytes):
    offset = 0
    while offset + 8 <= len(data):
        tag = data[offset : offset + 4]
        size = int.from_bytes(data[offset + 4 : offset + 8], "little")
        start = offset + 8
        end = start + size
        if end > len(data):
            break
        yield tag, data[start:end]
        offset = end


def hirc_objects(bank: bytes):
    for tag, payload in chunks(bank):
        if tag != b"HIRC" or len(payload) < 4:
            continue
        count = int.from_bytes(payload[:4], "little")
        pos = 4
        for _ in range(count):
            if pos + 9 > len(payload):
                break
            obj_type = payload[pos]
            size = int.from_bytes(payload[pos + 1 : pos + 5], "little")
            obj_start = pos + 5
            obj_end = obj_start + size
            if obj_end > len(payload) or size < 4:
                break
            obj_data = payload[obj_start:obj_end]
            obj_id = int.from_bytes(obj_data[:4], "little")
            yield obj_type, obj_id, obj_data
            pos = obj_end


def fnv1_32(text: str) -> int:
    value = 2166136261
    for byte in text.encode("utf-8"):
        value = (value * 16777619) & 0xFFFFFFFF
        value ^= byte
    return value


def load_event_names(path: Path) -> dict[int, set[str]]:
    data = json.loads(path.read_text("utf-8"))
    names: dict[int, set[str]] = defaultdict(set)
    for section in data.values():
        if not isinstance(section, dict):
            continue
        for name in section:
            names[fnv1_32(name)].add(name)
            names[fnv1_32(name.lower())].add(name)
    return names


def load_manifest(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def media_id_from_path(relative_path: str) -> int | None:
    stem = Path(relative_path).stem
    return int(stem) if stem.isdecimal() else None


def sanitize_title(text: str) -> str:
    text = text.strip().lower()
    text = re.sub(r"^play_", "", text)
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return re.sub(r"_+", "_", text).strip("_")


def group_event_names(names: set[str]) -> str:
    if not names:
        return ""

    sanitized = sorted({sanitize_title(name) for name in names if name})
    # Collapse common numbered variants such as online_93/94/98_amb_loop.
    tokenized = [item.split("_") for item in sanitized]
    lengths = {len(tokens) for tokens in tokenized}
    if len(lengths) == 1:
        length = lengths.pop()
        variable_indexes = []
        fixed: list[str | None] = []
        for index in range(length):
            values = {tokens[index] for tokens in tokenized}
            if len(values) == 1:
                fixed.append(next(iter(values)))
            else:
                fixed.append(None)
                variable_indexes.append(index)
        if len(variable_indexes) == 1:
            variable_index = variable_indexes[0]
            values = sorted({tokens[variable_index] for tokens in tokenized})
            collapsed = [part if part is not None else "_".join(values) for part in fixed]
            return "_".join(collapsed)

    if len(sanitized) <= 4:
        return "__".join(sanitized)

    common_prefix = re.sub(r"_+$", "", re.sub(r"[^_]+$", "", sanitized[0]))
    if common_prefix and all(item.startswith(common_prefix) for item in sanitized):
        return f"{common_prefix}multiple"
    return "__".join(sanitized[:4]) + "__multiple"


def build_media_event_map(game_root: Path, bank_paths: list[str], known_media_ids: set[int], event_names: dict[int, set[str]]):
    media_events: dict[int, set[str]] = defaultdict(set)
    media_banks: dict[int, set[str]] = defaultdict(set)
    media_object_types: dict[int, set[str]] = defaultdict(set)
    for index, rel_path in enumerate(bank_paths, start=1):
        bank_path = game_root / "assets" / rel_path
        try:
            bank = decode_bank_if_needed(bank_path.read_bytes())
        except OSError:
            continue

        objects = list(hirc_objects(bank))
        if not objects:
            continue

        obj_data_by_id: dict[int, bytes] = {}
        obj_type_by_id: dict[int, int] = {}
        reverse_refs: dict[int, set[int]] = defaultdict(set)
        event_ids = set()

        for obj_type, obj_id, obj_data in objects:
            obj_data_by_id[obj_id] = obj_data
            obj_type_by_id[obj_id] = obj_type
            if obj_type == 4:
                event_ids.add(obj_id)

        object_ids = set(obj_data_by_id)
        sound_media_ids: dict[int, set[int]] = defaultdict(set)
        for candidate_id, candidate_data in obj_data_by_id.items():
            data_len = len(candidate_data)
            for offset in range(0, data_len - 3):
                value = int.from_bytes(candidate_data[offset : offset + 4], "little")
                if value in object_ids and value != candidate_id:
                    reverse_refs[value].add(candidate_id)
                if obj_type_by_id.get(candidate_id) == 2 and value in known_media_ids:
                    sound_media_ids[candidate_id].add(value)

        for sound_id, found_media_ids in sound_media_ids.items():
            queue = deque([sound_id])
            seen = {sound_id}
            found_events: set[str] = set()
            while queue:
                current = queue.popleft()
                for parent in reverse_refs.get(current, set()):
                    if parent in seen:
                        continue
                    seen.add(parent)
                    if parent in event_ids:
                        found_events.update(event_names.get(parent, {f"event_{parent}"}))
                    queue.append(parent)

            for media_id in found_media_ids:
                media_banks[media_id].add(rel_path)
                media_object_types[media_id].add(HIRC_TYPES.get(obj_type_by_id.get(sound_id, -1), "Object"))
                media_events[media_id].update(found_events)

        if index % 500 == 0:
            print(f"Processed banks: {index}/{len(bank_paths)}")

    return media_events, media_banks, media_object_types


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a report mapping audio assets to human-readable Wwise names.")
    parser.add_argument("--game-root", type=Path, default=DEFAULT_GAME_ROOT)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--events", type=Path, default=DEFAULT_EVENTS)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    game_root = args.game_root.resolve()
    rows = load_manifest(args.manifest)
    event_names = load_event_names(args.events)

    audio_rows = [row for row in rows if row["extension"] in {".wem", ".bnk"}]
    wem_rows = [row for row in audio_rows if row["extension"] == ".wem"]
    bank_rows = [row for row in audio_rows if row["extension"] == ".bnk"]

    known_media_ids = {media_id for row in wem_rows if (media_id := media_id_from_path(row["relative_path"])) is not None}
    print(f"Known WEM media ids: {len(known_media_ids)}")
    print(f"Banks to parse: {len(bank_rows)}")

    media_events, media_banks, media_object_types = build_media_event_map(
        game_root,
        [row["relative_path"] for row in bank_rows],
        known_media_ids,
        event_names,
    )

    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    report_path = out / "audio_name_report.csv"
    missing_path = out / "audio_without_human_name.txt"
    summary_path = out / "audio_name_summary.txt"

    output_rows = []
    missing = []
    for row in audio_rows:
        rel = row["relative_path"]
        ext = row["extension"]
        media_id = media_id_from_path(rel)
        events = media_events.get(media_id or -1, set()) if ext == ".wem" else set()
        banks = media_banks.get(media_id or -1, set()) if ext == ".wem" else {rel}
        title = group_event_names(events)

        if ext == ".bnk":
            title = sanitize_title(Path(rel).stem)
            status = "bank_name"
        elif events:
            status = "event_name"
        elif media_id is None:
            title = sanitize_title(Path(rel).stem)
            status = "non_numeric_wem_name" if title else "missing"
        else:
            title = ""
            status = "missing"

        suggested_filename = f"{title}__{media_id}{ext}" if title and media_id is not None else (f"{title}{ext}" if title else "")
        output = {
            "relative_path": rel,
            "extension": ext,
            "media_id": media_id or "",
            "status": status,
            "suggested_title": title,
            "suggested_filename": suggested_filename,
            "event_names": "|".join(sorted(events)),
            "banks": "|".join(sorted(banks)),
            "object_types": "|".join(sorted(media_object_types.get(media_id or -1, set()))),
            "size": row["size"],
        }
        output_rows.append(output)
        if status == "missing":
            missing.append(output)

    fieldnames = [
        "relative_path",
        "extension",
        "media_id",
        "status",
        "suggested_title",
        "suggested_filename",
        "event_names",
        "banks",
        "object_types",
        "size",
    ]
    with report_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(output_rows)

    with missing_path.open("w", encoding="utf-8") as handle:
        for item in missing:
            handle.write(f"{item['relative_path']}\n")

    status_counts: dict[str, int] = defaultdict(int)
    missing_dirs: dict[str, int] = defaultdict(int)
    for item in output_rows:
        status_counts[str(item["status"])] += 1
    for item in missing:
        missing_dirs[str(Path(str(item["relative_path"])).parent)] += 1

    with summary_path.open("w", encoding="utf-8") as handle:
        handle.write(f"Audio rows: {len(output_rows)}\n")
        for status, count in sorted(status_counts.items(), key=lambda pair: (-pair[1], pair[0])):
            handle.write(f"{status}: {count}\n")
        handle.write(f"Missing human-readable WEM names: {len(missing)}\n\n")
        handle.write("Missing by directory:\n")
        for directory, count in sorted(missing_dirs.items(), key=lambda pair: (-pair[1], pair[0])):
            handle.write(f"{count}\t{directory}\n")

    print(f"Wrote {report_path}")
    print(f"Wrote {missing_path}")
    print(f"Wrote {summary_path}")
    print(f"Audio rows: {len(output_rows)}")
    print(f"Missing human-readable WEM names: {len(missing)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
