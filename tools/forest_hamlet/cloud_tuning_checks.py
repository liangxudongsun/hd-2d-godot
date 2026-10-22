#!/usr/bin/env python3
"""Check original GPU read-backs of the user's two live cloud controls.

The production scene is tone mapped. These comparisons establish visible
responses and matching clear endpoints, not radiometric transmission ratios.
The previous calibrated cloud evidence remains a separate historical result.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageChops, ImageStat

ROOT = Path(__file__).resolve().parents[2]
NAMES = (
    "cloud-tuning-default", "cloud-tuning-contrast-low", "cloud-tuning-contrast-zero",
    "cloud-tuning-density-zero", "cloud-tuning-density-full", "cloud-tuning-contrast-maximum", "cloud-tuning-panel-1080",
    "cloud-tuning-panel-720", "cloud-tuning-input-720",
)
SOURCE_FILES = (
    "scripts/forest_hamlet/scene.gd", "scripts/forest_hamlet/cloud_lighting.gd",
    "shaders/forest_hamlet/cloud_occluder.gdshader",
    "tests/forest_hamlet/cloud_tuning_runtime.gd",
    "tools/forest_hamlet/capture_cloud_tuning.gd",
    "tools/forest_hamlet/cloud_tuning_checks.py", "tools/forest_hamlet/run_cloud_tuning.py",
)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def difference(a: Image.Image, b: Image.Image) -> dict:
    delta = ImageChops.difference(a, b)
    stats = ImageStat.Stat(delta)
    histogram = delta.convert("L").histogram()
    return {"mean_abs_rgb": sum(stats.mean) / 3.0,
            "pixels_luma_difference_above_2": sum(histogram[3:]),
            "pixel_count": a.width * a.height}


def validate(destination: Path) -> dict:
    capture_path = destination / "cloud-tuning-gpu-report.json"
    capture = json.loads(capture_path.read_text(encoding="utf-8"))
    checks = []

    def check(label: str, value: bool) -> None:
        checks.append({"label": label, "passed": bool(value)})

    check("actual Forward Plus capture and every runtime capture contract passed",
          capture.get("schema") == 1 and capture.get("passed") is True
          and capture.get("gpu") is True and capture.get("renderer") == "forward_plus"
          and bool(capture.get("adapter")) and not capture.get("failures")
          and bool(capture.get("checks")) and all(row.get("passed") is True for row in capture["checks"]))
    records = {row["file"]: row for row in capture.get("screenshots", [])}
    complete = len(capture.get("screenshots", [])) == len(NAMES) and set(records) == {name+".png" for name in NAMES}
    check("exact nine control comparison and panel captures exist", complete)
    if not complete:
        raise ValueError("Incomplete cloud tuning GPU capture")
    fingerprint = json.loads((destination / "runtime-fingerprint.json").read_text(encoding="utf-8"))
    identity = hashlib.sha256(json.dumps(fingerprint["files"], sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    check("GPU report binds the unchanged production runtime fingerprint",
          fingerprint.get("sha256") == identity == capture.get("runtime_fingerprint")
          and all(sha(ROOT / relative) == digest for relative, digest in fingerprint["files"].items()))
    for relative, digest in capture.get("source_files", {}).items():
        check("capture tool and runtime source unchanged: "+relative, sha(ROOT / relative.removeprefix("res://")) == digest)
    images = {}
    means = {}
    for name in NAMES:
        path = destination / (name+".png")
        record = records[path.name]
        size = [1280,720] if name.endswith("720") else [1920,1080]
        check(name+": original PNG hash and dimensions match", record.get("sha256") == sha(path) and record.get("size") == size)
        with Image.open(path) as source:
            image = source.convert("RGB")
        images[name] = image
        stats = ImageStat.Stat(image)
        means[name] = sum(stats.mean) / 3.0
        check(name+": read-back is a nonempty rendered scene", list(image.size) == size and min(stats.stddev) > 12.0)
    expected = {
        "cloud-tuning-default": (.30,.5), "cloud-tuning-contrast-low": (.10,.5),
        "cloud-tuning-contrast-zero": (0.0,.5), "cloud-tuning-density-zero": (.30,0.0),
        "cloud-tuning-density-full": (.30,1.0), "cloud-tuning-contrast-maximum": (.80,1.0),
        "cloud-tuning-panel-1080": (.30,.5), "cloud-tuning-panel-720": (.30,.5),
    }
    for name, (contrast, density) in expected.items():
        state = records[name+".png"]["state"]
        tuning = state["clouds"]["cloud_tuning"]
        check(name+": correct independent tuning values reached the captured scene",
              abs(tuning["contrast_strength"]-contrast)<1e-6 and abs(tuning["cloud_density"]-density)<1e-6)
        check(name+": independent clocks and maximum sunlight floor are preserved",
              state["clouds"]["clock_seconds"] == 0.0 and state["global_light"]["clock_seconds"] == 0.0
              and abs(tuning["hard_attenuation_cap"]-.80)<1e-6
              and abs(tuning["maximum_attenuation"]-contrast)<1e-6
              and abs(state["clouds"]["light_split"]["base_ratio"]-(1.0-contrast))<1e-6
              and abs(state["clouds"]["light_split"]["cloud_ratio"]-contrast)<1e-6
              and state["clouds"]["light_split"]["base_ratio"]>=.199999)
    baseline = images["cloud-tuning-default"]
    contrasts = {name: difference(baseline, images[name]) for name in (
        "cloud-tuning-contrast-low", "cloud-tuning-contrast-zero", "cloud-tuning-density-zero", "cloud-tuning-density-full", "cloud-tuning-contrast-maximum",
    )}
    for name, result in contrasts.items():
        check(name+": changing the slider changes actual scene pixels",
              result["mean_abs_rgb"]>.10 and result["pixels_luma_difference_above_2"]>1000)
    check("less contrast progressively brightens the same frozen cloud field",
          means["cloud-tuning-contrast-zero"]>means["cloud-tuning-contrast-low"]+.10
          and means["cloud-tuning-contrast-low"]>means["cloud-tuning-default"]+.10)
    check("full density darkens the same scene more than the default partial cloud field",
          means["cloud-tuning-default"]>means["cloud-tuning-density-full"]+.10)
    maximum_comparison = difference(images["cloud-tuning-density-full"], images["cloud-tuning-contrast-maximum"])
    check("the user-selected 80 percent maximum visibly darkens full clouds more than the default 30 percent setting",
          means["cloud-tuning-density-full"]>means["cloud-tuning-contrast-maximum"]+1.0
          and maximum_comparison["mean_abs_rgb"]>1.0 and maximum_comparison["pixels_luma_difference_above_2"]>10000)
    clear_equivalence = difference(images["cloud-tuning-contrast-zero"], images["cloud-tuning-density-zero"])
    check("zero contrast and zero density produce matching clear-cloud scene endpoints",
          clear_equivalence["mean_abs_rgb"]<.15 and clear_equivalence["pixels_luma_difference_above_2"]<5000)
    panel_difference = difference(baseline, images["cloud-tuning-panel-1080"])
    check("visible controls are rendered over the same scene",
          panel_difference["mean_abs_rgb"]>.50 and panel_difference["pixels_luma_difference_above_2"]>10000)
    for name in ("cloud-tuning-panel-1080", "cloud-tuning-panel-720", "cloud-tuning-input-720"):
        panel = records[name+".png"]["panel"]
        check(name+": both readable controls fit the viewport",
              panel.get("visible") is True and all(row.get("visible") is True and row.get("inside_viewport") is True and row.get("label_inside_viewport") is True
              and row["rect"][2]>=120 and row["rect"][3]>=20 and bool(row.get("label")) for row in panel["controls"].values()))
    pointer = capture["pointer_test"]
    check("actual pointer interaction changes the live production density",
          abs(pointer["after"]-pointer["before"])>10 and 10<=pointer["after"]<=40
          and abs(pointer["shader_value"]-pointer["after"]/100.0)<1e-6)
    pointer_pixels = difference(images["cloud-tuning-panel-720"], images["cloud-tuning-input-720"])
    check("actual mouse interaction produces a visibly different rendered frame",
          pointer_pixels["mean_abs_rgb"]>.10 and pointer_pixels["pixels_luma_difference_above_2"]>1000)
    failures = [row["label"] for row in checks if not row["passed"]]
    report = {"schema":1,"passed":not failures,"checks":checks,"failures":failures,
              "runtime_fingerprint":capture["runtime_fingerprint"],"capture_sha256":sha(capture_path),
              "source_files":{relative:sha(ROOT/relative) for relative in SOURCE_FILES},
              "mean_encoded_rgb":means,"default_comparisons":contrasts,
              "clear_endpoint_comparison":clear_equivalence,"panel_comparison":panel_difference,"maximum_contrast_comparison":maximum_comparison,
              "mouse_interaction_comparison":pointer_pixels,
              "scope":"Original tone-mapped scene PNG read-back and UI routing; encoded RGB differences are not physical transmission ratios."}
    (destination / "cloud-tuning-pixel-report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("CLOUD_TUNING_PIXELS "+json.dumps({"passed":report["passed"],"checks":len(checks),"failures":failures}))
    if failures:
        raise RuntimeError("Cloud tuning GPU pixel validation failed")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory",type=Path)
    validate(parser.parse_args().directory.resolve())
