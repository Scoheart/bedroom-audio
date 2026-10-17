"""Playback scheduling and a bounded, fresh queue for live system audio."""
import threading
import time

RATE = 44100
FRAME_BYTES = 4
MODES = {'realtime': 100, 'compatible': 150, 'low': 500, 'stable': 1500}

def mode_name(value):
    return value if isinstance(value,str) and value in MODES else 'realtime'

def negotiated_frames(requested_ms, response):
    """Honor an explicit receiver window; an absent reply is not confirmation."""
    desired = round(RATE * requested_ms / 1000)
    floor = response.get('latencyMin')
    ceiling = response.get('latencyMax')
    valid = lambda value: isinstance(value,int) and not isinstance(value,bool) and 0 < value <= RATE*10
    if valid(floor):desired = max(desired,floor)
    if valid(ceiling) and (not valid(floor) or ceiling >= floor):desired = min(desired,ceiling)
    return desired

class LiveQueue:
    """Keep at most 30 ms; recover to 10 ms after a stall, never replay old audio."""
    def __init__(self, clock=time.perf_counter):
        self.clock=clock;self.lock=threading.Lock();self.data=bytearray()
        self.limit=RATE*30//1000*FRAME_BYTES
        self.target=RATE*10//1000*FRAME_BYTES
        self.last_capture=None;self.first_read=True
        self.dropped_frames=0;self.silence_frames=0;self.high_water_bytes=0

    def _keep(self,size):
        extra=max(0,len(self.data)-size)
        if extra:
            del self.data[:extra];self.dropped_frames+=extra//FRAME_BYTES

    def push(self,data):
        if len(data)%FRAME_BYTES:raise ValueError('PCM must contain complete stereo frames')
        with self.lock:
            now=self.clock()
            if self.last_capture is not None and now-self.last_capture>.1:self._keep(0)
            self.last_capture=now;self.data.extend(data)
            if len(self.data)>self.limit:self._keep(self.target)
            self.high_water_bytes=max(self.high_water_bytes,len(self.data))

    def read(self,frames):
        size=frames*FRAME_BYTES
        with self.lock:
            if self.first_read:
                self._keep(self.target);self.first_read=False
            if self.last_capture is not None and self.clock()-self.last_capture>.1:self._keep(0)
            result=bytes(self.data[:size]);del self.data[:len(result)]
            self.silence_frames+=(size-len(result))//FRAME_BYTES
        return result+b'\0'*(size-len(result))

    def snapshot(self):
        with self.lock:
            return {'capture_queue_ms':round(len(self.data)/FRAME_BYTES/RATE*1000,1),
                'capture_queue_high_ms':round(self.high_water_bytes/FRAME_BYTES/RATE*1000,1),
                'capture_queue_limit_ms':30,'dropped_frames':self.dropped_frames,
                'silence_fill_frames':self.silence_frames}
