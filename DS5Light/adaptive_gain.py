"""Session-local decision policy for one-second Studio rear PCM observations."""
import numpy as np

from core import HAPTIC_GAIN_MAX, HAPTIC_GAIN_MIN, RATE


class AdaptiveGain:
    """Suggest bounded changes to PC gain, with the manual setting as the ceiling."""

    def __init__(self, manual_percent):
        if type(manual_percent) is not int or not HAPTIC_GAIN_MIN * 100 <= manual_percent <= HAPTIC_GAIN_MAX * 100:
            raise ValueError('Invalid manual PC gain percentage.')
        self.manual = self.target = manual_percent
        self.last_window = None
        self.pressure = self.quiet = 0

    def observe(self, window, limited, samples, *, recovery_limited=None):
        """Return a new target only after consecutive complete windows justify a step."""
        if type(window) is not int or window < 0 or (
                self.last_window is not None and window <= self.last_window):
            return None
        if self.last_window is None or window != self.last_window + 1:
            self.pressure = self.quiet = 0
        self.last_window = window
        # A full second at 48 kHz contains 96,000 rear samples across both channels.
        if type(samples) is not int or samples != 96000 or type(limited) is not int or not 0 <= limited <= samples:
            self.pressure = self.quiet = 0
            return None

        self.pressure = self.pressure + 1 if limited * 100 >= samples else 0
        recovery_pressure = limited if recovery_limited is None else max(limited, recovery_limited)
        self.quiet = self.quiet + 1 if recovery_pressure * 1000 <= samples else 0
        target = self.target
        if self.pressure >= 3 and target > 100:
            target = max(100, target - 5)
        elif self.quiet >= 8 and target < self.manual:
            target = min(self.manual, target + 5)
        if target == self.target:
            return None
        self.pressure = self.quiet = 0
        self.target = target
        return target


class AdaptiveRearLevel:
    """Collect exact sample windows on the single Studio renderer thread."""

    def __init__(self):
        self.controls = None
        self.policy = None
        self.window = self.frames = self.limited = self.recovery_limited = 0

    def interrupt(self):
        self.window += 1
        self.frames = self.limited = self.recovery_limited = 0

    def process(self, data, controls, level, rear_peak):
        if controls != self.controls:
            self.controls = controls
            self.policy = AdaptiveGain(round(controls.gain * 100)) if not controls.bypass and controls.gain > 1 else None
            self.interrupt()
        if self.policy is None:
            return level.process(data, controls.gain, rear_peak=rear_peak)

        remaining = (RATE - self.frames) * 8
        previous = level.limited_samples
        gain = controls.gain if self.policy.target == self.policy.manual else self.policy.target / 100
        block = data[:remaining]
        if self.policy.target < self.policy.manual:
            # Recover only if the next step has headroom on the current input.
            next_percent = min(self.policy.manual, self.policy.target + 5)
            rear = np.frombuffer(block, '<i2').reshape(-1, 4)[:, 2:]
            self.recovery_limited += int(np.count_nonzero(rear > rear_peak * 100 // next_percent))
        output = level.process(block, gain, rear_peak=rear_peak)
        self.frames += len(output) // 8
        self.limited += level.limited_samples - previous
        if self.frames == RATE:
            self.policy.observe(self.window, self.limited, RATE * 2,
                                recovery_limited=self.recovery_limited)
            self.interrupt()
        if len(data) > remaining:
            output += self.process(data[remaining:], controls, level, rear_peak)
        return output
