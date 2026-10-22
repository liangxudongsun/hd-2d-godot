#!/usr/bin/env python3
"""Run native AW godot.verify against an immutable project-owned snapshot.

Only source closure copies, native receipts and summaries are written. Existing
scene/assets are not changed; no installation, service, export or art approval.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

from register_vgp import decode, digest, freeze_json, installed_cli
from process_atmosphere_aw import DEFAULT_RUN, NATIVE_TOOL_SOURCES, ensure_config, freeze_text, safe_id
from atmosphere_workflow_profiles import native_test_spec, profile_spec


COPY_ROOTS = ("assets", "scripts", "scenes", "shaders", "tests")
EXCLUDED_PARTS = {".git", ".godot", ".xdg", "build", "node_modules", "__pycache__"}
TEST_SCRIPT = "tests/forest_hamlet/atmosphere_runtime.gd"
ARTIFACT = "atmosphere-runtime-report.json"


def closure(root: Path, extra_sources: tuple = (), test_script: str = TEST_SCRIPT) -> list[Path]:
    files = {root / "project.godot"}
    for name in COPY_ROOTS:
        directory = root / name
        if not directory.is_dir():
            raise RuntimeError("Missing source directory: " + name)
        for path in directory.rglob("*"):
            relative = path.relative_to(root)
            if path.is_file() and not (set(relative.parts) & EXCLUDED_PARTS) and path.name != ".gdignore":
                files.add(path)
    for path in (root / "tools").rglob("*.gd"):
        if not (set(path.relative_to(root).parts) & EXCLUDED_PARTS):
            files.add(path)
    # Preserve the exact external GPU capture/analysis orchestration as source
    # inputs. godot.verify still executes only the explicit headless GD test.
    files.update(root / relative for relative in (*NATIVE_TOOL_SOURCES, *extra_sources))
    for path in files:
        if not path.is_file() or path.is_symlink():
            raise RuntimeError("Native snapshot requires regular source files: " + path.relative_to(root).as_posix())
        path.resolve().relative_to(root)
    if root / test_script not in files:
        raise RuntimeError("Atmosphere runtime test is absent from the snapshot closure")
    return sorted(files)


def verify_rows(root: Path, project: Path, rows: list[dict]) -> None:
    for row in rows:
        if digest(root / row["source"]) != row["sha256"]:
            raise RuntimeError("Runtime source changed after snapshot: " + row["source"])
        if digest(project / row["source"]) != row["sha256"]:
            raise RuntimeError("Immutable native snapshot changed: " + row["source"])
    actual = {path.relative_to(project).as_posix() for path in project.rglob("*") if path.is_file() or path.is_symlink()}
    expected = {row["source"] for row in rows}
    if actual != expected:
        raise RuntimeError("Native source snapshot has unexpected or missing files")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, default=Path.cwd())
    parser.add_argument("--profile", choices=["atmosphere", "cloud-tuning"], default="atmosphere")
    parser.add_argument("--run-id")
    parser.add_argument("--snapshot-id")
    parser.add_argument("--config")
    parser.add_argument("--godot", help="Existing Godot executable; defaults to installed godot")
    args = parser.parse_args()
    spec = profile_spec(args.profile)
    args.run_id = args.run_id or spec["run_id"]
    args.snapshot_id = args.snapshot_id or spec["snapshot_id"]
    args.config = args.config or spec["config"]
    safe_id(args.run_id)
    safe_id(args.snapshot_id)
    root = args.project.resolve()
    config = ensure_config(root, args.config, args.profile)
    inputs = root / "art/inputs/forest-hamlet" / args.snapshot_id
    project_copy = inputs / "project"
    state = root / "art/derived/forest-hamlet" / args.run_id / "native-godot"
    output = root / "art/derived/workbench/godot" / args.run_id
    if output.is_relative_to(inputs) or inputs.is_relative_to(output):
        raise RuntimeError("Native input snapshot and workflow output must not contain one another")
    inputs.mkdir(parents=True, exist_ok=True)
    state.mkdir(parents=True, exist_ok=True)
    # The original Godot project must not scan this nested project. The copied
    # project's own root has no .gdignore, so AW can import it independently.
    freeze_text(inputs / ".gdignore", "")
    paths = closure(root, spec["extra_sources"], spec["test_script"])
    rows = [{"source": path.relative_to(root).as_posix(), "snapshot": "project/" + path.relative_to(root).as_posix(),
             "sha256": digest(path), "bytes": path.stat().st_size} for path in paths]
    files_identity = {row["source"]: row["sha256"] for row in rows}
    snapshot_sha = hashlib.sha256(json.dumps(files_identity, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    snapshot = {"schema_version": 1, "scope": "Explicit selected project directories plus declared validation-tool sources; excludes art/build/editor caches", "file_count": len(rows),
                "total_bytes": sum(row["bytes"] for row in rows), "sha256": snapshot_sha, "files": rows,
                "driver": "tools/forest_hamlet/verify_atmosphere_godot_aw.py", "driver_sha256": digest(Path(__file__))}
    snapshot_path = inputs / "snapshot.json"
    freeze_json(snapshot_path, snapshot)
    for row in rows:
        source = root / row["source"]
        destination = inputs / row["snapshot"]
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            if digest(destination) != row["sha256"]:
                raise RuntimeError("An existing native snapshot file differs; choose a new snapshot ID: " + row["source"])
        else:
            shutil.copyfile(source, destination)
    verify_rows(root, project_copy, rows)
    recipe = {"schema_version": 1, "project": "project", "files": [row["snapshot"] for row in rows],
              "engine_version": "4.7.2", "tests": [native_test_spec(args.profile)]}
    recipe_path = inputs / "godot-verify.recipe.json"
    freeze_json(recipe_path, recipe)
    native_cli = installed_cli("aw")
    godot = Path(args.godot).expanduser().resolve(strict=True) if args.godot else Path(installed_cli("godot")).resolve(strict=True)
    if not godot.is_file() or not os.access(godot, os.X_OK):
        raise RuntimeError("The selected existing Godot executable is unavailable")
    env = os.environ.copy()
    env["PATH"] = os.pathsep.join([str(godot.parent), str(Path(native_cli).parent), env.get("PATH", "")])
    # This is the exact portable argv executed, with the selected binary's
    # directory prepended only in the child process environment.
    base = ["aw", "--project", ".", "--project-config", config.relative_to(root).as_posix()]

    def execute(label: str, command: list[str]) -> dict:
        freeze_json(state / f"{label}.command.json", command)
        result = subprocess.run([native_cli, *command[1:]], cwd=root, env=env, capture_output=True, text=True, timeout=600)
        if result.returncode:
            freeze_text(state / f"{label}.failed.stdout.txt", result.stdout)
            freeze_text(state / f"{label}.failed.stderr.txt", result.stderr)
            raise RuntimeError(f"Native AW {label} failed ({result.returncode}): {result.stderr or result.stdout}")
        value = decode(result.stdout)
        freeze_json(state / f"{label}.response.json", value)
        return value

    if not output.exists():
        execute("validate", base + ["workflow", "validate", "godot.verify", "--input", recipe_path.relative_to(root).as_posix(), "--json"])
        execute("run", base + ["workflow", "run", "godot.verify", "--input", recipe_path.relative_to(root).as_posix(),
                              "--output", output.relative_to(root).as_posix(), "--godot", godot.name, "--json"])
    # A completed immutable run is checked and reused, never blindly resumed.
    # An incomplete native run must be investigated before choosing recovery.
    run_path = output / "run.json"
    record = json.loads(run_path.read_text(encoding="utf-8"))
    if record.get("status") != "completed" or record.get("workflow") != "godot.verify":
        raise RuntimeError("Existing native Godot run is incomplete or has a different workflow; it was not retried")
    observed = record.get("resources", {}).get("godot", {})
    if not str(observed.get("version", "")).startswith("4.7.2.") or observed.get("sha256") != digest(godot):
        raise RuntimeError("Native AW Godot engine identity/version differs from the selected installed binary")
    input_spec = output / "inputs/input.json"
    if json.loads(input_spec.read_text(encoding="utf-8")) != recipe:
        raise RuntimeError("Native workflow frozen recipe differs from the declared recipe")
    for row in rows:
        frozen = output / "inputs" / row["snapshot"]
        if digest(frozen) != row["sha256"]:
            raise RuntimeError("Native workflow frozen source differs: " + row["source"])
    reports = [path for path in output.rglob(spec["artifact"])
               if not ({"inputs", "project"} & set(path.relative_to(output).parts))]
    if len(reports) != 1:
        raise RuntimeError(f"Expected exactly one native runtime test artifact, got {len(reports)}")
    report_path = reports[0]
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if report.get("passed") is not True or not report.get("checks") or report.get("failures"):
        raise RuntimeError("Native AW-run Godot atmosphere test has not passed")
    verify_rows(root, project_copy, rows)
    summary = {
        "schema_version": 1, "run_id": args.run_id, "profile": args.profile, "workflow": "godot.verify", "execution_status": "completed",
        "aw_run": run_path.relative_to(root).as_posix(), "aw_run_sha256": digest(run_path),
        "recipe": recipe_path.relative_to(root).as_posix(), "recipe_sha256": digest(recipe_path),
        "snapshot": snapshot_path.relative_to(root).as_posix(), "snapshot_sha256": digest(snapshot_path),
        "source_closure_sha256": snapshot_sha, "file_count": len(rows), "total_bytes": snapshot["total_bytes"],
        "native_frozen_recipe": input_spec.relative_to(root).as_posix(), "native_frozen_recipe_sha256": digest(input_spec),
        "test_report": report_path.relative_to(root).as_posix(), "test_report_sha256": digest(report_path),
        "test_checks": len(report["checks"]), "engine_version": observed["version"], "engine_sha256": observed["sha256"],
        "producer_version": record.get("producer_version"), "driver_sha256": digest(Path(__file__)),
        "rendered": False, "aesthetic_approval": "pending",
        "scope": "Actual installed AW godot.verify imports the frozen project and runs the runtime test with an explicit success marker; actual GPU artwork evidence is captured separately."
    }
    summary_path = state / "summary.json"
    freeze_json(summary_path, summary)
    print(json.dumps({"status": "completed", "summary": summary_path.relative_to(root).as_posix(),
                      "aw_run": summary["aw_run"], "recipe": summary["recipe"], "snapshot": summary["snapshot"],
                      "test_report": summary["test_report"], "test_checks": summary["test_checks"],
                      "file_count": len(rows), "total_bytes": snapshot["total_bytes"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
