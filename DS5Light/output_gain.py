"""Final PCM output level: 100% is exact unity, changes slew over at most 30 ms."""

from studio_i18n import text as _ui_tr
import math

import numpy as np





class OutputGain:

    def __init__(self):

        self.current=1.0

        self.limited_samples=0

        self._zero=None

        self.capacity=480

        self.positions=np.arange(1,self.capacity+1,dtype=np.float32)

        self._work=None
        self._slew_work=None

        self._pcm=None



    def process(self,data,target):

        if type(target) not in (int,float) or not math.isfinite(target) or not 0<=target<=1.5:

            raise ValueError(_ui_tr('진동 세기 범위 오류'))

        if target==self.current==1.0 or not data: return data

        if target==self.current==0.0:

            if len(data)%8:raise ValueError(_ui_tr('4채널 PCM 길이 오류'))

            if self._zero is None or len(self._zero)!=len(data):self._zero=bytes(len(data))

            return self._zero

        x=np.frombuffer(data,'<i2').reshape(-1,4)

        n=len(x)

        if n>self.capacity:

            self.capacity=n; self.positions=np.arange(1,n+1,dtype=np.float32)

        if self._work is None or len(self._work)<n:

            self._work=np.empty((self.capacity,4),dtype=np.float32)

            self._pcm=np.empty((self.capacity,4),dtype="<i2")

        y=self._work[:n];pcm=self._pcm[:n]

        if self.current==target: np.copyto(y,x)

        if self.current==target:

            # A settled level needs no per-sample slew array or maximum scan.

            np.multiply(y,np.float32(target),out=y)

            amplified=target>1

        else:

            if self._slew_work is None or len(self._slew_work)<n:
                self._slew_work=np.empty((self.capacity,4),dtype=np.float64)
            y=self._slew_work[:n]

            maximum_step=1.5/(48000*.03)

            steps=self.positions[:n]*maximum_step

            gains=self.current+np.clip(target-self.current,-steps,steps)

            self.current=float(gains[-1])

            if abs(self.current-target)<1e-6: self.current=float(target)

            np.copyto(y,x)
            np.multiply(y,gains[:,None],out=y)

            amplified=target>1 or np.max(gains)>1

        if amplified:

            self.limited_samples+=int(np.count_nonzero((y>32767)|(y<-32768)))

        np.rint(y,out=y);np.clip(y,-32768,32767,out=y)

        pcm[:]=y

        # Return owned bytes: the next block may reuse both scratch buffers.

        return pcm.tobytes()



    def reconnect(self):

        self.current=0.0

