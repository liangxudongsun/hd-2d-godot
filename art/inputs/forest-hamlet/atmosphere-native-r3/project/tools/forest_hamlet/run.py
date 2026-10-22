#!/usr/bin/env python3
"""Project-local forest scene commands; never installs tools or starts services."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import shutil
import struct
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from project import engine, desktop_environment


def blender():
    value=os.environ.get('BLENDER','blender')
    found=shutil.which(value)
    if not found and value=='blender':
        for candidate in ['/snap/bin/blender','/var/lib/snapd/snap/bin/blender']:
            if Path(candidate).is_file():
                found=candidate
                break
    if not found:raise RuntimeError('Blender not found. Set BLENDER to an installed executable.')
    return found


def validate_assets():
    from PIL import Image
    checks=[]
    def check(label, value):
        checks.append({'name':label,'passed':bool(value)})
        print(('PASS ' if value else 'FAIL ')+label)
    source=ROOT/'art/inputs/forest-hamlet/material-atlas.png'
    record=json.loads((source.parent/'imagegen-provenance.json').read_text())
    check('source atlas identity',hashlib.sha256(source.read_bytes()).hexdigest()==record['sha256'])
    check('imagegen seed/version explicitly unknown',record['seed'] is None and record['model_version'] is None)
    production=json.loads((ROOT/'assets/forest-hamlet/material-production.json').read_text())
    expected_size=tuple(production['size'])
    for name in ['grass','earth','wood','stone']:
        p=ROOT/'assets/forest-hamlet/textures'/f'{name}.png'
        with Image.open(p) as image:
            check(name+' texture dimensions',image.size==expected_size and expected_size==(64,64))
            check(name+' restrained source palette',len(image.convert('RGB').getcolors(maxcolors=65) or []) in range(1,65))
            check(name+' opaque albedo',image.mode in ['RGB','RGBA'] and (image.mode=='RGB' or image.getchannel('A').getextrema()==(255,255)))
    summary=ROOT/production['summary']
    aw=json.loads(summary.read_text())
    check('official AW world.compile completed',aw['execution_status']=='completed' and aw['workflow']=='world.compile')
    for item in aw['outputs']:
        check(item['name']+' exact AW output bytes',hashlib.sha256((ROOT/item['runtime']).read_bytes()).hexdigest()==item['sha256'])
    baseline=json.loads((source.parent/'character-reuse.json').read_text())
    altered=[p for p,h in baseline['files'].items() if not (ROOT/p).is_file() or hashlib.sha256((ROOT/p).read_bytes()).hexdigest()!=h]
    check('345 original character files immutable',len(baseline['files'])==345 and not altered)
    models=json.loads((source.parent/'blender/manifest.json').read_text())
    check('nine editable original model sources',len(models['assets'])==9)
    for asset in models['assets']:
        src=ROOT/asset['source'];out=ROOT/asset['output']
        check(asset['id']+' source exists',src.is_file() and src.stat().st_size>1000)
        data=out.read_bytes()
        check(asset['id']+' glTF binary valid',data[:4]==b'glTF' and struct.unpack_from('<I',data,4)[0]==2 and struct.unpack_from('<I',data,8)[0]==len(data))
        check(asset['id']+' output identity',hashlib.sha256(data).hexdigest()==asset['sha256'])
    report={'schema':1,'checks':checks,'passed':all(c['passed'] for c in checks),'character_files':len(baseline['files']),'changed_originals':altered}
    output=ROOT/'build/forest-hamlet/assets-report.json'
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(report,indent=2)+'\n')
    if not report['passed']:raise RuntimeError('Forest asset validation failed')


def runtime_fingerprint(destination):
    paths={ROOT/'project.godot',ROOT/'scenes/forest_hamlet.tscn',ROOT/'scenes/forest_hamlet_close.tscn',ROOT/'scripts/pixel_actor.gd',ROOT/'scripts/ancient_canal/actor.gd'}
    for relative in ['scripts/forest_hamlet','shaders/forest_hamlet','assets/forest-hamlet','shaders/ancient_canal']:
        paths.update(p for p in (ROOT/relative).rglob('*') if p.is_file() and p.suffix not in ['.import','.uid'])
    reused=json.loads((ROOT/'art/inputs/forest-hamlet/character-reuse.json').read_text())
    paths.update(ROOT/p for p in reused['files'])
    files={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths)}
    value=hashlib.sha256(json.dumps(files,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    (destination/'runtime-fingerprint.json').write_text(json.dumps({'schema':1,'sha256':value,'files':files},indent=2)+'\n')
    return value


def execute(command, label, graphical=False, timeout=240):
    env=desktop_environment() if graphical else os.environ.copy()
    output=ROOT/'build/forest-hamlet/logs'
    output.mkdir(parents=True,exist_ok=True)
    started=time.time()
    result=subprocess.run(command,cwd=ROOT,env=env,capture_output=True,text=True,timeout=timeout)
    text=result.stdout+result.stderr
    (output/(label+'.log')).write_text(text)
    # Godot can report parse/runtime errors with process exit status zero.
    failed=result.returncode!=0 or any(token in text for token in ['SCRIPT ERROR:','Parse Error:','ERROR:','FOREST_FAIL'])
    report={'command_label':label,'returncode':result.returncode,'passed':not failed,'elapsed_s':round(time.time()-started,3),'log':str((output/(label+'.log')).relative_to(ROOT))}
    (output/(label+'.json')).write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report))
    print(text[-6000:])
    if failed:raise RuntimeError(label+' failed; inspect the saved log')



def validate_billboard_capture(destination):
    """Measure the rendered shader silhouette against the unchanged source PNG."""
    import math
    from PIL import Image
    source=ROOT/'assets/characters/crescent-traveler/v1/down/frames/00000.png'
    with Image.open(source) as original:
        source_box=original.getchannel('A').point(lambda value: 255 if value >= 128 else 0).getbbox()
    if source_box is None:
        raise RuntimeError('Original billboard reference has no opaque pixels')
    source_width=source_box[2]-source_box[0]
    source_height=source_box[3]-source_box[1]
    focal_pixels=1080.0/(2.0*8.0*math.tan(math.radians(39.0)*.5))
    measurements=[]
    failures=[]
    baseline=None
    for name,scale in [('billboard-pitch15',1.0),('billboard-pitch35',1.0),('billboard-pitch60',1.0),('billboard-yaw55',1.0),('billboard-scale125',1.25)]:
        with Image.open(destination/(name+'.png')) as opened:
            rgb=opened.convert('RGB')
            # Debug emission exceeds the black clear background in every channel.
            mask=rgb.convert('L').point(lambda value: 255 if value > 24 else 0)
            box=mask.getbbox()
        if box is None:
            failures.append(name+': empty GPU silhouette')
            continue
        width,height=box[2]-box[0],box[3]-box[1]
        expected=[source_width*.009*focal_pixels*scale,source_height*.009*focal_pixels*scale]
        size_ok=abs(width-expected[0])<=3.0 and abs(height-expected[1])<=3.0
        if not size_ok:
            failures.append(name+': rendered size differs from source aspect/scale')
        if baseline is None:
            baseline=(width,height)
        stable=scale!=1.0 or (abs(width-baseline[0])<=2 and abs(height-baseline[1])<=2)
        if not stable:
            failures.append(name+': silhouette changes with camera angle')
        measurements.append({'file':name+'.png','scale':scale,'bounds':list(box),'size':[width,height],'expected_size':expected,'source_aspect_preserved':size_ok,'camera_angle_invariant':stable})
    report={'schema':1,'passed':not failures and len(measurements)==5,'scope':'Actual GPU pixel read-back; same unchanged front frame, constant distance and FOV, black background, normal debug emission','source':source.relative_to(ROOT).as_posix(),'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'source_bounds':list(source_box),'distance':8.0,'fov':39.0,'checks':measurements,'failures':failures}
    (destination/'billboard-gpu-report.json').write_text(json.dumps(report,indent=2)+'\n')
    print('FOREST_BILLBOARD_GPU '+json.dumps({'passed':report['passed'],'views':len(measurements),'failures':failures}))
    if not report['passed']:
        raise RuntimeError('GPU billboard silhouette validation failed')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['run','run-close','import','models','assets','test','test-close','capture','capture-camera','test-vegetation','capture-vegetation'])
    parser.add_argument('--output',default='build/forest-hamlet/capture')
    parser.add_argument('--no-route',action='store_true',help='Capture stills only during visual iteration')
    args=parser.parse_args()
    base=[engine(),'--path',str(ROOT)]
    if args.command in ['run','run-close']:
        scene_path='res://scenes/forest_hamlet_close.tscn' if args.command=='run-close' else 'res://scenes/forest_hamlet.tscn'
        subprocess.run(base+[scene_path],cwd=ROOT,env=desktop_environment(),check=True)
    elif args.command=='import':
        execute(base+['--headless','--editor','--quit'],'import',timeout=300)
    elif args.command=='models':
        execute([blender(),'--background','--factory-startup','--disable-autoexec','--python','tools/forest_hamlet/build_assets.py'],'models',timeout=300)
    elif args.command=='assets':validate_assets()
    elif args.command=='test':
        validate_assets()
        execute(base+['--headless','--fixed-fps','60','--script','res://tests/forest_hamlet/runtime.gd'],'runtime',timeout=180)
    elif args.command=='test-close':
        validate_assets()
        execute(base+['--headless','--fixed-fps','60','--script','res://tests/forest_hamlet/close_runtime.gd','--','--forest-output=res://'+args.output],'close-runtime',timeout=180)
    elif args.command=='test-vegetation':
        from vegetation_checks import validate_vegetation_assets
        destination=(ROOT/args.output).resolve()
        destination.relative_to(ROOT)
        destination.mkdir(parents=True,exist_ok=True)
        validate_assets()
        validate_vegetation_assets(destination)
        for script,label in [('vegetation_runtime.gd','vegetation-runtime'),('close_runtime.gd','close-runtime')]:
            execute(base+['--headless','--fixed-fps','60','--script','res://tests/forest_hamlet/'+script,'--','--forest-output=res://'+str(destination.relative_to(ROOT))],label,timeout=180)
    elif args.command in ['capture','capture-camera','capture-vegetation']:
        destination=(ROOT/args.output).resolve()
        destination.relative_to(ROOT)
        destination.mkdir(parents=True,exist_ok=True)
        # A real GPU viewport, positioned away from the user's desktop, performs
        # rendering. The capture script explicitly waits for finished frames.
        capture_args=['--forest-output=res://'+str(destination.relative_to(ROOT)),'--forest-fingerprint='+runtime_fingerprint(destination)]
        if args.no_route:capture_args.append('--forest-no-route')
        capture_script='res://tools/forest_hamlet/'+{'capture':'capture.gd','capture-camera':'capture_camera.gd','capture-vegetation':'capture_vegetation.gd'}[args.command]
        execute(base+['--display-driver','x11','--position','10000,10000','--audio-driver','Dummy','--disable-render-loop','--script',capture_script,'--']+capture_args,args.command,graphical=True,timeout=300)
        if args.command=='capture-vegetation':
            from vegetation_checks import validate_vegetation_capture
            validate_vegetation_capture(destination)
        else:
            validate_billboard_capture(destination)


if __name__=='__main__':
    try:main()
    except (OSError,ValueError,RuntimeError,subprocess.SubprocessError) as exc:
        print(str(exc),file=sys.stderr)
        raise SystemExit(1)
