import unittest
from unittest.mock import Mock, patch

import numpy as np

from device_binding import DeviceIdentity
from tiny_gru import BURST, SHARP, UNCERTAIN, WEIGHT, MixFrontAI, ai_input_level, hit_shape, hit_strength


class MixFrontAITests(unittest.TestCase):
    def test_quiet_input_is_lifted_without_creating_a_hit_from_silence(self):
        features = np.zeros((4, 4), dtype=np.float32)
        features[0, 1] = 8e-6
        features[2, 1] = 3e-4
        features[3, 1] = .8
        _, gain, mid = ai_input_level(features, 3e-4)
        self.assertGreater(gain, 1)
        self.assertGreater(mid, 1e-5)
        features[0, 1] = 1e-8
        self.assertEqual(ai_input_level(features, 0)[2], 0)
        features[0, 1] = 8e-6
        features[3, 1] = 0.
        self.assertEqual(ai_input_level(features, 0)[2], 0)

    def test_shape_uses_class_margin_and_causal_tail_evidence(self):
        evidence = np.zeros((4, 4), dtype=np.float32)
        evidence[1, 1] = .10
        for event, shape in ((0, WEIGHT), (2, SHARP), (4, BURST)):
            scores = np.zeros(7)
            scores[event] = 2.
            self.assertEqual(hit_shape(scores, evidence), (shape, 0))
        evidence[2, 1] = .08
        self.assertEqual(hit_shape(scores, evidence), (BURST, 1))
        scores[3] = 1.9
        self.assertEqual(hit_shape(scores, evidence), (UNCERTAIN, 0))

    def test_marginal_impact_requires_a_lead_over_speech(self):
        probabilities = np.array([.69, .90, .60, .55, .60, .60, .60])
        logits = lambda: np.log(probabilities / (1 - probabilities))
        self.assertGreater(hit_strength(logits(), .02), 0)
        probabilities[3] = .65
        self.assertEqual(hit_strength(logits(), .02), 0)
        probabilities[2] = .80
        self.assertGreater(hit_strength(logits(), .02), 0)
        self.assertEqual(hit_strength(logits(), 0.0), 0)

    def test_strong_marker_requires_an_accepted_hit(self):
        state = np.zeros(16, dtype=np.float32)
        features = state.reshape(4, 4)
        device = Mock()
        device.send_feature_report.side_effect = len
        for strong in (False, True):
            with self.subTest(strong=strong), patch.dict(
                'os.environ', DS5LIGHT_STRONG_AI_TEST=str(int(strong))
            ):
                device.reset_mock()
                ai = MixFrontAI(Mock(), lambda: False)
                self.addCleanup(ai.close)
                ai.weights = {}
                with (patch('tiny_gru.infer', return_value=(state, np.full(7, 2.))),
                      patch('tiny_gru.time.monotonic', return_value=1.),
                      patch('device_diagnostics.with_selected_device',
                            side_effect=lambda binding, identity, send, cancel: send(device))):
                    ai._infer(features, 0., ai.generation, state, 3, 1.)
                    device.send_feature_report.assert_not_called()
                    ai._infer(features, .02, ai.generation, state, 3, 1.)
                packet, = device.send_feature_report.call_args.args
                self.assertEqual(len(packet), 64)
                self.assertEqual(packet[8:12], b'TST1' if strong else bytes(4))
                self.assertEqual(packet[12:14], bytes([UNCERTAIN, 0]))
                self.assertEqual(packet[7], 100)  # An ordinary saturated hit still has no marker.

    def test_hid_uses_real_device_helper_with_event_shaped_cancellation(self):
        binding = Mock()
        binding.snapshot.return_value = DeviceIdentity(hid_path=b'test-pico')
        device = Mock()
        device.send_feature_report.side_effect = len
        features = np.zeros((4, 4), dtype=np.float32)
        features[0, 1] = .02
        features[3, 1] = .8
        state = np.zeros(16, dtype=np.float32)

        for stopped in (False, True):
            with self.subTest(stopped=stopped):
                device.reset_mock()
                ai = MixFrontAI(binding, lambda: stopped)
                self.addCleanup(ai.close)
                ai.weights = {}
                with (patch('tiny_gru.infer', return_value=(state, np.full(7, 2.))),
                      patch('tiny_gru.time.monotonic', return_value=1.),
                      patch('hid.device', return_value=device)):
                    ai._infer(features, .02, ai.generation, state, 3, 1.)
                self.assertEqual(ai.sent, int(not stopped))
                if stopped:
                    device.open_path.assert_not_called()
                else:
                    device.open_path.assert_called_once_with(b'test-pico')
                    packet = device.send_feature_report.call_args.args[0]
                    self.assertEqual((len(packet), packet[:7]), (64, b'\x80\x66\x27MAI1'))
                    device.close.assert_called_once()
