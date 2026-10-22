#!/usr/bin/env python3
"""Validate original scene-settings GPU read-backs and complete source closure.

These are tone-mapped display-space comparisons. They establish visible live
effects and restored appearance, without claiming radiometric transmission or
real-time rendering performance.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops, ImageFilter, ImageStat

from atmosphere_workflow_profiles import SCENE_SETTINGS_SHOTS, SCENE_SETTINGS_SOURCES

ROOT = Path(__file__).resolve().parents[2]
SOURCE_FILES = (
    "scripts/forest_hamlet/scene.gd", "scripts/forest_hamlet/close_scene.gd",
    "scripts/forest_hamlet/scene_settings.gd", "scripts/forest_hamlet/settings_panel.gd",
    "scripts/forest_hamlet/cloud_lighting.gd", "scripts/forest_hamlet/global_lighting.gd",
    "scripts/forest_hamlet/actor.gd", "shaders/forest_hamlet/cloud_occluder.gdshader",
    "tests/forest_hamlet/scene_settings_runtime.gd",
    "tools/forest_hamlet/capture_scene_settings.gd", "tools/forest_hamlet/scene_settings_checks.py",
    "tools/forest_hamlet/run_scene_settings.py",
)
PARAMETERS = {
    "cloud_contrast", "cloud_density", "dof_amount", "dof_near_margin", "dof_near_transition",
    "dof_far_margin", "dof_far_transition", "glow_intensity", "glow_strength", "glow_bloom",
    "glow_hdr_threshold", "glow_hdr_scale", "exposure", "contrast", "saturation",
    "wind_strength", "parallax_strength", "fog_density_scale", "sun_variation", "ambient_variation",
}
FEATURES = {"normals", "bloom", "dof", "wind", "backdrop_normals", "parallax", "clouds", "atmosphere", "global_light"}
SECTIONS = {
    "environment": {"exposure", "contrast", "saturation", "fog_density_scale"},
    "dof": {"dof_amount", "dof_near_margin", "dof_near_transition", "dof_far_margin", "dof_far_transition"},
    "glow": {"glow_intensity", "glow_strength", "glow_bloom", "glow_hdr_threshold", "glow_hdr_scale"},
    "clouds": {"cloud_contrast", "cloud_density", "sun_variation", "ambient_variation"},
    "other": {"wind_strength", "parallax_strength"},
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_identity(files: dict[str, str]) -> str:
    return hashlib.sha256(json.dumps(files, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def equivalent(left: Any, right: Any) -> bool:
    if isinstance(left, bool) or isinstance(right, bool):
        return type(left) is type(right) and left == right
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return math.isclose(left, right, rel_tol=1e-5, abs_tol=1e-6)
    if isinstance(left, dict) and isinstance(right, dict):
        return left.keys() == right.keys() and all(equivalent(value, right[key]) for key, value in left.items())
    if isinstance(left, list) and isinstance(right, list):
        return len(left) == len(right) and all(equivalent(a, b) for a, b in zip(left, right))
    return type(left) is type(right) and left == right


def fingerprint(destination: Path, filename: str) -> dict:
    result = json.loads((destination / filename).read_text(encoding="utf-8"))
    files = result.get("files")
    if result.get("schema") != 1 or not isinstance(files, dict) or not files or result.get("sha256") != canonical_identity(files):
        raise ValueError("Invalid canonical fingerprint: " + filename)
    for relative, expected in files.items():
        path = Path(relative)
        if path.is_absolute() or ".." in path.parts or "\\" in relative or path.as_posix() != relative:
            raise ValueError("Unsafe fingerprint source path: " + relative)
        source = ROOT / relative
        source.resolve(strict=True).relative_to(ROOT)
        if source.is_symlink() or sha(source) != expected:
            raise ValueError("Source changed after verification: " + relative)
    return result


def bound_reports(destination: Path, reports: list[dict]) -> tuple[dict, dict]:
    runtime = fingerprint(destination, "runtime-fingerprint.json")
    sources = fingerprint(destination, "source-fingerprint.json")
    required = set(SOURCE_FILES) | set(SCENE_SETTINGS_SOURCES) | set(runtime["files"])
    if not required <= set(sources["files"]):
        raise ValueError("Source fingerprint omits runtime, settings, validation or workflow sources")
    if any(sources["files"][name] != value for name, value in runtime["files"].items()):
        raise ValueError("Runtime and source fingerprints bind different production bytes")
    for report in reports:
        if report.get("runtime_fingerprint") != runtime["sha256"] or report.get("source_fingerprint") != sources["sha256"]:
            raise ValueError("Reports do not bind the same current runtime and validation sources")
        if not set(SOURCE_FILES) <= set(report.get("source_files", {})):
            raise ValueError("Report omits its live scene or validation source provenance")
        for name, value in report["source_files"].items():
            if sources["files"].get(name) != value:
                raise ValueError("Report source differs from complete source closure: " + name)
    return runtime, sources


def passed_report(report: dict) -> bool:
    return (report.get("schema") == 1 and report.get("passed") is True and not report.get("failures")
            and bool(report.get("checks")) and all(row.get("passed") is True for row in report["checks"]))


def complete_profile(profile: dict) -> bool:
    return (profile.get("schema_version") == 2 and profile.get("time_preset") in {"day", "dusk"}
            and set(profile.get("features", {})) == FEATURES
            and all(type(value) is bool for value in profile["features"].values())
            and set(profile.get("parameters", {})) == PARAMETERS
            and all(type(value) in {int, float} and math.isfinite(value) for value in profile["parameters"].values()))


def validate_runtime(destination: Path) -> dict:
    """Require saved/startup results and a completed physical route, not just exit 0."""
    report = json.loads((destination / "scene-settings-runtime-report.json").read_text(encoding="utf-8"))
    if not passed_report(report):
        raise RuntimeError("Scene-settings runtime contracts failed: " + repr(report.get("failures")))
    bound_reports(destination, [report])
    selected = report.get("selected", {})
    if (not complete_profile(selected) or selected.get("time_preset") != "dusk"
            or not equivalent(report.get("restored", {}).get("settings"), selected)
            or not equivalent(report.get("startup", {}).get("settings"), selected)):
        raise RuntimeError("Runtime evidence does not establish complete saved and startup restoration")
    route = report.get("route", {})
    if (route.get("completed") is not True or route.get("waypoints") != 6 or route.get("total_waypoints") != 6
            or route.get("elapsed_seconds", 0) <= 0 or len(route.get("samples", [])) <= 30
            or report.get("minimum_route_height", -math.inf) <= -.5):
        raise RuntimeError("Runtime evidence lacks the complete original six-waypoint physical route")
    if report.get("settings_sha256") != sha(destination / "isolated-scene-settings.cfg"):
        raise RuntimeError("Runtime settings fixture differs from the profile that was restored")
    return report


def difference(a: Image.Image, b: Image.Image) -> dict:
    delta = ImageChops.difference(a, b)
    stats = ImageStat.Stat(delta)
    histogram = delta.convert("L").histogram()
    return {"mean_abs_rgb": sum(stats.mean) / 3.0,
            "pixels_luma_difference_above_2": sum(histogram[3:]), "pixel_count": a.width * a.height}


def edge_energy(image: Image.Image) -> float:
    # Exclude FIND_EDGES' retained one-pixel image border from the measurement.
    edges = image.convert("L").filter(ImageFilter.FIND_EDGES)
    return ImageStat.Stat(edges.crop((2, 2, image.width - 2, image.height - 2))).mean[0]


def same_except_parameter(left: dict, right: dict, parameter: str) -> bool:
    left = {**left, "parameters": {key: value for key, value in left["parameters"].items() if key != parameter}}
    right = {**right, "parameters": {key: value for key, value in right["parameters"].items() if key != parameter}}
    return equivalent(left, right)


def usable_control(row: dict) -> bool:
    return (row.get("visible") is True and row.get("inside_viewport") is True and row.get("inside_clip") is True
            and row.get("label_inside_viewport") is True and row.get("label_inside_clip") is True
            and row.get("rect", [0, 0, 0, 0])[2] >= 120 and row.get("rect", [0, 0, 0, 0])[3] >= 20
            and bool(row.get("label")))


def validate(destination: Path) -> dict:
    runtime = validate_runtime(destination)
    capture_path = destination / "scene-settings-gpu-report.json"
    capture = json.loads(capture_path.read_text(encoding="utf-8"))
    runtime_identity, source_identity = bound_reports(destination, [runtime, capture])
    checks = []

    def check(label: str, condition: bool) -> None:
        checks.append({"label": label, "passed": bool(condition)})

    check("runtime controls persistence startup and full original physics route passed", passed_report(runtime))
    check("every capture contract ran on actual Forward Plus hardware",
          passed_report(capture) and capture.get("gpu") is True and capture.get("renderer") == "forward_plus"
          and bool(capture.get("adapter")))
    records = {row["file"]: row for row in capture.get("screenshots", [])}
    complete = len(capture.get("screenshots", [])) == len(SCENE_SETTINGS_SHOTS) and set(records) == set(SCENE_SETTINGS_SHOTS)
    check("exact fifteen original effect persistence section and input frames exist", complete)
    if not complete:
        raise ValueError("Incomplete scene-settings GPU capture")
    images: dict[str, Image.Image] = {}
    means: dict[str, float] = {}
    originals = []
    for filename, size in SCENE_SETTINGS_SHOTS.items():
        path = destination / filename
        record = records[filename]
        digest = sha(path)
        check(filename + ": original PNG hash and dimensions match", record.get("sha256") == digest and record.get("size") == size)
        with Image.open(path) as source:
            image = source.convert("RGB")
        images[filename] = image
        statistics = ImageStat.Stat(image)
        means[filename] = sum(statistics.mean) / 3.0
        check(filename + ": read-back contains a nonempty rendered scene", list(image.size) == size and min(statistics.stddev) > 10.0)
        originals.append({"file": filename, "sha256": digest, "size": list(image.size)})
        settings = record.get("settings", {})
        state = record["state"]
        motion = record["motion"]
        check(filename + ": captured profile is complete", complete_profile(settings))
        check(filename + ": camera actor and independent clocks stay fixed",
              state["framing"]["in_frame"] is True
              and .22 < state["framing"]["silhouette_rect"][3] < .24
              and abs(state["framing"]["pitch_degrees"] - 14.0) < .1
              and equivalent(state["framing"]["fov"], 39.0)
              and equivalent(state["framing"]["pixel_size"], .009)
              and state["clouds"]["clock_seconds"] == 0.0 and state["global_light"]["clock_seconds"] == 0.0
              and motion["comparison_frozen"] is True and motion["scene_clock_paused"] is True
              and motion["actor_physics_paused"] is True and abs(motion["wind_strength"]) < 1e-8
              and abs(motion["water_flow_speed"]) < 1e-8)
        native = record["native_effects"]
        check(filename + ": unchanged actor depth stays strictly inside the edited focus interval",
              native["dof_near"] < state["framing"]["view_depth"] < native["dof_far"])

    def frame(name: str) -> dict:
        return records["scene-settings-" + name + ".png"]

    def pixels(name: str) -> Image.Image:
        return images["scene-settings-" + name + ".png"]

    dof_off, dof_strong = frame("dof-off"), frame("dof-strong")
    check("DOF endpoints isolate the actual amount slider with the same camera lights and scene settings",
          same_except_parameter(dof_off["settings"], dof_strong["settings"], "dof_amount")
          and equivalent(dof_off["native_effects"]["dof_amount"], 0.0)
          and equivalent(dof_strong["native_effects"]["dof_amount"], .25)
          and dof_off["native_effects"]["dof_near_enabled"] is True and dof_strong["native_effects"]["dof_far_enabled"] is True
          and equivalent(dof_off["state"]["camera"], dof_strong["state"]["camera"])
          and equivalent(dof_off["state"]["player"], dof_strong["state"]["player"]))
    dof_difference = difference(pixels("dof-off"), pixels("dof-strong"))
    dof_edges = {"off": edge_energy(pixels("dof-off")), "strong": edge_energy(pixels("dof-strong"))}
    check("increasing the live DOF amount changes thousands of actual scene pixels",
          dof_difference["mean_abs_rgb"] > .10 and dof_difference["pixels_luma_difference_above_2"] > 5000)
    check("strong DOF reduces rendered edge detail outside the protected actor depth plane", dof_edges["strong"] < dof_edges["off"] * .98)
    glow_off, glow_strong = frame("glow-off"), frame("glow-strong")
    check("Glow endpoints isolate the actual intensity slider at the same dusk lighting",
          same_except_parameter(glow_off["settings"], glow_strong["settings"], "glow_intensity")
          and glow_off["settings"]["time_preset"] == "dusk"
          and equivalent(glow_off["native_effects"]["glow_intensity"], 0.0)
          and equivalent(glow_strong["native_effects"]["glow_intensity"], 1.6)
          and glow_off["native_effects"]["glow_enabled"] is True and glow_strong["native_effects"]["glow_enabled"] is True)
    glow_difference = difference(pixels("glow-off"), pixels("glow-strong"))
    check("increasing live Glow intensity produces a brighter visibly different hardware frame",
          glow_difference["mean_abs_rgb"] > .10 and glow_difference["pixels_luma_difference_above_2"] > 5000
          and means["scene-settings-glow-strong.png"] > means["scene-settings-glow-off.png"] + .10)
    saved, restored = frame("dusk-saved"), frame("dusk-restored")
    check("fresh restoration keeps the complete saved dusk profile and native DOF Glow outputs",
          equivalent(capture["saved_settings"], capture["restored_settings"])
          and equivalent(saved["settings"], restored["settings"])
          and equivalent(saved["native_effects"], restored["native_effects"])
          and saved["settings"]["time_preset"] == restored["settings"]["time_preset"] == "dusk"
          and capture.get("settings_sha256") == sha(destination / "isolated-gpu-scene-settings.cfg"))
    restored_difference = difference(pixels("dusk-saved"), pixels("dusk-restored"))
    check("saved and freshly restored dusk produce matching actual scene appearance",
          restored_difference["mean_abs_rgb"] < .35
          and restored_difference["pixels_luma_difference_above_2"] < restored_difference["pixel_count"] * .02)
    for section, identifiers in SECTIONS.items():
        panel = frame("panel-" + section + "-1080")["panel"]
        check(section + ": correct complete control group is captured in its own section",
              panel["section"] == section and set(panel["controls"]) == identifiers
              and panel["visible"] is True and panel["panel_inside_viewport"] is True
              and any(usable_control(row) for row in panel["controls"].values()))
        check(section + ": save load reset and both presets remain visible outside scrolling",
              set(panel["actions"]) == {"save", "load", "reset", "day", "dusk"}
              and all(row["visible"] is True and row["inside_viewport"] is True and row["text"] for row in panel["actions"].values()))
    pointer_records = {row["control"]: row for row in capture.get("pointer_tests", [])}
    check("actual viewport mouse tests cover both DOF and Glow", len(capture.get("pointer_tests", [])) == 2 and set(pointer_records) == {"dof_amount", "glow_intensity"})
    pointer_differences = {}
    for section, control in (("dof", "dof_amount"), ("glow", "glow_intensity")):
        before, after = frame("panel-" + section + "-720"), frame("input-" + section + "-720")
        check(section + ": the edited control and value label are actually inside the 720p scroll clip",
              all(row["panel"]["panel_inside_viewport"] is True and usable_control(row["panel"]["controls"][control]) for row in (before, after)))
        pointer = pointer_records.get(control, {})
        check(section + ": mouse movement reaches the corresponding native camera or environment value",
              abs(pointer.get("after", 0) - pointer.get("before", 0)) > pointer.get("step", 1) * 2
              and equivalent(pointer.get("after"), pointer.get("native_value"))
              and equivalent(pointer.get("native_value"), after["native_effects"][control])
              and equivalent(pointer.get("after"), after["settings"]["parameters"][control]))
        result = difference(pixels("panel-" + section + "-720"), pixels("input-" + section + "-720"))
        pointer_differences[section] = result
        check(section + ": actual mouse editing changes the captured rendered frame",
              result["mean_abs_rgb"] > .05 and result["pixels_luma_difference_above_2"] > 1000)
    failures = [row["label"] for row in checks if not row["passed"]]
    report = {
        "schema": 1, "passed": not failures, "checks": checks, "failures": failures,
        "runtime_fingerprint": runtime_identity["sha256"], "source_fingerprint": source_identity["sha256"],
        "source_files": {relative: sha(ROOT / relative) for relative in SOURCE_FILES},
        "capture_sha256": sha(capture_path), "runtime_report_sha256": sha(destination / "scene-settings-runtime-report.json"),
        "original_pngs": originals, "mean_encoded_rgb": means,
        "dof_comparison": dof_difference, "dof_edge_energy": dof_edges, "glow_comparison": glow_difference,
        "saved_restored_comparison": restored_difference, "pointer_comparisons": pointer_differences,
        "scope": "Original tone-mapped Forward+ PNG read-back, complete persisted settings, real GUI routing and complete runtime/validation/workflow source hashes; display RGB differences are not physical radiometry or real-time FPS measurements.",
    }
    (destination / "scene-settings-pixel-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("SCENE_SETTINGS_PIXELS " + json.dumps({"passed": report["passed"], "checks": len(checks), "failures": failures}))
    if failures:
        raise RuntimeError("Scene-settings GPU pixel validation failed")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    validate(parser.parse_args().directory.resolve())
