from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path


DEFAULT_VGMSTREAM = Path("tools/vgmstream/vgmstream-cli.exe")
DEFAULT_INPUT = Path("extracted/audio_xor_decoded")
DEFAULT_OUT = Path("extracted/audio_converted")


def require_tool(path_or_name: str | Path) -> str:
    text = str(path_or_name)
    if Path(text).exists():
        return text
    found = shutil.which(text)
    if found:
        return found
    raise SystemExit(f"Missing required tool: {text}")


def convert_one(source: Path, out_dir: Path, vgmstream: str, ffmpeg: str, fmt: str, bitrate: str, keep_wav: bool) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    wav = out_dir / f"{source.stem}.wav"
    final = out_dir / f"{source.stem}.{fmt}"

    subprocess.run([vgmstream, "-o", str(wav), str(source)], check=True)

    if fmt == "mp3":
        cmd = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-i", str(wav), "-codec:a", "libmp3lame", "-b:a", bitrate, str(final)]
    elif fmt == "ogg":
        cmd = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-i", str(wav), "-codec:a", "libvorbis", "-q:a", "5", str(final)]
    else:
        raise SystemExit(f"Unsupported format: {fmt}")

    subprocess.run(cmd, check=True)
    if not keep_wav:
        wav.unlink(missing_ok=True)
    return final


def main() -> int:
    parser = argparse.ArgumentParser(description="Convert decoded Wwise .wem files to MP3 or OGG.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="Decoded .wem file or directory.")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--vgmstream", type=Path, default=DEFAULT_VGMSTREAM)
    parser.add_argument("--ffmpeg", default="ffmpeg")
    parser.add_argument("--format", choices=["mp3", "ogg"], default="mp3")
    parser.add_argument("--bitrate", default="192k", help="MP3 bitrate, ignored for OGG.")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--keep-wav", action="store_true")
    args = parser.parse_args()

    vgmstream = require_tool(args.vgmstream)
    ffmpeg = require_tool(args.ffmpeg)
    source = args.input.resolve()
    out = args.out.resolve()

    if source.is_file():
        files = [source]
    else:
        files = sorted(source.rglob("*.wem"))
    if args.limit:
        files = files[: args.limit]
    if not files:
        raise SystemExit(f"No .wem files found in {source}")

    for file_path in files:
        final = convert_one(file_path, out, vgmstream, ffmpeg, args.format, args.bitrate, args.keep_wav)
        print(final)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
