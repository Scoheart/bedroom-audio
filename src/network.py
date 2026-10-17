"""User-initiated, narrowly scoped Windows Firewall repair."""
from __future__ import annotations
import ctypes
import os
from pathlib import Path
import subprocess
import sys
import time
from common import FROZEN,RESOURCE,read_json

def repair_network(folder):
    if not FROZEN:
        raise RuntimeError('请使用打包后的 BedroomAudio.exe 修复网络许可。')
    request=str(time.time_ns())
    powershell=Path(os.environ['SystemRoot'])/'System32'/'WindowsPowerShell'/'v1.0'/'powershell.exe'
    params=subprocess.list2cmdline(['-NoProfile','-NonInteractive','-File',
        str(RESOURCE/'Repair-HomePod-Network.ps1'),'-Program',sys.executable,
        '-DataDir',str(folder),'-Request',request])
    shell=ctypes.WinDLL('shell32',use_last_error=True)
    shell.ShellExecuteW.argtypes=[ctypes.c_void_p,ctypes.c_wchar_p,ctypes.c_wchar_p,
        ctypes.c_wchar_p,ctypes.c_wchar_p,ctypes.c_int]
    shell.ShellExecuteW.restype=ctypes.c_void_p
    result=shell.ShellExecuteW(None,'runas',str(powershell),params,None,0)
    if not result or result<=32:
        raise RuntimeError('网络许可尚未更新：管理员确认被取消或无法启动。')
    deadline=time.monotonic()+90
    while time.monotonic()<deadline:
        answer=read_json(folder/'network-repair.json',{})
        if answer.get('request')==request:
            if not answer.get('ok'):raise RuntimeError(answer.get('error','网络许可更新失败'))
            return answer
        time.sleep(.25)
    raise RuntimeError('网络许可更新尚未完成，请查看管理员确认或稍后重试。')
