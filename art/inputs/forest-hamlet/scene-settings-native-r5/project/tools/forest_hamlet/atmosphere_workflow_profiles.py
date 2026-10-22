"""Explicit validation scopes for immutable atmosphere workflow revisions.

The original atmosphere profile retains its full r3 evidence contract. The
cloud-tuning profile records new UI/control evidence without claiming that its
focused captures reran the earlier physical-route or radiometry experiments.
The scene-settings successor binds its complete runtime and verification source
closure and requires the original r4 asset set to remain byte-identical.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from PIL import Image

def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


PROFILE_NAMES = ("atmosphere", "cloud-tuning", "scene-settings")
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
SCENE_SETTINGS_VALIDATION_SOURCES = (
    "tests/forest_hamlet/scene_settings_runtime.gd",
    "tools/forest_hamlet/capture_scene_settings.gd",
    "tools/forest_hamlet/scene_settings_checks.py",
    "tools/forest_hamlet/run_scene_settings.py",
)
SCENE_SETTINGS_WORKFLOW_SOURCES = (
    "tools/forest_hamlet/atmosphere_workflow_profiles.py",
    "tools/forest_hamlet/process_atmosphere_aw.py",
    "tools/forest_hamlet/register_atmosphere_vgp.py",
    "tools/forest_hamlet/verify_atmosphere_godot_aw.py",
    "tools/forest_hamlet/archive_cloud_tuning_evidence.py",
    "tools/forest_hamlet/register_vgp.py",
)
SCENE_SETTINGS_SHARED_SOURCES = (
    "tools/project.py",
    "tools/forest_hamlet/run.py",
    "tools/forest_hamlet/capture.gd",
)
SCENE_SETTINGS_SOURCES = (
    "scripts/forest_hamlet/scene_settings.gd",
    "scripts/forest_hamlet/settings_panel.gd",
    *SCENE_SETTINGS_VALIDATION_SOURCES, *SCENE_SETTINGS_WORKFLOW_SOURCES,
    *SCENE_SETTINGS_SHARED_SOURCES,
)
SCENE_SETTINGS_REPORTS = (
    "scene-settings-runtime-report.json",
    "scene-settings-gpu-report.json",
    "scene-settings-pixel-report.json",
)
SCENE_SETTINGS_SHOTS = {
    **{name + ".png": [1920, 1080] for name in (
        "scene-settings-dof-off", "scene-settings-dof-strong",
        "scene-settings-glow-off", "scene-settings-glow-strong",
        "scene-settings-dusk-saved", "scene-settings-dusk-restored",
        "scene-settings-panel-environment-1080", "scene-settings-panel-dof-1080",
        "scene-settings-panel-glow-1080", "scene-settings-panel-clouds-1080",
        "scene-settings-panel-other-1080",
    )},
    **{name + ".png": [1280, 720] for name in (
        "scene-settings-panel-dof-720", "scene-settings-input-dof-720",
        "scene-settings-panel-glow-720", "scene-settings-input-glow-720",
    )},
}
SCENE_SETTINGS_PREDECESSOR = "forest-hamlet-20261022-cloud-tuning-r4"
SCENE_SETTINGS_ASSET_BASELINE = "art/inputs/forest-hamlet/cloud-tuning-native-r4/snapshot.json"


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
    if profile == "scene-settings":
        return {
            "run_id": "forest-hamlet-20261022-scene-settings-r5",
            "snapshot_id": "scene-settings-native-r5",
            "config": "art/inputs/forest-hamlet/scene-settings-r5/workbench-project.yaml",
            "evidence_dir": "build/forest-hamlet/scene-settings-r5-final",
            "test_id": "scene-settings-runtime",
            "test_script": "tests/forest_hamlet/scene_settings_runtime.gd",
            "artifact": "scene-settings-runtime-report.json",
            "marker": "SCENE_SETTINGS_RUNTIME_DONE passed=true",
            "extra_sources": SCENE_SETTINGS_SOURCES,
            "extra_evidence": ("docs/forest-hamlet/scene-settings-r5.md",),
            "previous_run_id": SCENE_SETTINGS_PREDECESSOR,
            "archive_dir": "docs/forest-hamlet/revisions/scene-settings-r5-20261022",
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


def _verified_fingerprint(root: Path, path: Path) -> dict:
    fingerprint = json.loads(path.read_text(encoding="utf-8"))
    files = fingerprint.get("files")
    if fingerprint.get("schema") != 1 or not isinstance(files, dict) or not files:
        raise RuntimeError("Scene settings fingerprint needs a nonempty versioned file map")
    canonical = json.dumps(files, sort_keys=True, separators=(",", ":")).encode()
    if hashlib.sha256(canonical).hexdigest() != fingerprint.get("sha256"):
        raise RuntimeError("Scene settings fingerprint identity differs: " + path.name)
    for name, expected in files.items():
        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts or "\\" in name or relative.as_posix() != name:
            raise RuntimeError("Unsafe scene settings fingerprint source: " + name)
        source = root / name
        source.resolve(strict=True).relative_to(root)
        if source.is_symlink() or not source.is_file() or digest(source) != expected:
            raise RuntimeError("Source changed after scene settings verification: " + name)
    return fingerprint


def _scene_settings_original_assets(root: Path) -> tuple[list[Path], dict]:
    """Compare every original runtime asset with the immutable r4 snapshot."""
    snapshot_path = root / SCENE_SETTINGS_ASSET_BASELINE
    previous_path = root / "art/derived/forest-hamlet" / SCENE_SETTINGS_PREDECESSOR / "native-godot/summary.json"
    previous = json.loads(previous_path.read_text(encoding="utf-8"))
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    if (previous.get("profile") != "cloud-tuning" or previous.get("execution_status") != "completed"
            or previous.get("snapshot") != SCENE_SETTINGS_ASSET_BASELINE
            or previous.get("snapshot_sha256") != digest(snapshot_path)):
        raise RuntimeError("Original asset baseline must bind the completed immutable r4 native snapshot")
    rows = snapshot.get("files", [])
    identity = {row["source"]: row["sha256"] for row in rows}
    sha256 = hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if (len(rows) != len(identity) or len(rows) != snapshot.get("file_count")
            or sha256 != snapshot.get("sha256") or sha256 != previous.get("source_closure_sha256")):
        raise RuntimeError("The original r4 snapshot file identity differs")
    assets = {row["source"]: row for row in rows if row["source"].startswith("assets/")}
    observed = {path.relative_to(root).as_posix() for path in (root / "assets").rglob("*")
                if path.is_file() or path.is_symlink()}
    if not assets or set(assets) != observed:
        raise RuntimeError("The original r4 runtime asset file set changed")
    for name, row in assets.items():
        source = root / name
        source.resolve(strict=True).relative_to(root)
        if source.is_symlink() or digest(source) != row["sha256"] or source.stat().st_size != row["bytes"]:
            raise RuntimeError("An original r4 runtime asset changed: " + name)
    asset_identity = {name: row["sha256"] for name, row in assets.items()}
    asset_sha256 = hashlib.sha256(json.dumps(asset_identity, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return [snapshot_path, previous_path], {
        "passed": True, "predecessor_run_id": SCENE_SETTINGS_PREDECESSOR,
        "baseline_snapshot": SCENE_SETTINGS_ASSET_BASELINE, "baseline_snapshot_sha256": digest(snapshot_path),
        "baseline_summary": previous_path.relative_to(root).as_posix(), "baseline_summary_sha256": digest(previous_path),
        "file_count": len(assets), "total_bytes": sum(row["bytes"] for row in assets.values()),
        "assets_sha256": asset_sha256,
        "scope": "Exact assets/** file set, SHA256 and byte count against the completed r4 native snapshot; original character frames, normals, masks, models, terrain, vegetation and backdrop are unchanged.",
    }


def scene_settings_evidence(root: Path, destination: Path) -> tuple[list[Path], dict]:
    """Require complete real GPU evidence for the new settings contract."""
    paths, reports = [], {}
    for name in SCENE_SETTINGS_REPORTS:
        path = destination / name
        report = json.loads(path.read_text(encoding="utf-8"))
        if (report.get("schema") != 1 or report.get("passed") is not True or not report.get("checks")
                or report.get("failures") or not all(row.get("passed") is True for row in report["checks"])):
            raise RuntimeError("Scene settings report has not passed: " + name)
        paths.append(path)
        reports[name] = report
    capture, pixels = reports[SCENE_SETTINGS_REPORTS[1]], reports[SCENE_SETTINGS_REPORTS[2]]
    if (capture.get("gpu") is not True or capture.get("renderer") != "forward_plus" or not capture.get("adapter")
            or capture.get("preview_only") is True):
        raise RuntimeError("Scene settings evidence requires the actual Forward+ GPU")
    if pixels.get("capture_sha256") != digest(destination / SCENE_SETTINGS_REPORTS[1]):
        raise RuntimeError("Scene settings pixel checks do not bind the original GPU report")
    runtime_path, source_path = destination / "runtime-fingerprint.json", destination / "source-fingerprint.json"
    runtime = _verified_fingerprint(root, runtime_path)
    source = _verified_fingerprint(root, source_path)
    if (not set(SCENE_SETTINGS_SOURCES) <= set(source["files"])
            or not all(source["files"].get(name) == sha256 for name, sha256 in runtime["files"].items())):
        raise RuntimeError("Scene settings source fingerprint omits runtime or validation/workflow sources")
    bound_sources = set()
    for report in reports.values():
        if (report.get("runtime_fingerprint") != runtime["sha256"]
                or report.get("source_fingerprint") != source["sha256"]):
            raise RuntimeError("Scene settings reports describe different runtime or verification sources")
        for name, sha256 in report.get("source_files", {}).items():
            name = name.removeprefix("res://")
            if source["files"].get(name) != sha256:
                raise RuntimeError("Scene settings report source differs from the complete fingerprint: " + name)
            bound_sources.add(name)
    if not set(SCENE_SETTINGS_VALIDATION_SOURCES) <= bound_sources:
        raise RuntimeError("Scene settings reports omit runtime/capture/check/runner source provenance")
    shots, pixel_shots = capture.get("screenshots", []), pixels.get("original_pngs", [])
    for rows in (shots, pixel_shots):
        if len(rows) != len(SCENE_SETTINGS_SHOTS) or {row.get("file") for row in rows} != set(SCENE_SETTINGS_SHOTS):
            raise RuntimeError("Scene settings evidence must contain the exact fifteen original effect/UI frames")
    pixel_hashes = {row["file"]: row["sha256"] for row in pixel_shots}
    for row in shots:
        path = destination / row["file"]
        if (row.get("size") != SCENE_SETTINGS_SHOTS[row["file"]]
                or digest(path) != row["sha256"] or pixel_hashes[row["file"]] != row["sha256"]):
            raise RuntimeError("Scene settings original PNG identity differs: " + row["file"])
        with Image.open(path) as image:
            if image.format != "PNG" or list(image.size) != row["size"]:
                raise RuntimeError("Scene settings decoded PNG dimensions/format differ: " + row["file"])
        paths.append(path)
    make_path = destination / "make-test-report.json"
    make_report = json.loads(make_path.read_text(encoding="utf-8"))
    if make_report.get("passed") is not True or make_report.get("returncode", 0) != 0:
        raise RuntimeError("The current project make test gate has not passed")
    baseline_paths, original_assets = _scene_settings_original_assets(root)
    paths.extend([runtime_path, source_path, make_path, *baseline_paths])
    return paths, {
        "profile": "scene-settings", "runtime_fingerprint": runtime["sha256"],
        "source_fingerprint": source["sha256"], "source_fingerprint_file_count": len(source["files"]),
        "capture_directory": destination.relative_to(root).as_posix(),
        "report_count": len(SCENE_SETTINGS_REPORTS), "screenshot_count": len(shots),
        "total_original_png_count": len(shots), "complete_final_evidence": True,
        "gpu_checks": len(capture["checks"]), "pixel_checks": len(pixels["checks"]),
        "runtime_checks": len(reports[SCENE_SETTINGS_REPORTS[0]]["checks"]),
        "report_paths": [(destination / name).relative_to(root).as_posix() for name in SCENE_SETTINGS_REPORTS],
        "original_assets": original_assets,
        "scope": "Focused live scene settings: native DOF and Glow numeric controls, day/dusk, environment, clouds and other existing effect parameters; full-profile save/load/reset and fresh-start restore, read-only migration of legacy 70 percent contrast / 48 percent density, real mouse/keyboard input and five-section panel layouts at 1080p and 720p. Exact runtime and verification-source fingerprints and original r4 asset preservation are required. The dedicated runtime suite records its own physical-route regression; earlier GPU route captures and calibrated radiometry remain historical. No human aesthetic approval is created.",
    }
