"""Accurate Windows audio pacing and conservative transport backoff."""
import asyncio
import ctypes
import time

class AudioLoop(asyncio.ProactorEventLoop):
    def __init__(self):
        super().__init__()
        self._clock_resolution=time.get_clock_info('perf_counter').resolution
    def time(self):return time.perf_counter()

class AudioTimer:
    def __enter__(self):
        self.active=ctypes.windll.winmm.timeBeginPeriod(1)==0
        return self
    def __exit__(self,*_):
        if self.active:ctypes.windll.winmm.timeEndPeriod(1)

def run_audio(coroutine):
    # Scope the timer request to this hidden audio process and always release it.
    with AudioTimer():return asyncio.run(coroutine,loop_factory=AudioLoop)

class TransportHealth:
    """Back off only after two poor 5-second windows, never on one late packet."""
    def __init__(self,clock=time.perf_counter):
        self.clock=clock;self.started=None;self.previous=None;self.window_start=None
        self.window_gaps=[];self.window_lost=0;self.bad_windows=0
        self.max_gap=0;self.retransmit_packets=0;self.retransmit_requests=0
        self.last_p95=0;self.last_max=0

    def sent(self):
        now=self.clock()
        if self.started is None:self.started=now;self.window_start=now
        if self.previous is not None:
            gap=(now-self.previous)*1000
            self.max_gap=max(self.max_gap,gap);self.window_gaps.append(gap)
        self.previous=now

    def retransmit(self,packets):
        self.window_lost+=packets;self.retransmit_packets+=packets;self.retransmit_requests+=1

    def assess(self,latency_ms):
        now=self.clock()
        if self.window_start is None or now-self.window_start<5:return None
        gaps=sorted(self.window_gaps)
        self.last_p95=gaps[min(len(gaps)-1,int(len(gaps)*.95))] if gaps else 0
        self.last_max=max(gaps,default=0)
        stalls=sum(gap>max(20,latency_ms*.6) for gap in gaps)
        bad=stalls>=2 or self.window_lost>=12
        self.bad_windows=self.bad_windows+1 if bad else 0
        self.window_gaps=[];self.window_lost=0;self.window_start=now
        if self.bad_windows>=2:
            for target in (120,150,250,350,500):
                if target>latency_ms:return target
        return None

    def snapshot(self):
        return {'send_gap_max_ms':round(self.max_gap,2),'send_gap_p95_ms':round(self.last_p95,2),
            'retransmit_requests':self.retransmit_requests,'retransmit_packets':self.retransmit_packets,
            'transport_bad_windows':self.bad_windows}
