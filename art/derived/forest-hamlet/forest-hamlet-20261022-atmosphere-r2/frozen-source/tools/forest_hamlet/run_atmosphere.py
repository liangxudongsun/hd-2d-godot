#!/usr/bin/env python3
"""Run focused atmosphere contracts and actual GPU evidence without installations."""
from pathlib import Path
import argparse

from run import ROOT, engine, execute, runtime_fingerprint
from atmosphere_checks import validate_assets, validate_capture


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['assets','test','capture'])
    parser.add_argument('--output',default='build/forest-hamlet/atmosphere-r2-final')
    parser.add_argument('--no-route',action='store_true',help='Temporary visual iteration only; final evidence includes the real physical route')
    parser.add_argument('--preview',action='store_true',help='Three composition/light tuning frames only; never final validation')
    args=parser.parse_args()
    destination=(ROOT/args.output).resolve()
    destination.relative_to(ROOT)
    destination.mkdir(parents=True,exist_ok=True)
    relative=destination.relative_to(ROOT).as_posix()
    base=[engine(),'--path',str(ROOT),'--fixed-fps','60']
    if args.command=='assets':
        validate_assets(destination)
    elif args.command=='test':
        validate_assets(destination)
        execute(base+['--headless','--script','res://tests/forest_hamlet/atmosphere_runtime.gd','--','--forest-output=res://'+relative], 'atmosphere-runtime',timeout=180)
    else:
        fingerprint=runtime_fingerprint(destination)
        command=base+['--script','res://tools/forest_hamlet/capture_atmosphere.gd','--','--forest-output=res://'+relative,'--forest-fingerprint='+fingerprint]
        if args.no_route:
            command.append('--forest-no-route')
        if args.preview:
            command.append('--atmosphere-preview')
        execute(command,'atmosphere-preview' if args.preview else 'atmosphere-gpu',graphical=True,timeout=300)
        if not args.preview:
            validate_capture(destination)


if __name__=='__main__':
    main()
