import os, re, hou

def _clipboard_text():
    txt = ""
    try:
        txt = hou.ui.getTextFromClipboard() or ""
    except Exception:
        pass
    if not txt:
        try:
            from PySide2 import QtWidgets
            txt = QtWidgets.QApplication.clipboard().text() or ""
        except Exception:
            pass
    if not txt.strip():
        return ""
    p = txt.strip().splitlines()[0].strip().strip('"').strip("'")
    if p.lower().startswith("file:///"):
        p = p[8:]
    return p

def _hip_ext():
    lic = hou.licenseCategory()
    if lic == hou.licenseCategoryType.Apprentice:
        return ".hipnc"
    if lic == hou.licenseCategoryType.Indie:
        return ".hiplc"
    return ".hip"

def _shot_name(folder):
    parts = folder.replace("\\", "/").rstrip("/").split("/")
    for p in reversed(parts):
        if re.match(r"(?i)^shot", p):
            return p
    # fallback: parent of from_maya / hair_sim
    for p in reversed(parts):
        if p.lower() not in ("from_maya", "hair_sim", ""):
            return p
    return "shot"

def _next_version(folder, base, ext):
    rx = re.compile(r"^" + re.escape(base) + r"_v(\d+)\.hip(nc|lc)?$", re.IGNORECASE)
    hi = 0
    for f in os.listdir(folder):
        m = rx.match(f)
        if m:
            hi = max(hi, int(m.group(1)))
    return "{0}_v{1:03d}{2}".format(base, hi + 1, ext)

def run():
    path = _clipboard_text()
    if not path:
        hou.ui.displayMessage("Clipboard is empty.\nCopy the from_maya folder path first.",
                              severity=hou.severityType.Warning)
        return

    path = os.path.normpath(path)
    folder = os.path.dirname(path) if os.path.splitext(path)[1] else path

    if not os.path.isdir(folder):
        if hou.ui.displayMessage("Folder does not exist:\n\n" + folder + "\n\nCreate it?",
                                 buttons=("Create", "Cancel"), default_choice=0,
                                 close_choice=1) != 0:
            return
        os.makedirs(folder)

    base = _shot_name(folder) + "_hair_sim"
    suggested = _next_version(folder, base, _hip_ext())

    btn, name = hou.ui.readInput(
        "Save the current scene into:\n\n" + folder + "\n\nFile name:",
        buttons=("Save", "Cancel"), default_choice=0, close_choice=1,
        initial_contents=suggested, title="Save HIP to Clipboard Path")
    if btn != 0 or not name.strip():
        return

    name = name.strip()
    if not re.search(r"\.hip(nc|lc)?$", name, re.IGNORECASE):
        name += _hip_ext()
    target = os.path.join(folder, name)

    if os.path.exists(target):
        if hou.ui.displayMessage("File already exists:\n\n" + target + "\n\nOverwrite?",
                                 buttons=("Overwrite", "Cancel"), default_choice=1,
                                 close_choice=1, severity=hou.severityType.Warning) != 0:
            return

    hou.hipFile.save(file_name=target.replace("\\", "/"))
    hou.ui.setStatusMessage("Saved: " + target, severity=hou.severityType.Message)
    print("[My Tools] Saved HIP: " + target)

run()
