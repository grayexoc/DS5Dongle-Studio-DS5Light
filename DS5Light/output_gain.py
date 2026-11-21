"""Final PCM output level: 100% is exact unity, large changes slew over at most 60 ms."""

from studio_i18n import text as _ui_tr
import math

import numpy as np
from core import HAPTIC_GAIN_MAX





class OutputGain:

    def __init__(self):

        self.current=1.0

        self.limited_samples=0

        self._zero=None

        self.capacity=480

        self.positions=np.arange(1,self.capacity+1,dtype=np.float64)
        self._slew_target=None
        self._slew_start=1.0
        self._slew_frames=0

        self._work=None
        self._slew_work=None

        self._pcm=None



    def process(self,data,target, *, rear_peak=None):

        if type(target) not in (int,float) or not math.isfinite(target) or not 0<=target<=HAPTIC_GAIN_MAX:

            raise ValueError(_ui_tr('진동 세기 범위 오류'))

        if target==self.current:
            self._slew_target=None

        if not data or (rear_peak is None and target==self.current==1.0): return data

        if rear_peak is None and target==self.current==0.0:

            if len(data)%8:raise ValueError(_ui_tr('4채널 PCM 길이 오류'))

            if self._zero is None or len(self._zero)!=len(data):self._zero=bytes(len(data))

            return self._zero

        x=np.frombuffer(data,'<i2').reshape(-1,4)

        n=len(x)

        if n>self.capacity:

            self.capacity=n; self.positions=np.arange(1,n+1,dtype=np.float64)

        if self._work is None or len(self._work)<n:

            self._work=np.empty((self.capacity,4),dtype=np.float32)

            self._pcm=np.empty((self.capacity,4),dtype="<i2")

        y=self._work[:n];pcm=self._pcm[:n]

        if self.current==target: np.copyto(y,x)

        if self.current==target:

            # A settled level needs no per-sample slew array or maximum scan.

            gain_channels = y if rear_peak is None else y[:, 2:]
            np.multiply(gain_channels,np.float32(target),out=gain_channels)

            amplified=target>1

        else:

            if self._slew_work is None or len(self._slew_work)<n:
                self._slew_work=np.empty((self.capacity,4),dtype=np.float64)
            y=self._slew_work[:n]

            maximum_step=1.5/(48000*.03)

            if target!=self._slew_target:
                self._slew_target=target
                self._slew_start=self.current
                self._slew_frames=0
            # Derive the ramp from its original sample position so regrouping
            # 240- and 480-frame transport blocks cannot change PCM rounding.
            steps=(self.positions[:n]+self._slew_frames)*maximum_step
            gains=self._slew_start+np.clip(target-self._slew_start,-steps,steps)
            self._slew_frames+=n

            self.current=float(gains[-1])

            if abs(self.current-target)<1e-6: self.current=float(target)

            np.copyto(y,x)
            gain_channels = y if rear_peak is None else y[:, 2:]
            np.multiply(gain_channels,gains[:,None],out=gain_channels)

            amplified=target>1 or np.max(gains)>1

        if rear_peak is not None:
            rear = y[:, 2:]
            self.limited_samples += int(np.count_nonzero(rear > rear_peak))
            np.clip(rear, 0, rear_peak, out=rear)
        elif amplified:

            self.limited_samples+=int(np.count_nonzero((y>32767)|(y<-32768)))

        np.rint(y,out=y);np.clip(y,-32768,32767,out=y)

        pcm[:]=y

        # Return owned bytes: the next block may reuse both scratch buffers.

        return pcm.tobytes()



    def reconnect(self):

        self.current=0.0
        self._slew_target=None

