#!/usr/bin/env python3
"""Verify and archive the final forest vegetation evidence without rerunning Godot.

Run from the project checkout. Existing evidence is immutable: an identical
rerun is allowed, but a differing file requires a new revision directory.
The README is managed separately and is never written by this script.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[2]
SPECIES = {
    "broadleaf_a", "broadleaf_b", "fir", "grass", "fern", "reeds",
    "flowers_white", "flowers_pink", "window_flowers", "lily_pad",
}
SCREENSHOTS = {
    "overview-day.png", "overview-dusk.png", "close-normals-on.png",
    "close-normals-off.png", "close-dusk.png", "close-route-left.png",
    "close-route-right.png", "plants-light-left-normals-on.png",
    "plants-light-left-normals-off.png", "plants-light-right-normals-on.png",
    "plants-light-right-normals-off.png",
}
CAPTURE_REPORTS = (
    "vegetation-assets-report.json", "vegetation-runtime-report.json",
    "close-runtime-report.json", "vegetation-gpu-pixel-report.json",
    "vegetation-gpu-report.json", "make-test-report.json",
)
OMIT_KEYS = {"stdout", "stderr", "stdout_text", "stderr_text", "log_text", "logs", "build_logs"}
# res:// paths and URLs are portable. Bare host filesystem paths are not.
HOST_PATH = re.compile(r"(?<![\w:/])(?:/[A-Za-z_][\w.-]*(?:/[^\s\"'<>]*)?|[A-Za-z]:[\\/][^\s\"'<>]*)")


def require(condition: object, message: str) -> None:
    if not condition:
        raise ValueError(message)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def project_path(value: str | Path) -> Path:
    path = (ROOT / value).resolve()
    try:
        path.relative_to(ROOT)
    except ValueError:
        raise ValueError("Evidence path must remain inside the project checkout") from None
    return path


def relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def read_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def verify_hash(path: Path, expected: str, label: str = "") -> str:
    require(isinstance(expected, str) and re.fullmatch(r"[0-9a-f]{64}", expected),
            f"Missing or malformed SHA-256: {label or relative(path)}")
    require(path.is_file(), f"Missing file: {label or relative(path)}")
    actual = digest(path.read_bytes())
    require(actual == expected, f"SHA-256 mismatch: {label or relative(path)}")
    return actual


def portable(value: object) -> object:
    """Retain measurements, replace checkout roots and omit log bodies."""
    if isinstance(value, dict):
        return {str(key): portable(item) for key, item in value.items() if key not in OMIT_KEYS}
    if isinstance(value, list):
        return [portable(item) for item in value]
    if isinstance(value, str):
        text = value.replace(str(ROOT) + "/", "").replace(str(ROOT), ".")
        return HOST_PATH.sub("[host-path omitted]", text)
    return value


def encode(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")


def passed_report(path: Path) -> dict:
    value = read_json(path)
    require(isinstance(value, dict) and value.get("passed") is True,
            f"Report has not passed: {relative(path)}")
    require(not value.get("failures"), f"Report contains failures: {relative(path)}")
    checks = value.get("checks", [])
    require(isinstance(checks, list) and all(isinstance(x, dict) and x.get("passed") is True for x in checks),
            f"Report contains a failing or malformed check: {relative(path)}")
    if "returncode" in value:
        require(value["returncode"] == 0, f"Nonzero exit status: {relative(path)}")
    return value


def current_fingerprint() -> dict:
    """Use the project's authoritative function; leave no scratch evidence."""
    sys.dont_write_bytecode = True
    source = ROOT / "tools/forest_hamlet/run.py"
    spec = importlib.util.spec_from_file_location("forest_evidence_runner", source)
    require(spec is not None and spec.loader is not None, "Cannot load forest run.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    require(module.ROOT == ROOT, "Fingerprint runner resolved a different project")
    build = ROOT / "build/forest-hamlet"
    build.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="archive-fingerprint-", dir=build) as directory:
        target = Path(directory)
        actual = module.runtime_fingerprint(target)
        result = read_json(target / "runtime-fingerprint.json")
        require(result["sha256"] == actual, "Current fingerprint function returned inconsistent evidence")
        return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", default="build/forest-hamlet/vegetation-r2-final")
    parser.add_argument("--aw-run-id", default="forest-hamlet-20261022-vegetation-r2-paired")
    parser.add_argument("--vgp-run-id", default="forest-hamlet-20261022-vegetation-r2-review")
    parser.add_argument("--output", default="docs/forest-hamlet/revisions/vegetation-r2-20261022")
    args = parser.parse_args()
    for value in (args.aw_run_id, args.vgp_run_id):
        require(re.fullmatch(r"[a-z0-9][a-z0-9_-]*", value), "Unsafe workflow run ID")
    capture = project_path(args.capture)
    output = project_path(args.output)
    revisions = project_path("docs/forest-hamlet/revisions")
    require(output != revisions and revisions in output.parents,
            "Output must be a named directory under docs/forest-hamlet/revisions")
    require(capture.is_dir(), "Capture directory is missing")

    # All bytes and summaries are prepared before any archive files are written.
    payloads: dict[str, bytes] = {}
    evidence: list[dict] = []

    def add_json(name: str, value: object, source: Path | None = None) -> None:
        clean = portable(value)
        original = source.read_bytes() if source is not None else None
        data = original if original is not None and clean == value else encode(clean)
        require(name not in payloads, f"Duplicate archive name: {name}")
        payloads[name] = data
        row = {"file": name, "sha256": digest(data)}
        if source is not None:
            row.update(source=relative(source), source_sha256=digest(original))
        evidence.append(row)

    reports = {name: passed_report(capture / name) for name in CAPTURE_REPORTS}
    assets_path = ROOT / "build/forest-hamlet/assets-report.json"
    overview_path = ROOT / "build/forest-hamlet/runtime/runtime-report.json"
    reports["assets-report.json"] = passed_report(assets_path)
    reports["runtime-report.json"] = passed_report(overview_path)
    require(reports["assets-report.json"].get("character_files") == 345 and
            reports["assets-report.json"].get("changed_originals") == [],
            "Original character preservation report does not verify all 345 files")
    require(reports["make-test-report.json"].get("command") == ["make", "test"],
            "Expected the final make test report")
    gpu = reports["vegetation-gpu-report.json"]
    pixels = reports["vegetation-gpu-pixel-report.json"]
    require(gpu.get("gpu") is True and gpu.get("renderer") == "forward_plus" and gpu.get("adapter"),
            "Capture is not a recorded Forward+ hardware GPU run")
    require(gpu.get("viewport") == [1920, 1080], "Unexpected capture viewport")
    for name in ("vegetation-gpu-report.json", "close-runtime-report.json", "runtime-report.json"):
        require(reports[name].get("route", {}).get("completed") is True,
                f"Physical route did not complete: {name}")
    require(pixels.get("input_capture_sha256") == digest((capture / "vegetation-gpu-report.json").read_bytes()),
            "GPU pixel report does not identify this capture report")

    captured_path = capture / "runtime-fingerprint.json"
    captured = read_json(captured_path)
    current = current_fingerprint()
    require(captured == current and gpu.get("runtime_fingerprint") == current["sha256"],
            "Capture fingerprint differs from the current runtime; create a fresh capture")
    add_json("runtime-fingerprint.json", captured, captured_path)
    shots = gpu.get("screenshots", [])
    require(len(shots) == 11 and {item.get("file") for item in shots} == SCREENSHOTS,
            "Expected exactly the final 11 gameplay and lighting PNGs")
    for item in sorted(shots, key=lambda row: row["file"]):
        name = item["file"]
        path = capture / name
        verify_hash(path, item.get("sha256"), name)
        data = path.read_bytes()
        require(data[:8] == b"\x89PNG\r\n\x1a\n" and item.get("size") == [1920, 1080],
                f"Malformed screenshot or dimensions: {name}")
        payloads[name] = data
        evidence.append({"file": name, "source": relative(path), "sha256": digest(data)})
    for name, value in reports.items():
        path = assets_path if name == "assets-report.json" else overview_path if name == "runtime-report.json" else capture / name
        add_json(name, value, path)

    # The AW receipt identifies official compiled colors; normal maps retain
    # their independently authored source bytes and paired-canvas identity.
    aw_dir = ROOT / "art/derived/forest-hamlet" / args.aw_run_id
    aw_path = aw_dir / "vegetation-summary.json"
    aw = read_json(aw_path)
    require(aw.get("execution_status") == "completed" and aw.get("workflow") == "world.compile",
            "AW is not a completed native world.compile run")
    native_path = project_path(aw["aw_run"])
    require(args.aw_run_id in native_path.parts, "AW receipt belongs to a different run")
    verify_hash(native_path, aw["aw_run_sha256"])
    native = read_json(native_path)
    require(native.get("status") == "completed" and native.get("workflow") == "world.compile",
            "Native AW run receipt is not completed")
    manifest_path = project_path(aw["runtime_manifest"])
    verify_hash(manifest_path, aw["runtime_manifest_sha256"])
    manifest = read_json(manifest_path)
    require(manifest.get("schema") == 1 and manifest.get("normal_convention") == "OpenGL",
            "Unexpected runtime vegetation manifest")
    outputs = aw["outputs"]
    require(len(outputs) == 10 and {item["name"] for item in outputs} == SPECIES,
            "AW does not contain the ten expected vegetation pairs")
    by_id = {item["id"]: item for item in manifest["assets"]}
    require(len(manifest["assets"]) == 10 and set(by_id) == SPECIES, "Manifest species differ from AW")
    measured = {item["id"]: item for item in reports["vegetation-assets-report.json"]["assets"]}
    require(set(measured) == SPECIES, "PNG validation report does not cover every species")
    require(reports["vegetation-assets-report.json"]["manifest_sha256"] == aw["runtime_manifest_sha256"],
            "PNG validation used a different runtime manifest")
    for item in outputs:
        name = item["name"]
        entry = by_id[name]
        for runtime_key, source_key, hash_key, manifest_key, report_key in (
            ("runtime", "source", "sha256", "color", "color_sha256"),
            ("normal_runtime", "normal_source", "normal_sha256", "normal", "normal_sha256"),
        ):
            runtime_path = project_path(item[runtime_key])
            source_path = project_path(item[source_key])
            require(runtime_path == project_path(manifest_path.parent / entry[manifest_key]),
                    f"Manifest and AW paths differ for {name}")
            verify_hash(runtime_path, item[hash_key])
            verify_hash(source_path, item[hash_key])
            require(entry[report_key] == item[hash_key] == measured[name][report_key],
                    f"AW, manifest and validation hashes differ for {name}")
        require(item.get("paired_alpha_equal") is True and
                entry["alpha_sha256"] == measured[name]["alpha_sha256"],
                f"Color/normal alpha evidence differs for {name}")
    production_path = ROOT / "assets/forest-hamlet/vegetation-production.json"
    production = read_json(production_path)
    require(production.get("run_id") == args.aw_run_id and production.get("asset_count") == 10 and
            project_path(production["summary"]) == aw_path, "Current runtime production pointer differs from AW")
    frozen_path = aw_dir / "vegetation-frozen-inputs.json"
    frozen = read_json(frozen_path)
    require(frozen.get("run_id") == args.aw_run_id and frozen.get("inputs"), "AW frozen inputs are missing")
    verify_hash(ROOT / "tools/forest_hamlet/process_vegetation_aw.py", frozen["driver_sha256"])
    for item in frozen["inputs"]:
        verify_hash(project_path(item["path"]), item["sha256"])
    add_json("aw-summary.json", aw, aw_path)
    add_json("aw-frozen-inputs.json", frozen, frozen_path)
    add_json("vegetation-manifest.json", manifest, manifest_path)

    # Check the frozen ingest bundle itself, then its current repository source.
    # Native receipt bodies/commands may contain host paths; only portable
    # summaries and the small readiness check are retained here.
    vgp_dir = ROOT / "art/derived/forest-hamlet" / args.vgp_run_id / "vgp"
    vgp_path = vgp_dir / "summary.json"
    vgp = read_json(vgp_path)
    candidates = [item for item in vgp["assets"] if item.get("key") == "vegetation"]
    require(len(candidates) == 1, "VGP must identify one vegetation candidate")
    candidate = candidates[0]
    require(candidate.get("main_output_count") == 20 and candidate.get("stage") == "concept_design",
            "VGP candidate does not contain twenty concept-stage outputs")
    check_path = project_path(candidate["check_receipt"])
    require(check_path.parent == vgp_dir, "VGP check receipt belongs to a different run")
    check = read_json(check_path)
    require(check.get("ready") is True and check.get("issues") == [],
            "VGP candidate readiness check has unresolved issues")
    if "revision_id" in check:
        require(check["revision_id"] == candidate["revision_id"], "VGP check identifies a different revision")
    frozen_files_path = vgp_dir / "vegetation.frozen-files.json"
    frozen_files = read_json(frozen_files_path)
    require(isinstance(frozen_files, list) and frozen_files, "VGP frozen file list is empty")
    aliases: set[str] = set()
    frozen_sources: dict[str, str] = {}
    for item in frozen_files:
        alias = item["archive_name"]
        require(isinstance(alias, str) and alias not in ("", ".", "..") and
                "/" not in alias and "\\" not in alias and alias not in aliases,
                "Unsafe or duplicate VGP bundle filename")
        aliases.add(alias)
        source = project_path(item["source"])
        bundled = vgp_dir / "bundle" / alias
        verify_hash(source, item["sha256"])
        verify_hash(bundled, item["sha256"])
        require(source.stat().st_size == bundled.stat().st_size == item["bytes"],
                f"VGP frozen size differs: {alias}")
        frozen_sources[relative(source)] = item["sha256"]
    for path in [aw_path, manifest_path, *[project_path(item[field]) for item in outputs for field in ("runtime", "normal_runtime")]]:
        require(frozen_sources.get(relative(path)) == digest(path.read_bytes()),
                f"VGP frozen bundle does not include current AW evidence: {relative(path)}")
    add_json("vgp-summary.json", vgp, vgp_path)
    add_json("vgp-check.json", check, check_path)
    add_json("vgp-frozen-files.json", frozen_files, frozen_files_path)

    preparation_path = project_path(aw["preparation"])
    preparation = read_json(preparation_path)
    normal_path = project_path(preparation["normal_recipe"])
    rig = read_json(normal_path)
    source_files = []
    source_provenance = []
    for value in dict.fromkeys(aw.get("source_files", [])):
        path = project_path(value)
        source_files.append({"path": relative(path), "sha256": digest(path.read_bytes())})
        if path.name == "provenance.json":
            provenance = read_json(path)
            for image in provenance.get("images", []):
                verify_hash(project_path(image["path"]), image["sha256"])
            source_provenance.append({"path": relative(path), "record": provenance})
    require(source_provenance, "Source image provenance record is missing")
    normal_summary = {
        "schema": 1, "preparation": relative(preparation_path),
        "preparation_sha256": digest(preparation_path.read_bytes()),
        "source_provenance": source_provenance, "source_files": source_files,
        "normal_recipe": relative(normal_path), "normal_recipe_sha256": digest(normal_path.read_bytes()),
        "normal_method": rig.get("method"), "normal_basis": rig.get("normal_basis"),
        "normal_workflow": aw.get("normal_workflow"), "normal_convention": aw.get("normal_convention"),
        "normal_generation": "Independently authored geometric relief; linear vector PNGs are paired with native AW color output",
        "normal_source_bytes_equal_runtime": True,
        "all_pair_alpha_equal": True,
        "maximum_normal_length_error": max(item["normal_max_length_error"] for item in measured.values()),
        "pairs": [{key: item[key] for key in ("name", "size", "runtime", "sha256", "normal_source", "normal_runtime", "normal_sha256")}
                  for item in outputs],
        "artistic_approval": aw.get("human_aesthetic_approval", "pending"),
    }
    add_json("source-normal-provenance.json", normal_summary)

    summary = {
        "schema": 1, "passed": True,
        "scope": "Verified existing final test reports, current runtime identity, GPU frames and native workflow evidence; no aesthetic decision is created",
        "runtime_fingerprint": current["sha256"], "runtime_file_count": len(current["files"]),
        "capture": relative(capture), "screenshots": len(shots),
        "reports": {name: {"passed": True, "checks": len(value.get("checks", []))} for name, value in reports.items()},
        "renderer": gpu["renderer"], "adapter": gpu["adapter"], "viewport": gpu["viewport"],
        "near_framing": gpu["near_framing"],
        "physical_routes_completed": ["overview", "close", "GPU close"],
        "vegetation_families": sorted(SPECIES),
        "vegetation_sprite_count": reports["vegetation-runtime-report.json"]["registered_sprites"],
        "original_character": {"files": 345, "changed_originals": []},
        "aw": {"run_id": args.aw_run_id, "workflow": aw["workflow"], "execution_status": aw["execution_status"],
               "runtime_manifest_sha256": aw["runtime_manifest_sha256"], "pairs": 10, "frozen_inputs": len(frozen["inputs"])},
        "vgp": {"run_id": args.vgp_run_id, "asset_id": candidate["asset_id"], "revision_id": candidate["revision_id"],
                "round_id": vgp["round_id"], "stage": candidate["stage"], "ready": True, "issues": [],
                "review_status": vgp.get("review_status"), "main_outputs": 20, "frozen_files": len(frozen_files)},
        "artistic_approval": aw.get("human_aesthetic_approval", "pending"),
        "evidence": sorted(evidence, key=lambda row: row["file"]),
        "portability": "Paths are repository-relative or res://; raw logs and native host command receipts are omitted. Source and archived hashes are both listed when applicable.",
    }
    payloads["validation.json"] = encode(portable(summary))
    # An existing README or unrelated earlier evidence is never overwritten.
    for name, data in payloads.items():
        target = output / name
        require(not target.exists() or target.is_file() and target.read_bytes() == data,
                f"Refusing to overwrite historical evidence: {relative(target)}")
    output.mkdir(parents=True, exist_ok=True)
    for name, data in payloads.items():
        target = output / name
        if not target.exists():
            with target.open("xb") as stream:
                stream.write(data)
    print(json.dumps({"passed": True, "output": relative(output), "files": len(payloads),
                      "screenshots": len(shots), "runtime_fingerprint": current["sha256"]}, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, TypeError, ImportError) as error:
        print("Evidence archive rejected: " + str(portable(str(error))), file=sys.stderr)
        raise SystemExit(1)
