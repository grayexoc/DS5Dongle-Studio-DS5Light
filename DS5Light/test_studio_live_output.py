import time
import unittest
from contextlib import contextmanager, nullcontext
from queue import Queue
from threading import Event
from unittest.mock import Mock, patch

import numpy as np

from core import BLOCK, RATE, Controls
from studio_rehearsal_format import REHEARSAL_PEAK
from studio_live_output import StudioLiveOutput
from studio_settings_protocol import PartialApplyError


class StudioLiveOutputTests(unittest.TestCase):
    def setUp(self):
        route = patch('studio_live_output.read_route_preview', return_value=dict(
            live_route_verified=True, changes={}, reason='Route already correct',
            observed={'auto_haptics_enable': 2, 'ah_dsp_source': 1, 'auto_mute_replace': 0}))
        self.preview = route.start()
        self.addCleanup(route.stop)

    def test_restore_after_renderer_start_failure_or_stop(self):
        for error in (None, OSError('exclusive open failed')):
            with self.subTest(error=error):
                self.preview.return_value['changes'] = {'auto_mute_replace': (0, 1)}
                receipt = object()
                session = StudioLiveOutput.__new__(StudioLiveOutput)
                session._opened = None
                client, cleanup = Mock(), Mock()
                with (
                    patch('studio_live_output.apply_route_preview', return_value=receipt) as apply,
                    patch('studio_live_output.rollback_route_apply') as restore,
                ):
                    try:
                        with session._managed_route(client, cleanup):
                            restore.assert_not_called()
                            if error:
                                raise error
                    except OSError as exc:
                        self.assertIs(exc, error)
                    apply.assert_called_once_with(cleanup, self.preview.return_value)
                    restore.assert_called_once_with(cleanup, receipt)
                    self.assertEqual(session.restore_status, 'Studio 경로 복구 확인')

    def test_recovery_requires_the_acknowledged_revision(self):
        for token in (None, 'acknowledged-token'):
            with self.subTest(token=token):
                session = StudioLiveOutput.__new__(StudioLiveOutput)
                session._opened = None
                preview = self.preview.return_value
                preview['changes'] = {'auto_mute_replace': (0, 1)}
                error = PartialApplyError('readback failed')
                if token:
                    error.route_revision = token
                cleanup = Mock()
                with (
                    patch('studio_live_output.apply_route_preview', side_effect=error),
                    patch('studio_live_output.rollback_route_apply', side_effect=OSError('disconnected')) as restore,
                    self.assertRaises(PartialApplyError),
                ):
                    with session._managed_route(Mock(), cleanup):
                        self.fail('The renderer cannot open after an unverified apply.')
                if token:
                    restore.assert_called_once_with(cleanup, dict(
                        revision=token, before=preview['observed'],
                        applied=dict(preview['observed'],auto_mute_replace=1)))
                else:
                    restore.assert_not_called()
                self.assertEqual(session.restore_status, 'Studio 경로 복구 미확인')

    def test_route_changed_before_worker_does_not_write_or_open_renderer(self):
        self.preview.return_value['observed']['ah_dsp_source'] = 0
        session = StudioLiveOutput.__new__(StudioLiveOutput)
        with patch('studio_live_output.apply_route_preview') as apply:
            with self.assertRaisesRegex(RuntimeError, '출력 경로가 변경'):
                with session._managed_route(Mock(), Mock()):
                    self.fail('Stale profile cannot open exclusive output')
            apply.assert_not_called()

    def test_worker_sends_bounded_blocks_and_stops_on_failure(self):
        binding = Mock()
        renderer = Mock()
        sent = Event()
        renderer.write.side_effect = lambda _: sent.set()
        binding.snapshot.return_value = object()
        lease = nullcontext((renderer, {'generation': 3}, 12, time.monotonic() + 10))
        with (
            patch('studio_live_output.with_selected_device', side_effect=lambda _, i, operation, cancel: operation(Mock())),
            patch('studio_live_output.prepare_exclusive_renderer', return_value=nullcontext(Mock())) as prepare,
            patch('studio_live_output.leased_studio_renderer', return_value=lease),
        ):
            output = StudioLiveOutput(binding, binding.snapshot(), 'studio', Event())
            output.wait_ready()
            try:
                data = np.tile(np.array([32767, -32768, 20000, 20000], dtype='<i2'), (BLOCK * 2, 1))
                output.write(data.tobytes(), Controls(bypass=True))
                self.assertTrue(sent.wait(1))
                pcm = np.frombuffer(renderer.write.call_args.args[0], '<i2').reshape(-1, 4)
                self.assertEqual(len(pcm), BLOCK * 2)
                np.testing.assert_array_equal(pcm[0], [4915, -4915, 0, 0])
                self.assertEqual(output.stats()['queued_frames'], BLOCK * 2)
                self.assertFalse(output.stats()['adaptive_gain'])
                self.assertIsNone(output.stats()['queue_to_render_ms'])
                self.assertIsNone(output.stats()['write_ms'])
                prepare.assert_called_once_with('studio', live=True, cancel=output._stop.is_set)
                renderer.write.side_effect = OSError('stopped')
                output.write(data.tobytes(), Controls(), measure=True)
                output._thread.join(1)
                self.assertEqual(output.stats()['submitted_frames'], BLOCK * 2)
                self.assertEqual(output.stats()['queued_frames'], BLOCK * 4)
                self.assertGreaterEqual(output.stats()['queue_to_render_ms'][0], 0.)
                with self.assertRaisesRegex(RuntimeError, 'stopped'):
                    output.check()
            finally:
                output.close()

    def test_opted_in_worker_processes_rear_gain_without_changing_stereo(self):
        binding = Mock()
        binding.snapshot.return_value = object()
        renderer = Mock()
        sent = Event()
        renderer.write.side_effect = lambda _: sent.set()
        lease = nullcontext((renderer, {}, 12, time.monotonic() + 10))
        with (
            patch('studio_live_output.with_selected_device', side_effect=lambda _, i, op, cancel: op(Mock())),
            patch('studio_live_output.prepare_exclusive_renderer', return_value=nullcontext(Mock())),
            patch('studio_live_output.leased_studio_renderer', return_value=lease),
        ):
            output = StudioLiveOutput(binding, binding.snapshot(), 'studio', Event(), adaptive_gain=True)
            try:
                output.wait_ready()
                data = np.tile(np.array([32767, -32768, 0, 0], dtype='<i2'), (BLOCK, 1))
                output.write(data.tobytes(), Controls(gain=1.5), measure=True)
                self.assertTrue(sent.wait(1))
                pcm = np.frombuffer(renderer.write.call_args.args[0], '<i2').reshape(-1, 4)
                np.testing.assert_array_equal(pcm[0, :2], [4915, -4915])
                self.assertTrue(output.stats()['adaptive_gain'])
                self.assertEqual(output.stats()['adaptive_gain_target_percent'], 150)
            finally:
                output.close()
            stats = output.stats()
            self.assertGreaterEqual(stats['queue_to_render_ms'][0], 0.)
            self.assertGreaterEqual(stats['write_ms'][0], 0.)

    def test_live_worker_shapes_impacts_and_steers_only_for_stereo_capture(self):
        batch_frames = 1920
        controls = Controls(gain=1.25)
        starts = (2 * batch_frames, 5 * batch_frames)
        data = np.zeros((8 * batch_frames, 4), dtype='<i2')
        elapsed = np.arange(8 * BLOCK) / RATE
        burst = np.rint(.26 * 32768 * np.sin(2*np.pi*400*elapsed)
                        * np.exp(-elapsed/.018)).astype('<i2')
        for channel, start in enumerate(starts):
            data[start:start+len(burst), channel] = burst

        for stereo_capture in (False, True):
            with self.subTest(stereo_capture=stereo_capture):
                binding = Mock()
                renderer = Mock()
                submissions = Queue()
                renderer.write.side_effect = submissions.put
                lease = nullcontext((renderer, {}, 12, time.monotonic() + 10))
                with (
                    patch('studio_live_output.with_selected_device', side_effect=lambda _, i, op, cancel: op(Mock())),
                    patch('studio_live_output.prepare_exclusive_renderer', return_value=nullcontext(Mock())),
                    patch('studio_live_output.leased_studio_renderer', return_value=lease),
                ):
                    output = StudioLiveOutput(binding, binding.snapshot(), 'studio', Event())
                    try:
                        output.wait_ready()
                        rendered = []
                        for batch in np.split(data, 8):
                            output.write(batch.tobytes(), controls, stereo_capture=stereo_capture)
                            rendered.append(submissions.get(timeout=1))
                    finally:
                        output.close()

                pcm = np.frombuffer(b''.join(rendered), '<i2').reshape(-1, 4)
                if stereo_capture:
                    from studio_replay import prepare_stereo_fixture

                    preview = prepare_stereo_fixture(data[:, :2], RATE, controls, live_pcm_scale=True)
                    np.testing.assert_array_equal(pcm, preview)
                np.testing.assert_array_equal(
                    pcm[:, :2], np.rint(data[:, :2].astype(float) * (REHEARSAL_PEAK / 32768)).astype('<i2'))
                self.assertLessEqual(pcm[:, 2:].max(), REHEARSAL_PEAK)
                self.assertFalse(pcm[:starts[0], 2:].any())
                for channel, start in enumerate(starts):
                    hit = pcm[start:start+BLOCK, 2:]
                    primary = hit[:, channel]
                    self.assertGreater(primary[-1], 0)
                    self.assertAlmostEqual(primary[BLOCK//2-1] / primary[-1], .875, delta=.01)
                    if stereo_capture:
                        self.assertGreater(np.linalg.norm(primary), 1.5 * np.linalg.norm(hit[:, 1-channel]))
                    else:
                        np.testing.assert_array_equal(hit[:, 0], hit[:, 1])

    def test_worker_lowers_and_restores_gain_across_contiguous_render_windows(self):
        binding = Mock()
        binding.snapshot.return_value = object()
        submissions = Queue()
        renderer = Mock()
        renderer.write.side_effect = lambda data: submissions.put(bytes(data))
        lease = nullcontext((renderer, {}, 12, time.monotonic() + 20))
        controls = Controls(gain=1.5)
        batch_frames = 1920

        with (
            patch('studio_live_output.with_selected_device', side_effect=lambda _, i, op, cancel: op(Mock())),
            patch('studio_live_output.prepare_exclusive_renderer', return_value=nullcontext(Mock())),
            patch('studio_live_output.leased_studio_renderer', return_value=lease),
        ):
            output = StudioLiveOutput(binding, binding.snapshot(), 'studio', Event(), adaptive_gain=True)
            try:
                output.wait_ready()
                frames = np.arange(75 * batch_frames)
                tone = np.rint(0.7 * 32768 * np.sin(2 * np.pi * 45 * frames / 48000)
                               * (frames % 4800 < 1200)).astype('<i2')
                loud = np.zeros((len(frames), 4), dtype='<i2')
                loud[:, 0], loud[:, 1] = tone, -tone
                quiet = np.zeros((batch_frames, 4), dtype='<i2')

                def submit(block):
                    output.write(block.tobytes(), controls)
                    data = submissions.get(timeout=1)
                    self.assertEqual(len(data), block.nbytes)
                    return np.frombuffer(data, '<i2').reshape(-1, 4)

                for start in range(0, len(loud), batch_frames):
                    block = loud[start:start + batch_frames]
                    pcm = submit(block)
                    np.testing.assert_array_equal(
                        pcm[:, :2], np.rint(block[:, :2].astype(float) * (4915 / 32768)).astype('<i2'))
                    self.assertLessEqual(int(pcm[:, 2:].max()), 4915)
                self.assertEqual(output.stats()['adaptive_gain_target_percent'], 145)
                for _ in range(200):
                    silent = submit(quiet)
                self.assertEqual(output.stats()['adaptive_gain_target_percent'], 150)
                self.assertFalse(silent.any())
            finally:
                output.close()

    def test_slow_renewal_does_not_block_audio_and_refusal_closes_output(self):
        binding = Mock()
        binding.snapshot.return_value = object()
        renderer = Mock()
        client = Mock()
        renewing, reply, sent = Event(), Event(), Event()

        def reject(*args, **kwargs):
            renewing.set()
            if not reply.wait(1):
                raise AssertionError('audio did not progress while renewal was waiting')
            raise RuntimeError('renewal refused')

        client.rear_lease_exchange.side_effect = reject
        renderer.write.side_effect = lambda _: sent.set()
        def lease(*args):
            return nullcontext((renderer, {'generation': 3}, 12, time.monotonic() + .45))
        with (
            patch('studio_live_output.with_selected_device', side_effect=lambda _, i, operation, cancel: operation(Mock())),
            patch('studio_live_output.SettingsClient', return_value=client),
            patch('studio_live_output.prepare_exclusive_renderer', return_value=nullcontext(Mock())),
            patch('studio_live_output.leased_studio_renderer', side_effect=lease),
        ):
            output = StudioLiveOutput(binding, binding.snapshot(), 'studio', Event())
            output.wait_ready()
            try:
                self.assertTrue(renewing.wait(1))
                output.write(bytes(BLOCK * 8), Controls(bypass=True))
                self.assertTrue(sent.wait(1))
                reply.set()
                output._thread.join(1)
                with self.assertRaisesRegex(RuntimeError, 'renewal refused'):
                    output.write(bytes(BLOCK * 8), Controls())
                renderer.write.assert_called_once()
            finally:
                reply.set()
                output.close()

    def test_stop_cancels_a_worker_still_preparing_its_renderer(self):
        binding = Mock()
        binding.snapshot.return_value = object()
        parent_stop, entered, stopped = Event(), Event(), Event()

        @contextmanager
        def prepare(endpoint, *, live, cancel):
            entered.set()
            try:
                while not cancel():
                    stopped.wait(.01)
                raise RuntimeError('cancelled')
                yield
            finally:
                stopped.set()

        with (
            patch('studio_live_output.with_selected_device', side_effect=lambda _, i, operation, cancel: operation(Mock())),
            patch('studio_live_output.prepare_exclusive_renderer', side_effect=prepare),
        ):
            output = StudioLiveOutput(binding, binding.snapshot(), 'studio', parent_stop)
            try:
                self.assertTrue(entered.wait(2))
                parent_stop.set()
                output.request_stop()
                with self.assertRaises(KeyboardInterrupt):
                    output.wait_ready()
                self.assertTrue(stopped.is_set())
                self.assertTrue(output.is_closed())
            finally:
                output.close()

    def test_worker_uses_identity_pinned_before_start(self):
        original, replacement = object(), object()
        binding = Mock()
        binding.snapshot.return_value = replacement
        def lock_device(bound, identity, operation, cancel):
            self.assertIs(bound, binding)
            self.assertIs(identity, original)
            raise RuntimeError('binding changed')
        with patch('studio_live_output.with_selected_device', side_effect=lock_device):
            output = StudioLiveOutput(binding, original, 'studio', Event())
            try:
                with self.assertRaisesRegex(RuntimeError, 'binding changed'):
                    output.wait_ready()
            finally:
                output.close()

    def test_full_queue_fails_instead_of_waiting_for_renderer(self):
        output = StudioLiveOutput.__new__(StudioLiveOutput)
        output._stop = Event()
        output._thread = Mock()
        output._error = None
        output.queued_frames = 0
        output._queue = Queue(maxsize=1)
        output.write(b'one', Controls())
        with self.assertRaisesRegex(RuntimeError, 'queue filled'):
            output.write(b'two', Controls())
        self.assertTrue(output._stop.is_set())
        self.assertEqual(output._queue.get_nowait()[0], b'one')
