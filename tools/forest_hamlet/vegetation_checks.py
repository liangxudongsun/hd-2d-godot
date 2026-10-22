#!/usr/bin/env python3
"""Independent source and GPU read-back checks for the image vegetation."""
from pathlib import Path
import argparse
import hashlib
import json
import math
import struct

from PIL import Image, ImageChops, ImageStat

ROOT = Path(__file__).resolve().parents[2]
IDS = ('broadleaf_a', 'broadleaf_b', 'fir', 'grass', 'fern', 'reeds',
       'flowers_white', 'flowers_pink', 'window_flowers', 'lily_pad')


def _save(path, report):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n')


def validate_vegetation_assets(destination=None):
    destination = Path(destination or ROOT / 'build/forest-hamlet/vegetation-assets')
    folder = ROOT / 'assets/forest-hamlet/vegetation'
    manifest_path = folder / 'manifest.json'
    manifest = json.loads(manifest_path.read_text())
    checks, records = [], []

    def check(label, condition):
        checks.append({'label': label, 'passed': bool(condition)})

    entries = manifest.get('assets', [])
    check('manifest has all ten unique vegetation species',
          len(entries) == len(IDS) and {a.get('id') for a in entries} == set(IDS))
    check('normal convention is explicit OpenGL', manifest.get('normal_convention') == 'OpenGL')
    for asset in entries:
        asset_id = asset['id']
        color_path = (folder / asset['color']).resolve()
        normal_path = (folder / asset['normal']).resolve()
        color_path.relative_to(folder.resolve())
        normal_path.relative_to(folder.resolve())
        with Image.open(color_path) as loaded:
            color_mode = loaded.mode
            color = loaded.convert('RGBA')
        with Image.open(normal_path) as loaded:
            normal_mode = loaded.mode
            normal = loaded.convert('RGBA')
        color_alpha = color.getchannel('A')
        normal_alpha = normal.getchannel('A')
        check(asset_id + ': both sources are RGBA', color_mode == 'RGBA' and normal_mode == 'RGBA')
        check(asset_id + ': color and normal dimensions agree with manifest',
              color.size == normal.size == tuple(asset['size_px']))
        alpha_equal = color.size == normal.size and color_alpha.tobytes() == normal_alpha.tobytes()
        check(asset_id + ': color and normal alpha bytes align exactly', alpha_equal)
        check(asset_id + ': transparent cutout includes visible pixels', color_alpha.getextrema() == (0, 255))
        bbox = color_alpha.point(lambda a: 255 if a >= 128 else 0).getbbox()
        visible_rect = [bbox[0], bbox[1], bbox[2]-bbox[0], bbox[3]-bbox[1]] if bbox else []
        check(asset_id + ': visible rectangle matches actual shader alpha cutoff', visible_rect == asset['visible_rect_px'])
        pivot = asset['pivot_px']
        check(asset_id + ': pixel pivot and world height are valid',
              0 <= pivot[0] <= color.width and 0 <= pivot[1] <= color.height and float(asset['height_m']) > 0)
        maximum_error = 0.0
        visible = tilted = negative_z = 0
        xy_squared = 0.0
        for r, g, b, a in normal.getdata():
            if a < 128:
                continue
            x, y, z = r/127.5-1.0, g/127.5-1.0, b/127.5-1.0
            maximum_error = max(maximum_error, abs(math.sqrt(x*x+y*y+z*z)-1.0))
            xy_squared += x*x+y*y
            visible += 1
            tilted += abs(x) > .04 or abs(y) > .04
            negative_z += z < -.004
        check(asset_id + ': quantized normal vectors retain unit length', visible > 0 and maximum_error <= .015)
        check(asset_id + ': normals use the outward tangent hemisphere', negative_z == 0)
        check(asset_id + ': normal map contains real directional detail', visible > 0 and tilted / max(visible, 1) > .01)
        hashes = {'color_sha256': hashlib.sha256(color_path.read_bytes()).hexdigest(),
                  'normal_sha256': hashlib.sha256(normal_path.read_bytes()).hexdigest(),
                  'alpha_sha256': hashlib.sha256(color_alpha.tobytes()).hexdigest()}
        for name, value in hashes.items():
            if name in asset:
                check(asset_id + ': ' + name + ' matches source bytes', value == asset[name])
        records.append({'id': asset_id, 'size': list(color.size), 'visible_rect': visible_rect,
                        'visible_pixels': visible, 'normal_max_length_error': maximum_error,
                        'normal_xy_rms': math.sqrt(xy_squared / max(visible, 1)),
                        'tilted_fraction': tilted / max(visible, 1), **hashes})
    # The old cottage embedded colored flower geometry. Its replacement must
    # retain the structural model and one gold icosahedron door handle only.
    cottage_path = ROOT / 'assets/forest-hamlet/models/cottage_without_plants.glb'
    check('plant-free cottage model exists', cottage_path.is_file())
    cottage_record = {}
    if cottage_path.is_file():
        data = cottage_path.read_bytes()
        valid_header = data[:4] == b'glTF' and struct.unpack_from('<I', data, 8)[0] == len(data)
        check('plant-free cottage is a valid glTF binary', valid_header)
        chunk_length, chunk_type = struct.unpack_from('<II', data, 12)
        if not valid_header or chunk_type != 0x4E4F534A:
            raise RuntimeError('Invalid plant-free cottage GLB container')
        gltf = json.loads(data[20:20+chunk_length])
        used_materials, gold_triangles = set(), 0
        for mesh in gltf.get('meshes', []):
            for primitive in mesh.get('primitives', []):
                material = gltf.get('materials', [])[primitive['material']]['name'].split('.')[0]
                used_materials.add(material)
                if material == 'flower_gold':
                    count = gltf['accessors'][primitive['indices']]['count'] if 'indices' in primitive else gltf['accessors'][primitive['attributes']['POSITION']]['count']
                    gold_triangles += count // 3
        forbidden = [name for name in used_materials if name.startswith('leaf_') or name in {'flower_white', 'flower_pink', 'flower_blue'}]
        check('plant-free cottage contains no leaf or colored flower primitive', not forbidden)
        check('gold door handle is retained without old gold flower geometry', gold_triangles == 20)
        cottage_record = {'sha256': hashlib.sha256(data).hexdigest(), 'materials': sorted(used_materials), 'gold_triangles': gold_triangles, 'forbidden_plant_materials': forbidden}
    report = {'schema': 1, 'passed': all(c['passed'] for c in checks), 'checks': checks,
              'manifest_sha256': hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
              'scope': 'Independent PNG alpha, dimension, pivot and encoded normal checks; no GPU or artistic approval',
              'assets': records, 'plant_free_cottage': cottage_record}
    _save(destination / 'vegetation-assets-report.json', report)
    print('VEGETATION_ASSETS ' + json.dumps({'passed': report['passed'], 'assets': len(records), 'checks': len(checks)}))
    if not report['passed']:
        raise RuntimeError('Vegetation asset validation failed: ' + '; '.join(c['label'] for c in checks if not c['passed']))
    return report


def _difference(a, b, mask=None):
    difference = ImageChops.difference(a.convert('RGB'), b.convert('RGB'))
    channels = difference.split()
    largest = ImageChops.lighter(ImageChops.lighter(channels[0], channels[1]), channels[2])
    changed = largest.point(lambda v: 255 if v > 2 else 0)
    if mask is not None:
        changed = ImageChops.multiply(changed, mask)
    count = sum(changed.histogram()[1:])
    valid_pixels = sum(mask.histogram()[1:]) if mask is not None else a.width*a.height
    mean = sum(ImageStat.Stat(difference, mask=mask).mean) / 3.0 if valid_pixels else 0.0
    return {'pixels': valid_pixels, 'changed_pixels_over_2': count,
            'changed_fraction': count/max(valid_pixels, 1), 'mean_absolute_rgb_difference': mean}


def validate_vegetation_capture(destination):
    destination = Path(destination)
    capture = json.loads((destination / 'vegetation-gpu-report.json').read_text())
    checks, per_species = [], []

    def check(label, condition):
        checks.append({'label': label, 'passed': bool(condition)})

    check('GPU capture itself passed', capture.get('passed') is True)
    check('capture uses actual Forward+ GPU', capture.get('renderer') == 'forward_plus' and bool(capture.get('adapter')))
    names = {'left_on': 'plants-light-left-normals-on.png', 'left_off': 'plants-light-left-normals-off.png',
             'right_on': 'plants-light-right-normals-on.png', 'right_off': 'plants-light-right-normals-off.png'}
    images = {key: Image.open(destination / value).convert('RGB') for key, value in names.items()}
    check('all four lighting probes have the same resolution', len({im.size for im in images.values()}) == 1)
    check('lighting probes cover all ten species', {p['id'] for p in capture['probe_layout']} == set(IDS))
    for item in capture['probe_layout']:
        box = tuple(int(x) for x in item['crop_px'])
        crops = {key: im.crop(box) for key, im in images.items()}
        # The isolated trial has a constant clear background, no world, fog,
        # DoF, moving vertices, shadow-casters or other changing light sources.
        masks = []
        for key, im in images.items():
            background = Image.new('RGB', crops[key].size, im.getpixel((0, 0)))
            delta = ImageChops.difference(crops[key], background)
            channels = delta.split()
            masks.append(ImageChops.lighter(ImageChops.lighter(channels[0], channels[1]), channels[2]).point(lambda v: 255 if v > 3 else 0))
        mask = masks[0]
        for other in masks[1:]:
            mask = ImageChops.lighter(mask, other)
        left = _difference(crops['left_on'], crops['left_off'], mask)
        right = _difference(crops['right_on'], crops['right_off'], mask)
        directional_on = _difference(crops['left_on'], crops['right_on'], mask)
        directional_off = _difference(crops['left_off'], crops['right_off'], mask)
        asset_id = item['id']
        check(asset_id + ': visible GPU specimen', left['pixels'] >= 100)
        check(asset_id + ': normal toggle changes left-lit surface', left['changed_pixels_over_2'] >= 20 and left['mean_absolute_rgb_difference'] > .25)
        check(asset_id + ': normal toggle changes right-lit surface', right['changed_pixels_over_2'] >= 20 and right['mean_absolute_rgb_difference'] > .25)
        check(asset_id + ': normal detail responds to light direction beyond flat-plane baseline',
              directional_on['changed_pixels_over_2'] >= 20 and directional_on['mean_absolute_rgb_difference'] > directional_off['mean_absolute_rgb_difference'] + .25)
        per_species.append({'id': asset_id, 'crop_px': list(box), 'left_normal_toggle': left,
                            'right_normal_toggle': right, 'light_direction_normals_on': directional_on,
                            'light_direction_normals_off': directional_off})
    with Image.open(destination / 'close-normals-on.png') as a, Image.open(destination / 'close-normals-off.png') as b:
        gameplay_difference = _difference(a, b)
    check('vegetation normal switch changes frozen actual gameplay image', gameplay_difference['changed_pixels_over_2'] >= 200)
    report = {'schema': 1, 'passed': all(c['passed'] for c in checks), 'checks': checks,
              'scope': 'Independent real GPU RGB pixel read-back; identical albedo and frozen geometry; normal toggle and symmetric light-direction comparisons',
              'gameplay_normal_toggle': gameplay_difference, 'species': per_species,
              'input_capture_sha256': hashlib.sha256((destination / 'vegetation-gpu-report.json').read_bytes()).hexdigest()}
    _save(destination / 'vegetation-gpu-pixel-report.json', report)
    print('VEGETATION_GPU_PIXELS ' + json.dumps({'passed': report['passed'], 'species': len(per_species), 'checks': len(checks)}))
    if not report['passed']:
        raise RuntimeError('Vegetation GPU pixel validation failed: ' + '; '.join(c['label'] for c in checks if not c['passed']))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['assets', 'gpu'])
    parser.add_argument('--output', default='build/forest-hamlet/vegetation')
    args = parser.parse_args()
    destination = (ROOT / args.output).resolve()
    destination.relative_to(ROOT)
    if args.command == 'assets':
        validate_vegetation_assets(destination)
    else:
        validate_vegetation_capture(destination)


if __name__ == '__main__':
    main()
