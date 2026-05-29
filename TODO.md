FIXED
 python .\level_probe\extract_battle_grid.py --bundle battle/map/battle000_007-spcl.unity3d && python .\level_probe\dump_scene_layout.py --bundle battle/map/battle000_007-spcl.unity3d && python .\level_probe\export_grid_json.py --map battle000_007-spcl && python .\level_probe\export_mesh_json.py --map battle000_007-spcl && python .\level_probe\export_level_index.py && start "" cmd /k python .\server.py && timeout /t 3 >nul && start "" "http://localhost:5173/web_level_viewer/?map=battle000_007-spcl"
 
FIXED
 python .\level_probe\extract_battle_grid.py --bundle battle/map/battle000_008.unity3d && python .\level_probe\dump_scene_layout.py --bundle battle/map/battle000_008.unity3d && python .\level_probe\export_grid_json.py --map battle000_008 && python .\level_probe\export_mesh_json.py --map battle000_008 && python .\level_probe\export_level_index.py && start "" cmd /k python .\server.py && timeout /t 3 >nul && start "" "http://localhost:5173/web_level_viewer/?map=battle000_008


--NOTE still some broken here

start "" cmd /k python .\server.py && timeout /t 3 >nul && start "" "http://localhost:5173/web_level_viewer/?map=stage_alm-os-da00201"

BUG: https://spotco.github.io/SwordOfConvallaria_LevelPreview/?map=stage_alm-os-da00201
	billboard sprites tree03 (3) not facing toward camera
	
BUG: http://localhost:5173/web_level_viewer/?map=stage_desert-os-da01201
	tree (5) texture missing transparency
	
BUG: http://localhost:5173/web_level_viewer/?map=stage_plain-cp-ni00301
	StageAnimation-trees000-shadow not facing toward camera, and missing transparency