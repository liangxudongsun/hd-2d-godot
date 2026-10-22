#!/usr/bin/env python3
"""Run focused live cloud-control tests and actual GPU evidence, without installs."""
from __future__ import annotations

import argparse

from run import ROOT, engine, execute, runtime_fingerprint
from cloud_tuning_checks import validate


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command",choices=["test","capture","check"])
    parser.add_argument("--output",default="build/forest-hamlet/cloud-tuning-r4")
    args = parser.parse_args()
    destination = (ROOT/args.output).resolve()
    destination.relative_to(ROOT)
    destination.mkdir(parents=True,exist_ok=True)
    if args.command=="check":
        validate(destination)
        return
    identity = runtime_fingerprint(destination)
    relative = destination.relative_to(ROOT).as_posix()
    parameters = ["--forest-output=res://"+relative,"--forest-fingerprint="+identity]
    base = [engine(),"--path",str(ROOT),"--fixed-fps","60"]
    if args.command=="test":
        execute(base+["--headless","--script","res://tests/forest_hamlet/cloud_tuning_runtime.gd","--",*parameters],"cloud-tuning-r4-runtime",timeout=180)
    else:
        # Use the established offscreen X11 path. The script force_draws its
        # independent SubViewport, avoiding a minimized Wayland shutdown stall.
        execute(base+["--display-driver","x11","--position","10000,10000","--audio-driver","Dummy",
                      "--disable-render-loop","--script","res://tools/forest_hamlet/capture_cloud_tuning.gd","--",*parameters],
                "cloud-tuning-r4-gpu",graphical=True,timeout=180)
        validate(destination)


if __name__ == "__main__":
    main()
