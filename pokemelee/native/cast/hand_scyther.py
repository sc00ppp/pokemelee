"""Source-shaped Scyther on Link; replayable from the untouched pre-prep copy.

The actual source bone membership separates anatomy inside shared materials.
Stored corner normals remain untouched; stand_feet and round_out follow this.
"""

from cast_paths import WORK, TARGETS
import json
import sys
from pathlib import Path

import bpy
import numpy as np
from PIL import Image
from mathutils import Vector, Matrix

R = Path(str(WORK / ''))
ROOT = R/'hand/scyther-Link'
BUILD = ROOT/'3-build'
data = json.loads((ROOT/'review/inventory.json').read_text(encoding='utf-8'))
src = data['source']
sb = {k:np.array(v['head']) for k,v in src['bones'].items()}
tb = {k:np.array(v['head']) for k,v in data['base']['bones'].items()}

def unit(v):
    return v / np.linalg.norm(v)

def rotation(a,b):
    return np.array(Vector(a).normalized().rotation_difference(Vector(b).normalized()).to_matrix())

def weights(ob,i,held):
    for g in ob.vertex_groups:
        g.remove([i])
    for name,w in held.items():
        if w > 1e-6:
            (ob.vertex_groups.get(name) or ob.vertex_groups.new(name=name)).add([i],float(w),'REPLACE')

def tube(p,a,b,ta,tb,radial):
    d=b-a
    f=np.dot(p-a,d)/np.dot(d,d)
    off=p-a-f*d
    return ta+f*(tb-ta)+radial*rotation(d,tb-ta)@off, f

def blade_frame(root,tip):
    forward=unit(sb[tip]-sb[root])
    up=unit(np.array([0.,0.,1.])-forward[2]*forward)
    across=unit(np.cross(forward,up))
    return np.column_stack([across,forward,up])

bpy.ops.wm.open_mainfile(filepath=str(BUILD/'base.blend'))
body_a=sb['Bone_02']
body_b=sb['Bone_23']
body_ta=tb['JOBJ_4']
body_tb=np.array([0.,-.22,12.2])
body_rot=rotation(body_b-body_a,body_tb-body_ta)
wing_rot=np.array(Matrix.Rotation(np.deg2rad(-48),3,'X'))
blades={}
for root,tip,wrist in [('Bone_05','Bone_08_HandLeft','JOBJ_23'),
                       ('Bone_10','Bone_13_HandRight','JOBJ_55')]:
    sf=blade_frame(root,tip)
    # The cutting axis follows the sword direction, the broad face remains
    # vertical. Keep the forearm root on the wrist in every animation.
    # Link's raised shield puts a straight-up scythe over the near eye in Run.
    # Splay only that blade outward; in Run this moves it forward of the face.
    forward=unit(np.array([-.62 if root=='Bone_10' else 0.,-1.,0.]))
    up=np.array([0.,0.,1.])
    tf=np.column_stack([np.cross(forward,up),forward,up])
    upper='Bone_04' if root=='Bone_05' else 'Bone_09'
    shoulder='JOBJ_21' if root=='Bone_05' else 'JOBJ_53'
    elbow='JOBJ_22' if root=='Bone_05' else 'JOBJ_54'
    weapon='JOBJ_25' if root=='Bone_05' else 'JOBJ_67'
    blades[root]=(sf,tf,weapon,upper,shoulder,elbow,np.linalg.norm(sb[tip]-sb[root]))

arms={'Bone_04':('Bone_05','JOBJ_21','JOBJ_22','JOBJ_23'),
      'Bone_09':('Bone_10','JOBJ_53','JOBJ_54','JOBJ_55')}
thighs={'Bone_34':('Bone_35','JOBJ_6','JOBJ_7'),
        'Bone_40':('Bone_41','JOBJ_12','JOBJ_13')}
shins={'Bone_35':('Bone_36','JOBJ_7','JOBJ_9'),
       'Bone_41':('Bone_42','JOBJ_13','JOBJ_15')}
feet={'Bone_36':('Bone_38_FootLeft','JOBJ_9','JOBJ_10'),
      'Bone_42':('Bone_44_FootRight','JOBJ_15','JOBJ_16')}

for name,m in src['meshes'].items():
    ob=bpy.data.objects[name]
    assert len(ob.data.vertices)==len(m['points'])
    for i,(p,w) in enumerate(zip(np.array(m['points']),m['weights'])):
        owner=max(w,key=w.get)
        if owner in ('Bone_24','Bone_25','Bone_32'):
            q=np.array([0.,-.42,13.1])+7.2*(p-sb['Bone_24'])
            held={'JOBJ_40':1}
            # The eye overlay needs clearance from the rounded forehead.
            if name=='strike_mesh_12':
                q+=np.array([np.sign(p[0])*.045,-.035,.025])
        elif owner in ('Bone_03','Bone_23'):
            q,f=tube(p,body_a,body_b,body_ta,body_tb,6.2)
            chest=float(np.clip((q[2]-8.7)/2.4,0,1))
            held={'JOBJ_4':1-chest,'JOBJ_18':chest}
        elif owner=='Bone_02':
            q=body_ta+6.4*body_rot@(p-body_a)
            held={'JOBJ_4':1}
        elif owner in ('Bone_15','Bone_17','Bone_18','Bone_19','Bone_21','Bone_22'):
            side=1 if p[0]>=0 else -1
            root=sb['Bone_15' if side==1 else 'Bone_19']
            q=np.array([side*.65,.75,12.0])+wing_rot@((p-root)*[3.8,4.8,4.8])
            held={'JOBJ_18':1}
        elif owner in arms:
            blade,shoulder,elbow,wrist=arms[owner]
            # This source segment ends in a cone, not a second wrist ring.
            # Keep its cone short at the elbow and let the scythe's green root
            # supply Link's forearm. Stretching the cone to the wrist made a needle.
            q,f=tube(p,sb[owner],sb[blade],tb[shoulder],tb[elbow],5.0)
            elbow_share=float(np.clip((f-.55)/.25,0,1))
            held={shoulder:1-elbow_share,elbow:elbow_share}
        elif owner in blades:
            sf,tf,weapon,upper,shoulder,elbow,length=blades[owner]
            local=sf.T@(p-sb[owner])
            blend=float(np.clip((local[1]-.03)/.19,0,1))
            root_q,_=tube(p,sb[upper],sb[owner],tb[shoulder],tb[elbow],5.0)
            far_q=tb[weapon]+tf@np.array([local[0]*7.0,max(local[1]-.22,0)/(length-.22)*9.6,local[2]*8.0])
            q=root_q*(1-blend)+far_q*blend
            held={elbow:1-blend,weapon:blend}
        elif owner in thighs:
            end,hip,knee=thighs[owner]
            q,f=tube(p,sb[owner],sb[end],tb[hip],tb[knee],4.8)
            knee_share=float(np.clip((f-.9)/.25,0,1))
            held={hip:1-knee_share,knee:knee_share}
        elif owner in shins:
            end,knee,foot=shins[owner]
            q,f=tube(p,sb[owner],sb[end],tb[knee],tb[foot],4.8)
            held={knee:1}
        elif owner in feet:
            tip,foot,toe=feet[owner]
            forward=sb[tip]-sb[owner]
            forward[2]=0
            target=tb[toe]-tb[foot]
            target[2]=0
            rot=rotation(forward,target)
            q=tb[foot]+6.2*rot@(p-sb[owner])
            held={foot:1}
        else:
            raise ValueError(owner)
        ob.data.vertices[i].co=q
        weights(ob,i,held)
    ob.data.update()

# The source membrane is uniformly half transparent, with no alpha cutout.
# In Melee its overlapping triangles sort as dark facets. Preserve its exact
# RGB gradient and make the four small membranes opaque like the official art.
mat=bpy.data.materials['strike_mat_9']
texnode=next(n for n in mat.node_tree.nodes if n.type=='TEX_IMAGE' and n.image)
im=texnode.image
rgba=np.array(im.pixels[:]).reshape(im.size[1],im.size[0],4)
rgba[:,:,3]=1
path=ROOT/'wing-opaque.png'
Image.fromarray(np.rint(rgba[::-1]*255).astype(np.uint8)).save(path)
new=bpy.data.images.load(str(path),check_existing=False)
new.pack()
texnode.image=new
bsdf=next(n for n in mat.node_tree.nodes if n.type=='BSDF_PRINCIPLED')
for link in list(bsdf.inputs['Alpha'].links):
    mat.node_tree.links.remove(link)
bsdf.inputs['Alpha'].default_value=1
mat.surface_render_method='DITHERED'

# This raw build predates the fixed make_fixed UV argument and has no eye
# objects. Read the existing source atlas directly, with its real 64-pixel rows.
from rigswap.core import eyes
eye=bpy.data.objects['strike_mesh_12']
tex=next(n.image for n in eye.data.materials[0].node_tree.nodes if n.type=='TEX_IMAGE' and n.image)
sur=eyes.Surface(1,eye,0,list(range(len(eye.data.polygons))),tex.name)
record=eyes.make_fixed(BUILD,[sur],{tex.name:eyes._pixels(tex)},
                       {'half':[0,64],'closed':[0,128],'band':64})
(BUILD/'eyes.json').write_text(json.dumps(record,indent=2),encoding='utf-8')

# The export contract explicitly replaces each weapon and suppresses its
# stowed form and sheath. No target facts or rigswap code are modified.
slots=json.loads(Path(str(TARGETS / 'Link.weapons.json')).read_text(encoding='utf-8'))['weapons']
for s in slots:
    s['replacement']='Scyther anatomical forearm scythe'
    s['attachment']='JOBJ_25' if s['part']=='sword' else 'JOBJ_67'
(BUILD/'weapons_replaced.json').write_text(json.dumps(slots,indent=2),encoding='utf-8')
bpy.ops.wm.save_as_mainfile(filepath=str(BUILD/'build.blend'))
bpy.ops.wm.save_as_mainfile(filepath=str(BUILD/'edited.blend'))
(ROOT/'edit-record.json').write_text(json.dumps({
    'source':'mons/scyther/1-load/models/1-123_Scyther.blend',
    'head':'Source skull, jaw, teeth and eyes share a rigid transform, scale 7.2',
    'body':'Source torso upright; cross-section 6.2; pointed abdomen 6.4',
    'limbs':'Source geometry along actual Link joints; cross-section 4.8-5.0',
    'blades':'Source scythe roots on elbows; green base spans forearms; cutting blades on sword JOBJ_25 / shield JOBJ_67; supported weapon replacement',
    'wings':'Source four-wing assembly reduced and folded behind thorax; uniform half-alpha replaced with opacity to avoid sorting facets',
    'eyes':'Source atlas with clamping and real 64-pixel blink stride',
    'normals':'Stored normals unmodified; round_out is the only subdivision/shading step',
},indent=2),encoding='utf-8')
