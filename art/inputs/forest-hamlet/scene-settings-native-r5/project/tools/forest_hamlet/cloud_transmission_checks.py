#!/usr/bin/env python3
"""Measure real cloud transmission after a calibrated linear-tone-map capture.

Original PNG bytes are retained. These are inverse-sRGB estimates, never raw
HDR. The half-energy control tests the assumed transfer function. The maximum
thickness target must be explained by actual quantization bounds; tolerances
for spatial alpha-hash coverage are fixed here before GPU measurements.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import statistics

from PIL import Image, ImageChops, ImageStat

ROOT = Path(__file__).resolve().parents[2]
NAMES = (
    "cloud-direct-dark", "cloud-direct-clear", "cloud-direct-half-calibration",
    "cloud-direct-uniform-clear", "cloud-direct-thin", "cloud-direct-thin-repeat",
    "cloud-direct-thick", "cloud-direct-natural",
)
THIN_TARGET = 0.90
THICK_TARGET = 0.70
THIN_SPATIAL_TOLERANCE = 0.02
HALF_CALIBRATION_TOLERANCE = 0.015
REPEAT_MEAN_TOLERANCE = 0.005


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inverse_srgb(encoded: float) -> float:
    encoded = max(0.0, min(1.0, encoded))
    return encoded / 12.92 if encoded <= 0.04045 else ((encoded + 0.055) / 1.055) ** 2.4


LINEAR = [inverse_srgb(v / 255.0) for v in range(256)]
LOWER = [inverse_srgb((v - 0.5) / 255.0) for v in range(256)]
UPPER = [inverse_srgb((v + 0.5) / 255.0) for v in range(256)]


def luma(pixel, table=LINEAR):
    return table[pixel[0]] * .2126 + table[pixel[1]] * .7152 + table[pixel[2]] * .0722


def quantile(sorted_values, fraction):
    return sorted_values[round((len(sorted_values) - 1) * fraction)]


def measure(image, clear, dark, box):
    a, b, z = [list(im.crop(box).getdata()) for im in (image, clear, dark)]
    denominators = [luma(v) - luma(d) for v, d in zip(b, z)]
    numerators = [luma(v) - luma(d) for v, d in zip(a, z)]
    if not denominators or min(denominators) <= .01:
        raise ValueError("Predeclared radiometry ROI is not fully lit in the clear baseline: " + str(box))
    total_base = sum(denominators)
    ratio = sum(numerators) / total_base
    per_pixel = sorted(n / d for n, d in zip(numerators, denominators))
    lower_n = sum(luma(v, LOWER) - luma(d, UPPER) for v, d in zip(a, z))
    upper_n = sum(luma(v, UPPER) - luma(d, LOWER) for v, d in zip(a, z))
    lower_d = sum(luma(v, LOWER) - luma(d, UPPER) for v, d in zip(b, z))
    upper_d = sum(luma(v, UPPER) - luma(d, LOWER) for v, d in zip(b, z))
    # Spatial blocks expose hash coverage/noise instead of hiding it in a mean.
    block_means = []
    width, height = box[2] - box[0], box[3] - box[1]
    for y in range(0, height, 32):
        for x in range(0, width, 32):
            indices = [yy * width + xx for yy in range(y, min(y + 32, height))
                       for xx in range(x, min(x + 32, width))]
            block_means.append(sum(numerators[i] for i in indices) / sum(denominators[i] for i in indices))
    return {
        "pixels": len(a), "rect_px": list(box), "linear_clear_mean": total_base / len(a),
        "linear_sample_mean": sum(numerators) / len(a), "direct_transmission_estimate": ratio,
        "attenuation_estimate": 1.0 - ratio,
        "quantization_interval": [lower_n / upper_d, upper_n / lower_d],
        "per_pixel_min": per_pixel[0], "per_pixel_p01": quantile(per_pixel, .01),
        "per_pixel_median": quantile(per_pixel, .5), "per_pixel_p99": quantile(per_pixel, .99),
        "per_pixel_max": per_pixel[-1], "per_pixel_stddev": statistics.pstdev(per_pixel),
        "spatial_blocks_32px": {"count": len(block_means), "mean": statistics.mean(block_means),
                                "stddev": statistics.pstdev(block_means), "min": min(block_means),
                                "max": max(block_means), "values": block_means},
    }


def validate(destination: Path):
    capture_path = destination / "cloud-transmission-capture.json"
    capture = json.loads(capture_path.read_text())
    checks = []

    def check(label, value):
        checks.append({"label": label, "passed": bool(value)})

    check("actual native GPU capture completed", capture.get("passed") is True and capture.get("gpu") is True
          and capture.get("renderer") == "forward_plus" and bool(capture.get("adapter"))
          and capture.get("viewport") == [1024, 768] and not capture.get("failures")
          and capture.get("checks") and all(c.get("passed") is True for c in capture["checks"]))
    records = {row["file"]: row for row in capture.get("screenshots", [])}
    check("exact eight original GPU controls are present", len(capture.get("screenshots", [])) == len(NAMES)
          and set(records) == {name + ".png" for name in NAMES})
    if not checks[-1]["passed"]:
        raise ValueError("Incomplete cloud transmission capture")
    for name, expected in capture.get("source_files", {}).items():
        check("capture source identity: " + name, sha(ROOT / name.removeprefix("res://")) == expected)
    conditions = capture.get("conditions", {})
    check("linear tone mapper and fixed neutral measurement pipeline recorded",
          conditions.get("tone_mapper") == "LINEAR" and conditions.get("exposure") == 1.0
          and conditions.get("ambient_energy") == 0.0
          and all(conditions.get(k) is False for k in ("fog", "glow", "ssao", "ssil", "ssr", "gi",
                                                      "auto_exposure", "adjustments", "global_modulation")))
    images = {}
    for name in NAMES:
        path = destination / (name + ".png")
        row = records[path.name]
        check(name + ": PNG hash and viewport dimensions agree", sha(path) == row["sha256"] and row["size"] == [1024, 768])
        images[name] = Image.open(path).convert("RGB")
        check(name + ": decoded PNG dimensions agree", images[name].size == (1024, 768))
        split = row["cloud_lighting"]["light_split"]
        source, base, cloud = split["source"], split["base70"], split["cloud30"]
        energy = row["source_energy"]
        check(name + ": native 70/30 lights conserve the authoritative total",
              math.isclose(base["energy"], .7 * energy, abs_tol=1e-6)
              and math.isclose(cloud["energy"], .3 * energy, abs_tol=1e-6)
              and math.isclose(base["energy"] + cloud["energy"], source["energy"], abs_tol=1e-6)
              and source["sky_mode"] == 2 and base["sky_mode"] == cloud["sky_mode"] == 1)
        layer = split["cloud_layer_mask"]
        check(name + ": both branches preserve ordinary caster shadows; only 30 percent branch sees clouds",
              base["shadow_enabled"] is True and cloud["shadow_enabled"] is True
              and base["shadow_opacity"] == cloud["shadow_opacity"] == 1.0
              and (base["shadow_caster_mask"] & layer) == 0 and (cloud["shadow_caster_mask"] & layer) == layer
              and (base["shadow_caster_mask"] & 1) == (cloud["shadow_caster_mask"] & 1) == 1
              and row["cloud_lighting"]["caster_layers"] == layer)
    clear, dark = images["cloud-direct-clear"], images["cloud-direct-dark"]
    roi_results = []
    for roi in capture["receiver_rois_px"]:
        box = tuple(roi["rect"])
        clear_extrema, dark_extrema = clear.crop(box).getextrema(), dark.crop(box).getextrema()
        check(roi["id"] + ": clear receiver avoids black and clipping", all(lo >= 40 and hi <= 235 for lo, hi in clear_extrema))
        check(roi["id"] + ": dark control verifies no hidden ambient or emissive contribution", all(hi <= 1 for lo, hi in dark_extrema))
        measurements = {name: measure(images[name], clear, dark, box) for name in NAMES if name not in ("cloud-direct-dark", "cloud-direct-clear")}
        half = measurements["cloud-direct-half-calibration"]
        check(roi["id"] + ": actual half-energy control validates inverse sRGB linear estimate",
              abs(half["direct_transmission_estimate"] - .5) <= HALF_CALIBRATION_TOLERANCE)
        uniform_clear = measurements["cloud-direct-uniform-clear"]
        check(roi["id"] + ": zero attenuation matches disabled clouds", abs(uniform_clear["direct_transmission_estimate"] - 1.0) <= .01)
        thin, repeat, thick = [measurements["cloud-direct-" + name] for name in ("thin", "thin-repeat", "thick")]
        check(roi["id"] + ": thin cloud transmits 90 percent within fixed spatial tolerance",
              abs(thin["direct_transmission_estimate"] - THIN_TARGET) <= THIN_SPATIAL_TOLERANCE)
        check(roi["id"] + ": repeated frozen thin-cloud readback remains stable",
              abs(thin["direct_transmission_estimate"] - repeat["direct_transmission_estimate"]) <= REPEAT_MEAN_TOLERANCE)
        check(roi["id"] + ": thick-cloud 70 percent target lies inside 8-bit quantization interval",
              thick["quantization_interval"][0] <= THICK_TARGET <= thick["quantization_interval"][1])
        check(roi["id"] + ": native shadow attenuation never becomes an opaque cloud projection",
              min(thin["per_pixel_min"], thick["per_pixel_min"], measurements["cloud-direct-natural"]["per_pixel_min"]) >= .68)
        roi_results.append({"id": roi["id"], "measurements": measurements})

    grid = capture["natural_grid_rect_px"]
    tiles = []
    for y in range(grid[1], grid[3], 76):
        for x in range(grid[0], grid[2], 76):
            box = (x, y, min(x + 76, grid[2]), min(y + 76, grid[3]))
            tile = measure(images["cloud-direct-natural"], clear, dark, box)
            tiles.append({"rect_px": list(box), "transmission": tile["direct_transmission_estimate"],
                          "quantization_interval": tile["quantization_interval"]})
    transmissions = [tile["transmission"] for tile in tiles]
    check("natural cloud field stays within 70 to 100 percent linear direct transmission",
          min(transmissions) >= .68 and max(transmissions) <= 1.01)
    check("natural cloud field creates spatially varying partial transmission",
          max(transmissions) - min(transmissions) >= .015)
    natural = records["cloud-direct-natural.png"]
    diagnostics = natural["natural_ray_samples"]
    check("natural mode is enabled and diagnostics declare bounded density-driven attenuation",
          natural["clouds_enabled"] is True and natural["uniform_attenuation"] == -1.0
          and all(0.0 <= d["effective_attenuation"] <= .3 and d["inside_caster"] for d in diagnostics))
    shadow_box = tuple(capture["ordinary_shadow_control"]["rect_px"])
    shadow_values = [luma(v) for v in clear.crop(shadow_box).getdata()]
    ordinary_shadow_ratio = statistics.mean(shadow_values) / roi_results[0]["measurements"]["cloud-direct-thin"]["linear_clear_mean"]
    check("ordinary solid object's native shadow remains dark on both light branches", ordinary_shadow_ratio < .05)
    failures = [c["label"] for c in checks if not c["passed"]]
    report = {
        "schema": 1, "passed": not failures, "checks": checks, "failures": failures,
        "scope": "Measured native cloud direct-light transmission on an actual GPU diffuse receiver; separate from final scene LDR appearance",
        "capture_sha256": sha(capture_path), "runtime_fingerprint": capture.get("runtime_fingerprint", ""),
        "measurement_encoding": "Calibrated inverse-sRGB estimate after LINEAR tonemap; not raw HDR",
        "method": "Linear RGB luminance after IEC sRGB inverse transfer; subtract captured zero-sun baseline; ratio of summed irradiance proxies at identical receiver pixels",
        "preregistered_tolerances": {"thin_target": THIN_TARGET, "thin_spatial_tolerance": THIN_SPATIAL_TOLERANCE,
                                    "thick_target": THICK_TARGET, "thick_tolerance": "target must lie inside actual 8-bit rounding interval",
                                    "half_calibration_tolerance": HALF_CALIBRATION_TOLERANCE, "repeat_mean_tolerance": REPEAT_MEAN_TOLERANCE},
        "rois": roi_results, "natural_tiles": tiles,
        "natural_transmission_range": [min(transmissions), max(transmissions)],
        "natural_transmission_stddev": statistics.pstdev(transmissions),
        "ordinary_shadow_ratio": ordinary_shadow_ratio,
        "original_pngs": [{"file": name + ".png", "sha256": records[name + ".png"]["sha256"]} for name in NAMES],
    }
    (destination / "cloud-transmission-pixel-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print("CLOUD_TRANSMISSION_PIXELS " + json.dumps({"passed": report["passed"], "checks": len(checks), "failures": failures,
          "rois": [{"id": r["id"], "thin": r["measurements"]["cloud-direct-thin"]["direct_transmission_estimate"],
                    "thick": r["measurements"]["cloud-direct-thick"]["direct_transmission_estimate"]} for r in roi_results],
          "natural_range": report["natural_transmission_range"], "ordinary_shadow_ratio": ordinary_shadow_ratio}))
    if failures:
        raise RuntimeError("Cloud transmission measurement failed; inspect original captures and recorded distributions")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="build/forest-hamlet/cloud-transmission-r3-prototype")
    args = parser.parse_args()
    target = (ROOT / args.output).resolve()
    target.relative_to(ROOT)
    validate(target)
