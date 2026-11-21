import struct
import threading
import queue
import unittest
import tkinter as tk
from tkinter import ttk
from types import SimpleNamespace
from unittest.mock import Mock, patch

from device_binding import DeviceIdentity
from studio_i18n import text as tr
from device_diagnostics import (CONTROL_BYTES, ReportTiming, collect_snapshot,
    decode_status, decode_transport, decode_usb_playback, run_output_test, tagged_command, tone_block, audio_recovery_candidates)


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
    def test_usb_playback_observation_is_optional_and_checks_flags(self):
        base = response()
        base[59:63] = bytes((1, 0, 0, 2))
        self.assertTrue(decode_status(base)['usb_playback_diagnostics'])
        page = response(3)
        page[9:11] = bytes((1, 3))
        struct.pack_into('<5I', page, 11, 8, 3, 2, 3, 42)
        self.assertEqual(decode_usb_playback(page), dict(known=True, active=True, generation=8,
                              opens=3, closes=2, invalidations=3, config_revision=42))
        page[31] = 2
        self.assertFalse(decode_usb_playback(page)["local_discard_complete"])
        page[10] = 1
        self.assertTrue(decode_usb_playback(page)["local_discard_complete"])
        page[31] = 1
        self.assertFalse(decode_usb_playback(page)["local_discard_complete"])
        page[10] = 0
        self.assertFalse(decode_usb_playback(page)['known'])
        page[10] = 2
        with self.assertRaises(ValueError):
            decode_usb_playback(page)

    def test_haptic_packet_peaks_are_optional_and_require_a_valid_packet(self):
        legacy = response()
        self.assertNotIn('haptic_packet_valid', decode_status(legacy))
        legacy[59:63] = bytes((1, 127, 128, 0))
        status = decode_status(legacy)
        self.assertFalse(status['haptic_packet_valid'])
        self.assertNotIn('haptic_packet_left_peak', status)
        legacy[62] = 1
        status = decode_status(legacy)
        self.assertTrue(status['haptic_packet_valid'])
        self.assertEqual((status['haptic_packet_left_peak'],status['haptic_packet_right_peak']), (127,128))

    def test_controller_ready_requires_a_current_consistent_diagnostic_sample(self):
        from studio_settings_protocol import SettingsClient
        for flags,expected in ((0,False),(1,False),(2,None),(3,True),(4,False)):
            with self.subTest(flags=flags):
                body=response();body[9]=flags
                stale=response();stale[5:9]=b'OLD!'
                body[5:9]=b'NEW!'
                device=Mock()
                device.send_feature_report.return_value=64
                device.get_feature_report.side_effect=[b'\x84'+stale,b'\x84'+body]
                with patch('device_diagnostics.secrets.token_bytes',return_value=b'NEW!'):
                    self.assertIs(SettingsClient(device,sleep=lambda _:None).controller_ready(),expected)
                self.assertEqual(device.get_feature_report.call_count,2)
        device.get_feature_report.side_effect=None
        device.get_feature_report.return_value=bytes(64)
        self.assertIsNone(SettingsClient(device,sleep=lambda _:None).controller_ready())

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

    def test_headset_test_uses_headset_volume(self):
        data = response()
        data[57:59] = bytes((1, 2))
        values = dict(disable_speaker=0, speaker_volume=0, headset_volume=80)
        with patch('device_diagnostics.tagged_command', return_value=data), \
             patch('device_diagnostics.speaker_settings', return_value=values) as settings, \
             patch('device_diagnostics.audio_test', side_effect=lambda *args: args[-1]()):
            result = run_output_test(None, 'speaker', threading.Event(), None,
                                     DeviceIdentity(), dict(endpoint_id='same'))
            self.assertTrue(result['completed'])
            self.assertEqual(result['output_route'], 'headset')
            self.assertEqual(settings.call_args.args[1], 'headset')
            values['headset_volume'] = 0
            self.assertIn('헤드셋', run_output_test(None, 'speaker', threading.Event(), None,
                          DeviceIdentity(), dict(endpoint_id='same'))['blocked_reason'])

    def test_old_firmware_preserves_speaker_test_without_route_flag(self):
        from device_diagnostics import speaker_block_reason, speaker_settings
        client = Mock()
        client.read_one.side_effect = [0, 50, 1]
        values = speaker_settings(client)
        self.assertNotIn('headset_volume', values)
        self.assertIsNone(speaker_block_reason(values))
        client.read_one.side_effect = [0, 0, 1, 80]
        self.assertIsNone(speaker_block_reason(speaker_settings(client)))
        self.assertNotIn('speaker_diagnostics', decode_status(response()))

    def test_speaker_counter_wrap_and_optional_pages(self):
        from device_diagnostics import finish_speaker_measurement
        client = Mock()
        client.metadata.return_value = b'fw'
        status = response()
        status[57:59] = bytes((1, 1))
        struct.pack_into('<I', status, 43, 1000)
        counters = response(2)
        struct.pack_into('<4I', counters, 9, 0xffffffff, 10, 20, 30)
        with patch('device_diagnostics.SettingsClient', return_value=client), \
             patch('device_diagnostics.tagged_command', side_effect=[status, TimeoutError('BT'), counters]):
            report = collect_snapshot(None, DeviceIdentity())
        self.assertTrue(report['status']['ready'])
        self.assertNotIn('diagnostic_error', report)
        self.assertEqual(report['page_errors'], {'transport': 'BT'})
        status = bytearray(status)
        struct.pack_into('<I', status, 43, 6000)
        struct.pack_into('<4I', counters, 9, 1, 10, 22, 31)
        with patch('device_diagnostics.tagged_command', side_effect=[status, counters]):
            finish_speaker_measurement(None, report, 7000, lambda: False)
        self.assertEqual(list(report['speaker_delta'].values()), [2, 0, 2, 1])
        status[58] = 2
        with patch('device_diagnostics.tagged_command', side_effect=[status, counters]):
            with self.assertRaises(RuntimeError):
                finish_speaker_measurement(None, report, 7000, lambda: False)

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
        self.assertNotIn('usb_audio_blocks', result)
        data[47] = 1
        struct.pack_into('<HHI', data, 48, 100, 200, 0xffffffff)
        result = decode_status(data)
        self.assertEqual((result['rear_left_peak'], result['rear_right_peak'], result['usb_audio_blocks']),
                         (100, 200, 0xffffffff))
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
        for kind, expected in [('haptic_left', {2}), ('haptic_right', {3}), ('speaker', {0})]:
            pcm = np.frombuffer(tone_block(kind, 2400), dtype='<i2').reshape(-1, 4)
            actual = {i for i in range(4) if pcm[:, i].any()}
            self.assertEqual(actual, expected)
            self.assertLessEqual(abs(pcm.astype('i4')).max(), 3933)
            self.assertFalse(np.frombuffer(tone_block(kind, 0), dtype='<i2')[:4].any())
            self.assertFalse(np.frombuffer(tone_block(kind, 71760), dtype='<i2')[-4:].any())
        speaker = np.frombuffer(tone_block('speaker', 0, 72000), dtype='<i2').reshape(-1, 4)
        present = abs(speaker).reshape(300, 240, 4).max(axis=1) > 0
        pulse_starts = present & ~np.vstack((np.zeros((1, 4), dtype=bool), present[:-1]))
        self.assertEqual(list(pulse_starts.sum(axis=0)), [2, 3, 0, 0])
        self.assertFalse((present[:, 0] & present[:, 1]).any())

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

    def test_rumble_comparison_selectors_and_legacy_fallback(self):
        status = response()
        status[56] = 1
        cancel = Mock()
        cancel.is_set.return_value = False
        for mode, side, selector, strength in (
                (0, 'left', 1, 64), (1, 'right', 8, 128),
                (2, 'both', 12, 64), (3, 'left', 13, 128)):
            with self.subTest(mode=mode), patch('device_diagnostics.tagged_command',
                                                return_value=status) as command, \
                    patch('device_diagnostics.SettingsClient.metadata', return_value=b'\x81\x66\x0537\x00'):
                result = run_output_test(None, 'rumble_' + side, cancel, None,
                                         DeviceIdentity(), rumble_mode=mode)
                self.assertEqual([call.args[1:] for call in command.call_args_list],
                                 [(0x1e, 0), (0x1f, selector), (0x1f, 0)])
                self.assertEqual(result['rumble_strength'], strength)
                self.assertEqual(result['rumble_mode'], 'improved' if mode >= 2 else 'classic')
        with patch('device_diagnostics.tagged_command', return_value=response()) as command:
            with self.assertRaises(RuntimeError):
                run_output_test(None, 'rumble_left', cancel, None, DeviceIdentity(), rumble_mode=3)
            self.assertEqual([call.args[1:] for call in command.call_args_list], [(0x1e, 0)])

    def test_v36_false_rumble_capability_never_starts_extended_output(self):
        status = response()
        status[56] = 1
        firmware = b'\x81\x66\x0536\x00'
        self.assertFalse(decode_status(status, firmware)['rumble_comparison'])
        with patch('device_diagnostics.tagged_command', return_value=status) as command, \
                patch('device_diagnostics.SettingsClient.metadata', return_value=firmware):
            with self.assertRaises(RuntimeError):
                run_output_test(None, 'rumble_right', threading.Event(), None,
                                DeviceIdentity(), rumble_mode=1)
        self.assertEqual([call.args[1:] for call in command.call_args_list], [(0x1e, 0)])

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


class AudioRecoveryTests(unittest.TestCase):
    def test_only_verified_active_four_channel_output_is_rebound(self):
        identity = DeviceIdentity(container_id='pico')
        other = dict(name='DualSense', endpoint_id='other', container_id='other', maxOutputChannels=4)
        pico = dict(other, endpoint_id='pico', container_id='pico')
        endpoint = dict(id='pico', container_id='pico', state=1, mix_channels=4)
        inventory = dict(endpoints=[endpoint], complete=True)
        self.assertEqual(audio_recovery_candidates(identity, [other, pico, pico], inventory), ('matched', [pico]))
        endpoint['mix_channels'] = 2
        self.assertEqual(audio_recovery_candidates(identity, [other, pico], inventory), ('channels', []))
        endpoint['state'] = 2
        self.assertEqual(audio_recovery_candidates(identity, [other], inventory), ('disabled', []))
        inventory['endpoints'] = []
        self.assertEqual(audio_recovery_candidates(identity, [other], inventory), ('missing', []))
        unknown = dict(other, container_id=None)
        self.assertEqual(audio_recovery_candidates(identity, [unknown], inventory), ('choose', [unknown]))
        identified = DeviceIdentity(usb_parent_id='pico-usb')
        foreign = dict(other, usb_parent_id='foreign-usb')
        self.assertEqual(audio_recovery_candidates(identified, [foreign], inventory), ('missing', []))
        self.assertEqual(audio_recovery_candidates(identity, [], inventory), ('missing', []))


class DialogTests(unittest.TestCase):
    def test_manual_output_requires_selection_and_same_hid(self):
        from tkinter import ttk
        identity=DeviceIdentity(hid_path=b'a',container_id='pico')
        self.app.studio.binding._identity=identity
        row=dict(name='DualSense',endpoint_id='audio',container_id='other',maxOutputChannels=4)
        self.app.use_recovered_pico_output=Mock()
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
        self.app.use_recovered_pico_output.assert_called_once_with(row)

    def setUp(self):
        from core import Controls
        from device_binding import DeviceBinding
        self.root = tk.Tk();self.root.withdraw()
        self.app = SimpleNamespace(root=self.root, engine=None, controls=Controls(), _closing=False,
            scope=tk.StringVar(self.root, value='process'), game=tk.StringVar(self.root, value='game-a'),
            destination=tk.StringVar(self.root, value='Auto'),
            _close_requested=False, _stopping=False,
            studio=SimpleNamespace(binding=DeviceBinding(), busy=False, rear_control_required=lambda:False),
            studio_settings=SimpleNamespace(busy=False), studio_power=SimpleNamespace(blocked=False))
        self.app.configured_controls = lambda: self.app.controls
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

    def test_studio_tools_fit_when_expanded_at_minimum_size(self):
        dialog = self.dialog
        self.root.tk.call('tk', 'scaling', 120/72)
        width, height = dialog.window.minsize()
        dialog.window.geometry(f'{width}x{height}')
        self.root.deiconify()
        dialog.window.deiconify()
        dialog.window.update()
        self.assertFalse(dialog.exclusive_button.winfo_viewable())
        dialog.studio_tools_button.invoke()
        dialog.window.update_idletasks()
        for button in (dialog.signal_button, dialog.exclusive_button, dialog.preview_button,
                       dialog.route_button, dialog.intensity_button):
            self.assertTrue(button.winfo_viewable(), button.cget('text'))
            self.assertGreaterEqual(button.winfo_width(), button.winfo_reqwidth())
            self.assertLessEqual(button.winfo_rooty() + button.winfo_height(),
                                 dialog.window.winfo_rooty() + dialog.window.winfo_height())
        dialog.studio_tools_button.invoke()
        self.assertFalse(dialog.exclusive_button.winfo_viewable())

    def test_exclusive_replay_uses_selected_hid_and_verified_endpoint(self):
        from core import Controls
        identity = DeviceIdentity(hid_path=b'pico')
        self.app.studio.binding._identity = identity
        controls = self.app.controls = Controls(bypass=True)
        self.dialog.report = {'status': dict(ready=True, auto_haptics=2, usb_playback_diagnostics=True)}
        self.dialog.update_test_buttons()
        self.assertEqual(str(self.dialog.exclusive_button.cget('state')), 'normal')
        with (
            patch('device_diagnostics_ui.filedialog.askopenfilename', return_value='fixture.wav'),
            patch.object(self.dialog, 'start') as start,
            patch('audio.devices', return_value=[]),
            patch('studio_replay.verified_endpoint', return_value={'endpoint_id': 'studio'}),
            patch('studio_replay.play_exclusive_on_endpoint') as play,
        ):
            self.dialog.exclusive_button.invoke()
            kind, operation = start.call_args.args
            self.assertEqual(kind, 'exclusive_replay')
            self.app.controls = Controls()
            operation(Mock(), identity)
            self.assertEqual(play.call_args.args[2], 'studio')
            self.assertIs(play.call_args.kwargs['stereo_controls'], controls)
            client = play.call_args.args[1]
            self.assertFalse(client.cancel())
            self.app.studio.binding._identity = DeviceIdentity(hid_path=b'other')
            self.assertTrue(client.cancel())
            with self.assertRaises(RuntimeError):
                operation(Mock(), identity)
            play.assert_called_once()

    def test_optimizer_preview_displays_and_invalidates_readback_candidate(self):
        import tkinter as tk
        from studio_i18n import text

        identity = DeviceIdentity(hid_path=b'pico')
        self.app.studio.binding._identity = identity
        self.app.studio.rear_control_required = lambda:False
        self.app.engine = Mock()
        self.assertFalse(self.dialog.available('optimizer_preview'))
        self.app.engine = None
        value = {'reason': 'review', 'identity': identity, 'live_output': False,
                 'epoch': self.dialog.preview_epoch, 'observed': {'ah_dsp_source': 1},
                 'changes': {'ah_dsp_source': (1, 0)}}
        self.dialog.results.put(('optimizer_preview', value, None))
        self.dialog.poll()
        self.assertIn('→', self.dialog.status.get())
        self.dialog.invalidate_optimizer_preview()
        stale = text('Studio 상태가 바뀌었습니다. 최적화 미리보기를 다시 조회하세요.')
        self.assertEqual(self.dialog.status.get(), stale)

        self.dialog.results.put(('optimizer_preview', value, None))
        self.dialog.poll()
        self.assertEqual(self.dialog.status.get(), stale)
        self.assertFalse(self.dialog.preview_visible)

    def test_route_button_requires_confirmation_and_restores_verified_candidate(self):
        identity = DeviceIdentity(hid_path=b'pico')
        self.app.studio.binding._identity = identity
        self.app.studio.rear_control_required = lambda:False
        candidate = dict(identity=identity, apply_supported=True, live_output=False,
                         epoch=self.dialog.preview_epoch)
        self.dialog.optimizer_result = candidate
        self.dialog.update_test_buttons()
        before = dict(auto_haptics_enable=0)
        applied = dict(auto_haptics_enable=2)
        with (patch('device_diagnostics_ui.messagebox.askokcancel', side_effect=[False, True]) as confirm,
              patch.object(self.dialog, 'start') as start,
              patch('studio_optimizer_preview.apply_route_preview',
                    return_value=dict(before=before, applied=applied)) as apply,
              patch('studio_optimizer_preview.rollback_route_apply') as restore):
            self.dialog.route_button.invoke()
            start.assert_not_called()
            self.dialog.route_button.invoke()
            kind, operation = start.call_args.args
            self.assertEqual(kind, 'optimizer_write')
            with self.assertRaises(RuntimeError):
                operation(Mock(), DeviceIdentity(hid_path=b'other'))
            apply.assert_not_called()
            receipt = operation(Mock(), identity)
            self.dialog.results.put((kind, receipt, None))
            self.dialog.poll()
            self.assertIs(self.dialog.route_receipt, receipt)
            self.dialog.route_button.invoke()
            kind, operation = start.call_args.args
            self.dialog.results.put((kind, operation(Mock(), identity), None))
            self.dialog.poll()
            self.assertIsNone(self.dialog.route_receipt)
            self.assertEqual(str(self.dialog.route_button.cget('state')), 'disabled')
            self.assertEqual(confirm.call_count, 2)
            apply.assert_called_once()
            restore.assert_called_once()

    def test_intensity_ui_applies_and_restores_without_overlapping_route_receipt(self):
        from dataclasses import asdict
        from core import Controls
        from studio_settings_protocol import SettingsClient

        identity = DeviceIdentity(hid_path=b'pico')
        route = dict(auto_haptics_enable=2, ah_dsp_source=1, auto_mute_replace=1)
        state = dict(revision=1, intensity=200, reply=None)
        hardware = Mock()
        requests = []

        def token():
            return struct.pack('<II', state['revision'], state['intensity'])

        def send(packet):
            self.assertEqual(packet[:4], bytes((0x80, 0x66, 0x26, 1)))
            self.assertEqual(packet[9:17], token())
            self.assertEqual(packet[17], state['intensity'])
            requests.append((packet[4], packet[17], packet[18]))
            state.update(revision=state['revision'] + 1, intensity=packet[18])
            state['reply'] = (bytes((0x84, 0x66, 0x26, 0)) + packet[3:9] + token()).ljust(64, b'\0')
            return len(packet)

        hardware.send_feature_report.side_effect = send
        hardware.get_feature_report.side_effect = lambda *_: state['reply']
        self.app.studio.binding._identity = identity
        self.app.studio.rear_control_required = lambda:True
        self.app.controls = Controls(gain=1.5)
        self.dialog.optimizer_result = dict(
            identity=identity, live_output=True, live_route_verified=True, intensity_supported=True,
            revision=token().hex(), changes={}, observed=route,
            studio_output_gain=2.0, studio_dsp_baseline=dict(ah_xover_hz=0, auto_haptics_gain=200))
        self.dialog.signal_result = dict(current=dict(rear_peak=4915), dsp_controls=asdict(self.app.controls))
        self.dialog.route_receipt = {'identity': identity}
        self.assertFalse(self.dialog.intensity_action_available())
        self.dialog.route_receipt = None
        self.dialog.update_test_buttons()
        with (patch('device_diagnostics_ui.messagebox.askokcancel', return_value=True) as confirm,
              patch.object(self.dialog, 'start') as start,
              patch('audio.devices', return_value=[]),
              patch('studio_replay.verified_endpoint', return_value={'endpoint_id': 'studio'}),
              patch.object(SettingsClient, 'profile', side_effect=lambda **_: {'config_token': token().hex()}),
              patch.object(SettingsClient, 'read_fields',
                           side_effect=lambda _: (dict(route, auto_haptics_gain=state['intensity']), [])),
              patch('studio_optimizer_preview.playback_snapshot', side_effect=lambda _: dict(
                  conditional_intensity_apply=True, known=True, active=False,
                  local_discard_complete=True, config_revision=state['revision']))):
            self.dialog.intensity_button.invoke()
            kind, operation = start.call_args.args
            self.assertEqual(kind, 'intensity_write')
            self.dialog.results.put((kind, operation(hardware, identity), None))
            self.dialog.poll()
            lowered = state['intensity']
            self.assertLess(lowered, 200)
            self.assertEqual(str(self.dialog.route_button.cget('state')), 'disabled')
            self.dialog.intensity_button.invoke()
            kind, operation = start.call_args.args
            self.dialog.results.put((kind, operation(hardware, identity), None))
            self.dialog.poll()
            self.assertIsNone(self.dialog.intensity_receipt)
            self.assertEqual(str(self.dialog.intensity_button.cget('state')), 'disabled')
            confirm.assert_called_once()
            self.assertEqual(requests, [(1, 200, lowered), (2, lowered, 200)])
            self.assertEqual(state['intensity'], 200)

    def test_wav_signal_preview_accepts_no_selected_device_and_exports_no_path(self):
        from core import Controls
        import json
        from pathlib import Path
        from tempfile import TemporaryDirectory

        self.app.controls = Controls()
        self.assertTrue(self.dialog.available('signal_preview'))
        signal = {'current': {'rear_peak': 200}, 'bypass': {'rear_peak': 0}, 'live_pcm': {'rear_peak': 30}}
        with (patch('device_diagnostics_ui.filedialog.askopenfilename', return_value='fixture.wav'),
              patch('device_diagnostics_ui.simpledialog.askstring', side_effect=[None, '1.25, 2']),
              patch.object(self.dialog, 'start') as start,
              patch('studio_optimizer_preview.analyze_rehearsal_windows', return_value=signal) as analyze):
            self.dialog.signal_preview()
            start.assert_not_called()
            self.dialog.signal_preview()
            kind, operation = start.call_args.args
            self.assertEqual(kind, 'signal_preview')
            self.assertEqual(operation(None, DeviceIdentity()), signal)
            analyze.assert_called_once_with(Path('fixture.wav'), self.app.controls, (1.25, 2.0))
        self.dialog.results.put(('signal_preview', signal, None))
        self.dialog.poll()
        self.assertIn('200 / 0', self.dialog.status.get())
        self.assertIn('30', self.dialog.status.get())
        with TemporaryDirectory() as directory:
            report = Path(directory) / 'test.json'
            with patch('device_diagnostics_ui.filedialog.asksaveasfilename', return_value=str(report)):
                self.dialog.export()
            self.assertEqual(json.loads(report.read_text(encoding='utf-8'))['optimizer_signal'], signal)

    def test_wav_candidate_is_unavailable_after_game_switch(self):
        from dataclasses import asdict

        self.dialog.signal_context = self.dialog.current_signal_context()
        self.dialog.signal_result = dict(dsp_controls=asdict(self.app.controls),
                                         pc_gain_candidate=dict(gain=1.0))
        self.assertEqual(self.dialog.pc_gain_action(), (1.0, False))
        self.app.game.set('game-b')
        self.assertEqual(self.dialog.pc_gain_action(), (None, False))

    def test_pc_gain_candidate_applies_only_to_matching_idle_controls(self):
        from dataclasses import asdict, replace
        from core import Controls

        controls = self.app.controls = Controls(gain=2.0)
        self.app.gain = tk.DoubleVar(self.root, value=200)
        self.app.update_controls = Mock(side_effect=lambda: setattr(
            self.app, 'controls', replace(self.app.controls, gain=self.app.gain.get() / 100)))
        signal = self.dialog.signal_result = dict(
            dsp_controls=asdict(controls), current=dict(rear_peak=4915),
            pc_gain_candidate=dict(gain=1.0, rear_peak=3500))
        self.app.studio.rear_control_required = lambda: True
        self.dialog.optimizer_result = dict(
            identity=self.app.studio.binding.snapshot(), live_output=True,
            live_route_verified=True, revision='observed', changes={}, intensity_supported=True,
            observed=dict(auto_haptics_enable=2, ah_dsp_source=1, auto_mute_replace=1),
            studio_output_gain=2.0, studio_dsp_baseline=dict(ah_xover_hz=0, auto_haptics_gain=200))
        self.dialog.update_test_buttons()
        self.assertEqual(str(self.dialog.pc_gain_button.cget('state')), 'normal')
        self.assertFalse(self.dialog.intensity_action_available())
        self.app.engine = Mock()
        self.dialog.pc_gain_button.invoke()
        self.app.engine = None
        self.dialog.update_test_buttons()
        self.app.controls = replace(controls, impact=.5)
        self.dialog.pc_gain_button.invoke()
        self.assertEqual(self.app.gain.get(), 200)
        self.app.update_controls.assert_not_called()
        self.app.controls = controls
        self.dialog.update_test_buttons()
        self.dialog.pc_gain_button.invoke()
        self.assertEqual(self.app.controls, replace(controls, gain=1.0))
        self.app.update_controls.assert_called_once_with()
        self.assertEqual(self.dialog.pc_gain_action(), (2.0, True))
        self.assertEqual(self.dialog.signal_result['current']['rear_peak'], 3500)
        self.assertIsNone(self.dialog.signal_result['pc_gain_candidate'])
        self.assertTrue(self.dialog.intensity_action_available())
        applied = self.app.controls
        self.app.controls = replace(applied, gain=1.25)
        self.app.gain.set(125)
        self.dialog.pc_gain_button.invoke()
        self.assertEqual(self.app.gain.get(), 125)
        self.app.update_controls.assert_called_once_with()
        self.app.controls = applied
        self.app.gain.set(100)
        self.dialog.update_test_buttons()
        self.dialog.pc_gain_button.invoke()
        self.assertEqual(self.app.controls, controls)
        self.assertIs(self.dialog.signal_result, signal)
        self.assertFalse(self.dialog.intensity_action_available())
        self.assertIsNone(self.dialog.pc_gain_restore)
        self.assertEqual(self.app.update_controls.call_count, 2)

        self.dialog.pc_gain_button.invoke()
        newer = dict(dsp_controls=asdict(self.app.controls), current=dict(rear_peak=10))
        self.dialog.signal_result = newer
        self.dialog.pc_gain_button.invoke()
        self.assertEqual(self.app.controls, controls)
        self.assertIs(self.dialog.signal_result, newer)
        self.assertFalse(self.dialog.intensity_action_available())

    def test_optimizer_export_excludes_identity_and_stale_preview(self):
        from dataclasses import asdict, replace
        from core import Controls
        import json
        from pathlib import Path
        from tempfile import TemporaryDirectory

        identity = DeviceIdentity(hid_path=b'private')
        self.app.studio.binding._identity = identity
        self.app.studio.rear_control_required = lambda:True
        self.app.controls = Controls(gain=2.0)
        self.app.configured_controls = lambda: replace(self.app.controls, background=False)
        self.dialog.signal_result = dict(dsp_controls=asdict(self.app.controls),
                                         pc_gain_candidate=dict(gain=1.0))
        self.dialog.optimizer_result = dict(identity=identity, live_output=True, revision='private-token',
                                            observed={'ah_dsp_source': 0},
                                            changes={'ah_dsp_source': (0, 1)}, reason='read only',
                                            apply_supported=True)
        with TemporaryDirectory() as directory:
            log = Path(directory) / 'preview.json'
            with patch('device_diagnostics_ui.filedialog.asksaveasfilename', return_value=str(log)):
                self.dialog.export()
            raw = log.read_text(encoding='utf-8')
            self.assertNotIn('private', raw)
            report = json.loads(raw)
            result = report['optimizer_preview']
            self.assertEqual(result['observed'], {'ah_dsp_source': 0})
            profile = report['haptics_profile']
            self.assertEqual(profile['pc']['desired_controls'], asdict(self.app.controls))
            self.assertFalse(profile['pc']['configured_controls']['background'])
            self.assertIsNone(profile['pc']['engine_requested_controls'])
            self.assertEqual(profile['studio']['desired_route']['ah_dsp_source'], 1)
            self.assertEqual(profile['studio']['route_status'], 'unverified')
            self.assertTrue(result['profile_revision_verified'])
            self.assertTrue(result['conditional_apply_ready_at_preview'])
            self.assertTrue(report['optimizer_signal']['matches_current_pc_controls'])
            self.assertEqual(report['optimizer_signal']['pc_gain_candidate'], {'gain': 1.0})
            self.dialog.optimizer_result.update(
                live_route_verified=True, changes={},
                observed=dict(auto_haptics_enable=2, ah_dsp_source=1, auto_mute_replace=1),
                studio_output_gain=2.0, studio_dsp_baseline=dict(ah_xover_hz=0, auto_haptics_gain=200))
            self.dialog.signal_result.update(
                current=dict(rear_peak=4915), live_pcm=dict(rear_peak=750),
                pc_gain_candidate=dict(gain=1.0, rear_peak=1500, live_pcm=dict(rear_peak=400)))
            self.assertIn('2.70', self.dialog.studio_intensity_summary())
            with patch('device_diagnostics_ui.filedialog.asksaveasfilename', return_value=str(log)):
                self.dialog.export()
            combined = json.loads(log.read_text(encoding='utf-8'))['optimizer_preview']
            self.assertEqual(combined['studio_pc_gain_only_estimate']['proposed'], 200)
            comparison = combined['studio_headroom_comparison']
            self.assertEqual(comparison['simulated_live']['trial_rear_peak'], 400)
            self.assertEqual(comparison['rehearsal']['trial_rear_peak'], 1500)
            self.assertNotIn('studio_intensity_candidate', combined)
            def change_selection_during_save(**_):
                self.app.studio.binding._identity = DeviceIdentity(hid_path=b'other')
                self.app.controls = replace(self.app.controls, gain=1.0)
                return str(log)

            with patch('device_diagnostics_ui.filedialog.asksaveasfilename', side_effect=change_selection_during_save):
                self.dialog.export()
            report = json.loads(log.read_text(encoding='utf-8'))
            self.assertNotIn('optimizer_preview', report)
            self.assertIsNone(report['haptics_profile']['studio']['observed_route'])
            self.assertFalse(report['optimizer_signal']['matches_current_pc_controls'])
            self.assertIsNone(self.dialog.optimizer_result)

    def test_audio_inventory_works_without_hid_and_cannot_rebind(self):
        inventory = dict(endpoints=[dict(id='test', name='Speaker', state=1, mix_channels=4)],
                         complete=True)
        self.assertTrue(self.dialog.available('audio_outputs'))
        with patch.object(self.dialog, 'start') as start, patch('windows_audio.snapshot', return_value=inventory):
            self.dialog.select_audio_output()
            kind, operation = start.call_args.args
            self.assertEqual(kind, 'audio_outputs')
            value = operation(None, DeviceIdentity())
        self.app.use_recovered_pico_output = Mock()
        self.dialog.show_audio_outputs(value)
        popup = next(w for w in self.dialog.window.winfo_children() if isinstance(w, tk.Toplevel))
        output_list = next(w for frame in popup.winfo_children() for w in frame.winfo_children()
                           if isinstance(w, tk.Listbox))
        self.assertIn('4 ch', output_list.get(0))
        self.app.use_recovered_pico_output.assert_not_called()
        self.assertTrue(all(str(button.cget('state')) == 'disabled' for button in self.dialog.output_buttons))

    def test_rumble_choice_falls_back_on_legacy_firmware(self):
        self.app.studio.binding._identity = DeviceIdentity(hid_path=b'pico')
        status = dict(ready=True, auto_haptics=0, rumble_comparison=True)
        self.dialog.report = dict(status=status)
        self.dialog.update_test_buttons()
        choice = self.dialog.rumble_choice
        self.assertEqual(str(choice.cget('state')), 'readonly')
        choice.current(3)
        status['rumble_comparison'] = False
        self.dialog.update_test_buttons()
        self.assertEqual(choice.current(), 0)
        self.assertEqual(str(choice.cget('state')), 'disabled')

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

    def test_forced_close_cancels_monitor_without_waiting_for_hid(self):
        monitor=Mock();self.dialog.input_monitor=monitor;self.dialog.busy=True
        self.dialog.close(force=True)
        monitor.stop.set.assert_called_once();monitor.thread.join.assert_not_called()
        self.assertTrue(self.dialog.cancel.is_set());self.assertIsNone(self.app.device_diagnostics)

    def test_export_converts_hid_path_and_keeps_unknown_types_explicit(self):
        self.assertEqual(self.dialog.json_value(b'\x01\xff'), '01ff')
        with self.assertRaises(TypeError):self.dialog.json_value(object())

    def test_shared_export_omits_device_identifiers_and_retains_measurements(self):
        from unittest.mock import mock_open
        import json
        device=dict(hid_path=b'private HID path',serial='private serial',container_id='private GUID',
                    endpoint_name='private name',edge_serial_present=True)
        self.dialog.report=dict(device=device,status=dict(usb_mode='DualSense'),firmware='47')
        self.dialog.timing=dict(device=device,reports=250)
        file=mock_open()
        with patch('device_diagnostics_ui.filedialog.asksaveasfilename',return_value='diagnostics.json'), \
             patch('pathlib.Path.open',file):self.dialog.export()
        exported=json.loads(file().write.call_args.args[0])
        self.assertEqual(exported['snapshot']['device'],dict(edge_serial_present=True))
        self.assertEqual(exported['input_timing']['device'],dict(edge_serial_present=True))
        self.assertEqual(exported['snapshot']['firmware'],'47')
        self.assertEqual(exported['input_timing']['reports'],250)
        self.assertEqual(self.dialog.report['device']['serial'],'private serial')

    def test_audio_signal_guidance_is_shown_and_cleared_on_read_failure(self):
        status=dict(ready=True,auto_haptics=0,usb_mode='DualSense',speaker_diagnostics=True)
        observation=dict(blocks_delta=1,channels=4,front_peak=0,rear_left_peak=0,rear_right_peak=0)
        with patch.object(self.dialog,'start_input_monitor'):
            self.dialog.show(dict(status=status,audio_observation=observation))
        from device_diagnostics import audio_signal_guidance
        hint = tr(audio_signal_guidance(dict(status=status, audio_observation=observation)))
        self.assertEqual(self.dialog.audio_hint.get(), hint)
        self.dialog.show(dict(diagnostic_error='read failed'))
        self.assertNotEqual(self.dialog.audio_hint.get(), hint)
        self.assertEqual(self.dialog.audio_hint.get(), tr(audio_signal_guidance(dict(diagnostic_error='read failed'))))

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
        self.assertTrue(all(v.get()==tr('미확인') for v in self.dialog.state_values))
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
        self.assertTrue(all(v.get()==tr('미확인') for v in self.dialog.state_values))
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
        self.app.studio.binding._identity = DeviceIdentity(hid_path=b'old')
        self.app._diagnostics_support = dict(identity=(b'old', None), supported=False, hint='unsupported')
        update_diagnostics_button(self.app)
        self.assertEqual(str(button.cget('state')), 'disabled')
        self.app.studio.binding._identity = DeviceIdentity(hid_path=b'new')
        update_diagnostics_button(self.app)
        self.assertEqual(str(button.cget('state')), 'normal')


if __name__ == '__main__':unittest.main()
