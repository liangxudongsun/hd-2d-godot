#!/usr/bin/env python3
"""Register the HD2D vegetation image/normal pairs in the existing VGP scene.

Uses the installed CLI, appends a concept-design candidate and review round,
and retains exact requests. It does not create decisions or stage admissions.
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


ASSET_KEY = "forest-hamlet-vegetation-sprites"


def safe_id(value: str) -> str:
    if not value or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789-_" for c in value):
        raise ValueError("Run IDs must be lowercase safe directory names")
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, default=Path.cwd())
    parser.add_argument("--run-id", default="forest-hamlet-20261022-vegetation-r1")
    parser.add_argument("--aw-run-id", default="forest-hamlet-20261022-vegetation-r1")
    parser.add_argument("--context-run-id", default="forest-hamlet-20261022-pixel-r2",
                        help="An existing native VGP forest scene registration")
    parser.add_argument("--previous-run-id", help="Previous vegetation candidate, for a successor revision")
    parser.add_argument("--existing-asset-id",
                        help="Reuse a verified image Asset after a failed first ingest; does not set a parent Revision")
    parser.add_argument("--integration-evidence", action="store_true",
                        help="Attach the plant-free cottage GLB, construction manifest and script as supporting scene evidence")
    args = parser.parse_args()
    for value in (args.run_id, args.aw_run_id, args.context_run_id,
                  *([args.previous_run_id] if args.previous_run_id else [])):
        safe_id(value)
    if args.previous_run_id == args.run_id:
        raise ValueError("A successor candidate needs a distinct run ID")
    if args.previous_run_id and args.existing_asset_id:
        raise ValueError("Use either --previous-run-id or --existing-asset-id, not both")
    root = args.project.resolve()
    derived = root / "art/derived/forest-hamlet"
    state = derived / args.run_id / "vgp"
    state.mkdir(parents=True, exist_ok=True)
    context_path = derived / args.context_run_id / "vgp/summary.json"
    context = json.loads(context_path.read_text(encoding="utf-8"))
    for field in ("project_id", "scene_classification_id", "case_id"):
        if not context.get(field):
            raise RuntimeError(f"Context registration lacks {field}")
    freeze_json(state / "context.json", {"run_id": args.context_run_id,
                "summary_sha256": digest(context_path), "summary": context})
    previous = None
    if args.previous_run_id:
        previous_path = derived / args.previous_run_id / "vgp/summary.json"
        previous = json.loads(previous_path.read_text(encoding="utf-8"))
        for field in ("project_id", "scene_classification_id", "case_id"):
            if previous.get(field) != context[field]:
                raise RuntimeError(f"Previous vegetation candidate has a different {field}")
        freeze_json(state / "predecessor.json", {"run_id": args.previous_run_id,
                    "summary_sha256": digest(previous_path), "summary": previous})

    summary_path = derived / args.aw_run_id / "vegetation-summary.json"
    production = json.loads(summary_path.read_text(encoding="utf-8"))
    if production.get("execution_status") != "completed":
        raise RuntimeError("The vegetation production run is not completed")
    if production.get("workflow") != "world.compile":
        raise RuntimeError("Expected the native AW world.compile workflow")
    if digest(root / production["aw_run"]) != production["aw_run_sha256"]:
        raise RuntimeError("Native AW run receipt changed after production")
    preparation_path = root / production["preparation"]
    preparation = json.loads(preparation_path.read_text(encoding="utf-8"))
    manifest_path = root / "assets/forest-hamlet/vegetation/manifest.json"
    if digest(manifest_path) != production["runtime_manifest_sha256"]:
        raise RuntimeError("Vegetation manifest changed after production")
    outputs = production["outputs"]
    for item in outputs:
        for path_field, hash_field in (("runtime", "sha256"), ("normal_runtime", "normal_sha256")):
            if digest(root / item[path_field]) != item[hash_field]:
                raise RuntimeError(f"Runtime vegetation changed after production: {item[path_field]}")

    def execute(label: str, command: list[str], *, immutable: bool = True):
        freeze_json(state / f"{label}.command.json", command)
        receipt = state / f"{label}.response.json"
        if immutable and receipt.exists():
            return json.loads(receipt.read_text(encoding="utf-8"))
        result = subprocess.run(command, cwd=root, capture_output=True, text=True, timeout=300)
        (state / f"{label}.stderr.txt").write_text(result.stderr, encoding="utf-8")
        if result.returncode:
            (state / f"{label}.failed.txt").write_text(result.stdout, encoding="utf-8")
            raise RuntimeError(f"VGP {label} failed ({result.returncode}): {result.stderr or result.stdout}")
        value = decode(result.stdout)
        dump(receipt, value)
        return value

    base = [installed_cli("vgp"), "--project-id", context["project_id"]]

    def command(label: str, operation: str, payload: dict, *, target: str | None = None,
                version: int | None = None, mutation: bool = True):
        body = {"schema_version": 1, "operation": operation, "payload": payload}
        if target:
            body["id"] = target
        if version is not None:
            body["expected_version"] = version
        if mutation:
            body["idempotency_key"] = f"{args.run_id}:{label}:v1"
        path = state / f"{label}.request.json"
        freeze_json(path, body)
        return execute(label, base + ["command", "--input", str(path)], immutable=mutation)

    classification = locate(command("scene-get", "classification.get", {},
                            target=context["scene_classification_id"], mutation=False),
                            {"id", "name", "kind", "version"})
    if classification["id"] != context["scene_classification_id"] or classification["kind"] != "scene":
        raise RuntimeError("Existing scene classification identity did not verify")
    case = locate(command("case-get", "review.get", {}, target=context["case_id"], mutation=False),
                  {"id", "version", "title", "type"}, kind="asset_content")
    if case["id"] != context["case_id"]:
        raise RuntimeError("Existing review Case identity did not verify")
    prior_asset = None
    if previous:
        matches = [x for x in previous.get("assets", []) if x.get("key") == "vegetation"]
        if len(matches) != 1:
            raise RuntimeError("Previous run must contain exactly one vegetation asset")
        prior_asset = matches[0]
        asset_raw = command("asset-get", "asset.get", {}, target=prior_asset["asset_id"], mutation=False)
    elif args.existing_asset_id:
        asset_raw = command("asset-get", "asset.get", {}, target=args.existing_asset_id, mutation=False)
    else:
        asset_raw = command("asset-create", "asset.create", {
            "name": "森林村落 · HD2D 植被图像与空间法线", "type": "image", "asset_key": ASSET_KEY,
            "category": "forest-hamlet", "tags": ["forest-hamlet", "HD2D", "vegetation", "normal-map", "candidate"]})
    asset = locate(asset_raw, {"id", "version", "name", "type"}, kind="image")
    if asset.get("asset_key") != ASSET_KEY or asset.get("archived"):
        raise RuntimeError("Vegetation Asset key or archived state did not verify")
    if args.existing_asset_id and asset["id"] != args.existing_asset_id:
        raise RuntimeError("Explicit existing vegetation Asset identity did not verify")
    parent_id = None
    if prior_asset:
        if asset["id"] != prior_asset["asset_id"]:
            raise RuntimeError("Previous vegetation Asset identity did not verify")
        parents = [x for x in asset_raw.get("revisions", []) if x.get("id") == prior_asset["revision_id"]]
        if len(parents) != 1 or parents[0].get("asset_id") != asset["id"] or parents[0].get("stage") != "concept_design":
            raise RuntimeError("Previous vegetation Revision belongs to a different asset or stage")
        parent_id = parents[0]["id"]

    # The VGP ingest API archives files under their basename. Preserve every
    # original byte in a versioned, unambiguous bundle; prepared and runtime
    # images often share basenames but must not overwrite one another.
    bundle = state / "bundle"
    bundle.mkdir(exist_ok=True)
    files: dict[str, Path] = {}
    frozen: list[dict] = []

    def add(path: Path, alias: str) -> str:
        path = path.resolve()
        relative = path.relative_to(root).as_posix()
        if "/" in alias or "\\" in alias or alias in ("", ".", ".."):
            raise ValueError(f"Unsafe bundle alias: {alias}")
        destination = bundle / alias
        row = {"source": relative, "archive_name": alias, "sha256": digest(path), "bytes": path.stat().st_size}
        if alias in files:
            existing = next(x for x in frozen if x["archive_name"] == alias)
            if existing["sha256"] != row["sha256"]:
                raise RuntimeError(f"Ambiguous VGP bundle filename: {alias}")
            return alias
        if destination.exists() and digest(destination) != row["sha256"]:
            raise RuntimeError(f"Frozen bundle file changed: {alias}; use a new run ID")
        if not destination.exists():
            shutil.copyfile(path, destination)
        files[alias] = destination
        frozen.append(row)
        return alias

    originals: list[str] = []
    for item in preparation["assets"]:
        name = item["name"]
        originals.append(add(root / item["color"], f"prepared-{name}.png"))
        originals.append(add(root / item["normal"], f"authored-{name}-normal.png"))
    for index, path in enumerate(production.get("source_files", [])):
        source = root / path
        originals.append(add(source, f"source-{index:02d}-" + source.name))
    # The production summary lists the exact script/recipe/source dependencies
    # that were used. Include those, without implying AW generated the normals.
    dependencies = [summary_path, preparation_path, manifest_path,
                    root / production["aw_run"], root / production["recipe"],
                    root / "tools/forest_hamlet/process_vegetation_aw.py",
                    root / "tools/forest_hamlet/register_vegetation_vgp.py"]
    if production.get("palette"):
        dependencies.append(root / production["palette"]["path"])
    for path in dependencies:
        add(path, "evidence-" + path.name)
    integration_context = []
    if args.integration_evidence:
        for path_string in (
            "assets/forest-hamlet/models/cottage_without_plants.glb",
            "art/inputs/forest-hamlet/blender-vegetation-r1/manifest.json",
            "tools/forest_hamlet/build_cottage_without_plants.py",
        ):
            source = root / path_string
            alias = add(source, "integration-" + source.name)
            integration_context.append({"source": path_string, "archive_name": alias,
                                        "sha256": digest(source),
                                        "role": "supporting scene integration evidence; not a primary image output or independent model review"})
    members = []
    for item in outputs:
        name = item["name"]
        width, height = item["size"]
        for role, field, original in (("color", "runtime", f"prepared-{name}.png"),
                                      ("normal", "normal_runtime", f"authored-{name}-normal.png")):
            alias = add(root / item[field], Path(item[field]).name)
            member_id = f"{name.replace('_', '-')}-{role}"
            if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", member_id):
                raise RuntimeError(f"Invalid native VGP material member ID: {member_id}")
            members.append({"id": member_id, "name": f"{name} {role}", "path": alias,
                            "original_paths": [original],
                            "processing_target": {"width": width, "height": height, "format": "png"}})
    freeze_json(state / "vegetation.frozen-files.json", frozen)
    originals = list(dict.fromkeys(originals))
    primary_names = {item["path"] for item in members}
    payload = {
        "kind": "candidate", "stage": "concept_design",
        "materials": {"members": members, "original_paths": originals,
                      "dependency_paths": [name for name in files if name not in primary_names | set(originals)]},
        "source": {"tool": "Asset Workbench + authored geometric normal recipe", "workflow": "world.compile",
                   "run": production["aw_run"], "producer_version": production.get("producer_version"),
                   "normal_policy": "Independent authored relief; OpenGL tangent vectors bypass color palette processing",
                   "aesthetic_approval": "pending"},
        "external_report": {"authority": "caller_reported", "workflow": "AW world.compile (color only)",
                            "execution_status": "completed", "aw_run_sha256": production["aw_run_sha256"],
                            "normal_workflow": production.get("normal_workflow", "authored geometric relief"),
                            "integration_context": integration_context,
                            "outputs": {Path(item[field]).name: {"width": item["size"][0], "height": item["size"][1],
                                        "paired_alpha_equal": True, "role": role}
                                        for item in outputs for role, field in (("color", "runtime"), ("normal", "normal_runtime"))}},
        "specification": {"purpose": "HD2D camera-facing vegetation sprites for both forest-hamlet scene entrances",
                          "aesthetic_approval": "pending"},
        "metadata": {"production_status": "externally_processed", "review_status": "pending",
                     "stage_note": "Technical processing is recorded as a concept candidate. No prior-stage decision, aesthetic approval or engine-ready admission is implied."}}
    if parent_id:
        payload["parent_revision_ids"] = [parent_id]
        payload["source"]["previous_revision_id"] = parent_id
    payload_path = state / "vegetation-ingest.payload.json"
    freeze_json(payload_path, payload)
    ingest_command = base + ["ingest", "--asset-id", asset["id"], "--key", f"{args.run_id}:vegetation:ingest:v1",
                             "--input", str(payload_path)]
    for file in files.values():
        ingest_command += ["--file", str(file)]
    revision = locate(execute("vegetation-ingest", ingest_command), {"id", "asset_id", "kind", "files"})
    check = command("vegetation-check", "asset.revision.check", {}, target=revision["id"], mutation=False)
    if check.get("ready") is not True or check.get("issues"):
        raise RuntimeError("Vegetation Revision is not ready for review; inspect the native check receipt")
    if not previous:
        saved = state / "vegetation-classify.request.json"
        if saved.exists():
            execute("vegetation-classify", base + ["command", "--input", str(saved)])
        else:
            current = locate(command("asset-current-get", "asset.get", {}, target=asset["id"], mutation=False),
                             {"id", "version", "name", "type"}, kind="image")
            command("vegetation-classify", "asset.classify", {"scene_ids": [classification["id"]], "level_ids": []},
                    target=asset["id"], version=current["version"])

    prior_state = derived / (args.previous_run_id or args.context_run_id) / "vgp"
    prior_round = json.loads((prior_state / "review-submit.response.json").read_text(encoding="utf-8"))
    if prior_round.get("case_id") != case["id"] or not prior_round.get("id"):
        raise RuntimeError("Prior review-round receipt does not verify against the existing Case")
    submit_payload = {"previous_round_id": prior_round["id"], "items": [{
        "subject_key": "forest-hamlet-vegetation", "title": "HD2D 植被图像与法线",
        "requirements": "Review all ten image/normal pairs in the near and overview scenes: silhouette, pixel scale, lighting, alpha alignment and complete replacement of volumetric plant models. Technical checks do not grant aesthetic approval.",
        "candidates": [{"revision_id": revision["id"], "label": args.run_id}]}]}
    saved_submit = state / "review-submit.request.json"
    if saved_submit.exists():
        saved = json.loads(saved_submit.read_text(encoding="utf-8"))
        if saved.get("id") != case["id"] or saved.get("payload") != submit_payload:
            raise RuntimeError("Saved review submission differs; use a new run ID")
        submitted = execute("review-submit", base + ["command", "--input", str(saved_submit)])
    else:
        case = locate(command("case-before-submit-get", "review.get", {}, target=case["id"], mutation=False),
                      {"id", "version", "title", "type"}, kind="asset_content")
        submitted = command("review-submit", "review.submit", submit_payload, target=case["id"], version=case["version"])
    result = {"schema_version": 1, "project_id": context["project_id"], "scene_classification_id": classification["id"],
              "case_id": case["id"], "round_id": submitted["id"], "previous_round_id": prior_round["id"],
              "context_run_id": args.context_run_id,
              "assets": [{"key": "vegetation", "asset_id": asset["id"], "revision_id": revision["id"],
                          "stage": "concept_design", "main_output_count": len(members), "status": "pending_review",
                          "check_receipt": (state / "vegetation-check.response.json").relative_to(root).as_posix()}],
              "review_status": "pending", "decisions_created": 0, "stage_admissions_created": 0,
              "supporting_integration_files": integration_context,
              "note": "Native VGP image candidate and review-round submission completed. AW compiled colors only; authored linear normal vectors were paired and validated separately. No approval was synthesized."}
    if parent_id:
        result["previous_run_id"] = args.previous_run_id
        result["assets"][0]["previous_revision_id"] = parent_id
    if args.existing_asset_id:
        result["existing_asset_id_reused"] = args.existing_asset_id
    dump(state / "summary.json", result)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(str(error), file=sys.stderr)
        raise
