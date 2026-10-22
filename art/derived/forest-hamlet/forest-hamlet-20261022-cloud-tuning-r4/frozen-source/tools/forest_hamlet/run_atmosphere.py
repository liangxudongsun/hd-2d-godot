#!/usr/bin/env python3
"""Run focused atmosphere contracts and actual GPU evidence without installations."""
from pathlib import Path
import argparse

from run import ROOT, engine, execute, runtime_fingerprint
from atmosphere_checks import validate_assets, validate_capture
from cloud_transmission_checks import validate as validate_cloud_transmission


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['assets','test','capture','transmission'])
    parser.add_argument('--output',default='build/forest-hamlet/atmosphere-r3-final')
    parser.add_argument('--no-route',action='store_true',help='Temporary visual iteration only; final evidence includes the real physical route')
    parser.add_argument('--preview',action='store_true',help='Three thin/thick/natural cloud appearance frames only; never final validation')
    args=parser.parse_args()
    destination=(ROOT/args.output).resolve()
    destination.relative_to(ROOT)
    destination.mkdir(parents=True,exist_ok=True)
    relative=destination.relative_to(ROOT).as_posix()
    base=[engine(),'--path',str(ROOT),'--fixed-fps','60']
    # Match the project's established offscreen GPU capture path. Both capture
    # scripts explicitly force_draw their SubViewport; a minimized Wayland
    # presentation surface can otherwise stall after the report is written.
    graphical_base=base+['--display-driver','x11','--position','10000,10000',
                         '--audio-driver','Dummy','--disable-render-loop']
    if args.command=='assets':
        validate_assets(destination)
    elif args.command=='test':
        validate_assets(destination)
        execute(base+['--headless','--script','res://tests/forest_hamlet/atmosphere_runtime.gd','--','--forest-output=res://'+relative], 'atmosphere-runtime',timeout=180)
    elif args.command=='transmission':
        fingerprint=runtime_fingerprint(destination)
        command=graphical_base+['--script','res://tools/forest_hamlet/capture_cloud_transmission.gd','--',
                      '--forest-output=res://'+relative,'--forest-fingerprint='+fingerprint]
        execute(command,'cloud-transmission-gpu',graphical=True,timeout=180)
        validate_cloud_transmission(destination)
    else:
        fingerprint=runtime_fingerprint(destination)
        command=graphical_base+['--script','res://tools/forest_hamlet/capture_atmosphere.gd','--','--forest-output=res://'+relative,'--forest-fingerprint='+fingerprint]
        if args.no_route:
            command.append('--forest-no-route')
        if args.preview:
            command.append('--atmosphere-preview')
        execute(command,'atmosphere-preview' if args.preview else 'atmosphere-gpu',graphical=True,timeout=300)
        if not args.preview:
            probe_destination=destination/'cloud-transmission'
            probe_destination.mkdir(parents=True,exist_ok=True)
            probe_relative=probe_destination.relative_to(ROOT).as_posix()
            probe_command=graphical_base+['--script','res://tools/forest_hamlet/capture_cloud_transmission.gd','--',
                                '--forest-output=res://'+probe_relative,'--forest-fingerprint='+fingerprint]
            execute(probe_command,'cloud-transmission-gpu',graphical=True,timeout=180)
            validate_cloud_transmission(probe_destination)
            validate_capture(destination)


if __name__=='__main__':
    main()
