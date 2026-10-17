"""Shared files, device discovery, and validated local process control."""
from __future__ import annotations
import asyncio
import json
import os
from pathlib import Path
import sys
import tempfile
import time

FROZEN = bool(getattr(sys, 'frozen', False))
SOURCE = Path(__file__).resolve().parent
RESOURCE = Path(getattr(sys, '_MEIPASS', SOURCE))
KNOWN = {}
PREFERRED = None
TITLE = 'Bedroom Audio · 卧室音频'

def data_dir(value=None):
    folder = Path(value) if value else Path(os.environ['LOCALAPPDATA'])/'BedroomAudio'
    folder.mkdir(parents=True, exist_ok=True)
    return folder

def read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8-sig'))
    except (OSError, ValueError):
        return default

def write_json(path, value):
    path = Path(path)
    # Discovery and Start can finish together. Each writer needs its own temp file.
    with tempfile.NamedTemporaryFile(mode='w',encoding='utf8',dir=path.parent,
                                     prefix=path.name+'.',suffix='.tmp',delete=False) as stream:
        temporary=Path(stream.name)
        json.dump(value,stream,ensure_ascii=False,indent=2)
    try:
        for attempt in range(4):
            try:
                os.replace(temporary,path)
                break
            except PermissionError:
                if attempt==3:raise
                time.sleep(.015)
    finally:
        temporary.unlink(missing_ok=True)


def volume_value(value, default=35):
    try:return max(0,min(100,int(round(float(value)))))
    except (TypeError,ValueError,OverflowError):return default

def normalize(value):
    return ''.join(c for c in str(value).upper() if c in '0123456789ABCDEF')

def configure_devices(folder):
    """Load the user's explicit receiver allowlist, never bundled device IDs."""
    global KNOWN, PREFERRED
    import re
    config = read_json(folder/'config.json')
    if not isinstance(config, dict):
        raise ValueError(f'请按 README 创建设备配置：{folder / "config.json"}')
    devices = config.get('devices')
    if not isinstance(devices, list) or len(devices) != 2:
        raise ValueError('config.json 的 devices 必须包含同一立体声对的两台设备。')
    known = {}
    for device in devices:
        if not isinstance(device, dict):
            raise ValueError('每个设备必须包含 id 和 name。')
        raw = str(device.get('id', ''))
        if not re.fullmatch(r'(?:[0-9a-fA-F]{12}|(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2})', raw):
            raise ValueError('设备 id 必须为 12 位十六进制值，可带冒号。')
        identity = normalize(raw)
        if identity in known:
            raise ValueError('两台设备的 id 不能相同。')
        name = str(device.get('name', '')).strip()
        if not name:
            raise ValueError('设备 name 不能为空。')
        known[identity] = name
    preferred = normalize(config.get('preferred_receiver', '')) or None
    if preferred and preferred not in known:
        raise ValueError('preferred_receiver 必须是 devices 中的一个 id。')
    KNOWN, PREFERRED = known, preferred
    return config


def initial_devices(folder):
    cached = read_json(folder/'devices.json', [])
    return [d for d in cached if isinstance(d, dict) and d.get('id') in KNOWN]

def worker_process(pid, folder):
    """A reused PID must never let this app terminate an unrelated process."""
    import psutil
    try:
        process = psutil.Process(int(pid))
        command = process.cmdline()
        if '--worker' in command and '--data-dir' in command:
            position = command.index('--data-dir')+1
            if Path(command[position]).resolve() == Path(folder).resolve():
                return process
    except (ValueError, IndexError, OSError, psutil.Error):
        pass
    return None

def current_worker(folder):
    value = read_json(folder/'worker.json', {})
    return worker_process(value.get('pid', 0), folder)

def choose_leader(devices, preferred=None):
    preferred = preferred or PREFERRED
    pair_ids = {d.get('pair_id') for d in devices if d.get('reachable') and d.get('pair_id')}
    if len(pair_ids) > 1:
        raise RuntimeError('所选设备属于不同立体声组，请检查 config.json。')
    online = [d for d in devices if d.get('reachable')]
    leaders = [d for d in online if d.get('leader') is True]
    paired = [d for d in devices if d.get('pair_id')]
    # HomePods can temporarily advertise multiple leaders during group changes.
    # Keep the receiver already verified by listening instead of swapping peers.
    preferred_device=next((d for d in online if d['id']==preferred),None)
    if preferred_device:
        return preferred_device
    if leaders:
        return next((d for d in leaders if d['id']==preferred),leaders[0])
    if paired:
        raise RuntimeError('未找到可连接的立体声组主机，请刷新设备后重试。')
    if online:
        return online[0]
    raise RuntimeError('所选音箱暂时无法连接，请检查音箱与电脑的网络。')

def display_state(status, alive, now=None):
    now = time.time() if now is None else now
    state = (status or {}).get('state', 'stopped')
    if not alive:
        return ('error' if state in {'error','connecting','streaming','reconnecting'} else 'stopped')
    if now-(status or {}).get('time', 0)>8:
        return 'unresponsive'
    return state

def txt_dict(raw):
    if isinstance(raw, dict):
        return {str(k): str(v) for k,v in raw.items()}
    result = {}
    if isinstance(raw, bytes):
        offset=0
        while offset<len(raw):
            size=raw[offset];offset+=1
            text=raw[offset:offset+size].decode('utf8',errors='replace');offset+=size
            key,_,value=text.partition('=');result[key]=value
    return result

async def probe(device):
    """A read-only AirPlay /info response verifies the address, not audible output."""
    import plistlib
    record=dict(device)
    record['reachable']=False
    writer=None
    try:
        reader,writer=await asyncio.wait_for(asyncio.open_connection(record['address'],record.get('port',7000)),2)
        writer.write(b'GET /info HTTP/1.1\r\nCSeq: 1\r\nUser-Agent: AirPlay/550.10\r\n\r\n')
        await writer.drain()
        header=await asyncio.wait_for(reader.readuntil(b'\r\n\r\n'),2)
        if b' 200 ' not in header.split(b'\r\n')[0]:
            raise RuntimeError('接收器拒绝状态查询')
        length=next(int(line.split(b':',1)[1]) for line in header.split(b'\r\n') if line.lower().startswith(b'content-length:'))
        if not 0<length<65536:
            raise RuntimeError('状态响应无效')
        info=plistlib.loads(await asyncio.wait_for(reader.readexactly(length),2))
        advertised=normalize(info.get('deviceID',''))
        if advertised and advertised!=record['id']:
            raise RuntimeError('此地址的设备已变化')
        props=txt_dict(info.get('txtAirPlay',b''))
        if props:
            record['airplay'].update(props)
        record.update(reachable=True,checked=time.time(),reason='',
                      pair_id=record['airplay'].get('tsid',''),
                      leader=record['airplay'].get('igl')=='1')
        if isinstance(info.get('initialVolume'),(float,int)):
            from pyatv.protocols.airplay.utils import dbfs_to_pct
            record['volume']=round(dbfs_to_pct(float(info['initialVolume'])))
    except Exception as error:
        record.update(checked=time.time(),reason=str(error) or '连接超时')
    finally:
        if writer:
            writer.close()
            try: await writer.wait_closed()
            except Exception: pass
    return record

async def discover(folder, force=False):
    import pyatv
    from pyatv.const import Protocol
    configure_devices(folder)
    cached=initial_devices(folder)
    hosts=[d['address'] for d in cached if d.get('address')]
    found=await pyatv.scan(asyncio.get_running_loop(),hosts=hosts or None,
                           protocol={Protocol.RAOP,Protocol.AirPlay},timeout=3)
    seen={}
    def merge(configs):
        for config in configs:
            air=config.get_service(Protocol.AirPlay)
            raop=config.get_service(Protocol.RAOP)
            if not air or not raop: continue
            identity=normalize(air.properties.get('deviceid',''))
            if identity not in KNOWN: continue
            props=dict(air.properties)
            seen[identity]={'id':identity,'name':KNOWN[identity],
                'address':str(config.address),'port':raop.port,
                'airplay':props,'raop':dict(raop.properties),
                'pair_id':props.get('tsid',''),'leader':props.get('igl')=='1'}
    merge(found)
    if force and len(seen)<2:
        merge(await pyatv.scan(asyncio.get_running_loop(),
                               protocol={Protocol.RAOP,Protocol.AirPlay},timeout=3))
    for old in cached:
        if old.get('id') in KNOWN:
            seen.setdefault(old['id'],old)
    records=await asyncio.gather(*(probe(seen[k]) for k in KNOWN if k in seen))
    write_json(folder/'devices.json',records)
    return records


async def list_receivers():
    """List candidates for configuration; never start streaming or save them."""
    import pyatv
    from pyatv.const import Protocol
    found = await pyatv.scan(asyncio.get_running_loop(),
                            protocol={Protocol.RAOP, Protocol.AirPlay}, timeout=5)
    result = []
    for config in found:
        air = config.get_service(Protocol.AirPlay)
        raop = config.get_service(Protocol.RAOP)
        if not air or not raop:
            continue
        identity = normalize(air.properties.get('deviceid', ''))
        if len(identity) != 12:
            continue
        result.append({'id': identity, 'name': config.name,
                       'address': str(config.address),
                       'pair_id': air.properties.get('tsid', ''),
                       'leader': air.properties.get('igl') == '1'})
    return result
