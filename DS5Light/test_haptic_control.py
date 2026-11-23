import unittest

import numpy as np

from core import BLOCK, RATE, Controls
from haptic_control import HapticMapper, encode_studio_pcm, fuse
from offline import process_array


class HapticControlTests(unittest.TestCase):
    def test_studio_pcm_encoder_preserves_channel_order_and_saturates(self):
        pcm = encode_studio_pcm(np.array([[-1, 1], [.5, -.25]]),
                                np.array([[.25, .5], [0, 1]]))
        self.assertEqual(pcm.dtype, np.dtype('<i2'))
        np.testing.assert_array_equal(pcm, [[-32768, 32767, 8192, 16384],
                                            [16384, -8192, 0, 32767]])

    def test_studio_pcm_encoder_rejects_invalid_rear_blocks(self):
        front = np.zeros((2, 2), dtype=np.float32)
        for rear in (np.zeros((2, 1)), np.zeros((1, 2)),
                     np.array([[0, -1], [0, 0]]), np.full((2, 2), np.nan)):
            with self.subTest(rear=rear), self.assertRaises(ValueError):
                encode_studio_pcm(front, rear)

    def test_fusion_requires_protection_and_allocates_only_remaining_headroom(self):
        self.assertEqual(fuse(0, 1), 0)
        self.assertEqual(fuse(.75, 0), .75)
        self.assertEqual(fuse(.75, .5), .875)
        self.assertEqual(fuse(4, 4), 1)
        with self.assertRaises(ValueError):
            fuse(float('nan'), 0)

    def test_centered_mapper_ramps_and_fresh_instance_starts_at_zero(self):
        mapper = HapticMapper()
        up = mapper.process(1., 4)
        down = mapper.process(0., 4)
        np.testing.assert_array_equal(up[:, 0], [.25, .5, .75, 1.])
        np.testing.assert_array_equal(down[:, 1], [.75, .5, .25, 0.])
        np.testing.assert_array_equal(HapticMapper().process(1., 4), up)

    def test_mapper_matches_reference_ramps_across_shaped_and_variable_blocks(self):
        for scalar in (float, np.float32):
            mapper = HapticMapper()
            start = (0., 0.)
            first = None
            for target, balance, frames, attack in (
                (.8, .65, BLOCK, 'sharp'),
                (.75, -.65, BLOCK, 'weight'),
                (.75, -.65, BLOCK, None),
                (.5, 0., BLOCK - 17, 'sharp'),
                (.2, .4, 0, None),
                (1., -.4, 1, 'weight'),
                (0., 0., BLOCK, 'weight'),
            ):
                with self.subTest(scalar=scalar, frames=frames, attack=attack):
                    target, balance = scalar(target), scalar(balance)
                    levels = (target * (1 - max(0, balance)), target * (1 - max(0, -balance)))
                    expected = np.linspace(start, levels, frames + 1, dtype=np.float32)[1:]
                    if attack is not None:
                        begin = np.asarray(start)
                        delta = np.asarray(levels) - begin
                        rising = delta > 0
                        progress = np.linspace(0, 1, frames + 1)[1:, None]
                        eased = progress ** 2 if attack == 'weight' else 1 - (1 - progress) ** 3
                        expected[:, rising] = begin[rising] + eased * delta[rising]
                    actual = mapper.process(target, frames, balance, attack=attack)
                    np.testing.assert_array_equal(actual.view(np.uint32), expected.view(np.uint32))
                    if first is None:
                        first = actual, expected
                    else:
                        np.testing.assert_array_equal(*first)
                    start = levels

    def test_stereo_control_follows_clear_hit_and_keeps_balanced_or_bypass_centered(self):
        clock = np.arange(RATE) / RATE
        background = .002 * np.sin(2 * np.pi * 90 * clock)
        elapsed = clock - .5
        hit = .20 * np.sin(2 * np.pi * 90 * elapsed) * np.exp(-np.maximum(elapsed, 0) / .03)
        hit[(elapsed < 0) | (elapsed > .08)] = 0
        for left, right in ((1, 0), (0, 1), (1, 1), (1, -.9)):
            with self.subTest(left=left, right=right):
                x = np.column_stack((background + hit * left, background + hit * right))
                normal, _ = process_array(x, studio_pcm16=True)
                stereo, _ = process_array(x, studio_pcm16=True, stereo_control=True)
                np.testing.assert_array_equal(normal[:, :2], stereo[:, :2])
                np.testing.assert_array_equal(normal[:RATE//2], stereo[:RATE//2])
                self.assertLessEqual(stereo[:, 2:].max(), normal[:, 2:].max())
                if not left or not right:
                    side = 2 if left else 3
                    self.assertGreater(np.linalg.norm(stereo[:, side]),
                                       np.linalg.norm(stereo[:, 5-side]) * 1.3)
                else:
                    np.testing.assert_array_equal(stereo[:, 2], stereo[:, 3])
                bypass, _ = process_array(x, controls=Controls(bypass=True), studio_pcm16=True, stereo_control=True)
                self.assertFalse(bypass[:, 2:].any())

    def test_stereo_control_uses_centered_fallback_for_non_stereo_sources(self):
        for channels in (1, 6, 8):
            with self.subTest(channels=channels):
                frames, baseline = [], []
                audio = np.zeros((4 * BLOCK, channels), dtype=np.float32)
                process_array(audio, control_frames=frames, stereo_control=True)
                process_array(audio, control_frames=baseline)
                self.assertEqual(frames, baseline)

    def test_stereo_control_uses_hit_instead_of_opposite_background(self):
        clock = np.arange(RATE) / RATE
        elapsed = clock - .5
        hit = .23 * np.sin(2 * np.pi * 86 * elapsed) * np.exp(-np.maximum(0, elapsed) / .025)
        hit[(elapsed < 0) | (elapsed > .08)] = 0
        bed = .032 * np.sin(2 * np.pi * 57 * clock)
        audio = np.column_stack((hit, bed))
        left, _ = process_array(audio, studio_pcm16=True, stereo_control=True)
        right, _ = process_array(audio[:, ::-1], studio_pcm16=True, stereo_control=True)
        np.testing.assert_array_equal(left[:, 2], right[:, 3])
        np.testing.assert_array_equal(left[:, 3], right[:, 2])
        self.assertGreater(np.linalg.norm(left[:, 2]), np.linalg.norm(left[:, 3]) * 2)

    def test_shaped_control_distinguishes_low_and_mid_hits_without_raising_peak(self):
        elapsed = np.arange(RATE) / RATE - .5
        for hz, offset, expected_progress in ((45, 1, .25), (400, 0, .875)):
            with self.subTest(hz=hz):
                pulse = .26 * np.sin(2 * np.pi * hz * elapsed) * np.exp(-np.maximum(0, elapsed) / .018)
                pulse[(elapsed < 0) | (elapsed > .045)] = 0
                stereo = np.column_stack((pulse, pulse))
                base, _ = process_array(stereo, studio_pcm16=True)
                shaped, _ = process_array(stereo, studio_pcm16=True, shape_control=True)
                np.testing.assert_array_equal(base[:, :2], shaped[:, :2])
                np.testing.assert_array_equal(base[:RATE//2], shaped[:RATE//2])
                first = RATE//2 + offset * BLOCK
                start, middle, end = map(int, shaped[[first-1, first+BLOCK//2-1, first+BLOCK-1], 2])
                self.assertGreater(end, start)
                self.assertAlmostEqual((middle-start)/(end-start), expected_progress, places=2)
                np.testing.assert_array_equal(base[BLOCK-1::BLOCK, 2:], shaped[BLOCK-1::BLOCK, 2:])
                self.assertEqual(base[:, 2:].max(), shaped[:, 2:].max())

    def test_live_background_slider_changes_rear_without_impact_boost(self):
        t = np.arange(RATE) / RATE
        x = np.repeat((.2 * np.sin(2 * np.pi * 80 * t))[:, None], 2, axis=1)
        peaks = []
        for strength in (.30, .55, .80):
            pcm, _ = process_array(x, controls=Controls(strength=strength, impact=0),
                                   studio_pcm16=True, live_pcm_scale=True)
            peaks.append(pcm[RATE//2:, 2:].max())
        self.assertGreater(peaks[0], peaks[1])
        self.assertGreater(peaks[1], peaks[2])
        self.assertGreater(peaks[2], 0)

    def test_live_sustained_direction_requires_stereo_and_preserves_center(self):
        t = np.arange(RATE) / RATE
        tone = .08 * np.sin(2 * np.pi * 80 * t)
        left = np.column_stack((tone, np.zeros_like(tone)))
        options = dict(studio_pcm16=True, live_pcm_scale=True)
        directed, _ = process_array(left, stereo_control=True, **options)
        downmix, _ = process_array(left, stereo_control=False, **options)
        center, _ = process_array(np.column_stack((tone, tone)), stereo_control=True, **options)
        steady = slice(RATE // 2, RATE)
        np.testing.assert_allclose(directed[steady, 3] / directed[steady, 2], .70, atol=.003)
        np.testing.assert_array_equal(directed[steady, 2], downmix[steady, 2])
        np.testing.assert_array_equal(downmix[:, 2], downmix[:, 3])
        np.testing.assert_array_equal(center[:, 2], center[:, 3])

    def test_live_sustained_direction_does_not_follow_periodic_waveform_peaks(self):
        t = np.arange(RATE) / RATE
        tone = .09 * np.sin(2 * np.pi * 80 * t)
        for right_gain, expected_ratio in ((.49, .816), (0., .70)):
            with self.subTest(right_gain=right_gain):
                stereo = np.column_stack((tone, tone * right_gain))
                pcm, _ = process_array(stereo, studio_pcm16=True, live_pcm_scale=True,
                                       stereo_control=True, shape_control=True)
                settled = pcm[-RATE//4:, 2:]
                np.testing.assert_allclose(settled[:, 1] / settled[:, 0], expected_ratio, atol=.003)

    def test_dsp_only_preserves_front_audio_but_rejects_high_only_rear_control(self):
        elapsed = np.arange(RATE) / RATE - .5
        for hz in (700, 750, 1000, 3300):
            with self.subTest(hz=hz):
                pulse = .26 * np.sin(2 * np.pi * hz * elapsed) * np.exp(-np.maximum(0, elapsed) / .018)
                pulse[(elapsed < 0) | (elapsed > .045)] = 0
                dry = np.rint(np.column_stack((pulse, pulse)) * 32768).astype('<i2')
                pcm, _ = process_array(dry.astype(np.float32) / 32768, studio_pcm16=True,
                                       shape_control=True, stereo_control=True)
                np.testing.assert_array_equal(pcm[:, :2], dry)
                self.assertFalse(pcm[:, 2:].any())

    def test_low_hit_still_opens_rear_control_over_high_background(self):
        time = np.arange(RATE) / RATE
        elapsed = time - .5
        for hz in (80, 600):
            with self.subTest(hz=hz):
                hit = .26 * np.sin(2*np.pi*hz*elapsed) * np.exp(-np.maximum(elapsed, 0)/.018)
                hit[(elapsed < 0) | (elapsed >= .045)] = 0
                signal = hit + .12 * np.sin(2*np.pi*3300*time) if hz == 80 else hit
                pcm, _ = process_array(np.column_stack((signal, signal)), studio_pcm16=True)
                self.assertFalse(pcm[:RATE//2, 2:].any())
                self.assertGreater(pcm[RATE//2:RATE//2+3*BLOCK, 2:].max(), 5000)

    def test_rear_control_recovers_weak_low_hit_without_reacting_to_high_background(self):
        time = np.arange(RATE) / RATE
        elapsed = time - .5
        envelope = np.exp(-np.maximum(elapsed, 0)/.018) * ((elapsed >= 0) & (elapsed < .045))
        background = .35 * np.sin(2*np.pi*3300*time) * (.8 + .2*np.cos(2*np.pi*3*elapsed))
        for hz in (80, 750, 3300):
            with self.subTest(hz=hz):
                signal = background + .06 * np.sin(2*np.pi*hz*elapsed) * envelope
                pcm, _ = process_array(np.column_stack((signal, signal)), studio_pcm16=True)
                self.assertFalse(pcm[:RATE//2, 2:].any())
                if hz == 80:
                    self.assertGreater(pcm[RATE//2:RATE//2+3*BLOCK, 2:].max(), 1500)
                else:
                    self.assertFalse(pcm[:, 2:].any())

    def test_shaped_fall_keeps_existing_release_and_bypass_stays_silent(self):
        mapper = HapticMapper()
        mapper.process(1., 4, attack='sharp')
        np.testing.assert_array_equal(mapper.process(0., 4, attack='weight')[:, 0], [.75, .5, .25, 0.])
        audio = np.random.default_rng(1).normal(0,.1,(4*BLOCK,2))
        pcm, _ = process_array(audio, controls=Controls(bypass=True), studio_pcm16=True, shape_control=True)
        self.assertFalse(pcm[:, 2:].any())

    def test_replay_preserves_wav_and_maps_only_protected_replay_evidence(self):
        t = np.arange(RATE) / RATE
        capture = (.002 * np.sin(2 * np.pi * 90 * t)).astype(np.float32)
        capture[RATE//2:RATE//2+BLOCK] *= 95
        x = np.column_stack((capture, capture))
        records, mono_records, bypass_records = [], [], []
        pcm, _ = process_array(x, control_frames=records)
        expected, _ = process_array(x)
        process_array(capture[:, None], control_frames=mono_records)
        process_array(x, controls=Controls(bypass=True), control_frames=bypass_records)
        np.testing.assert_array_equal(pcm, expected)
        self.assertEqual(records, mono_records)
        self.assertEqual(len(records), RATE // BLOCK)
        self.assertTrue(all(frame['first_sample'] == i*BLOCK for i, frame in enumerate(records)))
        controls = np.asarray([frame['control_lr'] for frame in records]).reshape(-1, 2)
        self.assertTrue(np.all(controls[:RATE//2] == 0))
        self.assertTrue(np.any(controls[RATE//2:] > 0))
        self.assertTrue(np.all((controls >= 0) & (controls <= 1)))
        np.testing.assert_array_equal(controls[:, 0], controls[:, 1])
        self.assertFalse(any(any(frame['control_lr']) for frame in bypass_records))

    def test_studio_pcm_preserves_front_and_uses_only_control_on_rear(self):
        t = np.arange(RATE) / RATE
        left = np.rint(65 * np.sin(2 * np.pi * 90 * t)).astype('<i2')
        left[RATE//2:RATE//2+BLOCK] *= 95
        right = -left
        original = np.column_stack((left, right))
        stereo = original.astype(np.float32) / 32768
        frames = []
        pcm, _ = process_array(stereo, studio_pcm16=True, control_frames=frames)
        self.assertEqual(pcm.dtype, np.dtype('<i2'))
        np.testing.assert_array_equal(pcm[:, :2], original)
        expected = np.asarray([frame['control_lr'] for frame in frames]).reshape(-1,2)
        np.testing.assert_array_equal(pcm[:, 2:], np.clip(np.rint(expected*32768),0,32767))
        self.assertTrue(pcm[:, 2:].any())
        bypass, _ = process_array(stereo, controls=Controls(bypass=True), studio_pcm16=True)
        np.testing.assert_array_equal(bypass[:, :2], original)
        self.assertFalse(bypass[:, 2:].any())
        with self.assertRaises(ValueError):
            process_array(stereo[:, :1], studio_pcm16=True)
