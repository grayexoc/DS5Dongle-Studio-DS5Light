"""Deterministic regression checks; no real USB traffic or audio output."""
import queue
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch
import controller_presence as cp
from audio import Engine
from core import Controls
from studio_slots import Slot
import test_modified_ui as fixtures


class PresenceTests(unittest.TestCase):
    def setUp(self):
        self.now=100.;self.calls=0;self.answer=[dict(path=b'old',serial_number='ours')]
        class Immediate:
            def __init__(self,target,**kw):self.target=target
            def start(self):self.target()
        def query():
            self.calls+=1
            if isinstance(self.answer,Exception):raise self.answer
            return self.answer
        self.patches=[patch.object(cp.time,'monotonic',lambda:self.now),patch.object(cp,'devices',query),patch.object(cp.threading,'Thread',Immediate)]
        for p in self.patches:p.start();self.addCleanup(p.stop)
        self.engine=SimpleNamespace(phase='running',errors=0,last_block_time=self.now,stop_event=threading.Event())
        self.monitor=cp.ControllerPresence()
    def tick(self,progress=True,**kw):
        self.now+=1
        if progress:self.engine.last_block_time=self.now
        self.monitor.tick(self.engine,b'old',**kw)
    def test_healthy_and_silent_never_poll_even_after_30_seconds(self):
        for _ in range(120):self.tick()
        self.assertEqual(self.calls,0);self.assertFalse(self.monitor.disconnected)
    def test_stall_checks_once_if_present_and_does_not_start_backup_poll(self):
        self.tick();self.tick(False);self.tick(False);self.tick(False)
        for _ in range(120):self.tick(False)
        self.assertEqual(self.calls,1)
    def test_two_misses_and_recovery(self):
        self.tick();self.answer=[];self.engine.phase='waiting'
        self.tick();self.tick();self.assertFalse(self.monitor.disconnected)
        self.tick();self.tick();self.assertTrue(self.monitor.disconnected)
        self.answer=[dict(path=b'old',serial_number='ours')]
        self.tick();self.tick();self.assertFalse(self.monitor.disconnected)
    def test_serial_seed_recovers_changed_path_without_extra_healthy_query(self):
        self.tick(serial='ours');self.assertEqual(self.calls,0)
        self.answer=[dict(path=b'new',serial_number='ours')];self.engine.phase='waiting'
        self.tick(serial='ours');self.tick(serial='ours')
        self.assertEqual(self.monitor.misses,0);self.assertFalse(self.monitor.active)
    def test_other_device_or_duplicate_serial_cannot_replace_selected_one(self):
        self.tick(serial='ours')
        for candidates in ([dict(path=b'new',serial_number='other')],
                           [dict(path=b'a',serial_number='ours'),dict(path=b'b',serial_number='ours')]):
            self.answer=candidates;self.engine.errors+=1
            self.tick(serial='ours');self.tick(serial='ours')
            self.assertGreater(self.monitor.misses,0)
    def test_enumeration_errors_are_unknown_and_bounded(self):
        self.tick();self.answer=OSError('denied');self.engine.errors=1
        for _ in range(20):self.tick()
        self.assertEqual(self.calls,3);self.assertFalse(self.monitor.disconnected)
    def test_paused_checks_resume_without_losing_event(self):
        self.tick();self.engine.phase='waiting';self.tick(paused=True)
        self.assertEqual(self.calls,0);self.tick();self.assertEqual(self.calls,1)
    def test_stop_and_close_do_not_launch_queries(self):
        self.tick();self.engine.phase='waiting';self.engine.stop_event.set()
        self.tick();self.monitor.close();self.tick();self.assertEqual(self.calls,0)
    def test_stale_worker_result_is_ignored(self):
        self.tick();old=self.monitor.generation
        self.monitor.tick(None,None);self.monitor.results.put((old,False,None))
        self.monitor.tick(None,None);self.assertFalse(self.monitor.disconnected)


class TransportTests(unittest.TestCase):
    def test_vector_routing_preserves_original_pcm(self):
        import numpy as np
        from audio import original_namespace,duplicate_stereo_pcm
        original=original_namespace()['map_stereo_to_4ch']
        rng=np.random.default_rng(77)
        for n in (0,1,37,240,480,960):
            for data in (bytes(n*4),rng.integers(-32768,32767,(n,2),dtype=np.int16).tobytes()):
                self.assertEqual(duplicate_stereo_pcm(data),original(data,'duplicate'))

    def test_smaller_blocks_preserve_dsp_and_gain_output(self):
        import numpy as np
        from audio import OutputProcessor
        data=np.random.default_rng(42).integers(-18000,18000,(4800,4),dtype=np.int16)
        for bypass in (True,False):
            for gain in (1.,1.5):
                controls=Controls(bypass=bypass,gain=gain)
                large=OutputProcessor();small=OutputProcessor()
                a=b''.join(large.process(block.tobytes(),controls) for block in np.split(data,10))
                b=b''.join(small.process(block.tobytes(),controls) for block in np.split(data,20))
                self.assertEqual(a,b)
    def test_mode_specific_defaults_preserve_device_loopback(self):
        self.assertEqual(Engine().transport_frames,480)
        self.assertEqual(Engine(process_pid=123).transport_frames,240)
    def test_invalid_block_rejected(self):
        with self.assertRaises(ValueError):Engine(transport_frames=120)
    def run_transport(self,fail_small=False,fail_all=False,diagnostics=True):
        e=Engine(controls=Controls(bypass=True),transport_frames=240);e.diagnostics_enabled=diagnostics;opened=[];writes=[];holder={}
        rows=[dict(index=0,name='PC Loopback',maxInputChannels=2,maxOutputChannels=0,defaultSampleRate=48000,isLoopbackDevice=True),
              dict(index=1,name='DualSense',maxOutputChannels=4,hostApi=1,endpoint_id='output')]
        class Stream:
            def get_read_available(self):return 240
            def read(self,n,**kw):return bytes(n*2*2)
            def write(self,data,**kw):writes.append(data)
            def get_input_latency(self):return .01
            def get_output_latency(self):return .01
        class PA:
            def get_device_info_by_index(self,i):return rows[i]
            def get_host_api_info_by_type(self,_):return dict(index=1)
            def is_format_supported(self,*a,**kw):return True
            def open(self,**kw):
                opened.append(kw)
                if kw.get('output') and (fail_all or fail_small and kw['frames_per_buffer']==240):raise OSError('buffer refused')
                return Stream()
        def namespace(module):
            def run(args):
                holder['frames']=ns['FRAMES_PER_BUFFER'];p=module.PyAudio()
                inp=p.open(input=True,input_device_index=0,rate=48000,channels=2,frames_per_buffer=240)
                out=p.open(output=True,output_device_index=1,rate=48000,channels=4,frames_per_buffer=240)
                data=inp.read(240);out.write(data*2)
                return 0
            ns={'run':run};return ns
        with patch('audio.devices',return_value=rows),patch('audio.pa.PyAudio',PA),patch('audio.original_namespace',side_effect=namespace):e._run()
        return e,opened,writes,holder
    def test_hidden_diagnostics_preserve_output_and_health(self):
        off,_,a,_=self.run_transport(diagnostics=False)
        on,_,b,_=self.run_transport(diagnostics=True)
        self.assertEqual(a,b);self.assertEqual(off.blocks,on.blocks)
        self.assertIsNotNone(off.last_block_time)
        self.assertFalse(off.times)
        self.assertTrue(all(not values for values in off.latency_samples.values()))
        self.assertTrue(on.times)

    def test_smaller_block_and_device_queue_estimate(self):
        e,opened,writes,holder=self.run_transport()
        self.assertEqual(e.errors,0,e.status);self.assertEqual(holder['frames'],240)
        self.assertEqual(e.buffer_fallbacks,0);self.assertEqual(e.blocks,1)
        self.assertTrue(e.stats()['latency_ms']['capture_to_output_call_ms'])
        self.assertEqual(e.stats()['capture_timing_source'],'device_queue_estimate')
    def test_buffer_rejection_falls_back_on_same_endpoint(self):
        e,opened,_,_=self.run_transport(fail_small=True)
        outputs=[kw for kw in opened if kw.get('output')]
        self.assertEqual([kw['frames_per_buffer'] for kw in outputs],[240,480])
        self.assertEqual({kw['output_device_index'] for kw in outputs},{1})
        self.assertEqual(e.buffer_fallbacks,1);self.assertEqual(e.errors,0,e.status)
    def test_both_buffer_sizes_fail_closed(self):
        e,opened,writes,_=self.run_transport(fail_all=True)
        self.assertEqual(e.phase,'error');self.assertEqual(e.errors,1);self.assertFalse(writes)


class StudioRefreshTests(unittest.TestCase):
    setUp=fixtures.ModifiedUITests.setUp
    tearDown=fixtures.ModifiedUITests.tearDown
    def test_confirmed_profile_keeps_white_slot_number_and_gold_name(self):
        p=self.ui.studio
        p.slots=[Slot(0,'saved','Mix'),Slot(1,'saved','Other')];p.slot_paths=[b'device']*2
        p.choice.configure(values=['01 · Mix','02 · Other'])
        p._sync_current_profile(b'device',dict(index=0,name='Mix',auto_haptics_enable=1));p.render()
        self.assertEqual(p.choice.get(),'01 · Mix');self.assertEqual(p.choice.current(),0)
        self.assertEqual(p._profile_display,('01 · ','Mix'))
        self.assertEqual(p.profile_caption.cget('text'),'현재 프로필:')
        self.assertEqual([p.profile_text.itemcget(i,'fill') for i in p.profile_text.find_all()],['#eee9df','#d6ad52'])
        p.choice.current(1);p.render()
        self.assertEqual(str(p.choice.cget('style')),'TCombobox')
        p._sync_current_profile(b'device',dict(index=1,name='Other',auto_haptics_enable=1));p.render()
        self.assertEqual(p.choice.get(),'02 · Other');self.assertEqual(p.choice.current(),1)
        self.assertEqual(p.choice.cget('values')[0],'01 · Mix')
        self.assertEqual(p._profile_display,('02 · ','Other'))

    def test_confirmed_profile_before_catalog_is_gold_and_failed_read_is_not(self):
        p=self.ui.studio
        p._sync_current_profile(b'device',dict(index=2,name='Mix',auto_haptics_enable=1));p.render()
        self.assertEqual(p.choice.get(),'03 · Mix')
        self.assertEqual(p._profile_display,('03 · ','Mix'))
        p.choice.set('조회 실패');p.render()
        self.assertIsNone(p._profile_display)
        self.assertEqual(p.profile_caption.cget('text'),'슬롯 목록')

    def test_recent_catalog_is_reused_after_fresh_start_check(self):
        p=self.ui.studio;p.slots=[Slot(0,'saved','Mix')];p.slot_paths=[b'device'];p.profile_path=b'device';p.last_read=time.monotonic()
        p.choice.configure(values=['01 · Mix']);p.choice.current(0)
        with patch.object(p,'task') as task:p.discover(allow_running=True)
        task.assert_not_called();self.assertEqual(p.choice.get(),'01 · Mix')
    def test_explicit_refresh_and_stale_catalog_still_query(self):
        p=self.ui.studio;p.slots=[Slot(0,'saved','Mix')];p.slot_paths=[b'device'];p.profile_path=b'device';p.last_read=time.monotonic()
        with patch.object(p,'task') as task:p.discover(allow_running=True,refresh=True)
        task.assert_called_once()
        p.slots=[Slot(0,'saved','Mix')];p.last_read=-1e9
        with patch.object(p,'task') as task:p.discover(allow_running=True)
        task.assert_called_once()
    def test_start_check_retains_existing_device_serial(self):
        p=self.ui.studio;p._start_callback=lambda:None;operations=[]
        with patch.object(p,'task',side_effect=lambda _,op:operations.append(op)):
            p._begin_start_check()
        profile=dict(index=0,name='Mix',edited=False,auto_haptics_enable=1)
        with patch('studio_panel.devices',return_value=[dict(path=b'device',serial_number='ours')]),patch('studio_panel.run_device',return_value=profile):
            path,result=operations[0]()
        p._observe_profile(path,result)
        self.assertEqual(p.device_serials[b'device'],'ours')

    def test_off_blocks_start_but_mix_and_replace_start_without_notice(self):
        from unittest.mock import Mock
        p=self.ui.studio
        for mode in (0,1,2):
            callback=Mock();p._start_callback=callback
            profile=dict(index=1,name='Audio Haptic',edited=False,auto_haptics_enable=mode)
            p._finish_start_check((b'device',profile),None)
            if mode==0:
                callback.assert_not_called();self.assertEqual(self.ui.status.get(),p.haptics_notice)
            else:
                callback.assert_called_once();self.assertFalse(p.haptics_blocked)

    def test_unknown_profile_does_not_start_or_invent_off(self):
        from unittest.mock import Mock
        p=self.ui.studio;p.auto_haptics_mode=None;callback=Mock();p._start_callback=callback
        p._finish_start_check(None,'timeout')
        callback.assert_not_called();self.assertIsNone(p.auto_haptics_mode)

    def test_profile_activation_and_reset_are_not_repeated_on_read_retry(self):
        p=self.ui.studio;p.slots=[Slot(0,'saved','Mix')];p.slot_paths=[b'old'];p.paths=[b'old']
        p.choice.configure(values=['01 · Mix']);p.choice.current(0);operations=[];calls=[]
        with patch.object(p,'task',side_effect=lambda _,op:operations.append(op)):p.activate()
        reads=[0]
        def run(path,index=None,action=None):
            calls.append((path,index,action))
            if index is not None:return dict(slot=Slot(0,'saved','Mix'),reconnect=True,deferred=False)
            if action=='reconnect_usb':return None
            reads[0]+=1
            if reads[0]==1:raise OSError('settling')
            return dict(index=0,name='Mix',edited=False,auto_haptics_enable=1)
        old=dict(path=b'old',serial_number='ours');new=dict(path=b'new',serial_number='ours')
        with patch('studio_panel.devices',side_effect=[[old],[new],[new]]),patch('studio_panel.run_device',side_effect=run),patch.object(p._cancel,'wait',return_value=False):
            result=operations[0]()
        self.assertTrue(result['verified']);self.assertEqual(result['path'],b'new')
        self.assertEqual(sum(index is not None for _,index,_ in calls),1)
        self.assertEqual(sum(action=='reconnect_usb' for _,_,action in calls),1)

if __name__=='__main__':unittest.main()
