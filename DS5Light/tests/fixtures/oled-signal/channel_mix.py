"""Optional standard 5.1 routing before legacy first-two-channel extraction."""
import numpy as np


class ChannelMixer:
    def __init__(self):
        self.rear = 0.
        self.lfe = 0.
        self.center = 0.
        self.gain = 1.
        self.soft_mix = None

    def process(self, data, channels, rate, rear=False, lfe=False, limiter='hard', center=False):
        if limiter not in ('hard', 'soft'):
            raise ValueError('알 수 없는 합산 제한 방식')
        # The process helper supplies fixed standard 5.1 / 7.1-surround masks.
        # Device-wide 8ch is only accepted after its mask is checked by the engine.
        if channels not in (6,8):
            self.rear = self.lfe = self.center = 0.
            self.gain = 1.
            self.soft_mix = None
            return data
        if not rear and not lfe and not center and self.rear == 0 and self.lfe == 0 and self.center == 0 and self.gain == 1:
            self.soft_mix = float(limiter == 'soft')
            return data
        x = np.frombuffer(data, '<i2').reshape(-1, channels)
        n = len(x)
        if not n:
            return data
        # 30 ms linear coefficient slew, independent of capture block length.
        def ramp(current, target, maximum):
            length = max(1, round(rate * .03))
            start = round(current / maximum * length)
            end = round(target / maximum * length)
            positions = start + np.sign(end-start)*np.arange(1, n+1)
            return np.clip(positions, min(start,end), max(start,end)) / length * maximum
        r = ramp(self.rear, .5 if rear else 0., .5)
        f = ramp(self.lfe, .25 if lfe else 0., .25)
        c = ramp(self.center, 2**-.5 if center else 0., 2**-.5)
        self.center = float(c[-1])
        self.rear, self.lfe = float(r[-1]), float(f[-1])
        # FL FR FC LFE surround-L surround-R. FC is optional, linked to both sides.
        # Front remains unity; only actual over-range sums trigger limiting.
        surrounds=x[:,4:6].astype(np.float64)
        if channels==8:
            # Averaging avoids a 6 dB jump for duplicated sides/rears.
            surrounds=(surrounds+x[:,6:8])*.5
        mixed = x[:, :2].astype(np.float64) + r[:, None]*surrounds + f[:, None]*x[:, 3:4] + c[:, None]*x[:, 2:3]
        # Linked stereo peak gain: immediate attack, linear recovery to unity
        # (at most 50 ms). No lookahead, no added audio buffering.
        overload = np.maximum(np.max(mixed, axis=1)/32767, -np.min(mixed, axis=1)/32768)
        required = 1 / np.maximum(1., overload)
        release_step = 1 / max(1, round(rate * .05))
        steps = release_step * np.arange(1, n + 1, dtype=np.float64)
        # Vector form of gain[i] = min(required[i], gain[i-1] + release_step).
        gains = np.minimum.accumulate(required - steps)
        gains = np.minimum(gains, self.gain) + steps
        self.gain = float(gains[-1])
        target = float(limiter == 'soft')
        if self.soft_mix is None:
            self.soft_mix = target
        # Crossfade limiting policies over 20 ms without reopening devices.
        step = 1 / max(1, round(rate * .02))
        start = self.soft_mix
        if start == target == 0:
            # The hard path does not need a parallel soft-limiter signal.
            mixed = np.clip(mixed, -32768, 32767)
        elif start == target == 1:
            mixed = mixed * gains[:, None]
        else:
            blend = start + np.clip(target-start, -step*np.arange(1,n+1), step*np.arange(1,n+1))
            hard = np.clip(mixed, -32768, 32767)
            soft = mixed * gains[:, None]
            mixed = hard*(1-blend[:,None]) + soft*blend[:,None]
        self.soft_mix = float(np.clip(start + np.sign(target-start)*min(abs(target-start), step*n), 0, 1))
        result = x.copy()
        result[:, :2] = np.clip(np.rint(mixed), -32768, 32767).astype('<i2')
        return result.tobytes()
