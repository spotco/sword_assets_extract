# Sword of Convallaria asset extraction notes

This workspace contains notes and scripts for reading assets from:

`C:\Program Files (x86)\Steam\steamapps\common\Sword of Convallaria`

Do not write into the game install. The scripts default to writing under this
workspace only.

## Observed layout

- `assets\` is the main payload directory.
- `SwordOfConvallaria_us\SoC_Data\` is the Unity player data for the US client.
- `Launcher_Data\` is a separate Unity launcher.
- The Unity bundles are normal `UnityFS` files built with `2020.3.42f1XD1.1.889b`.
- Audio files under `assets\audio` are Wwise files obfuscated with repeating XOR
  key `XD_Audio`.
  - `.wem` decodes to `RIFF....WAVE`.
  - `.bnk` decodes to `BKHD`.
- There are no obvious loose `.png`, `.jpg`, `.ogg`, `.wav`, or `.mp3` files under
  `assets`; images appear to be inside Unity `.unity3d` bundles.
- There are many loose `.mp4` movie files under `assets\movie`.

## Current file counts

From `assets\`:

- `42871` `.wem`
- `5913` `.unity3d`
- `5538` `.bnk`
- `120` `.mp4`
- `25` `.proto`
- `25` `.bytes`

Total size observed: about 8.68 GB.

## Scripts

Run from this workspace.

Inventory the game assets:

```powershell
python .\scripts\inventory_assets.py
```

The inventory skips `assets\Report` by default because it contains live runtime
report files that may change while scanning. Add `--include-report` only if you
specifically want to include it.

Decode Wwise audio to this workspace:

```powershell
python .\scripts\decode_wwise_xor.py --limit 10
python .\scripts\decode_wwise_xor.py --overwrite
```

The decoded `.wem` files are still Wwise Vorbis/Opus-style media. Use a WEM
converter such as `vgmstream` or `ww2ogg` after decoding if you need `.wav` or
`.ogg`.

Some `.bnk`/`.wem` files are already plain Wwise files. The decoder detects
those and copies them unchanged, so it is safe to run across the whole audio
tree.

Convert decoded `.wem` files to compressed playable audio after installing
`vgmstream-cli` under `tools\vgmstream` and ensuring `ffmpeg` is on PATH:

```powershell
python .\scripts\convert_decoded_wem.py --input .\extracted\audio_xor_decoded\1000465655.wem --format mp3
python .\scripts\convert_decoded_wem.py --input .\extracted\audio_xor_decoded --format ogg --limit 10
```

## Naming audio by Wwise event

WEM filenames are numeric Wwise media ids, for example `1000465655.wem`. To find
a useful label, map that media id back through the Wwise banks and then resolve
the bank event id to names from `bnk_events.unity3d`.

First dump the event-name table once:

```powershell
python .\scripts\dump_unity_textassets.py "C:\Program Files (x86)\Steam\steamapps\common\Sword of Convallaria\assets\bnk_events.unity3d" --out .\extracted\unity_textassets
```

This writes:

`extracted\unity_textassets\bnk_events__bnk_events__1876318598449274942.bytes`

Then trace a WEM/media id:

```powershell
python .\scripts\find_wwise_media_id.py 1000465655
python .\scripts\trace_wwise_media_id.py 1000465655
```

What the scripts do:

- `find_wwise_media_id.py` scans `.bnk` files, decoding `XD_Audio` XOR banks in
  memory when needed, and reports which banks contain the media id as little
  endian bytes.
- `trace_wwise_media_id.py` parses the Wwise `HIRC` section in matching banks.
  It finds the `Sound` object containing the media id, walks references through
  containers/actions, and resolves final `Event` ids against the dumped
  `bnk_events` JSON.

For `1000465655`, the trace produced:

```text
bnk_sfx_scenario_online_93.bnk
  Event name=play_online_93_amb_loop

bnk_sfx_scenario_online_94.bnk
  Event name=play_online_94_amb_loop

bnk_sfx_scenario_online_98.bnk
  Event name=play_online_98_amb_loop
```

The recommended filename from that evidence is:

`play_online_93_94_98_amb_loop__1000465655.mp3`

For bulk naming, keep the numeric id at the end because the same media id can be
referenced by multiple event names. Prefer exact event names when there is one
clear hit, and use a grouped name when multiple events share the same media.

To build the full audio naming report from `reports\asset_manifest.csv`:

```powershell
python .\scripts\build_audio_name_report.py
```

Outputs:

- `reports\audio_name_report.csv`: one row per `.wem` and `.bnk` audio asset,
  with original relative path, status, event names, bank references, suggested
  title, and suggested filename.
- `reports\audio_without_human_name.txt`: every `.wem` that could not be traced
  to a Wwise event name.
- `reports\audio_name_summary.txt`: counts by naming status and missing-name
  counts by directory.

Status meanings:

- `event_name`: a `.wem` was traced through Wwise `HIRC` to one or more events.
- `bank_name`: a `.bnk` uses its existing bank filename as the human-readable
  label.
- `missing`: a `.wem` appears in the manifest but could not be traced to an
  event name in the parsed banks.

For the unnamed non-voice music/ambience subset, run:

```powershell
python .\scripts\analyze_unnamed_audio.py
python .\scripts\name_unnamed_music_from_banks.py
python .\scripts\search_media_ids_in_metadata.py
python .\scripts\match_unnamed_audio_hashes.py
```

The main result is `reports\unnamed_music_name_candidates.csv`. Detailed notes
on music categorization and naming strategy are in
`reports\music_categorization_notes.md`.

Export images from Unity bundles, if `UnityPy` is installed:

```powershell
python -m pip install UnityPy
python .\scripts\export_unity_images.py --include atlas --include icon --limit 20
```

The `export_unity_images.py` script intentionally fails fast with installation
instructions if `UnityPy` is not available. AssetRipper or AssetStudio should
also be able to read these `UnityFS` bundles directly.

Carve simple embedded media signatures from copied/sample files:

```powershell
python .\scripts\carve_signatures.py --input .\samples
```

This is mainly a sanity check. Unity Texture2D data is usually serialized or
compressed, so carving is not expected to recover most images.
