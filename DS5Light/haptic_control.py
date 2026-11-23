"""Fusion and bounded stereo control mapping for Studio processing."""

import math

import numpy as np
from core import BLOCK, HAPTIC_BAND_COUNT

_BLOCK_SAMPLE = np.arange(1, BLOCK + 1, dtype=np.int16)[:, None]
_BLOCK_PROGRESS = np.linspace(0, 1, BLOCK + 1)[1:, None]
_BLOCK_WEIGHT = _BLOCK_PROGRESS ** 2
_BLOCK_SHARP = 1 - (1 - _BLOCK_PROGRESS) ** 3


def fuse(protected, detail):
    """Allocate remaining headroom after preserving the DSP transient."""
    if not (math.isfinite(protected) and math.isfinite(detail)):
        raise ValueError('Non-finite haptic evidence.')
    protected = min(1.0, max(0.0, protected))
    if protected == 0.0:
        return 0.0
    detail = min(1.0, max(0.0, detail))
    return protected + (1.0 - protected) * detail


class HapticMapper:
    def __init__(self):
        self.level = (0.0, 0.0)

    def process(self, target, frames, balance=0.0, *, attack=None):
        levels = (target * (1 - max(0, balance)), target * (1 - max(0, -balance)))
        start = np.asarray(self.level)
        delta = np.asarray(levels) - start
        if frames == BLOCK and delta.dtype in (np.float32, np.float64):
            step = delta / BLOCK
            if (step == 0).any():
                # Match linspace when a step is zero, including subnormal targets.
                ramp = start + _BLOCK_PROGRESS.astype(delta.dtype, copy=False) * delta
            else:
                ramp = start + _BLOCK_SAMPLE * step
            ramp[-1] = levels
            ramp = ramp.astype(np.float32, copy=False)
        else:
            ramp = np.linspace(self.level, levels, frames + 1, dtype=np.float32)[1:]
        if attack is not None:
            rising = delta > 0
            if rising.any():
                if frames == BLOCK:
                    eased = _BLOCK_WEIGHT if attack == 'weight' else _BLOCK_SHARP
                else:
                    progress = np.linspace(0, 1, frames + 1)[1:, None]
                    eased = progress ** 2 if attack == 'weight' else 1 - (1 - progress) ** 3
                ramp[:, rising] = start[rising] + eased * delta[rising]
        self.level = levels
        return ramp

class HapticControlDsp:
    """One stream's DSP and rear-control ramp state."""

    def __init__(self, processor, *, stereo=False, shape=False):
        self.processor = processor
        self.mapper = HapticMapper()
        self.evidence = np.empty(2, dtype=np.float32)
        self.direction = np.empty(2, dtype=np.float32) if stereo else None
        self.bands = np.empty(HAPTIC_BAND_COUNT, dtype=np.float32) if shape else None

    def process(self, stereo, controls, *, band_features=None, allow_direction=True, rear_only=False):
        direction = self.direction if allow_direction else None
        filtered = self.processor.process(stereo, controls,
                                          band_features=band_features, haptic_evidence=self.evidence,
                                          haptic_direction=direction, haptic_bands=self.bands, rear_only=rear_only)
        if not len(filtered):
            return filtered, np.empty((0, 2))
        balance = self.processor.sustained_balance if rear_only and direction is not None else 0.0
        if direction is not None:
            left, right = direction
            total = left + right
            if total > 0:
                ratio = (right - left) / total
                # Require roughly 4:1 excess energy on one side. Attenuate
                # only the quieter side, keeping the level bound unchanged.
                if abs(ratio) >= .6:
                    balance = math.copysign(min(abs(ratio), .65), ratio)
        attack = None
        if self.bands is not None:
            low, mid = self.bands ** 2
            if low > 3 * mid:
                attack = 'weight'
            elif mid > 3 * low:
                attack = 'sharp'
        target = fuse(*self.evidence)
        if rear_only:
            # Lift quiet PC control before the firmware gate. Unity remains
            # the maximum and the mapper retains the original stereo ramp.
            target = 3.0 * target / (1.0 + 2.0 * target)
        return filtered, self.mapper.process(target, len(filtered), balance, attack=attack)

def encode_studio_pcm(front, rear):
    """Pack matching stereo audio and nonnegative rear control as PCM16."""
    front, rear = np.asarray(front), np.asarray(rear)
    if front.ndim != 2 or front.shape[1] != 2 or rear.shape != front.shape:
        raise ValueError('Studio PCM requires matching stereo front and rear blocks.')
    if not np.isfinite(front).all() or not np.isfinite(rear).all():
        raise ValueError('Studio PCM requires finite audio and control values.')
    if np.any(rear < 0):
        raise ValueError('Studio rear control values must be nonnegative.')
    channels = np.column_stack((front, rear))
    return np.clip(np.rint(channels * 32768), -32768, 32767).astype('<i2')
