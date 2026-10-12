# -*- coding: utf-8 -*-
"""Mi -> Hair  -  turn every animated '_mi_' rig in the scene into its hair character.

  * finds references whose namespace contains '_mi_'        (0123_1_mi_rig_fn)
  * looks up its hair file in the project's Assets_FN/characters tree   (0123_1_hair_fn.mb)
  * swaps the reference (namespace is renamed FIRST, so XGen builds its collections with the final name)
  * checks that the XGen collection(s) of the hair file are loaded and reports the .xgen files beside it

Namespace after the swap = hair file name (+ trailing number of the old namespace, like Step 3 of
Char Pipeline Tool) - so  Maya namespace == alembic name == Houdini $CHAR  still holds.

Open from  My Tools > Mi -> Hair (swap + XGen).  Reuses char_pipeline_tool.py (must sit beside it).
"""
import os
import re
import traceback

import maya.cmds as cmds

import char_pipeline_tool as cpt

QtWidgets, QtCore, QtGui = cpt.QtWidgets, cpt.QtCore, cpt.QtGui

TOKEN = "_mi_"
DEFAULT_PATTERN = "{id}_hair_fn"          # {id} = rig file name up to '_mi_'
HAIR_EXT = (".mb", ".ma")


# =============================================================================
#  Core logic (no UI)
# =============================================================================

def is_mi(ns):
    return TOKEN in ns.lower()


def char_id(info):
    """'0123_1_mi_rig_fn.mb' -> '0123_1'  (file name first, namespace as fallback)."""
    base = os.path.splitext(info["file"])[0]
    for src in (base, info["ns"]):
        i = src.lower().find(TOKEN)
        if i > 0:
            return src[:i]
    return None


def default_hair_roots():
    """<project or a parent>/(Maya/)Assets_FN/characters that exist."""
    p = (cmds.workspace(q=True, rootDirectory=True) or "").replace("\\", "/").rstrip("/")
    out = []
    for _ in range(5):
        if not p:
            break
        for rel in ("Assets_FN/characters", "Maya/Assets_FN/characters"):
            c = p + "/" + rel
            if os.path.isdir(c) and c not in out:
                out.append(c)
        parent = os.path.dirname(p)
        if parent == p:
            break
        p = parent
    return out


def index_files(roots):
    """{lower file base name: [paths]} for every .mb/.ma under the roots."""
    idx = {}
    for root in roots:
        for d, _dirs, files in os.walk(root):
            for f in files:
                b, e = os.path.splitext(f)
                if e.lower() in HAIR_EXT:
                    idx.setdefault(b.lower(), []).append(os.path.join(d, f).replace("\\", "/"))
    return idx


def pick_best(paths):
    """Prefer .mb, a 'hair' folder, then the newest file."""
    def key(p):
        parts = p.lower().split("/")[:-1]
        try:
            age = -os.path.getmtime(p)
        except OSError:
            age = 0
        return (not p.lower().endswith(".mb"), not any("hair" in s for s in parts), age)
    return sorted(paths, key=key)[0] if paths else None


def hair_name(cid, pattern):
    return pattern.replace("{id}", cid)


def hair_namespace(old_ns, hair_base):
    m = re.search(r"(\d+)$", old_ns)
    return hair_base + (m.group(1) if m else "")


def scan(roots, pattern, only=None):
    """One row per '_mi_' reference: where its hair file is and what the new namespace will be."""
    idx = index_files(roots) if roots else {}
    rows = []
    for rn in cpt.all_top_refs():
        info = cpt.ref_info(rn)
        if not info or not is_mi(info["ns"]):
            continue
        if only is not None and rn not in only:
            continue
        cid = char_id(info)
        base = hair_name(cid, pattern) if cid else None
        found = idx.get(base.lower(), []) if base else []
        path = pick_best(found)
        rows.append({
            "rn": rn, "ns": info["ns"], "file": info["file"], "id": cid,
            "hair": path, "alts": len(found), "base": base,
            "new_ns": hair_namespace(info["ns"], os.path.splitext(os.path.basename(path))[0]) if path else None,
            "xgen": cpt.xgen_files_beside(path) if path else [],
        })
    return rows


def convert(rows, rename_ns, log):
    cpt.ensure_xgen_plugin(log)
    done = 0
    for r in rows:
        if not r["hair"]:
            log("err", "%s: no hair file '%s' found - skipped." % (r["ns"], r["base"]))
            continue
        log("ok", "%s: %s  ->  %s" % (r["ns"], r["file"], os.path.basename(r["hair"])))
        if r["alts"] > 1:
            log("warn", "    %d files named %s found, using %s" % (r["alts"], r["base"], r["hair"]))
        final = cpt.swap_reference(r["rn"], r["hair"], r["new_ns"] if rename_ns else None, log)
        pals = cpt.ref_palettes(r["rn"])
        xf = cpt.xgen_files_beside(r["hair"])
        if len(pals) == len(xf):
            log("ok", "    XGen: %d collection(s) loaded, %d .xgen file(s) beside the hair file  [%s]"
                % (len(pals), len(xf), final))
        else:
            log("warn", "    XGen: %d collection(s) in scene but %d .xgen file(s) beside %s"
                % (len(pals), len(xf), os.path.basename(r["hair"])))
        done += 1
    return done


# =============================================================================
#  UI
# =============================================================================

class MiToHairUI(QtWidgets.QDialog):

    COLS = ["Namespace (mi)", "Hair file", "New namespace", "XGen files"]

    def __init__(self, parent=None):
        super(MiToHairUI, self).__init__(parent or cpt.maya_main_window())
        self.setWindowTitle("Mi -> Hair")
        self.setWindowFlags(QtCore.Qt.Window)
        self.setMinimumSize(900, 560)
        self.setStyleSheet(cpt.STYLE)
        self.settings = QtCore.QSettings("MiToHair", "UI")
        self.rows = []
        self._build()
        self.rescan()

    def _build(self):
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(8)
        t = QtWidgets.QLabel("Mi -> Hair")
        t.setObjectName("title")
        s = QtWidgets.QLabel("Finds every '_mi_' character, swaps it to its hair file and checks the XGen collection.")
        s.setObjectName("subtitle")
        root.addWidget(t)
        root.addWidget(s)

        form = QtWidgets.QFormLayout()
        self.root_le = QtWidgets.QLineEdit(self.settings.value("roots", ""))
        self.root_le.setPlaceholderText("empty = auto (…/Assets_FN/characters);  several folders separated by ;")
        b = QtWidgets.QPushButton("Browse...")
        b.clicked.connect(self._browse)
        rr = QtWidgets.QHBoxLayout()
        rr.addWidget(self.root_le, 1)
        rr.addWidget(b)
        self.pat_le = QtWidgets.QLineEdit(self.settings.value("pattern", DEFAULT_PATTERN))
        self.ns_cb = QtWidgets.QCheckBox("Rename namespace after the hair file (keeps trailing number)")
        self.ns_cb.setChecked(self.settings.value("rename", "true") == "true")
        form.addRow("Hair folder", rr)
        form.addRow("Hair file name", self.pat_le)
        form.addRow("", self.ns_cb)
        root.addLayout(form)

        self.tree = QtWidgets.QTreeWidget()
        self.tree.setHeaderLabels(self.COLS)
        self.tree.setRootIsDecorated(False)
        self.tree.itemDoubleClicked.connect(self._select_in_viewport)
        root.addWidget(self.tree, 1)

        row = QtWidgets.QHBoxLayout()
        for text, fn in (("Rescan", self.rescan),
                         ("Check All", lambda: self._check_all(True)),
                         ("Uncheck All", lambda: self._check_all(False))):
            btn = QtWidgets.QPushButton(text)
            btn.clicked.connect(fn)
            row.addWidget(btn)
        row.addStretch(1)
        root.addLayout(row)

        self.run_btn = QtWidgets.QPushButton("Convert checked  (Mi -> Hair)")
        self.run_btn.setObjectName("runAll")
        self.run_btn.clicked.connect(self.run)
        root.addWidget(self.run_btn)

        self.log_te = QtWidgets.QPlainTextEdit()
        self.log_te.setReadOnly(True)
        self.log_te.setMaximumHeight(150)
        root.addWidget(self.log_te)

    def _roots(self):
        txt = self.root_le.text().strip()
        if txt:
            return [p.strip().replace("\\", "/") for p in txt.split(";") if p.strip()]
        return default_hair_roots()

    def _browse(self):
        res = cmds.fileDialog2(fileMode=3, caption="Hair folder (e.g. …/Assets_FN/characters)")
        if res:
            self.root_le.setText(res[0])
            self.rescan()

    def rescan(self):
        self.tree.clear()
        roots = self._roots()
        if not roots:
            self.log("warn", "No hair folder found automatically - set 'Hair folder'.")
        else:
            self.log("info", "Searching in: %s" % "  |  ".join(roots))
        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
        try:
            self.rows = scan(roots, self.pat_le.text().strip() or DEFAULT_PATTERN)
        finally:
            QtWidgets.QApplication.restoreOverrideCursor()
        for r in self.rows:
            it = QtWidgets.QTreeWidgetItem([
                r["ns"],
                r["hair"] or "NOT FOUND:  %s" % (r["base"] or "(no '_mi_' in file name)"),
                r["new_ns"] or "",
                ("%d" % len(r["xgen"])) if r["hair"] else ""])
            it.setData(0, QtCore.Qt.UserRole, r["rn"])
            it.setFlags(it.flags() | QtCore.Qt.ItemIsUserCheckable)
            ok = bool(r["hair"])
            it.setCheckState(0, QtCore.Qt.Checked if ok else QtCore.Qt.Unchecked)
            if not ok:
                it.setForeground(1, QtGui.QBrush(QtGui.QColor("#ff6b6b")))
            elif r["alts"] > 1:
                it.setForeground(1, QtGui.QBrush(QtGui.QColor("#e6b450")))
                it.setToolTip(1, "%d files with this name - the best one is used" % r["alts"])
            self.tree.addTopLevelItem(it)
        for c in range(len(self.COLS)):
            self.tree.resizeColumnToContents(c)
        self.log("info", "%d '_mi_' character(s) in the scene, %d with a hair file."
                 % (len(self.rows), sum(1 for r in self.rows if r["hair"])))

    def _check_all(self, state):
        for i in range(self.tree.topLevelItemCount()):
            it = self.tree.topLevelItem(i)
            if state and "NOT FOUND" in it.text(1):
                continue
            it.setCheckState(0, QtCore.Qt.Checked if state else QtCore.Qt.Unchecked)

    def _select_in_viewport(self, item, _col):
        rn = item.data(0, QtCore.Qt.UserRole)
        try:
            nodes = cmds.referenceQuery(rn, nodes=True, dagPath=True) or []
            cmds.select(cmds.ls(nodes, assemblies=True), replace=True)
        except RuntimeError:
            pass

    def log(self, level, msg):
        colors = {"ok": "#7fd48f", "warn": "#e6b450", "err": "#ff6b6b", "info": "#8fb8ff"}
        tags = {"ok": "OK  ", "warn": "WARN", "err": "ERR ", "info": "INFO"}
        self.log_te.appendHtml('<span style="color:%s">[%s]</span> %s' % (
            colors.get(level, "#d8dce2"), tags.get(level, "    "),
            msg.replace("<", "&lt;").replace(">", "&gt;")))
        print("[MiToHair] %s  %s" % (tags.get(level, ""), msg))
        QtWidgets.QApplication.processEvents()

    def run(self):
        checked = set()
        for i in range(self.tree.topLevelItemCount()):
            it = self.tree.topLevelItem(i)
            if it.checkState(0) == QtCore.Qt.Checked:
                checked.add(it.data(0, QtCore.Qt.UserRole))
        rows = [r for r in self.rows if r["rn"] in checked]
        if not rows:
            self.log("warn", "Nothing checked.")
            return
        self.settings.setValue("roots", self.root_le.text())
        self.settings.setValue("pattern", self.pat_le.text())
        self.settings.setValue("rename", "true" if self.ns_cb.isChecked() else "false")
        self.log("info", "---- Converting %d character(s) ----" % len(rows))
        cmds.undoInfo(openChunk=True, chunkName="MiToHair")
        try:
            n = convert(rows, self.ns_cb.isChecked(), self.log)
            self.log("info", "Done: %d of %d converted." % (n, len(rows)))
        except Exception as e:
            self.log("err", "Failed: %s" % e)
            print(traceback.format_exc())
        finally:
            cmds.undoInfo(closeChunk=True)
        self.rescan()


_WINDOW = None


def show():
    global _WINDOW
    try:
        if _WINDOW is not None:
            _WINDOW.close()
            _WINDOW.deleteLater()
    except Exception:
        pass
    _WINDOW = MiToHairUI()
    _WINDOW.show()
    return _WINDOW


if __name__ == "__main__":
    show()
