"""Exercise the production buffer with independent simulated input/output clocks."""
import threading
import unittest
import numpy as np
from collections import deque
from types import SimpleNamespace
from unittest.mock import patch

from process_audio import ProcessCaptureStream
from capture_clock import CaptureClock


def fake_stream(channels=2):
    s = ProcessCaptureStream.__new__(ProcessCaptureStream)
    s.channels = channels
    s.closed = False
    s.error = None
    s.child = SimpleNamespace(poll=lambda: None)
    s.pending = bytearray()
    s.pending_segments = deque()
    s.pending_time = 0.
    s.queue = deque(maxlen=8)
    s.lock = threading.Lock()
    s.condition = threading.Condition(s.lock)
    s.stale = s.drops = s.discontinuities = 0
    s.messages = []
    return s


class CaptureClockTests(unittest.TestCase):
    def simulate(self, ppm=100, stall=0., seconds=360):
        s = fake_stream()
        now = 1000.01
        packet_number = 1
        stopped_once = False
        stop = threading.Event()
        with patch('process_audio.time.perf_counter', side_effect=lambda: now):
            while now < 1000.+seconds:
                if stall and not stopped_once and now >= 1010.:
                    now += stall
                    stopped_once = True
                while 1000.+packet_number*.01 <= now+1e-9:
                    stamp = 1000.+packet_number*.01
                    self.assertLess(len(s.queue), s.queue.maxlen)
                    s.queue.append((stamp, bytes(480*4), stamp-.01, packet_number*480, 0, stamp))
                    packet_number += 1
                if s.get_read_available() < 240:
                    now = max(now, 1000.+packet_number*.01)
                    stamp = 1000.+packet_number*.01
                    s.queue.append((stamp, bytes(480*4), stamp-.01, packet_number*480, 0, stamp))
                    packet_number += 1
                self.assertEqual(len(s.read_wait(240, stop)), 240*4)
                now += .005*(1+ppm/1_000_000)
        buffered = (len(s.pending)+sum(len(p[1]) for p in s.queue))//4
        self.assertLess(buffered, 960, 'clock mismatch left at least 20ms queued')
        self.assertEqual(s.stale, 0, 'small drift must recover without expired-packet deletion')
        return s

    def test_six_minutes_of_100ppm_drift(self):
        self.simulate()

    def test_one_off_30ms_stall_recovers(self):
        self.simulate(ppm=0, stall=.030, seconds=90)

    def test_balanced_clocks_remain_bit_exact(self):
        s=self.simulate(ppm=0, seconds=15)
        self.assertEqual(s.rate_corrected_blocks, 0)

    def test_1000ppm_drift_stays_bounded(self):
        self.simulate(ppm=1000, seconds=180)

    def test_quick_burst_does_not_enable_correction(self):
        c=CaptureClock()
        for _ in range(4):
            self.assertIsNone(c.plan(240,1440,480))
        self.assertIsNone(c.plan(240,480,480))
        self.assertFalse(c.active)

    def test_repeated_buffer_dips_do_not_hide_sustained_backlog(self):
        c = CaptureClock()
        for i in range(200):
            c.plan(240, 960 if i % 2 else 480, 480)
        self.assertTrue(c.active)

        for i in range(200):
            c.plan(240, 480 if i % 2 else 240, 480)
        self.assertFalse(c.active)

    def test_one_packet_plus_one_block_bursts_stay_below_activation(self):
        c = CaptureClock()
        for i in range(200):
            self.assertIsNone(c.plan(240, 720 if i % 2 else 480, 480))

    def test_exact_block_without_lookahead_keeps_backlog_average(self):
        c = CaptureClock()
        c.active = True
        c.average_frames = 960.
        c.phase = .5
        plan = c.plan(240, 240, 480)
        self.assertEqual(plan[:2], (240, 240))
        self.assertTrue(c.active)
        self.assertEqual(plan[3], 0.)

    def test_multichannel_amplitude_and_fractional_continuity(self):
        for channels in (2,6,8):
            c=CaptureClock()
            c.active=True
            c.average_frames=1200.
            consumed=0
            last=None
            for block in range(35):
                # Shared ramp permits checking source time continuity on every channel.
                source=np.tile(np.arange(consumed,consumed+244,dtype='<i2')[:,None],(1,channels))
                if block==30:c.active=False
                plan=c.plan(240,1200 if block<30 else 240,480)
                if plan is None:
                    break
                data=c.render(source[:plan[1]].tobytes(),channels,plan)
                out=np.frombuffer(data,dtype='<i2').reshape(-1,channels)
                self.assertEqual(out.shape,(240,channels))
                np.testing.assert_array_equal(out,out[:,0,None].repeat(channels,axis=1))
                self.assertTrue(np.all(np.diff(out[:,0])>=0))
                if last is not None:self.assertLessEqual(abs(int(out[0,0])-last-1),1)
                last=int(out[-1,0]);consumed+=plan[0]
            self.assertEqual(c.phase,0.)

    def test_constant_full_scale_and_silence_remain_exact(self):
        for value in (-32768,0,32767):
            c=CaptureClock();c.active=True;c.average_frames=1440.
            plan=c.plan(240,1440,480)
            pcm=np.full((plan[1],8),value,dtype='<i2').tobytes()
            out=np.frombuffer(c.render(pcm,8,plan),dtype='<i2')
            self.assertTrue(np.all(out==value))

    def test_haptic_band_tracks_continuous_source_positions(self):
        c=CaptureClock();c.active=True;c.average_frames=1440.
        consumed=0;errors=[];ideals=[]
        for _ in range(100):
            plan=c.plan(240,1440,480)
            sample_positions=consumed+np.arange(plan[1])
            pcm=np.rint(24000*np.sin(2*np.pi*200*sample_positions/48000)).astype('<i2')
            expected=24000*np.sin(2*np.pi*200*(consumed+plan[2])/48000)
            output=np.frombuffer(c.render(pcm.tobytes(),1,plan),dtype='<i2').astype(float)
            errors.extend(output-expected);ideals.extend(expected)
            consumed+=plan[0]
        relative_rms=np.sqrt(np.mean(np.square(errors)))/np.sqrt(np.mean(np.square(ideals)))
        self.assertLess(relative_rms,.0002)

    def test_rate_correction_advances_source_timing_and_counts(self):
        s=fake_stream(6)
        s._buffer_state()
        s._clock_events=(0,0,0)
        s._clock.active=True;s._clock.phase=.9;s._clock.average_frames=1920.
        pcm=np.arange(1920*6,dtype='<i2').tobytes()
        s.pending=bytearray(pcm)
        s.pending_segments.append([len(pcm),999.99,1000.,0,0,1000.])
        with patch('process_audio.time.perf_counter',return_value=1000.):
            output=s.read(240)
        self.assertEqual(len(output),240*6*2)
        self.assertEqual(s.rate_corrected_frames,1)
        self.assertEqual(len(s.pending),(1920-241)*6*2)
        self.assertAlmostEqual(s.pending_segments[0][1],999.99+241/48000)
        self.assertEqual(s.pending_segments[0][3],241)
        self.assertAlmostEqual(s.last_read_timing[0],999.99+.9/48000)

    def test_wait_cancellation_is_preserved(self):
        s=fake_stream();stop=threading.Event();stop.set()
        with self.assertRaises(KeyboardInterrupt):s.read_wait(240,stop)

    def test_startup_discard_resets_fractional_state(self):
        s=fake_stream();s._buffer_state();s.prefill_discarded_frames=0
        s._clock.active=True;s._clock.phase=.8
        s.discard_backlog()
        self.assertEqual(s._clock.phase,0.)
        self.assertFalse(s._clock.active)

    def test_packet_loss_resets_fractional_state(self):
        s=fake_stream();s._buffer_state()
        s._clock_events=(0,0,0);s._clock.active=True;s._clock.phase=.8
        s.drops=1
        data=bytes(480*4)
        s.pending=bytearray(data)
        s.pending_segments.append([len(data),999.99,1000.,0,0,1000.])
        with patch('process_audio.time.perf_counter',return_value=1000.):
            self.assertEqual(s.read(240),data[:960])
        self.assertEqual(s._clock.phase,0.)
        self.assertEqual(s.rate_corrected_frames,0)


if __name__ == '__main__':
    unittest.main()
