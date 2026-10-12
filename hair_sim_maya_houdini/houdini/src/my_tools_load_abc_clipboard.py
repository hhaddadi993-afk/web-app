import os
import hou

SCALE = 0.01

def _clean_path(text):
    if not text:
        return ''
    p = text.strip().splitlines()[0].strip().strip('"').strip("'")
    if p.lower().startswith('file:///'):
        p = p[8:]
    return p.replace('\\', '/')

def _load_abc_from_clipboard():
    path = _clean_path(hou.ui.getTextFromClipboard())

    if not path.lower().endswith('.abc'):
        hou.ui.displayMessage('Clipboard is not an Alembic path:\n%s' % path,
                              severity=hou.severityType.Error)
        return
    if not os.path.isfile(path):
        hou.ui.displayMessage('File not found:\n%s' % path,
                              severity=hou.severityType.Error)
        return

    name = os.path.splitext(os.path.basename(path))[0]
    safe = ''.join(c if c.isalnum() or c == '_' else '_' for c in name)
    if safe and safe[0].isdigit():
        safe = '_' + safe

    geo = hou.node('/obj').createNode('geo', node_name=safe or 'abc_import')

    abc = geo.createNode('alembic', 'alembic_in')
    abc.parm('fileName').set(path)

    unpack = geo.createNode('unpack', 'unpack')
    unpack.setInput(0, abc)

    xform = geo.createNode('xform', 'scale_0_01')
    xform.setInput(0, unpack)
    xform.parm('scale').set(SCALE)

    out = geo.createNode('null', 'OUT')
    out.setInput(0, xform)
    out.setDisplayFlag(True)
    out.setRenderFlag(True)

    geo.layoutChildren()
    geo.setSelected(True, clear_all_selected=True)
    print('Loaded: %s  (scale %s)' % (path, SCALE))

_load_abc_from_clipboard()
