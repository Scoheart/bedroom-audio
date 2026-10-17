import sys,time,unittest,struct
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import common

class ConnectionMeaning(unittest.TestCase):
    def test_volume_pointer_mapping_includes_endpoints_and_clamps_drag(self):
        from volume_control import percentage_at
        self.assertEqual(percentage_at(18,500),0)
        self.assertEqual(percentage_at(250,500),50)
        self.assertEqual(percentage_at(482,500),100)
        self.assertEqual(percentage_at(-80,500),0)
        self.assertEqual(percentage_at(650,500),100)

    def test_setup_timeout_distinguishes_missing_clock_from_other_failure(self):
        import asyncio
        from unittest.mock import AsyncMock
        from types import SimpleNamespace
        import engine
        async def check():
            saved=engine.original_setup
            saved_clock=engine.CLOCK_RX
            try:
                engine.original_setup=AsyncMock(side_effect=TimeoutError('SETUP'))
                peer=SimpleNamespace(connection=SimpleNamespace(remote_ip='192.0.2.11'))
                engine.CLOCK_RX=0
                with self.assertRaises(engine.ClockTimeout):
                    await engine.alac_setup(peer,body={'streams':[{'type':96}]})
                engine.CLOCK_RX=3
                with self.assertRaises(TimeoutError):
                    await engine.alac_setup(peer,body={'streams':[{'type':96}]})
            finally:engine.original_setup=saved;engine.CLOCK_RX=saved_clock
        asyncio.run(check())

    def test_volume_command_awaits_receiver_and_preserves_errors(self):
        import asyncio
        from engine import apply_volume
        class Receiver:
            def __init__(self):self.values=[]
            async def set_volume(self,value):self.values.append(value)
        class Broken:
            async def set_volume(self,value):raise ConnectionError('receiver disconnected')
        async def check():
            receiver=Receiver()
            for requested,expected in ((0,0),(35,35),(-8,0),(160,100)):
                self.assertEqual(await apply_volume(receiver,{'volume':requested}),expected)
            self.assertEqual(receiver.values,[0,35,0,100])
            with self.assertRaises(ConnectionError):await apply_volume(Broken(),{'volume':20})
        asyncio.run(check())

    def test_invalid_saved_volume_uses_default(self):
        for value in (None,'bad',float('inf'),float('nan')):
            self.assertEqual(common.volume_value(value),35)
        self.assertEqual(common.volume_value(133),100)
        self.assertEqual(common.volume_value(-10),0)

    def test_stale_and_dead_workers_never_show_connected(self):
        status={'state':'streaming','time':100}
        self.assertEqual(common.display_state(status,True,now=105),'streaming')
        self.assertEqual(common.display_state(status,True,now=110),'unresponsive')
        self.assertEqual(common.display_state(status,False,now=101),'error')

    def test_both_advertise_leader_keep_audibly_verified_target(self):
        devices=[{'id':k,'leader':True,'reachable':True,'pair_id':'pair'} for k in ('AABBCCDDEE01','AABBCCDDEE02')]
        self.assertEqual(common.choose_leader(devices, preferred='AABBCCDDEE02')['id'],'AABBCCDDEE02')
        devices[1]['reachable']=False
        self.assertEqual(common.choose_leader(devices, preferred='AABBCCDDEE02')['id'],'AABBCCDDEE01')

    def test_offline_pair_or_only_secondary_does_not_start(self):
        with self.assertRaises(RuntimeError):common.choose_leader([])
        with self.assertRaises(RuntimeError):common.choose_leader([{'id':'x','reachable':True,'leader':False,'pair_id':'pair'}])

    def test_reused_pid_is_not_a_worker(self):
        import os,tempfile
        with tempfile.TemporaryDirectory() as folder:
            self.assertIsNone(common.worker_process(os.getpid(),Path(folder)))

    def test_alac_payload_keeps_signed_stereo_samples(self):
        import av
        from engine import wrap_alac
        data=struct.pack('>hh',2000,-1000)*352
        codec=av.CodecContext.create('alac','r')
        codec.extradata=struct.pack('>I4sI',36,b'alac',0)+struct.pack('>IBBBBBBHIII',352,0,16,40,10,14,2,255,0,0,44100)
        codec.open();frame=codec.decode(av.Packet(wrap_alac(data)))[0]
        self.assertEqual(frame.samples,352)
        self.assertEqual(struct.unpack('<h',bytes(frame.planes[0])[:2])[0],2000)
        self.assertEqual(struct.unpack('<h',bytes(frame.planes[1])[:2])[0],-1000)

class LatencyTests(unittest.TestCase):
    def test_reset_preserves_real_rtp_schedule(self):
        import engine
        from pyatv.protocols.raop.protocols import StreamContext
        context=StreamContext();context.reset()
        self.assertEqual(context.latency,4410)
        self.assertEqual(context.rtptime,4410)
        context.bedroom_latency_frames=30000;context.reset()
        self.assertEqual(context.latency,30000)
        context.head_ts+=352
        self.assertEqual(context.rtptime-(context.head_ts-context.start_ts),30000)

    def test_negotiation_obeys_explicit_receiver_floor_and_ceiling(self):
        from latency import negotiated_frames,mode_name
        self.assertEqual(negotiated_frames(500,{}),22050)
        self.assertEqual(negotiated_frames(500,{'latencyMin':44100}),44100)
        self.assertEqual(negotiated_frames(500,{'latencyMax':15435}),15435)
        self.assertEqual(negotiated_frames(500,{'latencyMin':30000,'latencyMax':10000}),30000)
        self.assertEqual(negotiated_frames(500,{'latencyMin':'bad'}),22050)
        self.assertEqual(negotiated_frames(150,{}),6615)
        for bad in (None,{},'unknown'):self.assertEqual(mode_name(bad),'realtime')

    def test_capture_during_handshake_does_not_replay_old_audio(self):
        from latency import LiveQueue
        queue=LiveQueue(clock=lambda:0)
        queue.push(b'old!'*882)
        queue.push(b'new!'*441)
        self.assertEqual(queue.read(352),b'new!'*352)
        self.assertEqual(queue.dropped_frames,882)

    def test_queue_stays_bounded_and_keeps_newest_after_sender_stall(self):
        from latency import LiveQueue
        queue=LiveQueue(clock=lambda:0)
        queue.push(b'old!'*100);queue.read(100)
        queue.push(b'old!'*44100+b'new!'*441)
        self.assertEqual(queue.read(352),b'new!'*352)
        self.assertLessEqual(queue.snapshot()['capture_queue_high_ms'],30)
        self.assertEqual(queue.dropped_frames,44100)

    def test_capture_pause_discards_stale_tail_and_pads_exact_frames(self):
        from latency import LiveQueue
        clock=[0.0];queue=LiveQueue(clock=lambda:clock[0])
        queue.push(b'old!'*100)
        clock[0]=.2
        self.assertEqual(queue.read(352),b'\0'*1408)
        self.assertEqual(queue.dropped_frames,100)
        self.assertEqual(queue.silence_frames,352)
        queue.push(b'new!'*1)
        self.assertEqual(queue.read(2),b'new!'+b'\0'*4)

class RealtimeTests(unittest.TestCase):
    def test_record_latency_floor_is_respected_even_after_setup(self):
        import engine
        from latency import negotiated_frames
        from types import SimpleNamespace
        previous=engine.RECEIVER_WINDOW
        try:
            engine.RECEIVER_WINDOW={}
            engine.receiver_latency_header(SimpleNamespace(headers={'Audio-Latency':'4410'}))
            self.assertEqual(negotiated_frames(50,engine.RECEIVER_WINDOW),4410)
            engine.receiver_latency_header(SimpleNamespace(headers={'audio-latency':'2205'}))
            self.assertEqual(negotiated_frames(50,engine.RECEIVER_WINDOW),4410)
            engine.receiver_latency_header(SimpleNamespace(headers={'Audio-Latency':'invalid'}))
            self.assertEqual(negotiated_frames(50,engine.RECEIVER_WINDOW),4410)
        finally:engine.RECEIVER_WINDOW=previous

    def test_hundred_ms_mode_backs_off_in_small_steps(self):
        from realtime import TransportHealth
        for budget,expected in ((100,120),(120,150),(150,250)):
            clock=[0.0];health=TransportHealth(clock=lambda:clock[0]);health.sent()
            health.retransmit(12);clock[0]=5;self.assertIsNone(health.assess(budget))
            health.retransmit(12);clock[0]=10;self.assertEqual(health.assess(budget),expected)

    def test_hundred_ms_mode_detects_stalls_within_its_smaller_budget(self):
        from realtime import TransportHealth
        clock=[0.0];health=TransportHealth(clock=lambda:clock[0]);health.sent()
        for end,result in ((5,None),(10,120)):
            clock[0]+=.07;health.sent();clock[0]+=.07;health.sent()
            clock[0]=end;self.assertEqual(health.assess(100),result)

    def test_live_anchor_removes_handshake_age_without_changing_rtp_sequence(self):
        from unittest.mock import patch
        import engine
        from pyatv.protocols.raop.protocols import StreamContext
        context=StreamContext();context.reset();seq=context.rtpseq;rtp=context.rtptime
        context.start_ts-=4410;context.head_ts-=4410
        with patch('pyatv.protocols.raop.timing.ntp2ts',return_value=context.head_ts+4410):
            self.assertEqual(engine.anchor_live(context),100)
        self.assertEqual(context.rtpseq,seq)
        self.assertEqual(context.rtptime,rtp)
        self.assertEqual(context.start_ts,context.head_ts)

    def test_audio_loop_and_sender_use_high_resolution_clock(self):
        import time,engine
        from realtime import AudioLoop
        loop=AudioLoop()
        try:
            self.assertLess(loop._clock_resolution,.001)
            before=time.perf_counter();now=loop.time();after=time.perf_counter()
            self.assertTrue(before<=now<=after)
            self.assertIs(engine.stream_client.monotonic,time.perf_counter)
            self.assertIs(engine.stream_client.monotonic_ns,time.perf_counter_ns)
        finally:loop.close()

    def test_repeated_loss_enables_bounded_stability_backoff(self):
        from realtime import TransportHealth
        clock=[0.0];health=TransportHealth(clock=lambda:clock[0]);health.sent()
        for end,result in ((5,None),(10,250)):
            health.retransmit(12);clock[0]=end
            self.assertEqual(health.assess(150),result)
        self.assertEqual(health.retransmit_packets,24)
        self.assertEqual(health.retransmit_requests,2)

    def test_one_bad_window_does_not_reconnect_or_accumulate(self):
        from realtime import TransportHealth
        clock=[0.0];health=TransportHealth(clock=lambda:clock[0]);health.sent()
        health.retransmit(40);clock[0]=5;self.assertIsNone(health.assess(150))
        clock[0]=10;self.assertIsNone(health.assess(150))
        health.retransmit(40);clock[0]=15;self.assertIsNone(health.assess(150))
        self.assertEqual(health.bad_windows,1)

    def test_repeated_sender_stalls_backoff_but_never_loop_above_500(self):
        from realtime import TransportHealth
        clock=[0.0];health=TransportHealth(clock=lambda:clock[0]);health.sent()
        for end,result in ((5,None),(10,250)):
            clock[0]+=.2;health.sent();clock[0]+=.2;health.sent()
            clock[0]=end;self.assertEqual(health.assess(150),result)
        for end in (15,20):
            health.retransmit(40);clock[0]=end;self.assertIsNone(health.assess(500))

    def test_fast_alac_preserves_every_sample_in_both_channels(self):
        import av,random
        from engine import wrap_alac
        randomizer=random.Random(24)
        for count in (1,352):
            left=[randomizer.randint(-32768,32767) for _ in range(count)]
            right=[randomizer.randint(-32768,32767) for _ in range(count)]
            pcm=b''.join(struct.pack('>hh',a,b) for a,b in zip(left,right))
            codec=av.CodecContext.create('alac','r')
            codec.extradata=struct.pack('>I4sI',36,b'alac',0)+struct.pack('>IBBBBBBHIII',352,0,16,40,10,14,2,255,0,0,44100)
            codec.open();frame=codec.decode(av.Packet(wrap_alac(pcm)))[0]
            self.assertEqual(frame.samples,count)
            self.assertEqual(list(struct.unpack('<'+'h'*count,bytes(frame.planes[0])[:count*2])),left)
            self.assertEqual(list(struct.unpack('<'+'h'*count,bytes(frame.planes[1])[:count*2])),right)
        with self.assertRaises(ValueError):wrap_alac(b'bad')

if __name__=='__main__':unittest.main()
