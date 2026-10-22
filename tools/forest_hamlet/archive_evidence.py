#!/usr/bin/env python3
"""Archive verified forest scene evidence without modifying native AW/VGP records."""
from pathlib import Path
import argparse
import hashlib
import json
import shutil
import struct

from PIL import Image, ImageChops, ImageStat

ROOT = Path(__file__).resolve().parents[2]


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', default='build/forest-hamlet/final-r4')
    parser.add_argument('--aw-run-id', default='forest-hamlet-20261022-r1')
    parser.add_argument('--vgp-run-id', default='forest-hamlet-20261022-r2')
    parser.add_argument('--output', default='docs/forest-hamlet', help='Use a new revision directory to preserve prior evidence.')
    parser.add_argument('--shared-test', default='build/forest-hamlet/logs/make-test-final.json')
    args = parser.parse_args()
    capture = (ROOT / args.capture).resolve()
    capture.relative_to(ROOT)
    docs = (ROOT / args.output).resolve()
    docs.relative_to(ROOT)
    evidence, images = docs / 'evidence', docs / 'captures'
    evidence.mkdir(parents=True, exist_ok=True)
    images.mkdir(parents=True, exist_ok=True)
    (docs / '.gdignore').write_text('')
    aw = ROOT / 'art/derived/forest-hamlet' / args.aw_run_id
    vgp = ROOT / 'art/derived/forest-hamlet' / args.vgp_run_id / 'vgp'
    report = read(capture / 'gpu-report.json')
    fingerprint = read(capture / 'runtime-fingerprint.json')
    runtime = read(ROOT / 'build/forest-hamlet/runtime/runtime-report.json')
    assets = read(ROOT / 'build/forest-hamlet/assets-report.json')
    shared = read(ROOT / args.shared_test)
    billboard_path = capture / 'billboard-gpu-report.json'
    billboard = read(billboard_path) if billboard_path.exists() else None
    if billboard is not None and not billboard['passed']:
        raise RuntimeError('Billboard GPU read-back did not pass')
    for name, result in [('GPU', report), ('runtime', runtime), ('assets', assets), ('make test', shared)]:
        if not result['passed']:
            raise RuntimeError(f'{name} evidence is not passed')
    changed = [p for p, h in fingerprint['files'].items() if sha(ROOT / p) != h]
    if changed:
        raise RuntimeError(f'Files changed after GPU capture: {changed}')
    vgp_summary = read(vgp / 'summary.json')
    for name in ['materials-check.response.json', 'models-check.response.json']:
        check = read(vgp / name)
        if not check['ready'] or check['issues']:
            raise RuntimeError('VGP technical check is not ready: ' + name)
    for name in ['materials', 'models']:
        for item in read(vgp / (name + '.frozen-files.json')):
            if sha(ROOT / item['path']) != item['sha256']:
                raise RuntimeError('Runtime sources differ from latest VGP candidate: ' + item['path'])
    copies = [(capture / 'gpu-report.json', 'gpu-report.json'),
              (capture / 'runtime-fingerprint.json', 'runtime-fingerprint.json'),
              (ROOT / 'build/forest-hamlet/runtime/runtime-report.json', 'runtime-report.json'),
              (ROOT / 'build/forest-hamlet/assets-report.json', 'assets-report.json'),
              (aw / 'materials-summary.json', 'materials-summary.json'),
              (vgp / 'summary.json', 'vgp-summary.json'),
              (vgp / 'materials-check.response.json', 'vgp-materials-check.json'),
              (vgp / 'models-check.response.json', 'vgp-models-check.json')]
    if billboard is not None:
        copies.append((billboard_path, 'billboard-gpu-report.json'))
    for source, name in copies:
        shutil.copyfile(source, evidence / name)
    for shot in report['screenshots']:
        source = capture / shot['file']
        if sha(source) != shot['sha256']:
            raise RuntimeError('Screenshot identity mismatch: ' + shot['file'])
        shutil.copyfile(source, images / source.name)
    pairs = [('comparison-baseline', 'ground-normals-off'),
             ('comparison-baseline', 'dof-off'), ('comparison-baseline', 'bloom-off'),
             ('dusk-glow-on', 'dusk-glow-off'),
             ('ground-detail-normals-on', 'ground-detail-normals-off')]
    comparisons = []
    for a, b in pairs:
        ia = Image.open(capture / (a + '.png')).convert('RGB')
        ib = Image.open(capture / (b + '.png')).convert('RGB')
        diff = ImageChops.difference(ia, ib)
        red, green, blue = diff.split()
        maximum = ImageChops.lighter(ImageChops.lighter(red, green), blue)
        comparisons.append({'baseline': a + '.png', 'variant': b + '.png',
                            'changed_pixels_above_2_rgb_levels': sum(maximum.histogram()[3:]),
                            'mean_absolute_rgb_difference_0_255': sum(ImageStat.Stat(diff).mean) / 3,
                            'scope': 'Descriptive frozen-scene image difference, not an artistic score.'})
    triangles = {}
    for path in sorted((ROOT / 'assets/forest-hamlet/models').glob('*.glb')):
        data = path.read_bytes()
        length, kind = struct.unpack_from('<II', data, 12)
        gltf = json.loads(data[20:20 + length])
        count = 0
        for mesh in gltf['meshes']:
            for part in mesh['primitives']:
                if part.get('mode', 4) == 4:
                    index = part.get('indices', part['attributes']['POSITION'])
                    count += gltf['accessors'][index]['count'] // 3
        triangles[path.stem] = count
    result = {'schema': 1, 'scene': 'res://scenes/forest_hamlet.tscn',
              'scope': 'Actual implementation and GPU evidence; user aesthetic approval remains pending.',
              'capture_run': capture.relative_to(ROOT).as_posix(),
              'runtime_fingerprint': report['runtime_fingerprint'],
              'fingerprint_file_count': len(fingerprint['files']), 'fingerprint_matches_current_files': True,
              'asset_checks': len(assets['checks']), 'asset_checks_passed': True,
              'runtime_checks': len(runtime['checks']), 'runtime_passed': True, 'gpu_passed': True,
              'gpu_adapter': report['adapter'], 'renderer': report['renderer'], 'viewport': report['viewport'],
              'screenshots': len(report['screenshots']), 'route_completed': report['route']['completed'],
              'route_waypoints': report['route']['waypoints'], 'route_simulation_seconds': report['route']['elapsed_seconds'],
              'asset_instances': report['asset_instances'], 'terrain_triangles': report['terrain_triangles'],
              'model_triangles': triangles, 'frame_counts': report['screenshots'][0]['render_counts'],
              'effect_comparisons': comparisons, 'original_character_files_unchanged': assets['character_files'],
              'aw': {'workflow': 'world.compile', 'run_id': args.aw_run_id, 'status': 'completed'},
              'vgp': {'run_id': args.vgp_run_id, 'case_id': vgp_summary['case_id'],
                      'round_id': vgp_summary['round_id'], 'stable_assets': 2, 'stage': 'concept_design',
                      'review_status': 'pending', 'technical_checks_ready': True,
                      'decisions_created': 0, 'stage_admissions_created': 0},
              'shared_make_test': shared,
              'reference_framing': report['screenshots'][0]['state'].get('framing'),
              'billboard_gpu': billboard,
              'material_tile_sizes': {item['name']:item['size'] for item in read(aw / 'materials-summary.json')['outputs']}}
    (evidence / 'validation.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
