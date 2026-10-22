"""Explicit validation scopes for immutable atmosphere workflow revisions.

The original atmosphere profile retains its full r3 evidence contract. The
cloud-tuning profile records new UI/control evidence without claiming that its
focused captures reran the earlier physical-route or radiometry experiments.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from PIL import Image

from register_vgp import digest


TUNING_SOURCES = (
    "tests/forest_hamlet/cloud_tuning_runtime.gd",
    "tools/forest_hamlet/capture_cloud_tuning.gd",
    "tools/forest_hamlet/cloud_tuning_checks.py",
    "tools/forest_hamlet/run_cloud_tuning.py",
    "tools/forest_hamlet/atmosphere_workflow_profiles.py",
)
TUNING_REPORTS = (
    "cloud-tuning-runtime-report.json",
    "cloud-tuning-gpu-report.json",
    "cloud-tuning-pixel-report.json",
)
TUNING_SHOTS = {
    "cloud-tuning-default.png": [1920, 1080],
    "cloud-tuning-contrast-low.png": [1920, 1080],
    "cloud-tuning-contrast-zero.png": [1920, 1080],
    "cloud-tuning-density-zero.png": [1920, 1080],
    "cloud-tuning-density-full.png": [1920, 1080],
    "cloud-tuning-contrast-maximum.png": [1920, 1080],
    "cloud-tuning-panel-1080.png": [1920, 1080],
    "cloud-tuning-panel-720.png": [1280, 720],
    "cloud-tuning-input-720.png": [1280, 720],
}


def profile_spec(profile: str) -> dict:
    if profile == "atmosphere":
        return {
            "run_id": "forest-hamlet-20261022-atmosphere-r3",
            "snapshot_id": "atmosphere-native-r3",
            "config": "art/inputs/forest-hamlet/atmosphere-r3/workbench-project.yaml",
            "evidence_dir": "build/forest-hamlet/atmosphere-r3-final",
            "test_id": "atmosphere-runtime",
            "test_script": "tests/forest_hamlet/atmosphere_runtime.gd",
            "artifact": "atmosphere-runtime-report.json",
            "marker": "ATMOSPHERE_RUNTIME_DONE passed=true",
            "extra_sources": (),
        }
    if profile == "cloud-tuning":
        return {
            "run_id": "forest-hamlet-20261022-cloud-tuning-r4",
            "snapshot_id": "cloud-tuning-native-r4",
            "config": "art/inputs/forest-hamlet/cloud-tuning-r4/workbench-project.yaml",
            "evidence_dir": "build/forest-hamlet/cloud-tuning-r4-final",
            "test_id": "cloud-tuning-runtime",
            "test_script": "tests/forest_hamlet/cloud_tuning_runtime.gd",
            "artifact": "cloud-tuning-runtime-report.json",
            "marker": "CLOUD_TUNING_RUNTIME_DONE passed=true",
            "extra_sources": TUNING_SOURCES,
        }
    raise ValueError("Unknown atmosphere workflow profile: " + profile)


def native_test_spec(profile: str) -> dict:
    spec = profile_spec(profile)
    return {"id": spec["test_id"], "script": spec["test_script"], "render": False,
            "args": [], "require": [spec["marker"]], "artifacts": [spec["artifact"]]}


def cloud_tuning_evidence(root: Path, destination: Path) -> tuple[list[Path], dict]:
    """Require passed, source-bound, actual GPU UI evidence for this revision."""
    paths = []
    reports = {}
    for name in TUNING_REPORTS:
        path = destination / name
        report = json.loads(path.read_text(encoding="utf-8"))
        if (report.get("schema") != 1 or report.get("passed") is not True
                or not report.get("checks") or report.get("failures")
                or not all(row.get("passed") is True for row in report["checks"])):
            raise RuntimeError("Focused cloud tuning report has not passed: " + name)
        paths.append(path)
        reports[name] = report
    capture = reports[TUNING_REPORTS[1]]
    pixels = reports[TUNING_REPORTS[2]]
    if (capture.get("gpu") is not True or capture.get("renderer") != "forward_plus"
            or not capture.get("adapter")):
        raise RuntimeError("Focused cloud tuning evidence needs the actual Forward+ GPU")
    if pixels.get("capture_sha256") != digest(destination / TUNING_REPORTS[1]):
        raise RuntimeError("Focused pixel checks do not bind the original GPU capture report")
    fingerprint_path = destination / "runtime-fingerprint.json"
    fingerprint = json.loads(fingerprint_path.read_text(encoding="utf-8"))
    canonical = json.dumps(fingerprint["files"], sort_keys=True, separators=(",", ":")).encode()
    if hashlib.sha256(canonical).hexdigest() != fingerprint["sha256"]:
        raise RuntimeError("Cloud tuning runtime fingerprint identity differs")
    for report in reports.values():
        if report.get("runtime_fingerprint") != fingerprint["sha256"]:
            raise RuntimeError("Cloud tuning reports describe different runtime sources")
    for name, expected in fingerprint["files"].items():
        path = (root / name).resolve(strict=True)
        path.relative_to(root)
        if digest(path) != expected:
            raise RuntimeError("Runtime changed after cloud tuning verification: " + name)
    # Runtime and GPU reports bind their test/capture sources separately because
    # the shared scene fingerprint deliberately contains only runtime assets.
    bound_sources = {}
    for report in reports.values():
        for name, expected in report.get("source_files", {}).items():
            normalized = name.removeprefix("res://")
            path = (root / normalized).resolve(strict=True)
            path.relative_to(root)
            if digest(path) != expected:
                raise RuntimeError("Cloud tuning validation source changed: " + normalized)
            bound_sources[normalized] = expected
    required_validation = set(TUNING_SOURCES) - {"tools/forest_hamlet/atmosphere_workflow_profiles.py"}
    if not required_validation <= set(bound_sources):
        raise RuntimeError("Focused report source provenance omits its runtime/capture/check/runner sources")
    shots = capture.get("screenshots", [])
    if len(shots) != len(TUNING_SHOTS) or {row.get("file") for row in shots} != set(TUNING_SHOTS):
        raise RuntimeError("Focused GPU evidence must contain the exact nine original tuning/UI frames")
    for row in shots:
        path = destination / row["file"]
        if row.get("size") != TUNING_SHOTS[row["file"]] or digest(path) != row["sha256"]:
            raise RuntimeError("Cloud tuning original PNG hash or dimensions differ: " + row["file"])
        with Image.open(path) as image:
            if list(image.size) != row["size"]:
                raise RuntimeError("Cloud tuning decoded PNG dimensions differ: " + row["file"])
        paths.append(path)
    make_path = destination / "make-test-report.json"
    make_report = json.loads(make_path.read_text(encoding="utf-8"))
    if make_report.get("passed") is not True or make_report.get("returncode", 0) != 0:
        raise RuntimeError("The current project make test gate has not passed")
    paths.extend([fingerprint_path, make_path])
    return paths, {
        "profile": "cloud-tuning", "runtime_fingerprint": fingerprint["sha256"],
        "capture_directory": destination.relative_to(root).as_posix(),
        "report_count": len(TUNING_REPORTS), "screenshot_count": len(shots),
        "total_original_png_count": len(shots), "complete_final_evidence": True,
        "gpu_checks": len(capture["checks"]), "pixel_checks": len(pixels["checks"]),
        "runtime_checks": len(reports[TUNING_REPORTS[0]]["checks"]),
        "report_paths": [(destination / name).relative_to(root).as_posix() for name in TUNING_REPORTS],
        "scope": "Focused live contrast from 0 to 80 percent attenuation (default 30), independent density, preserved default thin 10/thick 30 behavior, dynamic native sun branches retaining at least 20 percent sunlight, settings persistence and real panel input/layout at 1080p and 720p; prior physical-route and calibrated radiometry evidence remains historical r3 evidence and is not claimed as rerun here.",
    }
