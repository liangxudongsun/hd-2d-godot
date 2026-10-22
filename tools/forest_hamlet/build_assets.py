#!/usr/bin/env python3
"""Original deterministic woodland models. Run with Blender --background --python.

Sources and GLBs stay in the consuming project. Textures come from AW's archived
material workflow; no material is sampled from the reference video.
"""
from pathlib import Path
import hashlib
import json
import math
import random
import sys

import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'assets/forest-hamlet/models'
SOURCE = ROOT / 'art/inputs/forest-hamlet/blender'
TEXTURES = ROOT / 'assets/forest-hamlet/textures'
SEED = 20261022
RNG = random.Random(SEED)
MATS = {}


def material(name, color, texture=None, emission=0.0, roughness=0.85):
    m = bpy.data.materials.new(name)
    m.diffuse_color = (*color, 1)
    m.use_nodes = True
    bsdf = m.node_tree.nodes.get('Principled BSDF')
    bsdf.inputs['Base Color'].default_value = (*color, 1)
    bsdf.inputs['Roughness'].default_value = roughness
    if emission:
        bsdf.inputs['Emission Color'].default_value = (*color, 1)
        bsdf.inputs['Emission Strength'].default_value = emission
    if texture:
        image = bpy.data.images.load(str(TEXTURES / texture), check_existing=True)
        image.pack()
        image.filepath = bpy.path.relpath(str(TEXTURES / texture), start=str(SOURCE))
        node = m.node_tree.nodes.new('ShaderNodeTexImage')
        node.image = image
        node.interpolation = 'Closest'
        m.node_tree.links.new(node.outputs['Color'], bsdf.inputs['Base Color'])
    MATS[name] = m
    return m


def setup_materials():
    material('timber', (0.49, 0.28, 0.12), 'wood.png')
    material('stone', (0.37, 0.43, 0.39), 'stone.png')
    material('roof', (0.55, 0.31, 0.11), 'wood.png')
    material('beam', (0.19, 0.10, 0.052))
    material('plaster', (0.76, 0.68, 0.45))
    material('glass', (0.22, 0.47, 0.55), roughness=0.24)
    material('window_glow', (1.0, 0.65, 0.26), emission=0.6)
    material('iron', (0.085, 0.10, 0.10), roughness=0.5)
    material('trunk', (0.31, 0.18, 0.085), 'wood.png')
    for i, c in enumerate([(0.27,0.42,0.12),(0.35,0.48,0.16),(0.21,0.35,0.12),(0.43,0.52,0.19),(0.19,0.30,0.13)]):
        material('leaf_' + str(i), c)
    for name,c in [('flower_white',(.94,.88,.62)),('flower_pink',(.81,.29,.37)),('flower_blue',(.31,.52,.72)),('flower_gold',(.94,.63,.18))]:
        material(name,c)


def assign(obj, mat, name):
    obj.name = name
    obj.data.materials.append(MATS[mat])
    return obj


def cube(name, p, s, mat, bevel=0.0):
    bpy.ops.mesh.primitive_cube_add(size=1, location=p)
    o = assign(bpy.context.object, mat, name)
    o.scale = s
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if bevel:
        mod = o.modifiers.new('small handmade bevel', 'BEVEL')
        mod.width = bevel
        mod.segments = 1
        bpy.context.view_layer.objects.active = o
        bpy.ops.object.modifier_apply(modifier=mod.name)
    return o


def beam(name, a, b, radius, mat='beam', vertices=6):
    a,b = Vector(a),Vector(b)
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius, depth=(b-a).length, location=(a+b)*.5)
    o = assign(bpy.context.object,mat,name)
    o.rotation_euler = (b-a).to_track_quat('Z','Y').to_euler()
    return o


def ico(name, p, s, mat, subdivision=1):
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=subdivision, radius=1, location=p)
    o = assign(bpy.context.object,mat,name)
    o.scale = s
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    return o


def mesh(name, vertices, faces, mat):
    d = bpy.data.meshes.new(name)
    d.from_pydata(vertices, [], faces)
    d.update()
    o = bpy.data.objects.new(name,d)
    bpy.context.collection.objects.link(o)
    assign(o,mat,name)
    return o


def cottage():
    # Blender Z is up; negative Y becomes the front (+Z) in Godot.
    cube('stone foundation',(0,0,.25),(5.6,4.4,.5),'stone',.09)
    cube('timber walls',(0,0,1.78),(5.25,4.05,2.65),'timber')
    # Triangular gables are real solids, never facade billboards.
    verts=[(-2.62,-2.03,3.1),(2.62,-2.03,3.1),(0,-2.03,5.15),(-2.62,2.03,3.1),(2.62,2.03,3.1),(0,2.03,5.15)]
    mesh('gable walls',verts,[(0,1,2),(5,4,3),(0,3,4,1),(1,4,5,2),(2,5,3,0)],'plaster')
    for side in (-1,1):
        # Separate overlapping roof courses give a readable edge silhouette.
        slope=math.atan2(2.2,3.1)
        for row in range(10):
            x=side*(.16+row*.315)
            z=5.3-abs(x)*2.2/3.1
            for col in range(9):
                y=-2.42+col*.60 + (0.12 if row%2 else 0)
                o=cube('cedar roof course',(x,y,z),(.45,.62,.12),'roof',.015)
                o.rotation_euler.y=side*slope
        for y in (-2.55,2.55):
            beam('gable roof trim',(0,y,5.38),(side*3.2,y,3.04),.12)
    beam('roof ridge',(0,-2.66,5.38),(0,2.69,5.38),.15)
    # Foundation corners and timber frame emphasize genuine volume.
    for x in (-2.62,2.62):
        for y in (-2.07,2.07): cube('corner post',(x,y,1.77),(.20,.18,2.75),'beam')
    for z in (.65,2.9,3.12): cube('front beam',(0,-2.09,z),(5.36,.16,.16),'beam')
    for x in (-2.1,0,2.1):
        beam('gable bracing',(x,-2.09,3.2),(0,-2.09,5.03),.08)
    cube('door surround',(-.68,-2.13,1.32),(1.13,.22,2.25),'beam')
    cube('door',(-.68,-2.27,1.34),(.86,.10,1.95),'timber')
    ico('door handle',(-.39,-2.36,1.33),(.065,.065,.065),'flower_gold')
    for x in (-1.92,1.38):
        cube('window frame',(x,-2.13,1.95),(1.02,.22,1.02),'beam')
        cube('window glass',(x,-2.27,1.95),(.83,.07,.79),'glass')
        cube('window vertical mullion',(x,-2.33,1.95),(.07,.06,.86),'plaster')
        cube('window horizontal mullion',(x,-2.33,1.95),(.88,.06,.07),'plaster')
        cube('window sill',(x,-2.35,1.48),(1.14,.42,.12),'timber',.025)
    for x in (-.88,.88):
        cube('attic frame',(x,-2.12,3.6),(.9,.13,.53),'beam')
        cube('attic glass',(x,-2.2,3.6),(.73,.05,.36),'glass')
    for y in (-.9,.95):
        cube('side window frame',(2.66,y,1.98),(.15,1.0,1.0),'beam')
        cube('side window glass',(2.76,y,1.98),(.05,.78,.78),'glass')
    for i in range(3): cube('door step',(-.68,-2.60-i*.34,.32-i*.10),(1.32,.42,.22),'stone',.045)
    cube('stone chimney',(1.61,.85,4.64),(.66,.71,1.6),'stone',.04)
    cube('chimney lip',(1.61,.85,5.5),(.83,.86,.18),'stone',.03)
    cube('chimney dark opening',(1.61,.85,5.60),(.49,.49,.03),'iron')
    # Small flower boxes built into the front facade.
    for x in (-1.91,1.38):
        cube('window flower box',(x,-2.54,1.28),(1.14,.45,.28),'timber',.02)
        for j in range(6):
            fx=x-.45+j*.18
            ico('flower leaves',(fx,-2.55,1.47),(.16,.15,.18),'leaf_1')
            ico('flower',(fx,-2.61,1.65),(.075,.075,.065),['flower_white','flower_pink','flower_gold'][j%3])


def tree():
    # Many compact sprays describe one crown instead of a few giant spheres.
    # Golden-angle placement breaks rings; inner sprays close the canopy while
    # outer sprays keep a leafy silhouette about 4 m wide and 5.3 m tall.
    beam('living trunk',(0,0,0),(.10,-.04,3.55),.20,'trunk',9)
    for i in range(9):
        a=i*2.399+RNG.uniform(-.22,.22)
        h=1.75+i*.19
        radius=RNG.uniform(.88,1.34)
        end=(math.cos(a)*radius,math.sin(a)*radius*.91,h+RNG.uniform(.48,.82))
        beam('branch',(.035,-.01,h),end,RNG.uniform(.060,.086),'trunk')
    for i in range(78):
        z=2.72+(i+.5)/78*2.10+RNG.uniform(-.14,.14)
        crown_radius=1.46*math.sqrt(max(.12,1-((z-3.82)/1.48)**2))
        a=i*2.399+RNG.uniform(-.36,.36)
        radial_fraction=RNG.uniform(.28,.52) if i%6==0 else RNG.uniform(.72,1.0)
        r=crown_radius*radial_fraction
        lean=.13*(z-3.6)
        p=(math.cos(a)*r+lean,math.sin(a)*r*.91,z)
        s=(RNG.uniform(.47,.64),RNG.uniform(.40,.57),RNG.uniform(.33,.48))
        o=ico('leaf spray',p,s,'leaf_'+str(RNG.randrange(5)),1 if i%5==0 else 2)
        for v in o.data.vertices:
            v.co*=RNG.uniform(.85,1.14)
            # Each spray is slightly pinched on one side rather than round.
            if v.co.x>0: v.co.y*=.80
        o.rotation_euler=(RNG.uniform(-.25,.25),RNG.uniform(-.25,.25),a+RNG.uniform(-.55,.55))


def fir():
    beam('fir trunk',(0,0,0),(.035,-.02,4.78),.16,'trunk')
    # These short inner cores merely close holes behind the branch sprays.
    # None reaches above the needles as an exposed, elongated pointed cone.
    counts=[12,12,11,10,9,8,6]
    for i,count in enumerate(counts):
        radius=1.47-i*.18
        layer_z=1.53+i*.47
        bpy.ops.mesh.primitive_cone_add(vertices=9,radius1=radius*.56,
            radius2=radius*.23,depth=.57,location=(.03*math.sin(i),0,layer_z+.09))
        assign(bpy.context.object,'leaf_'+str((i+2)%5),'fir hidden core')
        for j in range(count):
            a=j*2.399+i*1.27+RNG.uniform(-.30,.30)
            r=radius*RNG.uniform(.44,.84)
            p=(math.cos(a)*r,math.sin(a)*r,layer_z+RNG.uniform(-.21,.21))
            sx=.24+radius*RNG.uniform(.26,.36)
            sy=.15+radius*RNG.uniform(.14,.22)
            sz=RNG.uniform(.13,.23)+radius*.045
            o=ico('fir needle spray',p,(sx,sy,sz),'leaf_'+str(RNG.randrange(5)),2)
            for v in o.data.vertices:
                outward=max(0.0,v.co.x/sx)
                v.co.y*=1.0-.62*outward
                v.co.z-=.12*outward
                v.co*=RNG.uniform(.84,1.13)
            o.rotation_euler=(RNG.uniform(-.13,.13),RNG.uniform(-.08,.08),a)
            if j%4==0:
                tip=(math.cos(a)*radius*.72,math.sin(a)*radius*.72,p[2]-.10)
                beam('fir branch',(0,0,layer_z+.05),tip,.035,'trunk',5)
    # A handful of narrow, offset terminal twigs completes the taper naturally.
    for i in range(5):
        a=i*2.399
        p=(math.cos(a)*.13,math.sin(a)*.13,4.68+i*.055)
        o=ico('fir terminal twig',p,(.19,.14,.25),'leaf_'+str((i+1)%5),1)
        o.rotation_euler=(RNG.uniform(-.3,.3),RNG.uniform(-.3,.3),a)


def fence():
    for x in (-1,0,1):
        cube('fence post',(x,0,.63),(.16,.17,1.26),'timber',.035)
        bpy.ops.mesh.primitive_cone_add(vertices=4,radius1=.14,depth=.24,location=(x,0,1.35),rotation=(0,0,math.pi/4))
        assign(bpy.context.object,'timber','post cap')
    for z in (.43,.95): cube('fence rail',(0,.015,z),(2.15,.11,.12),'timber',.025)


def rock():
    o=ico('stone',(0,0,.27),(.63,.42,.36),'stone',2)
    for v in o.data.vertices: v.co*=RNG.uniform(.88,1.12)


def lamp():
    cube('lamp foot',(0,0,.13),(.5,.5,.26),'stone',.06)
    beam('lamp post',(0,0,.15),(0,0,2.8),.085,'iron',8)
    cube('lamp lower cap',(0,0,2.66),(.48,.48,.09),'iron')
    cube('lamp glass',(0,0,2.96),(.34,.34,.51),'window_glow')
    for x in (-.20,.20):
        for y in (-.20,.20): beam('lamp bar',(x,y,2.66),(x,y,3.22),.025,'iron')
    bpy.ops.mesh.primitive_cone_add(vertices=4,radius1=.40,radius2=.10,depth=.24,location=(0,0,3.32),rotation=(0,0,math.pi/4))
    assign(bpy.context.object,'iron','lamp roof')


def bench():
    for x in (-.8,.8):
        for y in (-.23,.23): cube('bench leg',(x,y,.33),(.12,.13,.66),'beam')
    for y in (-.27,-.09,.09,.27): cube('bench seat',(0,y,.68),(2.0,.16,.09),'timber',.02)
    for z in (.96,1.23): cube('bench back',(0,.34,z),(2.0,.10,.21),'timber',.02)
    for x in (-.8,.8): cube('bench upright',(x,.34,.86),(.1,.1,.96),'beam')


def sign():
    cube('sign post',(0,0,.72),(.14,.14,1.44),'timber')
    cube('blank trail sign',(0,-.03,1.4),(1.1,.13,.57),'timber',.025)
    # Original physical moon emblem, no extracted logos or lettering.
    for i in range(9):
        a=-1.4+i*.35
        ico('moon emblem',(.16*math.cos(a)-.06,-.12,1.4+.16*math.sin(a)),(.035,.025,.04),'flower_gold')


def grass():
    verts=[];faces=[]
    for i in range(9):
        a=RNG.random()*math.tau
        x=RNG.uniform(-.17,.17);y=RNG.uniform(-.17,.17);h=RNG.uniform(.22,.46)
        dx=math.cos(a)*.045;dy=math.sin(a)*.045
        n=len(verts)
        verts.extend([(x-dx,y-dy,0),(x+dx,y+dy,0),(x+.05,y+.03,h)])
        faces.extend([(n,n+1,n+2),(n+2,n+1,n)])
    mesh('grass blades',verts,faces,'leaf_1')


def export(name, factory):
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    RNG.seed(SEED+sum(name.encode()))
    factory()
    for o in list(bpy.context.scene.objects):
        if o.type!='MESH' or not o.data.materials or not o.data.materials[0].name.startswith('leaf_'):
            continue
        colors=o.data.color_attributes.new(name='Tint',type='BYTE_COLOR',domain='CORNER')
        base=o.data.materials[0].diffuse_color
        for face in o.data.polygons:
            variation=RNG.uniform(.94,1.06)
            face.use_smooth=True
            for index in face.loop_indices:
                colors.data[index].color=tuple(min(1,c*variation) for c in base[:3])+(1,)
        m=o.data.materials[0]
        if not m.node_tree.nodes.get('Tint'):
            tint=m.node_tree.nodes.new('ShaderNodeVertexColor');tint.name='Tint';tint.layer_name='Tint'
            m.node_tree.links.new(tint.outputs['Color'],m.node_tree.nodes.get('Principled BSDF').inputs['Base Color'])
    # One draw surface per material instead of hundreds of tiny plank objects.
    for mat_name in MATS:
        group=[o for o in bpy.context.scene.objects if o.type=='MESH' and o.data.materials and o.data.materials[0].name==mat_name]
        if not group: continue
        bpy.ops.object.select_all(action='DESELECT')
        for o in group:o.select_set(True)
        bpy.context.view_layer.objects.active=group[0]
        if len(group)>1:bpy.ops.object.join()
        bpy.context.object.name=name+'_'+mat_name
    bpy.ops.object.select_all(action='SELECT')
    # Apply transforms to keep predictable pivot and engine-space wind weights.
    for o in list(bpy.context.selected_objects):
        bpy.context.view_layer.objects.active=o
        bpy.ops.object.transform_apply(location=False,rotation=True,scale=True)
    blend=SOURCE/(name+'.blend')
    bpy.ops.wm.save_as_mainfile(filepath=str(blend),check_existing=False)
    glb=OUT/(name+'.glb')
    bpy.ops.export_scene.gltf(filepath=str(glb),export_format='GLB',use_selection=True,export_yup=True,export_apply=True)
    return {'id':name,'source':str(blend.relative_to(ROOT)),'output':str(glb.relative_to(ROOT)),
            'sha256':hashlib.sha256(glb.read_bytes()).hexdigest(),'seed':SEED+sum(name.encode()),
            'mesh_objects':sum(1 for o in bpy.context.scene.objects if o.type=='MESH')}


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    SOURCE.mkdir(parents=True,exist_ok=True)
    setup_materials()
    records=[]
    for name,fn in [('cottage',cottage),('broadleaf',tree),('fir',fir),('fence',fence),('rock',rock),('lamp',lamp),('bench',bench),('sign',sign),('grass',grass)]:
        records.append(export(name,fn))
    manifest={'schema':1,'generator':'tools/forest_hamlet/build_assets.py','generator_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'seed':SEED,'blender_version':bpy.app.version_string,
              'textures':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(TEXTURES.glob('*.png'))},
              'coordinate_system':'Blender Z up; glTF exporter performs Y-up conversion once',
              'copyright':'Original procedural geometry; reference video supplies visual direction only','assets':records}
    (SOURCE/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print('FOREST_MODELS_READY '+str(len(records)))


if __name__=='__main__':
    main()
