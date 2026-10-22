#!/usr/bin/env python3
"""Export the verified native Godot inputs through AW delivery export + verify.

This preserves the selected original color bytes. Geometric normal generation
and external GPU evidence are independently frozen, not attributed to AW.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import zipfile

from PIL import Image

from register_vgp import decode, digest, freeze_json, installed_cli


DEFAULT_RUN = "forest-hamlet-20261022-atmosphere-r2"
SOURCE = "art/inputs/forest-hamlet/snow-r1/source/snow-master.png"
RIG = "art/inputs/forest-hamlet/snow-r1/normal-rig.json"
GENERATOR = "tools/forest_hamlet/prepare_snow_backdrop.py"
MANIFEST = "assets/forest-hamlet/backdrop/manifest.json"
SOURCE_SHA256 = "fa11b07fc545379570c1a86f8f5c70a5d5fe01c38aa4ffd2306ad6c5d381ce8c"
REPORT_NAMES = (
    "atmosphere-assets-report.json", "atmosphere-runtime-report.json",
    "atmosphere-gpu-report.json", "atmosphere-gpu-pixel-report.json",
)
SCREENSHOTS = {
    "close-day-clouds-a.png", "close-day-clouds-off.png", "close-day-clouds-b.png",
    "close-day-glow-off.png", "close-day-atmosphere-off.png", "close-dusk-atmosphere.png",
    "close-route-left.png", "close-route-right.png", "snow-left-normals-on.png",
    "snow-left-normals-off.png", "snow-right-normals-on.png", "snow-right-normals-off.png",
    "close-day-global-weak.png", "close-day-global-strong.png", "close-day-global-off.png",
}
CONFIG_TEXT = """schema_version: 1
confirmed: true
references: []
art:
  style: Soft HD2D distant snow panorama; reduced high-frequency detail
  projection: perspective
  texture_filter: linear-background / nearest-near
  alpha_policy: opaque
  palette:
    mode: per-asset
resolution:
  logical_canvas: [1983, 793]
  engine_viewport: [1920, 1080]
  display_scale: 1
domains:
  godot:
    enabled: true
    engine_version: 4.7.2
forest_hamlet_scope:
  specification_basis: User selected the revised distant snow illustration and requested scene integration, normal relighting, moving cloud shadows, independent irregular global light variation and WorldEnvironment Glow.
  source_size: [1983, 793]
  source_color_policy: Preserve original PNG bytes; no palette mapping or resampling.
  near_texture_filter: nearest
  background_texture_filter: linear
  normal_policy: Authored low-frequency geometric normals; no color-brightness height conversion.
  aesthetic_approval: pending
  confirmation_scope: Existing task and style authorization only; no user aesthetic acceptance or VGP decision is created.
"""


def safe_id(value: str) -> str:
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,95}", value):
        raise ValueError("Run IDs must be safe lowercase directory names")
    return value


def freeze_text(path: Path, value: str) -> None:
    if path.exists():
        if path.read_text(encoding="utf-8") != value:
            raise RuntimeError(f"Frozen text differs: {path}; choose a new config/version")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def ensure_config(root: Path, relative: str = "art/inputs/forest-hamlet/atmosphere-r2/workbench-project.yaml") -> Path:
    config = (root / relative).resolve()
    config.relative_to(root)
    freeze_text(config, CONFIG_TEXT)
    return config


def relative_file(root: Path, path: Path) -> str:
    resolved = path.resolve(strict=True)
    relative = resolved.relative_to(root).as_posix()
    if not resolved.is_file() or path.is_symlink():
        raise RuntimeError("Expected a regular project file: " + relative)
    return relative


def evidence_files(root: Path, destination: Path) -> tuple[list[Path], dict]:
    paths = []
    reports = {}
    for name in REPORT_NAMES:
        path = destination / name
        report = json.loads(path.read_text(encoding="utf-8"))
        if report.get("passed") is not True:
            raise RuntimeError("Final technical report has not passed: " + name)
        paths.append(path)
        reports[name] = report
    capture = reports["atmosphere-gpu-report.json"]
    # Schema 1 predates the convenience completeness flag. Derive the same
    # requirement from the immutable capture facts; never rewrite the report.
    explicit_complete = "complete_final_evidence" in capture
    if ((explicit_complete and capture["complete_final_evidence"] is not True)
            or (not explicit_complete and capture.get("schema") != 1)
            or capture.get("preview_only") is True
            or capture.get("gpu") is not True or capture.get("renderer") != "forward_plus"):
        raise RuntimeError("Need complete actual Forward+ GPU evidence, not preview-only frames")
    checks = capture.get("checks", [])
    if not checks or not all(isinstance(row, dict) and row.get("passed") is True for row in checks) or capture.get("failures"):
        raise RuntimeError("Every final GPU check must pass without failures")
    route = capture.get("route", {})
    if route.get("completed") is not True or route.get("waypoints") != 6 or route.get("total_waypoints") != 6:
        raise RuntimeError("The final six-waypoint physical route has not completed")
    screenshots = capture.get("screenshots", [])
    if len(screenshots) != len(SCREENSHOTS) or {item.get("file") for item in screenshots} != SCREENSHOTS:
        raise RuntimeError("Final GPU evidence must contain the exact fifteen distinct capture files")
    for item in screenshots:
        file = destination / item["file"]
        if file.parent.resolve() != destination.resolve() or digest(file) != item["sha256"]:
            raise RuntimeError("GPU screenshot identity does not verify: " + str(item.get("file")))
        paths.append(file)
    fingerprint_path = destination / "runtime-fingerprint.json"
    fingerprint = json.loads(fingerprint_path.read_text(encoding="utf-8"))
    canonical = json.dumps(fingerprint["files"], sort_keys=True, separators=(",", ":")).encode()
    if hashlib.sha256(canonical).hexdigest() != fingerprint["sha256"] or capture.get("runtime_fingerprint") != fingerprint["sha256"]:
        raise RuntimeError("GPU and runtime fingerprints differ")
    for name, expected in fingerprint["files"].items():
        if digest(root / name) != expected:
            raise RuntimeError("Runtime changed after the final capture: " + name)
    paths.append(fingerprint_path)
    test_report = destination / "make-test-report.json"
    if test_report.exists():
        if json.loads(test_report.read_text(encoding="utf-8")).get("passed") is not True:
            raise RuntimeError("Existing final make-test report failed")
        paths.append(test_report)
    return paths, {"runtime_fingerprint": fingerprint["sha256"], "report_count": len(REPORT_NAMES),
                   "screenshot_count": len(screenshots), "physical_route_completed": True,
                   "complete_final_evidence": True, "gpu_checks": len(checks),
                   "completeness_basis": "explicit_flag_and_complete_capture" if explicit_complete else "derived_schema1_complete_capture"}


def native_godot_evidence(root: Path, summary_path: Path) -> tuple[list[Path], dict]:
    """Verify the native run and add its receipts without copying its project again."""
    summary_name = relative_file(root, summary_path)
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    if (summary.get("workflow") != "godot.verify" or summary.get("execution_status") != "completed"
            or summary.get("rendered") is not False or summary.get("aesthetic_approval") != "pending"):
        raise RuntimeError("A completed native Godot verification with pending art review is required")
    fields = ("aw_run", "recipe", "snapshot", "native_frozen_recipe", "test_report")
    paths = [summary_path]
    for field in fields:
        path = root / summary[field]
        relative_file(root, path)
        if digest(path) != summary[field + "_sha256"]:
            raise RuntimeError("Native Godot evidence changed: " + field)
        paths.append(path)
    driver = root / "tools/forest_hamlet/verify_atmosphere_godot_aw.py"
    if digest(driver) != summary["driver_sha256"]:
        raise RuntimeError("Native Godot driver changed after verification")
    paths.append(driver)
    run_path = root / summary["aw_run"]
    record = json.loads(run_path.read_text(encoding="utf-8"))
    resource = record.get("resources", {}).get("godot", {})
    if (record.get("workflow") != "godot.verify" or record.get("status") != "completed"
            or resource.get("version") != summary["engine_version"]
            or not str(resource.get("version", "")).startswith("4.7.2.")
            or resource.get("sha256") != summary["engine_sha256"]):
        raise RuntimeError("Native Godot receipt no longer verifies the pinned engine")
    recipe = json.loads((root / summary["recipe"]).read_text(encoding="utf-8"))
    if recipe != json.loads((root / summary["native_frozen_recipe"]).read_text(encoding="utf-8")):
        raise RuntimeError("Native Godot recipe and its frozen copy differ")
    test = {"id": "atmosphere-runtime", "script": "tests/forest_hamlet/atmosphere_runtime.gd", "render": False,
            "args": [], "require": ["ATMOSPHERE_RUNTIME_DONE passed=true"], "artifacts": ["atmosphere-runtime-report.json"]}
    if recipe.get("engine_version") != "4.7.2" or recipe.get("project") != "project" or recipe.get("tests") != [test]:
        raise RuntimeError("Native Godot recipe does not declare the required runtime verification")
    report = json.loads((root / summary["test_report"]).read_text(encoding="utf-8"))
    if (report.get("passed") is not True or not report.get("checks") or report.get("failures")
            or len(report["checks"]) != summary["test_checks"]):
        raise RuntimeError("The native Godot runtime report has not passed")
    snapshot_path = root / summary["snapshot"]
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    rows = snapshot["files"]
    identity = {row["source"]: row["sha256"] for row in rows}
    closure_sha = hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if (len(rows) != len(identity) or len(rows) != summary["file_count"] or len(rows) != snapshot["file_count"]
            or closure_sha != summary["source_closure_sha256"] or closure_sha != snapshot["sha256"]
            or snapshot["driver_sha256"] != summary["driver_sha256"]
            or recipe["files"] != [row["snapshot"] for row in rows]):
        raise RuntimeError("Native Godot source closure identity does not verify")
    for row in rows:
        if row["snapshot"] != "project/" + row["source"]:
            raise RuntimeError("Native Godot snapshot path differs from its source path")
        for path in (root / row["source"], snapshot_path.parent / row["snapshot"], run_path.parent / "inputs" / row["snapshot"]):
            relative_file(root, path)
            if digest(path) != row["sha256"] or path.stat().st_size != row["bytes"]:
                raise RuntimeError("Native Godot source/snapshot/frozen closure changed: " + row["source"])
    metadata = {key: summary[key] for key in (
        "workflow", "execution_status", "aw_run", "aw_run_sha256", "recipe", "recipe_sha256",
        "snapshot", "snapshot_sha256", "native_frozen_recipe", "native_frozen_recipe_sha256",
        "test_report", "test_report_sha256", "source_closure_sha256", "file_count", "total_bytes",
        "test_checks", "engine_version", "engine_sha256", "rendered")}
    metadata.update({"summary": summary_name, "summary_sha256": digest(summary_path)})
    return paths, metadata


def verify_delivery_archive(root: Path, directory: Path, selected: list[dict], native: dict,
                            variant: str, request_id: str) -> dict:
    """Independently bind the real native manifest/ZIP to exact selected inputs."""
    manifest_path = directory / "delivery.json"
    archive_path = directory / "delivery.zip"
    technical_path = directory / "technical.json"
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    if (manifest.get("schema_version") != 1 or manifest.get("asset_key") != "forest-hamlet-snow-atmosphere"
            or manifest.get("variant_key") != variant or manifest.get("producer", {}).get("workflow") != "godot.verify"
            or manifest["producer"].get("request_id") != request_id
            or manifest.get("sources", {}).get("run_receipt_sha256") != native["aw_run_sha256"]
            or manifest["sources"].get("recipe_sha256") != native["native_frozen_recipe_sha256"]):
        raise RuntimeError("Native delivery provenance differs from the verified Godot run")
    identity = dict(manifest)
    delivery_id = identity.pop("delivery_id")
    canonical = (json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()
    if delivery_id != "delivery-" + hashlib.sha256(canonical).hexdigest():
        raise RuntimeError("Native delivery ID differs from its manifest identity")
    rows = manifest["files"]
    registered = {row["path"]: row for row in rows}
    if len(registered) != len(rows):
        raise RuntimeError("Native delivery contains duplicate file records")
    with zipfile.ZipFile(archive_path) as archive:
        entries = archive.infolist()
        if len(entries) != len({item.filename for item in entries}) or {item.filename for item in entries} != set(registered) | {"delivery.json"}:
            raise RuntimeError("Native delivery ZIP file set differs from its manifest")
        if archive.read("delivery.json") != manifest_bytes or archive.read("technical.json") != technical_path.read_bytes():
            raise RuntimeError("Native delivery external receipts differ from ZIP members")
        for item in entries:
            path = PurePosixPath(item.filename)
            if path.is_absolute() or ".." in path.parts or "\\" in item.filename or item.is_dir() or item.flag_bits & 1:
                raise RuntimeError("Unsafe native delivery ZIP member")
            if item.filename == "delivery.json":
                continue
            row = registered[item.filename]
            with archive.open(item) as stream:
                sha256 = hashlib.file_digest(stream, "sha256").hexdigest()
            if item.file_size != row["bytes"] or sha256 != row["sha256"]:
                raise RuntimeError("Native delivery member hash/size differs: " + item.filename)
        for row in selected:
            delivered = registered.get(row["path"])
            if delivered is None or any(delivered[field] != row[field] for field in ("sha256", "bytes", "role")):
                raise RuntimeError("Selected run input was not delivered exactly: " + row["path"])
            source = root / row["source"]
            native_source = (root / native["aw_run"]).parent / row["run_source"]
            if digest(source) != row["sha256"] or digest(native_source) != row["sha256"]:
                raise RuntimeError("Selected source differs from the native delivered file: " + row["source"])
        expected_members = {row["path"] for row in selected} | {"technical.json"} | {row["path"] for row in manifest["review_media"]}
        if set(registered) != expected_members:
            raise RuntimeError("Native delivery contains unselected material")
    for row in manifest["review_media"]:
        if digest(directory / Path(row["path"]).name) != row["sha256"]:
            raise RuntimeError("Native delivery review media differs from the manifest")
    technical = json.loads(technical_path.read_text(encoding="utf-8"))
    if technical.get("status") != "completed" or technical.get("workflow") != "godot.verify":
        raise RuntimeError("Native delivery technical receipt does not describe the completed Godot verification")
    return {"delivery_id": delivery_id, "aw_manifest": relative_file(root, manifest_path), "aw_manifest_sha256": digest(manifest_path),
            "aw_archive": relative_file(root, archive_path), "aw_archive_sha256": digest(archive_path),
            "aw_technical": relative_file(root, technical_path), "aw_technical_sha256": digest(technical_path),
            "producer_version": manifest["producer"].get("version"), "delivery_file_count": len(rows)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, default=Path.cwd())
    parser.add_argument("--run-id", default=DEFAULT_RUN)
    parser.add_argument("--evidence-dir", default="build/forest-hamlet/atmosphere-r2-final")
    parser.add_argument("--config", default="art/inputs/forest-hamlet/atmosphere-r2/workbench-project.yaml")
    parser.add_argument("--ensure-config-only", action="store_true", help="Create/verify the separate confirmed task configuration without delivery export")
    parser.add_argument("--extra-evidence", action="append", default=[], help="Add an exact project-relative file to the frozen closure; repeat for native Godot receipt, recipe and summary")
    parser.add_argument("--native-godot-summary", help="Native godot.verify summary; defaults to this run's native-godot/summary.json and its dependencies are included automatically")
    args = parser.parse_args()
    safe_id(args.run_id)
    root = args.project.resolve()
    config = ensure_config(root, args.config)
    if args.ensure_config_only:
        print(json.dumps({"status": "configured", "config": config.relative_to(root).as_posix(), "sha256": digest(config)}))
        return
    state = root / "art/derived/forest-hamlet" / args.run_id
    state.mkdir(parents=True, exist_ok=True)
    evidence = (root / args.evidence_dir).resolve(strict=True)
    evidence.relative_to(root)
    evidence_paths, evidence_summary = evidence_files(root, evidence)
    native_summary_path = root / args.native_godot_summary if args.native_godot_summary else state / "native-godot/summary.json"
    native_paths, native_summary = native_godot_evidence(root, native_summary_path)
    manifest_path = root / MANIFEST
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("validation", {}).get("passed") is not True:
        raise RuntimeError("The authored source/normal preparation has not passed")
    if digest(root / SOURCE) != SOURCE_SHA256 or digest(root / manifest["color"]) != SOURCE_SHA256:
        raise RuntimeError("Selected source color PNG bytes changed")
    if digest(root / RIG) != manifest["rig_sha256"] or digest(root / GENERATOR) != manifest["generator_sha256"]:
        raise RuntimeError("Authored rig or generator differs from the runtime manifest")
    outputs = []
    for name in ("color", "normal", "regions"):
        path = root / manifest[name]
        with Image.open(path) as image:
            size = list(image.size)
            opaque = image.convert("RGBA").getextrema()[3] == (255, 255)
        if size != [1983, 793] or not opaque or digest(path) != manifest["files"][path.name]:
            raise RuntimeError("Backdrop output size/alpha/hash differs: " + name)
        outputs.append({"name": name, "runtime": path.relative_to(root).as_posix(), "sha256": digest(path), "size": size, "opaque": True})
    selection = root / "art/inputs/forest-hamlet/atmosphere-r2/selection.json"
    freeze_json(selection, {
        "schema_version": 1,
        "selected_source": SOURCE,
        "source_sha256": SOURCE_SHA256,
        "basis": "User selected the simplified snow mountain illustration by asking to add this distant view to the existing game scene with normal-based lighting, overhead occlusion and Glow.",
        "quoted_instruction": "刚才的游戏场景加入远景，并使用法线模拟光照；同时，在天空增加遮挡，使得环境光照强度不均匀的洒落到场景物品中，营造一种场景光线有胴体啊的感觉，通过给世界环境增加 glow 效果，有光晕的效果。",
        "interpretation": "Implement moving spatially nonuniform illumination plus independently controllable irregular global light variation; preserve the selected distant-only soft snow image.",
        "additional_scope": "The later user direction adds independent irregular global light intensity changes alongside the cloud shadows; r1 evidence is preserved and this r2 run verifies the expanded behavior.",
        "selection": "selected", "human_aesthetic_approval": "pending",
        "approval_boundary": "Implementation authorization does not create an art-review approval or VGP decision."
    })
    sources = [
        root / SOURCE, root / RIG, root / GENERATOR, manifest_path,
        root / "art/inputs/forest-hamlet/snow-r1/technical-notes.md",
        selection, config,
        root / "scripts/forest_hamlet/snow_backdrop.gd",
        root / "shaders/forest_hamlet/snow_backdrop.gdshader",
        root / "scripts/forest_hamlet/cloud_lighting.gd",
        root / "scripts/forest_hamlet/global_lighting.gd",
        root / "shaders/forest_hamlet/cloud_occluder.gdshader",
        root / "scripts/forest_hamlet/scene.gd",
        root / "scripts/forest_hamlet/close_scene.gd",
        root / "project.godot",
        root / "tools/forest_hamlet/process_atmosphere_aw.py",
        root / "tools/forest_hamlet/register_atmosphere_vgp.py",
        root / "tools/forest_hamlet/register_vgp.py",
        root / "tests/forest_hamlet/atmosphere_runtime.gd",
        root / "tools/forest_hamlet/capture_atmosphere.gd",
        root / "tools/forest_hamlet/atmosphere_checks.py",
        root / "tools/forest_hamlet/run_atmosphere.py",
        *[root / row["runtime"] for row in outputs], *evidence_paths, *native_paths,
        *[root / relative for relative in args.extra_evidence],
    ]
    cloud_notes = root / "docs/forest-hamlet/cloud-lighting.md"
    if cloud_notes.is_file():
        sources.append(cloud_notes)
    run = root / "art/derived/workbench/delivery" / args.run_id
    godot_run = (root / native_summary["aw_run"]).parent
    delivery_rows = []
    groups = []

    def select(source: str, run_source: str, role: str, name: str) -> None:
        original = root / source
        frozen = godot_run / run_source
        relative_file(root, original)
        relative_file(root, frozen)
        frozen.relative_to(godot_run)
        if digest(original) != digest(frozen):
            raise RuntimeError("Selected original differs from the completed native run: " + source)
        groups.append({"path": run_source, "role": role, "name": name})
        delivery_rows.append({"source": source, "run_source": run_source,
                              "path": role + "/" + name + "/" + frozen.name,
                              "sha256": digest(frozen), "bytes": frozen.stat().st_size, "role": role})

    for item in outputs:
        select(item["runtime"], "inputs/project/" + item["runtime"], "runtime", "snow-" + item["name"])
    select(native_summary["native_frozen_recipe"], "inputs/input.json", "recipe", "godot-verify")
    select(native_summary["aw_run"], "run.json", "evidence", "godot-run")
    select(native_summary["test_report"], (root / native_summary["test_report"]).relative_to(godot_run).as_posix(), "evidence", "atmosphere-runtime")
    select(MANIFEST, "inputs/project/" + MANIFEST, "evidence", "backdrop-manifest")
    runtime_sources = ["project.godot", "scripts/forest_hamlet/scene.gd", "scripts/forest_hamlet/close_scene.gd",
                       "scripts/forest_hamlet/snow_backdrop.gd", "scripts/forest_hamlet/cloud_lighting.gd",
                       "scripts/forest_hamlet/global_lighting.gd",
                       "shaders/forest_hamlet/snow_backdrop.gdshader", "shaders/forest_hamlet/cloud_occluder.gdshader",
                       "tests/forest_hamlet/atmosphere_runtime.gd", "tools/forest_hamlet/capture_atmosphere.gd"]
    for index, name in enumerate(runtime_sources):
        select(name, "inputs/project/" + name, "editable", f"runtime-source-{index:02d}")
    delivery_selection = {
        "asset_key": "forest-hamlet-snow-atmosphere", "variant_key": args.run_id,
        "purpose": "Deliver unchanged snow color/normal/region PNGs and runtime sources for cloud shadows and independent irregular global illumination from the completed native Godot verification. External GPU evidence is separately frozen by the project and is not AW-generated or AW-rendered.",
        "outputs": groups, "review_media": [{"path": "inputs/project/" + outputs[0]["runtime"], "source_paths": ["inputs/project/" + outputs[0]["runtime"]]}],
        "entrypoints": [],
    }
    selection_path = state / "aw-delivery.selection.json"
    freeze_json(selection_path, delivery_selection)
    request_id = args.run_id + ":delivery:v1"
    native_cli = installed_cli("aw")
    base = ["aw", "--project", ".", "--project-config", config.relative_to(root).as_posix()]

    def execute(label: str, command: list[str]) -> dict:
        freeze_json(state / f"{label}.command.json", command)
        result = subprocess.run([native_cli, *command[1:]], cwd=root, capture_output=True, text=True, timeout=300)
        receipt = state / f"{label}.response.json"
        if result.returncode:
            freeze_text(state / f"{label}.failed.stdout.txt", result.stdout)
            freeze_text(state / f"{label}.failed.stderr.txt", result.stderr)
            raise RuntimeError(f"Native AW {label} failed ({result.returncode}): {result.stderr or result.stdout}")
        value = decode(result.stdout)
        freeze_json(receipt, value)
        return value

    if not run.exists():
        execute("aw-delivery-export", base + ["delivery", "export", "--run", godot_run.relative_to(root).as_posix(),
                "--output", run.relative_to(root).as_posix(), "--selection", selection_path.relative_to(root).as_posix(),
                "--request-id", request_id, "--json"])
    checked = execute("aw-delivery-verify", base + ["delivery", "verify", "--package", run.relative_to(root).as_posix(), "--json"])
    delivered = verify_delivery_archive(root, run, delivery_rows, native_summary, args.run_id, request_id)
    # Native CLI may wrap the verification result; find its status without
    # guessing which presentation envelope the installed release uses.
    def verified(value):
        if isinstance(value, dict):
            if value.get("status") == "verified" and value.get("delivery_id") == delivered["delivery_id"]:
                return value
            for child in value.values():
                found = verified(child)
                if found:
                    return found
        elif isinstance(value, list):
            for child in value:
                found = verified(child)
                if found:
                    return found
        return None
    verification = verified(checked)
    if (verification is None or verification.get("sha256") != delivered["aw_archive_sha256"]
            or verification.get("manifest") != json.loads((root / delivered["aw_manifest"]).read_text(encoding="utf-8"))):
        raise RuntimeError("Native AW verification did not confirm the exact delivery manifest and ZIP")
    verify_receipt = state / "aw-delivery-verify.response.json"
    sources.extend([selection_path, root / delivered["aw_manifest"], root / delivered["aw_archive"],
                    root / delivered["aw_technical"], verify_receipt])
    export_receipt = state / "aw-delivery-export.response.json"
    if export_receipt.is_file():
        sources.append(export_receipt)
    rows = []
    freeze_text(state / "frozen-source/.gdignore", "")
    output_paths = {row["runtime"] for row in outputs}
    for path in sorted(set(sources)):
        relative = relative_file(root, path)
        destination = state / "frozen-source" / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        expected = digest(path)
        if destination.exists():
            if digest(destination) != expected:
                raise RuntimeError("Independent source freeze differs; choose a new run ID: " + relative)
        else:
            shutil.copyfile(path, destination)
        role = "recipe" if relative == RIG else "input" if relative == SOURCE else "output" if relative in output_paths else "evidence"
        rows.append({"source": relative, "path": destination.relative_to(root).as_posix(),
                     "sha256": expected, "bytes": path.stat().st_size, "role": role})
    for row in rows:
        if digest(root / row["source"]) != row["sha256"] or digest(root / row["path"]) != row["sha256"]:
            raise RuntimeError("Independent source closure changed during validation: " + row["source"])
    frozen_inputs = state / "delivery-frozen-inputs.json"
    freeze_json(frozen_inputs, {"schema_version": 1, "run_id": args.run_id,
                "owner": "Project provenance script; separate from native AW delivery", "files": rows,
                "aw_delivery_files": delivery_rows, "evidence": evidence_summary})
    report_paths = [(evidence / name).relative_to(root).as_posix() for name in REPORT_NAMES]
    summary = {
        "schema_version": 1, "run_id": args.run_id, "workflow": "delivery.export+delivery.verify", "execution_status": "completed",
        "aw_directory": run.relative_to(root).as_posix(), "request_id": request_id, **delivered,
        "selection": selection_path.relative_to(root).as_posix(), "selection_sha256": digest(selection_path),
        "verify_receipt": verify_receipt.relative_to(root).as_posix(), "verify_receipt_sha256": digest(verify_receipt),
        "frozen_inputs": frozen_inputs.relative_to(root).as_posix(), "frozen_inputs_sha256": digest(frozen_inputs),
        "project_config": config.relative_to(root).as_posix(), "runtime_manifest": MANIFEST,
        "runtime_manifest_sha256": digest(manifest_path), "source": SOURCE, "source_sha256": SOURCE_SHA256,
        "normal_workflow": "Manually annotated low-frequency geometric facets, emitted as OpenGL tangent-space vectors by prepare_snow_backdrop.py; independent of AW delivery",
        "extra_evidence": [relative_file(root, root / relative) for relative in args.extra_evidence],
        "outputs": outputs, "closure": rows, "aw_delivery_files": delivery_rows,
        "technical_evidence": evidence_summary, "native_godot": native_summary,
        "human_aesthetic_approval": "pending", "adoption": {
            "selection": {"status": "selected", "evidence": [selection.relative_to(root).as_posix()]},
            "technical": {"status": "passed", "evidence": report_paths + [native_summary["summary"], delivered["aw_manifest"], verify_receipt.relative_to(root).as_posix()]},
            "art": {"status": "pending", "evidence": ["User aesthetic review remains separate from technical checks."]},
            "integration": {"status": "integrated", "evidence": [report_paths[2], (evidence / "runtime-fingerprint.json").relative_to(root).as_posix()]}},
        "aw_delivery_scope": "Only the selected files already inside the completed native Godot run; see aw_delivery_files for ZIP mappings.",
        "independent_closure_scope": "Project script SHA256 freezes original art, authored normal rig, GPU images/reports and provenance. These external GPU results are not native AW-rendered or AW-verified GPU output.",
        "note": "Native AW godot.verify ran the headless runtime test. Native delivery export/verify packaged and verified selected frozen-run inputs. External GPU evidence was separately captured and checked. No image generation, normal generation or aesthetic approval is attributed to AW."
    }
    freeze_json(state / "atmosphere-summary.json", summary)
    print(json.dumps({"status": "completed", "summary": (state / "atmosphere-summary.json").relative_to(root).as_posix(), "primary_outputs": len(outputs), "closure_files": len(rows), "evidence": evidence_summary}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
