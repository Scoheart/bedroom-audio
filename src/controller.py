"""Nonblocking application controls; the UI never runs network work itself."""
from __future__ import annotations
import asyncio
import os
from pathlib import Path
import subprocess
import sys
import time
from common import (FROZEN,SOURCE,current_worker,discover,initial_devices,
                    read_json,write_json,choose_leader)

HIDDEN=getattr(subprocess,'CREATE_NO_WINDOW',0)

def command(folder):
    args=[sys.executable]
    if not FROZEN:args.append(str(SOURCE/'app.py'))
    return args+['--worker','--data-dir',str(folder),'--parent-pid',str(os.getpid())]

def prepare_audio():
    import comtypes
    comtypes.CoInitialize()
    try:
        import psutil
        for process in psutil.process_iter(['name','exe']):
            if (process.info['name'] or '').lower()=='tuneblade.exe':
                raise RuntimeError('请先退出 TuneBlade，再启动 Bedroom Audio。')
        from pycaw.pycaw import AudioUtilities
        AudioUtilities.GetSpeakers().EndpointVolume.SetMute(0,None)
    finally:comtypes.CoUninitialize()

def start(folder):
    existing=current_worker(folder)
    if existing:return existing.pid
    devices=initial_devices(folder)
    if not devices or time.time()-max(d.get('checked',0) for d in devices)>30:
        devices=asyncio.run(discover(folder,force=True))
    choose_leader(devices)
    prepare_audio()
    stop=folder/'stop.request'
    if stop.exists():stop.unlink()
    write_json(folder/'status.json',{'state':'connecting','time':time.time()})
    with (folder/'worker-output.log').open('w',encoding='utf8') as log:
        process=subprocess.Popen(command(folder),stdout=log,stderr=log,creationflags=HIDDEN)
    write_json(folder/'worker.json',{'pid':process.pid})
    return process.pid

def stop(folder):
    import psutil
    (folder/'stop.request').write_text('stop',encoding='utf8')
    process=current_worker(folder)
    if process:
        try:process.wait(12)
        except psutil.TimeoutExpired:
            process.terminate()
            try:process.wait(3)
            except psutil.TimeoutExpired:process.kill()
    write_json(folder/'status.json',{'state':'stopped','time':time.time()})

def refresh(folder,force=False):
    return asyncio.run(discover(folder,force=force))
