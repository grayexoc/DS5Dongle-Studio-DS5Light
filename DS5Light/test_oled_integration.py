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
    def test_engine_stop_waits_for_owned_studio_worker(self):
        engine = Engine()
        engine._studio_output = worker = Mock()
        worker.wait_closed.side_effect = [False, True]
        self.assertFalse(engine.stop())
        worker.request_stop.assert_called_once()
        self.assertTrue(engine.stop())


    def test_explicit_studio_live_path_does_not_fall_back_to_shared_output(self):
        import audio

        rows = [dict(index=0, name='PC input', maxInputChannels=2, defaultSampleRate=48000,
                     isLoopbackDevice=True, hostApi=1), output()]
        target = rows[1]
        engine = Engine(input_name='PC input', output_name=target['name'],
                        controls=Controls(bypass=True), binding=binding())
        engine.studio_live = True
        engine.diagnostics_enabled = True
        native = Mock()
        pa = Mock()
        pa.get_host_api_info_by_type.return_value = {'index': 1}
        pa.get_device_info_by_index.side_effect = {row['index']: row for row in rows}.__getitem__
        pa.get_device_info_generator.side_effect = lambda: iter(rows)
        payload = b'\x00\xc0' * (480 * 4)
        input_kwargs = dict(input=True, input_device_index=0, rate=48000, channels=2)

        def namespace(module):
            def run(args):
                audio_api = module.PyAudio()
                audio_api.open(**input_kwargs)
                kwargs = dict(output=True, output_device_index=args.out_index, rate=48000, channels=4)
                stream = audio_api.open(**kwargs)
                engine._capture_timing = (audio.time.perf_counter(), None)
                stream.write(payload)
                engine.diagnostics_enabled = False
                stream.write(bytes(len(payload)))
                stream.close()
                with self.assertRaisesRegex(RuntimeError, 'fresh start'):
                    audio_api.open(**kwargs)
                return 0
            return {'run': run}

        with (
            patch.object(audio, 'devices', return_value=rows),
            patch.object(audio.pa, 'PyAudio', return_value=pa),
            patch.object(audio, 'original_namespace', side_effect=namespace),
            patch('studio_replay.verified_endpoint', return_value=target),
            patch('studio_live_output.StudioLiveOutput', return_value=native) as renderer,
        ):
            engine._run()
        self.assertEqual(engine.errors, 0, engine.status)
        renderer.assert_called_once_with(engine.binding, engine.binding.snapshot(), target['endpoint_id'],
                                         engine.stop_event, adaptive_gain=False)
        self.assertEqual(native.write.call_count, 2)
        native.write.assert_any_call(payload, engine.controls, stereo_capture=True, measure=True)
        native.write.assert_called_with(bytes(len(payload)), engine.controls, stereo_capture=True, measure=False)
        self.assertEqual(engine.blocks, 2)
        self.assertEqual(engine.peak, 0.5)
        for key in ('capture_to_output_call_ms', 'output_write_wait_ms'):
            self.assertEqual(len(engine.latency_samples[key]), 1)
            self.assertGreaterEqual(engine.latency_samples[key][0], 0)
        native.close.assert_called_once()
        pa.open.assert_called_once_with(**input_kwargs)


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
    def test_replace_header_exposes_dsp_source_and_legacy_poll_keeps_verified_value(self):
        from studio_slots import StudioClient

        raw = bytearray(63)
        raw[23:30] = b'SLP2' + bytes((2, 0, 1))
        client = StudioClient(Mock())
        with patch.object(client, 'metadata', return_value=raw):
            profile = client.profile(include_state=True)
        self.assertEqual(profile['ah_dsp_source'], 1)
        self.assertNotIn('mix_native_level', profile)

        old = Mock()
        old.profile.return_value = {k: profile[k] for k in ('index', 'name', 'edited')}
        with patch('hid.device', return_value=Mock()), patch.object(watch, 'StudioClient', return_value=old):
            observed = watch.read_current(DeviceIdentity(b'ours', 'ours'), profile)
        self.assertEqual(observed['profile']['ah_dsp_source'], 1)
        old.profile_state.assert_not_called()

    def test_healthy_metadata_does_not_enumerate_or_read_full_slots(self):
        client=Mock();client.profile.return_value={k:AH[k] for k in ('index','name','edited')}
        with patch('hid.device',return_value=Mock()),patch.object(watch,'StudioClient',return_value=client),patch.object(watch,'devices') as scan:
            result=watch.read_current(DeviceIdentity(b'ours','ours'),AH,False)
        scan.assert_not_called();client.profile_state.assert_not_called();client.slots.assert_not_called()
        self.assertEqual(result['profile']['auto_haptics_enable'],1)
    def test_extended_settings_revision_is_read_with_the_route_in_one_request(self):
        profile = dict(AH, config_token='01000000aabbccdd')
        client = Mock()
        client.profile.return_value = profile
        with patch('hid.device', return_value=Mock()), patch.object(watch, 'StudioClient', return_value=client):
            result = watch.read_current(DeviceIdentity(b'ours', 'ours'), AH)
        client.profile.assert_called_once_with(include_mute=True, include_state=True, include_revision=True)
        client.profile_state.assert_not_called()
        self.assertEqual(result['profile']['config_token'], profile['config_token'])
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

    def test_open_failure_uses_selected_binding_to_recover_mode_switch(self):
        old=Mock();old.open_path.side_effect=OSError('gone')
        new=Mock();client=Mock();client.profile.return_value=dict(AH)
        b=binding();identity=b.snapshot();row=hidrow(b'new')
        with patch('hid.device',side_effect=[old,new]),patch.object(watch,'devices',return_value=[row]),patch.object(watch,'StudioClient',return_value=client),patch.object(b,'resolve_hid',return_value=row) as resolve:
            result=watch.read_current(identity,AH,binding=b)
        resolve.assert_called_once_with([row],external_mode_change=True)
        self.assertEqual(result['row'],row)

    def test_pad_profile_switch_from_xbox_recovers_native_hid(self):
        xbox=dict(path=b'vid_1209',vendor_id=0x1209,product_id=1,
                  usb_parent_id='xbox',serial_number='pico',container_id='xbox-container')
        native=dict(path=b'vid_054c',vendor_id=0x054c,product_id=0x0ce6,
                    usb_parent_id='native',serial_number=None,container_id='native-container')
        other=dict(native,path=b'other',usb_parent_id='other')
        b=DeviceBinding()
        old=Mock();old.open_path.side_effect=OSError('gone')
        new=Mock();client=Mock();client.profile.return_value=dict(OFF)
        with patch('windows_device_identity.usb_port_paths',side_effect=lambda parent:
                   ('pico-port',) if parent in ('xbox','native') else ('other-port',)):
            b.bind_hid(xbox)
            identity=b.snapshot()
            self.assertIsNone(b.resolve_hid([other],external_mode_change=True))
            duplicate=dict(native,path=b'rostered-duplicate')
            self.assertIsNone(b.resolve_hid([native,duplicate],external_mode_change=True))
            with patch('hid.device',side_effect=[old,new]),patch.object(watch,'devices',return_value=[other,native]),patch.object(watch,'StudioClient',return_value=client):
                result=watch.read_current(identity,AH,binding=b)
            self.assertEqual(result['row'],native)
            self.assertEqual(result['profile'],OFF)
            new.open_path.assert_called_once_with(native['path'])
            rebound=b.bind_hid(result['row'])
            self.assertEqual(rebound.serial,'pico')
            self.assertEqual(rebound.usb_parent_id,'native')

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

    def test_recovery_tries_quickly_after_loss_then_returns_to_normal(self):
        data=dict(path=b'ours',profile=AH,full=True,row=None)
        with patch.object(watch,'read_current',side_effect=[OSError('lost')]*4+[data]):
            self.tick()
            for delay in (.5,1.,2.,30.):
                self.now=self.m.next_check
                self.tick();self.tick()
                self.assertAlmostEqual(self.m.next_check-self.now,delay)
            self.now=self.m.next_check
            self.tick()
            self.assertTrue(self.tick()['recovered'])
            self.assertAlmostEqual(self.m.next_check-self.now,self.m.INTERVAL)

    def test_missing_pico_stops_probing_until_windows_notification(self):
        self.m.event_discovery=True
        data=dict(path=b'ours',profile=AH,full=True,row=None)
        responses=[OSError('lost')]*4+[OSError('not ready'),data]
        with patch.object(self.m.events,'tick'),patch.object(watch,'read_current',side_effect=responses) as read:
            self.tick()
            for _ in range(4):
                self.now=self.m.next_check
                self.tick();self.tick()
            self.assertEqual(self.m.next_check,float('inf'))
            self.now+=300
            self.tick()
            self.assertEqual(read.call_count,4)
            self.m.wake_discovery()
            self.tick()
            self.assertEqual(read.call_count,5)
            self.tick()
            self.assertAlmostEqual(self.m.next_check-self.now,.5)
            self.now=self.m.next_check
            self.tick()
            self.assertTrue(self.tick()['recovered'])
            self.assertEqual(read.call_count,6)

    def test_notification_waits_for_settings_before_starting_recovery_window(self):
        self.m.event_discovery=True
        with patch.object(self.m.events,'tick'),patch.object(watch,'read_current',side_effect=OSError('not ready')) as read:
            self.tick(paused=True)
            self.m.wake_discovery()
            self.now+=10
            self.tick(paused=True)
            read.assert_not_called()
            self.tick()
            self.assertEqual(self.m.recovery_until,self.now+5)
            self.now+=1
            self.tick()
            self.assertAlmostEqual(self.m.next_check-self.now,.5)

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
            u._watch_external_profile();start.assert_called_once_with(automatic=True)
        u.stop()
        with patch.object(u.profile_watch,'tick',return_value=dict(path=b'ours',profile=AH,row=None)),patch.object(u.battery,'tick'),patch.object(u,'start') as start:
            u._watch_external_profile();start.assert_not_called()
    def test_external_profile_invalidates_studio_write_guard_preserving_draft(self):
        import test_studio_settings as f
        u=self.ui;e=u.studio_settings;e.build();e.doc.load(f.defaults());e.loaded=True;e.write_ready=True
        e.profile_stamp={k:AH[k] for k in ('index','name','edited')};e.doc.values['auto_haptics_gain']=123
        u._external_profile(dict(path=b'ours',profile=OFF,row=hidrow()))
        self.assertFalse(e.write_ready);self.assertEqual(e.doc.values['auto_haptics_gain'],123)

    def test_same_profile_reconnect_reopens_visible_editor_on_path_change(self):
        u=self.ui
        e=u.studio_settings;e.build()
        u._external_profile(dict(path=b'ours',profile=AH,row=hidrow()))
        e.path=b'ours';e.loaded=e.write_ready=True
        e.profile_stamp={k:AH[k] for k in ('index','name','edited')}
        e.doc.load({'auto_haptics_enable':AH['auto_haptics_enable']})
        u.selected_tab=2
        with patch.object(e,'begin_entry') as refresh:
            u._external_profile(dict(path=b'new',profile=AH,row=dict(hidrow(),path=b'new')))
        self.assertFalse(e.write_ready);self.assertTrue(e.external_stale)
        refresh.assert_called_once()

    def test_read_failure_is_reset_once_when_same_path_recovers(self):
        u=self.ui
        e=u.studio_settings;e.build();u.selected_tab=2
        u._external_profile(dict(path=b'ours',profile=AH,row=hidrow()))
        e.path=b'ours';e.loaded=False;e.entry_failed=True;e.external_stale=True
        with patch.object(e,'begin_entry') as refresh:
            u._external_profile(dict(path=b'ours',profile=AH,row=None,recovered=True))
            u._external_profile(dict(path=b'ours',profile=AH,row=None))
        refresh.assert_called_once()
    def test_verified_mix_observation_switches_live_channel_route(self):
        u=self.ui
        u.engine=SimpleNamespace(front_only=False,studio_live=False)
        try:
            with patch.object(u,'render'),patch.object(u,'stop') as stop:
                for mode,level,source,front in ((1,50,0,True),(1,0,0,False),(1,100,0,True),
                                                (2,0,1,False),(1,100,0,True),
                                                (2,100,0,False),(2,100,1,False),(2,100,0,False)):
                    # Rear control uses the managed renderer when filtering;
                    # the legacy bypass path must still carry both pairs.
                    rear=(mode,source)==(2,1)
                    stop.reset_mock()
                    u._external_profile(dict(path=b'ours',row=hidrow(),profile=dict(AH,auto_haptics_enable=mode,
                                              mix_native_level=level,ah_dsp_source=source)))
                    self.assertEqual(u.engine.front_only,front)
                    self.assertEqual(stop.call_count,int(u.engine.studio_live!=rear))
                    u.engine.studio_live=rear
        finally:u.engine=None
    def test_revision_only_observation_invalidates_preview_without_restarting_audio(self):
        u = self.ui
        original = dict(AH, config_token='01000000aabbccdd')
        changed = dict(original, config_token='02000000aabbccdd')
        u._external_profile(dict(path=b'ours', row=hidrow(), profile=original))
        u.engine = SimpleNamespace(front_only=False, studio_live=False)
        diagnostic = u.device_diagnostics = Mock(optimizer_result=None)
        editor = u.studio_settings
        editor.path = b'ours'
        editor.loaded = editor.write_ready = True
        editor.profile_revision = original['config_token']
        editor.doc.load({'auto_haptics_gain': 100})
        editor.doc.values['auto_haptics_gain'] = 110
        try:
            with patch.object(u, 'stop') as stop:
                u._external_profile(dict(path=b'ours', profile=changed))
                diagnostic.invalidate_optimizer_preview.assert_called_once_with()
                stop.assert_not_called()
                self.assertEqual(u.studio.observed_profile_revision, changed['config_token'])
                self.assertTrue(editor.external_stale)
                self.assertFalse(editor.write_ready)
                self.assertEqual(editor.doc.values['auto_haptics_gain'], 110)
                diagnostic.reset_mock()
                u._external_profile(dict(path=b'ours', profile=changed))
                diagnostic.invalidate_optimizer_preview.assert_not_called()
                diagnostic.optimizer_result = {'revision': original['config_token']}
                u._external_profile(dict(path=b'ours', profile=changed))
                diagnostic.invalidate_optimizer_preview.assert_called_once_with()
        finally:
            u.device_diagnostics = None
            u.engine = None
    def test_start_does_not_immediately_scan_whole_slot_catalog(self):
        p=self.ui.studio;p.last_profile_check=time.monotonic();p.choice.set('02 · Audio Haptic')
        with patch.object(p,'task') as task:p.discover(allow_running=True,after_start=True)
        task.assert_not_called();self.assertEqual(p.choice.get(),'02 · Audio Haptic')
    def test_visible_clean_studio_requests_one_scalar_refresh_without_slot_scan(self):
        import test_studio_settings as f
        u=self.ui;e=u.studio_settings;e.build();e.doc.load(f.defaults());e.loaded=True;e.write_ready=True;u.selected_tab=2
        e.entry_queries_enabled=True
        e.profile_stamp={k:AH[k] for k in ('index','name','edited')}
        with patch.object(e,'task') as task,patch.object(e,'schedule_entry') as schedule:
            u._external_profile(dict(path=b'ours',profile=OFF,row=hidrow()))
            schedule.assert_called_once()
            e.entry_step(e.entry_generation)
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
    def test_mix_matches_previous_bytes_and_gain_preserves_transition_bounds(self):
        from channel_mix import ChannelMixer
        from output_gain import OutputGain
        old=self.baseline('channel_mix').ChannelMixer();new=ChannelMixer()
        oldgain=self.baseline('output_gain').OutputGain();newgain=OutputGain();rng=np.random.default_rng(41)
        for i in range(240):
            ch=(2,6,8)[i//80];n=(37,240,480)[i%3];data=rng.integers(-32768,32767,(n,ch),dtype=np.int16).tobytes()
            controls=dict(rear=i%13<6,lfe=i%17<8,center=i%19<9,limiter='soft' if i%23<11 else 'hard')
            self.assertEqual(old.process(data,ch,48000,**controls),new.process(data,ch,48000,**controls))
            data=rng.integers(-32768,32767,(n,4),dtype=np.int16).tobytes();target=(0.,.5,1.,1.5)[i//60]
            settled=oldgain.current==newgain.current==target
            previous=oldgain.process(data,target)
            result=newgain.process(data,target)
            if settled:
                self.assertEqual(previous,result)
            else:
                difference=np.frombuffer(previous,'<i2').astype(int)-np.frombuffer(result,'<i2')
                self.assertLessEqual(np.max(np.abs(difference)),1)
            self.assertEqual(oldgain.limited_samples,newgain.limited_samples)
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
