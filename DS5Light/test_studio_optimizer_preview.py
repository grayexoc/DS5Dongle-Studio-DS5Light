from dataclasses import replace
import unittest
from unittest.mock import Mock, patch

from studio_optimizer_preview import read_route_preview


class StudioOptimizerPreviewTests(unittest.TestCase):
    def setUp(self):
        self.client = Mock()
        self.profile = {'config_token': '01000000aabbccdd'}
        self.client.profile.return_value = self.profile
        self.values = dict(auto_haptics_enable=0, ah_dsp_source=0, auto_mute_replace=0, mix_native_level=0)
        self.client.read_fields.return_value = self.values, []
        self.status = dict(ready=True, auto_haptics=0, usb_mode='DualSense', usb_playback_diagnostics=True)
        self.addCleanup(patch.stopall)
        patch('studio_optimizer_preview.tagged_command').start()
        patch('studio_optimizer_preview.decode_status', return_value=self.status).start()
        self.playback = patch('studio_optimizer_preview.playback_snapshot',
                              return_value={'rear_link_epoch': 0, 'config_revision': 1}).start()

    def preview(self, live=True, endpoint=True):
        return read_route_preview(self.client, live_output=live, endpoint_verified=endpoint)

    def test_xbox_cannot_offer_a_live_route_or_a_writable_route_candidate(self):
        self.status.update(usb_mode='XInput', auto_haptics=1)
        self.values.update(auto_haptics_enable=1, ah_dsp_source=1, mix_native_level=35)
        for live in (False,True):
            result=self.preview(live=live)
            self.assertEqual(result['changes'],{})
            self.assertNotIn('live_route_verified',result)
        self.playback.assert_not_called()

    def test_live_candidate_is_a_read_only_diff(self):
        result = self.preview()
        self.assertEqual(result['revision'], '01000000aabbccdd')
        self.assertEqual(result['observed'], dict(auto_haptics_enable=0, ah_dsp_source=0, auto_mute_replace=0))
        self.assertEqual(result['changes'], dict(auto_haptics_enable=(0, 2),
                                               ah_dsp_source=(0, 1), auto_mute_replace=(0, 1)))
        self.assertEqual(set(result['field_reasons']), set(result['changes']))
        self.assertEqual([call[0] for call in self.client.method_calls], ['profile', 'read_fields', 'profile'])

    def test_native_mix_is_preserved_and_can_preview_its_front_input(self):
        self.status['auto_haptics'] = 1
        self.values.update(auto_haptics_enable=1, ah_dsp_source=1, mix_native_level=35)
        self.assertEqual(self.preview()['changes'], {})
        self.assertEqual(self.preview(live=False)['changes'], {'ah_dsp_source': (1, 0)})

    def test_missing_support_identity_and_stale_revision_abstain(self):
        self.assertEqual(self.preview(endpoint=False)['changes'], {})
        self.playback.return_value = {}
        self.assertEqual(self.preview()['changes'], {})
        self.client.profile.side_effect = [self.profile, {'config_token': 'r2'}]
        self.assertNotIn('revision', self.preview())

    def test_live_candidate_abstains_when_usb_and_profile_revisions_disagree(self):
        self.playback.return_value['config_revision'] = 2
        result = self.preview()
        self.assertFalse(result['changes'])
        self.assertNotIn('revision', result)

    def test_compatible_settings_have_no_candidate(self):
        self.status['auto_haptics'] = 2
        self.values.update(auto_haptics_enable=2, ah_dsp_source=1, auto_mute_replace=1)
        self.assertEqual(self.preview()['changes'], {})

    def test_profile_diagnostics_distinguish_desired_route_and_verified_readback(self):
        from core import Controls
        from studio_optimizer_preview import describe_haptics_profile

        desired, running = Controls(gain=1.5), Controls(gain=1.25)
        profile = describe_haptics_profile(desired, running, live_output=True, preview=self.preview())
        self.assertEqual(profile['pc']['desired_controls']['gain'], 1.5)
        self.assertEqual(profile['pc']['engine_requested_controls']['gain'], 1.25)
        self.assertEqual(profile['studio']['route_status'], 'differs_from_readback')
        self.assertEqual(profile['studio']['desired_route']['auto_haptics_enable'], 2)
        self.status['auto_haptics'] = 2
        self.values.update(auto_haptics_enable=2, ah_dsp_source=1, auto_mute_replace=1)
        for live, endpoint, status in ((True, True, 'matches_readback'), (True, False, 'unverified'),
                                       (False, True, 'observed')):
            with self.subTest(status=status):
                profile = describe_haptics_profile(desired, None, live_output=live,
                                                   preview=self.preview(live=live, endpoint=endpoint))
                self.assertEqual(profile['studio']['route_status'], status)
                self.assertEqual(profile['studio']['observed_route']['ah_dsp_source'], 1)
                self.assertEqual(profile['studio']['desired_route'] is not None, live)
        self.status['auto_haptics'] = 1
        self.values.update(auto_haptics_enable=1, mix_native_level=35)
        profile = describe_haptics_profile(desired, None, live_output=False, preview=self.preview(live=False))
        self.assertEqual(profile['studio']['desired_route'], {'ah_dsp_source': 0})
        self.assertEqual(profile['studio']['route_status'], 'differs_from_readback')

    def test_dsp_baseline_requires_complete_valid_settings(self):
        baseline = dict(auto_haptics_gain=100, auto_haptics_lowpass_hz=120,
                        auto_haptics_slope=12, auto_haptics_smooth=20, auto_haptics_gate=10,
                        ah_xover_hz=60, ah_low_gain=100, ah_high_gain=50)
        self.values.update(baseline)
        self.assertEqual(self.preview()['studio_dsp_baseline'], baseline)
        self.values['ah_xover_hz'] = 120
        preview = self.preview()
        self.assertNotIn('studio_dsp_baseline', preview)
        self.assertTrue(preview['changes'])
        self.values.pop('ah_xover_hz')
        self.client.read_fields.return_value = self.values, ['ah_xover_hz']
        self.assertNotIn('studio_dsp_baseline', self.preview())

    def test_studio_intensity_candidate_reduces_single_band_estimate(self):
        from studio_optimizer_preview import preview_studio_intensity

        preview = dict(live_route_verified=True, revision='valid', changes={},
                       observed=dict(auto_haptics_enable=2, ah_dsp_source=1, auto_mute_replace=1),
                       studio_output_gain=2.0,
                       studio_dsp_baseline=dict(ah_xover_hz=0, auto_haptics_gain=200))
        signal = dict(current=dict(rear_peak=4915), dsp_controls=dict(bypass=False))
        candidate = preview_studio_intensity(preview, signal)
        self.assertGreater(candidate['current_upper_bound'], 1.0)
        self.assertLessEqual(candidate['proposed_upper_bound'], 1.0)
        self.assertGreater(candidate['proposed'], 0)
        pc_only = preview_studio_intensity(preview, dict(
            signal, pc_gain_candidate=dict(gain=1.25, rear_peak=1500)))
        self.assertEqual(pc_only['proposed'], pc_only['observed'])
        self.assertLessEqual(pc_only['proposed_upper_bound'], 1.0)
        joint = preview_studio_intensity(preview, dict(
            signal, pc_gain_candidate=dict(gain=1.25, rear_peak=3500)))
        self.assertEqual(joint['trial_rear_peak'], 3500)
        self.assertGreater(joint['proposed'], candidate['proposed'])
        self.assertLess(joint['proposed'], joint['observed'])
        self.assertIsNone(preview_studio_intensity(dict(preview, live_route_verified=False), signal))
        self.assertIsNone(preview_studio_intensity(dict(
            preview, studio_dsp_baseline=dict(ah_xover_hz=60, auto_haptics_gain=200)), signal))
        self.assertIsNone(preview_studio_intensity(preview, dict(signal, current=dict(rear_peak=100))))

        split = dict(preview, studio_dsp_baseline=dict(
            ah_xover_hz=60, auto_haptics_gain=200, ah_low_gain=100, ah_high_gain=50))
        split_signal = dict(signal, current=dict(rear_peak=4915, rear_nonnegative=True))
        estimate = preview_studio_intensity(split, split_signal)
        self.assertEqual(estimate['basis'], 'cold_start_split_band_pre_soft_clip')
        self.assertEqual(estimate['band_factor'], 1.5)
        self.assertAlmostEqual(estimate['current_upper_bound'], 1.5 * candidate['current_upper_bound'])
        self.assertLess(estimate['proposed'], candidate['proposed'])
        self.assertLessEqual(estimate['proposed_upper_bound'], 1.0)
        self.assertIsNone(preview_studio_intensity(split, signal))
        self.assertIsNone(preview_studio_intensity(split, dict(
            split_signal, pc_gain_candidate=dict(gain=1.25, rear_peak=1000, rear_nonnegative=False))))
        split['studio_dsp_baseline'].update(ah_low_gain=0, ah_high_gain=0)
        self.assertIsNone(preview_studio_intensity(split, split_signal))

    def test_headroom_compares_same_studio_settings_without_offering_live_write(self):
        from studio_optimizer_preview import compare_studio_headroom, preview_studio_intensity

        preview = dict(live_route_verified=True, revision='valid', changes={},
                       observed=dict(auto_haptics_enable=2, ah_dsp_source=1, auto_mute_replace=1),
                       studio_output_gain=2.0, studio_dsp_baseline=dict(ah_xover_hz=0, auto_haptics_gain=200))
        signal = dict(current=dict(rear_peak=4915), live_pcm=dict(rear_peak=750),
                      pc_gain_candidate=dict(gain=1.25, rear_peak=3500, live_pcm=dict(rear_peak=500)))
        comparison = compare_studio_headroom(preview, signal)
        self.assertEqual(comparison['criterion'], 1.0)
        self.assertGreater(comparison['rehearsal']['current_upper_bound'], 1.0)
        self.assertLess(comparison['simulated_live']['current_upper_bound'], 1.0)
        self.assertAlmostEqual(comparison['simulated_live']['trial_upper_bound'], 500 * 18 / 32768)
        self.assertNotIn('proposed', comparison['simulated_live'])
        candidate = preview_studio_intensity(preview, signal)
        self.assertEqual(candidate['trial_rear_peak'], 3500)
        self.assertLess(candidate['proposed'], candidate['observed'])
        self.assertIsNone(compare_studio_headroom(dict(preview, revision=None), signal))
        self.assertIsNone(compare_studio_headroom(preview, dict(signal, live_pcm=None)))
        below_limit = dict(signal, current=dict(rear_peak=1200), pc_gain_candidate=None)
        self.assertIsNone(preview_studio_intensity(preview, below_limit))
        self.assertLess(compare_studio_headroom(preview, below_limit)['rehearsal']['current_upper_bound'], 1.0)

    def test_wav_analysis_compares_dsp_and_bypass_without_audio_device(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        import numpy as np
        from scipy.io import wavfile
        from core import Controls
        from studio_optimizer_preview import analyze_rehearsal_signal

        t = np.arange(48000) / 48000
        signal = np.rint(65 * np.sin(2 * np.pi * 90 * t)).astype('<i2')
        signal[24000:24240] *= 95
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'fixture.wav'
            wavfile.write(path, 48000, np.column_stack((signal, -signal)))
            report = analyze_rehearsal_signal(path, Controls(gain=.75))
            self.assertEqual(report['frames'], len(signal))
            self.assertEqual(report['source']['frames'], len(signal))
            self.assertEqual(report['source']['peak_lr'], [np.max(np.abs(signal)) / 32768] * 2)
            rms = np.sqrt(np.mean(np.square(signal.astype(float) / 32768)))
            np.testing.assert_allclose(report['source']['rms_lr'], [rms, rms])
            self.assertEqual(report['dsp_controls']['gain'], .75)
            self.assertGreater(report['current']['rear_frames'], 0)
            self.assertGreater(report['current']['rear_peak'], 0)
            self.assertGreater(report['live_pcm']['rear_peak'], 0)
            self.assertLess(report['live_pcm']['rear_peak'], report['current']['rear_peak'])
            self.assertEqual(report['bypass']['rear_peak'], 0)
            self.assertEqual(report['bypass']['rear_frames'], 0)
            self.assertEqual(report['bypass']['rear_rms_lr'], [0, 0])
            self.assertEqual(report['bypass']['rear_ceiling_frames'], 0)
            self.assertIsNone(report['pc_gain_candidate'])

    def test_pc_gain_candidate_requires_measured_improvement(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        import numpy as np
        from scipy.io import wavfile
        from core import Controls
        from studio_optimizer_preview import analyze_rehearsal_signal
        from studio_rehearsal_format import REHEARSAL_PEAK

        source = np.zeros((2, 2), dtype='<i2')
        current = np.array([[10, -10, REHEARSAL_PEAK, 5], [2, 3, 60, 10]], dtype='<i2')
        bypass = current.copy()
        bypass[:, 2:] = 0
        improved = current.copy()
        improved[0, 2] -= 1
        drops_right = improved.copy()
        drops_right[:, 3] = 0
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'fixture.wav'
            wavfile.write(path, 48000, source)
            for trial, expected in ((improved, True), (current, False), (bypass, False), (drops_right, False)):
                with (self.subTest(expected=expected),
                      patch('studio_replay.prepare_stereo_fixture', side_effect=[current, bypass, trial]) as render,
                      patch('studio_optimizer_preview._measure_live_pcm', return_value={})):
                    result = analyze_rehearsal_signal(path, Controls(gain=1.5))
                    self.assertEqual(render.call_args.args[-1].gain, 1.0)
                    self.assertEqual(bool(result['pc_gain_candidate']), expected)
                    if expected:
                        self.assertEqual(result['pc_gain_candidate']['rear_ceiling_frames'], 0)

    def test_pc_gain_candidate_uses_encoded_wav_comparison(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        import numpy as np
        from scipy.io import wavfile
        from core import Controls
        from studio_optimizer_preview import (
            analyze_rehearsal_signal, analyze_rehearsal_windows, applied_pc_gain_signal, preview_studio_intensity,
            _load_rehearsal_window,
        )

        frames = np.arange(24000)
        tone = 3500 * np.sin(2 * np.pi * 90 * frames / 48000)
        burst = (tone * (frames % 4800 < 960)).astype('<i2')
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'fixture.wav'
            burst = np.concatenate((np.zeros(72000, dtype='<i2'), burst))
            wavfile.write(path, 48000, np.column_stack((burst, -burst)))
            controls = Controls(gain=2.0)
            initial = analyze_rehearsal_signal(path, controls)
            self.assertEqual(initial['source']['frames'], 72000)
            self.assertIsNone(initial['pc_gain_candidate'])
            report = analyze_rehearsal_signal(path, controls, start=1.5)
            with patch('studio_optimizer_preview._load_rehearsal_window', wraps=_load_rehearsal_window) as load:
                combined = analyze_rehearsal_windows(path, controls, (0, 1.5))
                self.assertEqual(load.call_count, 2)
            self.assertEqual(combined['frames'], len(burst))
            shared = combined['pc_gain_candidate']
            self.assertEqual(shared['gain'], report['pc_gain_candidate']['gain'])
            self.assertEqual(shared['rear_ceiling_frames'], 0)
            self.assertEqual(shared['rear_peak'], max(trial['rear_peak'] for trial in shared['windows']))
            self.assertTrue(shared['rear_nonnegative'])
            self.assertTrue(combined['current']['rear_nonnegative'])
            self.assertEqual(shared['windows'][0]['rear_frames'], 0)
            preview = dict(live_route_verified=True, revision='fixture', changes={},
                           observed=dict(auto_haptics_enable=2, ah_dsp_source=1, auto_mute_replace=1),
                           studio_output_gain=2.0,
                           studio_dsp_baseline=dict(ah_xover_hz=30, auto_haptics_gain=200,
                                                    ah_low_gain=100, ah_high_gain=50))
            joint = preview_studio_intensity(preview, combined)
            self.assertEqual(joint['pc_gain'], shared['gain'])
            self.assertEqual(joint['trial_rear_peak'], shared['rear_peak'])
            self.assertEqual(joint['basis'], 'cold_start_split_band_pre_soft_clip')
            self.assertLess(joint['proposed'], joint['observed'])
            self.assertLessEqual(joint['proposed_upper_bound'], 1.0)
            applied = replace(controls, gain=shared['gain'])
            accepted = applied_pc_gain_signal(combined, controls, applied)
            self.assertIsNone(accepted['pc_gain_candidate'])
            self.assertEqual(accepted['current']['rear_peak'], shared['rear_peak'])
            self.assertEqual([window['current'] for window in accepted['windows']], shared['windows'])
            self.assertEqual(accepted['live_pcm'], shared['live_pcm'])
            self.assertEqual([window['live_pcm'] for window in accepted['windows']], shared['live_pcm_windows'])
            self.assertEqual(preview_studio_intensity(preview, accepted)['proposed'], joint['proposed'])
            self.assertIsNone(applied_pc_gain_signal(combined, controls, replace(applied, impact=.1)))
            with self.assertRaises(ValueError):
                analyze_rehearsal_windows(path, controls, (0, 0))
            with self.assertRaises(ValueError):
                analyze_rehearsal_signal(path, controls, start=2.0)
        self.assertEqual(report['source']['first_frame'], 72000)
        self.assertEqual(report['source']['frames'], 24000)
        current = report['current']
        candidate = report['pc_gain_candidate']
        self.assertGreater(current['rear_ceiling_frames'], 0)
        self.assertGreater(candidate['gain'], 1.0)
        self.assertLess(candidate['gain'], 2.0)
        self.assertEqual(candidate['rear_ceiling_frames'], 0)
        self.assertEqual(candidate['front_peak'], current['front_peak'])
        self.assertTrue(all(rms > 0 for rms in candidate['rear_rms_lr']))

    def test_shared_gain_records_measurements_when_a_window_fails(self):
        from pathlib import Path
        from core import Controls
        from studio_optimizer_preview import analyze_rehearsal_windows

        def measurement(ceiling_frames, rms=(1.0, 1.0)):
            return dict(rear_peak=4900, rear_ceiling_frames=ceiling_frames, rear_rms_lr=rms)

        def window(first, ceiling, candidate):
            return dict(frames=240, sample_rate=48000, rear_ceiling=4915, dsp_controls={},
                        source=dict(first_frame=first), current=measurement(ceiling),
                        bypass=measurement(0), live_pcm=measurement(0), pc_gain_candidate=candidate)

        first = window(0, 3, dict(gain=1.25))
        second = window(48000, 0, None)
        for trial in (measurement(1), measurement(0, (1.0, 0.0))):
            with (self.subTest(trial=trial),
                  patch('studio_optimizer_preview._load_rehearsal_window', return_value=(48000, None)),
                  patch('studio_optimizer_preview._analyze_rehearsal_window', side_effect=[first, second]),
                  patch('studio_replay.prepare_stereo_fixture'),
                  patch('studio_optimizer_preview._measure_rehearsal_output', side_effect=[measurement(0), trial])):
                report = analyze_rehearsal_windows(Path('fixture.wav'), Controls(gain=2.0), (0, 1))
                self.assertIsNone(report['pc_gain_candidate'])
                rejected = report['rejected_pc_gain_trial']
                self.assertEqual(rejected['failing_first_frames'], [48000])
                self.assertEqual(rejected['windows'][1], trial)

    def test_intensity_apply_and_restore_verify_idle_route_and_new_token(self):
        from dataclasses import asdict
        from core import Controls
        from studio_optimizer_preview import apply_intensity_preview, rollback_intensity_apply

        controls = Controls(gain=1.5)
        route = dict(auto_haptics_enable=2, ah_dsp_source=1, auto_mute_replace=1)
        preview = dict(live_route_verified=True, revision=self.profile['config_token'], changes={},
                       observed=route, studio_output_gain=2.0,
                       studio_dsp_baseline=dict(ah_xover_hz=0, auto_haptics_gain=200))
        signal = dict(current=dict(rear_peak=4915), dsp_controls=asdict(controls))
        self.playback.return_value.update(conditional_intensity_apply=True, known=True,
                                          active=False, local_discard_complete=True)
        self.client.read_fields.return_value = dict(route, auto_haptics_gain=200), []
        with self.assertRaisesRegex(ValueError, 'Reanalyze'):
            apply_intensity_preview(self.client, preview, dict(signal, pc_gain_candidate={'gain': 1.25}), controls)
        next_token = '0200000011223344'

        def write(op, token, observed, target):
            self.client.read_fields.return_value = dict(route, auto_haptics_gain=target), []
            result = next_token if op == 1 else '03000000aabbccdd'
            self.client.profile.return_value = {'config_token': result}
            return result

        self.client.conditional_studio_intensity_write.side_effect = write
        receipt = apply_intensity_preview(self.client, preview, signal, controls)
        self.assertEqual(receipt['revision'], next_token)
        self.assertLess(receipt['applied'], receipt['before'])
        with self.assertRaises(ValueError):
            rollback_intensity_apply(self.client, receipt)
        self.client.conditional_studio_intensity_write.assert_called_once()
        self.playback.return_value['config_revision'] = 2
        self.assertEqual(rollback_intensity_apply(self.client, receipt), '03000000aabbccdd')
        self.client.conditional_studio_intensity_write.assert_called_with(2, next_token, receipt['applied'], 200)

    def test_apply_and_rollback_use_owned_revision_and_verify_readback(self):
        from studio_optimizer_preview import apply_route_preview, rollback_route_apply

        self.playback.return_value['conditional_route_apply'] = True
        preview = self.preview()
        after = '0200000011223344'
        restored = '03000000aabbccdd'
        target = dict(auto_haptics_enable=2, ah_dsp_source=1, auto_mute_replace=1)
        self.client.conditional_studio_route_write.side_effect = [after, restored]
        self.client.profile.return_value = {'config_token': after}
        self.client.read_fields.return_value = target, []
        receipt = apply_route_preview(self.client, preview)
        self.client.conditional_studio_route_write.assert_called_once_with(
            1, preview['revision'], (0, 0, 0), (2, 1, 1))
        self.playback.return_value['config_revision'] = 3
        with self.assertRaises(ValueError):
            rollback_route_apply(self.client, receipt)
        self.assertEqual(self.client.conditional_studio_route_write.call_count, 1)
        self.playback.return_value['config_revision'] = 2
        self.client.profile.return_value = {'config_token': restored}
        self.client.read_fields.return_value = preview['observed'], []
        self.assertEqual(rollback_route_apply(self.client, receipt), restored)
        self.client.conditional_studio_route_write.assert_called_with(2, after, (2, 1, 1), (0, 0, 0))

    def test_uncertain_readback_never_writes_again(self):
        from studio_optimizer_preview import apply_route_preview
        from studio_settings_protocol import PartialApplyError

        self.playback.return_value['conditional_route_apply'] = True
        preview = self.preview()
        self.client.conditional_studio_route_write.return_value = '0200000011223344'
        with self.assertRaises(PartialApplyError):
            apply_route_preview(self.client, preview)
        self.client.conditional_studio_route_write.assert_called_once()
