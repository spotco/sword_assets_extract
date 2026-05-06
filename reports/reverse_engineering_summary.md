# Reverse-engineering summary

This game was more involved than a typical Unity asset extraction, mostly
because of the audio.

## Difficulty compared to an average Unity game

- Images were average Unity work.
  - The `.unity3d` files are standard `UnityFS` bundles.
  - `UnityPy` can read and export textures/sprites from them.
- Audio was harder than average.
  - Most `.wem` and many `.bnk` files are not stored as normal Wwise files on
    disk.
  - They are XOR-obfuscated with a repeating key: `XD_Audio`.
- Audio naming was much harder than average.
  - Actual playable audio files live as numeric Wwise media IDs, such as
    `audio/Media/1001162596.wem`.
  - Human-readable names usually live in Wwise bank filenames, Wwise events, or
    music containers, not in the WEM file itself.
- Music naming was the trickiest part.
  - Normal SFX/VO can often be traced through `Sound -> Action -> Event`.
  - Music often uses Wwise music objects instead:
    `MusicTrack`, `MusicSegment`, `MusicPlaylistContainer`, and
    `MusicSwitchContainer`.

## Key discoveries

### Audio obfuscation

Many audio files are XOR-obfuscated with this repeating key:

```text
XD_Audio
```

After XOR decoding:

- `.wem` files become Wwise RIFF/WAVE-style files.
- `.bnk` files become Wwise banks beginning with `BKHD`.

Example:

```text
obfuscated WEM -> XOR with XD_Audio -> RIFF....WAVE
obfuscated BNK -> XOR with XD_Audio -> BKHD
```

### Where the audio lives

Main audio folder:

```text
C:\Program Files (x86)\Steam\steamapps\common\Sword of Convallaria\assets\audio
```

Important subfolders/files:

```text
audio/Media/*.wem       actual audio payloads, named by numeric media id
audio/*.bnk             Wwise banks, often with useful human-readable names
audio/cn/*.bnk          Chinese voice banks
audio/jp/*.bnk          Japanese voice banks
audio/kr/*.bnk          Korean voice banks
```

## Naming chain

The basic naming chain is:

```text
numeric WEM filename -> Wwise media id -> BNK DIDX/HIRC reference -> event or bank name
```

Example:

```text
audio/Media/1001162596.wem
media id: 1001162596
referenced by: Music_Story_SophiaFull.bnk
human title: Music_Story_SophiaFull
exported name: Mus_Scenario_SophiaFull_1001162596.mp3
```

Another example:

```text
audio/Media/29471732.wem
referenced through: bnk_sfx_amb_state.bnk
event names:
  Play_Amb_Scene_CityLYDay
  Play_Amb_Scene_CityLYEve
  play_Amb_Battle_Weather
```

## Strategies that worked

1. Decode WEM/BNK files with the `XD_Audio` XOR key.
2. Use `vgmstream-cli` to decode Wwise WEMs to WAV.
3. Use `ffmpeg` to convert WAV to MP3/OGG.
4. Use `bnk_events.unity3d` as the Wwise event-name table.
5. For normal SFX/VO, trace:

```text
Sound -> Action -> Event
```

6. For music/ambience, use:

```text
DIDX media id -> Music_*.bnk filename
```

and when DIDX is not enough, trace Wwise music HIRC objects:

```text
MusicTrack -> MusicSegment -> MusicPlaylistContainer -> MusicSwitchContainer -> Action/Event
```

## Strategies that were less useful

- Searching raw Unity bundles for media ids sometimes produced incidental binary
  matches and usually did not produce reliable names.
- Exact decoded-audio hash matching found no duplicate named WEMs for the final
  still-missing music/ambience candidate.
- Plain `ffmpeg` cannot directly decode the Wwise Custom Vorbis WEM files; it
  sees them as RIFF/WAVE but does not know the codec. `vgmstream-cli` is needed.

## Remaining unresolved audio

One non-voice candidate still has no recovered human-readable name:

```text
audio/Media/953029036.wem
duration: 27.029s
channels: 2
bitrate: 160 kbps
category: possibly music/ambience or long SFX
```

It has been exported numerically as:

```text
extracted/music_mp3/953029036.mp3
```

## Estimated human effort

A technically strong reverse-engineering or game-modding person could likely
figure this out, but it is not a beginner AssetStudio-only extraction.

Rough estimate:

- Plain Unity texture export: straightforward.
- Decoding playable audio: moderate difficulty because of XOR obfuscation.
- Recovering useful audio names: high difficulty without Wwise-bank familiarity.

The two important breakthroughs were:

```text
XOR key: XD_Audio
Naming chain: WEM media id -> BNK DIDX/HIRC -> event/bank name
```

