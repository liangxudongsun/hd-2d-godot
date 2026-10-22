#!/usr/bin/env python3
"""Freeze public r4 tuning evidence after genuine AW and VGP completion."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re

from atmosphere_workflow_profiles import profile_spec
from process_atmosphere_aw import evidence_files, native_godot_evidence, relative_file, safe_id, verify_delivery_archive
from register_vgp import digest, freeze_json, locate


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def public_json(value, key: str = "") -> None:
    if isinstance(value, dict):
        for name, child in value.items():
            require(name.lower() not in {"local_ref", "token", "access_token", "refresh_token", "authorization", "password", "signed_url", "upload_url", "download_url"}, "Private transport/credential field: " + name)
            public_json(child, name)
    elif isinstance(value, list):
        for child in value:
            public_json(child, key)
    elif isinstance(value, str):
        require(not value.startswith("/") and not re.match(r"^[A-Za-z]:[\\/]", value), "Absolute host path in public evidence")
        require(not (key in {"stdout", "stderr", "log", "logs"} and "\n" in value), "Build log body in public evidence")


def main() -> None:
    spec = profile_spec("cloud-tuning")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, default=Path.cwd())
    parser.add_argument("--run-id", default=spec["run_id"])
    parser.add_argument("--evidence-dir", default=spec["evidence_dir"])
    parser.add_argument("--output", default="docs/forest-hamlet/revisions/cloud-tuning-r4-20261022")
    args = parser.parse_args()
    safe_id(args.run_id)
    root = args.project.resolve()

    def path(relative: str) -> Path:
        result = root / relative
        relative_file(root, result)
        return result

    def read(source: Path):
        return json.loads(source.read_text(encoding="utf-8"))

    def bound(record: dict, field: str) -> Path:
        source = path(record[field])
        require(digest(source) == record[field + "_sha256"], "Changed workflow receipt: " + field)
        return source

    evidence = (root / args.evidence_dir).resolve(strict=True)
    evidence.relative_to(root)
    evidence_paths, technical = evidence_files(root, evidence, "cloud-tuning")
    state = root / "art/derived/forest-hamlet" / args.run_id
    aw_path, vgp_path = state / "atmosphere-summary.json", state / "vgp/summary.json"
    aw, vgp = read(aw_path), read(vgp_path)
    require(aw.get("profile") == "cloud-tuning" and aw.get("run_id") == args.run_id and aw.get("execution_status") == "completed" and aw.get("workflow") == "delivery.export+delivery.verify", "Need the completed r4 AW delivery")
    require(aw["technical_evidence"] == technical and aw.get("human_aesthetic_approval") == "pending", "Evidence scope or art status differs")
    _, native = native_godot_evidence(root, path(aw["native_godot"]["summary"]))
    require(native == aw["native_godot"] and native.get("profile") == "cloud-tuning", "Native AW source closure differs")
    delivery = verify_delivery_archive(root, root / aw["aw_directory"], aw["aw_delivery_files"], native, args.run_id, aw["request_id"])
    require(all(aw.get(key) == value for key, value in delivery.items()), "Delivery identity differs from AW summary")
    for field in ("aw_manifest", "aw_archive", "aw_technical", "selection", "verify_receipt", "frozen_inputs"):
        bound(aw, field)
    verified = locate(read(path(aw["verify_receipt"])), {"status", "delivery_id", "sha256", "manifest"})
    require(verified["status"] == "verified" and verified["delivery_id"] == aw["delivery_id"] and verified["sha256"] == aw["aw_archive_sha256"] and verified["manifest"] == read(path(aw["aw_manifest"])), "Native delivery.verify receipt does not bind this package")
    verified_archive = Path(verified["archive"])
    if not verified_archive.is_absolute():
        verified_archive = root / verified_archive
    require(verified_archive.resolve(strict=True) == path(aw["aw_archive"]).resolve(strict=True), "Native verification archive path identifies another package")
    native_receipt = read(path(native["aw_run"]))
    native_public = {"schema_version": 1, "workflow": native_receipt["workflow"], "status": native_receipt["status"], "producer_version": native_receipt.get("producer_version"), "engine": {key: native_receipt["resources"]["godot"][key] for key in ("version", "sha256")}, "recipe": native["recipe"], "recipe_sha256": native["recipe_sha256"], "source_receipt": native["aw_run"], "source_receipt_sha256": native["aw_run_sha256"], "scope": "Public projection of the verified original native run receipt; host-specific source and executable paths are omitted. The unchanged original receipt is bound by its SHA256."}
    verification_public = {**verified, "archive": aw["aw_archive"], "source_receipt": aw["verify_receipt"], "source_receipt_sha256": aw["verify_receipt_sha256"], "projection_scope": "Only the archive path is expressed relative to the project after verifying it resolves to the exact original package; status, archive SHA256, manifest and file verification records are preserved. The original receipt remains unchanged and SHA256-bound."}
    projections = {"aw-godot-receipt.json": (native_public, path(native["aw_run"])), "aw-delivery-verification.json": (verification_public, path(aw["verify_receipt"]))}
    frozen = read(path(aw["frozen_inputs"]))
    require(frozen["files"] == aw["closure"] and frozen["aw_delivery_files"] == aw["aw_delivery_files"], "AW independent closure index differs")
    for row in aw["closure"]:
        for name in ("source", "path"):
            source = path(row[name])
            require(digest(source) == row["sha256"] and source.stat().st_size == row["bytes"], "AW frozen source changed: " + row[name])
    require(vgp.get("profile") == "cloud-tuning" and vgp.get("review_status") == "pending" and vgp.get("decisions_created") == 0 and vgp.get("stage_admissions_created") == 0 and len(vgp.get("assets", [])) == 1, "VGP must be one pending candidate without decisions")
    require(vgp["native_godot"] == native and all(vgp["aw_delivery"].get(key) == aw[key] for key in vgp["aw_delivery"]), "VGP does not bind this AW run")
    asset = vgp["assets"][0]
    require(asset.get("key") == "snow-atmosphere" and asset.get("stage") == "concept_design" and asset.get("status") == "pending_review", "VGP asset status or category differs")
    require(vgp.get("previous_run_id") == "forest-hamlet-20261022-atmosphere-r3", "The r3 predecessor was not preserved")
    previous_path = path("art/derived/forest-hamlet/" + vgp["previous_run_id"] + "/vgp/summary.json")
    previous, predecessor = read(previous_path), read(state / "vgp/predecessor.json")
    parent = previous["assets"][0]
    require(predecessor["summary_sha256"] == digest(previous_path) and predecessor["summary"] == previous, "Frozen predecessor summary changed")
    require(asset["asset_id"] == parent["asset_id"] and asset["previous_revision_id"] == parent["revision_id"] and vgp["previous_round_id"] == previous["round_id"] and all(vgp[key] == previous[key] for key in ("project_id", "scene_classification_id", "case_id")), "VGP r3 asset/revision/round lineage differs")
    check = read(path(asset["check_receipt"]))
    require(check.get("ready") is True and not check.get("issues"), "VGP candidate is not ready for review")
    for field in ("materials", "server_verification", "transport_manifest", "packed_manifest", "logical_frozen"):
        bound(vgp, field)
    logical = read(path(vgp["logical_frozen"]))
    require(len(logical) == vgp["logical_file_count"] and {row["source"] for row in aw["closure"]} <= {row["source"] for row in logical}, "VGP logical source closure is incomplete")
    for row in logical:
        source, frozen_copy = path(row["source"]), state / "vgp/bundle" / row["archive_name"]
        relative_file(root, frozen_copy)
        require(digest(source) == row["sha256"] == digest(frozen_copy) and source.stat().st_size == row["bytes"] == frozen_copy.stat().st_size, "VGP logical frozen source changed")
    require(read(path(vgp["transport_manifest"]))["files"] == vgp["transport_files"] and read(path(vgp["packed_manifest"]))["entries"] == vgp["packed_dependencies"], "VGP transport or packed source mapping differs")
    materials, server = read(path(vgp["materials"])), read(path(vgp["server_verification"]))
    require(materials["id"] == asset["revision_id"] and materials["asset_id"] == asset["asset_id"] and materials["parent_revision_ids"] == [parent["revision_id"]] and materials["kind"] == "candidate" and materials["stage"] == "concept_design", "Public candidate material identity differs")
    originals = materials["materials"]["originals"]
    require(any(not item.get("revision_id") and item["sha256"] == aw["source_sha256"] for item in originals) and any(item.get("revision_id") == parent["revision_id"] and item["sha256"] == aw["source_sha256"] for item in originals), "Current and inherited original references must both remain")
    server_files = {row["name"]: row for row in server["files"]}
    require(server.get("passed") is True and server.get("revision_id") == asset["revision_id"] and len(server_files) == len(server["files"]) == len(vgp["transport_files"]) == vgp["bundle_file_count"], "VGP attachment count or receipt differs")
    for row in vgp["transport_files"]:
        source, observed = path(row["path"]), server_files[row["archive_name"]]
        require(digest(source) == row["sha256"] == observed["sha256"] and source.stat().st_size == row["bytes"] == observed["size_bytes"], "VGP actual attachment differs: " + row["archive_name"])
    round_request, round_response = read(state / "vgp/review-submit.request.json"), read(state / "vgp/review-submit.response.json")
    require(round_request["id"] == vgp["case_id"] and round_request["payload"]["previous_round_id"] == previous["round_id"] and round_request["payload"]["items"][0]["candidates"][0]["revision_id"] == asset["revision_id"] and round_response["id"] == vgp["round_id"] and round_response["case_id"] == vgp["case_id"], "Review round is not linked to this candidate and r3 round")
    files = {source.name: source for source in evidence_paths}
    files.update({"aw-summary.json": aw_path, "vgp-summary.json": vgp_path, "vgp-check.json": path(asset["check_receipt"]), "vgp-predecessor.json": state / "vgp/predecessor.json", "vgp-round-request.json": state / "vgp/review-submit.request.json", "vgp-round-response.json": state / "vgp/review-submit.response.json"})
    for name, field in {"aw-godot-summary": "summary", "aw-godot-recipe": "recipe", "aw-godot-runtime-report": "test_report", "aw-godot-snapshot": "snapshot"}.items():
        files[name + ".json"] = path(native[field])
    for name, field in {"aw-delivery-manifest": "aw_manifest", "aw-delivery-technical": "aw_technical", "aw-delivery-selection": "selection", "independent-frozen-inputs": "frozen_inputs"}.items():
        files[name + ".json"] = path(aw[field])
    for name, field in {"vgp-materials": "materials", "vgp-server-verification": "server_verification", "vgp-transport-files": "transport_manifest", "vgp-packed-dependencies": "packed_manifest", "vgp-frozen-files": "logical_frozen"}.items():
        files[name + ".json"] = path(vgp[field])
    destination = (root / args.output).resolve()
    destination.relative_to(root)
    require(destination.is_relative_to(root / "docs/forest-hamlet/revisions"), "Archive must stay in the project revision-evidence directory")
    for name, (projection, source) in projections.items():
        public_json(projection)
        target = destination / name
        require(not target.exists() or read(target) == projection, "Existing public projection differs: " + name)
    for name, source in files.items():
        relative_file(root, source)
        if source.suffix == ".json":
            public_json(read(source))
        target = destination / name
        require(not target.exists() or digest(target) == digest(source), "Existing archive bytes differ: " + name)
    destination.mkdir(parents=True, exist_ok=True)
    artifacts = []
    for name, source in sorted(files.items()):
        target = destination / name
        if not target.exists():
            with target.open("xb") as stream:
                stream.write(source.read_bytes())
        require(digest(target) == digest(source), "Archived copy differs: " + name)
        artifacts.append({"file": name, "source": source.relative_to(root).as_posix(), "sha256": digest(target), "bytes": target.stat().st_size})
    for name, (projection, source) in sorted(projections.items()):
        target = destination / name
        freeze_json(target, projection)
        artifacts.append({"file": name, "source": source.relative_to(root).as_posix(), "source_sha256": digest(source), "public_projection": True, "producer": "tools/forest_hamlet/archive_cloud_tuning_evidence.py", "sha256": digest(target), "bytes": target.stat().st_size})
    audit = {"schema_version": 1, "passed": True, **delivery, "source_summary": aw_path.relative_to(root).as_posix(), "source_summary_sha256": digest(aw_path), "scope": "Independent archive-time verification of the native AW manifest, ZIP bytes, selected run files, verification receipt and current frozen source closure."}
    freeze_json(destination / "aw-delivery-audit.json", audit)
    artifacts.append({"file": "aw-delivery-audit.json", "producer": "tools/forest_hamlet/archive_cloud_tuning_evidence.py", "sha256": digest(destination / "aw-delivery-audit.json"), "bytes": (destination / "aw-delivery-audit.json").stat().st_size})
    validation = {"schema_version": 1, "passed": True, "profile": "cloud-tuning", "run_id": args.run_id, "runtime_fingerprint": technical["runtime_fingerprint"], "technical_evidence": technical, "aw": {"native_run": native["aw_run"], "delivery_id": aw["delivery_id"], "native_source_closure_sha256": native["source_closure_sha256"]}, "vgp": {"asset_id": asset["asset_id"], "revision_id": asset["revision_id"], "parent_revision_id": parent["revision_id"], "round_id": vgp["round_id"], "previous_round_id": previous["round_id"], "ready": True, "review_status": "pending", "decisions_created": 0, "stage_admissions_created": 0}, "artifact_count": len(artifacts), "original_png_count": sum(row["file"].endswith(".png") for row in artifacts), "artifacts": artifacts, "driver": "tools/forest_hamlet/archive_cloud_tuning_evidence.py", "driver_sha256": digest(Path(__file__)), "scope": "Original focused evidence and public receipts only; no raw ingest handles, private credentials, huge native project copies or build log bodies. Validation index and later README are not self-indexed."}
    public_json(validation)
    freeze_json(destination / "validation.json", validation)
    print(json.dumps({"passed": True, "output": destination.relative_to(root).as_posix(), "indexed_artifacts": len(artifacts), "original_pngs": validation["original_png_count"], "total_files_with_validation": len(artifacts) + 1}, ensure_ascii=False))


if __name__ == "__main__":
    main()
