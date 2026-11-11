import struct
import threading
import queue
import unittest
import tkinter as tk
from tkinter import ttk
from types import SimpleNamespace
from unittest.mock import Mock, patch

from device_binding import DeviceIdentity
from device_diagnostics import (CONTROL_BYTES, ReportTiming, collect_snapshot,
    decode_status, decode_transport, run_output_test, tagged_command, tone_block)


def response(page=0):
    data = bytearray(63)
    data[:5] = bytes([0x66, 0x1e, 0, 1, page])
    data[9] = 0x13
    data[12] = 4
    return data


class Client:
    def __init__(self):self.calls = []
    def command(self, command, payload, **kw):
        self.calls.append((command, payload, kw))
        out = response(payload[0])
        out[5:9] = payload[1:]
        return bytes(out)


class DiagnosticTests(unittest.TestCase):
    def test_speaker_muting_is_reported_without_start_or_settings_write(self):
        for values in (dict(disable_speaker=1,speaker_volume=100,speaker_gain=2),
                       dict(disable_speaker=0,speaker_volume=0,speaker_gain=2)):
            with patch('device_diagnostics.tagged_command',return_value=response()) as command, \
                 patch('device_diagnostics.speaker_settings',return_value=values):
                result=run_output_test(None,'speaker',threading.Event(),None,
                                       DeviceIdentity(),dict(endpoint_id='same'))
            self.assertFalse(result['completed'])
            self.assertTrue(result['blocked_reason'])
            self.assertEqual(result['speaker_settings'],values)
            self.assertEqual(command.call_count,1)

    def test_support_probe_distinguishes_explicit_rejection_and_timeout(self):
        from device_diagnostics import probe_support, DiagnosticsUnsupported
        client = Mock()
        data = response();data[2] = 1
        client.command.return_value = bytes(data)
        with patch('device_diagnostics.SettingsClient', return_value=client):
            with self.assertRaises(DiagnosticsUnsupported):probe_support(None)
            client.command.side_effect = TimeoutError('no reply')
            with self.assertRaises(TimeoutError):probe_support(None)

    def test_wire_fields_and_unsigned_counter_wrap_are_preserved(self):
        data = response()
        data[17] = 256 - 42
        data[18] = 3
        data[19:27] = bytes([3, 0, 64, 32, 128, 0, 4, 1])
        data[27:35] = bytes([1, 0, 0, 0, 0, 0, 0, 0])
        struct.pack_into('<HH', data, 13, 100, 200)
        result = decode_status(data)
        self.assertEqual((result['rssi'], result['front_peak'], result['rear_peak']), (-42, 100, 200))
        self.assertEqual(result['last_host']['mute_power'], 128)
        self.assertEqual(result['current']['left_rumble'], 0)
        counters = response(1)
        struct.pack_into('<9IH', counters, 9, 0xffffffff, 2, 3, 4, 5, 6, 7, 8, 9, 10)
        self.assertEqual(decode_transport(counters)['sent'], 0xffffffff)
        self.assertEqual(decode_transport(counters)['queue_depth'], 10)
        for bad in (bytes(63), data[:20], response(1)):
            with self.assertRaises(ValueError):decode_status(bad)

    def test_tagged_requests_require_version_page_and_unique_tag(self):
        client = Client()
        tagged_command(client, 0x1e, 0)
        _, payload, options = client.calls[0]
        self.assertEqual(options['echo'], b'\x01' + payload)
        self.assertEqual(options['echo_offset'], 3)
        self.assertEqual(options['attempts'], 6)

    def test_timing_is_bounded_and_does_not_claim_packet_loss(self):
        meter = ReportTiming()
        meter.mark(b'\x02' + bytes(63), 0)
        for i in range(9000):meter.mark(b'\x01' + bytes(63), i * .004)
        result = meter.snapshot()
        self.assertEqual((result['reports'], result['intervals']), (9000, 8192))
        self.assertAlmostEqual(result['hz'], 250)
        self.assertAlmostEqual(result['p99_ms'], 4)
        self.assertNotIn('lost', result)
        self.assertIsNone(ReportTiming().snapshot()['hz'])

    def test_tones_route_only_to_requested_channels_and_ramp_to_zero(self):
        import numpy as np
        for kind, expected in [('haptic_left', {2}), ('haptic_right', {3}), ('speaker', {0, 1})]:
            pcm = np.frombuffer(tone_block(kind, 2400), dtype='<i2').reshape(-1, 4)
            actual = {i for i in range(4) if pcm[:, i].any()}
            self.assertEqual(actual, expected)
            self.assertLessEqual(abs(pcm.astype('i4')).max(), 3933)
            self.assertFalse(np.frombuffer(tone_block(kind, 0), dtype='<i2')[:4].any())
            self.assertFalse(np.frombuffer(tone_block(kind, 95760), dtype='<i2')[-4:].any())

    def test_unsupported_snapshot_is_exportable_and_no_profile_write_occurs(self):
        class Unsupported:
            def metadata(self, command):return b'fw'
            def profile(self):return {'index': 0}
            def command(self, *args, **kwargs):raise TimeoutError('unsupported')
        with patch('device_diagnostics.SettingsClient', return_value=Unsupported()):
            result = collect_snapshot(None, DeviceIdentity(hid_path=b'a'))
        self.assertEqual(result['diagnostic_error'], 'unsupported')
        self.assertEqual(result['profile'], {'index': 0})

    def test_stop_is_attempted_after_ambiguous_start_and_cancel(self):
        calls = []
        def command(client, command, value):
            calls.append((command, value))
            if command == 0x1e:return response()
            if value:raise TimeoutError('start acknowledgement lost')
            return bytes(63)
        with patch('device_diagnostics.tagged_command', side_effect=command):
            with self.assertRaises(TimeoutError):
                run_output_test(None, 'rumble_left', threading.Event(), None, DeviceIdentity())
        self.assertEqual(calls, [(0x1e, 0), (0x1f, 1), (0x1f, 0)])

    def test_audio_device_change_never_opens_default_output(self):
        from device_diagnostics import audio_test
        from device_binding import DeviceBinding
        binding = DeviceBinding()
        row = dict(endpoint_id='expected', index=3)
        with patch('audio.devices', return_value=[]) as devices, patch('pyaudiowpatch.PyAudio') as opened:
            with self.assertRaises(RuntimeError):
                audio_test('speaker', row, threading.Event(), binding, binding.snapshot())
        devices.assert_called_once_with(opened.return_value)
        opened.return_value.open.assert_not_called()
        opened.return_value.terminate.assert_called_once()

    def audio_fixture(self):
        from device_binding import DeviceBinding
        binding = DeviceBinding()
        binding._identity = DeviceIdentity(hid_path=b'pico', container_id='pico',
            endpoint_id='pico-audio', endpoint_name='DualSense')
        row = dict(index=3, endpoint_id='pico-audio', container_id='pico', name='DualSense',
                   maxOutputChannels=4, hostApi=1)
        return binding, row

    def test_audio_enumerates_and_opens_in_one_context_after_index_change(self):
        from device_diagnostics import audio_test
        binding, row = self.audio_fixture()
        fresh = dict(row, index=7)
        other = dict(index=3, name='Other speakers', maxOutputChannels=8, hostApi=1)
        p = Mock()
        p.get_host_api_info_by_type.return_value = dict(index=1)
        p.get_device_info_generator.return_value = [other, fresh]
        cancel = threading.Event()
        p.open.return_value.write.side_effect = lambda *a, **kw:cancel.set()
        with patch('pyaudiowpatch.PyAudio', return_value=p) as opened, \
             patch('audio.attach_endpoint_ids', side_effect=lambda rows:rows):
            audio_test('speaker', row, cancel, binding, binding.snapshot())
        opened.assert_called_once()
        self.assertEqual(p.open.call_args.kwargs['output_device_index'], 7)
        p.get_device_info_generator.assert_called_once()
        p.terminate.assert_called_once()

    def test_audio_cleanup_runs_even_when_stop_or_close_raises(self):
        from device_diagnostics import audio_test
        for failing in ('stop_stream', 'close'):
            with self.subTest(failing=failing):
                binding, row = self.audio_fixture()
                p = Mock();cancel = threading.Event()
                p.open.return_value.write.side_effect = lambda *a, **kw:cancel.set()
                getattr(p.open.return_value, failing).side_effect = OSError('device removed')
                with patch('audio.devices', return_value=[row]), patch('pyaudiowpatch.PyAudio', return_value=p):
                    with self.assertRaises(OSError):
                        audio_test('speaker', row, cancel, binding, binding.snapshot())
                p.open.return_value.close.assert_called_once()
                p.terminate.assert_called_once()

    def test_cancelled_audio_does_not_even_open_portaudio(self):
        from device_diagnostics import audio_test
        binding, row = self.audio_fixture();cancel = threading.Event();cancel.set()
        with patch('pyaudiowpatch.PyAudio') as opened:
            audio_test('speaker', row, cancel, binding, binding.snapshot())
        opened.assert_not_called()

    def test_slow_prepare_precedes_native_lease_and_paused_stream(self):
        from device_diagnostics import audio_test, TEST_AUDIO_FRAMES
        binding, row = self.audio_fixture();clock = [0.0];events = []
        p = Mock()
        def prepare():clock[0] += 2.1;return p
        def opened(**kwargs):
            self.assertFalse(kwargs['start']);events.append('open');return p.open.return_value
        p.open.side_effect = opened
        def begin():events.append('START');return clock[0] + 2
        def write(*args, **kw):
            events.append('PCM');clock[0] += .005
        p.open.return_value.write.side_effect = write
        with patch('pyaudiowpatch.PyAudio', side_effect=prepare), patch('audio.devices', return_value=[row]), \
             patch('device_diagnostics.time.monotonic', side_effect=lambda:clock[0]):
            audio_test('haptic_left', row, threading.Event(), binding, binding.snapshot(), begin)
        self.assertEqual(events[:3], ['open','START','PCM'])
        self.assertEqual(p.open.return_value.write.call_count, TEST_AUDIO_FRAMES // 240)
        self.assertLess(clock[0], 4.1)

    def test_slow_stream_start_aborts_before_pcm_and_still_sends_stop(self):
        binding, row = self.audio_fixture();clock = [0.0];p = Mock();commands = []
        def command(client, command, value):
            commands.append((command,value));return response() if command == 0x1e else bytes(63)
        def start_stream():clock[0] += 2.1
        p.open.return_value.start_stream.side_effect = start_stream
        with patch('device_diagnostics.tagged_command', side_effect=command), \
             patch('pyaudiowpatch.PyAudio', return_value=p), patch('audio.devices', return_value=[row]), \
             patch('device_diagnostics.time.monotonic', side_effect=lambda:clock[0]):
            with self.assertRaises(TimeoutError):
                run_output_test(None, 'haptic_left', threading.Event(), binding, binding.snapshot(), row)
        self.assertEqual(commands, [(0x1e,0),(0x1f,6),(0x1f,0)])
        p.open.return_value.write.assert_not_called()
        p.terminate.assert_called_once()

    def test_improved_rumble_flag_is_not_mislabelled_native(self):
        for flags0 in range(4):
            for flags2 in (0, 4):
                data = response();data[18] = 1
                data[19] = flags0;data[25] = flags2
                expected = 'rumble' if flags0 & 2 or flags2 & 4 else 'native PCM'
                self.assertEqual(decode_status(data)['last_host']['mode'], expected)

    def test_successful_trigger_test_stops_and_previews_exact_effect(self):
        calls = []
        def command(client, command, value):
            calls.append((command, value))
            return response() if command == 0x1e else bytes(63)
        cancel = SimpleNamespace(is_set=lambda:False, wait=lambda seconds:False)
        with patch('device_diagnostics.tagged_command', side_effect=command):
            result = run_output_test(None, 'trigger_left', cancel, None, DeviceIdentity())
        self.assertTrue(result['completed'])
        self.assertEqual(result['trigger_effect_hex'], '21 fc 03 80 24 49 12 00 00 00 00')
        self.assertEqual(calls, [(0x1e, 0), (0x1f, 4), (0x1f, 0)])

    def test_test_refused_during_audio_or_mix_without_stop_side_effect(self):
        for index, value in ((9, 7), (11, 1)):
            data = response();data[index] = value
            with patch('device_diagnostics.tagged_command', return_value=data) as command:
                with self.assertRaises(RuntimeError):
                    run_output_test(None, 'rumble_left', threading.Event(), None, DeviceIdentity())
            self.assertEqual(command.call_count, 1)


class DialogTests(unittest.TestCase):
    def test_manual_output_requires_selection_and_same_hid(self):
        from tkinter import ttk
        identity=DeviceIdentity(hid_path=b'a',container_id='pico')
        self.app.studio.binding._identity=identity
        row=dict(name='DualSense',endpoint_id='audio',container_id='other',maxOutputChannels=4)
        for changed in (False,True):
            self.app.studio.binding._identity=identity
            with patch.object(tk.Toplevel,'grab_set'):
                self.dialog.show_audio_outputs(dict(outputs=[row],identity=identity))
            popup=next(w for w in self.dialog.window.winfo_children() if isinstance(w,tk.Toplevel))
            box=next(w for w in popup.winfo_children() if isinstance(w,ttk.Combobox))
            button=next(w for w in popup.winfo_children() if isinstance(w,ttk.Button))
            button.invoke()
            self.assertIsNone(self.app.studio.binding.snapshot().endpoint_id)
            box.current(0)
            if changed:self.app.studio.binding._identity=DeviceIdentity(hid_path=b'b')
            button.invoke()
            self.assertEqual(self.app.studio.binding.snapshot().endpoint_id,None if changed else 'audio')

    def setUp(self):
        from device_binding import DeviceBinding
        self.root = tk.Tk();self.root.withdraw()
        self.app = SimpleNamespace(root=self.root, engine=None, _closing=False,
            _close_requested=False, _stopping=False,
            studio=SimpleNamespace(binding=DeviceBinding(), busy=False),
            studio_settings=SimpleNamespace(busy=False), studio_power=SimpleNamespace(blocked=False))
        from device_diagnostics_ui import DeviceDiagnosticsDialog
        with patch.object(tk.Toplevel, 'grab_set'):
            self.dialog = DeviceDiagnosticsDialog(self.app)
        self.app.device_diagnostics = self.dialog

    def tearDown(self):
        self.root.update_idletasks()
        self.root.destroy()

    def test_opening_performs_no_device_work_and_requires_selected_identity(self):
        self.assertIsNone(self.dialog.job)
        self.assertFalse(self.dialog.available('snapshot'))
        self.assertFalse(self.dialog.busy)

    def test_output_tests_block_audio_but_readonly_snapshot_remains_available(self):
        self.app.studio.binding._identity = DeviceIdentity(hid_path=b'a')
        self.app.engine = object()
        self.assertTrue(self.dialog.available('snapshot'))
        self.assertFalse(self.dialog.available('test'))

    def test_close_waits_for_cancel_and_cleanup_before_destroy(self):
        self.dialog.busy = True
        self.dialog.close()
        self.assertTrue(self.dialog.cancel.is_set())
        self.assertTrue(self.dialog.window.winfo_exists())
        self.dialog.results.put(('test', {}, None))
        self.dialog.poll()
        self.assertIsNone(self.app.device_diagnostics)

    def test_export_converts_hid_path_and_keeps_unknown_types_explicit(self):
        self.assertEqual(self.dialog.json_value(b'\x01\xff'), '01ff')
        with self.assertRaises(TypeError):self.dialog.json_value(object())

    def test_timing_summary_and_manual_response_are_saved_as_data(self):
        value = dict(reports=250, hz=250., max_ms=8., intervals_ms=[4., 8., 4.])
        self.dialog.show(value)
        self.assertIn('250.0', self.dialog.metric_values[0].get())
        self.assertIn('8.0', self.dialog.metric_values[1].get())
        self.dialog.last_test = dict(test='haptic_right', completed=True)
        self.dialog.test_results.append(self.dialog.last_test)
        self.dialog.confirm_response(False)
        self.assertIs(self.dialog.test_results[0]['user_confirmed_response'], False)

    def test_xinput_timing_stays_disabled_after_output_test(self):
        self.dialog.report = dict(status=dict(usb_mode='XInput', ready=True, auto_haptics=0))
        self.dialog.results.put(('test', dict(test='rumble_left', completed=True), None))
        self.dialog.poll()
        self.assertEqual(str(self.dialog.measure_button.cget('state')), 'disabled')

    def test_blocked_speaker_and_errors_remain_exportable(self):
        result=dict(test='speaker',completed=False,blocked_reason='speaker disabled')
        self.dialog.results.put(('test',result,None));self.dialog.poll()
        self.assertEqual(self.dialog.status.get(),'speaker disabled')
        self.assertEqual(self.dialog.test_results[-1],result)
        self.dialog.results.put(('test',None,'device removed'));self.dialog.poll()
        self.assertEqual(self.dialog.test_results[-1]['error'],'device removed')

    def test_controller_image_and_rounded_cards_render_without_device_access(self):
        from ui_controls import RoundedCard
        self.dialog.draw_controller()
        self.assertGreater(self.dialog._controller_image.width(),0)
        def descendants(widget):
            for child in widget.winfo_children():
                yield child
                yield from descendants(child)
        self.assertGreaterEqual(sum(isinstance(w,RoundedCard) for w in descendants(self.dialog.window)),8)

    def test_cancelled_none_result_still_closes_dialog(self):
        self.dialog.closing=True
        self.dialog.results.put(('test',None,None))
        self.dialog.poll()
        self.assertIsNone(self.app.device_diagnostics)

    def test_failed_refresh_invalidates_visible_status_and_tests(self):
        self.dialog.report=dict(status=dict(connected=True,ready=True,auto_haptics=0))
        self.dialog.show(self.dialog.report)
        self.dialog.results.put(('snapshot',None,'disconnected'))
        self.dialog.poll()
        self.assertTrue(all(v.get()=='미확인' for v in self.dialog.state_values))
        self.assertTrue(all(str(b.cget('state'))=='disabled' for b in self.dialog.output_buttons))

    def test_controller_shrinks_smoothly_and_keeps_aspect(self):
        self.dialog.diagram.winfo_width=lambda:398
        self.dialog.diagram.winfo_height=lambda:294
        self.dialog.draw_controller()
        first=self.dialog._controller_image.width()
        self.dialog.diagram.winfo_height=lambda:293
        self.dialog.draw_controller()
        self.assertLessEqual(first-self.dialog._controller_image.width(),2)
        self.assertLessEqual(self.dialog._controller_image.height(),293)
        self.assertGreater(self.dialog._controller_image.height(),270)

    def test_minimum_window_keeps_result_and_footer_visible(self):
        self.root.deiconify()
        self.dialog.window.transient('')
        self.dialog.window.deiconify()
        width,height=self.dialog.window.minsize()
        self.dialog.window.geometry(f'{width}x{height}')
        self.dialog.status.set('스피커 시험 · 전송 요청 완료 · 실제 반응을 확인하세요.')
        self.root.update()
        if self.dialog.window.winfo_width()<=1:
            self.skipTest('Desktop window mapping unavailable in this environment')
        bottom=self.dialog.window.winfo_rooty()+self.dialog.window.winfo_height()
        for widget in (self.dialog.result_label,self.dialog.stop_button,*self.dialog.confirm_buttons):
            self.assertTrue(widget.winfo_ismapped())
            self.assertGreaterEqual(widget.winfo_height(),widget.winfo_reqheight())
            self.assertLessEqual(widget.winfo_rooty()+widget.winfo_height(),bottom)

    def test_svg_input_parts_and_neutral_release(self):
        from diagnostic_art import active_parts
        neutral=dict(mask=0,lx=128,ly=128,rx=128,ry=128,l2=0,r2=0)
        self.assertFalse(active_parts(neutral))
        state=dict(neutral,mask=(1<<6)|(1<<17),lx=200,l2=100)
        self.assertTrue({'g80','path270','g76','L2'}<=active_parts(state))
        self.assertFalse(active_parts(neutral))

    def test_trigger_bumpers_and_microphone_have_distinct_parts(self):
        from diagnostic_art import active_parts
        self.assertEqual(active_parts(dict(mask=1<<8)),frozenset({'path220'}))
        self.assertEqual(active_parts(dict(mask=1<<10)),frozenset({'L2'}))
        self.assertEqual(active_parts(dict(mask=1<<11)),frozenset({'R2'}))
        self.assertEqual(active_parts(dict(mask=1<<18)),frozenset({'rect228'}))

    def test_input_monitor_stops_before_worker_and_on_close(self):
        monitor=SimpleNamespace(stop=threading.Event(),thread=Mock())
        monitor.thread.is_alive.return_value=False
        self.dialog.input_monitor=monitor
        self.assertTrue(self.dialog.stop_input_monitor())
        self.assertTrue(monitor.stop.is_set())
        monitor.thread.join.assert_called_once()
        self.assertIsNone(self.dialog.input_monitor)

    def test_input_failure_invalidates_status_and_output_buttons(self):
        self.dialog.report=dict(status=dict(ready=True,connected=True,auto_haptics=0))
        self.dialog.input_state=dict(mask=1<<18)
        self.dialog.input_failed('removed')
        self.assertIsNone(self.dialog.input_state)
        self.assertTrue(all(v.get()=='미확인' for v in self.dialog.state_values))
        self.assertTrue(all(str(b.cget('state'))=='disabled' for b in self.dialog.output_buttons))

    def test_stale_input_clears_highlight_and_stops_monitor(self):
        self.dialog.input_monitor=SimpleNamespace(results=queue.SimpleQueue())
        self.dialog.input_identity=self.app.studio.binding.snapshot()
        self.dialog.input_last_received=0
        self.dialog.input_state=dict(mask=1)
        with patch('device_diagnostics_ui.time.monotonic',return_value=1),patch.object(self.dialog,'input_failed') as failed:
            self.dialog.poll_input()
        failed.assert_called_once()
        self.dialog.input_monitor=None

    def test_unchanged_highlight_does_not_recreate_canvas_items(self):
        self.dialog.draw_controller()
        items=self.dialog.diagram.find_all()
        self.dialog.draw_controller()
        self.assertEqual(items,self.dialog.diagram.find_all())

    def test_failed_support_button_is_reenabled_for_another_device(self):
        from device_diagnostics_ui import update_diagnostics_button
        button = ttk.Button(self.root)
        self.app.device_diagnostics_button = button
        self.app._diagnostics_support = dict(identity=(None, None), supported=False, hint='unsupported')
        update_diagnostics_button(self.app)
        self.assertEqual(str(button.cget('state')), 'disabled')
        self.app.studio.binding._identity = DeviceIdentity(hid_path=b'new')
        update_diagnostics_button(self.app)
        self.assertEqual(str(button.cget('state')), 'normal')


if __name__ == '__main__':unittest.main()
