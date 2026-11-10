"""No timers or measurements: bounded reconnect cadence only."""
class RetryCadence:
    def __init__(self):self.attempt=0
    def reset(self):self.attempt=0
    def next_delay(self,expected=False):
        sequence=(.2,.4,.8,1.2,2.) if expected else (.5,1.,2.,4.,8.,10.)
        result=sequence[min(self.attempt,len(sequence)-1)]
        self.attempt+=1
        return result
