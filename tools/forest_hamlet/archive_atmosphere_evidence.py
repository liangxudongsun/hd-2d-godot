#!/usr/bin/env python3
"""Archive verified final atmosphere evidence without rerunning Godot or editing images.

All required reports, current runtime bytes, PNGs and native AW/VGP receipts
must agree before any archive files are written. A repeated identical archive
is allowed; differing historical files are never overwritten. README is owned
by the scene author and is not changed here.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import stat
import struct
import sys
import tempfile
import zipfile


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RUN = "forest-hamlet-20261022-atmosphere-r3"
SOURCE_SHA256 = "fa11b07fc545379570c1a86f8f5c70a5d5fe01c38aa4ffd2306ad6c5d381ce8c"
REPORT_NAMES = (
    "atmosphere-assets-report.json", "atmosphere-runtime-report.json",
    "atmosphere-gpu-report.json", "atmosphere-gpu-pixel-report.json",
)
PROBE_DIRECTORY = "cloud-transmission"
PROBE_REPORT_NAMES = ("cloud-transmission-capture.json", "cloud-transmission-pixel-report.json")
PROBE_SCREENSHOTS = {
    "cloud-direct-dark.png", "cloud-direct-clear.png", "cloud-direct-half-calibration.png",
    "cloud-direct-uniform-clear.png", "cloud-direct-thin.png", "cloud-direct-thin-repeat.png",
    "cloud-direct-thick.png", "cloud-direct-natural.png",
}
SCREENSHOTS = {
    "close-day-clouds-a.png", "close-day-clouds-off.png", "close-day-clouds-b.png",
    "close-day-glow-off.png", "close-day-atmosphere-off.png", "close-dusk-atmosphere.png",
    "close-route-left.png", "close-route-right.png", "snow-left-normals-on.png",
    "snow-left-normals-off.png", "snow-right-normals-on.png", "snow-right-normals-off.png",
    "close-day-global-weak.png", "close-day-global-strong.png", "close-day-global-off.png",
    "close-day-clouds-thin.png", "close-day-clouds-thick.png", "close-day-clouds-natural.png",
}
ORIGINAL_MODELS = {"cottage", "broadleaf", "fir", "fence", "rock", "lamp", "bench", "sign", "grass"}
OMIT_KEYS = {
    "stdout", "stderr", "stdout_text", "stderr_text", "log", "log_text", "logs", "build_logs",
    "command_line", "argv", "host", "hostname", "username",
    "local_ref", "token", "access_token", "refresh_token",
}
HOST_PATH = re.compile(r"(?<![\w:/])(?:/[A-Za-z_][\w.-]*(?:/[^\s\"'<>]*)?|[A-Za-z]:[\\/][^\s\"'<>]*)")


def require(condition: object, message: str) -> None:
    if not condition:
        raise ValueError(message)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def project_path(value: str | Path) -> Path:
    path = (ROOT / value).resolve()
    require(path.is_relative_to(ROOT), "Evidence path must remain inside the project checkout")
    return path


def relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def child_path(parent: Path, value: str) -> Path:
    require(isinstance(value, str) and value and not Path(value).is_absolute(), "Expected a relative frozen path")
    path = (parent / value).resolve()
    require(path != parent and path.is_relative_to(parent), "Frozen path escaped its own directory")
    return path


def read_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def verify_hash(path: Path, expected: str) -> str:
    require(isinstance(expected, str) and re.fullmatch(r"[0-9a-f]{64}", expected),
            "Missing or malformed SHA-256: " + relative(path))
    require(path.is_file(), "Missing evidence file: " + relative(path))
    actual = digest(path.read_bytes())
    require(actual == expected, "SHA-256 mismatch: " + relative(path))
    return actual


def portable(value: object) -> object:
    """Retain measurements and provenance while removing host paths and logs."""
    if isinstance(value, dict):
        return {str(portable(str(key))): portable(item) for key, item in value.items() if key not in OMIT_KEYS}
    if isinstance(value, list):
        return [portable(item) for item in value]
    if isinstance(value, str):
        text = value.replace(str(ROOT) + "/", "").replace(str(ROOT), ".")
        return HOST_PATH.sub("[host-path omitted]", text)
    return value


def encode(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")


def passed_report(path: Path, *, checks_required: bool = True) -> dict:
    value = read_json(path)
    require(isinstance(value, dict) and value.get("passed") is True,
            "Report has not passed: " + relative(path))
    require(not value.get("failures"), "Report contains failures: " + relative(path))
    checks = value.get("checks", [])
    require(isinstance(checks, list) and (not checks_required or bool(checks)) and
            all(isinstance(item, dict) and item.get("passed") is True for item in checks),
            "Report contains absent, failing or malformed checks: " + relative(path))
    if "returncode" in value:
        require(value["returncode"] == 0, "Nonzero exit status: " + relative(path))
    return value


def png_bytes(path: Path, row: dict, size: tuple[int, int]) -> bytes:
    verify_hash(path, row.get("sha256"))
    data = path.read_bytes()
    require(data[:8] == b"\x89PNG\r\n\x1a\n" and data[12:16] == b"IHDR" and
            struct.unpack(">II", data[16:24]) == size and row.get("size") == list(size),
            "Screenshot PNG header or dimensions differ: " + relative(path))
    return data


def verify_transmission(capture: Path, reports: dict, pixels: dict, fingerprint: str) -> tuple[dict, list[dict]]:
    """Bind the calibrated receiver measurement to its original GPU/source bytes."""
    directory = capture / PROBE_DIRECTORY
    probe = reports[PROBE_DIRECTORY + "/" + PROBE_REPORT_NAMES[0]]
    measured = reports[PROBE_DIRECTORY + "/" + PROBE_REPORT_NAMES[1]]
    capture_hash = digest((directory / PROBE_REPORT_NAMES[0]).read_bytes())
    pixel_hash = digest((directory / PROBE_REPORT_NAMES[1]).read_bytes())
    require(probe.get("schema") == measured.get("schema") == 1 and
            probe.get("runtime_fingerprint") == measured.get("runtime_fingerprint") == fingerprint and
            probe.get("gpu") is True and probe.get("renderer") == "forward_plus" and probe.get("adapter") and
            probe.get("viewport") == [1024, 768] and measured.get("capture_sha256") == capture_hash,
            "Calibrated cloud receiver evidence does not bind this actual GPU/runtime capture")
    reference = pixels.get("cloud_transmission", {})
    require(reference.get("capture") == PROBE_DIRECTORY + "/" + PROBE_REPORT_NAMES[0] and
            reference.get("pixel_report") == PROBE_DIRECTORY + "/" + PROBE_REPORT_NAMES[1] and
            reference.get("capture_sha256") == capture_hash and reference.get("pixel_report_sha256") == pixel_hash and
            reference.get("passed") is True and reference.get("checks") == len(measured["checks"]),
            "Main pixel report is not linked to the exact calibrated receiver reports")
    source_names = {"scripts/forest_hamlet/cloud_lighting.gd", "shaders/forest_hamlet/cloud_occluder.gdshader",
                    "tools/forest_hamlet/capture_cloud_transmission.gd", "tools/forest_hamlet/cloud_transmission_checks.py"}
    sources = probe.get("source_files", {})
    require({name.removeprefix("res://") for name in sources} == source_names,
            "Calibrated receiver evidence does not identify the production shader and measurement tools")
    for name, expected in sources.items():
        verify_hash(project_path(name.removeprefix("res://")), expected)
    conditions = probe.get("conditions", {})
    require(conditions.get("tone_mapper") == "LINEAR" and conditions.get("tonemap_mode") == 0 and
            conditions.get("exposure") == 1.0 and conditions.get("ambient_energy") == 0.0 and
            conditions.get("ambient_source_disabled") is True and conditions.get("sky_reflections_disabled") is True and
            all(conditions.get(name) is False for name in
                ("fog", "glow", "ssao", "ssil", "ssr", "gi", "auto_exposure", "adjustments", "global_modulation")),
            "Calibrated receiver measurement requires LINEAR tone mapping, fixed exposure and no ambient/post effects")
    require(measured.get("measurement_encoding") == "Calibrated inverse-sRGB estimate after LINEAR tonemap; not raw HDR" and
            reference.get("measurement_encoding") == measured["measurement_encoding"],
            "Transmission estimate must not be represented as raw HDR or a full-scene RGB percentage")
    shots, measured_shots = probe.get("screenshots", []), measured.get("original_pngs", [])
    require(len(shots) == len(measured_shots) == len(PROBE_SCREENSHOTS) and
            {row.get("file") for row in shots} == {row.get("file") for row in measured_shots} == PROBE_SCREENSHOTS,
            "Calibrated receiver evidence must retain the exact eight original PNG controls")
    measured_hashes = {row["file"]: row["sha256"] for row in measured_shots}
    for row in shots:
        require(measured_hashes[row["file"]] == row["sha256"], "Pixel analysis used another receiver PNG")
        png_bytes(directory / row["file"], row, (1024, 768))
    require(len(measured.get("rois", [])) == 3 and reference.get("rois") == measured["rois"] and
            reference.get("natural_transmission_range") == measured.get("natural_transmission_range") and
            reference.get("ordinary_shadow_ratio") == measured.get("ordinary_shadow_ratio"),
            "Main and receiver pixel measurements differ")
    return {
        "capture": relative(directory / PROBE_REPORT_NAMES[0]), "capture_sha256": capture_hash,
        "pixel_report": relative(directory / PROBE_REPORT_NAMES[1]), "pixel_report_sha256": pixel_hash,
        "capture_checks": len(probe["checks"]), "pixel_checks": len(measured["checks"]),
        "measurement_encoding": measured["measurement_encoding"], "raw_hdr": False,
        "original_pngs": [{"file": relative(directory / row["file"]), "sha256": row["sha256"]}
                          for row in sorted(shots, key=lambda item: item["file"])],
    }, shots


def current_fingerprint() -> dict:
    """Use the existing project fingerprint function and discard its temporary file."""
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location("forest_atmosphere_evidence_runner", ROOT / "tools/forest_hamlet/run.py")
    require(spec is not None and spec.loader is not None, "Cannot load forest run.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    require(module.ROOT == ROOT, "Fingerprint function resolved a different checkout")
    build = ROOT / "build/forest-hamlet"
    build.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="archive-atmosphere-fingerprint-", dir=build) as directory:
        target = Path(directory)
        expected = module.runtime_fingerprint(target)
        result = read_json(target / "runtime-fingerprint.json")
        require(result["sha256"] == expected, "Fingerprint function returned inconsistent evidence")
        return result


def find_delivery_verified(value: object, delivery_id: str, archive_sha256: str) -> dict | None:
    if isinstance(value, dict):
        if value.get("status") == "verified" and value.get("delivery_id") == delivery_id and value.get("sha256") == archive_sha256:
            return value
        children = value.values()
    elif isinstance(value, list):
        children = value
    else:
        return None
    for child in children:
        found = find_delivery_verified(child, delivery_id, archive_sha256)
        if found is not None:
            return found
    return None


def verify_originals(assets: dict, runtime: dict, fingerprint: dict) -> dict:
    require(assets.get("character_files") == 345 and assets.get("changed_originals") == [],
            "Original asset report does not preserve the 345 character files")
    checks = {item.get("name", item.get("label")): item["passed"] for item in assets["checks"]}
    require(checks.get("nine editable original model sources") is True,
            "Original asset report does not cover the nine model sources")
    baseline_path = ROOT / "art/inputs/forest-hamlet/character-reuse.json"
    baseline = read_json(baseline_path)
    require(len(baseline["files"]) == 345, "Character preservation baseline must contain 345 files")
    for name, expected in baseline["files"].items():
        verify_hash(project_path(name), expected)
        require(fingerprint["files"].get(name) == expected, "GPU fingerprint omits an original character file")
    model_path = ROOT / "art/inputs/forest-hamlet/blender/manifest.json"
    model_manifest = read_json(model_path)
    models = model_manifest["assets"]
    require(len(models) == 9 and {item["id"] for item in models} == ORIGINAL_MODELS,
            "Original model manifest must identify the same nine GLBs")
    model_rows = []
    for item in models:
        require(checks.get(item["id"] + " output identity") is True,
                "Original asset report lacks model identity: " + item["id"])
        path = project_path(item["output"])
        verify_hash(path, item["sha256"])
        require(fingerprint["files"].get(relative(path)) == item["sha256"], "GPU fingerprint differs from an original GLB")
        model_rows.append({"id": item["id"], "path": relative(path), "sha256": item["sha256"]})
    vegetation_path = ROOT / "assets/forest-hamlet/vegetation/manifest.json"
    vegetation = read_json(vegetation_path)
    require(len(vegetation["assets"]) == 10, "Expected ten existing paired vegetation assets")
    vegetation_rows = []
    for item in vegetation["assets"]:
        for name in ("color", "normal"):
            path = child_path(vegetation_path.parent, item[name])
            expected = item[name + "_sha256"]
            verify_hash(path, expected)
            require(fingerprint["files"].get(relative(path)) == expected, "GPU fingerprint differs from paired vegetation")
            vegetation_rows.append({"id": item["id"], "kind": name, "path": relative(path), "sha256": expected})
    require(any(item.get("label") == "all 218 existing image vegetation instances retained" and item.get("passed") is True
                for item in runtime["checks"]), "Runtime evidence does not retain the 218 vegetation instances")
    return {
        "character_files": 345, "changed_originals": [], "character_baseline": relative(baseline_path),
        "character_baseline_sha256": digest(baseline_path.read_bytes()), "original_glbs": model_rows,
        "model_manifest": relative(model_path), "model_manifest_sha256": digest(model_path.read_bytes()),
        "vegetation_manifest": relative(vegetation_path), "vegetation_manifest_sha256": digest(vegetation_path.read_bytes()),
        "vegetation_pngs": vegetation_rows, "vegetation_sprite_count": 218,
    }


def verify_native_godot(summary_path: Path) -> tuple[dict, dict[str, Path], dict]:
    """Verify the native run's own immutable identity, independently of delivery ID."""
    summary = read_json(summary_path)
    native_run_id = summary.get("run_id")
    require(isinstance(native_run_id, str) and re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,95}", native_run_id),
            "Unsafe native Godot run ID")
    require(summary_path == project_path(Path("art/derived/forest-hamlet") / native_run_id / "native-godot/summary.json"),
            "Native Godot summary path differs from its original run identity")
    require(summary.get("workflow") == "godot.verify" and
            summary.get("execution_status") == "completed" and summary.get("rendered") is False,
            "Expected completed native AW godot.verify runtime evidence")
    fields = ("aw_run", "recipe", "snapshot", "native_frozen_recipe", "test_report")
    paths = {key: project_path(summary[key]) for key in fields}
    require(paths["aw_run"] == project_path(Path("art/derived/workbench/godot") / native_run_id / "run.json"),
            "Native Godot receipt path differs from its original run identity")
    for key, path in paths.items():
        verify_hash(path, summary[key + "_sha256"])
    native = read_json(paths["aw_run"])
    require(native.get("status") == "completed" and native.get("workflow") == "godot.verify",
            "Native Godot receipt is not a completed godot.verify run")
    engine = native.get("resources", {}).get("godot", {})
    require(engine.get("version") == summary.get("engine_version") and
            engine.get("sha256") == summary.get("engine_sha256") and
            str(engine.get("version", "")).startswith("4.7.2."), "Native Godot engine evidence differs")
    recipe = read_json(paths["recipe"])
    require(recipe == read_json(paths["native_frozen_recipe"]), "Native frozen Godot recipe differs")
    tests = recipe.get("tests", [])
    require(len(tests) == 1 and tests[0].get("script") == "tests/forest_hamlet/atmosphere_runtime.gd" and
            tests[0].get("render") is False and "ATMOSPHERE_RUNTIME_DONE passed=true" in tests[0].get("require", []) and
            "atmosphere-runtime-report.json" in tests[0].get("artifacts", []), "Native recipe lacks the actual runtime-test contract")
    report = passed_report(paths["test_report"])
    require(len(report["checks"]) == summary.get("test_checks"), "Native runtime check count differs")
    snapshot = read_json(paths["snapshot"])
    rows = snapshot.get("files", [])
    require(rows and len(rows) == snapshot.get("file_count") == summary.get("file_count"), "Native source closure count differs")
    require(sum(row["bytes"] for row in rows) == snapshot.get("total_bytes") == summary.get("total_bytes"),
            "Native source closure byte count differs")
    identity = {row["source"]: row["sha256"] for row in rows}
    require(len(identity) == len(rows), "Native source closure contains duplicate files")
    closure_hash = digest(json.dumps(identity, sort_keys=True, separators=(",", ":")).encode())
    require(closure_hash == snapshot.get("sha256") == summary.get("source_closure_sha256"),
            "Native source closure identity differs")
    native_inputs = paths["aw_run"].parent / "inputs"
    require(paths["native_frozen_recipe"] == native_inputs / "input.json", "Native recipe belongs to another output directory")
    require(set(recipe.get("files", [])) == {row["snapshot"] for row in rows}, "Native recipe and snapshot closure differ")
    for row in rows:
        source = project_path(row["source"])
        require(row["snapshot"] == "project/" + row["source"], "Unexpected native source-to-snapshot mapping")
        copies = [source, child_path(paths["snapshot"].parent, row["snapshot"]), child_path(native_inputs, row["snapshot"])]
        for path in copies:
            verify_hash(path, row["sha256"])
            require(path.stat().st_size == row["bytes"], "Native source closure size differs: " + row["source"])
    driver = project_path(snapshot["driver"])
    verify_hash(driver, snapshot["driver_sha256"])
    require(snapshot["driver_sha256"] == summary.get("driver_sha256"), "Native verification driver identities differ")
    paths.update(summary=summary_path, driver=driver)
    return summary, paths, {
        "summary": summary, "snapshot": snapshot, "recipe": recipe, "report": report,
        "receipt": {"workflow": native["workflow"], "status": native["status"],
                    "producer_version": native.get("producer_version"),
                    "engine": {"version": engine["version"], "sha256": engine["sha256"]},
                    "native_receipt_sha256": summary["aw_run_sha256"]},
    }


def verify_delivery(aw: dict, native_summary: dict, native_paths: dict[str, Path], outputs: list[dict]) -> tuple[dict[str, Path], dict]:
    """Check the actual native delivery ZIP; caller-frozen GPU evidence is separate."""
    fields = ("aw_manifest", "aw_archive", "aw_technical", "selection", "verify_receipt")
    paths = {key: project_path(aw[key]) for key in fields}
    for key, path in paths.items():
        verify_hash(path, aw[key + "_sha256"])
    directory = project_path(aw["aw_directory"])
    require(paths["aw_manifest"] == directory / "delivery.json" and paths["aw_archive"] == directory / "delivery.zip" and
            paths["aw_technical"] == directory / "technical.json", "AW delivery files belong to another directory")
    manifest = read_json(paths["aw_manifest"])
    require(manifest.get("schema_version") == 1 and manifest.get("asset_key") == "forest-hamlet-snow-atmosphere" and
            manifest.get("variant_key") == aw["run_id"] and manifest.get("delivery_id") == aw.get("delivery_id"),
            "Native delivery identity differs from the selected asset and run")
    identity = {key: value for key, value in manifest.items() if key != "delivery_id"}
    canonical = (json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()
    require(manifest["delivery_id"] == "delivery-" + digest(canonical), "Native delivery ID does not match its manifest")
    producer, provenance = manifest.get("producer", {}), manifest.get("sources", {})
    require(producer.get("tool") == "asset-workbench" and producer.get("workflow") == "godot.verify" and
            producer.get("run_id") == native_paths["aw_run"].parent.name, "Delivery did not come from the completed native Godot run")
    require(provenance.get("run_receipt_sha256") == native_summary["aw_run_sha256"] and
            provenance.get("recipe_sha256") == native_summary["native_frozen_recipe_sha256"],
            "Delivery source receipt or recipe differs from the native Godot evidence")
    if "request_id" in aw:
        require(producer.get("request_id") == aw["request_id"], "Native delivery request identity differs")
    registered = manifest.get("files", [])
    require(registered and len(registered) == len({item["path"] for item in registered}), "Delivery manifest has absent or duplicate files")
    require(len(registered) == aw.get("delivery_file_count"), "Delivery file count differs from the production summary")
    by_path = {item["path"]: item for item in registered}
    with zipfile.ZipFile(paths["aw_archive"]) as archive:
        members = archive.infolist()
        require(len(members) == len({item.filename for item in members}) and
                {item.filename for item in members} == set(by_path) | {"delivery.json"},
                "Delivery ZIP contains duplicate, missing or unregistered members")
        require(archive.read("delivery.json") == paths["aw_manifest"].read_bytes(), "Delivery external and packaged manifests differ")
        for name, item in by_path.items():
            require(isinstance(name, str) and not Path(name).is_absolute() and "\\" not in name and
                    all(part not in ("", ".", "..") for part in name.split("/")), "Unsafe delivery member path")
            member = archive.getinfo(name)
            require(not member.is_dir() and member.file_size == item["bytes"], "Delivery member size differs: " + name)
            with archive.open(member) as stream:
                require(hashlib.file_digest(stream, "sha256").hexdigest() == item["sha256"], "Delivery member SHA-256 differs: " + name)
        require(archive.read("technical.json") == paths["aw_technical"].read_bytes(), "Delivery external and packaged technical receipts differ")
    technical = read_json(paths["aw_technical"])
    require(technical.get("status") == "completed" and technical.get("workflow") == "godot.verify" and
            technical.get("checks") and all(item.get("status") in ("passed", "completed") for item in technical["checks"]),
            "Native delivery technical receipt is not completed")
    for item in manifest.get("review_media", []):
        verify_hash(directory / Path(item["path"]).name, item["sha256"])
        require(by_path.get(item["path"], {}).get("sha256") == item["sha256"] and item.get("source_paths") and
                all(path in by_path for path in item["source_paths"]), "Delivery review image binding differs")
    verification = find_delivery_verified(read_json(paths["verify_receipt"]), aw["delivery_id"], aw["aw_archive_sha256"])
    require(verification is not None and verification.get("manifest") == manifest, "Native delivery.verify did not verify this exact ZIP and manifest")
    verified_files = verification.get("files", [])
    require(len(verified_files) == len(registered) and {item["path"] for item in verified_files} == set(by_path) and
            all(item.get("status") == "verified" and all(item.get(key) == by_path[item["path"]][key]
                for key in ("sha256", "bytes", "role")) for item in verified_files), "Native delivery.verify file records differ")
    selection = read_json(paths["selection"])
    require(selection.get("asset_key") == manifest["asset_key"] and selection.get("variant_key") == manifest["variant_key"],
            "Native delivery selection identifies another asset or variant")
    selected = selection.get("outputs", [])
    rows = aw.get("aw_delivery_files", [])
    require(rows and len(rows) == len({row["path"] for row in rows}), "Native delivery source mapping is absent or ambiguous")
    native_run = native_paths["aw_run"].parent
    delivered_sources = {}
    for row in rows:
        source, run_source = project_path(row["source"]), child_path(native_run, row["run_source"])
        verify_hash(source, row["sha256"])
        verify_hash(run_source, row["sha256"])
        require(source.stat().st_size == run_source.stat().st_size == row["bytes"], "Native delivery source size differs")
        item = by_path.get(row["path"], {})
        require(all(item.get(key) == row[key] for key in ("sha256", "bytes", "role")), "Delivery mapping differs from its actual ZIP member")
        require(any(group.get("path") == row["run_source"] and group.get("role") == row["role"] for group in selected),
                "Delivery mapping is absent from the frozen selection")
        delivered_sources[relative(source)] = row["sha256"]
    require({row["path"] for row in rows} == {name for name, item in by_path.items() if item["role"] != "review" and name != "technical.json"},
            "Delivery source mapping does not cover the selected native contents")
    required = [*[project_path(item["runtime"]) for item in outputs], ROOT / "scripts/forest_hamlet/global_lighting.gd",
                native_paths["native_frozen_recipe"], native_paths["test_report"], native_paths["aw_run"]]
    for path in required:
        require(delivered_sources.get(relative(path)) == digest(path.read_bytes()), "Native delivery omitted required PNG/runtime evidence: " + relative(path))
    for path in delivered_sources:
        if path.startswith("build/forest-hamlet/"):
            raise ValueError("External GPU evidence must remain separately identified, outside the native Godot delivery")
    return paths, {"manifest": manifest, "technical": technical, "verification": verification, "selection": selection}


def find_revision(value: object, revision_id: str, asset_id: str) -> list[dict]:
    if isinstance(value, dict):
        if value.get("id") == revision_id and value.get("asset_id") == asset_id and isinstance(value.get("files"), list):
            return [value]
        children = (item for key, item in value.items() if key not in ("local_ref", "ref", "token"))
    elif isinstance(value, list):
        children = value
    else:
        return []
    return [found for child in children for found in find_revision(child, revision_id, asset_id)]


def verify_original_references(rows: list[dict], aliases: set[str], actual_by_name: dict,
                               parent_ids: list[str]) -> list[dict]:
    """Keep current and explicitly inherited original references distinct."""
    expected = {(name, None) for name in aliases} | {(name, parent) for name in aliases for parent in parent_ids}
    identities, projected = set(), []
    for row in rows:
        name, parent = row.get("path"), row.get("revision_id")
        require(name in aliases and ("revision_id" not in row or isinstance(parent, str) and parent in parent_ids),
                "VGP original reference names an undeclared parent or source")
        identity = (name, parent)
        require(identity in expected and identity not in identities, "Duplicate or unexpected VGP original provenance reference")
        identities.add(identity)
        observed = actual_by_name[name]
        require(all(row.get(key) == observed.get(key) for key in ("sha256", "size_bytes", "role")),
                "Inherited or current VGP original differs from the actual original image bytes")
        projected.append({key: row[key] for key in ("path", "revision_id", "sha256", "size_bytes", "role") if key in row})
    require(identities == expected, "VGP originals do not retain each current and declared parent source reference")
    return projected


def verify_vgp_transport(vgp: dict, directory: Path, run_id: str, candidate: dict,
                         frozen: list[dict], outputs: list[dict]) -> tuple[dict[str, Path], dict]:
    """Verify actual server attachments, then every logical dependency in the ZIP.

    VGP files[].role is the server's storage role (currently `source`). The
    primary/original/dependency grouping is independently read from materials.
    Only an allowlisted projection of the receipt can leave this function.
    """
    names = {"logical_frozen": "atmosphere.frozen-files.json", "transport_manifest": "transport-files.json",
             "packed_manifest": "packed-dependencies.json", "server_verification": "transport-server-verification.json"}
    paths = {key: project_path(vgp[key]) for key in names}
    for key, path in paths.items():
        require(path == directory / names[key], "VGP transport record belongs to another run: " + key)
        verify_hash(path, vgp[key + "_sha256"])
    require(read_json(paths["logical_frozen"]) == frozen and vgp.get("logical_file_count") == len(frozen),
            "VGP logical source count or identity differs")
    transport_manifest = read_json(paths["transport_manifest"])
    packed_manifest = read_json(paths["packed_manifest"])
    transport, packed = vgp.get("transport_files", []), vgp.get("packed_dependencies", [])
    require(transport_manifest.get("schema_version") == packed_manifest.get("schema_version") == 1 and
            transport_manifest.get("run_id") == packed_manifest.get("run_id") == run_id and
            transport_manifest.get("files") == transport and packed_manifest.get("entries") == packed and
            all(transport_manifest.get(key) == vgp[key] for key in
                ("logical_frozen", "logical_frozen_sha256", "packed_manifest", "packed_manifest_sha256")),
            "VGP transport manifests differ from the summary")
    require(isinstance(transport, list) and 1 <= len(transport) <= 64 and
            len(transport) == vgp.get("bundle_file_count") and
            len({row["archive_name"] for row in transport}) == len(transport),
            "VGP actual attachments must be unique and remain within the 64-file limit")
    logical = {row["source"]: row for row in frozen}
    require(len(logical) == len(frozen), "Logical VGP freeze contains duplicate source paths")
    primary = {item["runtime"]: "snow-" + item["name"] + ".png" for item in outputs}
    original = "art/inputs/forest-hamlet/snow-r1/source/snow-master.png"
    expected_direct = {source for source in logical if source in primary or source == original or
                       (Path(source).parts[:2] == ("build", "forest-hamlet") and Path(source).suffix.lower() == ".png")}
    direct = [row for row in transport if row.get("kind") == "direct"]
    containers = [row for row in transport if row.get("kind") == "evidence_zip"]
    require(len(direct) + len(containers) == len(transport) and len(containers) == 1 and packed,
            "VGP transport must have direct original PNGs and exactly one dependency ZIP")
    require(len({row["source"] for row in direct}) == len(direct) and
            {row["source"] for row in direct} == expected_direct and
            len({row["source"] for row in packed}) == len(packed) and
            {row["source"] for row in packed} == set(logical) - expected_direct,
            "Every logical source must appear exactly once as a direct PNG or a packed dependency")
    logical_keys = ("source", "archive_name", "sha256", "bytes")
    for row in direct:
        require({key: row[key] for key in logical_keys} == logical[row["source"]],
                "Direct attachment differs from the logical freeze")
        path = project_path(row["path"])
        require(path == directory / "bundle" / row["archive_name"], "Direct VGP attachment path mapping differs")
        expected_role = "primary" if row["source"] in primary else "original" if row["source"] == original else "dependency"
        require(row.get("role") == expected_role, "Direct attachment has the wrong material grouping")
        if expected_role == "primary":
            require(row["archive_name"] == primary[row["source"]], "Primary VGP alias differs from its source")
    for row in packed:
        require({key: row[key] for key in logical_keys} == logical[row["source"]] and
                row.get("entry") == "dependencies/" + row["archive_name"],
                "Packed dependency differs from its logical source or safe ZIP path")
    for row in transport:
        path = project_path(row["path"])
        verify_hash(path, row["sha256"])
        require(path.stat().st_size == row["bytes"], "VGP actual attachment size differs")
    container = containers[0]
    require(packed_manifest.get("archive") == container and container.get("archive_name") == "evidence.zip" and
            container.get("role") == "dependency" and
            project_path(container["path"]) == directory / "transport/evidence.zip" and
            container.get("member_count") == len(packed) + 1,
            "VGP dependency container identity differs")
    index = {"schema_version": 1, "run_id": run_id, "logical_file_count": len(frozen),
             "direct_files": [row for row in frozen if row["source"] in expected_direct],
             "packed_dependencies": sorted(packed, key=lambda row: row["entry"])}
    index_bytes = (json.dumps(index, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()
    require(digest(index_bytes) == container.get("index_sha256"), "VGP ZIP index identity differs")
    paths["dependency_archive"] = project_path(container["path"])
    with zipfile.ZipFile(paths["dependency_archive"]) as archive:
        members = archive.infolist()
        expected_members = {"index.json", *[row["entry"] for row in packed]}
        require(len(members) == len(expected_members) and {item.filename for item in members} == expected_members,
                "Dependency ZIP has duplicate, missing or unexpected members")
        require(archive.read("index.json") == index_bytes, "Dependency ZIP index does not map the complete logical closure")
        for item in members:
            require(not item.is_dir() and item.date_time == (1980, 1, 1, 0, 0, 0) and item.create_system == 3 and
                    item.compress_type == zipfile.ZIP_STORED and stat.S_ISREG(item.external_attr >> 16) and
                    stat.S_IMODE(item.external_attr >> 16) == 0o644, "Dependency ZIP is not the declared deterministic file archive")
        for row in packed:
            member = archive.getinfo(row["entry"])
            require(member.file_size == row["bytes"], "Packed dependency byte count differs: " + row["archive_name"])
            with archive.open(member) as stream:
                require(hashlib.file_digest(stream, "sha256").hexdigest() == row["sha256"],
                        "Packed dependency SHA-256 differs: " + row["archive_name"])

    paths["ingest_receipt"] = directory / "atmosphere-ingest.response.json"
    matches = find_revision(read_json(paths["ingest_receipt"]), candidate["revision_id"], candidate["asset_id"])
    require(len(matches) == 1, "Actual VGP ingest receipt does not uniquely identify this candidate revision")
    revision = matches[0]
    require(revision.get("kind") == "candidate" and revision.get("stage") == "concept_design",
            "Actual VGP receipt has a different revision kind or stage")
    actual = revision["files"]
    actual_by_name = {row["name"]: row for row in actual}
    expected_by_name = {row["archive_name"]: row for row in transport}
    require(len(actual) == len(actual_by_name) == len(transport) and set(actual_by_name) == set(expected_by_name),
            "Actual server attachment set differs from the declared transport")
    for name, expected in expected_by_name.items():
        observed = actual_by_name[name]
        require(observed.get("sha256") == expected["sha256"] and observed.get("size_bytes") == expected["bytes"] and
                isinstance(observed.get("role"), str) and observed["role"], "Actual server attachment identity differs: " + name)
    projected_files = [{key: row[key] for key in ("name", "sha256", "size_bytes", "role")}
                       for row in sorted(actual, key=lambda row: row["name"])]
    server = read_json(paths["server_verification"])
    require(server == {"schema_version": 1, "revision_id": candidate["revision_id"], "passed": True, "files": projected_files},
            "Sanitized VGP server verification differs from the actual native ingest receipt")
    materials = revision.get("materials", {})
    previous = candidate.get("previous_revision_id")
    parent_ids = revision.get("parent_revision_ids", [])
    require(isinstance(parent_ids, list) and len(parent_ids) == len(set(parent_ids)) and
            parent_ids == ([previous] if previous else []),
            "Actual VGP parent revision differs from the explicitly declared predecessor")
    expected_groups = {kind: {row["archive_name"] for row in transport if row["role"] == kind}
                       for kind in ("primary", "original", "dependency")}
    native_groups = {
        "primary": [row.get("file", {}) for row in materials.get("members", [])],
        "dependency": materials.get("dependencies", [])}
    for kind, rows in native_groups.items():
        require(len(rows) == len(expected_groups[kind]) and {row.get("path") for row in rows} == expected_groups[kind],
                "Actual VGP material grouping differs: " + kind)
        for row in rows:
            observed = actual_by_name[row["path"]]
            require(all(row.get(key) == observed.get(key) for key in ("sha256", "size_bytes", "role")),
                    "VGP materials refer to another uploaded attachment")
    original_refs = verify_original_references(materials.get("originals", []), expected_groups["original"], actual_by_name, parent_ids)
    member_original_refs = {}
    for member in materials.get("members", []):
        references = verify_original_references(member.get("originals", []), expected_groups["original"], actual_by_name, parent_ids)
        require(sorted(references, key=lambda row: (row["path"], row.get("revision_id", ""))) ==
                sorted(original_refs, key=lambda row: (row["path"], row.get("revision_id", ""))),
                "VGP primary output lost an exact current or inherited original binding")
        member_original_refs[member["file"]["path"]] = references
    projection = {"schema_version": 1, "asset_id": revision["asset_id"], "revision_id": revision["id"],
                  "kind": revision["kind"], "stage": revision["stage"], "files": projected_files,
                  "parent_revision_ids": parent_ids, "original_references": original_refs,
                  "member_original_references": member_original_refs,
                  "material_groups": {key: sorted(value) for key, value in expected_groups.items()},
                  "source_receipt_sha256": digest(paths["ingest_receipt"].read_bytes()),
                  "scope": "Native server receipt metadata only; local handles and tokens omitted"}
    return paths, {"transport": transport_manifest, "packed": packed_manifest, "server": server,
                   "ingest": projection, "index": index, "actual_attachment_count": len(transport),
                   "direct_file_count": len(direct), "packed_dependency_count": len(packed),
                   "logical_file_count": len(frozen), "dependency_archive_sha256": container["sha256"]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", default="build/forest-hamlet/atmosphere-r3-final")
    parser.add_argument("--aw-run-id", default=DEFAULT_RUN)
    parser.add_argument("--vgp-run-id", default=DEFAULT_RUN)
    parser.add_argument("--output", default="docs/forest-hamlet/revisions/atmosphere-r3-20261022")
    parser.add_argument("--extra-report", action="append", default=[], metavar="NAME=PATH",
                        help="Explicitly add a passed forest/close/vegetation report under a unique JSON filename")
    args = parser.parse_args()
    for value in (args.aw_run_id, args.vgp_run_id):
        require(re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,95}", value), "Unsafe workflow run ID")
    capture, output = project_path(args.capture), project_path(args.output)
    revisions = project_path("docs/forest-hamlet/revisions")
    require(output != revisions and output.is_relative_to(revisions), "Output must be a named revision directory")
    require(capture.is_dir(), "Final capture directory is missing")
    payloads: dict[str, bytes] = {}
    evidence: list[dict] = []

    def add_json(name: str, value: object, source: Path | None = None) -> None:
        require(re.fullmatch(r"(?:[a-z0-9][a-z0-9_.-]*/)*[a-z0-9][a-z0-9_.-]*\.json", name) and name not in payloads,
                "Unsafe or duplicate archive filename: " + name)
        clean = portable(value)
        original = source.read_bytes() if source is not None else None
        # Retain original report bytes when no portability transform is needed,
        # so the pixel report's capture SHA remains directly verifiable offline.
        # Projected native receipt summaries must never copy the full source.
        unchanged_source = original is not None and clean == value and json.loads(original) == value
        data = original if unchanged_source else encode(clean)
        payloads[name] = data
        row = {"file": name, "sha256": digest(data)}
        if source is not None:
            row.update(source=relative(source), source_sha256=digest(original))
        evidence.append(row)

    report_paths = {name: capture / name for name in (*REPORT_NAMES, "make-test-report.json")}
    report_paths.update({PROBE_DIRECTORY + "/" + name: capture / PROBE_DIRECTORY / name for name in PROBE_REPORT_NAMES})
    capture_assets = capture / "assets-report.json"
    report_paths["assets-report.json"] = capture_assets if capture_assets.is_file() else ROOT / "build/forest-hamlet/assets-report.json"
    for argument in args.extra_report:
        name, separator, value = argument.partition("=")
        require(separator and re.fullmatch(r"[a-z0-9][a-z0-9_.-]*\.json", name) and name not in report_paths,
                "Extra report must be a unique NAME.json=project/path.json")
        report_paths[name] = project_path(value)
    for name in ("runtime-report.json", "vegetation-assets-report.json", "vegetation-runtime-report.json", "close-runtime-report.json"):
        if name not in report_paths and (capture / name).is_file():
            report_paths[name] = capture / name
    reports = {name: passed_report(path, checks_required=name != "make-test-report.json") for name, path in report_paths.items()}
    require(reports["make-test-report.json"].get("command") == ["make", "test"] and
            reports["make-test-report.json"].get("returncode") == 0, "Expected a passed final make test report")
    gpu, pixels = reports["atmosphere-gpu-report.json"], reports["atmosphere-gpu-pixel-report.json"]
    completion_field_present = "complete_final_evidence" in gpu
    require(gpu.get("preview_only") is not True, "Preview-only evidence cannot be archived as final")
    require(gpu.get("complete_final_evidence") is True if completion_field_present else gpu.get("schema") == 1,
            "Capture is explicitly incomplete or has an unsupported completeness schema")
    require(gpu.get("gpu") is True and gpu.get("renderer") == "forward_plus" and
            gpu.get("adapter") and gpu.get("viewport") == [1920, 1080],
            "Expected complete actual Forward+ hardware GPU evidence at 1920x1080")
    route = gpu.get("route", {})
    require(route.get("completed") is True and route.get("waypoints") == route.get("total_waypoints") == 6,
            "Final six-waypoint physical route did not complete all six points")
    require(pixels.get("capture_sha256") == digest(report_paths["atmosphere-gpu-report.json"].read_bytes()),
            "GPU pixel report does not identify this exact capture report")
    global_pixels = pixels.get("global_light", {})
    require(gpu.get("schema") == 3 and pixels.get("schema") == 3 and global_pixels.get("clouds_disabled") is True and
            gpu.get("global_lighting_probe", {}).get("samples") and len(global_pixels.get("receivers", [])) == 3,
            "Revision 3 requires independent global-light and bounded partial-cloud GPU evidence")
    captured_path = capture / "runtime-fingerprint.json"
    captured, current = read_json(captured_path), current_fingerprint()
    require(captured == current and gpu.get("runtime_fingerprint") == pixels.get("runtime_fingerprint") == current["sha256"],
            "Final capture fingerprint differs from the current runtime; create fresh evidence")
    cloud_evidence, probe_shots = verify_transmission(capture, reports, pixels, current["sha256"])
    for name, report in reports.items():
        if "runtime_fingerprint" in report:
            require(report["runtime_fingerprint"] == current["sha256"], "Report used another runtime: " + name)
        if "route" in report and "completed" in report["route"]:
            require(report["route"]["completed"] is True, "Recorded physical route did not complete: " + name)
        add_json(name, report, report_paths[name])
    add_json("runtime-fingerprint.json", captured, captured_path)
    shots = gpu.get("screenshots", [])
    require(len(shots) == len(SCREENSHOTS) and {item.get("file") for item in shots} == SCREENSHOTS,
            "Expected exactly the eighteen final gameplay and lighting PNGs")
    for item in sorted(shots, key=lambda row: row["file"]):
        name = item["file"]
        path = capture / name
        data = png_bytes(path, item, (1920, 1080))
        payloads[name] = data
        evidence.append({"file": name, "source": relative(path), "source_sha256": digest(data), "sha256": digest(data)})
    for item in sorted(probe_shots, key=lambda row: row["file"]):
        name = PROBE_DIRECTORY + "/" + item["file"]
        path = capture / name
        data = png_bytes(path, item, (1024, 768))
        payloads[name] = data
        evidence.append({"file": name, "source": relative(path), "source_sha256": digest(data), "sha256": digest(data)})
    preservation = verify_originals(reports["assets-report.json"], reports["atmosphere-runtime-report.json"], current)
    add_json("preserved-resources.json", preservation)

    aw_dir = ROOT / "art/derived/forest-hamlet" / args.aw_run_id
    aw_path = aw_dir / "atmosphere-summary.json"
    aw = read_json(aw_path)
    require(aw.get("run_id") == args.aw_run_id and aw.get("execution_status") == "completed" and
            aw.get("workflow") == "delivery.export+delivery.verify", "Native AW delivery export and verification are not completed")
    frozen_path = project_path(aw["frozen_inputs"])
    require(frozen_path == aw_dir / "delivery-frozen-inputs.json", "Independent evidence freeze belongs to another run")
    verify_hash(frozen_path, aw["frozen_inputs_sha256"])
    frozen = read_json(frozen_path)
    closure = aw.get("closure", [])
    require(closure and frozen.get("run_id") == args.aw_run_id and frozen.get("files") == closure and
            frozen.get("aw_delivery_files") == aw.get("aw_delivery_files"),
            "Production summary and independently frozen evidence closure differ")
    frozen_sources = {}
    for row in closure:
        source = project_path(row["source"])
        copy = project_path(row["path"])
        require(copy == child_path(aw_dir / "frozen-source", relative(source)), "Independent frozen copy has an unexpected source mapping")
        require(relative(source) not in frozen_sources, "Independent evidence closure contains duplicate sources")
        verify_hash(source, row["sha256"])
        verify_hash(copy, row["sha256"])
        require(source.stat().st_size == copy.stat().st_size == row["bytes"], "Independent frozen evidence size differs")
        frozen_sources[relative(source)] = row["sha256"]
    technical = aw.get("technical_evidence", {})
    require(technical == frozen.get("evidence") and technical.get("runtime_fingerprint") == current["sha256"] and
            technical.get("screenshot_count") == len(shots) and technical.get("report_count") == len(REPORT_NAMES) + len(PROBE_REPORT_NAMES) and
            technical.get("probe_screenshot_count") == len(probe_shots) and
            technical.get("total_original_png_count") == len(shots) + len(probe_shots) and
            technical.get("cloud_transmission") == cloud_evidence and technical.get("capture_directory") == relative(capture) and
            technical.get("gpu_checks") == len(gpu["checks"]) and technical.get("complete_final_evidence") is True and
            technical.get("physical_route_completed") is True, "Independently frozen GPU evidence identifies another capture")
    declared_native = aw.get("native_godot")
    require(isinstance(declared_native, dict) and isinstance(declared_native.get("summary"), str),
            "AW delivery must identify its original native Godot summary")
    native_summary_path = project_path(declared_native["summary"])
    verify_hash(native_summary_path, declared_native.get("summary_sha256"))
    native_summary, native_paths, native_records = verify_native_godot(native_summary_path)
    native_metadata = {key: native_summary[key] for key in (
        "workflow", "execution_status", "aw_run", "aw_run_sha256", "recipe", "recipe_sha256",
        "snapshot", "snapshot_sha256", "native_frozen_recipe", "native_frozen_recipe_sha256",
        "test_report", "test_report_sha256", "source_closure_sha256", "file_count", "total_bytes",
        "test_checks", "engine_version", "engine_sha256", "rendered")}
    native_metadata.update(summary=relative(native_paths["summary"]), summary_sha256=digest(native_paths["summary"].read_bytes()))
    require(aw.get("native_godot") == native_metadata, "AW summary does not identify the verified native Godot evidence")
    required_frozen = [capture / name for name in (*REPORT_NAMES, "make-test-report.json", "runtime-fingerprint.json", *sorted(SCREENSHOTS))]
    required_frozen.extend(capture / PROBE_DIRECTORY / name for name in (*PROBE_REPORT_NAMES, *sorted(PROBE_SCREENSHOTS)))
    required_frozen.extend(native_paths.values())
    for path in required_frozen:
        require(frozen_sources.get(relative(path)) == digest(path.read_bytes()), "Independent evidence closure omitted current evidence: " + relative(path))

    manifest_path = project_path(aw["runtime_manifest"])
    verify_hash(manifest_path, aw["runtime_manifest_sha256"])
    manifest = read_json(manifest_path)
    require(manifest.get("validation", {}).get("passed") is True and
            manifest.get("geometry_count") == manifest.get("independent_color_layers") == 1 and
            manifest.get("parallax_kind") == "single_distant_board", "Backdrop manifest does not describe the validated single board")
    require(reports["atmosphere-assets-report.json"].get("manifest_sha256") == aw["runtime_manifest_sha256"],
            "Asset validation used a different backdrop manifest")
    source = project_path(aw["source"])
    require(source == project_path(manifest["source"]) and aw.get("source_sha256") == manifest.get("source_sha256") == SOURCE_SHA256,
            "Selected snow source identity differs")
    verify_hash(source, SOURCE_SHA256)
    outputs = aw.get("outputs", [])
    require(len(outputs) == 3 and {item["name"] for item in outputs} == {"color", "normal", "regions"},
            "AW must identify exactly the three aligned backdrop outputs")
    for item in outputs:
        path = project_path(item["runtime"])
        require(path == project_path(manifest[item["name"]]) and item.get("size") == manifest["dimensions"] == [1983, 793]
                and item.get("opaque") is True, "AW and backdrop manifest output metadata differ")
        verify_hash(path, item["sha256"])
        require(manifest["files"][path.name] == item["sha256"] == frozen_sources.get(relative(path)), "AW output hashes differ")
    require(next(item for item in outputs if item["name"] == "color")["sha256"] == SOURCE_SHA256,
            "Original snow color bytes were altered")
    rig_path, generator_path = project_path(manifest["rig"]), project_path(manifest["generator"])
    verify_hash(rig_path, manifest["rig_sha256"])
    verify_hash(generator_path, manifest["generator_sha256"])
    rig = read_json(rig_path)
    require(rig.get("color_is_height") is False and rig.get("massifs"), "Authored normal provenance is missing")
    delivery_paths, delivery_records = verify_delivery(aw, native_summary, native_paths, outputs)
    for path in [manifest_path, source, rig_path, generator_path, *delivery_paths.values()]:
        require(frozen_sources.get(relative(path)) == digest(path.read_bytes()), "Independent closure omitted selected source or native delivery evidence: " + relative(path))
    add_json("aw-summary.json", aw, aw_path)
    add_json("independent-frozen-inputs.json", frozen, frozen_path)
    add_json("aw-delivery-manifest.json", delivery_records["manifest"], delivery_paths["aw_manifest"])
    add_json("aw-delivery-technical.json", delivery_records["technical"], delivery_paths["aw_technical"])
    add_json("aw-delivery-verification.json", delivery_records["verification"], delivery_paths["verify_receipt"])
    add_json("aw-delivery-selection.json", delivery_records["selection"], delivery_paths["selection"])
    add_json("aw-delivery-source-map.json", {
        "authority": "native AW delivery ZIP contents independently matched to the completed Godot run",
        "delivery_id": aw["delivery_id"], "archive": aw["aw_archive"], "archive_sha256": aw["aw_archive_sha256"],
        "files": aw["aw_delivery_files"],
        "external_gpu_evidence": "The eighteen scene PNGs, eight calibrated receiver PNGs and their reports are independently frozen in independent-frozen-inputs.json and the VGP transport; they are not outputs of the headless native Godot run or contents of its AW delivery.",
    })
    add_json("aw-godot-summary.json", native_summary, native_paths["summary"])
    add_json("aw-godot-receipt.json", native_records["receipt"], native_paths["aw_run"])
    add_json("aw-godot-recipe.json", native_records["recipe"], native_paths["recipe"])
    add_json("aw-godot-snapshot.json", native_records["snapshot"], native_paths["snapshot"])
    add_json("aw-godot-runtime-report.json", native_records["report"], native_paths["test_report"])
    add_json("backdrop-manifest.json", manifest, manifest_path)
    add_json("source-normal-provenance.json", {
        "source": relative(source), "source_sha256": SOURCE_SHA256, "source_dimensions": manifest["dimensions"],
        "color_bytes_preserved": True, "rig": relative(rig_path), "rig_sha256": manifest["rig_sha256"],
        "generator": relative(generator_path), "generator_sha256": manifest["generator_sha256"],
        "normal_workflow": aw.get("normal_workflow"), "normal_method": manifest.get("normal_method"),
        "normal_convention": manifest.get("normal_convention"), "color_is_height": False,
        "geometry_count": 1, "independent_color_layers": 1, "parallax_kind": "single_distant_board",
        "outputs": outputs, "limitations": manifest.get("limitations", []),
        "human_aesthetic_approval": aw.get("human_aesthetic_approval", "pending"),
    })

    vgp_dir = ROOT / "art/derived/forest-hamlet" / args.vgp_run_id / "vgp"
    vgp_path = vgp_dir / "summary.json"
    vgp = read_json(vgp_path)
    require(vgp.get("native_godot") == native_metadata, "VGP summary identifies different native Godot evidence")
    delivery_metadata = {key: aw[key] for key in ("delivery_id", "aw_manifest", "aw_manifest_sha256", "aw_archive", "aw_archive_sha256", "verify_receipt", "verify_receipt_sha256")}
    require(vgp.get("aw_delivery") == delivery_metadata, "VGP summary identifies a different native AW delivery")
    candidates = [item for item in vgp.get("assets", []) if item.get("key") == "snow-atmosphere"]
    require(len(candidates) == 1, "VGP must identify one snow-atmosphere candidate")
    candidate = candidates[0]
    require(candidate.get("asset_key") == "forest-hamlet-snow-atmosphere" and candidate.get("main_output_count") == 3 and
            candidate.get("stage") == "concept_design", "VGP must retain the three primary outputs at the recorded concept stage")
    require(vgp.get("decisions_created") == 0 and vgp.get("stage_admissions_created") == 0,
            "This workflow must not manufacture an aesthetic decision or later-stage admission")
    check_path = project_path(candidate["check_receipt"])
    require(check_path.parent == vgp_dir, "VGP readiness check belongs to another run")
    check = read_json(check_path)
    require(check.get("ready") is True and check.get("issues") == [], "VGP candidate readiness check has unresolved issues")
    if "revision_id" in check:
        require(check["revision_id"] == candidate["revision_id"], "VGP check identifies a different revision")
    vgp_frozen_path = vgp_dir / "atmosphere.frozen-files.json"
    vgp_frozen = read_json(vgp_frozen_path)
    require(isinstance(vgp_frozen, list) and vgp_frozen, "VGP frozen bundle list is missing")
    aliases, bundled_sources = set(), {}
    for row in vgp_frozen:
        alias = row["archive_name"]
        require(isinstance(alias, str) and alias not in ("", ".", "..") and "/" not in alias and "\\" not in alias
                and alias not in aliases, "Unsafe or duplicate VGP bundle filename")
        aliases.add(alias)
        source_path, bundled = project_path(row["source"]), vgp_dir / "bundle" / alias
        require(relative(source_path) not in bundled_sources, "VGP logical closure contains duplicate source paths")
        verify_hash(source_path, row["sha256"])
        verify_hash(bundled, row["sha256"])
        require(source_path.stat().st_size == bundled.stat().st_size == row["bytes"], "VGP bundle byte count differs: " + alias)
        bundled_sources[relative(source_path)] = row["sha256"]
    for path in [aw_path, frozen_path, *delivery_paths.values(), *[project_path(name) for name in frozen_sources]]:
        require(bundled_sources.get(relative(path)) == digest(path.read_bytes()), "VGP bundle omitted native delivery or independently frozen evidence: " + relative(path))
    for name in ("color", "normal", "regions"):
        require("snow-" + name + ".png" in aliases, "VGP primary output alias is missing: " + name)
    transport_paths, transport_records = verify_vgp_transport(vgp, vgp_dir, args.vgp_run_id, candidate, vgp_frozen, outputs)
    add_json("vgp-summary.json", vgp, vgp_path)
    add_json("vgp-check.json", check, check_path)
    add_json("vgp-frozen-files.json", vgp_frozen, vgp_frozen_path)
    add_json("vgp-transport-files.json", transport_records["transport"], transport_paths["transport_manifest"])
    add_json("vgp-packed-dependencies.json", transport_records["packed"], transport_paths["packed_manifest"])
    add_json("vgp-server-verification.json", transport_records["server"], transport_paths["server_verification"])
    add_json("vgp-ingest-receipt.json", transport_records["ingest"], transport_paths["ingest_receipt"])
    add_json("vgp-dependency-index.json", transport_records["index"])
    evidence[-1].update(source=relative(transport_paths["dependency_archive"]), source_sha256=transport_records["dependency_archive_sha256"])

    summary = {
        "schema": 3, "passed": True,
        "scope": "Current runtime identity, original resources, final GPU read-back, passed tests and native AW/VGP evidence; visual review remains separate",
        "runtime_fingerprint": current["sha256"], "runtime_file_count": len(current["files"]),
        "capture": relative(capture), "screenshots": len(shots), "probe_screenshots": len(probe_shots),
        "total_original_png_count": len(shots) + len(probe_shots), "complete_final_evidence": True,
        "completeness_basis": "reported_complete_capture_verified" if completion_field_present else "derived_schema1_complete_capture",
        "completeness_rule": "Non-preview; explicit complete capture; every check passed; exact eighteen scene and eight calibrated receiver PNGs with verified hashes; actual Forward+; independently measured partial-cloud transmission and global-light variation; six of six physical waypoints completed. Source reports and PNG bytes are never amended.",
        "renderer": gpu["renderer"], "adapter": gpu["adapter"], "viewport": gpu["viewport"],
        "physical_route_completed": True, "near_framing": gpu["near_framing"],
        "reports": {name: {"passed": True, "checks": len(value.get("checks", []))} for name, value in reports.items()},
        "preserved": {"character_files": 345, "original_glbs": 9, "vegetation_pngs": 20, "vegetation_sprites": 218},
        "source_sha256": SOURCE_SHA256,
        "cloud_transmission": {**cloud_evidence,
                               "rois": reports[PROBE_DIRECTORY + "/" + PROBE_REPORT_NAMES[1]]["rois"],
                               "natural_transmission_range": reports[PROBE_DIRECTORY + "/" + PROBE_REPORT_NAMES[1]]["natural_transmission_range"],
                               "ordinary_shadow_ratio": reports[PROBE_DIRECTORY + "/" + PROBE_REPORT_NAMES[1]]["ordinary_shadow_ratio"]},
        "global_light": {"clouds_disabled_for_comparison": True, "weak_time_seconds": global_pixels["weak_time_seconds"],
                         "strong_time_seconds": global_pixels["strong_time_seconds"], "weak_vs_strong": global_pixels["weak_vs_strong"],
                         "weak_vs_off": global_pixels["weak_vs_off"], "strong_vs_off": global_pixels["strong_vs_off"],
                         "receiver_count": len(global_pixels["receivers"]), "live_route_samples": len(global_pixels["route_global_light"])},
        "aw": {"run_id": args.aw_run_id, "workflow": aw["workflow"], "execution_status": aw["execution_status"],
               "primary_outputs": 3, "delivery_id": aw["delivery_id"], "archive_sha256": aw["aw_archive_sha256"],
               "native_delivery_files": len(aw["aw_delivery_files"]), "native_verification": "verified",
               "godot_workflow": native_summary["workflow"], "godot_runtime_checks": native_summary["test_checks"],
               "godot_snapshot_files": native_summary["file_count"], "godot_source_closure_sha256": native_summary["source_closure_sha256"]},
        "independent_evidence_freeze": {"authority": "caller-created immutable SHA-256 copies, separately verified in the VGP bundle",
                                       "files": len(closure), "manifest": relative(frozen_path), "manifest_sha256": aw["frozen_inputs_sha256"],
                                       "includes_external_gpu_evidence": True, "gpu_is_native_godot_output": False},
        "vgp": {"run_id": args.vgp_run_id, "asset_id": candidate["asset_id"], "revision_id": candidate["revision_id"],
                "round_id": vgp["round_id"], "stage": candidate["stage"], "ready": True, "issues": [],
                "review_status": vgp.get("review_status"), "main_outputs": 3, "logical_frozen_files": len(vgp_frozen),
                "actual_attachments": transport_records["actual_attachment_count"],
                "direct_files": transport_records["direct_file_count"],
                "packed_dependencies": transport_records["packed_dependency_count"],
                "dependency_archive_sha256": transport_records["dependency_archive_sha256"],
                "actual_server_receipt_verified": True, "complete_logical_coverage_verified": True},
        "human_aesthetic_approval": aw.get("human_aesthetic_approval", "pending"),
        "evidence": sorted(evidence, key=lambda row: row["file"]),
        "portability": "Repository-relative and res:// paths are retained. Host paths, log bodies and native local handles/tokens are omitted; original source and archived SHA-256 values remain separately recorded. All PNG bytes and the cloud-transmission subdirectory are preserved.",
    }
    require("validation.json" not in payloads, "validation.json is reserved for the archive index")
    payloads["validation.json"] = encode(portable(summary))
    for name, data in payloads.items():
        target = child_path(output, name)
        require(not target.exists() or target.is_file() and target.read_bytes() == data,
                "Refusing to overwrite historical evidence: " + relative(target))
    output.mkdir(parents=True, exist_ok=True)
    for name, data in payloads.items():
        target = child_path(output, name)
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("xb") as stream:
                stream.write(data)
    print(json.dumps({"passed": True, "output": relative(output), "files": len(payloads), "screenshots": len(shots),
                      "probe_screenshots": len(probe_shots), "total_original_png_count": len(shots) + len(probe_shots),
                      "vgp_actual_attachments": transport_records["actual_attachment_count"],
                      "vgp_logical_files": transport_records["logical_file_count"],
                      "runtime_fingerprint": current["sha256"]}, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, TypeError, ImportError, struct.error, zipfile.BadZipFile) as error:
        print("Atmosphere evidence archive rejected: " + str(portable(str(error))), file=sys.stderr)
        raise SystemExit(1)
