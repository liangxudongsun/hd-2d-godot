#!/usr/bin/env python3
"""Export a versioned structural cottage with every window plant removed.

Run in the existing Blender binary. The original nine-model source kit remains
unchanged. The wooden boxes and metal door handle remain real structural props.
"""
from pathlib import Path
import hashlib
import importlib.util
import json

import bpy

ROOT=Path(__file__).resolve().parents[2]
SOURCE=ROOT/'art/inputs/forest-hamlet/blender-vegetation-r1'
BASE=ROOT/'tools/forest_hamlet/build_assets.py'

def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def main():
    spec=importlib.util.spec_from_file_location('forest_original_builder',BASE)
    builder=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    builder.SOURCE=SOURCE
    SOURCE.mkdir(parents=True,exist_ok=True)
    builder.OUT.mkdir(parents=True,exist_ok=True)
    builder.setup_materials()
    removed=[]
    kept={}
    def structural_cottage():
        builder.cottage()
        for obj in list(bpy.context.scene.objects):
            if obj.name=='flower' or obj.name.startswith('flower.') or obj.name.startswith('flower leaves'):
                removed.append(obj.name)
                bpy.data.objects.remove(obj,do_unlink=True)
        assert len(removed)==24,removed
        kept['door_handle']=sum(o.name.startswith('door handle') for o in bpy.context.scene.objects)
        kept['window_boxes']=sum(o.name.startswith('window flower box') for o in bpy.context.scene.objects)
        assert kept=={'door_handle':1,'window_boxes':2},kept
        assert not any(m.name.startswith('leaf_') or m.name in ('flower_white','flower_pink','flower_blue')
            for o in bpy.context.scene.objects if o.type=='MESH' for m in o.data.materials)
    item=builder.export('cottage_without_plants',structural_cottage)
    record={'schema':1,'generator':'tools/forest_hamlet/build_cottage_without_plants.py',
        'generator_sha256':digest(__file__),'base_generator':'tools/forest_hamlet/build_assets.py',
        'base_generator_sha256':digest(BASE),'blender_version':bpy.app.version_string,
        'removed_plant_objects':removed,'removed_plant_object_count':len(removed),
        'preserved_structural_objects':kept,'runtime_plant_geometry_count':0,
        'replacement':'Two separately rooted color/normal Sprite3D window flower strips per cottage',
        'assets':[item],'source_sha256':digest(ROOT/item['source']),
        'textures':{p.name:digest(p) for p in sorted(builder.TEXTURES.glob('*.png'))}}
    (SOURCE/'manifest.json').write_text(json.dumps(record,indent=2)+'\n')
    print('FOREST_PLANT_FREE_COTTAGE '+json.dumps({'removed':len(removed),'preserved':kept,'output':item['output']}))

if __name__=='__main__':main()
