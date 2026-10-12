# -*- coding: utf-8 -*-
"""One-time (re-runnable) installer: hooks this folder into Maya and Houdini.

    python install.py                 # install for the newest Maya / Houdini found
    python install.py --maya 2023 --houdini 22.0
    python install.py --dry-run       # show what would change, write nothing
    python install.py --uninstall

What it does (only between  # >>> MY_PIPELINE ... # <<< MY_PIPELINE  markers, so your own lines stay):
  Maya     Documents/maya/<ver>/Maya.env             MY_PIPELINE_ROOT = <this folder>
           Documents/maya/<ver>/scripts/userSetup.py  adds maya/ to sys.path + builds the "My Tools" menu
  Houdini  Documents/houdini<ver>/packages/my_pipeline.json   adds houdini/ to HOUDINI_PATH
           -> the "My Tools" menu comes from houdini/MainMenuCommon.xml in THIS folder
              (an old copy in Documents/houdini<ver>/ is renamed to .bak: it would duplicate the menu)

Move or rename this folder -> run install.py again.  Plain Python 3, no Maya/Houdini needed.
"""
import argparse
import glob
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.abspath(__file__)).replace("\\", "/")
BEGIN = "# >>> MY_PIPELINE  (managed by install.py - do not edit between the markers)"
END = "# <<< MY_PIPELINE"
BLOCK_RX = re.compile(r"[ \t]*# >>> MY_PIPELINE.*?# <<< MY_PIPELINE[ \t]*\n?", re.S)

USERSETUP_BODY = '''import os as _mp_os, sys as _mp_sys
try:
    _mp_root = _mp_os.environ.get("MY_PIPELINE_ROOT") or r"{root}"
    _mp_path = _mp_root + "/maya"
    if _mp_path not in _mp_sys.path:
        _mp_sys.path.insert(0, _mp_path)
    import maya.cmds as _mp_cmds
    import my_tools_maya
    _mp_cmds.evalDeferred(my_tools_maya.create_menu)
except Exception as _mp_e:
    print("[My Pipeline] could not build the menu: %s" % _mp_e)'''


def documents():
    return os.path.join(os.path.expanduser("~"), "Documents")


def upsert_block(path, body, remove=False, dry=False):
    text = ""
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            text = f.read()
    stripped = BLOCK_RX.sub("", text).rstrip("\n")
    if remove:
        new = (stripped + "\n") if stripped else ""
        if not text:
            return "nothing to remove: " + path
    else:
        new = (stripped + "\n\n" if stripped else "") + BEGIN + "\n" + body + "\n" + END + "\n"
    if new == text:
        return "unchanged: " + path
    if not dry:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if text and not os.path.isfile(path + ".bak_pipeline"):
            with open(path + ".bak_pipeline", "w", encoding="utf-8", newline="\n") as f:
                f.write(text)                     # one-time backup of the original
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(new)
    return ("would update: " if dry else "updated: ") + path


def maya_dir(version):
    base = os.path.join(documents(), "maya")
    if version:
        return os.path.join(base, version)
    found = sorted(d for d in glob.glob(os.path.join(base, "20*")) if os.path.isdir(d))
    return found[-1] if found else None


def houdini_dir(version):
    base = documents()
    if version:
        return os.path.join(base, "houdini" + version)
    found = sorted(d for d in glob.glob(os.path.join(base, "houdini2*")) if os.path.isdir(d))
    return found[-1] if found else None


def install_maya(mdir, remove, dry):
    out = []
    out.append(upsert_block(os.path.join(mdir, "Maya.env"),
                            "MY_PIPELINE_ROOT = " + ROOT, remove, dry))
    out.append(upsert_block(os.path.join(mdir, "scripts", "userSetup.py"),
                            USERSETUP_BODY.format(root=ROOT), remove, dry))
    return out


def install_houdini(hdir, remove, dry):
    out = []
    pkg = os.path.join(hdir, "packages", "my_pipeline.json")
    if remove:
        if os.path.isfile(pkg) and not dry:
            os.remove(pkg)
        out.append(("would remove: " if dry else "removed: ") + pkg)
    else:
        data = {"enable": True,
                "env": [{"MY_PIPELINE_ROOT": ROOT}],
                "hpath": ROOT + "/houdini"}
        if not dry:
            os.makedirs(os.path.dirname(pkg), exist_ok=True)
            with open(pkg, "w", encoding="utf-8", newline="\n") as f:
                json.dump(data, f, indent=2)
                f.write("\n")
        out.append(("would write: " if dry else "wrote: ") + pkg)
        old = os.path.join(hdir, "MainMenuCommon.xml")
        if os.path.isfile(old):
            if not dry:
                os.replace(old, old + ".bak")
            out.append(("would rename: " if dry else "renamed: ") + old + "  ->  .bak  (old copy = duplicate menu)")
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--maya", help="Maya version folder, e.g. 2023 (default: newest found)")
    ap.add_argument("--houdini", help="Houdini version, e.g. 22.0 (default: newest found)")
    ap.add_argument("--maya-dir", help="full path of the Maya prefs folder (overrides --maya)")
    ap.add_argument("--houdini-dir", help="full path of the Houdini prefs folder (overrides --houdini)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--uninstall", action="store_true")
    a = ap.parse_args(argv)

    if not os.path.isfile(os.path.join(ROOT, "houdini", "MainMenuCommon.xml")):
        print("houdini/MainMenuCommon.xml is missing - run:  python houdini/build_menu.py")
        return 1
    mdir = a.maya_dir or maya_dir(a.maya)
    hdir = a.houdini_dir or houdini_dir(a.houdini)
    lines = ["pipeline root: " + ROOT]
    if mdir:
        lines += ["MAYA    " + x for x in install_maya(mdir, a.uninstall, a.dry_run)]
    else:
        lines.append("MAYA    prefs folder not found (use --maya 2023 or --maya-dir)")
    if hdir:
        lines += ["HOUDINI " + x for x in install_houdini(hdir, a.uninstall, a.dry_run)]
    else:
        lines.append("HOUDINI prefs folder not found (use --houdini 22.0 or --houdini-dir)")
    print("\n".join(lines))
    print("\nRestart Maya and Houdini." if not a.dry_run and not a.uninstall else "")
    return 0


if __name__ == "__main__":
    sys.exit(main())
