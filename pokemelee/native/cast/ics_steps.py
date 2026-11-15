"""Run the existing hand tools with isolated IC targets and preserved source normals."""

from cast_paths import WORK, TARGETS
import sys
import numpy as np
from ics_runtime import enable, helpers, ROOT
enable()
step, *args = sys.argv[1:]
sys.argv = [step, *args]
if step == 'round_out':
    ns = helpers('round_out.py')
    def tag(meshes, rip):
        for ob in meshes:
            me = ob.data
            values = ns['stored_normals'](me)
            if ns['RIP'] in me.attributes:
                me.attributes.remove(me.attributes[ns['RIP']])
            layer = me.attributes.new(ns['RIP'], 'FLOAT_VECTOR', 'CORNER')
            layer.data.foreach_set('vector', values.ravel())
    def surface(meshes):
        parts = [ns['corners'](ob) for ob in meshes]
        place = np.concatenate([p[0] for p in parts])
        group, _ = ns['groups'](place)
        cuts = np.cumsum([len(p[0]) for p in parts])[:-1]
        return np.split(place,cuts), np.split(group,cuts), [p[3] for p in parts]
    # round_out still performs its PN edge cut, but its normals come from the
    # source's interpolated CORNER attribute, never face-normal reconstruction.
    ns['tag_creases'] = tag
    ns['surface_normals'] = surface
    import inspect
    code = inspect.getsource(ns['cut'])
    code = code.replace('new = bm.verts[before:]\n    weights = bm.verts.layers.deform.verify()',
                        'weights = bm.verts.layers.deform.verify()\n    new = bm.verts[before:]')
    exec(compile(code, 'ics-round-cut', 'exec'), ns)
elif step == 'soft_legs':
    ns = helpers('soft_legs.py')
    ns['CHAINS']['Nana'] = (4, (36,37,39), (42,43,45))
    ns.setdefault('SPANS', {})
    # Smoochum has only two short foot lobes below the belly. No source thigh
    # or shin crosses Nana's knee; do not invent that anatomy for this helper.
    original_ring = ns['ring']
    def ring(*values):
        if not np.isfinite(values[-1]):
            return 0
        return original_ring(*values)
    ns['ring'] = ring
elif step in ('hand_view', 'stand_feet'):
    ns = helpers(step+'.py')
else:
    raise ValueError(step)
ns['main']()
