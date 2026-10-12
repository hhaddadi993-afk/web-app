# -*- coding: utf-8 -*-
"""My Tools menu for Maya  -  one place that lists every tool of the pipeline.

Loaded at Maya start-up by the block that install.py adds to userSetup.py.
To add a tool: add ONE line to TOOLS (label, module name, function) - nothing else.

Each click re-imports (reloads) the module, so edits to a tool are picked up
without restarting Maya.
"""
import importlib
import importlib.util
import os
import re
import sys
import traceback

import maya.cmds as cmds

MENU_NAME = "myToolsPipelineMenu"

# (menu label, module, function to call)  -  None = divider
# A module that ends with a top-level show() call opens itself on import; this is
# detected automatically, so the function is only called when it does not.
TOOLS = [
    ("Mi -> Hair (swap + XGen)...", "mi_to_hair", "show"),
    ("Char Pipeline Tool...", "char_pipeline_tool", "show"),
    None,
    ("ABC Export by Namespace...", "abc_export_by_namespace", "show"),
    ("XGen: Assign Houdini Cache...", "xgen_assign_houdini_cache", "show"),
]


def pipeline_root():
    """Folder that holds maya/ and houdini/ (set by Maya.env, else derived from this file)."""
    root = os.environ.get("MY_PIPELINE_ROOT")
    if root and os.path.isdir(root):
        return root.replace("\\", "/")
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__))).replace("\\", "/")


def _opens_itself(module_name):
    """True if the module file has a top-level show() call (runs on import)."""
    try:
        spec = importlib.util.find_spec(module_name)
        if not spec or not spec.origin or not os.path.isfile(spec.origin):
            return False
        with open(spec.origin, encoding="utf-8", errors="ignore") as f:
            return re.search(r"^show\(\)", f.read(), re.M) is not None
    except Exception:
        return False


def launch(module_name, func_name):
    try:
        if module_name in sys.modules:
            mod = importlib.reload(sys.modules[module_name])
            opened = _opens_itself(module_name)
        else:
            mod = importlib.import_module(module_name)
            opened = _opens_itself(module_name)
        if not opened:
            getattr(mod, func_name)()
    except ImportError:
        cmds.confirmDialog(
            title="My Tools", button=["OK"],
            message="Tool '%s' was not found.\n\nExpected in:\n%s/maya/%s.py"
                    % (module_name, pipeline_root(), module_name))
    except Exception:
        traceback.print_exc()
        cmds.warning("My Tools: '%s' failed - see the Script Editor." % module_name)


def create_menu():
    if cmds.about(batch=True):
        return
    if cmds.menu(MENU_NAME, exists=True):
        cmds.deleteUI(MENU_NAME, menu=True)
    cmds.menu(MENU_NAME, label="My Tools", parent="MayaWindow", tearOff=True)
    for item in TOOLS:
        if item is None:
            cmds.menuItem(divider=True, parent=MENU_NAME)
            continue
        label, mod, fn = item
        cmds.menuItem(label=label, parent=MENU_NAME,
                      command=lambda *_, m=mod, f=fn: launch(m, f))
    cmds.menuItem(divider=True, parent=MENU_NAME)
    cmds.menuItem(label="Reload this menu", parent=MENU_NAME,
                  command=lambda *_: launch_reload())
    cmds.menuItem(label="Open pipeline folder", parent=MENU_NAME,
                  command=lambda *_: _open_folder(pipeline_root()))


def launch_reload():
    importlib.reload(sys.modules[__name__])
    sys.modules[__name__].create_menu()


def _open_folder(path):
    try:
        if sys.platform.startswith("win"):
            os.startfile(path)                  # noqa
        else:
            cmds.launch(openURL=path)
    except Exception as e:
        cmds.warning("Cannot open %s: %s" % (path, e))
