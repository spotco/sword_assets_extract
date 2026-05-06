# Level Layout Findings

This report was generated from read-only probes against the Steam install at
`C:\Program Files (x86)\Steam\steamapps\common\Sword of Convallaria`.

## Most Likely Location

The main tactical battle layouts are in:

`assets/battle/map/*.unity3d`

This folder contains 492 Unity bundles and the sampled files are scene-like
UnityFS bundles, not simple images or audio. They include `GameObject`,
`Transform`, `MeshRenderer`, `MeshFilter`, colliders, lights, cameras, and
game-specific MonoBehaviours.

## Confirmed Battle Map Structure

Sample bundle:

`assets/battle/map/stage_city-ca-da00101.unity3d`

Important hierarchy found inside the bundle:

`MapTool/Map/block_root/emptyblock/{enter,noenter,...}/empty X_Z`

Important components found:

- `MapTool`
  - Has `width` and `height`.
  - In the sample, both are `20`.
- `MapProperty`
  - Has battle/camera bounds and scenario camera settings.
  - In the sample, `useBattle = 1`, `boundMin = (-2,0,-2)`,
    `boundMax = (16,0,19)`.
- `BlockProperty`
  - Attached to individual grid tile objects.
  - In the sample, 285 block tiles were extracted.
  - Fields seen so far: `type`, `isGamepadCursorMovable`.
- `BattleGrassData`
  - Contains `blockPos` entries and paths back to grid cells, mostly for grass
    instance placement.

## How Tile Records Appear To Work

Each tile is a Unity `GameObject` under `emptyblock`. The object name is usually
`empty X_Z`, matching grid X/Z. Its transform position also stores X/Z and a Y
height/elevation. The object has a small trigger `BoxCollider`, usually size
`1,0.1,1`, plus a `BlockProperty` MonoBehaviour.

Example row from the grid extractor:

```text
MapTool/Map/block_root/emptyblock/enter/empty 7_15
local_position = 7,2.4,15
block_type = 10
collider = BoxCollider trigger, size 1,0.1,1
```

The `enter` and `noenter` path segments are strong indicators for walkable
versus blocked/invalid cells. `BlockProperty.type` is likely an enum for finer
tile behavior, material, height, or tactical state. The exact enum mapping is
not decoded yet.

## Other Candidate Locations

These folders also contain likely layout or scene data:

- `assets/scenario` and `assets/scenario/scene`
  - Story/cutscene environments.
- `assets/minisandbox/map`
  - Hub or alternate mode maps.
- `assets/capital/map` and `assets/capital/setting_group`
  - Capital/hub layouts and setting groups.
- `assets/dreamlands/map`
  - Dreamlands mode maps.
- `assets/worldboss/map`
  - World boss mode maps.
- `assets/infinitechallenge/map`
  - Infinite challenge mode maps.

These are worth probing with the same object inventory and scene dump tools, but
the tactical grid evidence is strongest in `assets/battle/map`.

## Open Questions

- Decode the `BlockProperty.type` enum.
- Find where spawn points, objectives, enemy waves, and mission-to-map links are
  stored.
- Determine whether those gameplay records live in the battle map bundle,
  `db_lua.bytes`, `db_template.unity3d`, protobuf-backed tables, or server-side
  content.
- Build a simple map visualizer from `<map>_grid_blocks.csv` to inspect
  walkable/no-enter areas and elevation.

## Tool Outputs

The current probes write to `level_probe/reports`:

- `level_candidate_dirs.csv`
- `level_candidate_files.csv`
- `bundle_object_inventory.csv`
- `monobehaviour_scripts_by_bundle.csv`
- `monobehaviour_script_totals.csv`
- `<map>_scene_objects.csv`
- `<map>_colliders.csv`
- `<map>_monobehaviours.csv`
- `<map>_grid_blocks.csv`
- `<map>_block_type_counts.csv`
- `<map>_map_metadata.json`

