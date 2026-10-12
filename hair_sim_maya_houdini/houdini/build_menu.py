# -*- coding: utf-8 -*-
"""Rebuild MainMenuCommon.xml from houdini/src/.  Run after every source change:

    python build_menu.py            # writes MainMenuCommon.xml next to this file
    python build_menu.py --check    # syntax-check all sources, write nothing

Install: copy MainMenuCommon.xml to  Documents/houdini22.x/
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "src")
OUT = os.path.join(HERE, "MainMenuCommon.xml")

# (id, label, source file) in menu order; None = separator
ITEMS = [
    ("my_tools_load_abc_clipboard", "Load ABC from Clipboard (Unpack + 0.01)",
     "my_tools_load_abc_clipboard.py"),
    None,
    ("my_tools_save_hip_clipboard", "Save HIP to Clipboard Path",
     "my_tools_save_hip_clipboard.py"),
    None,
    ("my_tools_batch_hair_sim", "Batch Hair Sim: Setup SETUP_RUN",
     "install_template.py"),
]


def _read(name):
    with open(os.path.join(SRC, name), encoding="utf-8", newline="") as f:
        return f.read().replace("\r\n", "\n")


def _script(file_name):
    code = _read(file_name)
    if file_name == "install_template.py":
        # session_code.py is embedded as a Python string literal
        code = code.replace("__SESSION_SRC__", repr(_read("session_code.py")))
    if "]]>" in code:
        raise ValueError(file_name + ": contains ']]>' (breaks CDATA)")
    return code.strip("\n") + "\n"


def build():
    parts = ['<?xml version="1.0" encoding="UTF-8"?>', "<mainMenu>", "  <menuBar>", "",
             '    <subMenu id="my_tools_menu">', "      <label>My Tools</label>", ""]
    for it in ITEMS:
        if it is None:
            parts += ["      <separatorItem/>", ""]
            continue
        sid, label, fname = it
        compile(_script(fname), fname, "exec")          # syntax check
        parts += ['      <scriptItem id="%s">' % sid,
                  "        <label>%s</label>" % label,
                  "        <scriptCode><![CDATA[",
                  _script(fname) + "]]></scriptCode>",
                  "      </scriptItem>", ""]
    parts += ["    </subMenu>", "", "  </menuBar>", "</mainMenu>", ""]
    return "\n".join(parts)


if __name__ == "__main__":
    xml = build()
    compile(_read("session_code.py"), "session_code.py", "exec")
    if "--check" in sys.argv:
        print("OK: all sources compile")
    else:
        with open(OUT, "w", encoding="utf-8", newline="\n") as f:
            f.write(xml)
        print("Wrote %s (%d bytes)" % (OUT, len(xml.encode("utf-8"))))
