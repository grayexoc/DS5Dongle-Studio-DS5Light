"""Optional standard 5.1 routing before legacy first-two-channel extraction."""
from studio_i18n import text as _ui_tr
import numpy as np


class ChannelMixer:
    def __init__(self):
        self.rear = 0.
        self.lfe = 0.
        self.center = 0.
        self.gain = 1.
        self.soft_mix = None
        self._position_count=0
        self._capacity=0

    def process(self, data, channels, rate, rear=False, lfe=False, limiter='hard', center=False):
        if limiter not in ('hard', 'soft'):
            raise ValueError(_ui_tr('알 수 없는 합산 제한 방식'))
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
        if n>self._capacity:
            self._capacity=max(480,n)
            self._surrounds=np.empty((self._capacity,2),np.float64)
            self._mixed=np.empty((self._capacity,2),np.float64)
            self._term=np.empty((self._capacity,2),np.float64)
            self._result=np.empty((self._capacity,8),dtype='<i2')
            self._overload=np.empty(self._capacity,np.float64)
            self._required=np.empty(self._capacity,np.float64)
            self._steps=np.empty(self._capacity,np.float64)
            self._gains=np.empty(self._capacity,np.float64)
        if self._position_count!=n:
            self._positions=np.arange(1,n+1)
            self._float_positions=self._positions.astype(np.float64)
            self._position_count=n
        # 30 ms linear coefficient slew, independent of capture block length.
        def ramp(current, target, maximum):
            # Settled coefficients broadcast without allocating a per-frame ramp.
            if current == target:return target
            length = max(1, round(rate * .03))
            start = round(current / maximum * length)
            end = round(target / maximum * length)
            positions = start + np.sign(end-start)*self._positions
            values = np.clip(positions, min(start,end), max(start,end)) / length * maximum
            return values[:, None]
        r = ramp(self.rear, .5 if rear else 0., .5)
        f = ramp(self.lfe, .25 if lfe else 0., .25)
        c = ramp(self.center, 2**-.5 if center else 0., 2**-.5)
        self.center = float(c[-1,0]) if isinstance(c,np.ndarray) else c
        self.rear = float(r[-1,0]) if isinstance(r,np.ndarray) else r
        self.lfe = float(f[-1,0]) if isinstance(f,np.ndarray) else f
        # FL FR FC LFE surround-L surround-R. FC is optional, linked to both sides.
        # Front remains unity; only actual over-range sums trigger limiting.
        surrounds=self._surrounds[:n]
        mixed=self._mixed[:n]
        term=self._term[:n]
        np.copyto(surrounds,x[:,4:6])
        if channels==8:
            # Averaging avoids a 6 dB jump for duplicated sides/rears.
            np.add(surrounds,x[:,6:8],out=surrounds)
            np.multiply(surrounds,.5,out=surrounds)
        np.multiply(surrounds,r,out=term)
        np.add(x[:,:2],term,out=mixed)
        np.multiply(x[:,3:4],f,out=term)
        np.add(mixed,term,out=mixed)
        np.multiply(x[:,2:3],c,out=term)
        np.add(mixed,term,out=mixed)
        # Linked stereo peak gain: immediate attack, linear recovery to unity
        # (at most 50 ms). No lookahead, no added audio buffering.
        overload=self._overload[:n]
        required=self._required[:n]
        np.max(mixed,axis=1,out=overload)
        np.divide(overload,32767,out=overload)
        np.min(mixed,axis=1,out=required)
        np.negative(required,out=required)
        np.divide(required,32768,out=required)
        np.maximum(overload,required,out=overload)
        np.maximum(1.,overload,out=required)
        np.divide(1.,required,out=required)
        release_step = 1 / max(1, round(rate * .05))
        steps=self._steps[:n]
        np.multiply(release_step,self._float_positions,out=steps)
        # Vector form of gain[i] = min(required[i], gain[i-1] + release_step).
        gains=self._gains[:n]
        np.subtract(required,steps,out=gains)
        np.minimum.accumulate(gains,out=gains)
        np.minimum(gains,self.gain,out=gains)
        np.add(gains,steps,out=gains)
        self.gain = float(gains[-1])
        target = float(limiter == 'soft')
        if self.soft_mix is None:
            self.soft_mix = target
        # Crossfade limiting policies over 20 ms without reopening devices.
        step = 1 / max(1, round(rate * .02))
        start = self.soft_mix
        if start == target == 0:
            # The hard path does not need a parallel soft-limiter signal.
            np.clip(mixed,-32768,32767,out=mixed)
        elif start == target == 1:
            np.multiply(mixed,gains[:,None],out=mixed)
        else:
            blend = start + np.clip(target-start, -step*self._positions, step*self._positions)
            hard = np.clip(mixed, -32768, 32767)
            soft = mixed * gains[:, None]
            mixed = hard*(1-blend[:,None]) + soft*blend[:,None]
        self.soft_mix = float(np.clip(start + np.sign(target-start)*min(abs(target-start), step*n), 0, 1))
        result=self._result[:n,:channels]
        np.copyto(result,x)
        np.rint(mixed,out=mixed)
        np.clip(mixed,-32768,32767,out=mixed)
        result[:,:2]=mixed
        return result.tobytes()
