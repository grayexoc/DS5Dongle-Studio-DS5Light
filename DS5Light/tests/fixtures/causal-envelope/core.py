"""독립 구현: causal 대역별 배경 억제. 음악/음성 분리기는 아니다."""
from dataclasses import dataclass
import numpy as np
from scipy.signal import butter, sosfilt

RATE = 48000
BLOCK = 240

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

@dataclass(frozen=True)
class RumbleSample:
    timestamp: float = -1e9
    left: float = 0
    right: float = 0
    valid: bool = False

class RumbleStateProvider:
    status = '미지원: 퓨어 출력 닫힘'
    def sample(self):
        return RumbleSample()
    def close(self):
        pass

class MockRumbleProvider(RumbleStateProvider):
    """테스트 전용. GUI/실제 제공자에 자동으로 연결하지 않는다."""
    def __init__(self):
        self.value = RumbleSample()
    def sample(self):
        return self.value

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
        self.sos = [butter(2, f, fs=RATE, output='sos') for f in (120, 600, 2500)]
        self.zi = [np.zeros((len(s), 2, 2)) for s in self.sos]
        self.bg = np.full(4, 1e-8)
        self.mean = np.zeros(4)
        self.dev = np.full(4, .01)
        self.previous = np.zeros(4)
        self.gain = np.ones(4)
        self.pure_gain = 0.
        self.until = -1e9
        self.age = 0.
        self.last_mode = 'normal'
        self.slow_energy = np.full(4, 1e-8)
        self.fast_energy = np.full(4, 1e-8)
        self.hold = np.zeros(4)
        self.learn_pause = np.zeros(4)
        self.last_background = True
        self.initialized = False
        self.event_cooldown = np.zeros(4)
        self.was_event = np.zeros(4,dtype=bool)
        self._envelope_size = None
        self._slow_times = np.array([.045,.025,.020,.015])
        self._capacity = BLOCK
        self._bands = np.empty((4, self._capacity, 2), dtype=np.float32)
        self._ramp = np.empty((4, self._capacity), dtype=np.float64)
        self._weighted = np.empty((self._capacity, 2), dtype=np.float64)
        self._y = np.empty((self._capacity, 2), dtype=np.float64)
        self._positions = np.arange(1, self._capacity + 1, dtype=np.float64)

    def _ensure_capacity(self, n):
        if n <= self._capacity:
            return
        self._capacity = max(n, self._capacity * 2)
        self._bands = np.empty((4, self._capacity, 2), dtype=np.float32)
        self._ramp = np.empty((4, self._capacity), dtype=np.float64)
        self._weighted = np.empty((self._capacity, 2), dtype=np.float64)
        self._y = np.empty((self._capacity, 2), dtype=np.float64)
        self._positions = np.arange(1, self._capacity + 1, dtype=np.float64)

    def process(self, x, controls=Controls(), rumble=RumbleSample(), now=0.):
        x = select_stereo(x)
        if not np.isfinite(x).all():
            raise ValueError('비정상 오디오 값: 무음 실패 정책 필요')
        n = len(x)
        if not n:
            return x
        self._ensure_capacity(n)
        dt = n / RATE
        lows = []
        for k, sos in enumerate(self.sos):
            low, self.zi[k] = sosfilt(sos, x, axis=0, zi=self.zi[k])
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
        if self.age == 0:
            self.fast_energy = energy.copy()
            self.slow_energy = energy.copy()
            self.bg = np.maximum(energy, 1e-10)
        old_slow = self.slow_energy.copy()
        self.fast_energy += fast_a*(energy-self.fast_energy)
        self.slow_energy += slow_a*(energy-self.slow_energy)
        # Relative thresholds follow game volume; an absolute floor only stops
        # digital silence and quantization noise from opening protection.
        floor = np.maximum(1e-10, self.bg*.015)
        onset_ratio = self.fast_energy / np.maximum(old_slow, floor)
        background_ratio = self.slow_energy / np.maximum(self.bg, floor)
        contrast = np.clip((background_ratio-1.25)/3., 0, 1)
        onset = np.clip((onset_ratio-1.8)/2.2, 0, 1)
        onset *= np.clip((self.fast_energy-floor)/(floor*8+1e-12),0,1)
        event = (onset>.2) & (background_ratio>1.6)
        self.hold = np.maximum(0., self.hold-dt)
        self.hold[event] = .035
        # Freeze rising background briefly, never indefinitely. Repeated or
        # sustained energy resumes slow learning instead of latching the gate.
        self.learn_pause = np.maximum(0., self.learn_pause-dt)
        self.event_cooldown = np.maximum(0.,self.event_cooldown-dt)
        new_event = event & ~self.was_event & (self.event_cooldown<=0)
        self.learn_pause[new_event] = .080
        self.event_cooldown[new_event] = .25
        self.was_event = event.copy()
        rise_time=.045 if self.age<.20 else 1.8
        alpha = 1-np.exp(-dt/np.where(self.slow_energy>self.bg,rise_time,.22))
        alpha = np.where((self.learn_pause>0)&(self.slow_energy>self.bg),0.,alpha)
        self.bg += alpha*(self.slow_energy-self.bg)
        self.age += dt
        protection = np.maximum(contrast, np.where(self.hold>0,1.,onset))
        protection *= np.clip(controls.impact,0,1) if controls.transient else 0.
        strength = np.clip(controls.strength, 0, 1)
        target = 10**((-14*strength*(1-protection))/20)
        if not controls.background or controls.bypass:
            target[:] = 1
        if not self.initialized or controls.background and not self.last_background:
            # Start at the requested attenuation, not at unfiltered full gain.
            self.gain[:] = 10**(-14*strength/20) if controls.background and not controls.bypass else 1.
            self.initialized = True
        self.last_background = controls.background
        # Gains ramp sample-by-sample. No AGC or upward output boost.
        tau = np.where(target > self.gain, .003, .055)
        end = self.gain+(target-self.gain)*(1-np.exp(-dt/tau))
        ramp = self._ramp[:, :n]
        np.multiply((end-self.gain)[:, None], self._positions[:n], out=ramp)
        ramp /= n
        ramp += self.gain[:, None]
        y = self._y[:n]
        np.multiply(bands[0], ramp[0, :, None], out=y)
        for band in range(1, 4):
            np.multiply(bands[band], ramp[band, :, None], out=self._weighted[:n])
            np.add(y, self._weighted[:n], out=y)
        self.gain = end
        if controls.mode not in ('normal', 'pure'):
            raise ValueError('알 수 없는 모드')
        if self.last_mode != controls.mode:
            self.until = -1e9
        self.last_mode = controls.mode
        fresh = rumble.valid and 0 <= now-rumble.timestamp <= .075
        if fresh and max(rumble.left, rumble.right) >= .015:
            self.until = now+.025
        allowed = controls.mode == 'normal' or (fresh and now <= self.until)
        # Missing/stale information overrides hold; close over <= one 5ms block.
        gate_end = 1. if allowed else 0.
        if controls.mode == 'normal':
            self.pure_gain = gate_end
            np.clip(y, -1, 1, out=y)
            return y.astype(np.float32)
        g = np.linspace(self.pure_gain, gate_end, n+1)[1:]
        self.pure_gain = gate_end
        np.multiply(y, g[:, None], out=y)
        np.clip(y, -1, 1, out=y)
        return y.astype(np.float32)

class StreamingResampler:
    """Causal IIR antialias + stateful linear interpolation, prototype quality."""
    def __init__(self, source_rate, dest_rate=RATE):
        self.step = source_rate/dest_rate
        self.position = 0.
        self.tail = np.empty((0, 2))
        self.sos = butter(6, .42*min(source_rate, dest_rate), fs=source_rate, output='sos') if source_rate != dest_rate else None
        self.zi = np.zeros((len(self.sos), 2, 2)) if self.sos is not None else None
    def process(self, x):
        if self.sos is None:
            return x.copy()
        x, self.zi = sosfilt(self.sos, x, axis=0, zi=self.zi)
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
