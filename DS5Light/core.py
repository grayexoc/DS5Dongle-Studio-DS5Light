"""독립 구현: causal 대역별 배경 억제. 음악/음성 분리기는 아니다."""
from dataclasses import dataclass
import numpy as np


def load_signal_filters():
    import scipy.signal
    return scipy.signal

RATE = 48000
BLOCK = 240
HAPTIC_BAND_COUNT = 2  # Below the existing 600 Hz crossover.
MIN_HAPTIC_ENERGY_SHARE = .25
HAPTIC_GAIN_MIN = 0.5
HAPTIC_GAIN_MAX = 3.0
LEGACY_HAPTIC_GAIN_MAX = 4.0

@dataclass(frozen=True)
class Controls:
    mode: str = 'normal'
    bypass: bool = False
    strength: float = .55
    background: bool = True
    transient: bool = True
    rear: bool = False
    lfe: bool = False
    limiter: str = 'hard'
    center: bool = False
    gain: float = 1.0
    impact: float = .85

def select_stereo(x):
    x = np.asarray(x, dtype=np.float32)
    if x.ndim != 2 or x.shape[1] < 1:
        raise ValueError('입력은 frames × channels이어야 합니다')
    return np.repeat(x, 2, axis=1) if x.shape[1] == 1 else x[:, :2]

def duplicate(x):
    return np.tile(x, (1, 2))

class Processor:
    def __init__(self):
        # Complementary differences sum exactly to x; common stereo controls.
        self._signal = load_signal_filters()
        self.sos = [self._signal.butter(2, f, fs=RATE, output='sos') for f in (120, 600, 2500)]
        self.zi = [np.zeros((len(s), 2, 2)) for s in self.sos]
        self.bg = np.full(4, 1e-8)
        self.mean = np.zeros(4)
        self.dev = np.full(4, .01)
        self.previous = np.zeros(4)
        self.gain = np.ones(4)
        self.age = 0.
        self.slow_energy = np.full(4, 1e-8)
        self.fast_energy = np.full(4, 1e-8)
        self.hold = np.zeros(4)
        self.learn_pause = np.zeros(4)
        self.last_background = True
        self.initialized = False
        self.event_cooldown = np.zeros(4)
        self.was_event = np.zeros(4,dtype=bool)
        self.stable_rise = np.zeros(4)
        self._envelope_size = None
        self._coefficient_controls = None
        self._slow_times = np.array([.045,.025,.020,.015])
        self._direction_energy = None
        self._sustained_direction_time = 0.0
        self.sustained_balance = 0.0
        self._rear_evidence_active = False
        self._capacity = BLOCK
        self._bands = np.empty((4, self._capacity, 2), dtype=np.float32)
        self._ramp = np.empty((4, self._capacity), dtype=np.float64)
        self._weighted = np.empty((self._capacity, 2), dtype=np.float64)
        self._y = np.empty((self._capacity, 2), dtype=np.float64)
        self._positions = np.arange(1, self._capacity + 1, dtype=np.float64)
        self._cache_gain_curves()

    def _cache_gain_curves(self):
        # Same 3/55 ms time constants, sampled at the actual sample rate.
        # Cache on allocation, not in the real-time processing loop.
        self._attack_curve = -np.expm1(-self._positions / (RATE * .003))
        self._release_curve = -np.expm1(-self._positions / (RATE * .055))
        self._gap_release_curve = -np.expm1(-self._positions / (RATE * .025))

    def _ensure_capacity(self, n):
        if n <= self._capacity:
            return
        self._capacity = max(n, self._capacity * 2)
        self._bands = np.empty((4, self._capacity, 2), dtype=np.float32)
        self._ramp = np.empty((4, self._capacity), dtype=np.float64)
        self._weighted = np.empty((self._capacity, 2), dtype=np.float64)
        self._y = np.empty((self._capacity, 2), dtype=np.float64)
        self._positions = np.arange(1, self._capacity + 1, dtype=np.float64)
        self._cache_gain_curves()

    def _gain_ramp(self, target, n, gap=None):
        # Follow the exponential envelope inside the block as well as at its
        # endpoint. A straight chord delayed the beginning of an attack and
        # changed slope abruptly at every block boundary. No lookahead/queue.
        ramp = self._ramp[:, :n]
        ramp[:] = self._release_curve[:n]
        if gap is not None:
            np.copyto(ramp, self._gap_release_curve[:n], where=gap[:, None])
        np.copyto(ramp, self._attack_curve[:n], where=(target > self.gain)[:, None])
        ramp *= (target - self.gain)[:, None]
        ramp += self.gain[:, None]
        self.gain = ramp[:, -1].copy()
        return ramp

    def process(self, x, controls=Controls(), *,
                band_features=None, haptic_evidence=None, haptic_direction=None, haptic_bands=None, rear_only=False):
        x = select_stereo(x)
        if not np.isfinite(x).all():
            raise ValueError('비정상 오디오 값: 무음 실패 정책 필요')
        n = len(x)
        if not n:
            return x
        self._ensure_capacity(n)
        dt = n / RATE
        # Controls is frozen; recompute scalar bounds only on a settings change.
        # Keep the clipping math identical while avoiding two scalar NumPy
        # dispatches for every 5 ms block.
        if controls is not self._coefficient_controls:
            self._strength = np.clip(controls.strength, 0, 1)
            self._impact = np.clip(controls.impact, 0, 1) if controls.transient else 0.
            self._coefficient_controls = controls
        lows = []
        for k, sos in enumerate(self.sos):
            if len(sos) == 1:
                low, state = self._signal.lfilter(sos[0, :3], sos[0, 3:], x, axis=0, zi=self.zi[k][0])
                self.zi[k] = state[None]
            else:
                low, self.zi[k] = self._signal.sosfilt(sos, x, axis=0, zi=self.zi[k])
            lows.append(low)
        bands = self._bands[:, :n]
        np.copyto(bands[0], lows[0])
        np.subtract(lows[1], lows[0], out=bands[1])
        np.subtract(lows[2], lows[1], out=bands[2])
        np.subtract(x, lows[2], out=bands[3])
        # Energy before channel combination avoids antiphase cancellation.
        energy = np.einsum('ijk,ijk->i', bands, bands, optimize=False) / (n * 2)
        # Trailing envelopes only: no lookahead or additional audio queue.
        # The slow low-band envelope averages waveform phase fluctuations; a
        # separate fast/slow comparison preserves the start of short impacts.
        if self._envelope_size != n:
            self._fast_alpha = 1-np.exp(-dt/.006)
            self._slow_alpha = 1-np.exp(-dt/self._slow_times)
            self._envelope_size = n
        fast_a, slow_a = self._fast_alpha, self._slow_alpha
        self.sustained_balance = 0.0
        if haptic_direction is not None:
            haptic_direction.fill(0)
            left = bands[:HAPTIC_BAND_COUNT, :, 0]
            left_energy = np.einsum('ij,ij->i', left, left) / n
            # Reuse the shared stereo energy to derive the other channel.
            low_energy = energy[:HAPTIC_BAND_COUNT]
            side_energy = np.column_stack((left_energy, np.maximum(0, 2 * low_energy - left_energy)))
            if self._direction_energy is None:
                self._direction_energy = side_energy.copy()
            side_change = side_energy - self._direction_energy
            self._direction_energy += slow_a[:HAPTIC_BAND_COUNT, None] * side_change
            if rear_only and controls.mode == 'normal' and not controls.bypass:
                # Require persistent low-band imbalance before steering the background.
                left, right = self._direction_energy.sum(axis=0)
                ratio = (right - left) / max(left + right, 1e-10)
                if abs(ratio) >= .6:
                    direction = 1 if ratio > 0 else -1
                    elapsed = max(0., direction * self._sustained_direction_time) + dt
                    self._sustained_direction_time = direction * min(elapsed, .04)
                    if elapsed >= .04:
                        self.sustained_balance = ratio * .30
                else:
                    self._sustained_direction_time = 0.
            else:
                self._sustained_direction_time = 0.
        else:
            self._direction_energy = None
            self._sustained_direction_time = 0.
        if self.age == 0:
            self.fast_energy = energy.copy()
            self.slow_energy = energy.copy()
            self.bg = np.maximum(energy, 1e-10)
        old_slow = self.slow_energy.copy()
        # A weaker follow-up hit can rise sharply against the decaying tail
        # before the slower envelope recovers enough to recognise a new onset.
        protect_hits = controls.mode == 'normal' and not controls.bypass and self._impact > 0
        short_rise = False
        if protect_hits:
            short_rise = (energy > self.fast_energy * 2.7) & (energy > self.bg * 2.5)
        energy_jump = energy - self.fast_energy
        self.fast_energy += fast_a*energy_jump
        self.slow_energy += slow_a*(energy-self.slow_energy)
        # Relative thresholds follow game volume; an absolute floor only stops
        # digital silence and quantization noise from opening protection.
        floor = np.maximum(1e-10, self.bg*.015)
        onset_ratio = self.fast_energy / np.maximum(old_slow, floor)
        background_ratio = self.slow_energy / np.maximum(self.bg, floor)
        contrast = np.clip((background_ratio-1.25)/3., 0, 1)
        onset = np.clip((onset_ratio-1.8)/2.2, 0, 1)
        onset *= np.clip((self.fast_energy-floor)/(floor*8+1e-12),0,1)
        if band_features is not None:
            # Rows are instantaneous mean-square, fast envelope, slow envelope, and onset.
            band_features[:] = energy, self.fast_energy, self.slow_energy, onset
        event = (onset>.2) & (background_ratio>1.6)
        self.hold = np.maximum(0., self.hold-dt)
        # Freeze rising background briefly, never indefinitely. Repeated or
        # sustained energy resumes slow learning instead of latching the gate.
        self.learn_pause = np.maximum(0., self.learn_pause-dt)
        self.event_cooldown = np.maximum(0.,self.event_cooldown-dt)
        # The follow-up can renew protection, while background learning keeps
        # the original onset cooldown and independently decides when to pause.
        follow_up = ((self.event_cooldown > 0) & (self.hold <= 0) &
                     short_rise & (energy > floor * 8))
        self.hold[event | follow_up] = .035
        new_event = event & ~self.was_event & (self.event_cooldown<=0)
        self.learn_pause[new_event] = .080
        self.event_cooldown[new_event] = .25
        self.was_event = event.copy()
        rise_time=.045 if self.age<.20 else 1.8
        alpha = 1-np.exp(-dt/np.where(self.slow_energy>self.bg,rise_time,.22))
        alpha = np.where((self.learn_pause>0)&(self.slow_energy>self.bg),0.,alpha)
        # Learn valleys without letting an impact tail raise the background floor.
        learning_energy = np.minimum(self.slow_energy, self.fast_energy) if self._impact > 0 else self.slow_energy
        self.bg += alpha*(learning_energy-self.bg)
        self.age += dt
        if protect_hits and controls.background:
            # A higher background level can linger in contrast protection.
            # Reduce that contribution only after the envelopes have settled;
            # a confirmed hit still gets its original onset/hold protection.
            stable = ((self.fast_energy >= self.slow_energy * .6) &
                      (self.fast_energy <= self.slow_energy * 1.6) &
                      (background_ratio > 1.6))
            self.stable_rise = np.where(stable, np.minimum(self.stable_rise + dt, .30), 0.)
            contrast *= 1 - .65 * np.clip((self.stable_rise - .18) / .12, 0, 1)
        else:
            self.stable_rise.fill(0)
        protection = np.maximum(contrast, np.where(self.hold>0,1.,onset))
        protection *= self._impact
        # A real energy valley ends protection; sustained effects keep their decay.
        gap = (self.fast_energy < self.slow_energy*.5) & (self._impact > 0)
        self.hold[gap] = 0.
        protection[gap] *= np.clip(self.fast_energy[gap] / np.maximum(self.slow_energy[gap]*.5, floor[gap]), 0, 1)
        low = slice(0, HAPTIC_BAND_COUNT)
        # Keep spill from the crossover from opening impact protection.
        low_band_hit = protect_hits and energy[low].sum() >= energy.sum() * MIN_HAPTIC_ENERGY_SHARE
        if protect_hits and not low_band_hit and np.any((event | follow_up)[low]):
            # A loud steady background can dominate the block while the hit
            # supplies most of the new energy. Require a confirmed low rise.
            excess = np.maximum(energy_jump, 0.)
            low_band_hit = excess[low].sum() > .5 * excess.sum()
        if protect_hits and not low_band_hit:
            protection[low] = 0.
        if haptic_evidence is not None:
            haptic_evidence[:] = 0
            if haptic_bands is not None:
                haptic_bands.fill(0)
            sustain_low = False
            if rear_only and controls.mode == 'normal' and not controls.bypass:
                # Compare the bass to its neighbouring band. Treble can dominate
                # the full mix even when a real, sustained bass tone is present.
                bass_share = self.slow_energy[0] / max(self.slow_energy[low].sum(), 1e-12)
                broadband_low = energy[low].sum() >= energy.sum() * MIN_HAPTIC_ENERGY_SHARE
                sustain_low = (broadband_low or
                               (bass_share > .32 and energy[0] > max(1e-10, .32 * energy[low].sum())))
            if sustain_low or low_band_hit:
                amplitude = np.sqrt(energy[low])
            if sustain_low:
                attenuation = 10 ** (-14 * self._strength / 20) if controls.background else 1.0
                sustained = np.max(amplitude) if broadband_low else amplitude[0]
                # Restore weight where the lowest band carries substantial energy. The
                # slower envelope limits the lift during a sudden attack.
                bass_weight = min(1.0, max(0.0, (bass_share - .32) / .23))
                settled_bass = np.sqrt(min(energy[0], self.slow_energy[0]))
                haptic_evidence[0] = max(sustained, 3.0 * bass_weight * settled_bass) * attenuation
            if low_band_hit:
                protected = protection[low] * amplitude * (self.hold[low] > 0)
                transient_level = np.max(protected)
                haptic_evidence[0] = max(haptic_evidence[0], transient_level)
                if transient_level > 0.0:
                    self.sustained_balance = 0.0
                haptic_evidence[1] = np.max(onset[low] * amplitude)
                if haptic_bands is not None:
                    haptic_bands[low] = protected
                if haptic_direction is not None and transient_level > 0.0:
                    band = int(np.argmax(protected))
                    if np.max(side_change[band]) > floor[band] * 8:
                        np.maximum(0, side_change[band], out=haptic_direction)
        if rear_only:
            if haptic_evidence is not None:
                # A crossover ringing into digital silence may finish a hit,
                # but must not start one after a rejected high-only sound ends.
                active = haptic_evidence[0] > 0
                if active and not self._rear_evidence_active and not np.any(x):
                    haptic_evidence.fill(0)
                    active = False
                self._rear_evidence_active = active
            return x
        self._rear_evidence_active = False
        if controls.mode == 'pure':
            return np.zeros_like(x)
        if controls.mode != 'normal':
            raise ValueError('알 수 없는 모드')
        strength = self._strength
        target = 10**((-14*strength*(1-protection))/20)
        if not controls.background or controls.bypass:
            target[:] = 1
        if not self.initialized or controls.background and not self.last_background:
            # Start at the requested attenuation, not at unfiltered full gain.
            self.gain[:] = 10**(-14*strength/20) if controls.background and not controls.bypass else 1.
            self.initialized = True
        self.last_background = controls.background
        # Gains ramp sample-by-sample. No AGC or upward output boost.
        ramp = self._gain_ramp(target, n, gap)
        y = self._y[:n]
        np.multiply(bands[0], ramp[0, :, None], out=y)
        band_count = len(bands) if controls.bypass else HAPTIC_BAND_COUNT
        for band in range(1, band_count):
            np.multiply(bands[band], ramp[band, :, None], out=self._weighted[:n])
            np.add(y, self._weighted[:n], out=y)
        np.clip(y, -1, 1, out=y)
        return y.astype(np.float32)

class StreamingResampler:
    """Causal IIR antialias + stateful linear interpolation, prototype quality."""
    def __init__(self, source_rate, dest_rate=RATE):
        self.step = source_rate/dest_rate
        self.position = 0.
        self.tail = np.empty((0, 2))
        self._signal = load_signal_filters() if source_rate != dest_rate else None
        self.sos = self._signal.butter(6, .42*min(source_rate, dest_rate), fs=source_rate, output='sos') if self._signal is not None else None
        self.zi = np.zeros((len(self.sos), 2, 2)) if self.sos is not None else None
    def process(self, x):
        if self.sos is None:
            return x.copy()
        x, self.zi = self._signal.sosfilt(self.sos, x, axis=0, zi=self.zi)
        a = np.concatenate((self.tail, x))
        positions = np.arange(self.position, len(a)-1, self.step)
        if len(positions):
            i = positions.astype(int)
            f = (positions-i)[:, None]
            y = a[i]*(1-f)+a[i+1]*f
            self.position = positions[-1]+self.step-(len(a)-1)
        else:
            y = np.empty((0, 2))
            self.position -= max(0, len(a)-1)
        self.tail = a[-1:].copy()
        return y.astype(np.float32)

class FrameRing:
    """Bounded queue; caller provides short lock. Drift interpolation at render side."""
    def __init__(self, capacity=3840, target=720):
        self.data = np.zeros((capacity, 2), np.float32)
        self.capacity, self.target = capacity, target
        self.read = self.write = self.count = 0
        self.phase = 0.
        self.ready = False
        self.drops = self.underruns = 0
        self.correction = 0.
    def clear(self):
        self.read = self.write = self.count = 0
        self.phase = 0.
        self.ready = False
    def push(self, x):
        if len(x) >= self.capacity:
            x = x[-self.capacity+1:]
            self.clear()
            self.drops += 1
        if self.count+len(x) > self.capacity:
            self.clear()
            self.drops += 1
        idx = (self.write+np.arange(len(x))) % self.capacity
        self.data[idx] = x
        self.write = (self.write+len(x)) % self.capacity
        self.count += len(x)
    def pop(self, n):
        if not self.ready and self.count >= self.target+n:
            self.ready = True
        if not self.ready:
            return np.zeros((n, 2), np.float32)
        desired = np.clip((self.count-self.target-n)*.000002, -.001, .001)
        self.correction += .01*(desired-self.correction)
        pos = self.phase+np.arange(n)*(1+self.correction)
        consumed = int(self.phase+n*(1+self.correction))
        if int(pos[-1])+1 >= self.count or consumed > self.count:
            self.underruns += 1
            self.clear()
            return np.zeros((n, 2), np.float32)
        i = pos.astype(int)
        f = (pos-i)[:, None]
        out = self.data[(self.read+i)%self.capacity]*(1-f)+self.data[(self.read+i+1)%self.capacity]*f
        self.read = (self.read+consumed)%self.capacity
        self.count -= consumed
        self.phase = self.phase+n*(1+self.correction)-consumed
        return out.astype(np.float32)
