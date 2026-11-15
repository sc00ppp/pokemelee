"""Bake Swampert's own Idle pose with all source faces and custom normals."""

from cast_paths import WORK, TARGETS
from pathlib import Path
import bpy
import json
from collections import defaultdict
R=Path(str(WORK / ''))
bpy.ops.wm.open_mainfile(filepath=str(R/'mons/swampert/1-load/models/1-g3_laglarge.blend'))
arm=next(o for o in bpy.data.objects if o.type=='ARMATURE')
# Material splits repeat a boundary with different source skin weights.
# Average those weights before posing so the shared surface stays shared.
seams=defaultdict(list)
for ob in bpy.data.objects:
    if ob.type!='MESH':continue
    groups={g.index:g.name for g in ob.vertex_groups}
    for v in ob.data.vertices:
        key=tuple(round(x,4) for x in ob.matrix_world@v.co)
        seams[key].append((ob,v.index,{groups[g.group]:g.weight for g in v.groups if g.weight>0}))
for copies in seams.values():
    total=defaultdict(float)
    for ob,i,ws in copies:
        for name,w in ws.items():total[name]+=w/len(copies)
    for ob,i,ws in copies:
        for g in ob.vertex_groups:g.remove([i])
        for name,w in total.items():
            (ob.vertex_groups.get(name) or ob.vertex_groups.new(name=name)).add([i],w,'REPLACE')
for track in arm.animation_data.nla_tracks:track.mute=True
arm.animation_data.action=bpy.data.actions['laglarge_0_Idle']
bpy.context.scene.frame_set(15);bpy.context.view_layer.update()
meshes=[o for o in bpy.data.objects if o.type=='MESH']
for ob in meshes:
    bpy.context.view_layer.objects.active=ob
    for mod in list(ob.modifiers):
        if mod.type=='ARMATURE':bpy.ops.object.modifier_apply(modifier=mod.name)
    assert ob.data.has_custom_normals,ob.name
bpy.context.view_layer.objects.active=arm
arm.select_set(True)
bpy.ops.object.mode_set(mode='POSE');bpy.ops.pose.armature_apply(selected=False);bpy.ops.object.mode_set(mode='OBJECT')
arm.animation_data_clear()
for ob in meshes:
    mod=ob.modifiers.new('Armature','ARMATURE');mod.object=arm
out=R/'hand/swampert-DonkeyKong/v2/source-idle.blend'
bpy.ops.wm.save_as_mainfile(filepath=str(out))
print('HEADS')
for b in arm.data.bones:
    if int(b.name.split('_')[1]) in (5,7,8,9,10,11,15,23,24,25,29,40,44,45,55,59,61,62,63,68,69,70,74,81,82,83,84,85,86):print(b.name,list(arm.matrix_world@b.head_local))
