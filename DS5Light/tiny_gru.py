"""Opt-in H16 prototype. Run inference outside the Studio output worker."""
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
from types import SimpleNamespace
import time

import numpy as np


MODEL = Path(__file__).resolve().parent / 'assets' / 'tiny-gru-h16-smoke.npz'
# Head indices follow the sorted class names of the bundled H16 model.
IMPACT_CLASS = 0
SLASH_CLASS = 2
SPEECH_CLASS = 3
MAGIC_CLASS = 4
EXPLOSION_CLASS = 6
COMBAT_CLASSES = [IMPACT_CLASS, SLASH_CLASS, MAGIC_CLASS, 5, EXPLOSION_CLASS]
SHARP, WEIGHT, BURST, UNCERTAIN = range(1, 5)
AI_REFERENCE_POWER = .012
AI_MAX_POWER_GAIN = 256.0


def load_weights():
    with np.load(MODEL, allow_pickle=False) as archive:
        shapes = dict(mean=(16,), scale=(16,), gru_weight_ih_l0=(48, 16),
                      gru_weight_hh_l0=(48, 16), gru_bias_ih_l0=(48,),
                      gru_bias_hh_l0=(48,), head_weight=(7, 16), head_bias=(7,))
        weights = {name: archive[name] for name in shapes}
        if (any(w.shape != shapes[name] or w.dtype != np.float32 or not np.isfinite(w).all()
                for name, w in weights.items()) or np.any(weights['scale'] <= 0)):
            raise ValueError('Invalid Tiny GRU weights.')
    return weights


def sigmoid(values):
    return 1 / (1 + np.exp(-np.clip(values, -60, 60)))


def ai_input_level(features, previous_power):
    """Track trailing capture level without changing audio or relative onset."""
    power = float(features[2].sum())
    response = .012 if power > previous_power else .003
    level = previous_power + response * (power - previous_power)
    gain = max(1.0, min(AI_MAX_POWER_GAIN, AI_REFERENCE_POWER / max(level, 1e-8)))
    raw_mid = float(features[0, 1])
    mid = 0.0
    if (features[3, 1] >= .25 and raw_mid > 1e-7 and raw_mid * gain > 1e-5
            and raw_mid >= .18 * features[0].sum()):
        mid = raw_mid * gain
    return level, gain, mid


def infer(weights, frame, state):
    x = (frame - weights['mean']) / weights['scale']
    ir, iz, candidate = np.split(weights['gru_weight_ih_l0'] @ x + weights['gru_bias_ih_l0'], 3)
    hr, hz, hn = np.split(weights['gru_weight_hh_l0'] @ state + weights['gru_bias_hh_l0'], 3)
    update = sigmoid(iz + hz)
    state = (1 - update) * np.tanh(candidate + sigmoid(ir + hr) * hn) + update * state
    return state, weights['head_weight'] @ state + weights['head_bias']


def hit_strength(logits, mid_energy):
    scores = sigmoid(logits)
    combat = (float(scores[COMBAT_CLASSES].max()) - .70) / .30
    impact = 0.0
    # Recover weaker hits only when the impact score leads the speech score.
    if float(scores[IMPACT_CLASS]) >= float(scores[SPEECH_CLASS]) + .08:
        impact = (float(scores[IMPACT_CLASS]) - .665) / .335
    return min(100, round(1200 * np.sqrt(mid_energy) * max(0.0, combat, impact)))


def hit_shape(logits, evidence):
    scores = sigmoid(logits)
    ranked = sorted(COMBAT_CLASSES, key=scores.__getitem__, reverse=True)
    winner, runner_up = ranked[:2]
    if scores[winner] < .69 or scores[winner] - max(scores[runner_up], scores[SPEECH_CLASS]) < .035:
        return UNCERTAIN, 0
    energy, fast, slow, onset = evidence
    if winner == SLASH_CLASS or (winner == IMPACT_CLASS and onset[2] >= .5 and energy[2] > energy[0]):
        return SHARP, 0
    if winner in (MAGIC_CLASS, EXPLOSION_CLASS):
        # A tail requires energy already present in the causal slower envelope.
        tail = slow[1:3].sum() >= .55 * fast[1:3].sum() > 0
        return BURST, int(tail)
    return WEIGHT, 0


class MixFrontAI:
    def __init__(self, binding, stopped):
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='DS5Light-GRU')
        self.binding = binding
        self.strong_test = os.environ.get('DS5LIGHT_STRONG_AI_TEST', '1') == '1'
        self.identity = binding.snapshot()
        self.stopped = stopped
        self.weights = None
        self.features = np.empty((4, 4), dtype=np.float32)
        self.pending = None
        self.error = ''
        self.sent = 0
        self.sequence = 0
        self.generation = 0
        self.last_hit = 0.0
        self.reset()

    def reset(self):
        self.generation += 1
        self.sequence = 0
        self.previous_mid = 0.0
        self.input_power = AI_REFERENCE_POWER

    def _infer(self, features, mid, generation, previous, warm, now, evidence=None):
        from device_diagnostics import with_selected_device
        if self.weights is None:
            self.weights = load_weights()
        state, logits = infer(self.weights, features.ravel(), previous)
        if warm >= 3 and now - self.last_hit >= .050 and mid > 0 and np.isfinite(logits).all():
            strength = hit_strength(logits, mid)
            if strength:
                shape, tail = hit_shape(logits, features if evidence is None else evidence)
                if self.strong_test:
                    strength = 100

                def cancelled():
                    return self.stopped() or self.generation != generation or time.monotonic() - now >= .025

                def send(device):
                    if cancelled():
                        return False
                    marker = b'TST1' if self.strong_test else bytes(4)
                    packet = b'\x80\x66\x27MAI1' + bytes([strength]) + marker + bytes([shape, tail]) + bytes(50)
                    if device.send_feature_report(packet) != len(packet):
                        raise OSError('Studio AI report was not fully submitted.')
                    return True

                try:
                    cancel_event = SimpleNamespace(is_set=cancelled)
                    if with_selected_device(self.binding, self.identity, send, cancel_event):
                        self.last_hit = now
                        self.sent += 1
                except RuntimeError:
                    if not cancelled():
                        raise
        return state, warm + 1

    def fail(self, exc):
        self.error = f'{type(exc).__name__}: {exc}'
        self.reset()

    def observe(self, frames):
        if self.error or frames != 240:
            self.reset()
            return
        self.sequence += 1
        self.input_power, gain, mid = ai_input_level(self.features, self.input_power)
        if self.sequence % 2:
            self.previous_mid = mid
            if mid:
                self.previous_evidence = self.features.copy()
            return
        state = np.zeros(16, dtype=np.float32)
        warm = 0
        if self.pending is not None:
            if not self.pending.done():
                return
            try:
                result = self.pending.result()
                if self.pending_frame == (self.generation, self.sequence - 2):
                    state, warm = result
            except Exception as exc:
                self.fail(exc)
                return
        self.pending_frame = (self.generation, self.sequence)
        try:
            features = self.features.copy()
            evidence = self.previous_evidence if self.previous_mid > mid else features
            features[:3] *= gain
            self.pending = self.executor.submit(self._infer, features,
                                                max(mid, self.previous_mid), self.generation,
                                                state, warm, time.monotonic(), evidence)
        except Exception as exc:
            self.fail(exc)

    def close(self):
        self.reset()
        self.executor.shutdown(wait=False, cancel_futures=True)
