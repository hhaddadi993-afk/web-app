# -*- coding: utf-8 -*-
"""
Character Pipeline Tool  -  Maya plug-in (Python, Qt)
=====================================================

A general tool for any referenced character (not tied to one asset name).

  Step 1  Rest -> Anim transition
          Deletes every key before the animation start frame, keys a clean
          rest pose (rotate 0 / translate 0 / scale 1) on the rest frame and
          eases smoothly into the animation. Good for cloth / hair sims.

  Step 2  Swap version
          Swaps the referenced file by a name token (e.g. _lo_ -> _mi_)
          and renames the namespace the same way.

  Step 3  Replace with file
          Replaces the chosen characters with any file (e.g. a hair version)
          and renames the namespace after the new file, keeping the
          trailing number (char_mi_rig1 -> char_hair1).

Install
-------
  1. Copy this file to:  Documents/maya/<version>/plug-ins/
     (create the "plug-ins" folder if it does not exist)
  2. Maya > Windows > Settings/Preferences > Plug-in Manager
     > Refresh > tick "Loaded" (and "Auto load") for char_pipeline_tool.py
  3. A "Char Pipeline" menu appears in Maya's main menu bar.

Works with Maya 2022+ (PySide2) and Maya 2025+ (PySide6).
"""

import os
import re
import fnmatch
import traceback

import maya.cmds as cmds
import maya.api.OpenMaya as om
import maya.OpenMayaUI as omui

try:
    from PySide6 import QtWidgets, QtCore, QtGui
    from shiboken6 import wrapInstance
except ImportError:
    from PySide2 import QtWidgets, QtCore, QtGui
    from shiboken2 import wrapInstance


PLUGIN_NAME = "CharPipelineTool"
PLUGIN_VERSION = "1.1.0"
MENU_NAME = "charPipelineMenu"

ROT = ("rotateX", "rotateY", "rotateZ")
TRA = ("translateX", "translateY", "translateZ")
SCL = ("scaleX", "scaleY", "scaleZ")


def maya_useNewAPI():
    """Tell Maya this plug-in uses the Python API 2.0."""
    pass


# =============================================================================
#  Core logic (pure maya.cmds, no UI)
# =============================================================================

def _short(node):
    """'|grp|ns:ctrl' -> 'ctrl'"""
    return node.split("|")[-1].split(":")[-1]


def ref_from_node(node):
    try:
        if cmds.referenceQuery(node, isNodeReferenced=True):
            return cmds.referenceQuery(node, referenceNode=True, topReference=True)
    except RuntimeError:
        pass
    return None


def refs_from_selection():
    out = []
    for n in cmds.ls(sl=True, long=True) or []:
        rn = ref_from_node(n)
        if rn and rn not in out:
            out.append(rn)
    return out


def all_top_refs():
    out = []
    for rn in cmds.ls(type="reference") or []:
        if rn == "sharedReferenceNode" or "_UNKNOWN_REF_NODE_" in rn:
            continue
        try:
            cmds.referenceQuery(rn, filename=True)
            if cmds.referenceQuery(rn, referenceNode=True, parent=True):
                continue  # nested reference: handled by its parent
        except RuntimeError:
            continue
        out.append(rn)
    return out


def ref_info(rn):
    try:
        path = cmds.referenceQuery(rn, filename=True, withoutCopyNumber=True)
        return {
            "node": rn,
            "ns": cmds.referenceQuery(rn, namespace=True, shortName=True),
            "path": path,
            "file": os.path.basename(path),
            "loaded": cmds.referenceQuery(rn, isLoaded=True),
        }
    except RuntimeError:
        return None


def resolve_path(path):
    """Accept absolute paths, or paths relative to the Maya project."""
    path = (path or "").strip().replace("\\", "/")
    if not path:
        return None
    candidates = [path]
    root = cmds.workspace(q=True, rootDirectory=True) or ""
    candidates.append(os.path.join(root, path.lstrip("/")))
    for c in candidates:
        c = os.path.normpath(c).replace("\\", "/")
        if os.path.isfile(c):
            return c
    return None


def rename_namespace(rn, new_short):
    """Rename a reference's namespace, avoiding clashes. Returns final name."""
    full = cmds.referenceQuery(rn, namespace=True)
    short = cmds.referenceQuery(rn, namespace=True, shortName=True)
    if not new_short or new_short == short:
        return short
    parent = full.rsplit(":", 1)[0]
    cand, i = new_short, 1
    while cmds.namespace(exists="%s:%s" % (parent, cand)):
        cand = "%s_%d" % (new_short, i)
        i += 1
    cmds.file(cmds.referenceQuery(rn, filename=True), edit=True, namespace=cand)
    return cand


# -----------------------------------------------------------------------------
#  XGen support
# -----------------------------------------------------------------------------

def ensure_xgen_plugin(log=None):
    """XGen collections are only built if xgenToolkit is loaded BEFORE the
    reference is loaded. Otherwise palettes come in as unknown nodes."""
    try:
        if not cmds.pluginInfo("xgenToolkit", q=True, loaded=True):
            cmds.loadPlugin("xgenToolkit", quiet=True)
            if log:
                log("info", "Loaded xgenToolkit plug-in.")
        return True
    except Exception as e:
        if log:
            log("warn", "Could not load xgenToolkit: %s" % e)
        return False


def _xg():
    try:
        import xgenm
        return xgenm
    except Exception:
        return None


def ref_palettes(rn):
    try:
        nodes = cmds.referenceQuery(rn, nodes=True) or []
    except RuntimeError:
        return []
    return cmds.ls(nodes, type="xgmPalette") or []


def xgen_files_beside(path):
    """.xgen files next to a Maya file: <scene>__<collection>.xgen"""
    folder = os.path.dirname(path)
    base = os.path.splitext(os.path.basename(path))[0]
    try:
        return sorted(f for f in os.listdir(folder)
                      if f.lower().endswith(".xgen") and f.startswith(base + "__"))
    except OSError:
        return []


def _xgen_refresh_ui():
    xg = _xg()
    if not xg:
        return
    try:
        import xgenm.xgGlobal as xgg
        if xgg.Maya and xgg.DescriptionEditor:
            xgg.DescriptionEditor.refresh("Full")
    except Exception:
        pass


def check_xgen(rn, new_path, log):
    """After a swap: make sure every XGen collection of the new file is live.
    If a palette exists but XGen has not built it, reload the reference once."""
    expected = xgen_files_beside(new_path)
    pals = ref_palettes(rn)

    if not pals:
        if expected:
            log("err", "    XGen: %s exist(s) next to the file but no collection was created. "
                       "Is xgenToolkit loaded?  Try: save scene and reopen."
                % ", ".join(expected))
        return

    xg = _xg()
    live = []
    if xg:
        try:
            live = list(xg.palettes() or [])
        except Exception:
            live = []

    missing = [p for p in pals if xg and p not in live]
    if missing:
        # reloading fires XGen's reference callbacks and builds the collection
        cmds.file(unloadReference=rn)
        cmds.file(loadReference=rn)
        pals = ref_palettes(rn)
        try:
            live = list(xg.palettes() or [])
        except Exception:
            live = []
        missing = [p for p in pals if p not in live]

    folder = os.path.dirname(new_path)
    for p in pals:
        fname = ""
        try:
            fname = cmds.getAttr(p + ".xgFileName") or ""
        except Exception:
            pass
        ok_file = bool(fname) and os.path.isfile(os.path.join(folder, os.path.basename(fname)))
        if p in missing:
            log("err", "    XGen: collection %s not initialised (file: %s)" % (p, fname or "?"))
        elif fname and not ok_file:
            log("warn", "    XGen: %s  ->  .xgen file not found next to the .mb: %s" % (p, fname))
        else:
            log("ok", "    XGen: %s  (%s)" % (p, fname or "ok"))
    _xgen_refresh_ui()


def swap_reference(rn, new_path, new_ns, log):
    """Rename the namespace FIRST, then load the new file, so XGen builds its
    collections with the final namespace (renaming afterwards breaks XGen)."""
    old_ns = cmds.referenceQuery(rn, namespace=True, shortName=True)
    final_ns = old_ns
    if new_ns and new_ns != old_ns:
        final_ns = rename_namespace(rn, new_ns)
    cmds.file(new_path, loadReference=rn)
    if final_ns != old_ns:
        log("ok", "    namespace: %s  ->  %s" % (old_ns, final_ns))
    check_xgen(rn, new_path, log)
    return final_ns


def animated_nodes(rn, only_selected=False):
    if only_selected:
        cands = [n for n in cmds.ls(sl=True, type="transform", long=True) or []
                 if ref_from_node(n) == rn]
    else:
        nodes = cmds.referenceQuery(rn, nodes=True, dagPath=True) or []
        cands = cmds.ls(nodes, type="transform", long=True) or []
    return [n for n in cands
            if cmds.listConnections(n, source=True, destination=False, type="animCurve")]


def keyed_plugs(node):
    out = []
    for a in cmds.listAttr(node, keyable=True, unlocked=True) or []:
        p = "%s.%s" % (node, a)
        try:
            if cmds.keyframe(p, q=True, keyframeCount=True):
                out.append((a, p))
        except Exception:
            pass
    return out


def step_rest_transition(refs, rest, start, excludes, keep_joint_t,
                         only_selected, set_playback, log):
    if rest >= start:
        raise ValueError("Rest frame must be before the animation start frame.")
    total = 0
    for rn in refs:
        info = ref_info(rn)
        nodes = animated_nodes(rn, only_selected)
        nodes = [n for n in nodes
                 if not any(fnmatch.fnmatch(_short(n), pat) for pat in excludes)]
        if not nodes:
            log("warn", "%s: no animated controls found." % (info["ns"] if info else rn))
            continue

        count = 0
        for n in nodes:
            is_joint = cmds.nodeType(n) == "joint"
            for a, p in keyed_plugs(n):
                cmds.setKeyframe(p, t=start, insert=True)
                cmds.cutKey(p, time=(-1e7, start - 0.001), clear=True)
                v = cmds.getAttr(p, time=start)

                if a in ROT:
                    r = round(v / 360.0) * 360.0        # nearest "zero", no spinning
                elif a in TRA:
                    r = v if (is_joint and keep_joint_t) else 0.0
                elif a in SCL:
                    r = 1.0
                else:
                    r = v                               # custom attrs: IK/FK, spaces...

                cmds.setKeyframe(p, t=rest, v=r)
                cmds.keyTangent(p, t=(rest, rest), itt="flat", ott="flat")
                cmds.keyTangent(p, t=(start, start), lock=False)
                cmds.keyTangent(p, t=(start, start), itt="auto")
                count += 1
        total += count
        log("ok", "%s: %d controls, %d curves  (rest %g -> anim %g)"
            % (info["ns"] if info else rn, len(nodes), count, rest, start))

    if set_playback and total:
        cmds.playbackOptions(min=rest)
        cmds.currentTime(rest)
    return total


def step_swap_version(refs, from_tok, to_tok, rename_ns, log):
    if not from_tok or not to_tok:
        raise ValueError("Both 'From' and 'To' tokens are required.")
    ensure_xgen_plugin(log)
    done = 0
    for rn in refs:
        info = ref_info(rn)
        if not info:
            continue
        label = info["ns"]
        want_ns = info["ns"].replace(from_tok, to_tok) if (rename_ns and from_tok in info["ns"]) else None

        if from_tok in info["file"]:
            new_path = os.path.join(os.path.dirname(info["path"]),
                                    info["file"].replace(from_tok, to_tok)).replace("\\", "/")
            if not os.path.isfile(new_path):
                log("err", "%s: file not found  %s" % (label, new_path))
                continue
            log("ok", "%s: %s  ->  %s" % (label, info["file"], os.path.basename(new_path)))
            swap_reference(rn, new_path, want_ns, log)
            done += 1
        elif to_tok in info["file"]:
            log("info", "%s: already on '%s' file." % (label, to_tok))
            if want_ns:
                new_ns = rename_namespace(rn, want_ns)
                log("ok", "    namespace: %s  ->  %s" % (info["ns"], new_ns))
                if ref_palettes(rn):
                    log("warn", "    XGen: namespace renamed on an already-loaded XGen "
                                "reference. Save and reopen the scene to rebuild it.")
                done += 1
        else:
            log("warn", "%s: '%s' not in file name, skipped." % (label, from_tok))
    return done


def step_replace_with_file(refs, path, rename_ns, log):
    new_path = resolve_path(path)
    if not new_path:
        raise ValueError("File not found: %s" % path)
    new_base = os.path.splitext(os.path.basename(new_path))[0]
    ensure_xgen_plugin(log)
    xfiles = xgen_files_beside(new_path)
    if xfiles:
        log("info", "XGen files next to %s: %s" % (os.path.basename(new_path), ", ".join(xfiles)))
    done = 0
    for rn in refs:
        info = ref_info(rn)
        if not info:
            continue
        want_ns = None
        if rename_ns:
            m = re.search(r"(\d+)$", info["ns"])
            want_ns = new_base + (m.group(1) if m else "")
        log("ok", "%s: %s  ->  %s" % (info["ns"], info["file"], os.path.basename(new_path)))
        swap_reference(rn, new_path, want_ns, log)
        done += 1
    return done


# =============================================================================
#  UI
# =============================================================================

STYLE = """
QDialog { background: #262a30; }
QWidget { color: #d8dce2; font-size: 12px; }
QLabel#title { font-size: 18px; font-weight: 600; color: #ffffff; }
QLabel#subtitle { color: #8a93a0; }
QLabel#section { font-size: 13px; font-weight: 600; color: #ffffff; }
QLabel#desc { color: #8a93a0; }
QLabel#badge {
    background: #4f8cff; color: white; font-weight: 700;
    border-radius: 13px; min-width: 26px; max-width: 26px;
    min-height: 26px; max-height: 26px; qproperty-alignment: AlignCenter;
}
QFrame#card { background: #2f343c; border: 1px solid #3b414b; border-radius: 8px; }
QTreeWidget, QPlainTextEdit, QLineEdit, QSpinBox, QDoubleSpinBox {
    background: #1e2126; border: 1px solid #3b414b; border-radius: 5px; padding: 4px;
}
QTreeWidget::item { padding: 3px; }
QTreeWidget::item:selected { background: #3a4f75; }
QHeaderView::section { background: #2f343c; border: none; padding: 5px; color: #aab2bd; }
QPushButton {
    background: #3b414b; border: none; border-radius: 5px; padding: 6px 12px;
}
QPushButton:hover { background: #48505c; }
QPushButton#run { background: #3d7a55; font-weight: 600; }
QPushButton#run:hover { background: #4a9467; }
QPushButton#runAll { background: #4f8cff; font-weight: 700; font-size: 13px; padding: 10px; }
QPushButton#runAll:hover { background: #6a9dff; }
QCheckBox { spacing: 6px; }
QTabWidget::pane { border: none; }
"""


def maya_main_window():
    ptr = omui.MQtUtil.mainWindow()
    return wrapInstance(int(ptr), QtWidgets.QWidget) if ptr else None


class StepCard(QtWidgets.QFrame):
    """Numbered card: badge + title + description + enable box + body + Run."""

    def __init__(self, number, title, desc, parent=None):
        super(StepCard, self).__init__(parent)
        self.setObjectName("card")
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(8)

        head = QtWidgets.QHBoxLayout()
        badge = QtWidgets.QLabel(str(number))
        badge.setObjectName("badge")
        head.addWidget(badge)
        tcol = QtWidgets.QVBoxLayout()
        tcol.setSpacing(0)
        t = QtWidgets.QLabel(title)
        t.setObjectName("section")
        d = QtWidgets.QLabel(desc)
        d.setObjectName("desc")
        d.setWordWrap(True)
        tcol.addWidget(t)
        tcol.addWidget(d)
        head.addLayout(tcol, 1)
        self.enabled_cb = QtWidgets.QCheckBox("Include in Run All")
        self.enabled_cb.setChecked(True)
        head.addWidget(self.enabled_cb, 0, QtCore.Qt.AlignTop)
        lay.addLayout(head)

        self.form = QtWidgets.QFormLayout()
        self.form.setLabelAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        self.form.setHorizontalSpacing(10)
        lay.addLayout(self.form)

        self.run_btn = QtWidgets.QPushButton("Run step %d" % number)
        self.run_btn.setObjectName("run")
        row = QtWidgets.QHBoxLayout()
        row.addStretch(1)
        row.addWidget(self.run_btn)
        lay.addLayout(row)


class CharPipelineUI(QtWidgets.QDialog):

    def __init__(self, parent=maya_main_window()):
        super(CharPipelineUI, self).__init__(parent)
        self.setWindowTitle("Character Pipeline Tool  v%s" % PLUGIN_VERSION)
        self.setWindowFlags(QtCore.Qt.Window)
        self.setMinimumSize(620, 820)
        self.setStyleSheet(STYLE)
        self.settings = QtCore.QSettings("CharPipelineTool", "UI")
        self._build()
        self._load_settings()
        self.add_from_selection()

    # ------------------------------------------------------------------ build
    def _build(self):
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)

        title = QtWidgets.QLabel("Character Pipeline Tool")
        title.setObjectName("title")
        sub = QtWidgets.QLabel("Select characters in the viewport, add them below, then run the steps in order.")
        sub.setObjectName("subtitle")
        root.addWidget(title)
        root.addWidget(sub)

        # ---- characters list
        card = QtWidgets.QFrame()
        card.setObjectName("card")
        cl = QtWidgets.QVBoxLayout(card)
        cl.setContentsMargins(12, 10, 12, 10)
        lbl = QtWidgets.QLabel("Characters  (checked = targets)")
        lbl.setObjectName("section")
        cl.addWidget(lbl)

        self.tree = QtWidgets.QTreeWidget()
        self.tree.setHeaderLabels(["Namespace", "File", "Reference node"])
        self.tree.setRootIsDecorated(False)
        self.tree.setAlternatingRowColors(False)
        self.tree.setMinimumHeight(140)
        self.tree.header().setStretchLastSection(True)
        self.tree.itemDoubleClicked.connect(self._select_in_viewport)
        cl.addWidget(self.tree)

        br = QtWidgets.QHBoxLayout()
        for text, fn in (("Add from Selection", self.add_from_selection),
                         ("All in Scene", self.add_all),
                         ("Check All", lambda: self._check_all(True)),
                         ("Uncheck All", lambda: self._check_all(False)),
                         ("Clear", self.tree.clear)):
            b = QtWidgets.QPushButton(text)
            b.clicked.connect(fn)
            br.addWidget(b)
        cl.addLayout(br)
        root.addWidget(card)

        # ---- steps (scrollable)
        steps_w = QtWidgets.QWidget()
        sl = QtWidgets.QVBoxLayout(steps_w)
        sl.setContentsMargins(0, 0, 0, 0)
        sl.setSpacing(10)

        # step 1
        self.s1 = StepCard(1, "Rest -> Animation transition",
                           "Deletes keys before the start frame, keys a zero rest pose and eases into the animation.")
        self.rest_sb = QtWidgets.QDoubleSpinBox()
        self.start_sb = QtWidgets.QDoubleSpinBox()
        for sb in (self.rest_sb, self.start_sb):
            sb.setRange(-100000, 100000)
            sb.setDecimals(0)
        self.excl_le = QtWidgets.QLineEdit()
        self.excl_le.setPlaceholderText("e.g.  *Main*, *Root*, *World*   (wildcards, comma separated)")
        self.keepjt_cb = QtWidgets.QCheckBox("Keep joint translation (recommended for skeletons)")
        self.onlysel_cb = QtWidgets.QCheckBox("Only selected controls (instead of the whole character)")
        self.playback_cb = QtWidgets.QCheckBox("Set playback start to rest frame")
        self.s1.form.addRow("Rest frame", self.rest_sb)
        self.s1.form.addRow("Animation start", self.start_sb)
        self.s1.form.addRow("Exclude", self.excl_le)
        self.s1.form.addRow("", self.keepjt_cb)
        self.s1.form.addRow("", self.onlysel_cb)
        self.s1.form.addRow("", self.playback_cb)
        self.s1.run_btn.clicked.connect(lambda: self._run([1]))
        sl.addWidget(self.s1)

        # step 2
        self.s2 = StepCard(2, "Swap version",
                           "Swaps the referenced file by a name token (e.g. _lo_ -> _mi_). File must be in the same folder.")
        self.from_le = QtWidgets.QLineEdit()
        self.to_le = QtWidgets.QLineEdit()
        self.ns2_cb = QtWidgets.QCheckBox("Rename namespace with the same token")
        self.s2.form.addRow("From token", self.from_le)
        self.s2.form.addRow("To token", self.to_le)
        self.s2.form.addRow("", self.ns2_cb)
        self.s2.run_btn.clicked.connect(lambda: self._run([2]))
        sl.addWidget(self.s2)

        # step 3
        self.s3 = StepCard(3, "Replace with file",
                           "Replaces the checked characters with any file (e.g. a hair version).")
        pr = QtWidgets.QHBoxLayout()
        self.path_le = QtWidgets.QLineEdit()
        self.path_le.setPlaceholderText("Absolute path, or relative to the Maya project")
        bb = QtWidgets.QPushButton("Browse...")
        bb.clicked.connect(self._browse)
        pr.addWidget(self.path_le, 1)
        pr.addWidget(bb)
        self.ns3_cb = QtWidgets.QCheckBox("Rename namespace after the new file (keeps trailing number)")
        self.s3.form.addRow("New file", pr)
        self.s3.form.addRow("", self.ns3_cb)
        self.s3.run_btn.clicked.connect(lambda: self._run([3]))
        sl.addWidget(self.s3)
        sl.addStretch(1)

        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        scroll.setWidget(steps_w)
        root.addWidget(scroll, 3)

        # ---- run all
        self.runall_btn = QtWidgets.QPushButton("Run enabled steps in order   (1 -> 2 -> 3)")
        self.runall_btn.setObjectName("runAll")
        self.runall_btn.clicked.connect(self._run_all)
        root.addWidget(self.runall_btn)

        # ---- log
        self.log_te = QtWidgets.QPlainTextEdit()
        self.log_te.setReadOnly(True)
        self.log_te.setMaximumHeight(150)
        root.addWidget(self.log_te, 1)

    # --------------------------------------------------------------- settings
    def _load_settings(self):
        s = self.settings
        self.rest_sb.setValue(float(s.value("rest", 950)))
        self.start_sb.setValue(float(s.value("start", 980)))
        self.excl_le.setText(s.value("exclude", ""))
        self.keepjt_cb.setChecked(s.value("keepjt", "true") == "true")
        self.onlysel_cb.setChecked(s.value("onlysel", "false") == "true")
        self.playback_cb.setChecked(s.value("playback", "true") == "true")
        self.from_le.setText(s.value("from", "_lo_"))
        self.to_le.setText(s.value("to", "_mi_"))
        self.ns2_cb.setChecked(s.value("ns2", "true") == "true")
        self.path_le.setText(s.value("path", ""))
        self.ns3_cb.setChecked(s.value("ns3", "true") == "true")
        for i, card in ((1, self.s1), (2, self.s2), (3, self.s3)):
            card.enabled_cb.setChecked(s.value("en%d" % i, "true") == "true")

    def _save_settings(self):
        s = self.settings
        b = lambda w: "true" if w.isChecked() else "false"
        s.setValue("rest", self.rest_sb.value())
        s.setValue("start", self.start_sb.value())
        s.setValue("exclude", self.excl_le.text())
        s.setValue("keepjt", b(self.keepjt_cb))
        s.setValue("onlysel", b(self.onlysel_cb))
        s.setValue("playback", b(self.playback_cb))
        s.setValue("from", self.from_le.text())
        s.setValue("to", self.to_le.text())
        s.setValue("ns2", b(self.ns2_cb))
        s.setValue("path", self.path_le.text())
        s.setValue("ns3", b(self.ns3_cb))
        for i, card in ((1, self.s1), (2, self.s2), (3, self.s3)):
            s.setValue("en%d" % i, b(card.enabled_cb))

    def closeEvent(self, e):
        self._save_settings()
        super(CharPipelineUI, self).closeEvent(e)

    # ------------------------------------------------------------ characters
    def _existing(self):
        return [self.tree.topLevelItem(i).data(0, QtCore.Qt.UserRole)
                for i in range(self.tree.topLevelItemCount())]

    def _add_refs(self, refs):
        have = self._existing()
        added = 0
        for rn in refs:
            if rn in have:
                continue
            info = ref_info(rn)
            if not info:
                continue
            it = QtWidgets.QTreeWidgetItem([info["ns"], info["file"], rn])
            it.setData(0, QtCore.Qt.UserRole, rn)
            it.setFlags(it.flags() | QtCore.Qt.ItemIsUserCheckable)
            it.setCheckState(0, QtCore.Qt.Checked)
            if not info["loaded"]:
                it.setForeground(0, QtGui.QBrush(QtGui.QColor("#d89a4a")))
                it.setToolTip(0, "Reference is unloaded")
            self.tree.addTopLevelItem(it)
            added += 1
        for c in range(3):
            self.tree.resizeColumnToContents(c)
        return added

    def add_from_selection(self):
        refs = refs_from_selection()
        n = self._add_refs(refs)
        if refs:
            self.log("info", "Added %d character(s) from selection." % n)

    def add_all(self):
        n = self._add_refs(all_top_refs())
        self.log("info", "Added %d character(s) from scene." % n)

    def _check_all(self, state):
        st = QtCore.Qt.Checked if state else QtCore.Qt.Unchecked
        for i in range(self.tree.topLevelItemCount()):
            self.tree.topLevelItem(i).setCheckState(0, st)

    def _targets(self):
        out = []
        for i in range(self.tree.topLevelItemCount()):
            it = self.tree.topLevelItem(i)
            if it.checkState(0) == QtCore.Qt.Checked:
                out.append(it.data(0, QtCore.Qt.UserRole))
        return out

    def _refresh_labels(self):
        for i in range(self.tree.topLevelItemCount()):
            it = self.tree.topLevelItem(i)
            info = ref_info(it.data(0, QtCore.Qt.UserRole))
            if info:
                it.setText(0, info["ns"])
                it.setText(1, info["file"])
        for c in range(3):
            self.tree.resizeColumnToContents(c)

    def _select_in_viewport(self, item, _col):
        rn = item.data(0, QtCore.Qt.UserRole)
        try:
            nodes = cmds.referenceQuery(rn, nodes=True, dagPath=True) or []
            tops = cmds.ls(nodes, assemblies=True) or cmds.ls(nodes, type="transform")[:1]
            cmds.select(tops, replace=True)
        except RuntimeError:
            pass

    def _browse(self):
        start = os.path.dirname(self.path_le.text()) or cmds.workspace(q=True, rootDirectory=True)
        res = cmds.fileDialog2(fileMode=1, startingDirectory=start,
                               fileFilter="Maya Files (*.mb *.ma);;All Files (*.*)")
        if res:
            self.path_le.setText(res[0])

    # -------------------------------------------------------------------- log
    def log(self, level, msg):
        colors = {"ok": "#7fd48f", "warn": "#e6b450", "err": "#ff6b6b", "info": "#8fb8ff"}
        tags = {"ok": "OK  ", "warn": "WARN", "err": "ERR ", "info": "INFO"}
        html = '<span style="color:%s">[%s]</span> %s' % (
            colors.get(level, "#d8dce2"), tags.get(level, "    "),
            msg.replace("<", "&lt;").replace(">", "&gt;"))
        self.log_te.appendHtml(html)
        print("[CharPipeline] %s  %s" % (tags.get(level, ""), msg))
        QtWidgets.QApplication.processEvents()

    # -------------------------------------------------------------------- run
    def _run_all(self):
        steps = [i for i, c in ((1, self.s1), (2, self.s2), (3, self.s3))
                 if c.enabled_cb.isChecked()]
        if not steps:
            self.log("warn", "No steps enabled.")
            return
        self._run(steps)

    def _run(self, steps):
        refs = self._targets()
        if not refs:
            self.log("warn", "No characters checked. Use 'Add from Selection' first.")
            return
        self._save_settings()
        excludes = [p.strip() for p in self.excl_le.text().split(",") if p.strip()]

        for step in steps:
            self.log("info", "---- Step %d on %d character(s) ----" % (step, len(refs)))
            cmds.undoInfo(openChunk=True, chunkName="CharPipeline_step%d" % step)
            try:
                if step == 1:
                    step_rest_transition(refs, self.rest_sb.value(), self.start_sb.value(),
                                         excludes, self.keepjt_cb.isChecked(),
                                         self.onlysel_cb.isChecked(),
                                         self.playback_cb.isChecked(), self.log)
                elif step == 2:
                    step_swap_version(refs, self.from_le.text(), self.to_le.text(),
                                      self.ns2_cb.isChecked(), self.log)
                elif step == 3:
                    if not self.path_le.text().strip():
                        self.log("warn", "Step 3 skipped: no file chosen.")
                        continue
                    step_replace_with_file(refs, self.path_le.text(),
                                           self.ns3_cb.isChecked(), self.log)
            except Exception as e:
                self.log("err", "Step %d failed: %s" % (step, e))
                print(traceback.format_exc())
                break
            finally:
                cmds.undoInfo(closeChunk=True)
                self._refresh_labels()
        self.log("info", "Done.")


# =============================================================================
#  Window / menu / plug-in entry points
# =============================================================================

_WINDOW = None


def show():
    global _WINDOW
    try:
        if _WINDOW is not None:
            _WINDOW.close()
            _WINDOW.deleteLater()
    except Exception:
        pass
    _WINDOW = CharPipelineUI()
    _WINDOW.show()
    return _WINDOW


def _create_menu():
    _delete_menu()
    cmds.menu(MENU_NAME, label="Char Pipeline", parent="MayaWindow", tearOff=True)
    cmds.menuItem(label="Character Pipeline Tool...", command=lambda *_: show())
    cmds.menuItem(divider=True)
    cmds.menuItem(label="About", command=lambda *_: cmds.confirmDialog(
        title="Character Pipeline Tool",
        message="v%s\nRest transition / version swap / file replace\nfor any referenced character." % PLUGIN_VERSION,
        button=["OK"]))


def _delete_menu():
    if cmds.menu(MENU_NAME, exists=True):
        cmds.deleteUI(MENU_NAME, menu=True)


def initializePlugin(mobject):
    om.MFnPlugin(mobject, "CharPipeline", PLUGIN_VERSION, "Any")
    if not cmds.about(batch=True):
        cmds.evalDeferred(_create_menu)


def uninitializePlugin(mobject):
    om.MFnPlugin(mobject)
    global _WINDOW
    try:
        if _WINDOW is not None:
            _WINDOW.close()
    except Exception:
        pass
    _WINDOW = None
    if not cmds.about(batch=True):
        _delete_menu()


# Running the file directly in the Script Editor also opens the tool.
if __name__ == "__main__":
    show()
