"""Offline packaging smoke check. Never creates a window or plays audio."""
from __future__ import annotations
import asyncio
import importlib
from pathlib import Path
import struct
import sys
import traceback
from common import RESOURCE,write_json

def self_check(folder):
    result={'ok':False,'frozen':bool(getattr(sys,'frozen',False)),'checks':[]}
    try:
        for name in ('tkinter','pyatv','aiohttp','zeroconf','miniaudio','av',
                     'pyaudiowpatch','psutil','pycaw.pycaw','comtypes',
                     'cryptography.hazmat.primitives.ciphers.aead'):
            importlib.import_module(name)
            result['checks'].append('import '+name)
        assert (RESOURCE/'bedroom.ico').stat().st_size>100
        result['checks'].append('bundled resources')
        import av
        from engine import wrap_alac,apply_volume
        codec=av.CodecContext.create('alac','r')
        codec.extradata=struct.pack('>I4sI',36,b'alac',0)+struct.pack('>IBBBBBBHIII',352,0,16,40,10,14,2,255,0,0,44100)
        codec.open()
        frame=codec.decode(av.Packet(wrap_alac(struct.pack('>hh',1234,-2345)*352)))[0]
        assert frame.samples==352
        assert struct.unpack('<h',bytes(frame.planes[0])[:2])[0]==1234
        assert struct.unpack('<h',bytes(frame.planes[1])[:2])[0]==-2345
        result['checks'].append('ALAC signed stereo roundtrip')
        from realtime import run_audio
        from latency import MODES
        from pyatv.protocols.raop.protocols import StreamContext
        async def check_clock():
            loop=asyncio.get_running_loop()
            assert loop._clock_resolution<.001
            context=StreamContext();context.reset()
            assert context.latency==round(44100*MODES['realtime']/1000)
        run_audio(check_clock())
        result['checks'].append(f"high resolution audio loop and {MODES['realtime']} ms schedule")
        class Audio:
            async def set_volume(self,value):self.value=value
        async def check_volume():
            audio=Audio()
            assert await apply_volume(audio,{'volume':0})==0 and audio.value==0
            assert await apply_volume(audio,{'volume':35})==35 and audio.value==35
        asyncio.run(check_volume())
        result['checks'].append('volume request and mute path')
        from pycaw.pycaw import AudioUtilities
        endpoint=AudioUtilities.GetSpeakers()
        result['windows_output']=endpoint.FriendlyName
        result['windows_volume']=round(endpoint.EndpointVolume.GetMasterVolumeLevelScalar()*100)
        result['checks'].append('read Windows endpoint')
        result['ok']=True
    except Exception:
        result['error']=traceback.format_exc()
    write_json(folder/'self-check.json',result)
    return result
