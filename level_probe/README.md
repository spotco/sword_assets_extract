# Level layout probing tools

This folder contains read-only probes for locating and understanding level/map
layout data in Sword of Convallaria.

The tools read from the Steam install and write reports under `level_probe/reports`.
They do not edit the game folder.

## Current theories

1. **Battle map geometry/layout bundles**
   - Strong candidate folder: `assets/battle/map`.
   - Files are standard UnityFS scene-like bundles with many `GameObject`,
     `Transform`, `MeshRenderer`, `MeshFilter`, `BoxCollider`, `MeshCollider`,
     and `MonoBehaviour` objects.
   - Stores visible map geometry, collision, props, lights, cameras, and the
     tactical grid helper objects.
   - Confirmed structure in sampled bundles:
     `MapTool/Map/block_root/emptyblock/{enter,noenter,...}/empty X_Z`.
   - `MapTool` carries width/height fields. Example:
     `stage_city-ca-da00101.unity3d` has `width = 20`, `height = 20`.
   - `MapProperty` carries battle/camera bounds. Example:
     `boundMin = (-2,0,-2)`, `boundMax = (16,0,19)`.
   - Individual tiles are `GameObject`s with `BoxCollider` triggers and
     `BlockProperty` MonoBehaviours. Their transform position gives grid X/Z
     plus elevation in Y, while `BlockProperty.type` appears to classify tile
     behavior/material/height/state.

2. **Scenario/cutscene scene bundles**
   - Candidate folders: `assets/scenario`, `assets/scenario/scene`,
     `assets/scene`.
   - These look similar to Unity scene bundles and likely store story scene
     environments rather than tactical battle rules.

3. **Mode-specific map bundles**
   - Candidate folders: `assets/minisandbox/map`, `assets/dreamlands/map`,
     `assets/capital/map`, `assets/worldboss/map`,
     `assets/infinitechallenge/map`.
   - These probably store layouts for non-main battle modes or hubs.

4. **Battle logic/layout tables**
   - Candidate files: `db_lua.bytes`, `db_template.unity3d`,
     `asset_bundle.unity3d`, `asset_dep.unity3d`.
   - These may map missions/stages to map bundle names, spawn points, objectives,
     enemy waves, obstacles, or grid parameters.

5. **MonoBehaviour payloads in map bundles**
   - Map bundles include many MonoBehaviours. Their serialized fields may contain
     map metadata such as grid coordinates, stage ids, spawn markers, walkability,
     trigger regions, or camera/lighting config.
   - Confirmed battle-map MonoBehaviours include `BlockProperty`, `MapTool`,
     `MapProperty`, `BattleGrassData`, camera helpers, lighting config, and
     Wwise audio hooks.

## Evidence from sample bundles

- `assets/battle/map/stage_city-ca-da00101.unity3d`
  - 698 `GameObject`s, 698 `Transform`s, 290 colliders, 346 MonoBehaviours.
  - 285 `BlockProperty` tiles extracted.
  - Block type counts: `2=86`, `1=49`, `28=48`, `12=42`, `15=40`,
    `10=12`, `11=5`, `29=3`.
  - `BattleGrassData` includes `blockPos` values and paths back into the grid,
    such as `MapTool/Map/block_root/emptyblock/enter/enter-grass/empty 8_3`.

- `assets/battle/map/battle001.unity3d`
  - Older/smaller battle map bundle.
  - 96 `BlockProperty` tiles extracted.
  - Block type counts: `11=64`, `27=21`, `28=11`.

## Working interpretation

The battle maps are not a single opaque table. They are Unity scene bundles with
an editor-authored `MapTool` hierarchy. The core tactical layout can be probed
from:

1. `MapTool.width` / `MapTool.height` for nominal grid size.
2. `MapProperty.boundMin` / `MapProperty.boundMax` for battle/camera bounds.
3. `BlockProperty` objects under `MapTool/Map/block_root/emptyblock` for per-cell
   layout records.
4. The `enter` versus `noenter` folder in each tile path for likely walkable
   versus blocked/invalid cells.
5. The tile transform position: X/Z are grid coordinates and Y is elevation.
6. `BlockProperty.type` for a still-unknown tile category enum.

The remaining unknown is the exact enum mapping for `BlockProperty.type`, and
whether unit spawn/enemy wave/objective data lives inside these scene bundles or
in separate mission/config tables that reference the map bundle name.

For a browser-rendered level viewer plan, see
`level_probe/reports/threejs_level_visualizer_plan.md`.

## Useful commands

Survey likely map folders:

```powershell
python .\level_probe\survey_level_candidates.py
```

Inspect object type counts for representative bundles:

```powershell
python .\level_probe\bundle_object_inventory.py --limit 20
```

Dump scene hierarchy and colliders for one bundle:

```powershell
python .\level_probe\dump_scene_layout.py --bundle "C:\Program Files (x86)\Steam\steamapps\common\Sword of Convallaria\assets\battle\map\stage_city-ca-da00101.unity3d"
```

Extract the probable tactical grid blocks from one battle map:

```powershell
python .\level_probe\extract_battle_grid.py --bundle assets\battle\map\stage_city-ca-da00101.unity3d
```

This writes:

- `level_probe/reports/<map>_grid_blocks.csv`
- `level_probe/reports/<map>_block_type_counts.csv`
- `level_probe/reports/<map>_map_metadata.json`

Search Unity TextAssets and known metadata for map/stage terms:

```powershell
python .\level_probe\search_level_textassets.py --terms stage map grid spawn
```

Dump MonoBehaviour script/type summaries from map bundles:

```powershell
python .\level_probe\monobehaviour_probe.py --limit 10
```
