"""The verified AP2/NTP/ALAC sender, with peer feedback and atomic status."""
from __future__ import annotations
import asyncio
import array
import json
import logging
from logging.handlers import RotatingFileHandler
import os
import threading
import time
from ipaddress import ip_address
from common import choose_leader, discover, initial_devices, read_json, write_json, volume_value
from latency import LiveQueue,MODES,mode_name,negotiated_frames
from realtime import TransportHealth
import av
import pyaudiowpatch as pa
import pyatv
import pyatv.protocols.raop as raop
import pyatv.protocols.raop.stream_client as stream_client
from pyatv.const import Protocol,PairingRequirement
from pyatv.conf import AppleTV,ManualService
from pyatv.interface import MediaMetadata
from pyatv.protocols.raop.audio_source import AudioSource
from pyatv.protocols.raop.protocols.airplayv2 import AirPlayV2
from pyatv.protocols.raop.protocols import TimingServer,StreamContext
from pyatv.support.http import decode_bplist_from_body
from pyatv.settings import AirPlayVersion
from pyatv.storage.memory_storage import MemoryStorage
from pyatv.support.rtsp import RtspSession

PACKETS=0
FEEDBACK=0.0
PEER_ERROR=''
REMOTE_VOLUME=35
LAST_VOLUME_WRITE=0.0
CLOCK_RX=0
PHASE='connecting'
LATENCY_MS=MODES['realtime']
PLAYOUT_FRAMES=round(44100*LATENCY_MS/1000)
RECEIVER_WINDOW={}
HEALTH=TransportHealth()
ANCHOR_CONTROL_MS=0

# Python 3.12 on Windows uses GetTickCount64 for monotonic (~15.6 ms).
# Audio packets are 7.98 ms apart; both pacing and statistics must use QPC.
stream_client.monotonic=time.perf_counter
stream_client.monotonic_ns=time.perf_counter_ns

original_control=stream_client.ControlClient.datagram_received
def live_control(self,data,addr):
    if len(data)>=8 and data[1]&0x7f==0x55:
        HEALTH.retransmit(int.from_bytes(data[6:8],'big'))
    return original_control(self,data,addr)
stream_client.ControlClient.datagram_received=live_control

# Establish the NTP/RTP anchor only after RECORD, FLUSH and initial volume.
# Otherwise those round trips consume much of a 150 ms playout budget.
original_control_start=stream_client.ControlClient.start
def defer_control_start(self,address):
    if hasattr(self.context,'bedroom_latency_frames'):
        self.bedroom_address=address
    else:original_control_start(self,address)
stream_client.ControlClient.start=defer_control_start

def anchor_live(context):
    from pyatv.protocols.raop import timing
    previous=context.start_ts
    now=timing.ntp2ts(timing.ntp_now(),context.sample_rate)
    context.start_ts=now;context.head_ts=now
    return max(0,(now-previous)/context.sample_rate*1000)

original_stream_data=stream_client.StreamClient._stream_data
async def start_live_data(self,source,transport):
    global ANCHOR_CONTROL_MS,PLAYOUT_FRAMES
    if isinstance(source,WindowsLoopback):
        # RECORD can report a stricter floor than SETUP. Respect it before sync.
        PLAYOUT_FRAMES=negotiated_frames(LATENCY_MS,RECEIVER_WINDOW)
        self.context.bedroom_latency_frames=PLAYOUT_FRAMES
        self.context.latency=PLAYOUT_FRAMES
        ANCHOR_CONTROL_MS=anchor_live(self.context)
        original_control_start(self.control_client,self.control_client.bedroom_address)
        await asyncio.sleep(0)  # Send the initial sync before the first PCM packet.
        logging.getLogger('BedroomAudio').info('live_anchor control_roundtrips_ms=%.1f',ANCHOR_CONTROL_MS)
    return await original_stream_data(self,source,transport)
stream_client.StreamClient._stream_data=start_live_data

class BufferBackoff(RuntimeError):
    def __init__(self,milliseconds):
        self.milliseconds=milliseconds
        super().__init__(f'持续网络重传或发送卡顿，自动增加播放预留至 {milliseconds} ms')

# send_audio resets the context after SETUP. Preserve our selected/negotiated
# schedule across that reset; changing SETUP alone does not change RTP timing.
original_reset=StreamContext.reset
def live_reset(self):
    original_reset(self)
    self.latency=getattr(self,'bedroom_latency_frames',round(self.sample_rate*LATENCY_MS/1000))
StreamContext.reset=live_reset

original_audio_setup=AirPlayV2.setup_audio_stream
async def live_audio_setup(self,*args,**kwargs):
    global PLAYOUT_FRAMES
    await original_audio_setup(self,*args,**kwargs)
    PLAYOUT_FRAMES=negotiated_frames(LATENCY_MS,RECEIVER_WINDOW)
    self.context.bedroom_latency_frames=PLAYOUT_FRAMES
    self.context.latency=PLAYOUT_FRAMES
    logging.getLogger('BedroomAudio').info('latency_schedule requested_ms=%s scheduled_ms=%.1f receiver_window=%s',
        LATENCY_MS,PLAYOUT_FRAMES/44.1,RECEIVER_WINDOW)
AirPlayV2.setup_audio_stream=live_audio_setup

class ClockTimeout(RuntimeError):pass

def receiver_latency_header(response):
    """RAOP Audio-Latency is in sample frames, including a valid zero value."""
    for name,value in response.headers.items():
        if name.lower()=='audio-latency':
            try:frames=int(value)
            except (TypeError,ValueError):return
            if 0<=frames<=441000:
                previous=RECEIVER_WINDOW.get('latencyMin',0)
                if not isinstance(previous,int):previous=0
                RECEIVER_WINDOW['latencyMin']=max(previous,frames)
                logging.getLogger('BedroomAudio').info('receiver_latency_header frames=%s',frames)

original_record=RtspSession.record
async def record_with_latency(self,*args,**kwargs):
    response=await original_record(self,*args,**kwargs)
    receiver_latency_header(response)
    return response
RtspSession.record=record_with_latency

original_timing_receive=TimingServer.datagram_received
def clock_receive(self,data,addr):
    global CLOCK_RX
    original_timing_receive(self,data,addr)
    CLOCK_RX+=1
    if CLOCK_RX==1:
        logging.getLogger('BedroomAudio').info('clock_reply peer=%s:%s local_port=%s',*addr,self.port)
TimingServer.datagram_received=clock_receive

async def apply_volume(audio, command):
    """A request is acknowledged only after the receiver accepts SET_PARAMETER."""
    value=max(0,min(100,int(command['volume'])))
    await asyncio.wait_for(audio.set_volume(value),4)
    return value

def wrap_alac(audio):
    if len(audio)%4:raise ValueError('ALAC requires complete stereo frames')
    # 55 header bits, interleaved big-endian PCM, END(111), then 6 pad bits.
    # Avoid creating ~11,000 Python string characters per 8 ms packet.
    header=(1<<52)|(1<<35)|(1<<32)|(len(audio)//4)
    packet=(header<<(len(audio)*8+9))|(int.from_bytes(audio,'big')<<9)|(7<<6)
    return packet.to_bytes(len(audio)+8,'big')

original_setup=RtspSession.setup
async def alac_setup(self,*args,**kwargs):
    global PHASE,RECEIVER_WINDOW
    body=kwargs.get('body') or {}
    audio=bool(body.get('streams'))
    PHASE='audio_setup' if audio else 'clock_setup'
    logging.getLogger('BedroomAudio').info('%s peer=%s timing_port=%s clock_replies=%s',
        PHASE,self.connection.remote_ip,body.get('timingPort'),CLOCK_RX)
    for stream in (kwargs.get('body') or {}).get('streams',[]):
        if stream.get('type')==96:
            stream.update(ct=2,audioFormat=0x40000,
                latencyMin=0,
                latencyMax=round(44100*LATENCY_MS/1000))
    try:
        response=await original_setup(self,*args,**kwargs)
    except TimeoutError as error:
        if audio and CLOCK_RX==0:
            raise ClockTimeout('未收到 HomePod 的 UDP 时钟请求。请点击“修复网络许可”后重试。') from error
        raise
    logging.getLogger('BedroomAudio').info('%s accepted code=%s',PHASE,response.code)
    if audio:
        info=decode_bplist_from_body(response)
        streams=info.get('streams',[])
        RECEIVER_WINDOW={k:v for s in streams if s.get('type')==96
            for k,v in s.items() if k in ('latencyMin','latencyMax','audioLatency')}
        receiver_latency_header(response)
    return response
RtspSession.setup=alac_setup

original_send=AirPlayV2.send_audio_packet
async def alac_send(self,transport,header,audio):
    global PACKETS
    result=await original_send(self,transport,header,wrap_alac(audio))
    PACKETS+=1
    HEALTH.sent()
    return result
AirPlayV2.send_audio_packet=alac_send

async def checked_feedback(self):
    global FEEDBACK,PEER_ERROR,REMOTE_VOLUME
    from pyatv.protocols.airplay.utils import dbfs_to_pct
    failures=0;counter=0
    while True:
        try:
            response=await asyncio.wait_for(self.rtsp.feedback(),5)
            if response.code!=200:
                raise RuntimeError(f'接收器反馈 {response.code}')
            FEEDBACK=time.monotonic();failures=0
            counter+=1
            if counter%5==0:
                began=time.monotonic()
                try:
                    info=await asyncio.wait_for(self.rtsp.info(),4)
                    if isinstance(info.get('initialVolume'),(int,float)) and LAST_VOLUME_WRITE<began:
                        REMOTE_VOLUME=round(dbfs_to_pct(float(info['initialVolume'])))
                except Exception:pass
        except asyncio.CancelledError:
            raise
        except Exception as error:
            failures+=1
            if failures>=2:
                PEER_ERROR=str(error) or '接收器没有回应'
                return
        await asyncio.sleep(2)
AirPlayV2._feedback_task_loop=checked_feedback

class WindowsLoopback(AudioSource):
    def __init__(self,stop):
        self.stop=stop
        self.portaudio=pa.PyAudio()
        self.device=self.portaudio.get_default_wasapi_loopback()
        self.rate=int(self.device['defaultSampleRate'])
        self.channel_count=min(2,int(self.device['maxInputChannels']))
        self.queue=LiveQueue();self.lock=threading.Lock()
        self.stopped=False;self.error='';self.peak=0
        self.captured=0;self.capture_overflows=0
        self.resampler=av.AudioResampler(format='s16',layout='stereo',rate=44100)
        self.stream=None
        try:
            self.stream=self.portaudio.open(format=pa.paInt16,
                channels=self.channel_count,rate=self.rate,input=True,
                input_device_index=self.device['index'],
                frames_per_buffer=max(128,self.rate//200),stream_callback=self.capture)
            self.driver_latency_ms=round(self.stream.get_input_latency()*1000,1)
        except Exception:
            self.portaudio.terminate()
            raise

    def capture(self,data,count,_timing,_flags):
        if self.stopped:return None,pa.paComplete
        if _flags & pa.paInputOverflow:self.capture_overflows+=1
        try:
            frame=av.AudioFrame(format='s16',layout='stereo' if self.channel_count==2 else 'mono',samples=count)
            frame.sample_rate=self.rate;frame.planes[0].update(data)
            for output in self.resampler.resample(frame):
                # Packed s16 contains optional plane alignment after the real samples.
                raw=bytes(output.planes[0])[:output.samples*4]
                samples=array.array('h',raw)
                peak=max((abs(int(s)) for s in samples),default=0)
                self.captured+=output.samples;samples.byteswap()
                with self.lock:
                    self.peak=max(self.peak,peak)
                self.queue.push(samples.tobytes())
        except Exception as error:
            self.error=str(error);self.stopped=True
            return None,pa.paAbort
        return None,pa.paContinue

    async def readframes(self,count):
        if self.stopped or self.stop.exists():return b''
        return self.queue.read(count)

    def take_peak(self):
        with self.lock:
            value=self.peak;self.peak=0
        return value

    async def close(self):
        self.stopped=True
        if self.stream is not None:
            self.stream.stop_stream();self.stream.close();self.stream=None
            self.portaudio.terminate()

    async def get_metadata(self):return MediaMetadata(title='Windows system audio')
    sample_rate=property(lambda self:44100)
    channels=property(lambda self:2)
    sample_size=property(lambda self:2)
    duration=property(lambda self:0)

original_open=raop.open_source
async def open_live(file,*args,**kwargs):
    return file if isinstance(file,WindowsLoopback) else await original_open(file,*args,**kwargs)
raop.open_source=open_live

class Reporter:
    def __init__(self,folder):self.folder=folder;self.last=''
    def __call__(self,state,**details):
        write_json(self.folder/'status.json',{'state':state,'pid':os.getpid(),
                   'time':time.time(),**details})
        if state!=self.last:
            logging.getLogger('BedroomAudio').info('%s %s',state,details.get('error',''))
            self.last=state

async def session(folder,report,attempt,latency_override=0):
    global FEEDBACK,PEER_ERROR,REMOTE_VOLUME,LAST_VOLUME_WRITE,CLOCK_RX,PHASE,LATENCY_MS,RECEIVER_WINDOW,HEALTH
    FEEDBACK=0;PEER_ERROR='';LAST_VOLUME_WRITE=0.0;CLOCK_RX=0;PHASE='connecting'
    target=choose_leader(initial_devices(folder))
    properties=dict(target['raop']);properties['md']='0,1'
    config=AppleTV(ip_address(target['address']),'Bedroom stereo pair')
    config.add_service(ManualService('bedroom-live',Protocol.RAOP,target['port'],properties,
        pairing_requirement=PairingRequirement.NotNeeded))
    storage=MemoryStorage();settings=await storage.get_settings(config)
    settings.protocols.raop.protocol_version=AirPlayVersion.V2
    stop=folder/'stop.request'
    report('connecting',target=target['address'],attempt=attempt)
    atv=await pyatv.connect(config,asyncio.get_running_loop(),protocol=Protocol.RAOP,storage=storage)
    source=None;task=None
    try:
        baseline=read_json(folder/'volume.json',{})
        preferences=read_json(folder/'settings.json',{})
        latency_mode=mode_name(preferences.get('latency_mode'))
        LATENCY_MS=max(MODES[latency_mode],latency_override);RECEIVER_WINDOW={};HEALTH=TransportHealth()
        REMOTE_VOLUME=volume_value(preferences.get('volume',target.get('volume',35)))
        await atv.audio.set_volume(REMOTE_VOLUME)
        source=WindowsLoopback(stop)
        task=asyncio.create_task(atv.stream.stream_file(source))
        began=time.monotonic();old_packets=PACKETS;last_request=baseline.get('request');volume_error='';last_report=0;last_latency_log=0
        while not task.done():
            await asyncio.sleep(.2)
            if source.error:raise RuntimeError('无法捕获电脑声音：'+source.error)
            if PEER_ERROR:raise RuntimeError('与音箱的连接已中断：'+PEER_ERROR)
            safer_latency=HEALTH.assess(PLAYOUT_FRAMES/44.1)
            if safer_latency and not stop.exists():raise BufferBackoff(safer_latency)
            elapsed=time.monotonic()-began
            if elapsed>24 and not FEEDBACK:
                raise RuntimeError('音箱建立播放会话超时')
            if FEEDBACK and time.monotonic()-FEEDBACK>13:
                raise RuntimeError('音箱反馈超时')
            command=read_json(folder/'volume.json',{})
            if FEEDBACK and command.get('request') and command['request']!=last_request:
                try:
                    value=await apply_volume(atv.audio,command)
                    REMOTE_VOLUME=value;LAST_VOLUME_WRITE=time.monotonic();volume_error=''
                    last_request=command['request']
                    logging.getLogger('BedroomAudio').info('volume_accepted request=%s value=%s',last_request,value)
                except Exception as error:
                    volume_error=str(error) or '音箱音量设置未确认';last_request=command['request']
                    logging.getLogger('BedroomAudio').warning('volume_failed request=%s error=%s',last_request,volume_error)
            state='streaming' if PACKETS>old_packets and FEEDBACK else 'connecting'
            if time.monotonic()-last_report>.7:
                last_report=time.monotonic()
                metrics=source.queue.snapshot()
                if last_report-last_latency_log>10:
                    last_latency_log=last_report
                    logging.getLogger('BedroomAudio').info('latency_queue scheduled_ms=%.1f queue_ms=%s high_ms=%s dropped=%s',
                        PLAYOUT_FRAMES/44.1,metrics['capture_queue_ms'],metrics['capture_queue_high_ms'],metrics['dropped_frames'])
                report(state,target=target['address'],target_id=target['id'],attempt=attempt,
                capture_device=source.device['name'],packets=PACKETS,
                captured_frames=source.captured,peak=source.take_peak(),
                **metrics,**HEALTH.snapshot(),feedback_ok=bool(FEEDBACK),
                feedback_age=round(time.monotonic()-FEEDBACK,1) if FEEDBACK else None,
                elapsed=round(elapsed),remote_volume=REMOTE_VOLUME,
                volume_request=last_request if state=='streaming' else None,volume_error=volume_error,
                phase=PHASE,clock_replies=CLOCK_RX,latency_mode=latency_mode,
                scheduled_latency_ms=round(PLAYOUT_FRAMES/44.1,1),
                requested_latency_ms=MODES[latency_mode],latency_protection=PLAYOUT_FRAMES>round(MODES[latency_mode]*44.1),
                pacing_clock='QueryPerformanceCounter',pacing_resolution_ms=time.get_clock_info('perf_counter').resolution*1000,
                startup_control_ms=round(ANCHOR_CONTROL_MS,1),
                capture_driver_ms=source.driver_latency_ms,
                capture_callback_ms=round(max(128,source.rate//200)/source.rate*1000,1),
                capture_overflows=source.capture_overflows,
                receiver_latency_window=RECEIVER_WINDOW)
            if stop.exists():
                report('stopping',target=target['address'])
                await asyncio.wait_for(asyncio.shield(task),8)
                break
        await task
        if not stop.exists():raise RuntimeError('音频传输意外结束')
    finally:
        if task and not task.done():
            task.cancel()
            try:await asyncio.wait_for(task,3)
            except (asyncio.CancelledError,Exception):pass
        if source:await source.close()
        tasks=atv.close()
        if tasks:await asyncio.gather(*tasks,return_exceptions=True)

async def worker(folder):
    logger=logging.getLogger()
    logger.setLevel(logging.WARNING)
    handler=RotatingFileHandler(folder/'audio.log',maxBytes=1024*1024,backupCount=2,encoding='utf8')
    handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
    logger.addHandler(handler);logging.getLogger('BedroomAudio').setLevel(logging.INFO)
    report=Reporter(folder);write_json(folder/'worker.json',{'pid':os.getpid()})
    stop=folder/'stop.request'
    attempt=1;latency_override=0
    while attempt<=3:
        try:
            if stop.exists():report('stopped');return
            if attempt>1:
                await discover(folder,force=True)
            await session(folder,report,attempt,latency_override)
            report('stopped');return
        except BufferBackoff as error:
            latency_override=error.milliseconds
            logging.getLogger('BedroomAudio').warning('latency_backoff %s',error)
            if stop.exists():report('stopped');return
            report('reconnecting',error=str(error),attempt=attempt,next_retry=0,
                scheduled_latency_ms=latency_override,latency_protection=True)
        except Exception as error:
            logging.getLogger('BedroomAudio').exception('session failed')
            if stop.exists():report('stopped');return
            if attempt==3 or isinstance(error,ClockTimeout):
                report('error',error=str(error),needs_network_permission=isinstance(error,ClockTimeout));return
            report('reconnecting',error=str(error),attempt=attempt,next_retry=5)
            for _ in range(25):
                if stop.exists():report('stopped');return
                await asyncio.sleep(.2)
            attempt+=1
