from __future__ import annotations

import argparse
import csv
import json
import re
from collections import defaultdict, deque
from pathlib import Path


DEFAULT_GAME_ROOT = Path(r"C:\Program Files (x86)\Steam\steamapps\common\Sword of Convallaria")
DEFAULT_ANALYSIS = Path("reports/unnamed_audio_analysis.csv")
DEFAULT_EVENTS = Path("extracted/unity_textassets/bnk_events__bnk_events__1876318598449274942.bytes")
DEFAULT_OUT = Path("reports/unnamed_music_name_candidates.csv")
DEFAULT_SUMMARY = Path("reports/unnamed_music_name_strategy_notes.txt")
KEY = b"XD_Audio"
MUSIC_CATEGORIES = {"likely_music_or_ambience", "possibly_music_ambience_or_long_sfx"}


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
        if size < 0 or end > len(data):
            break
        yield tag, data[start:end]
        offset = end


def didx_media_ids(bank: bytes) -> set[int]:
    ids: set[int] = set()
    for tag, payload in chunks(bank):
        if tag != b"DIDX":
            continue
        for offset in range(0, len(payload) - 11, 12):
            media_id = int.from_bytes(payload[offset : offset + 4], "little")
            ids.add(media_id)
    return ids


def hirc_media_ids(bank: bytes, known_media_ids: set[int]) -> set[int]:
    ids: set[int] = set()
    for tag, payload in chunks(bank):
        if tag != b"HIRC" or len(payload) < 4:
            continue
        count = int.from_bytes(payload[:4], "little")
        pos = 4
        for _ in range(count):
            if pos + 9 > len(payload):
                break
            size = int.from_bytes(payload[pos + 1 : pos + 5], "little")
            obj_start = pos + 5
            obj_end = obj_start + size
            if obj_end > len(payload) or size < 4:
                break
            obj_data = payload[obj_start:obj_end]
            for offset in range(0, len(obj_data) - 3):
                value = int.from_bytes(obj_data[offset : offset + 4], "little")
                if value in known_media_ids:
                    ids.add(value)
            pos = obj_end
    return ids


def fnv1_32(text: str) -> int:
    value = 2166136261
    for byte in text.encode("utf-8"):
        value = (value * 16777619) & 0xFFFFFFFF
        value ^= byte
    return value


def load_event_names(path: Path) -> dict[int, set[str]]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text("utf-8"))
    names: dict[int, set[str]] = defaultdict(set)
    for section in data.values():
        if not isinstance(section, dict):
            continue
        for name in section:
            names[fnv1_32(name)].add(name)
            names[fnv1_32(name.lower())].add(name)
    return names


def hirc_media_events(bank: bytes, known_media_ids: set[int], event_names: dict[int, set[str]]) -> dict[int, set[str]]:
    objects: list[tuple[int, int, bytes]] = []
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
            objects.append((obj_type, obj_id, obj_data))
            pos = obj_end

    obj_ids = {obj_id for _, obj_id, _ in objects}
    event_ids = {obj_id for obj_type, obj_id, _ in objects if obj_type == 4}
    reverse_refs: dict[int, set[int]] = defaultdict(set)
    media_objects: dict[int, set[int]] = defaultdict(set)

    for obj_type, obj_id, obj_data in objects:
        for offset in range(0, len(obj_data) - 3):
            value = int.from_bytes(obj_data[offset : offset + 4], "little")
            if value in obj_ids and value != obj_id:
                reverse_refs[value].add(obj_id)
            if value in known_media_ids:
                media_objects[value].add(obj_id)

    media_to_events: dict[int, set[str]] = defaultdict(set)
    for media_id, start_objects in media_objects.items():
        for start_id in start_objects:
            queue = deque([start_id])
            seen = {start_id}
            while queue:
                current = queue.popleft()
                for parent in reverse_refs.get(current, set()):
                    if parent in seen:
                        continue
                    seen.add(parent)
                    if parent in event_ids:
                        media_to_events[media_id].update(event_names.get(parent, {f"event_{parent}"}))
                    queue.append(parent)
    return media_to_events


def media_id_from_path(relative_path: str) -> int:
    return int(Path(relative_path).stem)


def sanitize(text: str) -> str:
    text = text.strip()
    text = re.sub(r"\.bnk$", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^(lda_)?bnk_", "", text, flags=re.IGNORECASE)
    text = re.sub(r"[^A-Za-z0-9]+", "_", text)
    return re.sub(r"_+", "_", text).strip("_")


def classify_bank(bank_name: str) -> str:
    name = bank_name.lower()
    if "music_battle" in name:
        return "battle_music"
    if "music_scene" in name:
        return "scene_music"
    if "music_story" in name or "mus_story" in name:
        return "story_music"
    if "music_ui" in name or "init_mus_login" in name:
        return "ui_music"
    if "music_" in name:
        return "music"
    if "scenario" in name:
        return "scenario_sfx_or_ambience"
    return "non_music_bank"


def choose_title(bank_names: list[str]) -> str:
    titles = [sanitize(Path(name).stem) for name in bank_names]
    if not titles:
        return ""
    unique = sorted(set(titles))
    generic_titles = {
        "Music",
        "Music_Scene",
        "Music_Story",
        "Music_Battle",
        "Music_Control",
        "scenario_control",
        "Stop_Control_Event",
        "Test_Event",
    }
    specific = [title for title in unique if title not in generic_titles]
    if specific:
        unique = specific
    # Prefer the Music_* title if non-music banks also happen to reference it.
    music_titles = [title for title in unique if title.lower().startswith(("music_", "mus_", "init_mus_", "lda_music_"))]
    if music_titles:
        unique = music_titles
    if len(unique) == 1:
        return unique[0]

    # Collapse Scene/Story variants of the same music title.
    normalized = {}
    for title in unique:
        key = re.sub(r"^Music_(Scene|Story|Battle|UI)_", "", title, flags=re.IGNORECASE)
        key = re.sub(r"^Mus_Story_", "", key, flags=re.IGNORECASE)
        normalized.setdefault(key.lower(), []).append(title)
    if len(normalized) == 1:
        return sorted(next(iter(normalized.values())), key=len)[0]
    return "__".join(unique[:4]) + ("__multiple" if len(unique) > 4 else "")


def choose_event_title(event_names: set[str]) -> str:
    if not event_names:
        return ""
    titles = sorted({sanitize(name) for name in event_names})
    titles = [re.sub(r"^(Play|play)_", "", title) for title in titles]
    if len(titles) == 1:
        return titles[0]
    return "__".join(titles[:4]) + ("__multiple" if len(titles) > 4 else "")


def main() -> int:
    parser = argparse.ArgumentParser(description="Name unnamed likely music WEMs from direct Wwise DIDX bank references.")
    parser.add_argument("--game-root", type=Path, default=DEFAULT_GAME_ROOT)
    parser.add_argument("--analysis", type=Path, default=DEFAULT_ANALYSIS)
    parser.add_argument("--events", type=Path, default=DEFAULT_EVENTS)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    args = parser.parse_args()

    with args.analysis.open("r", newline="", encoding="utf-8") as handle:
        candidates = [row for row in csv.DictReader(handle) if row["category"] in MUSIC_CATEGORIES]
    media_ids = {media_id_from_path(row["relative_path"]) for row in candidates}
    event_names = load_event_names(args.events)

    media_to_banks: dict[int, set[str]] = defaultdict(set)
    media_to_events: dict[int, set[str]] = defaultdict(set)
    bank_dir = args.game_root / "assets" / "audio"
    bank_files = sorted(bank_dir.rglob("*.bnk"))
    for index, bank_path in enumerate(bank_files, start=1):
        try:
            bank = decode_bank_if_needed(bank_path.read_bytes())
        except OSError:
            continue
        ids = didx_media_ids(bank)
        bank_kind = classify_bank(bank_path.name)
        ids |= hirc_media_ids(bank, media_ids)
        for media_id, names in hirc_media_events(bank, media_ids, event_names).items():
            media_to_events[media_id].update(names)
            ids.add(media_id)
        matched = ids & media_ids
        if matched:
            rel = str(bank_path.relative_to(bank_dir)).replace("\\", "/")
            for media_id in matched:
                media_to_banks[media_id].add(rel)
        if index % 1000 == 0:
            print(f"Scanned banks: {index}/{len(bank_files)}")

    rows = []
    for row in candidates:
        media_id = media_id_from_path(row["relative_path"])
        bank_names = sorted(media_to_banks.get(media_id, set()))
        events = media_to_events.get(media_id, set())
        bank_types = sorted({classify_bank(name) for name in bank_names})
        event_title = choose_event_title(events)
        bank_title = choose_title(bank_names)
        title = event_title or bank_title
        confidence = (
            "high"
            if title and (events or any(kind.endswith("_music") or kind == "music" for kind in bank_types))
            else ("medium" if title else "missing")
        )
        rows.append(
            {
                "relative_path": row["relative_path"],
                "media_id": media_id,
                "category": row["category"],
                "duration_seconds": row["duration_seconds"],
                "channels": row["channels"],
                "bitrate": row["bitrate"],
                "bank_names": "|".join(bank_names),
                "bank_types": "|".join(bank_types),
                "event_names": "|".join(sorted(events)),
                "suggested_title": title,
                "suggested_filename": f"{title}__{media_id}.wem" if title else "",
                "confidence": confidence,
            }
        )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="", encoding="utf-8") as handle:
        fieldnames = [
            "relative_path",
            "media_id",
            "category",
            "duration_seconds",
            "channels",
            "bitrate",
            "confidence",
            "suggested_title",
            "suggested_filename",
            "bank_types",
            "bank_names",
            "event_names",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    counts: dict[str, int] = defaultdict(int)
    type_counts: dict[str, int] = defaultdict(int)
    missing = []
    for row in rows:
        counts[row["confidence"]] += 1
        if not row["suggested_title"]:
            missing.append(row)
        for kind in str(row["bank_types"]).split("|"):
            if kind:
                type_counts[kind] += 1

    with args.summary.open("w", encoding="utf-8") as handle:
        handle.write(f"Unnamed non-voice music candidates: {len(rows)}\n")
        for key, count in sorted(counts.items(), key=lambda item: (-item[1], item[0])):
            handle.write(f"{key}: {count}\n")
        handle.write("\nBank type hits:\n")
        for key, count in sorted(type_counts.items(), key=lambda item: (-item[1], item[0])):
            handle.write(f"{key}: {count}\n")
        handle.write("\nStrategy results:\n")
        handle.write("1. Direct Wwise DIDX media-id to .bnk filename mapping recovered names for files whose media id is listed in a Music_*.bnk bank.\n")
        handle.write("2. HIRC MusicTrack/media-id tracing recovered additional names where music/ambience was referenced by events instead of DIDX entries.\n")
        handle.write("3. Exact decoded-audio hash matching was tested separately and found no duplicate named WEMs for the still-missing files.\n")
        handle.write("4. Duration/channel categorization is still needed to separate music/ambience from short SFX.\n")
        handle.write("\nStill missing after all music naming strategies in this script:\n")
        for item in missing:
            handle.write(f"{item['relative_path']}\t{item['duration_seconds']}s\t{item['category']}\n")

    print(f"Wrote {args.out}")
    print(f"Wrote {args.summary}")
    print(f"Missing titles: {len(missing)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
