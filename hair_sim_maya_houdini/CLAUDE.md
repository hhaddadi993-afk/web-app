# Hair Sim Pipeline Tools (Maya 2023 <-> Houdini 22 FX)

The user is a Persian-speaking FX/CFX artist. **Reply in Persian (Farsi)**, keep code, paths and
UI labels in English. Work step by step; they test each step in Maya/Houdini and report back.
They are on Windows, Intel i9-14900K (32 threads), 64 GB RAM, studio Houdini 22 FX license.
Most scripts can't be run in the cloud session (no Maya/Houdini) - test logic with mocks, check
syntax, and say what was not tested live.

## Pipeline (per shot, ~10 animal characters, e.g. wildebeest)

```
Maya anim scene (.../SC_42/shot_042_20a/hair_sim/<scene>.mb)
  1. maya/abc_export_by_namespace.py      -> hair_sim/from_maya/<namespace>.abc   (one per character)
  2. Houdini: My Tools > Save HIP to Clipboard Path   -> hip saved INTO from_maya/ ($HIP = from_maya)
  3. Houdini: My Tools > Batch Hair Sim: Setup SETUP_RUN  (/obj/alembic_import_all/SETUP_RUN)
       per character -> $HIP/from_houdini/<char>/<part>.abc   (part = mane / beard / tail)
  4. maya/xgen_assign_houdini_cache.py     -> each XGen description gets its own guide cache
```

Naming contract: **Maya namespace == alembic file name == Houdini $CHAR == folder in from_houdini ==
XGen collection namespace.** Part name comes from the Houdini node name:
`rop_mane_static` -> `mane` (strip `filecache_`/`rop_`/`cache_` prefix and `_static` suffix).

## Layout

| Path | What |
|---|---|
| `install.py` | Run once (`python install.py`, `--dry-run`, `--uninstall`): writes marked `MY_PIPELINE` blocks into Maya.env + userSetup.py and a Houdini package json (hpath = `houdini/`). Menus then load from THIS folder |
| `maya/my_tools_maya.py` | Builds the Maya "My Tools" menu from the `TOOLS` list (one line per tool; reloads the module on every click) |
| `maya/mi_to_hair.py` | Finds `_mi_` namespaces, locates `<id>_hair_fn.mb` under `Assets_FN/characters`, swaps the reference (namespace first), verifies XGen collections vs `.xgen` files. Reuses `char_pipeline_tool` |
| `maya/char_pipeline_tool.py` | Maya plug-in: rest->anim transition, swap _lo_/_mi_ version, replace with file, XGen-safe namespace rename |
| `maya/abc_export_by_namespace.py` | **NOT IN THIS REPO YET** - PySide2 window, one .abc per top namespace into `<scene dir>/from_maya/`; start 950, end = last frame of `cam_XXXX_YYYY` +1 |
| `maya/xgen_assign_houdini_cache.py` | **NOT IN THIS REPO YET** - sets cacheFileName/useCache/liveMode per XGen description from `from_houdini/<char>/*.abc` (longest part-name match) |
| `houdini/MainMenuCommon.xml` | **Generated** "My Tools" menu. Install to `Documents/houdini22.x/`. Never hand-edit |
| `houdini/build_menu.py` | Rebuilds the XML from `houdini/src/`. Run after EVERY source change (`--check` = syntax only) |
| `houdini/src/my_tools_load_abc_clipboard.py` | Menu item: abc path from clipboard -> geo + alembic + unpack + xform 0.01 + OUT |
| `houdini/src/my_tools_save_hip_clipboard.py` | Menu item: save hip into clipboard folder as `<shot>_hair_sim_v###.hip` (auto version) |
| `houdini/src/install_template.py` | Menu item "Batch Hair Sim: Setup SETUP_RUN"; embeds `session_code.py` (placeholder `__SESSION_SRC__`), builds the SETUP_RUN UI |
| `houdini/src/session_code.py` | All runtime logic (`hou.session.hb_*(kwargs)`), written into the hip's Session Module between `# >>> HAIR_BATCH` / `# <<< HAIR_BATCH` |

## Naming (Maya assets)
Anim rig file/namespace `####_#_mi_rig_fn` -> hair file `####_#_hair_fn.mb` (own folder under `Maya/Assets_FN/characters/...hair...`).
After Mi->Hair the namespace is the hair file name (+ trailing number of the old one).

## SETUP_RUN (tab "Batch Hair Sim")
1. Pick Character - abc_folder ($HIP), char, abc_node
2. Output Paths - cache_root, sim_nodes, export_root, export_nodes, start/end (950-1103), solver start, timeline
3. Run - run_chars patterns (`*`, `wildebeest_*`, `^zebra_01`), Run Mode `direct` (default) / `cache`, Check Paths, Run Current, RUN ALL
4. Run in Background - parallel hython workers (bg_slots 4, bg_min_ram 12 GB as a *start* condition),
   worker at `$HIP/local_farm/hair_worker.py`, logs `$HIP/local_farm/logs/`. Houdini must stay open.

## Decisions / lessons (don't redo)
- Vellum in a for-each doesn't advance in time -> per-character runs.
- One sim ~14% CPU (~4-5 threads), ~9 GB RAM -> parallel local sims are the speed-up.
- Other PCs without Houdini can't help; user rejected Deadline (licenses). Deadline code was REMOVED.
- alembic fileName must be built from `abc_folder` + `char` (never from `abc_path`) -> recursion error.
- Vellum solvers inside locked HDAs are skipped (`isInsideLockedHDA`).
- Old parm values survive a template rebuild -> display parms are reset with revertToDefaults.
- Direct mode bypasses the File Caches; their bypass state is restored after each run.
- Postponed: shared `my_pipeline` folder + Houdini package json + Maya.env.

## Backlog
See `REVIEW.fa.md`.
