#!/usr/bin/env python3
"""Preserve every drawn source pixel on native AW prop-compatible canvases.

The first native validation required width multiples of 64 and height multiples
of 32. This successor adds transparent margins only, and authors refined normals
from the reviewed r2 form rig. It never downsamples or stretches the colour art.
"""
from pathlib import Path
import hashlib
import json
import math
import shutil

from PIL import Image
from prepare_vegetation import normal_map

ROOT=Path(__file__).resolve().parents[2]
OLD=ROOT/'art/inputs/forest-hamlet/vegetation-r2'
NEW=ROOT/'art/inputs/forest-hamlet/vegetation-r2-canvas'

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def rel(path):return Path(path).relative_to(ROOT).as_posix()
def dump(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')

def main():
    previous=json.loads((OLD/'preparation.json').read_text())
    rigs={x['id']:x for x in json.loads((NEW/'normal-rig.json').read_text())['assets']}
    assets=[]
    for item in previous['assets']:
        source=ROOT/item['color']
        original=Image.open(source).convert('RGBA')
        size=[max(64,math.ceil(original.width/64)*64),max(64,math.ceil(original.height/32)*32)]
        offset=[(size[0]-original.width)//2,size[1]-original.height]
        color=Image.new('RGBA',size,(0,0,0,0));color.paste(original,offset)
        # Exact source pixels survive, including transparent RGB bytes.
        restored=color.crop((offset[0],offset[1],offset[0]+original.width,offset[1]+original.height))
        assert restored.tobytes()==original.tobytes(),item['name']
        normal,visible,error=normal_map(color,rigs[item['name']])
        target=NEW/'prepared'/f"{item['name']}.png"
        normal_target=NEW/'prepared'/f"{item['name']}_normal.png"
        target.parent.mkdir(parents=True,exist_ok=True)
        color.save(target);normal.save(normal_target)
        record=dict(item)
        record.update(color=rel(target),normal=rel(normal_target),size=size,
            pivot=[item['pivot'][0]+offset[0],item['pivot'][1]+offset[1]],
            visible_rect=visible,native_canvas=item['size'],padding_offset=offset,
            native_color_source=item['color'],native_pixels_unchanged=True,
            color_sha256=sha(target),normal_sha256=sha(normal_target),normal_max_length_error=error)
        assets.append(record)
    palette=NEW/'palette.json';shutil.copyfile(ROOT/previous['palette']['path'],palette)
    sources=[path for path in previous['source_files'] if path!=previous['normal_recipe']]
    sources.extend([rel(OLD/'preparation.json'),rel(NEW/'normal-rig.json'),rel(Path(__file__))])
    dump(NEW/'preparation.json',{
        'schema_version':1,'seed':20261022,'art_revision':'r2 autumn reference; native pixel-preserving canvas padding',
        'predecessor_preparation':rel(OLD/'preparation.json'),
        'predecessor_native_run':'forest-hamlet-20261022-vegetation-r2 (validation rejected nonmultiple canvas; retained)',
        'generator':rel(Path(__file__)),'generator_sha256':sha(__file__),
        'assets':assets,'palette_size':192,'palette':{'path':rel(palette)},
        'normal_recipe':rel(NEW/'normal-rig.json'),
        'normal_convention':'OpenGL tangent: X right, Y up, Z towards viewer',
        'normal_workflow':'Hand-annotated r2 canopy boughs, fronds and flower heads; analytic surface vectors independent of diffuse luminance',
        'source_files':sources,'source_hashes':{p:sha(ROOT/p) for p in sources},
        'padding_policy':'Only transparent borders added to meet native AW prop 64x32 canvas multiples; every drawn color pixel retained exactly'})
    print(json.dumps({'assets':len(assets),'native_color_pixels_unchanged':True,'preparation':rel(NEW/'preparation.json')}))

if __name__=='__main__':main()
