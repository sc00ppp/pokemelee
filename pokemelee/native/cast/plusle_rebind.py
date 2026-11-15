"""plusle_rebind.py <in.blend> <out.blend> [frame]: Plusle's or Minun's load stood up, its face tiles read.

The rip's rest pose is the bind pose, and these two were bound lying on the floor: the skeleton's head is not above its
arms, so body reading fails. Their own Idle animation stands them up, so its frame 15 (head on the mirror plane, ears mirror images) becomes
the rest pose: the mesh is baked there and the armature applied.

Their eyes and mouth draw one tile of a 32x272 and a 64x384 atlas through a texture transform (KHR_texture_transform),
which the load keeps as a Mapping node and nothing downstream reads: the whole atlas lands on the eye quad, squashed to
thin lines. The transform is baked into the UVs and the node goes, so the UVs point at the tile itself."""

import sys

import bpy

src, dest = sys.argv[1:3]
frame = int(sys.argv[3]) if len(sys.argv) > 3 else 15
bpy.ops.wm.open_mainfile(filepath=src)
arm = next(o for o in bpy.data.objects if o.type == 'ARMATURE')
meshes = [o for o in bpy.data.objects if o.type == 'MESH']
scene = bpy.context.scene

arm.animation_data_create()
act = next(a for a in bpy.data.actions if 'Idle' in a.name)
arm.animation_data.action = act
if hasattr(arm.animation_data, 'action_slot') and act.slots:
    arm.animation_data.action_slot = act.slots[0]
scene.frame_set(frame)
bpy.context.view_layer.update()

dg = bpy.context.evaluated_depsgraph_get()
baked = {}
for ob in meshes:
    e = ob.evaluated_get(dg)
    me = e.to_mesh()
    baked[ob.name] = [v.co.copy() for v in me.vertices]
    assert len(baked[ob.name]) == len(ob.data.vertices), ob.name
    e.to_mesh_clear()

bpy.context.view_layer.objects.active = arm
arm.select_set(True)
bpy.ops.object.mode_set(mode='POSE')
bpy.ops.pose.select_all(action='SELECT')
bpy.ops.pose.armature_apply(selected=False)
bpy.ops.object.mode_set(mode='OBJECT')
arm.animation_data_clear()
for a in list(bpy.data.actions):
    bpy.data.actions.remove(a)
for b in arm.pose.bones:
    b.matrix_basis.identity()
for ob in meshes:
    for v, co in zip(ob.data.vertices, baked[ob.name]):
        v.co = co
    ob.data.update()

for m in bpy.data.materials:
    if not m.node_tree:
        continue
    mapping = next((n for n in m.node_tree.nodes if n.type == 'MAPPING'), None)
    if mapping is None:
        continue
    loc, scale = mapping.inputs['Location'].default_value, mapping.inputs['Scale'].default_value
    user = [ob for ob in meshes if m.name in [s.name for s in ob.data.materials]]
    for ob in user:
        layer = ob.data.uv_layers.active
        us = [(d.uv[0] * scale[0] + loc[0], d.uv[1] * scale[1] + loc[1]) for d in layer.data]
        for d, uv in zip(layer.data, us):
            d.uv = uv
        print(m.name, ob.name, 'u', round(min(u for u, _ in us), 3), round(max(u for u, _ in us), 3),
              'v', round(min(v for _, v in us), 3), round(max(v for _, v in us), 3))
    for n in [n for n in m.node_tree.nodes if n.type in ('MAPPING', 'UVMAP')]:
        m.node_tree.nodes.remove(n)

bpy.ops.wm.save_as_mainfile(filepath=dest)
print('saved', dest)
