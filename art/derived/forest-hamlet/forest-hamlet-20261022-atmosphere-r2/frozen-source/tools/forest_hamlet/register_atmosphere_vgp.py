#!/usr/bin/env python3
"""Register the snow/normal/region image set and atmosphere evidence in VGP.

Native VGP candidate + review round only. This never approves a candidate,
admits a later stage, overwrites the vegetation Asset, or starts a service.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

from register_vgp import decode, digest, dump, freeze_json, installed_cli, locate
from process_atmosphere_aw import native_godot_evidence, verify_delivery_archive


ASSET_KEY = "forest-hamlet-snow-atmosphere"
DEFAULT_RUN = "forest-hamlet-20261022-atmosphere-r2"


def safe_id(value: str) -> str:
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,95}", value):
        raise ValueError("Run IDs must be safe lowercase directory names")
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, default=Path.cwd())
    parser.add_argument("--run-id", default=DEFAULT_RUN)
    parser.add_argument("--aw-run-id", default=DEFAULT_RUN)
    parser.add_argument("--context-run-id", default="forest-hamlet-20261022-vegetation-r2-review")
    parser.add_argument("--previous-run-id", help="Append a successor to an existing snow-atmosphere Asset")
    parser.add_argument("--existing-asset-id", help="Resume a verified Asset after a failed first ingest")
    args = parser.parse_args()
    for value in (args.run_id, args.aw_run_id, args.context_run_id, *([args.previous_run_id] if args.previous_run_id else [])):
        safe_id(value)
    if args.previous_run_id == args.run_id or (args.previous_run_id and args.existing_asset_id):
        raise ValueError("Use a new run ID and only one predecessor/recovery selector")
    root = args.project.resolve()
    derived = root / "art/derived/forest-hamlet"
    state = derived / args.run_id / "vgp"
    state.mkdir(parents=True, exist_ok=True)
    context_path = derived / args.context_run_id / "vgp/summary.json"
    context = json.loads(context_path.read_text(encoding="utf-8"))
    for field in ("project_id", "scene_classification_id", "case_id"):
        if not context.get(field):
            raise RuntimeError(f"Context registration lacks {field}")
    freeze_json(state / "context.json", {"run_id": args.context_run_id, "summary_sha256": digest(context_path), "summary": context})
    previous = None
    if args.previous_run_id:
        previous_path = derived / args.previous_run_id / "vgp/summary.json"
        previous = json.loads(previous_path.read_text(encoding="utf-8"))
        for field in ("project_id", "scene_classification_id", "case_id"):
            if previous.get(field) != context[field]:
                raise RuntimeError(f"Previous atmosphere candidate has a different {field}")
        freeze_json(state / "predecessor.json", {"run_id": args.previous_run_id, "summary_sha256": digest(previous_path), "summary": previous})

    production_path = derived / args.aw_run_id / "atmosphere-summary.json"
    production = json.loads(production_path.read_text(encoding="utf-8"))
    if production.get("execution_status") != "completed" or production.get("workflow") != "delivery.export+delivery.verify":
        raise RuntimeError("Expected a completed native AW delivery export + verification")
    for field in ("aw_manifest", "aw_archive", "aw_technical", "selection", "verify_receipt", "frozen_inputs"):
        if digest(root / production[field]) != production[field + "_sha256"]:
            raise RuntimeError("Native AW delivery/provenance evidence changed: " + field)
    if digest(root / production["runtime_manifest"]) != production["runtime_manifest_sha256"]:
        raise RuntimeError("Backdrop manifest changed after delivery")
    if production.get("human_aesthetic_approval") != "pending":
        raise RuntimeError("This registration may not manufacture aesthetic approval")
    native_paths, native_summary = native_godot_evidence(root, root / production["native_godot"]["summary"])
    if native_summary != production["native_godot"]:
        raise RuntimeError("Native Godot evidence differs from the delivery summary")
    delivery = verify_delivery_archive(root, root / production["aw_directory"], production["aw_delivery_files"],
                                      native_summary, args.aw_run_id, production["request_id"])
    if any(production.get(field) != value for field, value in delivery.items()):
        raise RuntimeError("Native delivery manifest/ZIP identity differs from the production summary")
    native_verify = json.loads((root / production["verify_receipt"]).read_text(encoding="utf-8"))

    def verified(value):
        if isinstance(value, dict):
            if value.get("status") == "verified" and value.get("delivery_id") == production["delivery_id"]:
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

    verification = verified(native_verify)
    if (verification is None or verification.get("sha256") != production["aw_archive_sha256"]
            or verification.get("manifest") != json.loads((root / production["aw_manifest"]).read_text(encoding="utf-8"))):
        raise RuntimeError("Native delivery verification receipt does not bind this exact package")
    closure = production["closure"]
    if not {path.relative_to(root).as_posix() for path in native_paths} <= {row["source"] for row in closure}:
        raise RuntimeError("The independent source closure omitted native Godot evidence")
    frozen_inputs = json.loads((root / production["frozen_inputs"]).read_text(encoding="utf-8"))
    if frozen_inputs.get("files") != closure or frozen_inputs.get("aw_delivery_files") != production["aw_delivery_files"]:
        raise RuntimeError("Independent frozen input list differs from the delivery summary")
    for row in closure:
        if digest(root / row["source"]) != row["sha256"]:
            raise RuntimeError(f"Production closure changed: {row['source']}")
        if digest(root / row["path"]) != row["sha256"]:
            raise RuntimeError(f"Independent frozen source changed: {row['path']}")
    outputs = production["outputs"]
    if {item["name"] for item in outputs} != {"color", "normal", "regions"} or len(outputs) != 3:
        raise RuntimeError("Exactly the three primary technical PNGs are required")
    for item in outputs:
        if digest(root / item["runtime"]) != item["sha256"]:
            raise RuntimeError("Runtime output changed: " + item["runtime"])
        matching = [row for row in production["aw_delivery_files"] if row["source"] == item["runtime"] and row["role"] == "runtime" and row["sha256"] == item["sha256"]]
        if len(matching) != 1:
            raise RuntimeError("A primary PNG lacks an exact native delivery mapping: " + item["runtime"])

    native_cli = installed_cli("vgp")

    def execute(label: str, command: list[str], *, immutable: bool = True):
        # Record portable argv; the executable is resolved locally at execution.
        freeze_json(state / f"{label}.command.json", command)
        receipt = state / f"{label}.response.json"
        if immutable and receipt.exists():
            return json.loads(receipt.read_text(encoding="utf-8"))
        result = subprocess.run([native_cli, *command[1:]], cwd=root, capture_output=True, text=True, timeout=300)
        (state / f"{label}.stderr.txt").write_text(result.stderr, encoding="utf-8")
        if result.returncode:
            (state / f"{label}.failed.txt").write_text(result.stdout, encoding="utf-8")
            raise RuntimeError(f"VGP {label} failed ({result.returncode}): {result.stderr or result.stdout}")
        value = decode(result.stdout)
        dump(receipt, value)
        return value

    base = ["vgp", "--project-id", context["project_id"]]

    def command(label: str, operation: str, payload: dict, *, target: str | None = None,
                version: int | None = None, mutation: bool = True):
        body = {"schema_version": 1, "operation": operation, "payload": payload}
        if target:
            body["id"] = target
        if version is not None:
            body["expected_version"] = version
        if mutation:
            body["idempotency_key"] = f"{args.run_id}:{label}:v1"
        request = state / f"{label}.request.json"
        freeze_json(request, body)
        return execute(label, base + ["command", "--input", request.relative_to(root).as_posix()], immutable=mutation)

    classification = locate(command("scene-get", "classification.get", {}, target=context["scene_classification_id"], mutation=False), {"id", "name", "kind", "version"})
    if classification["id"] != context["scene_classification_id"] or classification["kind"] != "scene":
        raise RuntimeError("Existing scene classification did not verify")
    case = locate(command("case-get", "review.get", {}, target=context["case_id"], mutation=False), {"id", "version", "title", "type"}, kind="asset_content")
    if case["id"] != context["case_id"]:
        raise RuntimeError("Existing review Case did not verify")
    prior_asset = None
    if previous:
        matches = [x for x in previous.get("assets", []) if x.get("key") == "snow-atmosphere"]
        if len(matches) != 1:
            raise RuntimeError("Previous run must contain exactly one snow-atmosphere Asset")
        prior_asset = matches[0]
        asset_raw = command("asset-get", "asset.get", {}, target=prior_asset["asset_id"], mutation=False)
    elif args.existing_asset_id:
        asset_raw = command("asset-get", "asset.get", {}, target=args.existing_asset_id, mutation=False)
    else:
        asset_raw = command("asset-create", "asset.create", {
            "name": "林间小村 · HD2D 雪山远景与动态光照", "type": "image", "asset_key": ASSET_KEY,
            "category": "forest-hamlet", "tags": ["forest-hamlet", "HD2D", "snow", "normal-map", "cloud-shadow", "global-light-variation", "candidate"]})
    asset = locate(asset_raw, {"id", "version", "name", "type"}, kind="image")
    if asset.get("asset_key") != ASSET_KEY or asset.get("archived"):
        raise RuntimeError("Snow-atmosphere Asset key or archived state did not verify")
    if args.existing_asset_id and asset["id"] != args.existing_asset_id:
        raise RuntimeError("Explicit Asset identity did not verify")
    parent_id = None
    if prior_asset:
        if asset["id"] != prior_asset["asset_id"]:
            raise RuntimeError("Previous atmosphere Asset identity did not verify")
        parents = [x for x in asset_raw.get("revisions", []) if x.get("id") == prior_asset["revision_id"]]
        if len(parents) != 1 or parents[0].get("asset_id") != asset["id"] or parents[0].get("stage") != "concept_design":
            raise RuntimeError("Previous atmosphere Revision belongs to a different Asset or stage")
        parent_id = parents[0]["id"]

    bundle = state / "bundle"
    bundle.mkdir(exist_ok=True)
    files: dict[str, Path] = {}
    frozen: list[dict] = []

    def add(path: Path, alias: str) -> str:
        path = path.resolve()
        relative = path.relative_to(root).as_posix()
        if "/" in alias or "\\" in alias or alias in ("", ".", ".."):
            raise ValueError("Unsafe VGP archive alias")
        destination = bundle / alias
        row = {"source": relative, "archive_name": alias, "sha256": digest(path), "bytes": path.stat().st_size}
        if alias in files:
            previous_file = next(x for x in frozen if x["archive_name"] == alias)
            if previous_file["sha256"] != row["sha256"]:
                raise RuntimeError("Ambiguous VGP bundle filename: " + alias)
            return alias
        if destination.exists() and digest(destination) != row["sha256"]:
            raise RuntimeError("Frozen VGP bundle file changed; use a new run ID: " + alias)
        if not destination.exists():
            shutil.copyfile(path, destination)
        files[alias] = destination
        frozen.append(row)
        return alias

    # Use short unique basenames because VGP ingest archives by basename.
    source_aliases: dict[str, str] = {}
    for index, row in enumerate(closure):
        source = row["source"]
        source_aliases[source] = add(root / source, f"closure-{index:03d}-" + Path(source).name)
    originals = [source_aliases["art/inputs/forest-hamlet/snow-r1/source/snow-master.png"]]
    members = []
    for item in outputs:
        alias = add(root / item["runtime"], "snow-" + item["name"] + ".png")
        members.append({"id": "snow-" + item["name"], "name": "Snow backdrop " + item["name"], "path": alias,
                        "original_paths": originals,
                        "processing_target": {"width": item["size"][0], "height": item["size"][1], "format": "png"}})
    extra = [production_path, root / production["aw_manifest"], root / production["aw_archive"],
             root / production["aw_technical"], root / production["selection"], root / production["frozen_inputs"],
             root / production["verify_receipt"], root / "tools/forest_hamlet/register_atmosphere_vgp.py"]
    for index, path in enumerate(extra):
        add(path, f"native-{index:02d}-" + path.name)
    freeze_json(state / "atmosphere.frozen-files.json", frozen)
    primary = {row["path"] for row in members}
    dependencies = [name for name in files if name not in primary | set(originals)]
    payload = {
        "kind": "candidate", "stage": "concept_design",
        "materials": {"members": members, "original_paths": originals, "dependency_paths": dependencies},
        "source": {"tool": "ImageGen master + authored geometric normals + Asset Workbench", "workflow": "godot.verify+" + production["workflow"],
                   "run": native_summary["aw_run"], "producer_version": production.get("producer_version"),
                   "normal_policy": "Manually annotated low-frequency geometric facets; no brightness-to-height conversion; AW delivers unchanged PNGs from its verified Godot run",
                   "aesthetic_approval": "pending"},
        "external_report": {"authority": "caller_reported", "workflow": "AW godot.verify + delivery export + delivery verify", "execution_status": "completed",
                            "aw_delivery_manifest_sha256": production["aw_manifest_sha256"], "aw_delivery_archive_sha256": production["aw_archive_sha256"],
                            "normal_workflow": "authored low-frequency tangent-space facets",
                            "gpu_evidence_scope": "Captured and checked separately by project tools; independently frozen and included as dependencies, not AW-rendered or AW-verified GPU output",
                            "outputs": {"snow-" + item["name"] + ".png": {"width": item["size"][0], "height": item["size"][1], "role": item["name"]} for item in outputs}},
        "specification": {"purpose": "Soft distant HD2D snow backdrop with restrained normal relighting, world-relative parallax, native moving cloud shadows, independent irregular global light variation, volumetric light and Glow",
                          "aesthetic_approval": "pending", "parallax_scope": "one intact color board; not independently separated mountain layers"},
        "metadata": {"production_status": "externally_processed", "review_status": "pending",
                     "stage_note": "Native freeze and technical verification do not imply human aesthetic acceptance or engine-ready stage admission."}}
    if parent_id:
        payload["parent_revision_ids"] = [parent_id]
        payload["source"]["previous_revision_id"] = parent_id
    payload_path = state / "atmosphere-ingest.payload.json"
    freeze_json(payload_path, payload)
    ingest = base + ["ingest", "--asset-id", asset["id"], "--key", f"{args.run_id}:snow-atmosphere:ingest:v1", "--input", payload_path.relative_to(root).as_posix()]
    for path in files.values():
        ingest += ["--file", path.relative_to(root).as_posix()]
    revision = locate(execute("atmosphere-ingest", ingest), {"id", "asset_id", "kind", "files"})
    check = command("atmosphere-check", "asset.revision.check", {}, target=revision["id"], mutation=False)
    if check.get("ready") is not True or check.get("issues"):
        raise RuntimeError("Atmosphere Revision is not ready for review; inspect the native check")
    if not previous:
        saved = state / "atmosphere-classify.request.json"
        if saved.exists():
            execute("atmosphere-classify", base + ["command", "--input", saved.relative_to(root).as_posix()])
        else:
            current = locate(command("asset-current-get", "asset.get", {}, target=asset["id"], mutation=False), {"id", "version", "name", "type"}, kind="image")
            command("atmosphere-classify", "asset.classify", {"scene_ids": [classification["id"]], "level_ids": []}, target=asset["id"], version=current["version"])
    prior_state = derived / (args.previous_run_id or args.context_run_id) / "vgp"
    prior_round = json.loads((prior_state / "review-submit.response.json").read_text(encoding="utf-8"))
    if prior_round.get("case_id") != case["id"] or not prior_round.get("id"):
        raise RuntimeError("Prior review-round receipt does not verify against the existing Case")
    submit_payload = {"previous_round_id": prior_round["id"], "items": [{
        "subject_key": "forest-hamlet-snow-atmosphere", "title": "雪山远景、动态云影、全局光照与体积光",
        "requirements": "Review the unchanged soft distant snow artwork, geometric normal response, camera-relative parallax, true cloud shadows across different receivers, independent irregular global light variation, volumetric light and restrained Glow. Technical checks do not grant aesthetic approval.",
        "candidates": [{"revision_id": revision["id"], "label": args.run_id}]}]}
    saved_submit = state / "review-submit.request.json"
    if saved_submit.exists():
        saved = json.loads(saved_submit.read_text(encoding="utf-8"))
        if saved.get("id") != case["id"] or saved.get("payload") != submit_payload:
            raise RuntimeError("Saved review submission differs; use a new run ID")
        submitted = execute("review-submit", base + ["command", "--input", saved_submit.relative_to(root).as_posix()])
    else:
        case = locate(command("case-before-submit-get", "review.get", {}, target=case["id"], mutation=False), {"id", "version", "title", "type"}, kind="asset_content")
        submitted = command("review-submit", "review.submit", submit_payload, target=case["id"], version=case["version"])
    result = {"schema_version": 1, "project_id": context["project_id"], "scene_classification_id": classification["id"],
              "case_id": case["id"], "round_id": submitted["id"], "previous_round_id": prior_round["id"], "context_run_id": args.context_run_id,
              "assets": [{"key": "snow-atmosphere", "asset_key": ASSET_KEY, "asset_id": asset["id"], "revision_id": revision["id"],
                          "stage": "concept_design", "main_output_count": len(members), "status": "pending_review",
                          "check_receipt": (state / "atmosphere-check.response.json").relative_to(root).as_posix()}],
              "review_status": "pending", "decisions_created": 0, "stage_admissions_created": 0,
              "native_godot": native_summary,
              "aw_delivery": {key: production[key] for key in ("delivery_id", "aw_manifest", "aw_manifest_sha256", "aw_archive", "aw_archive_sha256", "verify_receipt", "verify_receipt_sha256")},
              "note": "Native VGP candidate/round completed. AW godot.verify ran the runtime test; AW delivery export/verify packaged selected frozen-run files. External GPU evidence and authored sources have a separate project SHA256 freeze and are included in the candidate dependencies. AW did not draw art/normals or render/verify the external GPU captures. No aesthetic approval synthesized."}
    if parent_id:
        result["previous_run_id"] = args.previous_run_id
        result["assets"][0]["previous_revision_id"] = parent_id
    if args.existing_asset_id:
        result["existing_asset_id_reused"] = args.existing_asset_id
    freeze_json(state / "summary.json", result)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
