import unittest

from adaptive_gain import AdaptiveGain


class AdaptiveGainTests(unittest.TestCase):
    def test_stationary_signal_does_not_recover_to_a_gain_that_would_clip(self):
        import numpy as np
        from adaptive_gain import AdaptiveRearLevel
        from core import Controls, RATE
        from output_gain import OutputGain

        renderer, level = AdaptiveRearLevel(), OutputGain()
        controls = Controls(gain=1.5)
        pcm = np.tile(np.array([0, 0, 675, 675], dtype='<i2'), (RATE, 1))
        for _ in range(20):
            renderer.process(pcm.tobytes(), controls, level, 1000)
        self.assertEqual(renderer.policy.target, 145)
        pcm[:, 2:] = 600
        for _ in range(8):
            renderer.process(pcm.tobytes(), controls, level, 1000)
        self.assertEqual(renderer.policy.target, 150)

    def test_steps_down_and_restores_with_separate_dwell_times(self):
        policy = AdaptiveGain(107)
        self.assertEqual([policy.observe(i, 960, 96000) for i in range(6)],
                         [None, None, 102, None, None, 100])
        self.assertEqual([policy.observe(i, 96, 96000) for i in range(6, 22)],
                         [None] * 7 + [105] + [None] * 7 + [107])
        self.assertIsNone(policy.observe(22, 0, 96000))

    def test_gaps_duplicates_and_invalid_samples_do_not_accelerate_steps(self):
        policy = AdaptiveGain(150)
        self.assertIsNone(policy.observe(0, 960, 96000))
        self.assertIsNone(policy.observe(0, 960, 96000))
        self.assertIsNone(policy.observe(1, 960, 96000))
        self.assertIsNone(policy.observe(3, 960, 96000))
        self.assertIsNone(policy.observe(4, 960, 48000))
        self.assertIsNone(policy.observe(5, 960, 96000))
        self.assertIsNone(policy.observe(6, 200, 96000))
        self.assertEqual([policy.observe(i, 960, 96000) for i in range(7, 10)], [None, None, 145])

    def test_manual_gain_at_or_below_unity_never_changes(self):
        for manual in (50, 100):
            policy = AdaptiveGain(manual)
            self.assertTrue(all(policy.observe(i, 960, 96000) is None for i in range(10)))
            self.assertEqual(policy.target, manual)

    def test_uses_actual_studio_rear_limiter_counts(self):
        import numpy as np
        from output_gain import OutputGain
        from studio_rehearsal_format import REHEARSAL_PEAK

        level = OutputGain()
        policy = AdaptiveGain(150)
        pcm = np.zeros((48000, 4), dtype='<i2')
        pcm[:, :2] = 20000
        pcm[:, 2:] = REHEARSAL_PEAK
        data = pcm.tobytes()
        decisions = []
        for window in range(3):
            previous = level.limited_samples
            level.process(data, 1.5, rear_peak=REHEARSAL_PEAK)
            decisions.append(policy.observe(window, level.limited_samples - previous, pcm[:, 2:].size))
        self.assertEqual(decisions, [None, None, 145])

    def test_render_windows_split_blocks_and_discard_old_manual_state(self):
        from dataclasses import replace
        from adaptive_gain import AdaptiveRearLevel
        from core import Controls, RATE
        from output_gain import OutputGain
        from studio_rehearsal_format import REHEARSAL_PEAK
        import numpy as np

        rear_level = AdaptiveRearLevel()
        level = OutputGain()
        controls = Controls(gain=1.5)
        pcm = np.tile(np.array([120, -120, REHEARSAL_PEAK, REHEARSAL_PEAK], dtype='<i2'), (RATE, 1))
        data = pcm.tobytes()
        for index in range(3):
            self.assertEqual(len(rear_level.process(data[:-8], controls, level, REHEARSAL_PEAK)), len(data) - 8)
            trial = rear_level.process(data[:16], controls, level, REHEARSAL_PEAK)
            np.testing.assert_array_equal(np.frombuffer(trial, '<i2').reshape(-1, 4)[:, :2], pcm[:2, :2])
            self.assertEqual(rear_level.frames, index + 1)
        self.assertEqual(rear_level.policy.target, 145)
        probe = pcm[:4800].copy()
        probe[:, 2:] = 2000
        played = rear_level.process(probe.tobytes(), controls, level, REHEARSAL_PEAK)
        np.testing.assert_array_equal(np.frombuffer(played, '<i2').reshape(-1, 4)[-1],
                                      [120, -120, 2900, 2900])
        rear_level.interrupt()
        self.assertEqual((rear_level.frames, rear_level.limited), (0, 0))
        manual = replace(controls, gain=1.23)
        rear_level.process(data[:8], manual, level, REHEARSAL_PEAK)
        self.assertEqual(rear_level.policy.target, 123)
        self.assertEqual(rear_level.frames, 1)
        rear_level.process(data[:8], replace(manual, bypass=True), level, REHEARSAL_PEAK)
        self.assertIsNone(rear_level.policy)
