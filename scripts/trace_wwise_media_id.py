from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


DEFAULT_GAME_ROOT = Path(r"C:\Program Files (x86)\Steam\steamapps\common\Sword of Convallaria")
KEY = b"XD_Audio"
HIRC_TYPES = {
    1: "State",
    2: "Sound",
    3: "Action",
    4: "Event",
    5: "RandomSequenceContainer",
    6: "SwitchContainer",
    7: "ActorMixer",
    8: "AudioBus",
    9: "BlendContainer",
    10: "MusicSegment",
    11: "MusicTrack",
    12: "MusicSwitchContainer",
    13: "MusicPlaylistContainer",
    14: "Attenuation",
    15: "DialogueEvent",
    16: "MotionBus",
    17: "MotionFx",
    18: "Effect",
    19: "AuxBus",
}


def xor_data(data: bytes) -> bytes:
    return bytes(byte ^ KEY[index % len(KEY)] for index, byte in enumerate(data))


def decode_if_needed(data: bytes) -> bytes:
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
        yield tag, start, data[start:end]
        offset = end


def hirc_objects(bank: bytes):
    for tag, start, payload in chunks(bank):
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
            yield {
                "type": obj_type,
                "type_name": HIRC_TYPES.get(obj_type, f"Type{obj_type}"),
                "id": obj_id,
                "bank_offset": start + obj_start,
                "data": obj_data,
            }
            pos = obj_end


def load_event_names(path: Path | None) -> dict[int, str]:
    if not path or not path.exists():
        return {}
    data = json.loads(path.read_text("utf-8"))
    names: dict[int, str] = {}
    for section in data.values():
        if not isinstance(section, dict):
            continue
        for name in section:
            names[fnv1_32(name)] = name
            names[fnv1_32(name.lower())] = name
    return names


def fnv1_32(text: str) -> int:
    value = 2166136261
    for byte in text.encode("utf-8"):
        value = (value * 16777619) & 0xFFFFFFFF
        value ^= byte
    return value


def strings(data: bytes) -> list[str]:
    return [m.group(0).decode("ascii", "ignore") for m in re.finditer(rb"[ -~]{4,}", data)]


def print_ref_tree(objs: list[dict], target_id: int, event_names: dict[int, str], indent: int, seen: set[int]) -> None:
    target_bytes = target_id.to_bytes(4, "little")
    refs = [candidate for candidate in objs if candidate["id"] != target_id and target_bytes in candidate["data"]]
    for ref in refs:
        label = event_names.get(ref["id"], "")
        suffix = f" name={label}" if label else ""
        print(f"{' ' * indent}referenced by {ref['type_name']} id={ref['id']}{suffix}")
        if ref["id"] not in seen and indent < 12:
            seen.add(ref["id"])
            print_ref_tree(objs, ref["id"], event_names, indent + 2, seen)


def main() -> int:
    parser = argparse.ArgumentParser(description="Trace a Wwise media id through HIRC references.")
    parser.add_argument("media_id", type=int)
    parser.add_argument("--root", type=Path, default=DEFAULT_GAME_ROOT / "assets" / "audio")
    parser.add_argument("--events", type=Path, default=Path("extracted/unity_textassets/bnk_events__bnk_events__1876318598449274942.bytes"))
    args = parser.parse_args()

    media_bytes = args.media_id.to_bytes(4, "little")
    event_names = load_event_names(args.events)

    for path in args.root.rglob("*.bnk"):
        try:
            bank = decode_if_needed(path.read_bytes())
        except OSError:
            continue
        if media_bytes not in bank:
            continue
        objs = list(hirc_objects(bank))
        media_objs = [obj for obj in objs if media_bytes in obj["data"]]
        if not media_objs:
            continue
        rel = path.relative_to(args.root)
        print(f"\n{rel}")
        for obj in media_objs:
            obj_id = obj["id"]
            print(f"  media in {obj['type_name']} id={obj_id} offset=0x{obj['bank_offset']:x}")
            print_ref_tree(objs, obj_id, event_names, 4, {obj_id})
            local_strings = strings(obj["data"])
            if local_strings:
                print("    strings: " + " | ".join(local_strings[:8]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
