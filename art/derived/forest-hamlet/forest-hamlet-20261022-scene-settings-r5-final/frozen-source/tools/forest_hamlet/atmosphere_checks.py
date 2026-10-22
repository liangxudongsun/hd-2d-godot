#!/usr/bin/env python3
"""Independent asset integrity and actual GPU pixel measurements for atmosphere."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

from PIL import Image, ImageChops, ImageStat

ROOT = Path(__file__).resolve().parents[2]
SCREENSHOTS = {
    'close-day-clouds-a.png', 'close-day-clouds-off.png', 'close-day-clouds-b.png',
    'close-day-glow-off.png', 'close-day-atmosphere-off.png', 'close-dusk-atmosphere.png',
    'close-route-left.png', 'close-route-right.png', 'snow-left-normals-on.png',
    'snow-left-normals-off.png', 'snow-right-normals-on.png', 'snow-right-normals-off.png',
    'close-day-global-weak.png', 'close-day-global-strong.png', 'close-day-global-off.png',
    'close-day-clouds-thin.png', 'close-day-clouds-thick.png', 'close-day-clouds-natural.png',
}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, report):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n')


def difference(a, b):
    delta = ImageChops.difference(a.convert('RGB'), b.convert('RGB'))
    channels = delta.split()
    largest = ImageChops.lighter(ImageChops.lighter(channels[0], channels[1]), channels[2])
    histogram = largest.histogram()
    count = sum(histogram[3:])
    return {'pixels': a.width*a.height, 'changed_pixels_over_2': count,
            'changed_fraction': count/max(a.width*a.height, 1),
            'mean_absolute_rgb_difference': sum(ImageStat.Stat(delta).mean)/3.0}


def finish(destination, name, report):
    save(destination / name, report)
    failures = [c['label'] for c in report['checks'] if not c['passed']]
    print('ATMOSPHERE_CHECKS ' + json.dumps({'report': name, 'passed': report['passed'],
                                           'checks': len(report['checks']), 'failures': failures}))
    if failures:
        raise RuntimeError('; '.join(failures))
    return report


def validate_assets(destination):
    manifest_path = ROOT / 'assets/forest-hamlet/backdrop/manifest.json'
    manifest = json.loads(manifest_path.read_text())
    checks = []

    def check(label, condition):
        checks.append({'label': label, 'passed': bool(condition)})

    source = ROOT / manifest['source']
    color_path = ROOT / manifest['color']
    normal_path = ROOT / manifest['normal']
    regions_path = ROOT / manifest['regions']
    check('approved color bytes are preserved in the runtime image', digest(source) == digest(color_path) == manifest['source_sha256'])
    for path in [color_path, normal_path, regions_path]:
        check(path.name + ': actual bytes match the runtime manifest', digest(path) == manifest['files'][path.name])
    check('normal rig source hash is current', digest(ROOT / manifest['rig']) == manifest['rig_sha256'])
    check('technical data generator source hash is current', digest(ROOT / manifest['generator']) == manifest['generator_sha256'])
    with Image.open(color_path) as c, Image.open(normal_path) as n, Image.open(regions_path) as r:
        check('all data textures align with the original color dimensions', c.size == n.size == r.size == tuple(manifest['dimensions']))
        normal = n.convert('RGB')
        regions = r.convert('RGB')
        check('the original wide panorama aspect is retained', 2.45 < c.width/c.height < 2.55)
    neutral = ((128, 128), (128, 128), (255, 255))
    check('open sky stays exactly flat in the normal data', normal.crop((0,0,normal.width,int(normal.height*.27))).getextrema() == neutral)
    check('bottom mist stays exactly flat in the normal data', normal.crop((0,int(normal.height*.80),normal.width,normal.height)).getextrema() == neutral)
    max_error = 0.0
    tilted = 0
    for red, green, blue in normal.getdata():
        x, y, z = red/127.5-1, green/127.5-1, blue/127.5-1
        max_error = max(max_error, abs(math.sqrt(x*x+y*y+z*z)-1))
        tilted += abs(x)>.06 or abs(y)>.06
    check('quantized tangent normals retain unit length', max_error < .008)
    check('nonflat mountain normals occupy a finite controlled region', .02 < tilted/(normal.width*normal.height) < .55)
    normal_range = normal.getextrema()
    check('mountain facet directions include opposing slopes', normal_range[0][0]<110 and normal_range[0][1]>145)
    rig = json.loads((ROOT / manifest['rig']).read_text())
    check('normal construction explicitly avoids RGB-as-height', rig.get('color_is_height') is False and bool(rig.get('massifs')))
    check('single source board is not mislabeled as independently layered art', manifest['geometry_count']==1 and manifest['independent_color_layers']==1 and manifest['parallax_kind']=='single_distant_board')
    report = {'schema':1, 'passed':all(c['passed'] for c in checks), 'checks':checks,
              'scope':'Source immutability, technical normal encoding and truthful single-board provenance; visual response is measured on the GPU separately',
              'manifest_sha256':digest(manifest_path), 'source_sha256':digest(source),
              'normal_max_unit_error':max_error, 'normal_tilted_fraction':tilted/(normal.width*normal.height),
              'dimensions':manifest['dimensions']}
    return finish(Path(destination), 'atmosphere-assets-report.json', report)


def box_from_normalized(rect, size):
    width, height = size
    return tuple(round(v*(width if i%2==0 else height)) for i, v in enumerate(rect))


def landmark_pixel_matching(left, right, left_record, right_record):
    """Confirm projected displacement with local image registration, not metadata alone."""
    left_points = {item['id']:item for item in left_record['backdrop'].get('landmarks',[])}
    right_points = {item['id']:item for item in right_record['backdrop'].get('landmarks',[])}
    records = []
    gray_left, gray_right = left.convert('L'), right.convert('L')
    radius = 16
    for key in sorted(left_points.keys() & right_points.keys()):
        a = left_points[key]['projected_pixels']
        b = right_points[key]['projected_pixels']
        ax, ay, bx, by = round(a[0]), round(a[1]), round(b[0]), round(b[1])
        if not (radius+13 <= ax < left.width-radius-13 and radius+5 <= ay < left.height-radius-5 and radius+13 <= bx < right.width-radius-13 and radius+5 <= by < right.height-radius-5):
            records.append({'id':key, 'usable':False, 'reason':'projected landmark too close to viewport boundary'})
            continue
        patch = gray_left.crop((ax-radius,ay-radius,ax+radius+1,ay+radius+1))
        texture_std = ImageStat.Stat(patch).stddev[0]
        best = (float('inf'), bx, by)
        for dy in range(-4,5):
            for dx in range(-12,13):
                x, y = bx+dx, by+dy
                candidate = gray_right.crop((x-radius,y-radius,x+radius+1,y+radius+1))
                error = ImageStat.Stat(ImageChops.difference(patch,candidate)).mean[0]
                if error < best[0]:
                    best = (error,x,y)
        unmoved = gray_right.crop((ax-radius,ay-radius,ax+radius+1,ay+radius+1))
        unmoved_error = ImageStat.Stat(ImageChops.difference(patch,unmoved)).mean[0]
        observed = [best[1]-ax,best[2]-ay]
        expected = [b[0]-a[0],b[1]-a[1]]
        useful = texture_std>2.0 and best[0]<12 and best[0]+.20<unmoved_error and abs(observed[0])>3 and abs(observed[0]-expected[0])<=13 and abs(observed[1]-expected[1])<=5
        records.append({'id':key,'usable':useful,'left_center_px':[ax,ay], 'predicted_right_center_px':[bx,by],
                        'matched_right_center_px':[best[1],best[2]],'expected_displacement_px':expected,
                        'measured_displacement_px':observed,'patch_std':texture_std,
                        'best_mean_absolute_luma_error':best[0],'unmoved_mean_absolute_luma_error':unmoved_error})
    return {'passed':any(r['usable'] for r in records),'landmarks':records,
            'method':'33x33 luminance patches; search ±12 horizontal/±4 vertical pixels around independently projected landmark; compare with zero-motion hypothesis'}


def validate_capture(destination):
    destination = Path(destination)
    report_path = destination / 'atmosphere-gpu-report.json'
    capture = json.loads(report_path.read_text())
    checks = []

    def check(label, condition):
        checks.append({'label':label, 'passed':bool(condition)})

    check('GPU capture contracts passed', capture.get('passed') is True)
    check('final evidence includes all eighteen gameplay views and the completed physical route', capture.get('complete_final_evidence') is True)
    check('actual hardware Forward+ is identified', capture.get('renderer')=='forward_plus' and bool(capture.get('adapter')))
    records = {item['file']:item for item in capture['screenshots']}
    check('capture contains the exact eighteen distinct comparison PNGs', len(capture['screenshots'])==len(SCREENSHOTS) and set(records)==SCREENSHOTS)
    images = {}
    for filename, record in records.items():
        path = destination / filename
        check(filename+': retained PNG hash matches GPU read-back', digest(path)==record['sha256'])
        with Image.open(path) as opened:
            images[filename] = opened.convert('RGB')
        check(filename+': image retains 1920x1080 GPU resolution', images[filename].size==(1920,1080))
    equal = lambda a,b: math.isclose(float(a),float(b),rel_tol=1e-6,abs_tol=1e-6)
    splits = [row['cloud_lighting']['light_split'] for row in records.values()]
    check('all real branch lights conserve the recorded authoritative solar energy',
          all(equal(s['base70']['energy'],s['source']['energy']*.70)
              and equal(s['cloud30']['energy'],s['source']['energy']*.30)
              and equal(s['total_direct_energy'],s['source']['energy'])
              and s['source']['sky_mode']==2 and s['base70']['sky_mode']==s['cloud30']['sky_mode']==1 for s in splits))
    check('only the 30 percent native branch receives cloud-layer shadows',
          all((s['base70']['shadow_caster_mask'] & s['cloud_layer_mask'])==0
              and (s['cloud30']['shadow_caster_mask'] & s['cloud_layer_mask'])==s['cloud_layer_mask']
              and (s['base70']['shadow_caster_mask'] & 1)==(s['cloud30']['shadow_caster_mask'] & 1)==1 for s in splits))
    gameplay = [row for row in records.values() if row['phase']!='isolated_actual_backdrop']
    check('ordinary entity shadow opacity stays full on both scene light branches',
          all(row['cloud_lighting']['light_split'][name]['shadow_enabled'] is True
              and equal(row['cloud_lighting']['light_split'][name]['shadow_opacity'],1)
              for row in gameplay for name in ('base70','cloud30')))
    partial_names = ['close-day-clouds-'+name+'.png' for name in ('thin','thick','natural')]
    check('three gameplay cloud previews use actual clear thin thick controls at identical global t0',
          all(equal(records[name]['cloud_lighting']['uniform_attenuation'],attenuation)
              and equal(records[name]['global_light']['clock_seconds'],0)
              and equal(records[name]['global_light']['sun_multiplier'],1)
              and equal(records[name]['global_light']['ambient_multiplier'],1)
              and equal(records[name]['cloud_lighting']['clock_seconds'],0)
              and records[name]['cloud_lighting']['enabled'] is True
              for name,attenuation in zip(partial_names,(.10,.30,-1.0))))
    check('controlled partial clouds retain camera actor source light and post settings',
          all(records[name]['state']['camera']==records[partial_names[0]]['state']['camera']
              and records[name]['state']['player']==records[partial_names[0]]['state']['player']
              and records[name]['main_light']==records[partial_names[0]]['main_light']
              and records[name]['environment']==records[partial_names[0]]['environment'] for name in partial_names))
    partial_appearance = {'measurement':'LDR appearance differences only; calibrated separate receiver determines direct transmission',
                          'thin_vs_thick':difference(images[partial_names[0]],images[partial_names[1]]),
                          'natural_vs_off':difference(images[partial_names[2]],images['close-day-clouds-off.png']),
                          'restored_natural_vs_initial':difference(images[partial_names[2]],images['close-day-clouds-a.png'])}
    check('thin and thick clouds visibly differ in real scene pixels',
          partial_appearance['thin_vs_thick']['changed_pixels_over_2']>=1000
          and partial_appearance['thin_vs_thick']['mean_absolute_rgb_difference']>.20)
    probe_dir = destination/'cloud-transmission'
    probe_capture_path = probe_dir/'cloud-transmission-capture.json'
    probe_pixel_path = probe_dir/'cloud-transmission-pixel-report.json'
    probe_capture = json.loads(probe_capture_path.read_text())
    probe_pixels = json.loads(probe_pixel_path.read_text())
    check('independent calibrated GPU transmission probe passed every contract',
          all(report.get('passed') is True and report.get('checks') and not report.get('failures')
              and all(item.get('passed') is True for item in report['checks']) for report in (probe_capture,probe_pixels)))
    check('calibrated receiver evidence belongs to this exact runtime and capture',
          probe_pixels.get('capture_sha256')==digest(probe_capture_path)
          and probe_capture.get('runtime_fingerprint')==probe_pixels.get('runtime_fingerprint')==capture.get('runtime_fingerprint'))
    from cloud_transmission_checks import NAMES as PROBE_NAMES
    probe_records={row['file']:row for row in probe_capture.get('screenshots',[])}
    check('all eight original calibrated receiver PNGs retain their capture hashes',
          len(probe_capture.get('screenshots',[]))==8 and set(probe_records)=={name+'.png' for name in PROBE_NAMES}
          and all(digest(probe_dir/name)==row['sha256'] and row['size']==[1024,768] for name,row in probe_records.items()))
    transmission_evidence = {'capture':'cloud-transmission/cloud-transmission-capture.json',
                             'capture_sha256':digest(probe_capture_path),
                             'pixel_report':'cloud-transmission/cloud-transmission-pixel-report.json',
                             'pixel_report_sha256':digest(probe_pixel_path),
                             'measurement_encoding':probe_pixels['measurement_encoding'],
                             'passed':probe_pixels['passed'],'checks':len(probe_pixels['checks']),
                             'rois':probe_pixels['rois'],'natural_transmission_range':probe_pixels['natural_transmission_range'],
                             'ordinary_shadow_ratio':probe_pixels['ordinary_shadow_ratio']}
    a = images['close-day-clouds-a.png']
    b = images['close-day-clouds-b.png']
    off = images['close-day-clouds-off.png']
    receiver_results = []
    for name, rect in capture['cloud_receiver_rois'].items():
        box = box_from_normalized(rect, a.size)
        a_crop, b_crop, off_crop = a.crop(box), b.crop(box), off.crop(box)
        at_a, at_b, moving = difference(a_crop,off_crop), difference(b_crop,off_crop), difference(a_crop,b_crop)
        strongest = max(at_a['mean_absolute_rgb_difference'],at_b['mean_absolute_rgb_difference'])
        check(name+': real rendered receiver changes under cloud occlusion', strongest>.20 and max(at_a['changed_pixels_over_2'],at_b['changed_pixels_over_2'])>=100)
        receiver_results.append({'receiver':name,'crop_px':list(box),'cloud_a_vs_off':at_a,'cloud_b_vs_off':at_b,'cloud_motion':moving})
    cloud_motion = difference(a,b)
    check('moving cloud mask changes the fixed-camera scene', cloud_motion['changed_pixels_over_2']>=500 and cloud_motion['mean_absolute_rgb_difference']>.10)
    light_records = [records[f]['main_light'] for f in ['close-day-clouds-a.png','close-day-clouds-b.png','close-day-clouds-off.png']]
    check('sun energy direction and color remain identical in the controlled cloud comparison', light_records[0]==light_records[1]==light_records[2])
    ambience = [records[f]['environment']['ambient_energy'] for f in ['close-day-clouds-a.png','close-day-clouds-b.png','close-day-clouds-off.png']]
    check('controlled cloud A/B keeps ambient fill constant while the global clock is held at t0', ambience[0]==ambience[1]==ambience[2])
    tile_differences = []
    for y in range(360,1000,128):
        for x in range(120,1800,168):
            box=(x,y,x+96,min(y+96,1080))
            tile_differences.append(difference(a.crop(box),b.crop(box))['mean_absolute_rgb_difference'])
    tile_mean=sum(tile_differences)/len(tile_differences)
    tile_std=math.sqrt(sum((v-tile_mean)**2 for v in tile_differences)/len(tile_differences))
    check('cloud drift produces spatially nonuniform changes across scene tiles', tile_std>.25 and max(tile_differences)-min(tile_differences)>.75)
    glow = difference(a,images['close-day-glow-off.png'])
    check('native Glow creates an actual visible halo contribution', glow['changed_pixels_over_2']>=100 and glow['mean_absolute_rgb_difference']>.025)
    histogram=a.convert('L').histogram()
    white_fraction=sum(histogram[250:])/(a.width*a.height)
    check('Glow avoids washing the frame into near-white', white_fraction<.08)
    fog = difference(a,images['close-day-atmosphere-off.png'])
    check('native volumetric atmosphere changes real rendered light', fog['changed_pixels_over_2']>=500 and fog['mean_absolute_rgb_difference']>.10)
    normal = {}
    for side in ['left','right']:
        on=images[f'snow-{side}-normals-on.png']
        flat=images[f'snow-{side}-normals-off.png']
        normal[side]=difference(on,flat)
        check(side+': actual background material responds to normal toggle', normal[side]['changed_pixels_over_2']>=100 and normal[side]['mean_absolute_rgb_difference']>.05)
    normal['directional_on']=difference(images['snow-left-normals-on.png'],images['snow-right-normals-on.png'])
    normal['directional_off']=difference(images['snow-left-normals-off.png'],images['snow-right-normals-off.png'])
    check('normal relighting responds to light direction beyond flat baseline', normal['directional_on']['mean_absolute_rgb_difference']>normal['directional_off']['mean_absolute_rgb_difference']+.10)
    # Independent global-light controls add evidence without weakening any cloud,
    # normal, Glow, fog, framing or parallax threshold above.
    equal = lambda a,b: math.isclose(float(a),float(b),rel_tol=1e-6,abs_tol=1e-6)
    frozen_ok = all(equal(row['global_light_readback']['before_'+field],row['global_light_readback']['after_'+field])
                    for row in records.values() for field in ('clock_seconds','sun_energy','ambient_energy'))
    check('global clock and actual native energies stay frozen throughout every controlled read-back',frozen_ok)
    controlled_names = ['close-day-clouds-a.png','close-day-clouds-off.png','close-day-clouds-b.png',
                        'close-day-glow-off.png','close-day-atmosphere-off.png','close-dusk-atmosphere.png',
                        'close-route-left.png','close-route-right.png']
    check('existing cloud post-effect and parallax comparisons hold enabled global modulation at its neutral t0',
          all(records[name]['global_light']['enabled'] is True and equal(records[name]['global_light']['clock_seconds'],0)
              and equal(records[name]['global_light']['sun_multiplier'],1) and equal(records[name]['global_light']['ambient_multiplier'],1)
              for name in controlled_names))
    check('symmetric normal probes disable global modulation',all(records[f'snow-{side}-normals-{mode}.png']['global_light']['enabled'] is False
                                                               for side in ('left','right') for mode in ('on','off')))
    global_names = [f'close-day-global-{name}.png' for name in ('weak','strong','off')]
    global_records = [records[name] for name in global_names]
    states = [row['global_light'] for row in global_records]
    weak_state,strong_state,off_state = states
    probe = capture['global_lighting_probe']
    samples = probe.get('samples',[])
    check('global strong and weak times come from a recorded complete 0 to 90 second scan',
          len(samples)==91 and [row['clock_seconds'] for row in samples]==list(range(91))
          and equal(weak_state['clock_seconds'],probe['weak_time_seconds']) and equal(strong_state['clock_seconds'],probe['strong_time_seconds'])
          and equal(weak_state['sun_multiplier'],min(row['sun_multiplier'] for row in samples))
          and equal(strong_state['sun_multiplier'],max(row['sun_multiplier'] for row in samples)))
    check('global energy comparison has cloud occlusion disabled at one fixed phase',
          all(row['cloud_lighting']['enabled'] is False and equal(row['cloud_lighting']['clock_seconds'],0) for row in global_records)
          and len({row['cloud_lighting']['mask_sha256'] for row in global_records})==1)
    check('global comparison preserves camera actor sun direction and post-effect settings',
          all(row['state']['camera']==global_records[0]['state']['camera'] and row['state']['player']==global_records[0]['state']['player']
              and {k:v for k,v in row['main_light'].items() if k!='energy'}=={k:v for k,v in global_records[0]['main_light'].items() if k!='energy'}
              and {k:v for k,v in row['environment'].items() if k!='ambient_energy'}=={k:v for k,v in global_records[0]['environment'].items() if k!='ambient_energy'}
              and row['motion']['comparison_frozen'] is True for row in global_records))
    check('global multiplier metadata matches actual rendered sun and ambient energies',
          all(equal(row['main_light']['energy'],state['sun_base_energy']*state['sun_multiplier'])
              and equal(row['environment']['ambient_energy'],state['ambient_base_energy']*state['ambient_multiplier'])
              and equal(row['main_light']['energy'],state['sun_energy']) and equal(row['environment']['ambient_energy'],state['ambient_energy'])
              for row,state in zip(global_records,states)))
    check('global on produces distinct strong and weak sunlight independently of clouds',
          weak_state['enabled'] is True and strong_state['enabled'] is True
          and strong_state['sun_multiplier']-weak_state['sun_multiplier']>.02)
    check('global off restores the declared day base energies',off_state['enabled'] is False
          and equal(off_state['sun_multiplier'],1) and equal(off_state['ambient_multiplier'],1)
          and equal(global_records[2]['main_light']['energy'],1.45) and equal(global_records[2]['environment']['ambient_energy'],.55))
    weak_image,strong_image,off_image = [images[name] for name in global_names]
    global_difference = difference(weak_image,strong_image)
    check('global strong versus weak creates visible GPU pixel changes with clouds disabled',
          global_difference['changed_pixels_over_2']>=1000 and global_difference['mean_absolute_rgb_difference']>.20)
    luminance = {name:ImageStat.Stat(images[name].convert('L')).mean[0] for name in global_names}
    check('the selected stronger sunlight measurably increases scene luminance',luminance[global_names[1]]>luminance[global_names[0]]+.20)
    global_receivers=[]
    for name,rect in capture['cloud_receiver_rois'].items():
        box=box_from_normalized(rect,weak_image.size)
        delta=difference(weak_image.crop(box),strong_image.crop(box))
        check(name+': global energy change reaches the real rendered receiver without cloud shadows',
              delta['changed_pixels_over_2']>=100 and delta['mean_absolute_rgb_difference']>.20)
        global_receivers.append({'receiver':name,'crop_px':list(box),'weak_vs_strong':delta})
    weak_off,strong_off=difference(weak_image,off_image),difference(strong_image,off_image)
    check('global off has a visible pixel difference from enabled modulation',
          max(weak_off['changed_pixels_over_2'],strong_off['changed_pixels_over_2'])>=1000
          and max(weak_off['mean_absolute_rgb_difference'],strong_off['mean_absolute_rgb_difference'])>.20)
    live=capture.get('route_global_light',[])
    check('global modulation remains enabled and advances during actual physical route motion',len(live)==4
          and all(row['global_light']['enabled'] is True for row in live)
          and all(live[index+1]['global_light']['clock_seconds']>live[index]['global_light']['clock_seconds'] for index in range(len(live)-1)))
    global_report={'weak_time_seconds':probe['weak_time_seconds'],'strong_time_seconds':probe['strong_time_seconds'],
                   'weak_vs_strong':global_difference,'weak_vs_off':weak_off,'strong_vs_off':strong_off,
                   'off_vs_neutral_t0_baseline':difference(off_image,off),'luminance':luminance,'receivers':global_receivers,
                   'states':states,'clouds_disabled':True,'route_global_light':live}
    parallax={'passed':False,'scope':'route not captured'}
    if 'close-route-left.png' in images and 'close-route-right.png' in images:
        parallax=landmark_pixel_matching(images['close-route-left.png'],images['close-route-right.png'],records['close-route-left.png'],records['close-route-right.png'])
        check('physical left-right route completed', capture.get('route',{}).get('completed') is True)
        check('actual GPU snow-ridge motion matches expected parallax', parallax['passed'])
    report={'schema':3,'passed':all(c['passed'] for c in checks),'checks':checks,
            'scope':'Independent GPU RGB read-back; global energy strong/weak/off with clouds disabled; normal toggle and light direction; spatial cloud receivers and drift; native Glow and fog; visual design approval remains external',
            'capture_sha256':digest(report_path),'runtime_fingerprint':capture.get('runtime_fingerprint',''),
            'cloud_receivers':receiver_results,'cloud_motion':cloud_motion,'cloud_tile_difference_std':tile_std,
            'cloud_tile_mean_differences':tile_differences,'glow':glow,'near_white_fraction':white_fraction,
            'volumetric_atmosphere':fog,'snow_normals':normal,'global_light':global_report,'parallax':parallax,
            'partial_cloud_appearance':partial_appearance,'cloud_transmission':transmission_evidence}
    return finish(destination,'atmosphere-gpu-pixel-report.json',report)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['assets','gpu'])
    parser.add_argument('--output',default='build/forest-hamlet/atmosphere-r3-final')
    args=parser.parse_args()
    destination=(ROOT/args.output).resolve()
    destination.relative_to(ROOT)
    destination.mkdir(parents=True,exist_ok=True)
    (validate_assets if args.command=='assets' else validate_capture)(destination)


if __name__=='__main__':
    main()
