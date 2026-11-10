"""OLED/Studio integration, all hardware and audio I/O are simulated."""
import copy,importlib.util,sys,threading,time,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
import numpy as np
from device_binding import DeviceBinding,DeviceIdentity,resolve_hid
from reconnect_policy import RetryCadence
from run_intent import RunIntent
import studio_profile_watch as watch
from audio import Engine,StereoDuplicator,OutputProcessor
from core import Controls
from windows_audio import attach_endpoint_ids
import test_modified_ui as fixture

AH=dict(index=1,name='Audio Haptic',edited=False,auto_haptics_enable=1)
OFF=dict(index=0,name='Native',edited=False,auto_haptics_enable=0)
def hidrow(path=b'ours',serial='ours',container='A'):
    return dict(path=path,serial_number=serial,container_id=container)
def output(index=1,name='DualSense',endpoint='E1',container='A'):
    return dict(index=index,name=name,endpoint_id=endpoint,container_id=container,id=endpoint,maxOutputChannels=4,hostApi=1)
def binding():
    b=DeviceBinding();b.bind_hid(hidrow());return b

class IdentityTests(unittest.TestCase):
    def test_same_serial_new_path_and_no_unique_other_fallback(self):
        self.assertEqual(resolve_hid([hidrow(b'new')],b'old','ours')['path'],b'new')
        self.assertIsNone(resolve_hid([hidrow(serial='other')],b'old','ours'))
        self.assertIsNone(resolve_hid([hidrow(b'new',None)],b'old'))
        self.assertIsNotNone(resolve_hid([hidrow()],allow_unique=True))
    def test_duplicate_serial_does_not_choose_arbitrary_target(self):
        rows=[hidrow(b'A'),hidrow(b'B')]
        self.assertIsNone(resolve_hid(rows,b'old','ours'))
        self.assertEqual(resolve_hid(rows,b'A','ours')['path'],b'A')
    def test_container_binds_hid_to_audio_and_survives_rename(self):
        b=binding();chosen=b.output([output(),output(2,'DualSense other','E2','B')]);b.bind_output(chosen)
        renamed=output(3,'Renamed audio endpoint','E3','A')
        self.assertEqual(b.output([output(1,'DualSense','E4','B'),renamed]),renamed)
        self.assertIsNone(b.output([output(1,'DualSense','E4','B')]))
        b.bind_hid(hidrow(b'new'));self.assertEqual(b.snapshot().endpoint_id,'E1')
    def test_ambiguous_portaudio_names_cannot_share_an_endpoint(self):
        rows=[dict(index=i,name='Same',maxOutputChannels=4) for i in (1,2)]
        attach_endpoint_ids(rows,endpoints=[dict(id='E1',name='Same',container_id='A')])
        self.assertFalse(any('endpoint_id' in row for row in rows))
    def test_serial_conflict_on_reused_path_clears_old_endpoint(self):
        b=binding();b.bind_output(output());b.bind_hid(hidrow(serial='replacement',container='B'))
        self.assertIsNone(b.snapshot().endpoint_id)
    def test_missing_serial_uses_container_but_contradicting_serial_is_rejected(self):
        self.assertIsNotNone(resolve_hid([hidrow(b'new',None,'A')],b'old','ours','A'))
        self.assertIsNone(resolve_hid([hidrow(b'new','other','A')],b'old','ours','A'))

    def test_explicit_other_device_output_is_rejected_but_stale_name_is_recoverable(self):
        b=binding();b.bind_output(output())
        rows=[output(2,'Renamed endpoint','E2','A'),output(1,'Other DualSense','other','B')]
        self.assertEqual(b.output(rows,name='DualSense')['endpoint_id'],'E2')
        self.assertIsNone(b.output(rows,name='Other DualSense'))

    def test_endpoint_only_identity_never_falls_back_by_name(self):
        b=DeviceBinding();b.bind_output(output())
        self.assertIsNone(b.output([output(endpoint='Other')]))
    def test_cadences_are_short_bounded_then_back_off(self):
        r=RetryCadence();self.assertEqual([r.next_delay(True) for _ in range(6)],[.2,.4,.8,1.2,2.,2.])
        r.reset();self.assertEqual([r.next_delay(False) for _ in range(8)],[.5,1.,2.,4.,8.,10.,10.,10.])
    def test_transport_defaults_stay_unchanged(self):
        self.assertEqual(Engine(process_pid=1).transport_frames,240)
        self.assertEqual(Engine().transport_frames,480)

class EngineReconnectTests(unittest.TestCase):
    def test_changed_endpoint_name_and_id_recover_only_same_container(self):
        import audio
        state={'changed':False};opened=[];waits=[];holder={}
        source=dict(index=0,name='PC input',maxInputChannels=2,defaultSampleRate=48000,isLoopbackDevice=True,hostApi=1)
        first=[source,output()]
        second=[source,output(1,'Other DualSense','other','B'),output(2,'Renamed DualSense','E2','A')]
        b=binding();b.fast_until=float('inf')
        e=Engine(input_name='PC input',output_name='DualSense',controls=Controls(bypass=True),binding=b)
        discard=Mock();e.process_stream=SimpleNamespace(discard_backlog=discard,close=Mock())
        class Stream:
            def write(self,data,**kw):
                if not state['changed']:state['changed']=True;raise OSError('USB re-enumerated')
            def get_output_latency(self):return .01
        class PA:
            def __init__(self):self.rows=list(second if state['changed'] else first)
            def get_device_info_generator(self):return iter(self.rows)
            def get_device_info_by_index(self,index):return next(r for r in self.rows if r['index']==index)
            def get_host_api_info_by_type(self,_):return dict(index=1)
            def is_format_supported(self,*args,**kw):return True
            def open(self,**kw):opened.append(kw['output_device_index']);return Stream()
        def namespace(module):
            def run(args):
                p=module.PyAudio();stream=p.open(output=True,output_device_index=args.out_index,rate=48000,channels=4,frames_per_buffer=480)
                try:stream.write(bytes(480*8))
                except OSError:
                    ns['time'].sleep(1.2)
                    p=module.PyAudio();index=ns['find_dongle_output'](p)
                    stream=p.open(output=True,output_device_index=index,rate=48000,channels=4,frames_per_buffer=480)
                    stream.write(bytes(480*8))
                return 0
            ns={'run':run};return ns
        endpoints=[dict(id=row['endpoint_id'],name=row['name'],container_id=row['container_id']) for row in second if row.get('endpoint_id')]
        with patch.object(audio,'devices',return_value=first),patch.object(audio.pa,'PyAudio',PA),patch.object(audio,'endpoint_snapshot',return_value={'endpoints':endpoints}),patch.object(audio,'original_namespace',side_effect=namespace),patch.object(e.stop_event,'wait',side_effect=lambda seconds:waits.append(seconds)):
            e._run()
        self.assertEqual(e.errors,0,e.status);self.assertEqual(opened,[1,2]);self.assertEqual(waits,[.2]);self.assertEqual(e.output_id,'E2');self.assertEqual(discard.call_count,2)

class WatchReadTests(unittest.TestCase):
    def test_healthy_metadata_does_not_enumerate_or_read_full_slots(self):
        client=Mock();client.profile.return_value={k:AH[k] for k in ('index','name','edited')}
        with patch('hid.device',return_value=Mock()),patch.object(watch,'StudioClient',return_value=client),patch.object(watch,'devices') as scan:
            result=watch.read_current(DeviceIdentity(b'ours','ours'),AH,False)
        scan.assert_not_called();client.profile_state.assert_not_called();client.slots.assert_not_called()
        self.assertEqual(result['profile']['auto_haptics_enable'],1)
    def test_profile_change_and_periodic_mode_validation_use_coherent_state(self):
        for previous,header,mode,full in ((AH,OFF,0,False),(AH,AH,1,True)):
            client=Mock();client.profile.return_value={k:header[k] for k in ('index','name','edited')};client.profile_state.return_value=header
            with patch('hid.device',return_value=Mock()),patch.object(watch,'StudioClient',return_value=client):
                result=watch.read_current(DeviceIdentity(b'ours','ours'),previous,full)
            client.profile_state.assert_called_once();self.assertEqual(result['profile']['auto_haptics_enable'],mode)
    def test_busy_hid_lock_skips_poll(self):
        with watch._DEVICE_LOCK:
            with patch('hid.device') as opened:self.assertIsNone(watch.read_current(DeviceIdentity(b'ours','ours'),AH))
        opened.assert_not_called()
    def test_open_failure_resolves_only_same_serial(self):
        old=Mock();old.open_path.side_effect=OSError('gone');new=Mock();client=Mock();client.profile.return_value={k:AH[k] for k in ('index','name','edited')}
        with patch('hid.device',side_effect=[old,new]),patch.object(watch,'devices',return_value=[hidrow(b'new'),hidrow(b'other','other','B')]),patch.object(watch,'StudioClient',return_value=client):
            result=watch.read_current(DeviceIdentity(b'old','ours'),AH)
        new.open_path.assert_called_once_with(b'new');old.close.assert_called_once();new.close.assert_called_once();self.assertEqual(result['path'],b'new')

class WatchScheduleTests(unittest.TestCase):
    def setUp(self):
        self.now=100.;self.b=binding();self.m=watch.ProfileWatch()
        class Immediate:
            def __init__(self,target,**kw):self.target=target
            def start(self):self.target()
        self.patches=[patch.object(watch.time,'monotonic',lambda:self.now),patch.object(watch.threading,'Thread',Immediate)]
        for p in self.patches:p.start();self.addCleanup(p.stop)
    def tick(self,**kw):return self.m.tick(self.b,seed=AH,**dict(enabled=True,token=1,**kw))
    def test_no_idle_work_and_no_poll_on_every_ui_tick(self):
        with patch.object(watch,'read_current',return_value=dict(path=b'ours',profile=AH,full=False,row=None)) as read:
            self.m.tick(self.b,False,1,seed=AH);self.now+=100;self.m.tick(self.b,False,1,seed=AH);read.assert_not_called()
            self.tick();self.now+=2;self.tick();read.assert_not_called()
            self.now+=1;self.tick();self.now+=1;self.assertIsNotNone(self.tick());self.assertEqual(read.call_count,1)
    def test_manual_stop_discards_already_queued_result(self):
        with patch.object(watch,'read_current',return_value=dict(path=b'ours',profile=OFF,full=True,row=None)):
            self.tick();self.now+=3;self.tick()
            self.assertIsNone(self.m.tick(self.b,False,2,seed=AH))
    def test_settings_work_pauses_queries_and_invalidates_old_result(self):
        with patch.object(watch,'read_current') as read:
            self.tick(paused=True);self.now+=20;self.tick(paused=True);read.assert_not_called()
            self.tick(paused=False);self.now+=2;self.tick();read.assert_not_called()
    def test_query_failures_back_off_and_do_not_invent_off(self):
        with patch.object(watch,'read_current',side_effect=OSError('unknown')):
            self.tick();self.now+=3;self.tick();self.now+=1;self.assertIsNone(self.tick())
            self.assertEqual(self.m.profile,AH);self.assertEqual(self.m.failures,1)

class IntentTests(unittest.TestCase):
    def test_only_off_pause_retains_auto_resume_intent(self):
        for reason in ('manual','process_exit','engine_exit','start_error','route_changed'):
            i=RunIntent();i.request(('game',));i.stop('profile_off');self.assertTrue(i.can_resume(('game',)))
            i.stop(reason);self.assertFalse(i.can_resume(('game',)))
    def test_different_route_cannot_resume(self):
        i=RunIntent();i.request(('old',));i.stop('profile_off');self.assertFalse(i.can_resume(('new',)))

class AppPolicyTests(unittest.TestCase):
    setUp=fixture.ModifiedUITests.setUp
    def tearDown(self):self.ui.profile_watch.close();fixture.ModifiedUITests.tearDown(self)
    def test_off_then_audio_profile_resume_requires_original_intent(self):
        u=self.ui;u.run_intent.request(u._run_route())
        u._external_profile(dict(path=b'ours',profile=OFF,row=hidrow()))
        self.assertTrue(u.run_intent.profile_paused)
        with patch.object(u.profile_watch,'tick',return_value=dict(path=b'ours',profile=AH,row=None)),patch.object(u.battery,'tick'),patch.object(u,'start') as start:
            u.tick();start.assert_called_once_with(automatic=True)
        u.stop()
        with patch.object(u.profile_watch,'tick',return_value=dict(path=b'ours',profile=AH,row=None)),patch.object(u.battery,'tick'),patch.object(u,'start') as start:
            u.tick();start.assert_not_called()
    def test_external_profile_invalidates_studio_write_guard_preserving_draft(self):
        import test_studio_settings as f
        u=self.ui;e=u.studio_settings;e.build();e.doc.load(f.defaults());e.loaded=True;e.write_ready=True
        e.profile_stamp={k:AH[k] for k in ('index','name','edited')};e.doc.values['auto_haptics_gain']=123
        u._external_profile(dict(path=b'ours',profile=OFF,row=hidrow()))
        self.assertFalse(e.write_ready);self.assertEqual(e.doc.values['auto_haptics_gain'],123)
    def test_start_does_not_immediately_scan_whole_slot_catalog(self):
        p=self.ui.studio;p.last_profile_check=time.monotonic();p.choice.set('02 · Audio Haptic')
        with patch.object(p,'task') as task:p.discover(allow_running=True,after_start=True)
        task.assert_not_called();self.assertEqual(p.choice.get(),'02 · Audio Haptic')
    def test_visible_clean_studio_requests_one_scalar_refresh_without_slot_scan(self):
        import test_studio_settings as f
        u=self.ui;e=u.studio_settings;e.build();e.doc.load(f.defaults());e.loaded=True;e.write_ready=True;u.selected_tab=2
        e.profile_stamp={k:AH[k] for k in ('index','name','edited')}
        with patch.object(e,'task') as task:
            u._external_profile(dict(path=b'ours',profile=OFF,row=hidrow()))
        self.assertTrue(e.external_stale);task.assert_called_once();self.assertEqual(task.call_args.args[0],'entry_read')
        self.assertIn('Off',e.identity.get())

    def test_same_profile_mode_change_refreshes_clean_values_but_not_a_draft(self):
        import test_studio_settings as f
        u=self.ui;e=u.studio_settings;e.build();e.doc.load(f.defaults());e.loaded=True;e.write_ready=False;e.path=b'ours'
        current=dict(AH,edited=True);e.profile_stamp={k:current[k] for k in ('index','name','edited')}
        values=f.defaults();values['auto_haptics_enable']=0;e.external_stale=True
        result=dict(rows=[hidrow()],path=b'ours',cfg=19,version='v1.42.0',values=values,profile=dict(current,auto_haptics_enable=0))
        e.merge_entry_snapshot(result)
        self.assertEqual(e.doc.values['auto_haptics_enable'],0);self.assertFalse(e.external_stale)
        e.doc.values['auto_haptics_gain']=123;e.external_stale=True
        e.merge_entry_snapshot(dict(result,profile=current))
        self.assertEqual(e.doc.values['auto_haptics_gain'],123);self.assertFalse(e.write_ready)
    def test_old_start_response_cannot_satisfy_a_new_request(self):
        u=self.ui;u.run_intent.request(u._run_route());p=u.studio;p._active_check_generation=u.run_intent.generation
        u.stop();u.run_intent.request(u._run_route());callback=Mock();p._start_callback=callback
        with patch.object(p,'_begin_start_check') as again:p._finish_start_check((b'ours',AH),None)
        callback.assert_not_called();again.assert_called_once()

    def test_pid_reuse_while_profile_paused_invalidates_original_run_route(self):
        u=self.ui;u.scope.set('process');u.game.set('Game');u.game_map['Game']=123
        u._process_snapshot=[dict(pid=123,started=1.)]
        u.run_intent.request(u._run_route());u.run_intent.stop('profile_off')
        u._process_snapshot=[dict(pid=123,started=2.)]
        self.assertFalse(u.run_intent.can_resume(u._run_route()))

    def test_failed_catalog_read_keeps_confirmed_profile_display(self):
        p=self.ui.studio;p._sync_current_profile(b'ours',AH);old=p.choice.get()
        p.results.put(('discover',([],['unavailable']),None));p.poll()
        self.assertEqual(p.choice.get(),old);self.assertTrue(p.catalog_invalid)
    def test_activation_timeout_reads_state_without_resending_or_resetting(self):
        from studio_slots import Slot
        p=self.ui.studio;p.slots=[Slot(1,'saved','Audio Haptic')];p.slot_paths=[b'ours'];p.choice.configure(values=['02 · Audio Haptic']);p.choice.current(0)
        operations=[]
        with patch.object(p,'task',side_effect=lambda kind,op:operations.append(op)):p.activate()
        def read(path,index=None,action=None):
            if index is not None:raise TimeoutError('reply lost')
            self.assertEqual(action,'read_profile_state');return AH
        with patch('studio_panel.devices',return_value=[hidrow()]),patch('studio_panel.run_device',side_effect=read) as run:
            result=operations[0]()
        self.assertTrue(result['verified']);self.assertEqual(run.call_count,2)
    def test_manual_stop_cancels_pending_start_callback(self):
        u=self.ui;u.run_intent.request(u._run_route());generation=u.run_intent.generation
        callback=Mock();u.studio._start_callback=callback;u.studio._active_check_generation=generation
        u.stop();u.studio._finish_start_check((b'ours',AH),None);callback.assert_not_called()

class SignalEquivalenceTests(unittest.TestCase):
    def baseline(self,name):
        path=Path(__file__).parent/'tests/fixtures/oled-signal'/(name+'.py')
        spec=importlib.util.spec_from_file_location('oled_baseline_'+name,path);m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m);return m
    def test_mix_and_gain_equal_previous_bytes_through_transitions(self):
        from channel_mix import ChannelMixer
        from output_gain import OutputGain
        old=self.baseline('channel_mix').ChannelMixer();new=ChannelMixer()
        oldgain=self.baseline('output_gain').OutputGain();newgain=OutputGain();rng=np.random.default_rng(41)
        for i in range(240):
            ch=(2,6,8)[i//80];n=(37,240,480)[i%3];data=rng.integers(-32768,32767,(n,ch),dtype=np.int16).tobytes()
            controls=dict(rear=i%13<6,lfe=i%17<8,center=i%19<9,limiter='soft' if i%23<11 else 'hard')
            self.assertEqual(old.process(data,ch,48000,**controls),new.process(data,ch,48000,**controls))
            data=rng.integers(-32768,32767,(n,4),dtype=np.int16).tobytes();target=(0.,.5,1.,1.5)[i//60]
            self.assertEqual(oldgain.process(data,target),newgain.process(data,target));self.assertEqual(oldgain.limited_samples,newgain.limited_samples)
    def test_passthroughs_preserve_object_and_transition_state(self):
        from output_gain import OutputGain
        from channel_mix import ChannelMixer
        data=bytes(240*4*2);gain=OutputGain();self.assertIs(gain.process(data,1.),data)
        mixer=ChannelMixer();self.assertIs(mixer.process(data,2,48000),data)
        processor=OutputProcessor();self.assertIs(processor.process(data,Controls(bypass=True)),data)
        for _ in range(10):gain.process(data,0.)
        self.assertIs(gain.process(data,0.),gain.process(data,0.))
        gain.reconnect();self.assertEqual(gain.current,0.)
    def test_reusable_quad_buffer_is_exact_and_returned_bytes_are_independent(self):
        from audio import duplicate_stereo_pcm
        dup=StereoDuplicator();rng=np.random.default_rng(9)
        for n in (0,1,37,240,480,960,240):
            data=rng.integers(-32768,32767,(n,2),dtype=np.int16).tobytes()
            result=dup.process(data);self.assertEqual(result,duplicate_stereo_pcm(data))
            expected=bytes(result);dup.process(bytes(max(1,n)*4));self.assertEqual(result,expected)

if __name__=='__main__':unittest.main()
