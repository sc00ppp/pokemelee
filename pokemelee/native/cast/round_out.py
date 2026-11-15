"""round_out.py <build dir> [--flat]: a low-poly port rounded out, from base.blend and edited.blend into build.blend.

A Colosseum model is 700 to 1300 triangles and a Melee fighter several thousand, and a port stretches those few triangles
along longer limbs, so at Melee's camera the silhouette reads as blocky panels. The model's own normals already say what
the surface does between its vertices, so every triangle is cut in four and each new point sits where those normals curve
to (a PN triangle edge), leaving the original points where they were. Shading then comes from the rounded surface itself,
shared by every corner at a place across all meshes, so no join between the rip's many small pieces shows. The rip's
stored normals decide what is a real crease: corners at one place stay apart only if the rip kept them apart. A crease
edge stays straight, so thin blades and fins keep their edge. --flat does the shading alone, with no new triangles.
--idle Fighter rounds in the fighter's idle pose and binds back after: a port fitted at idle has no one smooth surface in
the bind, and rounding there shatters it.

Run before hand_finish: it replaces build.blend with the unprepped result."""
import sys
from pathlib import Path

import bpy
import bmesh
from mathutils import Vector, kdtree
import numpy as np

CREASE = 30.0       # rip normals further apart than this at one place are a real edge
WELD = 1e-4         # corners this close, as a share of the model's size, are one place
MOST = .22          # the furthest a new point leaves its edge, as a share of the edge
WEIGHTS = 4         # joints a new point keeps: two vertices' weights together can pass the import's limit
SAME = 1e-4         # new points this close to an edge's midpoint are that edge's
RIP = 'rip_normal'


def mesh_objects():
    return [o for o in bpy.data.objects if o.type == 'MESH' and len(o.data.polygons)]


def stored_normals(me):
    values = np.empty(len(me.loops) * 3)
    me.corner_normals.foreach_get('vector', values)
    return values.reshape(-1, 3)


def tag_creases(meshes, rip):
    """Each corner carries the rip's normal through the cut, so a crease is still known on the new corners."""
    matched = 0
    for ob in meshes:
        me = ob.data
        normals = rip.get(ob.name)
        if normals is None or len(normals) != len(me.loops):
            print('no rip normals for', ob.name)
            normals = stored_normals(me)
        else:
            matched += 1
        if 'custom_normal' in me.attributes:
            me.attributes.remove(me.attributes['custom_normal'])
        layer = me.attributes.new(RIP, 'FLOAT_VECTOR', 'CORNER')
        layer.data.foreach_set('vector', normals.ravel())
    print('rip normals on %d of %d meshes' % (matched, len(meshes)))


def corners(ob):
    """(places, unit face normals, angles at the corner, rip normals) of one mesh, corner by corner."""
    me = ob.data
    co = np.array([v.co for v in me.vertices])
    index = np.empty(len(me.loops), int)
    me.loops.foreach_get('vertex_index', index)
    normals = np.empty(len(me.polygons) * 3)
    me.polygons.foreach_get('normal', normals)
    normals = normals.reshape(-1, 3)
    place, face, angle = co[index], np.empty((len(index), 3)), np.empty(len(index))
    for p in me.polygons:
        loops = np.arange(p.loop_start, p.loop_start + p.loop_total)
        face[loops] = normals[p.index]
        a = place[np.roll(loops, 1)] - place[loops]
        b = place[np.roll(loops, -1)] - place[loops]
        length = np.linalg.norm(a, axis=1) * np.linalg.norm(b, axis=1)
        angle[loops] = np.arccos(np.clip((a * b).sum(1) / np.maximum(length, 1e-12), -1, 1))
    tags = np.empty(len(index) * 3)
    me.attributes[RIP].data.foreach_get('vector', tags)
    tags = tags.reshape(-1, 3)
    tags /= np.maximum(np.linalg.norm(tags, axis=1, keepdims=True), 1e-9)
    return place, face, angle, tags


def groups(place):
    """Place number of each corner, and the corners of each place."""
    weld = np.ptp(place, axis=0).max() * WELD
    _, group = np.unique(np.round(place / weld).astype(np.int64), axis=0, return_inverse=True)
    group = group.ravel()
    order = np.argsort(group, kind='stable')
    return group, np.split(order, np.flatnonzero(np.diff(group[order])) + 1)


def surface_normals(meshes):
    """(place number, normal) corner by corner: faces meeting at a place, by angle, among corners the rip kept together."""
    parts = [corners(ob) for ob in meshes]
    place, face, angle, tags = [np.concatenate(p) for p in zip(*parts)]
    group, members_of = groups(place)
    crease = np.cos(np.radians(CREASE))
    out = face.copy()
    for members in members_of:
        near = tags[members] @ tags[members].T > crease
        total = near @ (face[members] * angle[members, None])
        length = np.linalg.norm(total, axis=1)
        good = length > 1e-9
        out[members[good]] = total[good] / length[good, None]
    ends = np.cumsum([len(p[0]) for p in parts])[:-1]
    return np.split(place, ends), np.split(group, ends), np.split(out, ends)


def shade(meshes):
    _, _, normals = surface_normals(meshes)
    for ob, values in zip(meshes, normals):
        me = ob.data
        me.polygons.foreach_set('use_smooth', [True] * len(me.polygons))
        me.normals_split_custom_set(values.tolist())
        me.update()


def offsets(meshes):
    """(mesh, edge's two vertices) -> how far the edge's new point leaves its midpoint."""
    places, numbers, normals = surface_normals(meshes)
    edges = {}
    for ob, place, number, normal in zip(meshes, places, numbers, normals):
        for p in ob.data.polygons:
            loops = list(range(p.loop_start, p.loop_start + p.loop_total))
            for i, j in zip(loops, loops[1:] + loops[:1]):
                if number[i] > number[j]:
                    i, j = j, i
                edges.setdefault((number[i], number[j]), []).append((place[i], normal[i], place[j], normal[j]))
    crease = np.cos(np.radians(CREASE))
    bulge = {}
    for key, sides in edges.items():
        a, na, b, nb = [np.array(v) for v in zip(*sides)]
        if (na @ na.T).min() < crease or (nb @ nb.T).min() < crease:
            continue
        a, b = a[0], b[0]
        na, nb = [unit(n.mean(0)) for n in (na, nb)]
        edge = b - a
        off = -(edge @ na * na - edge @ nb * nb) / 8
        most = np.linalg.norm(edge) * MOST
        length = np.linalg.norm(off)
        bulge[key] = off * min(1, most / max(length, 1e-12))
    return numbers, bulge


def unit(v):
    return v / np.linalg.norm(v)


def cut(ob, number, bulge):
    """Every triangle in four, the new points moved off their edges; UVs, weights and rip normals interpolate."""
    me = ob.data
    index = np.empty(len(me.loops), int)
    me.loops.foreach_get('vertex_index', index)
    place = {}
    for v, n in zip(index, number):
        place[int(v)] = n
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.verts.ensure_lookup_table()
    moves = []
    for e in bm.edges:
        a, b = e.verts
        if a.index not in place or b.index not in place:
            continue
        pa, pb = place[a.index], place[b.index]
        off = bulge.get((min(pa, pb), max(pa, pb)))
        if off is not None:
            moves.append(((a.co + b.co) / 2, off))
    before = len(bm.verts)
    bmesh.ops.subdivide_edges(bm, edges=bm.edges[:], cuts=1, use_grid_fill=True)
    bm.verts.ensure_lookup_table()
    new = bm.verts[before:]
    weights = bm.verts.layers.deform.verify()
    for v in new:
        held = sorted(v[weights].items(), key=lambda item: -item[1])
        total = sum(w for _, w in held[:WEIGHTS])
        for group, _ in held[WEIGHTS:]:
            del v[weights][group]
        for group, w in held[:WEIGHTS]:
            v[weights][group] = w / total
    tree = kdtree.KDTree(len(new))
    for i, v in enumerate(new):
        tree.insert(v.co, i)
    tree.balance()
    for mid, off in moves:
        # Every new point here: a UV seam splits a vertex in two, so one place can hold two edges, and two new points.
        for _, i, _ in tree.find_range(mid, SAME):
            new[i].co = mid + Vector(off)
    bm.to_mesh(me)
    bm.free()
    me.update()


def idle_skin(fighter):
    ns = {'__name__': 'view_helpers'}
    source = (Path(__file__).parent / 'hand_view.py').read_text(encoding='utf-8')
    exec(compile(source.rsplit('\nmain()', 1)[0], 'hand_view.py', 'exec'), ns)
    C, rest, frame = ns['C'], ns['rests'](fighter), ns['frame'](fighter, 'Wait1-1')
    return {j: C @ m @ np.linalg.inv(rest[j]) @ np.linalg.inv(C) for j, m in frame.items() if j in rest}


def vertex_skins(ob, skin):
    names = {g.index: int(g.name.split('_')[1]) for g in ob.vertex_groups if g.name.startswith('JOBJ_')}
    out = np.empty((len(ob.data.vertices), 4, 4))
    for v in ob.data.vertices:
        held = [(names[g.group], g.weight) for g in v.groups if g.group in names and g.weight > 0]
        total = sum(w for _, w in held)
        out[v.index] = sum(w / total * skin[j] for j, w in held)
    return out


def carry(me, matrices):
    co = np.empty(len(me.vertices) * 3)
    me.vertices.foreach_get('co', co)
    moved = np.einsum('nij,nj->ni', matrices[:, :3, :3], co.reshape(-1, 3)) + matrices[:, :3, 3]
    me.vertices.foreach_set('co', moved.ravel())
    me.update()


def pose(meshes, skin):
    for ob in meshes:
        assert ob.matrix_world.is_identity, ob.name
        carry(ob.data, vertex_skins(ob, skin))


def bind_back(meshes, skin):
    """To the bind from idle, the shading normals with it."""
    for ob in meshes:
        me = ob.data
        matrices = vertex_skins(ob, skin)
        normals = stored_normals(me)
        carry(me, np.linalg.inv(matrices))
        index = np.empty(len(me.loops), int)
        me.loops.foreach_get('vertex_index', index)
        normals = np.einsum('nji,nj->ni', matrices[index, :3, :3], normals)
        normals /= np.maximum(np.linalg.norm(normals, axis=1, keepdims=True), 1e-9)
        me.normals_split_custom_set(normals.tolist())
        me.update()


def main():
    build = Path(sys.argv[1])
    skin = idle_skin(sys.argv[sys.argv.index('--idle') + 1]) if '--idle' in sys.argv else None
    bpy.ops.wm.open_mainfile(filepath=str(build / 'base.blend'))
    rip = {o.name: stored_normals(o.data) for o in mesh_objects()}
    bpy.ops.wm.open_mainfile(filepath=str(build / 'edited.blend'))
    meshes = mesh_objects()
    tag_creases(meshes, rip)
    if skin:
        pose(meshes, skin)
    triangles = sum(len(o.data.polygons) for o in meshes)
    if '--flat' not in sys.argv:
        numbers, bulge = offsets(meshes)
        for ob, number in zip(meshes, numbers):
            cut(ob, number, bulge)
    shade(meshes)
    for ob in meshes:
        ob.data.attributes.remove(ob.data.attributes[RIP])
    if skin:
        bind_back(meshes, skin)
    print('%d faces -> %d, %d verts' % (triangles, sum(len(o.data.polygons) for o in meshes),
                                        sum(len(o.data.vertices) for o in meshes)))
    bpy.ops.wm.save_as_mainfile(filepath=str(build / 'build.blend'))


main()
