"""Small, positive-only rate correction for persistent process-capture backlog."""
import math
import numpy as np

AVERAGING_FRAMES = 12_000  # 250ms at 48kHz


class CaptureClock:
    def __init__(self):
        self.reset()

    def reset(self):
        self.phase = 0.
        self.active = False
        self.average_frames = None

    def plan(self, n, buffered, packet_frames):
        # Average over ~250ms of output samples so alternating packet depths
        # do not reset the decision. Keep a separate lower release threshold.
        low = max(n, packet_frames)
        if self.average_frames is None:
            self.average_frames = min(buffered, low)
        self.average_frames += (buffered-self.average_frames)*n/(AVERAGING_FRAMES+n)
        if self.average_frames <= low+n/8:
            self.active = False
        elif self.average_frames >= low+.75*n:
            self.active = True
        if self.active and buffered > n:
            step = 1.001
            advance = self.phase+n*step
            consumed = math.floor(advance+1e-9)
            phase = max(0., advance-consumed)
            last_position = self.phase+(n-1)*step
            needed = max(consumed, math.ceil(last_position)+1)
            if buffered >= needed:
                return consumed, needed, self.phase+np.arange(n)*step, phase
        # Settle the fractional offset without waiting for another packet.
        if self.phase:
            return n, n, np.linspace(self.phase, n-1, n), 0.
        return None

    def render(self, data, channels, plan):
        _, _, positions, phase = plan
        samples = np.frombuffer(data, dtype='<i2').reshape(-1, channels)
        left = positions.astype(np.intp)
        weight = (positions-left)[:, None]
        right = np.minimum(left+1, len(samples)-1)
        output = np.rint(samples[left]*(1.-weight)+samples[right]*weight).astype('<i2')
        self.phase = phase
        return output.tobytes()
