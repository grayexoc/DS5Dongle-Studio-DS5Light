import threading,time,unittest
from subprocess import TimeoutExpired
from unittest.mock import Mock,patch
from collections import deque
from types import SimpleNamespace
from process_audio import ProcessCaptureStream

class ProcessPolicyTests(unittest.TestCase):
    def test_start_failure_reaps_helper_and_closes_all_pipes(self):
        for start_fails in (0,1):
            with self.subTest(reader=start_fails):
                child=Mock()
                child.wait.side_effect=[TimeoutExpired('helper',1.5),TimeoutExpired('helper',2),0]
                readers=[Mock(),Mock()]
                readers[0].is_alive.return_value=bool(start_fails)
                readers[1].is_alive.return_value=False
                starts=[None]*start_fails+[RuntimeError('thread start failed')]
                with patch('process_audio.subprocess.Popen',return_value=child), \
                     patch('process_audio.threading.Thread',side_effect=readers), \
                     patch('process_audio.start_thread',side_effect=starts):
                    with self.assertRaisesRegex(RuntimeError,'thread start failed'):ProcessCaptureStream(123)
                child.terminate.assert_called_once();child.kill.assert_called_once()
                self.assertEqual(child.wait.call_count,3)
                for pipe in (child.stdin,child.stdout,child.stderr):pipe.close.assert_called_once()
                self.assertEqual(readers[0].join.call_count,start_fails)
                readers[1].join.assert_not_called()

    def stream(self):
        s=ProcessCaptureStream.__new__(ProcessCaptureStream)
        s.error=None; s.child=SimpleNamespace(poll=lambda:None)
        s.pending=bytearray(); s.pending_time=0.; s.channels=6
        s.queue=deque(maxlen=8); s.lock=threading.Lock(); s.stale=0; s.messages=[]
        return s
    def test_old_partial_audio_discarded(self):
        s=self.stream(); s.pending=bytearray(5760); s.pending_time=time.perf_counter()-1
        self.assertEqual(s.get_read_available(),0); self.assertEqual(s.stale,1)
    def test_exit_discards_queued_audio(self):
        s=self.stream(); s.pending=bytearray(5760); s.error='target exited'
        with self.assertRaises(RuntimeError):s.get_read_available()
        self.assertEqual(len(s.pending),0)
    def test_fresh_packet_exact(self):
        s=self.stream(); data=bytes(range(256))*23; data=data[:5760]
        s.queue.append((time.perf_counter(),data))
        self.assertEqual(s.get_read_available(),480)
        self.assertEqual(s.read(480),data)
    def test_no_device_fallback_on_reconnect(self):
        # Execute original run with fake output failure; ensure all reopened
        # input requests stay on virtual process device, including reconnect.
        from audio import original_namespace
        ns=original_namespace(); opened=[]; tries=0
        class S:
            def read(self,n,**kw):return bytes(n*6*2)
            def write(self,data,**kw):
                nonlocal tries
                tries+=1
                if tries==1:raise OSError('unplug simulation')
                raise KeyboardInterrupt()
            def close(self):pass
            def stop_stream(self):pass
        class P:
            def get_device_info_by_index(self,index):return dict(name='process',defaultSampleRate=48000,maxInputChannels=6)
            def open(self,**kw):
                if kw.get('input'):opened.append(kw['input_device_index'])
                return S()
            def terminate(self):pass
        ns['pyaudio']=SimpleNamespace(PyAudio=P,paInt16=8)
        ns['time']=SimpleNamespace(time=time.time,sleep=lambda n:None)
        ns['find_dongle_output']=lambda p:2
        ns['find_loopback_by_name']=lambda p,n:-7007
        ns['find_default_loopback']=lambda p:-7007
        ns['run'](SimpleNamespace(list=False,in_index=-7007,out_index=2,map='duplicate',verbose=False))
        self.assertEqual(opened,[-7007,-7007])

if __name__=='__main__':unittest.main(verbosity=2)
