#!/usr/bin/env python3
"""Run complete scene-settings contracts and original Forward+ GPU evidence."""
from __future__ import annotations

import argparse
import json

from atmosphere_workflow_profiles import SCENE_SETTINGS_SOURCES
from run import ROOT, engine, execute, runtime_fingerprint
from scene_settings_checks import SOURCE_FILES, canonical_identity, sha, validate, validate_runtime

DRIVER_SOURCES = (
    "tools/forest_hamlet/run.py",
    "tools/forest_hamlet/run_atmosphere.py",
    "tools/project.py",
)


def source_fingerprint(destination) -> str:
    """Bind production assets and every source responsible for this evidence."""
    runtime = json.loads((destination / "runtime-fingerprint.json").read_text(encoding="utf-8"))
    files = dict(runtime["files"])
    for relative in sorted(set(SOURCE_FILES) | set(SCENE_SETTINGS_SOURCES) | set(DRIVER_SOURCES)):
        files[relative] = sha(ROOT / relative)
    identity = canonical_identity(files)
    (destination / "source-fingerprint.json").write_text(
        json.dumps({"schema": 1, "sha256": identity, "files": files}, indent=2) + "\n", encoding="utf-8",
    )
    return identity


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["test", "capture", "check"])
    parser.add_argument("--output", default="build/forest-hamlet/scene-settings-r5")
    args = parser.parse_args()
    destination = (ROOT / args.output).resolve()
    destination.relative_to(ROOT)
    destination.mkdir(parents=True, exist_ok=True)
    if args.command == "check":
        validate(destination)
        return
    runtime_identity = runtime_fingerprint(destination)
    source_identity = source_fingerprint(destination)
    relative = destination.relative_to(ROOT).as_posix()
    identity_parameters = [
        "--forest-fingerprint=" + runtime_identity,
        "--forest-source-fingerprint=" + source_identity,
    ]
    base = [engine(), "--path", str(ROOT), "--fixed-fps", "60"]
    if args.command == "test":
        # Exercise the same --output entry point used by AW's native adapter.
        # The runtime also accepts --forest-output for existing direct callers.
        execute(base + ["--headless", "--script", "res://tests/forest_hamlet/scene_settings_runtime.gd",
                        "--", "--output=res://" + relative, *identity_parameters],
                "scene-settings-r5-runtime", timeout=240)
        validate_runtime(destination)
    else:
        # The test command must establish the current complete source closure
        # before spending GPU time. It also checks actual main-scene startup;
        # the GPU's independent SubViewport demonstrates fresh-instance reload.
        validate_runtime(destination)
        execute(base + [
            "--display-driver", "x11", "--position", "10000,10000", "--audio-driver", "Dummy",
            "--disable-render-loop", "--script", "res://tools/forest_hamlet/capture_scene_settings.gd",
            "--", "--forest-output=res://" + relative, *identity_parameters,
        ], "scene-settings-r5-gpu", graphical=True, timeout=300)
        validate(destination)


if __name__ == "__main__":
    main()
