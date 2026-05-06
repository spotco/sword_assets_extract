# Music categorization and naming notes

Scope: audio files from `reports/audio_without_human_name.txt` that were later
classified as non-voice music/ambience candidates in
`reports/unnamed_audio_analysis.csv`.

## Current outputs

- `reports/unnamed_audio_analysis.csv`
  - Metadata profile for all 508 previously unnamed WEM files.
- `reports/unnamed_audio_likely_music_or_ambience.txt`
  - Long stereo unnamed files, very likely music or ambience.
- `reports/unnamed_audio_possibly_music_ambience_or_long_sfx.txt`
  - Stereo files between about 20 and 60 seconds, possible ambience, loops, or
    long SFX.
- `reports/unnamed_music_name_candidates.csv`
  - Names recovered for the 121 non-voice music/ambience candidates.
- `reports/unnamed_music_name_strategy_notes.txt`
  - Short machine-generated summary of strategy results.
- `reports/unnamed_music_hash_matches.csv`
  - Exact decoded-audio hash duplicate check; no matches were found for the
    still-missing candidates.

## Categorization rules used

The split is metadata-based, not a listening pass.

- Localized voice:
  - Path under `audio/Media/cn`, `audio/Media/jp`, `audio/Media/kr`, or
    `audio/Media/en`.
  - Usually mono (`1ch`), low bitrate around 50-80 kbps, short duration.
- Likely music or ambience:
  - Root `audio/Media/*.wem`.
  - Stereo (`2ch`).
  - Duration at least 60 seconds.
- Possible music/ambience or long SFX:
  - Root `audio/Media/*.wem`.
  - Stereo (`2ch`).
  - Duration from about 20 to 60 seconds.
- Likely SFX or voice line:
  - Root `audio/Media/*.wem`.
  - Shorter than 10 seconds.
- Unknown:
  - Metadata did not fit the thresholds cleanly.

For the 508 initially unnamed WEMs, the categorization result was:

```text
350 likely localized voice
104 likely music or ambience
17 possibly music/ambience or long SFX
34 likely short SFX or voice lines
3 unknown short stereo files
```

The non-voice music/ambience working set is therefore `104 + 17 = 121` files.

## Naming strategies tested

### 1. Event-name HIRC trace

The existing `build_audio_name_report.py` resolves most WEMs by tracing Wwise
`Sound` objects through `Action` and `Event` objects and then resolving the event
id through `bnk_events.unity3d`.

This worked for 42,363 WEMs overall, but it did not name the 121 non-voice
music/ambience candidates because many music files are referenced through Wwise
music objects (`MusicTrack`, `MusicSegment`, `MusicPlaylistContainer`,
`MusicSwitchContainer`) rather than ordinary `Sound` objects.

### 2. Direct Wwise DIDX media-id to bank filename

Script: `scripts/name_unnamed_music_from_banks.py`

Many music WEM media ids appear directly in the `DIDX` chunk of small,
human-named music banks such as:

- `Music_Battle_Trail.bnk`
- `Music_Scene_Wolven.bnk`
- `Music_Story_SophiaFull.bnk`
- `Music_UI_Login.bnk`

When a WEM id is found in one of these banks, the bank filename is strong naming
evidence. Example:

```text
audio/Media/1001162596.wem -> Music_Story_SophiaFull
audio/Media/702423934.wem  -> Music_Scene_Wolven / Music_Story_Wolven
```

This was the most productive strategy.

### 3. Wwise MusicTrack/HIRC event trace

Script: `scripts/name_unnamed_music_from_banks.py`

Some ambience/music files do not appear in `DIDX` entries but do appear inside
Wwise music HIRC objects. The script now scans HIRC objects for media ids and
walks references up to events.

This recovered additional ambience names from `bnk_sfx_amb_state.bnk`, for
example:

```text
audio/Media/29471732.wem  -> Amb_Scene_CityLYDay / Amb_Scene_CityLYEve / Amb_Battle_Weather
audio/Media/709349582.wem -> Amb_Scene_CityLYDay / Amb_Scene_CityLYEve / Amb_Battle_Weather
```

This strategy raised the non-voice music/ambience naming coverage to 120 of 121.

### 4. Non-Media metadata search

Script: `scripts/search_media_ids_in_metadata.py`

The script searched non-`audio/Media` asset files for each remaining media id in
little-endian, big-endian, and decimal forms. Useful hits were rare. Some hits in
Unity bundles looked like incidental binary matches and did not provide readable
names. The useful hits confirmed that Wwise bank/HIRC parsing was the right
source of truth.

### 5. Exact decoded-audio hash matching

Script: `scripts/match_unnamed_audio_hashes.py`

The script checked whether still-unnamed files were exact decoded-byte duplicates
of already named WEMs with the same file size. This found no matches, so no names
could be inherited safely by duplicate hash.

## Current naming result for non-voice music candidates

From `reports/unnamed_music_name_candidates.csv`:

```text
121 total non-voice music/ambience candidates
120 high-confidence names recovered
1 still missing
```

The single still-missing file is:

```text
audio/Media/953029036.wem
duration: 27.029s
channels: 2
bitrate: 160 kbps
category: possibly_music_ambience_or_long_sfx
```

No useful bank reference, event reference, metadata string, or exact duplicate
match has been found for `953029036.wem` so far. Treat it as an orphaned or
unreferenced short stereo ambience/SFX candidate unless a future listening pass
or deeper Wwise parser identifies it.

## Music bank naming conventions observed

Music/ambience bank names are generally meaningful and should be preserved:

- `Music_Battle_*`: battle BGM.
- `Music_Scene_*`: location or scene ambience/BGM.
- `Music_Story_*`: story/cutscene BGM.
- `Music_UI_*` and `Init_Mus_Login`: UI/login music.
- `Mus_Story_*`: alternate story music naming.
- `bnk_sfx_amb_state`: ambience state bank; names should come from events such
  as `Play_Amb_Scene_CityLYDay`, not from the bank name alone.

When multiple specific music banks reference the same media id, keep a combined
or normalized title and preserve the numeric id in the filename.

