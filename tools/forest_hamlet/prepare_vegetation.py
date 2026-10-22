#!/usr/bin/env python3
"""Prepare ImageGen RGBA sprites and independently authored geometric normals.

The AW world.compile workflow owns final palette mapping. This explicit input
stage only crops the retained atlases, uniformly samples pixels, and aligns
paired colour/normal canvases. Diffuse luminance is never a height source.
"""
from pathlib import Path
import hashlib
import json

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'art/inputs/forest-hamlet/vegetation-r2'
PREPARED = BASE / 'prepared'
SEED = 20261022

# Crop coordinates were annotated against the complete retained source PNGs.
# Padding and uniform nearest sampling retain the original silhouette ratio.
SPECS = [
    ('broadleaf_a','tree-atlas',0,[512,544],5.3,1.0),
    ('broadleaf_b','tree-atlas',1,[384,560],5.2,1.0),
    ('fir','tree-atlas',2,[352,640],5.4,.85),
    ('grass','understory-atlas',0,[112,112],.45,1.0),
    ('fern','understory-atlas',1,[160,128],.56,.75),
    ('reeds','understory-atlas',2,[128,160],1.05,1.0),
    ('flowers_white','understory-atlas',3,[128,144],.52,.65),
    ('flowers_pink','understory-atlas',4,[128,144],.52,.65),
    ('window_flowers','understory-atlas',5,[224,96],.34,.45),
    ('lily_pad','understory-atlas',6,[160,64],.18,.18),
]

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def rel(path):
    return Path(path).relative_to(ROOT).as_posix()

def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n')

def unit(values):
    return values / np.maximum(np.linalg.norm(values,axis=-1,keepdims=True),1e-8)

def isolate_sheet(sheet):
    """Separate overlapping rectangular bounds without clipping any plant.

    The actual alpha components are disjoint even when their bounding boxes
    overlap. Keep complete large components, assigning detached tiny leaves to
    the nearest main silhouette. This is explicit atlas preparation, not art
    synthesis or a colour edit. Eight-connectivity and Euclidean distance are
    the same in the two installed scientific-library backends.
    """
    original=np.asarray(Image.open(BASE/'source'/f'{sheet}.png').convert('RGBA'))
    opaque=(original[...,3]>=128).astype(np.uint8)
    try:
        import cv2
        count,labels,stats,_=cv2.connectedComponentsWithStats(opaque,8)
        boxes={i:tuple(map(int,stats[i,:4])) for i in range(1,count)}
        sizes={i:int(stats[i,4]) for i in range(1,count)}
        def distance(mask):
            return cv2.distanceTransform(mask.astype(np.uint8),cv2.DIST_L2,cv2.DIST_MASK_PRECISE)
    except ImportError:
        from scipy import ndimage
        labels,count=ndimage.label(opaque,np.ones((3,3),int))
        boxes={};sizes={}
        for i,obj in enumerate(ndimage.find_objects(labels),1):
            if obj is None:continue
            boxes[i]=(obj[1].start,obj[0].start,obj[1].stop-obj[1].start,obj[0].stop-obj[0].start)
            sizes[i]=int((labels[obj]==i).sum())
        distance=ndimage.distance_transform_edt
    expected=3 if sheet=='tree-atlas' else 7
    large=sorted(sizes,key=lambda key:-sizes[key])[:expected]
    def slot_order(key):
        x,y,w,h=boxes[key]
        row=0 if sheet=='tree-atlas' or y<original.shape[0]*.56 else 1
        return row,x+w*.5
    large.sort(key=slot_order)
    assert all(sizes[k]>10000 for k in large),(sheet,large)
    distances=[distance(labels!=key) for key in large]
    assignments={key:index for index,key in enumerate(large)}
    for key,box in boxes.items():
        if key in assignments:continue
        x,y,w,h=box
        cx,cy=min(original.shape[1]-1,x+w//2),min(original.shape[0]-1,y+h//2)
        assignments[key]=int(np.argmin([round(float(d[cy,cx]),3) for d in distances]))
    owner=np.full(int(labels.max())+1,-1,np.int16)
    for key,index in assignments.items():owner[key]=index
    pixel_owner=owner[labels]
    result=[]
    for index,key in enumerate(large):
        pixels=original.copy()
        pixels[(pixel_owner!=index)|(opaque==0)]=0
        result.append(Image.fromarray(pixels))
    return result,{'sheet':sheet,'method':'8-connected alpha >=128; detached components assigned by exact nearest main silhouette',
        'main_components':[{'slot':i,'bounds':list(boxes[k]),'pixels':sizes[k]} for i,k in enumerate(large)],
        'alpha_pixels_retained':int((pixel_owner>=0).sum()),'alpha_pixels_original':int(opaque.sum())}

def normal_map(color, rig):
    """Analytic canopy lobes, trunks, frond tubes and flower/leaf disks.

    Rig coordinates use the visible sprite bounds, not a guessed model mesh.
    RGB is used solely to classify green foliage versus warm woody material.
    Each vector is independently defined by a visible form annotation.
    """
    pixels = np.asarray(color)
    alpha = pixels[...,3]
    visible = alpha >= 128
    ys,xs = np.nonzero(visible)
    x0,y0,x1,y1 = int(xs.min()),int(ys.min()),int(xs.max()+1),int(ys.max()+1)
    yy,xx = np.mgrid[0:alpha.shape[0],0:alpha.shape[1]].astype(np.float32)
    u=(xx-x0)/max(1,x1-x0-1)
    v=(yy-y0)/max(1,y1-y0-1)
    normal = unit(np.dstack(((u-.5)*.30,(.52-v)*.25,np.ones_like(u))))
    rgb=pixels[...,:3].astype(np.float32)
    saturation=(rgb.max(-1)-rgb.min(-1))/np.maximum(rgb.max(-1),1)
    green=(rgb[...,1]>rgb[...,0]*1.04)|(rgb[...,2]>rgb[...,0]*1.04)|((rgb[...,0]>rgb[...,1]*1.10)&(saturation>.57))
    # Broad stem and branch tubes are painted first; leaf lobes cover only green
    # areas on trees, so woody branches cannot acquire a canopy normal.
    for tube in rig.get('tubes',[]):
        points=tube['points'];radius=tube['radius'];slope=tube.get('slope',.68)
        distance=np.full(u.shape,np.inf,dtype=np.float32)
        radial=np.zeros((*u.shape,2),np.float32)
        grid=np.dstack((u,v))
        for pa,pb in zip(points,points[1:]):
            a=np.asarray(pa,np.float32);b=np.asarray(pb,np.float32);axis=b-a
            t=np.clip(((grid-a)*axis).sum(-1)/max(float((axis*axis).sum()),1e-8),0,1)
            delta=grid-(a+t[...,None]*axis)
            d2=(delta*delta).sum(-1)
            choose=d2<distance
            distance[choose]=d2[choose]
            radial[choose]=delta[choose]/radius
        nx=radial[...,0]*slope;ny=-radial[...,1]*slope
        nz=np.sqrt(np.maximum(.22,1-nx*nx-ny*ny))
        mask=distance<=(radius*1.8)**2
        if tube.get('wood_only'):mask &= ~green
        normal[mask]=unit(np.dstack((nx,ny,nz)))[mask]
    for shape in rig.get('lobes',[]):
        cx,cy,rx,ry=shape['ellipse'];slope=shape.get('slope',.63)
        dx=(u-cx)/rx;dy=(v-cy)/ry
        inside=dx*dx+dy*dy<=shape.get('coverage',1.25)**2
        if shape.get('foliage_only'):inside &= green
        nx=dx*slope+shape.get('yaw',0)
        ny=-dy*slope+shape.get('tilt',0)
        nz=np.sqrt(np.maximum(.20,1-nx*nx-ny*ny))
        mapped=unit(np.dstack((nx,ny,nz)))
        feather=max(0.0,min(.95,float(shape.get('feather',0.0))))
        if feather:
            radial=np.sqrt(dx*dx+dy*dy)/shape.get('coverage',1.25)
            weight=np.clip((1.0-radial)/feather,0.0,1.0)
            weight=weight*weight*(3.0-2.0*weight)
            mapped=unit(normal*(1.0-weight[...,None])+mapped*weight[...,None])
        normal[inside]=mapped[inside]
    normal=unit(normal)
    output=np.empty((*alpha.shape,4),np.uint8)
    output[...,:3]=np.rint(np.clip(normal*.5+.5,0,1)*255).astype(np.uint8)
    output[...,3]=alpha
    output[~visible,:3]=(128,128,255)
    decoded=output[visible,:3].astype(np.float32)/255*2-1
    error=float(np.max(np.abs(np.linalg.norm(decoded,axis=-1)-1)))
    assert error<.012,(rig['id'],error)
    return Image.fromarray(output),[x0,y0,x1-x0,y1-y0],error

def main():
    PREPARED.mkdir(parents=True,exist_ok=True)
    rig_record=json.loads((BASE/'normal-rig.json').read_text())
    rigs={item['id']:item for item in rig_record['assets']}
    assets=[]; samples=[]; isolated={}; isolation_records=[]
    for sheet in ['tree-atlas','understory-atlas']:
        isolated[sheet],record=isolate_sheet(sheet)
        isolation_records.append(record)
    for name,sheet,index,size,height,wind in SPECS:
        raw=BASE/'source'/f'{sheet}.png'
        original=Image.open(raw).convert('RGBA')
        box=[0,0,original.width,original.height]
        crop=isolated[sheet][index]
        a=np.asarray(crop)[...,3]
        yy,xx=np.nonzero(a>=128)
        bounds=(int(xx.min()),int(yy.min()),int(xx.max()+1),int(yy.max()+1))
        crop=crop.crop(bounds)
        padding=8 if name in ('broadleaf_a','broadleaf_b','fir') else 4
        scale=min((size[0]-2*padding)/crop.width,(size[1]-2*padding)/crop.height)
        scaled=[max(1,round(crop.width*scale)),max(1,round(crop.height*scale))]
        sampled=crop.resize(scaled,Image.Resampling.NEAREST)
        pixels=np.asarray(sampled).copy()
        pixels[...,3]=np.where(pixels[...,3]>=128,255,0).astype(np.uint8)
        pixels[pixels[...,3]==0,:3]=0
        sampled=Image.fromarray(pixels)
        canvas=Image.new('RGBA',size,(0,0,0,0))
        location=((size[0]-scaled[0])//2,size[1]-padding-scaled[1])
        canvas.paste(sampled,location)
        normal,visible_rect,error=normal_map(canvas,rigs[name])
        color_path=PREPARED/f'{name}.png'
        normal_path=PREPARED/f'{name}_normal.png'
        canvas.save(color_path)
        normal.save(normal_path)
        # Bottom-centre of actual alpha is the fixed root, not texture centre.
        pivot=[round(visible_rect[0]+visible_rect[2]/2),visible_rect[1]+visible_rect[3]]
        arr=np.asarray(canvas)
        visible_colors=arr[arr[...,3]>=128,:3]
        # Equal per-asset contribution keeps tiny flowers represented alongside
        # the large tree sheets; no normal vector enters the palette.
        indices=np.linspace(0,len(visible_colors)-1,4096).astype(int)
        samples.append(visible_colors[indices])
        assets.append({'name':name,'color':rel(color_path),'normal':rel(normal_path),
            'size':size,'pivot':pivot,'visible_rect':visible_rect,'height_m':height,
            'wind_weight':wind,'source':rel(raw),'source_crop':box,'isolated_sprite_index':index,
            'source_alpha_bounds_in_crop':list(bounds),'sampled_size':scaled,
            'sampling':'uniform nearest; alpha threshold 128; original retained',
            'color_sha256':sha(color_path),'normal_sha256':sha(normal_path),
            'normal_max_length_error':error})
    write_json(BASE/'atlas-isolation.json',{'schema':1,'sheets':isolation_records})
    palette_input=np.concatenate(samples,axis=0).reshape(256,160,3)
    quantized=Image.fromarray(palette_input).quantize(colors=192,method=Image.Quantize.MEDIANCUT)
    values=np.asarray(quantized.convert('RGB')).reshape(-1,3)
    # Snap representatives to actual original prepared pixels.
    source_colors=np.unique(palette_input.reshape(-1,3),axis=0).astype(np.float32)
    palette=[]
    for value in np.unique(values,axis=0):
        nearest=source_colors[np.argmin(((source_colors-value)**2).sum(1))].astype(int)
        hexvalue='#'+''.join(f'{v:02x}' for v in nearest)
        if hexvalue not in palette:palette.append(hexvalue)
    palette_path=BASE/'palette.json'
    write_json(palette_path,{'schema_version':1,'colors':palette,
        'source':'Equal-area visible pixel samples from ten retained ImageGen-derived sprites',
        'rule':'192 median-cut representatives snapped to original RGB; AW maps colours'})
    source_files=[BASE/'source/tree-atlas.png',BASE/'source/understory-atlas.png',
        BASE/'source/trees-prompt.txt',BASE/'source/understory-prompt.txt',
        BASE/'source/provenance.json',BASE/'source/user-vegetation-reference.png',BASE/'atlas-isolation.json',BASE/'normal-rig.json',Path(__file__)]
    write_json(BASE/'source/provenance.json',{'schema':1,'generator':'image_gen.imagegen',
        'date':'2026-10-22','seed':None,'model_version':None,'art_revision':'r2 following the supplied autumn HD2D screenshot; prior green preview rejected by user',
        'generation_calls':2,'transparent_background':True,
        'images':[{'path':rel(BASE/'source'/f'{name}.png'),
                   'sha256':sha(BASE/'source'/f'{name}.png'),
                   'size':list(Image.open(BASE/'source'/f'{name}.png').size)}
                  for name in ['tree-atlas','understory-atlas']],
        'use':'Original game vegetation colour sprites; no runtime geometry baked from the old models',
        'normal_source':'Independent editable form annotations, analytic surface vectors, not diffuse brightness'})
    write_json(BASE/'preparation.json',{'schema_version':1,'seed':SEED,
        'generator':rel(Path(__file__)),'generator_sha256':sha(__file__),
        'assets':assets,'palette':{'path':rel(palette_path)},
        'normal_convention':'OpenGL tangent: X right, Y up, Z towards viewer',
        'normal_recipe':rel(BASE/'normal-rig.json'),'palette_size':192,
        'source_files':[rel(p) for p in source_files],
        'source_hashes':{rel(p):sha(p) for p in source_files}})
    print(json.dumps({'prepared':len(assets),'palette_colors':len(palette),
        'output':rel(BASE/'preparation.json')}))

if __name__=='__main__':
    main()
