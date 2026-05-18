# Project Notes For Agents

## Sword Level Browser Rendering

Fixed:

1. Export-space camera alignment is now handled during export instead of in the web viewport.
   The grid, mesh, and collider exporters rotate world-space data into a camera-aligned
   frame derived from the embedded `MapProperty.camera`, and the viewer now uses a normal
   non-mirrored orthographic projection with normal pan/rotate/movement controls.
   Reference evidence remains the same for `stage_city-ca-da00101`: Unity's embedded
   camera basis is not aligned with raw world X/Z, so low-X/high-Z objects such as
   `muqiao` must be transformed into camera-oriented export space to appear on the
   correct side of the in-game view.

Current level extraction evidence is documented in:

- `level_probe/reports/level_layout_findings.md`
- `level_probe/reports/threejs_level_visualizer_plan.md`

Immediate pipeline:

1. Export tactical grid reports to browser-ready JSON with `level_probe/export_grid_json.py`.
2. Export collider reports to `colliders.json` when `<map>_colliders.csv` and `<map>_scene_objects.csv` exist.
3. Load the generated map folder from `extracted/web_levels/<map_name>/`.
4. Render the tactical grid using tile X/Y/Z, walkability bucket, and `BlockProperty.type`.
5. Add hover/selection so each tile shows original path, position, type, and collider metadata.
6. Render box collider overlays for visual alignment checks.
7. Export readable embedded Unity meshes to `meshes.json` and render them as an untextured debug layer.
8. Load map dependency bundles from `asset_dep.unity3d` while exporting meshes, but export only objects from the requested map bundle.
9. Write `extracted/web_levels/index.json` so the viewer can show all battle maps and grey out maps that have not been exported.
10. Export material metadata and textures to `materials.json` + `textures/*.png`; render meshes with their diffuse texture in the web viewer using a "Textured" toggle.
11. Next milestone: investigate additional texture slots (`_BumpMap`, `_EmissionMap`, specular), handle transparent/water materials separately, and support batch-exporting all maps.

Mesh export caveat:

- Unity static batching reuses large `Combined Mesh` assets across many renderers.
- For static-batched renderers, only export `m_StaticBatchInfo.firstSubMesh` through `subMeshCount`.
- Static-batched combined vertices are already in scene space; do not apply the GameObject transform again.
- Map bundles reference shared meshes in dependency bundles such as `share/fbx/share_fbx*`.
  `export_mesh_json.py` resolves those through `asset_dep.unity3d`.
- Remaining `unity default resources` misses are Unity built-ins, not normal game asset bundles.

Material/texture export:

- `export_mesh_json.py` now writes `materials.json` and `textures/*.png` alongside `meshes.json`.
- It reads `m_Materials` from each MeshRenderer, resolves the `Material` PPtr (including across dep bundles), and reads `m_SavedProperties.m_TexEnvs`.
- Main diffuse texture is detected by slot name: `_MainTex`, `_BaseMap`, `_AlbedoMap`, `_DiffuseMap`.
- Texture2D objects are decoded via UnityPy's `.image` (PIL) and saved as PNG. Already-exported PNGs are skipped on re-run.
- The viewer applies the main texture via `THREE.MeshBasicMaterial` (unlit, preserves baked lighting) when "Textured" is checked.

Useful first target:

```powershell
# Full pipeline for a new map (server.py runs all 5 steps automatically via the Extract button):
python .\level_probe\extract_battle_grid.py --bundle battle/map/stage_city-ca-da00101.unity3d
python .\level_probe\dump_scene_layout.py --bundle battle/map/stage_city-ca-da00101.unity3d
python .\level_probe\export_grid_json.py --map stage_city-ca-da00101
python .\level_probe\export_mesh_json.py --map stage_city-ca-da00101
python .\level_probe\export_level_index.py
python .\server.py
```

Then open:

```text
http://localhost:5173/web_level_viewer/
```
