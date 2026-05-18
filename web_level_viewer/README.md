# Web Level Viewer

Static grid-first viewer for extracted Sword of Convallaria battle maps.
It renders tactical grid tiles and, when present, box collider overlays from
`colliders.json` plus untextured raw mesh geometry from `meshes.json`.

## Build a GitHub Pages bundle

Run from the repository root:

```powershell
.\build_sword_level_preview.ps1
```

This script:

- stages a small static-site build with relative viewer URLs
- points the viewer at `https://raw.githubusercontent.com/spotco/SwordOfConvallaria_LevelPreview/main/web_levels`
- writes the final publishable folder to `..\SwordOfConvallaria_LevelPreview`

The packaged folder contains:

- `index.html`
- `app.js`, `styles.css`, `vendor/`
- `static_assets/`
- `.nojekyll`

You can override the remote source:

```powershell
.\build_sword_level_preview.ps1 -RemoteAssetBase "https://raw.githubusercontent.com/spotco/SwordOfConvallaria_LevelPreview/main/web_levels"
```

The packaged viewer expects that remote repository to contain `web_levels/index.json` plus per-map folders. Right now `spotco/SwordOfConvallaria_LevelPreview` is empty, so the built viewer will not load maps until those files are pushed there.

You can push the contents of `..\SwordOfConvallaria_LevelPreview` to a GitHub Pages branch or repository as a static site while keeping the heavy data files in the separate raw-file repository.

The viewer HTML now comes from a single shared template, `web_level_viewer/index.template.html`. `server.py` renders that template for local development with local asset/API roots, and `build_sword_level_preview.ps1` renders the same template for the packaged static build.

Shared static assets live under `web_level_viewer/static_assets/`. That folder is available in local development through `server.py` and is copied into the packaged preview build as-is.

## Full level-preview publish workflow

To rebuild the sibling `..\SwordOfConvallaria_LevelPreview` folder with both the viewer shell and `web_levels` data:

1. Extract all battle maps into this repo's local `extracted\web_levels` tree:

```powershell
.\extract_all_levels.ps1
```

2. Build or refresh the static viewer files in the sibling preview repo:

```powershell
.\build_sword_level_preview.ps1
```

3. Copy the extracted `web_levels` tree into that sibling preview repo:

```powershell
.\copy_extracted_web_levels_to_levelpreview.ps1
```

Current behavior:

- `extract_all_levels.ps1` refreshes `extracted\web_levels\index.json`, then extracts every map listed there into `extracted\web_levels\<map>\...`
- `build_sword_level_preview.ps1` overwrites only the generated viewer files in `..\SwordOfConvallaria_LevelPreview` and does not delete `web_levels`
- `copy_extracted_web_levels_to_levelpreview.ps1` overwrites `..\SwordOfConvallaria_LevelPreview\web_levels`

What is still required after those scripts run:

- commit and push the contents of `..\SwordOfConvallaria_LevelPreview` to the branch used by the raw URL, because the packaged viewer fetches assets from `raw.githubusercontent.com`
- make sure the raw URL branch in `build_sword_level_preview.ps1` matches the branch you actually push

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

Run the local dev server:

```powershell
python .\server.py
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
http://localhost:5173/web_level_viewer/?data=../extracted/web_levels/stage_city-ca-da00101/grid.json
```

## GitHub Pages restrictions

GitHub Pages is static hosting only, so the packaged site has these limits:

- no `/api/*` endpoints, so in-browser extraction is unavailable there
- no server-side logging endpoint, so viewer debug POSTs are disabled in the packaged build
- all required level JSON, meshes, materials, and textures must exist in the remote raw-file repository ahead of time
- the site may be served from a repository subpath like `/repo-name/`, so relative URLs are required; root-absolute `/extracted/...` URLs are not safe for project pages
- moving assets to raw file hosting avoids the GitHub Pages published-site size limit for the viewer repo, but the remote asset repository is still subject to normal GitHub repository and file-size constraints

The packaged viewer is built around those restrictions. Local development still supports the `server.py` extraction workflow.
