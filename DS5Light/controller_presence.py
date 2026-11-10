"""Symptom-triggered USB checks, separate from the audio processing thread."""
import queue
import threading
import time
from studio_slots import devices


class ControllerPresence:
    INTERVAL=2.
    STALL_SECONDS=2.
    MAX_UNKNOWN=3

    def __init__(self):
        self.results=queue.SimpleQueue();self.busy=False;self.closed=False
        self.engine=None;self.path=None;self.serial=None;self.next_check=0.
        self.misses=0;self.disconnected=False
        self.generation=0;self.active=False;self.unknown=0
        self.started_at=0.;self.last_phase=None;self.last_errors=0;self.stalled=False

    def tick(self,engine,path,paused=False,serial=None,binding=None):
        if self.closed:return
        now=time.monotonic()
        if engine is not self.engine or (engine is not None and path!=self.path):
            self.engine=engine;self.path=path;self.serial=serial
            self.generation+=1
            self.next_check=0.;self.misses=0;self.disconnected=False
            self.active=False;self.unknown=0;self.started_at=now
            self.last_phase=None;self.last_errors=0;self.stalled=False
        elif serial:
            self.serial=serial
        try:
            item=self.results.get_nowait();generation,present,serial=item[:3]
            if len(item)>3 and generation==self.generation and item[3] is not None and binding is not None:binding.bind_hid(item[3])
        except queue.Empty:pass
        else:
            self.busy=False
            if generation==self.generation:
                if present is True:
                    self.misses=0;self.disconnected=False;self.unknown=0
                    self.active=False
                    if serial:self.serial=serial
                elif present is False:
                    self.unknown=0;self.misses+=1
                    self.disconnected=self.misses>=2
                    # Confirm absence, then watch recovery only for this incident.
                    self.active=True
                else:
                    # Enumeration failure is not proof of device removal.
                    self.misses=0;self.unknown+=1
                    self.active=self.unknown<self.MAX_UNKNOWN
        if engine is None:
            self.disconnected=False;self.active=False;return
        # Read cheap counters only; silence still produces successful writes.
        phase=engine.phase
        errors=engine.errors
        last_write=engine.last_block_time
        stalled=now-(last_write if last_write is not None else self.started_at)>=self.STALL_SECONDS
        triggered=((phase in ('waiting','error') and phase!=self.last_phase)
                   or errors>self.last_errors or (stalled and not self.stalled))
        if triggered:
            self.active=True;self.unknown=0
        self.last_phase=phase;self.last_errors=errors;self.stalled=stalled
        if (not path or paused or engine.stop_event.is_set() or not self.active
                or self.busy or now<self.next_check):return
        self.next_check=now+min(12.,self.INTERVAL*2**max(0,self.misses-1));self.busy=True
        serial=self.serial;generation=self.generation
        def work():
            try:
                candidates=devices()
                from device_binding import resolve_hid
                target=binding.resolve_hid(candidates) if binding is not None else resolve_hid(candidates,path,serial)
                result=(target is not None,target.get('serial_number') if target else serial,target)
            except Exception:
                result=(None,serial)
            self.results.put((generation,*result))
        threading.Thread(target=work,name='DS5Light-controller-presence',daemon=True).start()

    def close(self):
        self.closed=True


class IdleControllerPresence:
    """Eight-second active-HID check, armed only by a verified connection."""
    INTERVAL=8.
    def __init__(self):
        self.results=queue.SimpleQueue();self.busy=False;self.closed=False
        self.armed=False;self.absent=False;self.generation=0;self.next_check=0.
    def arm(self):
        self.generation+=1;self.armed=True;self.absent=False
        self.next_check=time.monotonic()+self.INTERVAL
    def tick(self,binding,enabled=False):
        if self.closed:return None
        now=time.monotonic();result=None
        try:generation,present,row=self.results.get_nowait()
        except queue.Empty:pass
        else:
            self.busy=False
            if generation==self.generation and enabled and self.armed:
                self.next_check=now+self.INTERVAL
                if present is False:
                    self.armed=False;self.absent=True;result=False
                elif present is True:
                    if row is not None:binding.bind_hid(row)
                    result=True
        if not enabled:
            self.next_check=now+self.INTERVAL
            return None
        if not self.armed or self.busy or now<self.next_check:return result
        if binding.snapshot().hid_path is None:return result
        self.busy=True;self.next_check=now+self.INTERVAL;generation=self.generation
        def work():
            from studio_slots import _DEVICE_LOCK
            # Skip concurrent Studio writes/reads instead of waiting on them.
            if not _DEVICE_LOCK.acquire(blocking=False):
                self.results.put((generation,None,None));return
            try:
                # This firmware hides the active controller PID on BT loss,
                # or switches to its idle PID. Cached battery/RSSI is not proof.
                row=binding.resolve_hid(devices())
                value=(row is not None,row)
            except Exception:value=(None,None)
            finally:_DEVICE_LOCK.release()
            self.results.put((generation,*value))
        threading.Thread(target=work,name='DS5Light-idle-presence',daemon=True).start()
        return result
    def close(self):self.closed=True;self.generation+=1
