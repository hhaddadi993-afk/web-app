# hair_sim_maya_houdini

Maya <-> Houdini hair-sim pipeline tools (batch export from Maya, batch Vellum sim in Houdini,
cache assignment back onto XGen). See `CLAUDE.md` for the pipeline and naming contract.

```
python houdini/build_menu.py          # regenerate houdini/MainMenuCommon.xml
python houdini/build_menu.py --check  # syntax-check sources only
```

## Install (menus in Maya + Houdini)
```
python install.py --dry-run   # preview
python install.py             # Maya.env + userSetup.py + Houdini package; restart both apps
```
