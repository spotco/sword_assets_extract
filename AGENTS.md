# Project Notes For Agents

## Sword Level Browser Rendering

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
8. Next milestone: resolve dependent mesh/material bundles and move toward textured glTF/GLB export.

Mesh export caveat:

- Unity static batching reuses large `Combined Mesh` assets across many renderers.
- For static-batched renderers, only export `m_StaticBatchInfo.firstSubMesh` through `subMeshCount`.
- Static-batched combined vertices are already in scene space; do not apply the GameObject transform again.

Useful first target:

```powershell
python .\level_probe\export_grid_json.py --map stage_city-ca-da00101
python .\level_probe\export_mesh_json.py --map stage_city-ca-da00101
python -m http.server 5173
```

Then open:

```text
http://localhost:5173/web_level_viewer/
```
