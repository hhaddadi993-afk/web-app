# >>> HAIR_BATCH  (installed by My Tools > Batch Hair Sim - do not edit between these markers)
import os as _hb_os
import fnmatch as _hb_fnmatch


def _hb_expand(s):
    try:
        return hou.text.expandString(s)
    except AttributeError:
        return hou.expandString(s)


def _hb_list_chars(ctrl):
    folder = ctrl.evalParm("abc_folder")
    if not _hb_os.path.isdir(folder):
        return []
    return sorted(_hb_os.path.splitext(f)[0] for f in _hb_os.listdir(folder)
                  if f.lower().endswith(".abc"))


def hb_char_menu(kwargs):
    items = []
    for c in _hb_list_chars(kwargs["node"]):
        items += [c, c]
    return items or ["", "(no .abc found in folder)"]


def _hb_part(node):
    n = node.name()
    for p in ("filecache_", "rop_", "cache_"):
        if n.startswith(p):
            n = n[len(p):]
    for s in ("_static",):
        if n.endswith(s):
            n = n[:-len(s)]
    return n


def _hb_nodes(ctrl, parm_name):
    out = []
    for name in ctrl.evalParm(parm_name).split():
        n = ctrl.node("../" + name) or hou.node(name)
        if n is None:
            raise RuntimeError("Node not found: " + name)
        out.append(n)
    return out


def _hb_set_menu(parm, token):
    try:
        parm.set(token)
    except Exception:
        pass


def hb_wire(kwargs):
    """Point alembic / sim caches / export ROPs at the SETUP_RUN parameters."""
    ctrl = kwargs["node"]
    c = ctrl.path()
    ch = lambda p: '`chs("{0}/{1}")`'.format(c, p)
    report = []

    abc = hou.node(ctrl.evalParm("abc_node"))
    if abc is None or abc.parm("fileName") is None:
        raise RuntimeError("Alembic node not found (or has no fileName): " + ctrl.evalParm("abc_node"))
    if abc.path() == ctrl.path():
        raise RuntimeError("'Alembic SOP' points to SETUP_RUN itself - set it to the Alembic node")
    # built directly from folder + char (no chained reference -> no recursion)
    abc.parm("fileName").set("{0}/{1}.abc".format(ch("abc_folder"), ch("char")))
    report.append(abc.name() + "  <-  abc_folder/char.abc")

    for n in _hb_nodes(ctrl, "sim_nodes"):
        part = _hb_part(n)
        if n.parm("basedir") is not None:              # File Cache 2.0 (constructed)
            if n.parm("filemethod") is not None:
                _hb_set_menu(n.parm("filemethod"), "constructed")
            n.parm("basedir").set("{0}/{1}".format(ch("cache_root"), ch("char")))
            n.parm("basename").set(part)
        elif n.parm("file") is not None:               # old File Cache
            n.parm("file").set("{0}/{1}/{2}/{2}.$F4.bgeo.sc".format(ch("cache_root"), ch("char"), part))
        else:
            raise RuntimeError("Unknown cache node type: " + n.path())
        report.append("{0}  ->  cache/<char>/{1}/".format(n.name(), part))

    for n in _hb_nodes(ctrl, "export_nodes"):
        part = _hb_part(n)
        path = "{0}/{1}/{2}.abc".format(ch("export_root"), ch("char"), part)
        for pn in ("filename", "sopoutput", "file"):
            if n.parm(pn) is not None:
                n.parm(pn).set(path)
                break
        else:
            raise RuntimeError("No output path parm on: " + n.path())
        report.append("{0}  ->  from_houdini/<char>/{1}.abc".format(n.name(), part))
    report += _hb_wire_frames(ctrl)
    return report


def _hb_set_range_mode(n):
    p = n.parm("trange")
    if p is None:
        return
    for v in ("normal", 1):
        try:
            p.set(v)
            return
        except Exception:
            pass


def _hb_try_expr(n, pname, expr, report, label):
    """Set an expression; skip (and report) parms that are locked or inside a locked asset."""
    p = n.parm(pname)
    if p is None:
        return False
    try:
        p.setExpression(expr, hou.exprLanguage.Hscript)
        return True
    except hou.PermissionError:
        report.append("{0}: {1} is locked (skipped)".format(n.path(), label))
    except Exception as e:
        report.append("{0}: {1} not set ({2})".format(n.path(), label, e))
    return False


def _hb_wire_frames(ctrl):
    """Point every cache / ROP / vellum solver at SETUP_RUN start_frame / end_frame."""
    if ctrl.parm("start_frame") is None:
        return []
    c = ctrl.path()
    fs = 'ch("{0}/start_frame")'.format(c)
    fe = 'ch("{0}/end_frame")'.format(c)
    report = []
    for parm_name in ("sim_nodes", "export_nodes"):
        for n in _hb_nodes(ctrl, parm_name):
            if n.parm("f1") is None:
                report.append("{0}: no frame range parm (skipped)".format(n.name()))
                continue
            _hb_set_range_mode(n)
            ok1 = _hb_try_expr(n, "f1", fs, report, "start frame")
            ok2 = _hb_try_expr(n, "f2", fe, report, "end frame")
            if n.parm("f3") is not None:
                try:
                    n.parm("f3").deleteAllKeyframes()
                    n.parm("f3").set(1)
                except Exception:
                    pass
            if ok1 and ok2:
                report.append("{0}: frames from SETUP_RUN".format(n.name()))

    if ctrl.evalParm("set_solver_start"):
        for n in ctrl.parent().allSubChildren():
            if "vellumsolver" not in n.type().name().lower() or n.parm("startframe") is None:
                continue
            # solvers that live inside a locked asset (e.g. inside a vellum HDA) can't be edited
            if n.isInsideLockedHDA():
                continue
            if _hb_try_expr(n, "startframe", fs, report, "sim start frame"):
                report.append("{0}: sim start frame from SETUP_RUN".format(n.name()))

    if ctrl.evalParm("set_timeline"):
        a, b = ctrl.evalParm("start_frame"), ctrl.evalParm("end_frame")
        try:
            hou.playbar.setFrameRange(a, b)
            hou.playbar.setPlaybackRange(a, b)
            report.append("timeline: {0}-{1}".format(int(a), int(b)))
        except Exception:
            pass
    return report


def hb_frames_from_timeline(kwargs):
    ctrl = kwargs["node"]
    a, b = hou.playbar.frameRange()
    ctrl.parm("start_frame").set(a)
    ctrl.parm("end_frame").set(b)


def hb_apply_frames(kwargs):
    rep = _hb_wire_frames(kwargs["node"])
    _hb_status(kwargs["node"], "Frame range applied to {0} node(s)".format(len(rep)))


def _hb_out_parm(n):
    for pn in ("filename", "sopoutput", "file"):
        if n.parm(pn) is not None:
            return n.parm(pn)
    return None


def _hb_execute(n):
    if isinstance(n, hou.RopNode):
        n.render(verbose=False, output_progress=False)
    elif n.parm("execute") is not None:
        n.parm("execute").pressButton()
    else:
        raise RuntimeError("Cannot run " + n.path())


def _hb_status(ctrl, text):
    p = ctrl.parm("status")
    if p is not None:
        try:
            p.set(text)
        except Exception:
            pass
    print("[Batch Hair] " + text)


def _hb_frames(ctrl):
    if ctrl.parm("start_frame") is not None:
        return int(ctrl.evalParm("start_frame")), int(ctrl.evalParm("end_frame"))
    a, b = hou.playbar.frameRange()
    return int(a), int(b)


def _hb_path_at(n, frame):
    for pn in ("sopoutput", "file", "filename"):
        p = n.parm(pn)
        if p is not None:
            try:
                v = p.evalAtFrame(frame)
            except Exception:
                continue
            if v:
                return v.replace("\\", "/")
    return ""


def _hb_cache_missing(n, a, b):
    """Return the first missing cache file (start / middle / end frame), or '' if all exist."""
    for f in sorted({a, (a + b) // 2, b}):
        path = _hb_path_at(n, f)
        if not path or not _hb_os.path.isfile(path):
            return path or "(no path on {0})".format(n.name())
    return ""


def _hb_source_cache(rop, sims):
    """The sim cache this ROP must read from: same part name, else any cache above it."""
    above = set(x.path() for x in rop.inputAncestors())
    part = _hb_part(rop)
    same = [s for s in sims if _hb_part(s) == part]
    for s in same + sims:
        if s.path() in above:
            return s, True
    return (same[0] if same else None), False


def _hb_is_direct(ctrl):
    p = ctrl.parm("run_mode")
    return p is not None and p.evalAsString() == "direct"


def _hb_set_bypass(n, state):
    try:
        n.bypass(state)
    except Exception:
        pass


def _hb_run_char_direct(ctrl, char, sims, exps, op, idx, total):
    """No sim cache: File Caches are bypassed, each ROP simulates and writes the alembic in one pass.
    The original bypass state of the File Caches is restored afterwards."""
    saved = []
    for n in sims:
        try:
            saved.append((n, n.isBypassed()))
        except Exception:
            pass
        if n.parm("loadfromdisk") is not None:
            try:
                n.parm("loadfromdisk").set(0)     # never read an old cache
            except Exception:
                pass
        _hb_set_bypass(n, True)                   # passes the live sim straight through
    try:
        for i, n in enumerate(exps):
            if op is not None:
                op.updateProgress(float(i) / len(exps))
            _hb_status(ctrl, "RUNNING  {0}  ({1}/{2})   step {3}/{4}  SIM+EXPORT  {5}".format(
                char, idx, total, i + 1, len(exps), n.name()))
            out = _hb_out_parm(n)
            if out is not None:
                d = _hb_os.path.dirname(out.eval())
                if d and not _hb_os.path.isdir(d):
                    _hb_os.makedirs(d)
            _hb_execute(n)
            path = out.eval() if out is not None else ""
            if path and not _hb_os.path.isfile(path):
                raise RuntimeError("{0}: alembic was not written ({1})".format(n.name(), path))
    finally:
        for n, was in saved:
            _hb_set_bypass(n, was)


def _hb_run_char(ctrl, char, op=None, idx=1, total=1):
    ctrl.parm("char").set(char)
    sims = _hb_nodes(ctrl, "sim_nodes")
    exps = _hb_nodes(ctrl, "export_nodes")
    fa, fb = _hb_frames(ctrl)
    abc_file = _hb_os.path.join(ctrl.evalParm("abc_folder"), char + ".abc").replace("\\", "/")
    if not _hb_os.path.isfile(abc_file):
        raise RuntimeError("Alembic not found: " + abc_file)

    if _hb_is_direct(ctrl):
        _hb_run_char_direct(ctrl, char, sims, exps, op, idx, total)
        return
    for n in sims:
        _hb_set_bypass(n, False)

    # every ROP must sit below its sim cache, otherwise it would re-simulate
    for rop in exps:
        src, connected = _hb_source_cache(rop, sims)
        if not connected:
            raise RuntimeError("{0} is not connected below {1} - it would re-simulate instead "
                               "of reading the cache. Connect it under the File Cache."
                               .format(rop.name(), src.name() if src else "any sim cache"))

    skip = ctrl.parm("skip_cached") is not None and ctrl.evalParm("skip_cached")
    steps = sims + exps
    for i, n in enumerate(steps):
        if op is not None:
            op.updateProgress(float(i) / len(steps))
        is_sim = n in sims
        tag = "{0}  ({1}/{2})   step {3}/{4}".format(char, idx, total, i + 1, len(steps))

        if is_sim:
            if skip and not _hb_cache_missing(n, fa, fb):
                _hb_status(ctrl, "SKIP     {0}  SIM     {1}  (cache already on disk)".format(tag, n.name()))
            else:
                _hb_status(ctrl, "RUNNING  {0}  SIM     {1}".format(tag, n.name()))
                if n.parm("loadfromdisk") is not None:
                    n.parm("loadfromdisk").set(0)
                _hb_execute(n)
            # from now on this node only READS the cache
            if n.parm("loadfromdisk") is not None:
                n.parm("loadfromdisk").set(1)
            missing = _hb_cache_missing(n, fa, fb)
            if missing:
                raise RuntimeError("{0}: cache was not written ({1})".format(n.name(), missing))
            continue

        # export: make sure the cache above is on disk and in read mode
        src, _ = _hb_source_cache(n, sims)
        if src.parm("loadfromdisk") is None:
            raise RuntimeError("{0} has no 'Load from Disk' - cannot guarantee no re-sim".format(src.name()))
        src.parm("loadfromdisk").set(1)
        missing = _hb_cache_missing(src, fa, fb)
        if missing:
            raise RuntimeError("{0}: no cache for {1} ({2}) - not exporting to avoid a re-sim"
                               .format(n.name(), src.name(), missing))
        _hb_status(ctrl, "RUNNING  {0}  EXPORT  {1}  (reads {2})".format(tag, n.name(), src.name()))
        out = _hb_out_parm(n)
        if out is not None:
            d = _hb_os.path.dirname(out.eval())
            if d and not _hb_os.path.isdir(d):
                _hb_os.makedirs(d)
        _hb_execute(n)


def _hb_show_result(msg, failed):
    try:
        hou.ui.triggerUpdate()
    except Exception:
        pass
    hou.ui.displayMessage(msg, title="Batch Hair Sim",
                          severity=hou.severityType.Warning if failed else hou.severityType.Message)


def _hb_run(ctrl, chars):
    _hb_wire_frames(ctrl)
    if hou.hipFile.hasUnsavedChanges():
        hou.hipFile.save()
    done, failed = [], []
    try:
        with hou.InterruptableOperation("Batch Hair Sim", "Characters",
                                        open_interrupt_dialog=True) as op:
            for i, char in enumerate(chars):
                op.updateLongProgress(float(i) / len(chars), "{0}  ({1}/{2})".format(char, i + 1, len(chars)))
                try:
                    _hb_run_char(ctrl, char, op, i + 1, len(chars))
                    done.append(char)
                except hou.OperationInterrupted:
                    raise
                except Exception as e:
                    failed.append((char, str(e)))
                    print("[Batch Hair] FAILED {0}: {1}".format(char, e))
            # close the progress bar at 100% so the window goes away
            op.updateProgress(1.0)
            op.updateLongProgress(1.0, "Finished")
    except hou.OperationInterrupted:
        failed.append(("--", "cancelled by user"))

    _hb_status(ctrl, "FINISHED  {0} done, {1} failed   ({2})".format(
        len(done), len(failed), ", ".join(done) or "-"))
    msg = "Done: {0}\nFailed: {1}".format(", ".join(done) or "-", len(failed))
    if failed:
        msg += "\n\n" + "\n".join("{0}: {1}".format(c, e) for c, e in failed)

    # show the result only after Houdini has closed the progress window
    try:
        import hdefereval
        hdefereval.executeDeferred(lambda: _hb_show_result(msg, failed))
    except Exception:
        _hb_show_result(msg, failed)


def hb_run_current(kwargs):
    ctrl = kwargs["node"]
    _hb_run(ctrl, [ctrl.evalParm("char")])


def hb_run_all(kwargs):
    ctrl = kwargs["node"]
    chars = _hb_selected_chars(ctrl)
    if not chars:
        hou.ui.displayMessage("No alembic matches 'Characters to Run'.")
        return
    if hou.ui.displayMessage("Run {0} character(s)?\n\n{1}".format(len(chars), "\n".join(chars)),
                             buttons=("Run", "Cancel"), default_choice=0, close_choice=1) != 0:
        return
    _hb_run(ctrl, chars)


def _hb_resolved_path(n):
    """Final file path a cache / ROP node will write (current frame)."""
    for pn in ("sopoutput", "filename", "file", "outputfile"):
        p = n.parm(pn)
        if p is not None:
            try:
                v = p.eval()
            except Exception:
                continue
            if v:
                return v.replace("\\", "/")
    return ""


def hb_check(kwargs):
    """Dry run: show every path for the current character, nothing is written."""
    ctrl = kwargs["node"]
    char = ctrl.evalParm("char")
    lines, problems = [], []

    abc_file = _hb_os.path.join(ctrl.evalParm("abc_folder"), char + ".abc").replace("\\", "/")
    ok = _hb_os.path.isfile(abc_file)
    if ctrl.parm("start_frame") is not None:
        lines.append("FRAMES  {0} - {1}".format(int(ctrl.evalParm("start_frame")),
                                              int(ctrl.evalParm("end_frame"))))
        lines.append("")
    lines.append("INPUT  ({0})".format("found" if ok else "MISSING"))
    lines.append("   " + abc_file)
    if not ok:
        problems.append("Alembic file is missing")

    seen = {}
    direct = _hb_is_direct(ctrl)
    lines.append("")
    lines.append("MODE  " + ("DIRECT - sim caches bypassed, each ROP simulates and exports"
                             if direct else "CACHE - sim to disk first, ROPs read the cache"))
    for title, parm_name in (("SIM CACHES" + ("  (bypassed - not written)" if direct else ""), "sim_nodes"),
                             ("ALEMBIC EXPORTS", "export_nodes")):
        lines.append("")
        lines.append(title)
        try:
            nodes = _hb_nodes(ctrl, parm_name)
        except Exception as e:
            problems.append(str(e))
            continue
        for n in nodes:
            path = _hb_resolved_path(n)
            folder = _hb_os.path.dirname(path)
            rng = ""
            if n.parm("f1") is not None:
                a, b = n.evalParm("f1"), n.evalParm("f2")
                rng = "   [{0} - {1}]".format(int(a), int(b))
                if ctrl.parm("start_frame") is not None and (
                        int(a) != int(ctrl.evalParm("start_frame")) or
                        int(b) != int(ctrl.evalParm("end_frame"))):
                    problems.append("{0}: frame range {1}-{2} is not the SETUP_RUN range "
                                    "(press Apply Frame Range)".format(n.name(), int(a), int(b)))
            lines.append("   {0}{1}".format(n.name(), rng))
            if parm_name == "sim_nodes" and direct:
                continue
            if parm_name == "export_nodes" and not direct:
                try:
                    sims_ = _hb_nodes(ctrl, "sim_nodes")
                    src, connected = _hb_source_cache(n, sims_)
                    if connected:
                        fa, fb = _hb_frames(ctrl)
                        has = not _hb_cache_missing(src, fa, fb)
                        lines.append("      reads {0}  ({1})".format(
                            src.name(), "cache on disk" if has else "no cache yet - will be simmed first"))
                    else:
                        problems.append("{0} is not below {1} - it would RE-SIMULATE".format(
                            n.name(), src.name() if src else "a sim cache"))
                except Exception as e:
                    problems.append(str(e))
            lines.append("      " + (path or "(could not read the output path)"))
            if not path:
                problems.append(n.name() + ": output path not readable")
                continue
            if char and char not in path:
                problems.append(n.name() + ": path does not contain the character name")
            key = folder if parm_name == "sim_nodes" else path
            if key in seen:
                problems.append("{0} and {1} write to the same {2}".format(
                    seen[key], n.name(), "folder" if parm_name == "sim_nodes" else "file"))
            seen[key] = n.name()

    lines.append("")
    if problems:
        lines.append("PROBLEMS:")
        lines += ["   - " + p for p in problems]
        _hb_status(ctrl, "CHECK: {0} problem(s) - see the Check Paths window".format(len(problems)))
    else:
        lines.append("All paths are separate and use the character name.  OK to run.")
        _hb_status(ctrl, "CHECK OK for {0} - ready to run".format(char))
    hou.ui.displayMessage("\n".join(lines), title="Check Paths  -  " + char,
                          severity=hou.severityType.Warning if problems else hou.severityType.Message)
    return not problems


def hb_open(kwargs, parm_name):
    p = kwargs["node"].evalParm(parm_name)
    if not _hb_os.path.isdir(p):
        _hb_os.makedirs(p)
    hou.ui.showInFileBrowser(p + "/")
# ------------------------------------------------------------------ worker script (runs inside hython)
_HB_WORKER_SRC = r'''# Batch Hair Sim - worker (written by SETUP_RUN, runs inside hython)
import argparse, os, sys, time, traceback
import hou

ap = argparse.ArgumentParser()
ap.add_argument("--hip", required=True)
ap.add_argument("--ctrl", required=True)
ap.add_argument("--char", required=True)
ap.add_argument("--rop", required=True)
a = ap.parse_args()

def log(msg):
    print("[HairWorker] " + msg)
    sys.stdout.flush()

try:
    import socket
    log("host %s  |  char %s  |  rop %s" % (socket.gethostname(), a.char, a.rop))
    hou.hipFile.load(a.hip, suppress_save_prompt=True, ignore_load_warnings=True)
    ctrl = hou.node(a.ctrl)
    if ctrl is None:
        raise RuntimeError("control node not found: " + a.ctrl)
    ctrl.parm("char").set(a.char)

    abc_in = os.path.join(ctrl.evalParm("abc_folder"), a.char + ".abc")
    if not os.path.isfile(abc_in):
        raise RuntimeError("input alembic missing: " + abc_in)

    # Direct mode: sim caches are bypassed, the ROP simulates and writes in one pass
    for name in ctrl.evalParm("sim_nodes").split():
        n = ctrl.node("../" + name) or hou.node(name)
        if n is None:
            continue
        p = n.parm("loadfromdisk")
        if p is not None:
            p.set(0)
        n.bypass(True)

    rop = ctrl.node("../" + a.rop) or hou.node(a.rop)
    if rop is None:
        raise RuntimeError("ROP not found: " + a.rop)
    out_parm = None
    for pn in ("filename", "sopoutput", "file"):
        if rop.parm(pn) is not None:
            out_parm = rop.parm(pn)
            break
    out = out_parm.eval() if out_parm is not None else ""
    if out:
        d = os.path.dirname(out)
        if d and not os.path.isdir(d):
            os.makedirs(d)
    log("frames %d-%d  ->  %s" % (int(rop.evalParm("f1")), int(rop.evalParm("f2")), out))

    t = time.time()
    if isinstance(rop, hou.RopNode):
        rop.render(verbose=True, output_progress=True)
    else:
        rop.parm("execute").pressButton()

    if out and (not os.path.isfile(out) or os.path.getsize(out) == 0):
        raise RuntimeError("output was not written: " + out)
    log("DONE in %.1f min  ->  %s" % ((time.time() - t) / 60.0, out))
    sys.exit(0)
except SystemExit:
    raise
except Exception:
    traceback.print_exc()
    sys.exit(1)
'''


def _hb_selected_chars(ctrl):
    pats = ctrl.evalParm("run_chars").split() or ["*"]
    out = []
    for c in _hb_list_chars(ctrl):
        inc = [p for p in pats if not p.startswith("^")]
        exc = [p[1:] for p in pats if p.startswith("^")]
        if any(_hb_fnmatch.fnmatch(c, p) for p in (inc or ["*"])) and \
                not any(_hb_fnmatch.fnmatch(c, p) for p in exc):
            out.append(c)
    return out


# ------------------------------------------------------------------ background / parallel on this PC
_hb_bg = {"thread": None, "stop": False, "procs": {}}


def _hb_free_ram_gb():
    """Available physical RAM in GB (Windows), or None if unknown."""
    try:
        import ctypes

        class _MS(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
        m = _MS()
        m.dwLength = ctypes.sizeof(_MS)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
        return m.ullAvailPhys / float(1024 ** 3)
    except Exception:
        return None


def _hb_deferred(fn):
    try:
        import hdefereval
        hdefereval.executeDeferred(fn)
    except Exception:
        pass


def _hb_bg_status(ctrl_path, text):
    def _do():
        n = hou.node(ctrl_path)
        if n is not None:
            _hb_status(n, text)
    _hb_deferred(_do)


def _hb_bg_loop(ctrl_path, hython, worker, hip, jobs, slots, min_free, log_dir):
    import subprocess
    import time
    flags = 0
    if _hb_os.name == "nt":
        flags = 0x08000000 | 0x00004000      # no console window | below-normal priority (UI stays smooth)
    queue = list(jobs)
    running = {}                             # tag -> (Popen, logfile, t0)
    done, failed = [], []
    t_start = time.time()
    total = len(jobs)

    while queue or running:
        if _hb_bg["stop"]:
            for tag, (p, lf, _t) in running.items():
                try:
                    p.kill()
                except Exception:
                    pass
                lf.close()
                failed.append((tag, "stopped"))
            running.clear()
            failed += [("{0}_{1}".format(c, part), "not started") for c, r, part in queue]
            queue = []
            break

        # start new jobs while there is a free slot and enough RAM
        while queue and len(running) < slots:
            free = _hb_free_ram_gb()
            if running and free is not None and free < min_free:
                break
            char, rop_name, part = queue.pop(0)
            tag = "{0}_{1}".format(char, part)
            lf = open(_hb_os.path.join(log_dir, tag + ".log"), "w")
            cmd = [hython, worker, "--hip", hip, "--ctrl", ctrl_path, "--char", char, "--rop", rop_name]
            try:
                p = subprocess.Popen(cmd, stdout=lf, stderr=subprocess.STDOUT,
                                     cwd=_hb_os.path.dirname(hip), creationflags=flags)
                running[tag] = (p, lf, time.time())
                _hb_bg["procs"][tag] = p
            except Exception as e:
                lf.close()
                failed.append((tag, str(e)))
            time.sleep(3)                    # stagger start-up (scene load + license check)

        for tag in list(running):
            p, lf, t0 = running[tag]
            if p.poll() is None:
                continue
            lf.close()
            mins = (time.time() - t0) / 60.0
            if p.returncode == 0:
                done.append("{0}  ({1:.0f} min)".format(tag, mins))
            else:
                failed.append((tag, "exit code {0} - see logs/{1}.log".format(p.returncode, tag)))
            del running[tag]
            _hb_bg["procs"].pop(tag, None)

        free = _hb_free_ram_gb()
        _hb_bg_status(ctrl_path, "BACKGROUND  {0}/{1} done  |  running: {2}  |  queued {3}  |  "
                                 "failed {4}{5}".format(
                                     len(done), total, ", ".join(sorted(running)) or "-", len(queue),
                                     len(failed), "  |  free RAM {0:.0f} GB".format(free) if free else ""))
        time.sleep(5)

    mins = (time.time() - t_start) / 60.0
    summary = "Background sims finished in {0:.0f} min\n\nDone: {1}\nFailed: {2}".format(
        mins, len(done), len(failed))
    if done:
        summary += "\n\n" + "\n".join(done)
    if failed:
        summary += "\n\nFAILED:\n" + "\n".join("{0}: {1}".format(t, e) for t, e in failed)
    with open(_hb_os.path.join(log_dir, "_summary.txt"), "w") as f:
        f.write(summary)
    _hb_bg["thread"] = None
    _hb_bg["stop"] = False
    _hb_bg_status(ctrl_path, "BACKGROUND FINISHED  {0} done, {1} failed  ({2:.0f} min)".format(
        len(done), len(failed), mins))
    _hb_deferred(lambda: hou.ui.displayMessage(
        summary, title="Batch Hair Sim - Background",
        severity=hou.severityType.Warning if failed else hou.severityType.Message))


def hb_bg_run(kwargs):
    import threading
    ctrl = kwargs["node"]
    if _hb_bg["thread"] is not None and _hb_bg["thread"].is_alive():
        hou.ui.displayMessage("Background sims are already running. Press Stop first.")
        return

    chars = _hb_selected_chars(ctrl)
    rops = _hb_nodes(ctrl, "export_nodes")
    if not chars:
        hou.ui.displayMessage("No alembic matches 'Characters to Run'.")
        return
    missing = [c for c in chars if not _hb_os.path.isfile(
        _hb_os.path.join(ctrl.evalParm("abc_folder"), c + ".abc"))]
    if missing:
        hou.ui.displayMessage("Input alembic missing for:\n" + "\n".join(missing))
        return

    slots = int(ctrl.evalParm("bg_slots"))
    min_free = float(ctrl.evalParm("bg_min_ram"))
    hython = _hb_expand("$HFS").replace("\\", "/") + "/bin/" + ("hython.exe" if _hb_os.name == "nt" else "hython")
    if not _hb_os.path.isfile(hython):
        hou.ui.displayMessage("hython not found:\n" + hython)
        return

    jobs = [(c, r.name(), _hb_part(r)) for c in chars for r in rops]
    if hou.ui.displayMessage(
            "Run {0} sims in the background ({1} characters x {2} parts)?\n\n"
            "{3} at the same time  |  frames {4}-{5}\n"
            "A new sim only starts if at least {6:.0f} GB RAM is free.\n\n"
            "Keep this Houdini open until it finishes - you can keep working meanwhile."
            .format(len(jobs), len(chars), len(rops), slots, int(ctrl.evalParm("start_frame")),
                    int(ctrl.evalParm("end_frame")), min_free),
            buttons=("Start", "Cancel"), default_choice=0, close_choice=1,
            title="Run in Background") != 0:
        return

    _hb_wire_frames(ctrl)
    hou.hipFile.save()
    hip = hou.hipFile.path()

    base = _hb_os.path.join(_hb_expand("$HIP"), "local_farm")
    log_dir = _hb_os.path.join(base, "logs")
    if not _hb_os.path.isdir(log_dir):
        _hb_os.makedirs(log_dir)
    worker = _hb_os.path.join(base, "hair_worker.py").replace("\\", "/")
    with open(worker, "w") as f:
        f.write(_HB_WORKER_SRC)

    _hb_bg["stop"] = False
    t = threading.Thread(target=_hb_bg_loop,
                         args=(ctrl.path(), hython, worker, hip, jobs, slots, min_free, log_dir))
    t.daemon = True
    _hb_bg["thread"] = t
    t.start()
    _hb_status(ctrl, "BACKGROUND  starting {0} sims, {1} at a time...".format(len(jobs), slots))


def hb_bg_stop(kwargs):
    if _hb_bg["thread"] is None:
        hou.ui.displayMessage("Nothing is running in the background.")
        return
    if hou.ui.displayMessage("Stop all background sims? Running sims are killed (their output is incomplete).",
                             buttons=("Stop", "Cancel"), default_choice=1, close_choice=1) == 0:
        _hb_bg["stop"] = True


def hb_bg_logs(kwargs):
    p = _hb_os.path.join(_hb_expand("$HIP"), "local_farm", "logs")
    if not _hb_os.path.isdir(p):
        _hb_os.makedirs(p)
    hou.ui.showInFileBrowser(p.replace("\\", "/") + "/")
# <<< HAIR_BATCH
