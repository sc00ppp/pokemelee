"""Blender (4.3, background): a head-and-shoulders render of one or more Colosseum mon models, transparent background.

blender -b --factory-startup -P icon_render.py -- <job.json>
job: {"out": png, "size": [w, h], "views": [...]}  one render per view:
  view: {"out": png, "mons": [{"glb": path, "hide": [mesh name substrings], "height": 1.0, "x": 0, "y": 0,
                               "turn": deg}],
         "top": 0.5,      fraction of the group's height, from the top, that fills the frame
         "yaw": 25,       camera turn around the group (deg, + = camera to the mon's left, its face turned to us)
         "pitch": 8, "zoom": 1.0, "dx": 0, "dz": 0 (frame centre shift, in frame heights), "flat": false}
Each mon is scaled to `height` (its own height = 1) and stood on the floor at (x, y). glTF faces +Z, which the importer
turns into Blender -Y, so the camera looks along +Y from the -Y side.
"""
import json
import math
import sys

import bpy
from mathutils import Vector

job = json.load(open(sys.argv[sys.argv.index('--') + 1], encoding='utf-8'))


def clear():
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    for coll in (bpy.data.meshes, bpy.data.materials, bpy.data.images, bpy.data.armatures, bpy.data.cameras,
                 bpy.data.lights, bpy.data.worlds, bpy.data.actions):
        for item in list(coll):
            coll.remove(item)


def strip(objs):
    """Colosseum hit boxes and the rips' unit Icosphere: untextured meshes of 64 vertices or fewer."""
    for o in list(objs):
        if o.type != 'MESH':
            continue
        textured = any(s.material and s.material.use_nodes and any(n.type == 'TEX_IMAGE' for n in s.material.node_tree.nodes)
                       for s in o.material_slots)
        if (len(o.data.vertices) <= 64 and not textured) or o.name.startswith('Icosphere'):
            bpy.data.objects.remove(o, do_unlink=True)


def world_verts(objs):
    dg = bpy.context.evaluated_depsgraph_get()
    pts = []
    for o in objs:
        if o.type != 'MESH' or o.hide_render:
            continue
        ev = o.evaluated_get(dg)
        me = ev.to_mesh()
        mw = o.matrix_world
        pts += [mw @ v.co for v in me.vertices]
        ev.to_mesh_clear()
    return pts


def load_mon(m):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=m['glb'])
    objs = [o for o in bpy.data.objects if o not in before]
    strip(objs)
    objs = [o for o in bpy.data.objects if o not in before]
    for o in objs:
        if o.type == 'MESH' and any(h in o.name for h in m.get('hide', [])):
            o.hide_render = True
        for name, ext in m.get('wrap', {}).items():       # e.g. Gardevoir's eyes: mirrored UVs, clamped by the rip
            if o.type == 'MESH' and name in o.name:
                for s in o.material_slots:
                    for n in s.material.node_tree.nodes:
                        if n.type == 'TEX_IMAGE':
                            n.extension = ext
        # a blink strip whose rest frame is not the open one: copy rows [src, src+band) over [dst, dst+band), top-down
        for name, (dst, src, band) in m.get('rows', {}).items():
            if o.type == 'MESH' and name in o.name:
                for s in o.material_slots:
                    for n in s.material.node_tree.nodes:
                        if n.type == 'TEX_IMAGE' and n.image and not n.image.get('rows_done'):
                            import numpy as np
                            w, h = n.image.size
                            px = np.array(n.image.pixels[:], np.float32).reshape(h, w, 4)[::-1]   # top-down
                            px[dst:dst + band] = px[src:src + band]
                            n.image.pixels.foreach_set(px[::-1].ravel())
                            n.image['rows_done'] = 1
        # a face whose eye layer the rip lost: a front-on picture of the face over the piece, UVs projected straight
        # from the front off its own vertices (glTF +Z = Blender -Y, so x across and z up), `margin` in from each edge
        for name, f in m.get('face', {}).items():
            if o.type == 'MESH' and name in o.name:
                vs = o.data.vertices
                x0, x1 = min(v.co.x for v in vs), max(v.co.x for v in vs)
                z0, z1 = min(v.co.z for v in vs), max(v.co.z for v in vs)
                mg = f.get('margin', 0.0)
                for layer in o.data.uv_layers:          # every layer: the rip's face samples its second UV set
                    for loop in o.data.loops:
                        co = vs[loop.vertex_index].co
                        layer.data[loop.index].uv = (mg + (1 - 2 * mg) * (co.x - x0) / (x1 - x0),
                                                     1 - (mg + (1 - 2 * mg) * (z1 - co.z) / (z1 - z0)))
                img = bpy.data.images.load(f['image'])
                for s in o.material_slots:
                    for n in s.material.node_tree.nodes:
                        if n.type == 'TEX_IMAGE':
                            n.image = img
    roots = [o for o in objs if o.parent is None]
    pivot = bpy.data.objects.new('mon', None)
    bpy.context.scene.collection.objects.link(pivot)
    for r in roots:
        r.parent = pivot
    bpy.context.view_layer.update()
    pts = world_verts(objs)
    lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    s = m.get('height', 1.0) / max(1e-6, hi.z - lo.z)
    cx, cy = (lo.x + hi.x) / 2, (lo.y + hi.y) / 2
    for r in roots:
        r.location -= Vector((cx, cy, lo.z))
    pivot.scale = (s, s, s)
    pivot.rotation_euler = (0, 0, math.radians(m.get('turn', 0)))
    pivot.location = (m.get('x', 0), m.get('y', 0), 0)
    bpy.context.view_layer.update()
    return objs


def flat_materials(objs):
    """Texture colour straight to the output: no light, as Colosseum's own textures read (AniMelee look)."""
    for o in objs:
        for s in getattr(o, 'material_slots', []):
            mat = s.material
            if not mat or not mat.use_nodes:
                continue
            nt = mat.node_tree
            bsdf = next((n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED'), None)
            out = next((n for n in nt.nodes if n.type == 'OUTPUT_MATERIAL'), None)
            if not bsdf or not out:
                continue
            em = nt.nodes.new('ShaderNodeEmission')
            col = bsdf.inputs['Base Color']
            if col.is_linked:
                nt.links.new(col.links[0].from_socket, em.inputs['Color'])
            else:
                em.inputs['Color'].default_value = col.default_value
            mix = nt.nodes.new('ShaderNodeMixShader')
            tr = nt.nodes.new('ShaderNodeBsdfTransparent')
            alpha = bsdf.inputs['Alpha']
            if alpha.is_linked:
                nt.links.new(alpha.links[0].from_socket, mix.inputs['Fac'])
            else:
                mix.inputs['Fac'].default_value = alpha.default_value
            nt.links.new(tr.outputs[0], mix.inputs[1])
            nt.links.new(em.outputs[0], mix.inputs[2])
            nt.links.new(mix.outputs[0], out.inputs['Surface'])


def render(view, size):
    clear()
    sc = bpy.context.scene
    objs = []
    for m in view['mons']:
        objs += load_mon(m)
    if view.get('flat'):
        flat_materials(objs)
    pts = world_verts([o for o in bpy.data.objects])
    top = max(p.z for p in pts)
    span = view.get('top', 0.5) * top
    band = [p for p in pts if p.z >= top - span] or pts
    # centred across on the head (the top part of the band), not on arms or a tail held out to one side
    head = [p for p in pts if p.z >= top - span * view.get('head', 0.5)] or band
    c = Vector(((min(p.x for p in head) + max(p.x for p in head)) / 2,
                (min(p.y for p in head) + max(p.y for p in head)) / 2,
                top - span / 2))
    w_band = max(p.x for p in band) - min(p.x for p in band)
    aspect = size[0] / size[1]
    frame_h = (max(span, w_band / aspect) if view.get('fitw') else span) / view.get('zoom', 1.0)
    if 'at' in view:    # [centre, height] of the frame as fractions of the group's height: a head below wings or a tail
        c = Vector((view.get('cx', 0.0) * top, 0, view['at'][0] * top))
        frame_h = view['at'][1] * top
    c.z += view.get('dz', 0) * frame_h
    c.x += view.get('dx', 0) * frame_h
    cam_d = bpy.data.cameras.new('cam')
    cam_d.type = 'ORTHO'
    cam_d.ortho_scale = frame_h * aspect * 1.08
    cam = bpy.data.objects.new('cam', cam_d)
    sc.collection.objects.link(cam)
    yaw, pitch = math.radians(view.get('yaw', 25)), math.radians(view.get('pitch', 8))
    d = 10.0
    cam.location = c + Vector((math.sin(yaw) * math.cos(pitch) * d, -math.cos(yaw) * math.cos(pitch) * d, math.sin(pitch) * d))
    cam.rotation_euler = (c - cam.location).to_track_quat('-Z', 'Y').to_euler()
    cam_d.clip_end = 100
    sc.camera = cam
    if not view.get('flat'):
        for name, rot, energy in (('key', (50, 0, -35), 3.2), ('fill', (60, 0, 50), 1.2), ('rim', (-30, 0, 170), 2.0)):
            ld = bpy.data.lights.new(name, 'SUN')
            ld.energy = energy
            lo = bpy.data.objects.new(name, ld)
            lo.rotation_euler = [math.radians(a) for a in rot]
            sc.collection.objects.link(lo)
        world = bpy.data.worlds.new('w')
        world.use_nodes = True
        world.node_tree.nodes['Background'].inputs['Strength'].default_value = 0.9
        world.node_tree.nodes['Background'].inputs['Color'].default_value = (1, 1, 1, 1)
        sc.world = world
    sc.render.engine = 'BLENDER_EEVEE_NEXT'
    sc.eevee.taa_render_samples = 32
    sc.render.film_transparent = True
    sc.view_settings.view_transform = 'Standard'
    sc.render.resolution_x, sc.render.resolution_y = size
    sc.render.resolution_percentage = 100
    sc.render.filepath = view['out']
    bpy.ops.render.render(write_still=True)
    print('rendered', view['out'], flush=True)


for v in job['views']:
    try:
        render(v, job.get('size', [256, 224]))
    except Exception as exc:
        import traceback
        traceback.print_exc()
        print('FAILED', v['out'], exc, flush=True)
