from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import json
import unittest
from unittest.mock import Mock, patch

import numpy as np
from scipy.io import wavfile

from studio_replay import ROUTE_FIELDS, confirm_exclusive_close, leased_studio_renderer, observed_usb_transition, packaged_exclusive_main, play, read_fixture, verified_endpoint, verify_route, write_leased_fixture


class StudioReplayTests(unittest.TestCase):
    def test_fixture_requires_exact_format_and_bounded_rear_control(self):
        with TemporaryDirectory() as directory:
            fixture = Path(directory) / 'fixture.wav'
            pcm = np.array([[-4915, 4915, 10, 20]], dtype='<i2')
            wavfile.write(fixture, 48000, pcm)
            np.testing.assert_array_equal(read_fixture(fixture), pcm)
            for rate, data in ((44100, pcm), (48000, pcm[:, :2]), (48000, pcm.astype(np.float32)),
                               (48000, [[0, 0, -1, 0]]), (48000, [[0, 0, 4916, 0]])):
                with self.subTest(rate=rate, data=data):
                    wavfile.write(fixture, rate, np.asarray(data) if hasattr(data, 'dtype')
                                  else np.asarray(data, dtype='<i2'))
                    with self.assertRaises(ValueError):
                        read_fixture(fixture)

    def test_route_rejects_busy_wrong_mode_or_changed_revision(self):
        profile = dict(index=0, config_token='old')
        status = dict(connected=True, ready=True, auto_haptics=2,
                      audio_processing=False, audio_stream=False)
        client = Mock()
        client.profile.return_value = profile
        client.read_fields.return_value = (dict(zip(ROUTE_FIELDS, (2, 1, 1))), [])
        with patch('studio_replay.tagged_command'), patch('studio_replay.decode_status', return_value=status):
            self.assertEqual(verify_route(client, idle=True), profile)
            status['audio_processing'] = True
            with self.assertRaisesRegex(RuntimeError, 'already processing'):
                verify_route(client, idle=True)
            self.assertEqual(verify_route(client, idle=False), profile)
            client.read_fields.return_value = (dict(zip(ROUTE_FIELDS, (2, 0, 1))), [])
            with self.assertRaisesRegex(RuntimeError, 'requires Replace'):
                verify_route(client, idle=False)
            client.profile.side_effect = [profile, dict(profile, config_token='new')]
            with self.assertRaisesRegex(RuntimeError, 'stable'):
                verify_route(client, idle=False)

    def test_shared_rear_control_requires_exclusive_on_lease_firmware(self):
        profile = dict(index=0, config_token='stable')
        status = dict(connected=True, ready=True, auto_haptics=2, audio_processing=False,
                      audio_stream=False, usb_playback_diagnostics=True)
        client = Mock()
        client.profile.return_value = profile
        client.read_fields.return_value = (dict(zip(ROUTE_FIELDS, (2, 1, 1))), [])
        with (
            patch('studio_replay.tagged_command'),
            patch('studio_replay.decode_status', return_value=status),
            patch('studio_replay.playback_snapshot', return_value={'rear_link_epoch': 0}) as snapshot,
        ):
            self.assertEqual(verify_route(client, idle=True), profile)
            snapshot.assert_not_called()
            with self.assertRaisesRegex(RuntimeError, 'requires --exclusive'):
                verify_route(client, idle=True, shared_rear_control=True)
            snapshot.return_value = {'local_discard_complete': True}
            self.assertEqual(verify_route(client, idle=True, shared_rear_control=True), profile)

    def test_endpoint_requires_positive_identity(self):
        binding = Mock()
        binding.snapshot.return_value = SimpleNamespace(usb_parent_id='studio', container_id='same')
        endpoint = dict(endpoint_id='audio', maxOutputChannels=4, usb_parent_id='other', container_id='same')
        binding.output.return_value = endpoint
        with self.assertRaises(RuntimeError):
            verified_endpoint(binding, [endpoint])
        endpoint['usb_parent_id'] = 'studio'
        self.assertIs(verified_endpoint(binding, [endpoint]), endpoint)

    def test_profile_revision_change_stops_playback_before_next_write(self):
        output = Mock()
        output.is_format_supported.return_value = True
        handle = output.open.return_value
        profile = {'config_token': 'original'}
        fixture = np.zeros((24000, 4), dtype='<i2')
        with (
            patch('studio_replay.read_fixture', return_value=fixture),
            patch('studio_replay.InstanceLock'),
            patch('studio_replay.DeviceBinding'),
            patch('studio_replay.studio_devices', return_value=[{'path': b'studio'}]),
            patch('hid.device') as hid,
            patch('pyaudiowpatch.PyAudio', return_value=output),
            patch('studio_replay.devices'),
            patch('studio_replay.verified_endpoint', return_value={'index': 2, 'name': 'Studio'}),
            patch('studio_replay.verify_route', side_effect=[profile, profile, profile, {'config_token': 'changed'}]),
        ):
            with self.assertRaisesRegex(RuntimeError, 'route changed'):
                play(Path('fixture.wav'))
        handle.write.assert_called_once()
        handle.close.assert_called_once()
        output.terminate.assert_called_once()
        hid.return_value.close.assert_called_once()

    def test_observation_requires_explicit_close_after_a_new_open(self):
        before = dict(known=False, active=False, opens=0, closes=0, invalidations=0,
                      config_revision=7, generation=0)
        opened = dict(before, known=True, active=True, opens=1, generation=1)
        closed = dict(opened, active=False, closes=1, generation=2)
        for after, expected, discarded in (
            (closed, True, False), (opened, False, False),
            (dict(closed, local_discard_complete=True), True, True),
            (dict(closed, local_discard_complete=False), True, False),
        ):
            with self.subTest(after=after):
                output = Mock()
                output.is_format_supported.return_value = True
                with (
                    patch('studio_replay.read_fixture', return_value=np.zeros((480, 4), dtype='<i2')),
                    patch('studio_replay.InstanceLock'),
                    patch('studio_replay.DeviceBinding'),
                    patch('studio_replay.studio_devices', return_value=[{'path': b'studio'}]),
                    patch('hid.device'),
                    patch('pyaudiowpatch.PyAudio', return_value=output),
                    patch('studio_replay.devices'),
                    patch('studio_replay.verified_endpoint', return_value={'index': 2, 'name': 'Studio'}),
                    patch('studio_replay.verify_route', return_value={'config_token': 'stable'}),
                    patch('studio_replay.tagged_command'),
                    patch('studio_replay.decode_usb_playback', side_effect=[before, opened, after]),
                    patch('studio_replay.time.monotonic', side_effect=[0, 0, 0, 3]),
                    patch('builtins.print'),
                ):
                    report = play(Path('fixture.wav'), observe_boundary=True)
                self.assertIs(report['observed_close'], expected)
                self.assertIs(report['observed_local_discard'], discarded)
                output.open.return_value.close.assert_called_once()

    def test_transition_rejects_extra_events_stale_revision_or_invalidation(self):
        closed = dict(known=True, active=False, generation=0xffffffff, opens=0xffffffff,
                      closes=12, invalidations=4, config_revision=7)
        opened = dict(closed, active=True, generation=0, opens=0)
        self.assertTrue(observed_usb_transition(closed, opened, active=True))
        for change in (dict(generation=1), dict(opens=1), dict(closes=13),
                       dict(invalidations=5), dict(config_revision=8), dict(known=False)):
            with self.subTest(change=change):
                self.assertFalse(observed_usb_transition(closed, dict(opened, **change), active=True))


    def test_exclusive_renderer_requires_correlated_commit_and_closes_on_error(self):
        before = dict(known=True, active=False, generation=3, opens=1, closes=2,
                      invalidations=0, config_revision=7, rear_link_epoch=5)
        opened = dict(before, active=True, opens=2, generation=4)
        for snapshot, failure in ((opened, None), (dict(opened, rear_link_epoch=6), 'session changed'),
                                  (opened, 'ack lost')):
            with self.subTest(failure=failure):
                client = Mock()
                client.rear_lease_exchange.side_effect = [(12, 5), (12, 6) if failure is None
                                                         else RuntimeError('ack lost')]
                renderer = object()
                from contextlib import contextmanager
                events = []

                @contextmanager
                def open_exclusive():
                    events.append('acquired')
                    try:
                        yield renderer
                    finally:
                        events.append('released')

                with (
                    patch('studio_replay.verify_route', return_value={'config_token': '07000000aabbccdd'}),
                    patch('studio_replay.tagged_command'),
                    patch('studio_replay.decode_usb_playback', side_effect=[before, snapshot]),
                    patch('studio_replay.time.monotonic', return_value=4),
                ):
                    if failure is None:
                        with leased_studio_renderer(client, open_exclusive) as active:
                            self.assertEqual(active, (renderer, opened, 12, 6))
                    else:
                        with self.assertRaisesRegex(RuntimeError, failure):
                            with leased_studio_renderer(client, open_exclusive):
                                self.fail('Unverified session became writable')
                    self.assertEqual(events, ['acquired', 'released'])
                    self.assertEqual(client.rear_lease_exchange.call_count, 1 if 'session changed' == failure else 2)


    def test_changed_revision_never_reserves_or_opens_exclusive_renderer(self):
        client = Mock()
        open_exclusive = Mock()
        with (
            patch('studio_replay.verify_route', return_value={'config_token': '07000000aabbccdd'}),
            patch('studio_replay.playback_snapshot', return_value={'config_revision': 8}),
        ):
            with self.assertRaisesRegex(RuntimeError, 'before reserving'):
                with leased_studio_renderer(client, open_exclusive):
                    self.fail('Stale Studio profile became writable')
        client.rear_lease_exchange.assert_not_called()
        open_exclusive.assert_not_called()

    def test_leased_fixture_closes_on_expiry_or_renewal_failure(self):
        from contextlib import contextmanager
        pcm = np.zeros((14400, 4), dtype='<i2')
        for renewal, times, writes in ((None, [0.1, 1.0], 1),
                                       (RuntimeError('renewal refused'), [0.1, 0.6], 1),
                                       ((12, 1.6), [0.1, 0.6, 0.7, 0.8, 0.9], 3)):
            with self.subTest(renewal=renewal):
                renderer = Mock()
                client = Mock()
                opened = {'generation': 8}
                client.rear_lease_exchange.side_effect = [renewal] if isinstance(renewal, Exception) else None
                client.rear_lease_exchange.return_value = renewal

                @contextmanager
                def lease(*args):
                    try:
                        yield renderer, opened, 12, 1.0
                    finally:
                        renderer.close()

                with (
                    patch('studio_replay.read_fixture', return_value=pcm),
                    patch('studio_replay.leased_studio_renderer', side_effect=lease),
                    patch('studio_replay.time.monotonic', side_effect=times),
                ):
                    if writes == 1:
                        with self.assertRaises(RuntimeError):
                            write_leased_fixture(Path('fixture.wav'), client, Mock())
                    else:
                        write_leased_fixture(Path('fixture.wav'), client, Mock())

                self.assertEqual(renderer.write.call_count, writes)
                renderer.close.assert_called_once()
                if renewal is None:
                    client.rear_lease_exchange.assert_not_called()
                else:
                    client.rear_lease_exchange.assert_called_once_with(3, opened, attempt=12, sequence=1)

    def test_leased_fixture_cannot_finish_after_its_deadline(self):
        from contextlib import nullcontext

        renderer = Mock()
        client = Mock()
        with (
            patch('studio_replay.read_fixture', return_value=np.zeros((4800, 4), dtype='<i2')),
            patch('studio_replay.leased_studio_renderer',
                  return_value=nullcontext((renderer, {'generation': 8}, 12, 1.0))),
            patch('studio_replay.time.monotonic', side_effect=[0.1, 0.6, 1.6]),
        ):
            client.rear_lease_exchange.return_value = (12, 1.6)
            with self.assertRaisesRegex(RuntimeError, 'before the renderer finished'):
                write_leased_fixture(Path('fixture.wav'), client, Mock())
            client.rear_lease_exchange.assert_called_once_with(3, {'generation': 8}, attempt=12, sequence=1)
            renderer.drain.assert_called_once()

    def test_exclusive_cli_uses_verified_endpoint_without_opening_shared_stream(self):
        output = Mock()
        with (
            patch('studio_replay.read_fixture', return_value=np.zeros((480, 4), dtype='<i2')),
            patch('studio_replay.InstanceLock'),
            patch('studio_replay.DeviceBinding'),
            patch('studio_replay.studio_devices', return_value=[{'path': b'studio'}]),
            patch('hid.device'),
            patch('pyaudiowpatch.PyAudio', return_value=output),
            patch('studio_replay.devices'),
            patch('studio_replay.verified_endpoint', return_value={'endpoint_id': 'verified', 'name': 'Studio'}),
            patch('studio_exclusive.prepare_exclusive_renderer') as prepare,
            patch('studio_replay.write_leased_fixture') as write,
            patch('studio_replay.confirm_exclusive_close') as confirm,
            patch('builtins.print'),
        ):
            fixture = Path('fixture.wav')
            play(fixture, exclusive=True)
            prepare.assert_called_once_with('verified')
            self.assertEqual(write.call_args.args[0], fixture)
            output.open.assert_not_called()
            self.assertIs(confirm.call_args.args[1], write.return_value)

    def test_packaged_exclusive_reports_result_and_refuses_existing_report(self):
        with TemporaryDirectory() as directory, patch('studio_replay.play') as replay:
            report = Path(directory) / 'report.json'
            args = ['fixture.wav', '--report', str(report)]
            self.assertEqual(packaged_exclusive_main(args), 0)
            self.assertEqual(json.loads(report.read_text(encoding='utf-8')), {'submitted': True})
            with self.assertRaises(FileExistsError):
                packaged_exclusive_main(args)
            replay.assert_called_once_with(Path('fixture.wav'), exclusive=True)

            replay.side_effect = RuntimeError('lease refused')
            report.unlink()
            self.assertEqual(packaged_exclusive_main(args), 1)
            self.assertEqual(json.loads(report.read_text(encoding='utf-8')),
                             {'submitted': False, 'error': 'lease refused'})

    def test_offline_rehearsal_export_loads_in_the_replay_validator(self):
        from offline import main as offline_main
        with TemporaryDirectory() as directory:
            source = Path(directory) / 'source.wav'
            output = Path(directory) / 'rehearsal.wav'
            stereo = np.tile(np.array([20000, -10000], dtype='<i2'), (100000, 1))
            stereo[:12000] = 0
            wavfile.write(source, 48000, stereo)
            args = ['offline', str(source), str(output), '--studio-rehearsal', '0.25', '--bypass']
            with patch('sys.argv', args), patch('builtins.print'):
                offline_main()
            pcm = read_fixture(output)
            self.assertEqual(pcm.shape, (72000, 4))
            np.testing.assert_array_equal(pcm[0], [4915, -2458, 0, 0])
            self.assertFalse(pcm[:, 2:].any())

    def test_directional_rehearsal_preserves_front_and_switches_rear_sides(self):
        from contextlib import nullcontext
        from offline import main as offline_main
        from studio_rehearsal_format import REHEARSAL_PEAK

        rate = 48000
        time = np.arange(rate) / rate
        bed = .11 * np.sin(2 * np.pi * 3300 * time)
        stereo = np.column_stack((bed, -bed))
        for start, hz, sides in ((.25, 85, (1, 0)), (.5, 400, (0, 1)), (.75, 85, (1, 1))):
            elapsed = time - start
            pulse = .30 * np.sin(2 * np.pi * hz * elapsed) * np.exp(-np.maximum(elapsed, 0) / .018)
            pulse[(elapsed < 0) | (elapsed >= .045)] = 0
            stereo += pulse[:, None] * sides

        with TemporaryDirectory() as directory:
            source = Path(directory) / 'source.wav'
            wavfile.write(source, rate, np.rint(stereo * 32768).astype('<i2'))
            results = []
            for name, flags in (('centered', []), ('directional', ['--stereo-control']),
                                ('combined', ['--stereo-control', '--shape-control'])):
                output = Path(directory) / f'{name}.wav'
                args = ['offline', str(source), str(output), '--studio-rehearsal', *flags]
                with patch('sys.argv', args), patch('builtins.print') as printed:
                    offline_main()
                pcm = read_fixture(output)
                results.append(pcm)
                report = json.loads(printed.call_args.args[0])
                self.assertFalse(report['hardware_haptics_test'])
                self.assertEqual(report['frames'], len(pcm))
                stats = report['studio_rehearsal']
                rear = pcm[:, 2:].astype(float)
                self.assertEqual(stats['start_s'], 0)
                self.assertEqual(stats['stereo_control'], '--stereo-control' in flags)
                self.assertEqual(stats['shape_control'], '--shape-control' in flags)
                self.assertEqual(stats['rear_peak'], rear.max())
                self.assertEqual(stats['rear_ceiling'], REHEARSAL_PEAK)
                np.testing.assert_allclose(stats['rear_rms_lr'], np.sqrt(np.mean(rear**2, axis=0)))
            renderer = Mock()
            with (
                patch('studio_replay.leased_studio_renderer',
                      return_value=nullcontext((renderer, {'generation': 8}, 12, 5.0))),
                patch('studio_replay.time.monotonic', return_value=1.0),
            ):
                write_leased_fixture(output, Mock(), Mock())

        centered, directional, combined = results
        submitted = b''.join(call.args[0] for call in renderer.write.call_args_list)
        self.assertEqual(submitted, combined.tobytes())
        renderer.drain.assert_called_once()
        np.testing.assert_array_equal(centered[:, 2], centered[:, 3])
        self.assertFalse(np.array_equal(directional[:, 2:], combined[:, 2:]))
        for output_pcm in (directional, combined):
            np.testing.assert_array_equal(centered[:, :2], output_pcm[:, :2])
            self.assertEqual(np.abs(output_pcm).max(), REHEARSAL_PEAK)
            self.assertFalse(output_pcm[:rate//4, 2:].any())
            for start, dominant in ((.25, 2), (.5, 3)):
                first = int(start * rate)
                hit = output_pcm[first:first+int(.06*rate)]
                self.assertGreater(np.linalg.norm(hit[:, dominant]), 1.5 * np.linalg.norm(hit[:, 5-dominant]))
            np.testing.assert_array_equal(output_pcm[3*rate//4:, 2], output_pcm[3*rate//4:, 3])
            self.assertGreater(output_pcm[3*rate//4:, 2:].max(), 0)

    def test_diagnostic_stereo_selection_builds_a_bounded_four_channel_fixture(self):
        from core import Controls
        from offline import limit_rehearsal, normalize_wav, process_array
        with TemporaryDirectory() as directory:
            source = Path(directory) / 'stereo.wav'
            left = np.rint(20000 * np.sin(np.arange(75000) * .025)).astype('<i2')
            stereo = np.column_stack((left, -left))
            wavfile.write(source, 48000, stereo)
            with self.assertRaises(ValueError):
                read_fixture(source)
            fixture = read_fixture(source, stereo_controls=Controls())
            expected, _ = process_array(normalize_wav(stereo[:72000]), studio_pcm16=True,
                                        stereo_control=True, shape_control=True)
            np.testing.assert_array_equal(fixture, limit_rehearsal(expected))
            self.assertEqual(fixture.shape, (72000, 4))
            bypass = read_fixture(source, stereo_controls=Controls(bypass=True))
            self.assertFalse(bypass[:, 2:].any())

    def test_exclusive_close_requires_same_session_and_completed_discard(self):
        opened = dict(known=True, active=True, generation=8, opens=2, closes=1,
                      invalidations=0, config_revision=7, rear_link_epoch=4)
        closed = dict(opened, active=False, generation=9, closes=2, local_discard_complete=True)
        client = Mock()
        with (
            patch('studio_replay.playback_snapshot', side_effect=[dict(closed, local_discard_complete=False), closed]),
            patch('studio_replay.time.sleep'),
        ):
            confirm_exclusive_close(client, opened)
        with (
            patch('studio_replay.playback_snapshot', return_value=dict(closed, rear_link_epoch=5)),
            patch('studio_replay.time.monotonic', side_effect=[0, 0, 2]),
            patch('studio_replay.time.sleep'),
        ):
            with self.assertRaisesRegex(RuntimeError, 'could not be confirmed'):
                confirm_exclusive_close(client, opened)

    def test_diagnostic_stereo_gain_changes_rear_only(self):
        from core import Controls

        with TemporaryDirectory() as directory:
            source = Path(directory) / 'stereo.wav'
            t = np.arange(48000) / 48000
            audio = np.rint(65 * np.sin(2 * np.pi * 90 * t)).astype('<i2')
            audio[24000:24240] *= 95
            wavfile.write(source, 48000, np.column_stack((audio, -audio)))
            unity = read_fixture(source, stereo_controls=Controls())
            lower = read_fixture(source, stereo_controls=Controls(gain=.5))
            self.assertTrue(unity[24000:, 2:].any())
            np.testing.assert_array_equal(lower[:, :2], unity[:, :2])
            np.testing.assert_array_equal(lower[24000:, 2:], np.rint(unity[24000:, 2:] * .5))

    def test_rehearsal_wav_maps_pcm16_and_keeps_packed_pcm_compatible(self):
        import wave
        from studio_rehearsal_format import read_rehearsal_wav

        with TemporaryDirectory() as directory:
            direct = Path(directory) / 'pcm16.wav'
            wavfile.write(direct, 48000, np.zeros((480, 2), dtype='<i2'))
            rate, mapped = read_rehearsal_wav(direct)
            self.assertEqual(rate, 48000)
            self.assertIsInstance(mapped, np.memmap)
            del mapped

            packed = Path(directory) / 'pcm24.wav'
            with wave.open(str(packed), 'wb') as handle:
                handle.setparams((2, 3, 48000, 0, 'NONE', 'not compressed'))
                handle.writeframes(bytes.fromhex('010000ffffff'))
            rate, decoded = read_rehearsal_wav(packed)
            self.assertEqual(rate, 48000)
            np.testing.assert_array_equal(decoded, [[256, -256]])

    def test_stereo24_reads_bounded_window_without_full_decode(self):
        import wave
        from studio_rehearsal_format import read_rehearsal_wav

        with TemporaryDirectory() as directory:
            path = Path(directory) / 'packed.wav'
            with wave.open(str(path), 'wb') as handle:
                handle.setparams((2, 3, 48000, 0, 'NONE', 'not compressed'))
                handle.writeframes(bytes(6 * 12000) + bytes.fromhex('010000ffffff') * 96000)
            with patch('scipy.io.wavfile.read', wraps=wavfile.read) as reader:
                rate, pcm = read_rehearsal_wav(path, stereo_start=.25)
            reader.assert_called_once_with(path, mmap=True)
            self.assertEqual((rate, pcm.shape), (48000, (72000, 2)))
            np.testing.assert_array_equal(pcm[0], [256, -256])
            np.testing.assert_array_equal(pcm[-1], [256, -256])
