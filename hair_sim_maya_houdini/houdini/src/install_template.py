import re
import hou

CTRL_DEFAULT = "/obj/alembic_import_all/SETUP_RUN"
ABC_NODE_DEFAULT = "/obj/alembic_import_all/wildebeest_a_lo_wildebeest_lodB_geo"
SIM_DEFAULT = "filecache_tail_static filecache_beard_static filecache_mane_static"
EXPORT_DEFAULT = "rop_mane_static rop_beard_static rop_tail_static"
SESSION_SRC = __SESSION_SRC__


def _install_session_code():
    src = hou.sessionModuleSource() or ""
    src = re.sub(r"# >>> HAIR_BATCH.*?# <<< HAIR_BATCH\n?", "", src, flags=re.S).rstrip()
    if "import hou" not in src:
        src = "import hou\n" + src
    hou.setSessionModuleSource(src + "\n\n" + SESSION_SRC)


def _cb(fn):
    return "hou.session.{0}(kwargs)".format(fn)


def _build_parms(ctrl):
    ptg = ctrl.parmTemplateGroup()
    names = ("hb_folder", "hb_step1", "hb_step2", "hb_step3", "hb_ro", "status",
             "abc_folder", "char", "abc_path", "abc_node", "cache_root", "sim_nodes",
             "cache_preview", "export_root", "export_nodes", "export_preview", "wire",
             "run_chars", "run_mode", "skip_cached", "check", "run_current", "run_all", "open_cache", "open_export",
             "start_frame", "end_frame", "set_solver_start", "set_timeline", "frames_tl", "frames_apply", "sep4", "sep5",
             "hb_step4", "lbl4", "bg_slots", "bg_min_ram", "bg_run", "bg_stop", "bg_logs", "dl_group", "dl_machines", "dl_pool", "dl_limits", "dl_priority",
             "dl_hython", "dl_cmd", "dl_defaults", "dl_submit",
             "lbl_in", "lbl1", "lbl2", "lbl3", "sep1", "sep2", "sep3")
    for name in names:
        if ptg.find(name):
            ptg.remove(name)

    S = hou.StringParmTemplate
    PY = hou.scriptLanguage.Python
    RO = "{ hb_ro == 0 }"            # read-only display fields

    def note(name, text):
        return hou.LabelParmTemplate(name, "", column_labels=[text], is_label_hidden=True)

    def button(name, label, cb, join=False):
        b = hou.ButtonParmTemplate(name, label, script_callback=cb, script_callback_language=PY)
        b.setJoinWithNext(join)
        return b

    def readonly(name, label, value):
        p = S(name, label, 1, default_value=[value])
        p.setDisableWhen(RO)
        return p

    top = hou.FolderParmTemplate("hb_folder", "Batch Hair Sim", folder_type=hou.folderType.Tabs)

    hidden = hou.ToggleParmTemplate("hb_ro", "ro", default_value=False)
    hidden.hide(True)
    top.addParmTemplate(hidden)

    # ---------------------------------------------------------------- status
    top.addParmTemplate(readonly("status", "Status", "Idle - pick a character in step 1"))

    # ---------------------------------------------------------------- step 1
    f1 = hou.FolderParmTemplate("hb_step1", "STEP 1  -  Pick Character  (input from Maya)",
                                folder_type=hou.folderType.Simple)
    f1.addParmTemplate(note("lbl1", "Choose a character: its alembic is loaded right away, "
                                    "and all caches below point to its own folder."))
    f1.addParmTemplate(S("abc_folder", "Alembic Folder", 1, default_value=["$HIP"],
                         string_type=hou.stringParmType.FileReference,
                         file_type=hou.fileType.Directory))
    f1.addParmTemplate(S("char", "Character", 1, default_value=[""],
                         item_generator_script="hou.session.hb_char_menu(kwargs)",
                         item_generator_script_language=PY, menu_type=hou.menuType.Normal))
    f1.addParmTemplate(readonly("abc_path", "Reading", '`chs("abc_folder")`/`chs("char")`.abc'))
    f1.addParmTemplate(S("abc_node", "Alembic SOP", 1, default_value=[ABC_NODE_DEFAULT],
                         string_type=hou.stringParmType.NodeReference))
    top.addParmTemplate(f1)

    # ---------------------------------------------------------------- step 2
    f2 = hou.FolderParmTemplate("hb_step2", "STEP 2  -  Output Paths  (set once per shot)",
                                folder_type=hou.folderType.Simple)
    f2.addParmTemplate(note("lbl2", "Paths and frame range for every cache and ROP. "
                                    "After changing anything here press Apply."))
    f2.addParmTemplate(S("cache_root", "Sim Cache Root", 1, default_value=["$HIP/cache"],
                         string_type=hou.stringParmType.FileReference,
                         file_type=hou.fileType.Directory))
    f2.addParmTemplate(S("sim_nodes", "Sim Caches", 1, default_value=[SIM_DEFAULT]))
    f2.addParmTemplate(readonly("cache_preview", "  -> writes to",
                                '`chs("cache_root")`/`chs("char")`/<part>/'))
    f2.addParmTemplate(hou.SeparatorParmTemplate("sep2"))
    f2.addParmTemplate(S("export_root", "Export Root (Maya)", 1, default_value=["$HIP/from_houdini"],
                         string_type=hou.stringParmType.FileReference,
                         file_type=hou.fileType.Directory))
    f2.addParmTemplate(S("export_nodes", "Alembic ROPs", 1, default_value=[EXPORT_DEFAULT]))
    f2.addParmTemplate(readonly("export_preview", "  -> writes to",
                                '`chs("export_root")`/`chs("char")`/<part>.abc'))
    f2.addParmTemplate(hou.SeparatorParmTemplate("sep4"))
    fr = hou.FloatParmTemplate("start_frame", "Start Frame", 1, default_value=[950],
                               min=0, max=2000, min_is_strict=False, max_is_strict=False)
    fr.setJoinWithNext(True)
    f2.addParmTemplate(fr)
    f2.addParmTemplate(hou.FloatParmTemplate("end_frame", "End", 1, default_value=[1103],
                                             min=0, max=2000, min_is_strict=False,
                                             max_is_strict=False))
    f2.addParmTemplate(hou.ToggleParmTemplate("set_solver_start", "Vellum Solver starts at Start Frame",
                                              default_value=True))
    f2.addParmTemplate(hou.ToggleParmTemplate("set_timeline", "Set Houdini timeline to this range",
                                              default_value=True))
    f2.addParmTemplate(button("frames_tl", "Get From Timeline",
                              "hou.session.hb_frames_from_timeline(kwargs)", join=True))
    f2.addParmTemplate(button("frames_apply", "Apply Frame Range",
                              "hou.session.hb_apply_frames(kwargs)"))
    f2.addParmTemplate(hou.SeparatorParmTemplate("sep5"))
    f2.addParmTemplate(button("wire", "Apply Paths + Frames to Nodes", "hou.session.hb_wire(kwargs)"))
    top.addParmTemplate(f2)

    # ---------------------------------------------------------------- step 3
    f3 = hou.FolderParmTemplate("hb_step3", "STEP 3  -  Run",
                                folder_type=hou.folderType.Simple)
    f3.addParmTemplate(note("lbl3", "Direct mode: per character only the 3 alembic ROPs run (each one simulates)."
                                    " Press Check Paths first, then test one with Run Current."))
    f3.addParmTemplate(S("run_chars", "Characters to Run", 1, default_value=["*"],
                         help="Space separated patterns. * = all, e.g.  wildebeest_*  ^zebra_01"))
    f3.addParmTemplate(hou.MenuParmTemplate(
        "run_mode", "Run Mode",
        menu_items=("direct", "cache"),
        menu_labels=("Direct: ROP sims + exports  (no sim cache)",
                      "Cache: sim to disk first, ROP reads the cache"),
        default_value=0))
    sk = hou.ToggleParmTemplate("skip_cached",
                                "Skip sim if its cache already exists (export only)",
                                default_value=False)
    sk.setConditional(hou.parmCondType.HideWhen, "{ run_mode == direct }")
    f3.addParmTemplate(sk)
    f3.addParmTemplate(button("check", "Check Paths (dry run)", "hou.session.hb_check(kwargs)"))
    f3.addParmTemplate(button("run_current", "Run Current Character",
                              "hou.session.hb_run_current(kwargs)", join=True))
    f3.addParmTemplate(button("run_all", ">>  RUN ALL CHARACTERS  <<", "hou.session.hb_run_all(kwargs)"))
    f3.addParmTemplate(hou.SeparatorParmTemplate("sep3"))
    f3.addParmTemplate(button("open_cache", "Open Cache Folder",
                              'hou.session.hb_open(kwargs, "cache_root")', join=True))
    f3.addParmTemplate(button("open_export", "Open from_houdini Folder",
                              'hou.session.hb_open(kwargs, "export_root")'))
    top.addParmTemplate(f3)

    # ---------------------------------------------------------------- step 4
    f4 = hou.FolderParmTemplate("hb_step4", "STEP 4  -  Run in Background  (several sims at once on this PC)",
                                folder_type=hou.folderType.Simple)
    f4.addParmTemplate(note("lbl4", "Runs the same jobs as RUN ALL, but in the background and in parallel. "
                                    "Houdini stays free. Uses Characters to Run from Step 3."))
    f4.addParmTemplate(hou.IntParmTemplate("bg_slots", "Sims at the same time", 1, default_value=[4],
                                           min=1, max=8, min_is_strict=True))
    f4.addParmTemplate(hou.FloatParmTemplate("bg_min_ram", "Min free RAM to start (GB)", 1,
                                             default_value=[12], min=2, max=64))
    f4.addParmTemplate(button("bg_run", ">>  RUN IN BACKGROUND  <<", "hou.session.hb_bg_run(kwargs)"))
    f4.addParmTemplate(button("bg_stop", "Stop", "hou.session.hb_bg_stop(kwargs)", join=True))
    f4.addParmTemplate(button("bg_logs", "Open Logs", "hou.session.hb_bg_logs(kwargs)"))
    top.addParmTemplate(f4)

    ptg.append(top)
    ctrl.setParmTemplateGroup(ptg)

    # parms with the same name keep their old values - reset the display fields
    for name in ("abc_path", "cache_preview", "export_preview", "status"):
        p = ctrl.parm(name)
        if p is not None:
            p.deleteAllKeyframes()
            p.revertToDefaults()


def install():
    if not hou.hipFile.path() or hou.hipFile.basename().startswith("untitled"):
        hou.ui.displayMessage("Save the hip file first (alembics are read from $HIP).",
                              severity=hou.severityType.Warning)
        return
    ctrl = hou.node(CTRL_DEFAULT)
    if ctrl is None:
        sel = hou.selectedNodes()
        if not sel:
            hou.ui.displayMessage("Control null not found:\n{0}\n\nSelect your control null and run again."
                                  .format(CTRL_DEFAULT), severity=hou.severityType.Warning)
            return
        ctrl = sel[0]

    _install_session_code()
    _build_parms(ctrl)

    chars = hou.session._hb_list_chars(ctrl)
    if chars and not ctrl.evalParm("char"):
        ctrl.parm("char").set(chars[0])

    try:
        report = hou.session.hb_wire({"node": ctrl})
        wired = "\n".join(report)
    except Exception as e:
        wired = "Could not wire nodes yet:\n{0}\n\nFix the node names on SETUP_RUN and press " \
                "'Apply Paths to Nodes'.".format(e)

    ctrl.setSelected(True, clear_all_selected=True)
    hou.ui.displayMessage("SETUP_RUN is ready.\n\n{0} alembic(s) found in $HIP\n\n{1}".format(
        len(chars), wired), title="Batch Hair Sim")


install()
