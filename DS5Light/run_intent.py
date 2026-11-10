"""Explicit run intent: only an Auto Haptics OFF pause can auto-resume."""
class RunIntent:
    def __init__(self):self.requested=False;self.profile_paused=False;self.generation=0;self.route=None
    def request(self,route):
        self.requested=True;self.profile_paused=False;self.route=route;self.generation+=1
    def stop(self,reason='manual'):
        if reason=='profile_off' and self.requested:self.profile_paused=True
        else:self.requested=False;self.profile_paused=False;self.generation+=1
    def can_resume(self,route):return self.requested and self.profile_paused and self.route==route
