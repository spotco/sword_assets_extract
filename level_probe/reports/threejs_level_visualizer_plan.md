# Three.js Level Visualizer Plan

This note summarizes what we currently know about Sword of Convallaria level
data and sketches a practical path to render those levels in a browser with
Three.js.

## What We Have Learned

The main tactical battle maps appear to live in:

`assets/battle/map/*.unity3d`

These are Unity scene-style AssetBundle files. They are not just metadata; they
contain scene objects, transforms, meshes, renderers, colliders, lights,
particles, cameras, materials, and custom game MonoBehaviours.

The strongest sampled file so far is:

`assets/battle/map/stage_city-ca-da00101.unity3d`

That bundle contains:

- 698 `GameObject`s
- 698 `Transform`s
- 336 `MeshRenderer`s
- 336 `MeshFilter`s
- 290 colliders
- 346 MonoBehaviours
- 285 extracted tactical grid block records

The tactical layout hierarchy inside the bundle looks like:

`MapTool/Map/block_root/emptyblock/{enter,noenter,...}/empty X_Z`

Important scripts/components:

- `MapTool`
  - Has `width` and `height`.
  - Example: `stage_city-ca-da00101` is `20 x 20`.
- `MapProperty`
  - Has battle and camera bounds.
  - Example: `boundMin = (-2,0,-2)`, `boundMax = (16,0,19)`.
- `BlockProperty`
  - Attached to individual grid/tile objects.
  - Has at least `type` and `isGamepadCursorMovable`.
- `BattleGrassData`
  - Has grass instance metadata and `blockPos` values tied back to grid cells.

The current working interpretation is:

- The Unity scene hierarchy stores the visible level art.
- The `MapTool` hierarchy stores the tactical grid.
- Tile object names and paths expose grid coordinates, for example `empty 7_15`.
- Tile transforms expose X/Z coordinates and Y elevation.
- `enter` versus `noenter` path segments probably distinguish walkable and
  blocked/invalid cells.
- `BlockProperty.type` is a still-unknown tile category enum.

## What Has Been Done

Created a read-only probing folder:

`level_probe`

The tools read from the Steam install and write only into this repo.

Current tools:

- `survey_level_candidates.py`
  - Finds likely level/map/scene files and directories.
- `bundle_object_inventory.py`
  - Counts Unity object types inside candidate bundles.
- `dump_scene_layout.py`
  - Dumps GameObjects, transforms, colliders, and MonoBehaviours for one bundle.
- `monobehaviour_probe.py`
  - Summarizes MonoBehaviour script names and serialized field samples.
- `search_level_textassets.py`
  - Searches known Unity TextAssets/config bundles for level-related terms.
- `extract_battle_grid.py`
  - Extracts likely tactical grid records from one battle map bundle.

Important generated reports:

- `level_probe/reports/level_layout_findings.md`
- `level_probe/reports/level_candidate_dirs.csv`
- `level_probe/reports/bundle_object_inventory.csv`
- `level_probe/reports/stage_city-ca-da00101_grid_blocks.csv`
- `level_probe/reports/stage_city-ca-da00101_map_metadata.json`

## What A Browser Visualizer Needs

A useful first visualizer does not need to perfectly reproduce Unity rendering.
It should answer these questions first:

- What does the map geometry look like?
- Where are the walkable and blocked tiles?
- How does tile elevation line up with visible geometry?
- Which objects are props, collision, terrain, grass, water, lighting, etc.?

The practical target is a hybrid viewer:

1. Render extracted mesh geometry as Three.js meshes.
2. Overlay tactical grid cells from `extract_battle_grid.py`.
3. Color-code `enter`, `noenter`, and `BlockProperty.type`.
4. Let the user toggle layers: meshes, colliders, grid, lights, props, grass.
5. Inspect selected objects/tiles and show original Unity path/component data.

## Proposed Pipeline

### 1. Export A Bundle To Intermediate JSON

Create a tool like:

`level_probe/export_scene_for_web.py`

For one `.unity3d` map bundle, it should write an output folder under
`extracted/web_levels/<map_name>/`.

Initial output:

- `scene.json`
  - GameObject names
  - hierarchy paths
  - parent/child relationships
  - local/world transforms
  - component type list
  - mesh/material references
  - collider references
  - script names and useful MonoBehaviour fields
- `grid.json`
  - Converted version of `<map>_grid_blocks.csv`
  - per-cell X/Y/Z, walkability bucket, `BlockProperty.type`, source path
- `metadata.json`
  - map bundle path
  - map dimensions
  - bounds
  - object counts

This JSON layer is important because the browser should not need to understand
Unity serialized files.

### 2. Export Meshes

Use UnityPy to read `MeshFilter.m_Mesh` and `MeshRenderer` pairings.

Possible output options:

- Best long-term: export a `.glb` or `.gltf` scene.
- Easier first pass: export custom JSON buffers for positions, normals, UVs, and
  indices, then create `BufferGeometry` in Three.js.

Recommended route: produce glTF/GLB once the transform/material mapping is clear.
Three.js loads glTF reliably, and a GLB can package geometry and textures cleanly.

Important details to solve:

- Preserve Unity transform hierarchy.
- Convert Unity coordinate conventions to Three.js if needed.
- Preserve mesh local transforms separately from GameObject transforms.
- Handle negative scales and rotations correctly.
- Deduplicate shared meshes and materials.

### 3. Export Textures And Materials

Use UnityPy to extract `Texture2D` assets referenced by materials.

First-pass material strategy:

- Use `MeshBasicMaterial` or `MeshStandardMaterial`.
- Use base color/albedo texture where available.
- Use a neutral fallback color when the shader/material cannot be decoded.
- Ignore complex Unity shader graphs initially.

Later material improvements:

- Normal maps
- Emission maps
- Alpha cutout/transparency
- Water materials
- Vegetation/grass billboards
- Lightmaps, if present and traceable

### 4. Export Colliders

Use existing collider dumps as a separate debug layer.

First pass:

- `BoxCollider` as transparent boxes.
- `MeshCollider` as wireframe meshes if the linked mesh is readable.

This will help validate walkable/no-enter cells against actual level collision.

### 5. Render The Tactical Grid

Use `extract_battle_grid.py` data.

Three.js representation:

- One flat or slightly raised square per grid cell.
- Position from tile transform X/Y/Z.
- Color by path bucket:
  - `enter`: green/blue
  - `noenter`: red/gray
  - unknown/other: yellow
- Optional secondary color or label from `BlockProperty.type`.
- Add hover/select picking for cell details.

This should be the first browser milestone because it is already extractable.

### 6. Build The Web Viewer

Suggested minimal app:

- Vite + TypeScript + Three.js.
- `OrbitControls` for navigation.
- `GLTFLoader` if using GLB/GLTF.
- A side inspector panel for selected object/tile metadata.
- Layer toggles for:
  - scene meshes
  - tactical grid
  - colliders
  - lights
  - object names

The viewer can load a map folder such as:

`extracted/web_levels/stage_city-ca-da00101/metadata.json`

Then fetch:

- `scene.glb` or mesh JSON
- `grid.json`
- optional `colliders.json`
- optional textures

## Suggested Milestones

### Milestone 1: Grid-Only Viewer

Goal: render the tactical grid in Three.js from extracted JSON.

Tasks:

- Convert `<map>_grid_blocks.csv` to `grid.json`.
- Build a small Three.js page that draws elevated colored squares.
- Add orbit camera and cell hover/selection.
- Validate coordinates against `MapTool.width`, `height`, and bounds.

This proves the browser viewer and grid extraction without tackling Unity meshes.

### Milestone 2: Collider Overlay

Goal: render grid plus debug colliders.

Tasks:

- Export `BoxCollider` records to `colliders.json`.
- Draw transparent boxes at transformed positions.
- Compare collider layer with grid cells.

This helps validate walkability and height.

### Milestone 3: Raw Mesh Geometry

Goal: render untextured level geometry.

Tasks:

- Export mesh vertices/indices/normals from `MeshFilter` objects.
- Apply GameObject transforms.
- Render with neutral materials.
- Add toggles for mesh/collider/grid layers.

This proves the visible map can be reconstructed.

### Milestone 4: Textured Geometry

Goal: apply extracted texture/material data.

Tasks:

- Extract referenced `Texture2D` assets.
- Map material main textures to Three.js materials.
- Handle alpha cutouts for foliage/fences where possible.
- Deduplicate resources.

This makes the map recognizable.

### Milestone 5: glTF/GLB Export

Goal: replace custom mesh JSON with a standard web asset.

Tasks:

- Create `scene.glb` for each map.
- Store metadata/grid/collider overlays as JSON next to it.
- Load GLB in Three.js with `GLTFLoader`.

This makes the pipeline more maintainable and compatible with other tools.

### Milestone 6: Gameplay Metadata

Goal: show mission/spawn/objective data if found.

Tasks:

- Search `db_lua.bytes`, `db_template.unity3d`, and related config bundles for
  stage-to-map links.
- Identify spawn marker scripts or external spawn tables.
- Render spawn points, enemy waves, objectives, and triggers as overlays.

## Risks And Unknowns

- Unity material/shader fidelity may be hard. A browser viewer can still be
  useful with approximate materials.
- Some meshes or textures may be in dependent bundles, not the map bundle itself.
  `asset_dep.unity3d` may be needed to chase dependencies.
- Some gameplay data may be server-side or packed in tables not decoded yet.
- `BlockProperty.type` enum values need correlation across maps.
- Particles, timeline effects, camera post-processing, and custom shaders should
  be treated as later polish, not first-pass requirements.

## Immediate Next Steps

1. Create `export_grid_json.py` to turn `<map>_grid_blocks.csv` and
   `<map>_map_metadata.json` into a compact web-ready `grid.json`.
2. Create a new web app folder, likely `web_level_viewer/`.
3. Render `stage_city-ca-da00101` as a colored elevated grid in Three.js.
4. Add cell picking and an inspector panel.
5. Add collider export/rendering.
6. Start mesh extraction once grid alignment looks correct.

