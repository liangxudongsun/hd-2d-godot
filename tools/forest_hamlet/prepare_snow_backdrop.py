#!/usr/bin/env python3
"""Prepare technical snow normals; never retouch or resample the approved color art.

The normal field is painted with explicit low-frequency geometric facets. RGB
brightness is never interpreted as height. The runtime uses signed light-normal
response around a flat reference to gently relight an already painted plate.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil

import numpy as np
from PIL import Image, ImageDraw, ImageFilter


ROOT = Path(__file__).resolve().parents[2]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def smoothstep(a: float, b: float, value: np.ndarray) -> np.ndarray:
    t = np.clip((value - a) / (b - a), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def polygon_mask(points, size, feather):
    width, height = size
    image = Image.new('L', size, 0)
    ImageDraw.Draw(image).polygon([(round(u * (width - 1)), round(v * (height - 1))) for u, v in points], fill=255)
    # This is a technical normal-region mask, not a filter on the color art.
    if feather > 0:
        image = image.filter(ImageFilter.GaussianBlur(feather))
    return np.asarray(image, dtype=np.float32) / 255.0


def prepare(source: Path, rig_path: Path, output: Path) -> dict:
    rig = json.loads(rig_path.read_text())
    with Image.open(source) as image:
        width, height = image.size
    output.mkdir(parents=True, exist_ok=True)
    color = output / 'color.png'
    if source.resolve() != color.resolve():
        shutil.copyfile(source, color)
    if digest(color) != digest(source):
        raise RuntimeError('Approved color art changed during copy')

    # Hand-annotated visible faces are drawn from rear to front. The global
    # horizontal mist band gradually flattens the technical relief at its base.
    y = np.linspace(0.0, 1.0, height, dtype=np.float32)[:, None]
    mist_fade = 1.0 - smoothstep(rig['mist_fade_begin'], rig['mist_fade_end'], y)
    vector = np.zeros((height, width, 3), dtype=np.float32)
    vector[:, :, 2] = 1.0
    coverage = np.zeros((height, width), dtype=np.float32)
    for massif in rig['massifs']:
        apex, left, right, base = (massif[key] for key in ['apex', 'left', 'right', 'ridge_base'])
        for polygon, raw_normal in [([apex, left, base], massif['left_normal']), ([apex, base, right], massif['right_normal'])]:
            mask = polygon_mask(polygon, (width, height), rig['edge_feather_pixels']) * mist_fade * massif['weight']
            normal = np.array(raw_normal, dtype=np.float32)
            normal /= np.linalg.norm(normal)
            vector = vector * (1.0 - mask[:, :, None]) + normal[None, None, :] * mask[:, :, None]
            coverage = mask + coverage * (1.0 - mask)
    vector /= np.maximum(np.linalg.norm(vector, axis=2, keepdims=True), 1e-8)
    encoded = np.clip(np.rint((vector + 1.0) * 127.5), 0, 255).astype(np.uint8)
    # The exact neutral value is contractually stable outside the annotation.
    flat = coverage < (1.0 / 255.0)
    encoded[flat] = [128, 128, 255]
    Image.fromarray(encoded, 'RGB').save(output / 'normal.png', optimize=True)

    # R: mountain confidence; G: optional semantic distance (not actual depth);
    # B: mist contribution. It is metadata for material blending, NOT a claim
    # that the color plate has already been separated into independent layers.
    semantic = np.zeros((height, width, 3), dtype=np.float32)
    semantic[:, :, 0] = coverage
    semantic[:, :, 1] = np.clip(coverage * 0.7 + smoothstep(0.52, 0.80, y) * 0.18, 0, 1)
    semantic[:, :, 2] = smoothstep(rig['mist_fade_begin'], rig['mist_fade_end'], y)
    Image.fromarray(np.rint(semantic * 255).astype(np.uint8), 'RGB').save(output / 'regions.png', optimize=True)

    decoded = encoded.astype(np.float32) / 127.5 - 1.0
    normal_error = np.abs(np.linalg.norm(decoded, axis=2) - 1.0)
    horizontal_range = (float(decoded[:, :, 0].min()), float(decoded[:, :, 0].max()))
    sky = y[:, 0] < 0.275
    tests = {
        'approved_color_byte_identical': digest(color) == digest(source),
        'exact_source_dimensions': Image.open(color).size == (width, height),
        'normal_matches_color_dimensions': Image.open(output / 'normal.png').size == (width, height),
        'sky_is_flat_normal': bool(np.all(encoded[sky] == np.array([128, 128, 255], dtype=np.uint8))),
        'bottom_mist_is_flat_normal': bool(np.all(encoded[y[:, 0] > 0.79] == np.array([128, 128, 255], dtype=np.uint8))),
        'normal_unit_error_under_0_007': bool(normal_error.max() < 0.007),
        'opposing_ridge_faces': horizontal_range[0] < -0.2 and horizontal_range[1] > 0.2,
        'terrain_not_brightness_derived': rig['color_is_height'] is False,
    }
    if not all(tests.values()):
        raise RuntimeError('Technical normal validation failed: ' + json.dumps(tests))
    manifest = {
        'schema': 1,
        'id': 'forest-hamlet-snow-backdrop-r1',
        'source': 'art/inputs/forest-hamlet/snow-r1/source/snow-master.png',
        'source_sha256': digest(source),
        'rig': 'art/inputs/forest-hamlet/snow-r1/normal-rig.json',
        'rig_sha256': digest(rig_path),
        'generator': 'tools/forest_hamlet/prepare_snow_backdrop.py',
        'generator_sha256': digest(Path(__file__)),
        'dimensions': [width, height],
        'color': 'assets/forest-hamlet/backdrop/color.png',
        'normal': 'assets/forest-hamlet/backdrop/normal.png',
        'regions': 'assets/forest-hamlet/backdrop/regions.png',
        'files': {name: digest(output / name) for name in ['color.png', 'normal.png', 'regions.png']},
        'normal_method': rig['method'],
        'normal_convention': 'tangent space OpenGL; X right, Y up, positive Z',
        'normal_strength': rig['normal_strength_runtime'],
        'normal_max_unit_error': float(normal_error.max()),
        'geometry_count': 1,
        'parallax_kind': 'single_distant_board',
        'independent_color_layers': 1,
        'geometric_facets': len(rig['massifs']) * 2,
        'normal_region_fraction': float(np.mean(coverage > 0.02)),
        'landmarks': rig['landmarks'],
        'validation': {'passed': all(tests.values()), 'checks': tests},
        'limitations': ['Original illustration contains painted illumination; this is restrained dynamic normal relighting, not photometric reconstruction.', 'A single complete board has real relative parallax but no independent range-to-range motion.'],
    }
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + '\n')
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', default='art/inputs/forest-hamlet/snow-r1/source/snow-master.png')
    parser.add_argument('--rig', default='art/inputs/forest-hamlet/snow-r1/normal-rig.json')
    parser.add_argument('--output', default='assets/forest-hamlet/backdrop')
    args = parser.parse_args()
    result = prepare(ROOT / args.source, ROOT / args.rig, ROOT / args.output)
    print(json.dumps({'passed': result['validation']['passed'], 'source_sha256': result['source_sha256'], 'dimensions': result['dimensions'], 'geometric_facets': result['geometric_facets'], 'normal_unit_error': result['normal_max_unit_error']}))


if __name__ == '__main__':
    main()
