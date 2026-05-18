# Web Level Viewer

Static grid-first viewer for extracted Sword of Convallaria battle maps.
It renders tactical grid tiles and, when present, box collider overlays from
`colliders.json` plus untextured raw mesh geometry from `meshes.json`.

Generate the default map data:

```powershell
python .\level_probe\export_grid_json.py --map stage_city-ca-da00101
python .\level_probe\export_mesh_json.py --map stage_city-ca-da00101
python .\level_probe\export_level_index.py
```

This writes:

- `extracted/web_levels/<map>/grid.json`
- `extracted/web_levels/<map>/colliders.json`
- `extracted/web_levels/<map>/meshes.json`
- `extracted/web_levels/index.json`

The exporters now write grid, collider, mesh, and default-camera data in a
camera-aligned export frame, so the viewer can use a normal non-mirrored
orthographic camera and normal controls.

The mesh exporter handles Unity static batching by drawing only the renderer's
assigned submesh range. This avoids duplicating the whole combined mesh for
every `MeshFilter`.

It also reads `asset_dep.unity3d` and loads dependency bundles while exporting,
so shared meshes in bundles such as `share/fbx/share_fbx*` can be resolved
without exporting unrelated objects from those shared bundles.

The viewer uses `index.json` for the left map menu. Exported maps are clickable;
maps without exported `grid.json` are shown disabled.

Serve the repository root:

```powershell
python -m http.server 5173
```

Open:

```text
http://localhost:5173/web_level_viewer/
```

Use a different exported map with:

```text
http://localhost:5173/web_level_viewer/?map=battle001
```

Or load an explicit JSON path:

```text
http://localhost:5173/web_level_viewer/?data=/extracted/web_levels/stage_city-ca-da00101/grid.json
```
