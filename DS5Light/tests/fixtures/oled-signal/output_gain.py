"""Final PCM output level: 100% is exact unity, changes slew over at most 30 ms."""
import math
import numpy as np


class OutputGain:
    def __init__(self):
        self.current=1.0
        self.limited_samples=0
        self.capacity=480
        self.positions=np.arange(1,self.capacity+1,dtype=np.float32)

    def process(self,data,target):
        if type(target) not in (int,float) or not math.isfinite(target) or not 0<=target<=1.5:
            raise ValueError('진동 세기 범위 오류')
        if target==self.current==1.0 or not data: return data
        x=np.frombuffer(data,'<i2').reshape(-1,4)
        n=len(x)
        if n>self.capacity:
            self.capacity=n; self.positions=np.arange(1,n+1,dtype=np.float32)
        if self.current==target:
            # A settled level needs no per-sample slew array or maximum scan.
            y=x.astype(np.float32)*np.float32(target)
            amplified=target>1
        else:
            maximum_step=1.5/(48000*.03)
            steps=self.positions[:n]*maximum_step
            gains=self.current+np.clip(target-self.current,-steps,steps)
            self.current=float(gains[-1])
            if abs(self.current-target)<1e-6: self.current=float(target)
            y=x.astype(np.float32)*gains[:,None]
            amplified=target>1 or np.max(gains)>1
        if amplified:
            self.limited_samples+=int(np.count_nonzero((y>32767)|(y<-32768)))
        return np.clip(np.rint(y),-32768,32767).astype('<i2').tobytes()

    def reconnect(self):
        self.current=0.0
