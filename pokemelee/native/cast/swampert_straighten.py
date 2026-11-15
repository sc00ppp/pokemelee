"""Straighten Swampert's belly-down Colosseum bind pose on a copied load only."""
import json
import sys
from pathlib import Path
import bpy
from mathutils import Matrix, Vector

src, dest = map(Path, sys.argv[1:3])
bpy.ops.wm.open_mainfile(filepath=str(src.resolve()))
arm = next(o for o in bpy.data.objects if o.type == 'ARMATURE')
bpy.context.view_layer.objects.active = arm
arm.select_set(True)
names = {int(b.name.split('_')[1]): b.name for b in arm.data.bones}
def pb(n): return arm.pose.bones[names[n]]
def at(n): return arm.matrix_world @ pb(n).matrix.translation
def move(n, matrix):
    pb(n).matrix = arm.matrix_world.inverted() @ matrix @ arm.matrix_world @ pb(n).matrix
    bpy.context.view_layer.update()
def shift(n, to): move(n, Matrix.Translation(Vector(to) - at(n)))
def turn(n, old_direction, new_direction):
    q = Vector(old_direction).normalized().rotation_difference(Vector(new_direction).normalized())
    p = at(n)
    move(n, Matrix.Translation(p) @ q.to_matrix().to_4x4() @ Matrix.Translation(-p))
def aim(n, tip, direction): turn(n, at(tip) - at(n), direction)
def basis(x, z):
    z = Vector(z).normalized()
    x = Vector(x); x = (x - x.dot(z) * z).normalized()
    y = z.cross(x)
    return Matrix((x, y, z)).transposed().to_4x4()

# The foot surfaces are bound to separate controls coincident with the ankle.
# Make those controls follow their actual leg before changing the pose.
bpy.ops.object.mode_set(mode='EDIT')
for child, parent in ((81, 63), (84, 70)):
    arm.data.edit_bones[names[child]].parent = arm.data.edit_bones[names[parent]]
bpy.ops.object.mode_set(mode='OBJECT')
bpy.context.view_layer.update()
head_basis = basis(at(44) - at(45), (at(55) + at(59)) / 2 - (at(52) + at(56)) / 2)
torso_basis = basis(at(9) - at(23), at(8) - at(5))
torso_change = torso_basis.inverted()
origin = at(5)
move(5, Matrix.Translation(Vector((0, 0, .65))) @ torso_change @ Matrix.Translation(-origin))

# Keep the head's own face/fin proportions, but turn it upright independently
# of the body, which had been pitched almost ninety degrees.
current_head_basis = torso_change @ head_basis
origin = at(40)
move(40, Matrix.Translation(Vector((0, -.12, 1.30))) @ current_head_basis.inverted() @ Matrix.Translation(-origin))

for shoulder, elbow, wrist, sign in ((10, 11, 15, 1), (24, 25, 29, -1)):
    shift(shoulder, (sign * .245, -.015, .94))
    aim(shoulder, elbow, (sign, 0, -.22))
    aim(elbow, wrist, (sign, -.05, -.18))
for thigh, knee, ankle, foot, toe, sign in ((61, 62, 63, 81, 82, 1), (68, 69, 70, 84, 85, -1)):
    shift(thigh, (sign * .20, 0, .64))
    aim(thigh, knee, (sign * .15, .08, -1))
    aim(knee, ankle, (0, -.12, -1))
    aim(foot, toe, (0, -1, -.12))

# Bake the deliberate repose into geometry, then make it the new bind pose.
meshes = [o for o in bpy.data.objects if o.type == 'MESH']
for ob in meshes:
    bpy.context.view_layer.objects.active = ob
    for mod in list(ob.modifiers):
        if mod.type == 'ARMATURE':
            bpy.ops.object.modifier_apply(modifier=mod.name)
bpy.context.view_layer.objects.active = arm
bpy.ops.object.mode_set(mode='POSE')
bpy.ops.pose.armature_apply(selected=False)
bpy.ops.object.mode_set(mode='OBJECT')
for ob in meshes:
    mod = ob.modifiers.new('Armature', 'ARMATURE')
    mod.object = arm
floor = min((o.matrix_world @ v.co).z for o in meshes for v in o.data.vertices)
for ob in [arm] + meshes:
    if ob.parent is None:
        ob.location.z -= floor
dest.parent.mkdir(parents=True, exist_ok=True)
bpy.ops.wm.save_as_mainfile(filepath=str(dest.resolve()))
print('straightened source; floor shift', -floor)
