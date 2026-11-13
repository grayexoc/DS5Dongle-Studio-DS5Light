"""Low-rate upstream-compatible Studio battery reads, independent of audio."""
from thread_start import start_thread
import queue
import threading
import time
from studio_slots import devices,run_device


class BatteryMonitor:
    NORMAL_INTERVAL=300
    LOW_INTERVAL=60
    RETRY_INTERVAL=15
    def __init__(self):
        self.results=queue.SimpleQueue()
        self.busy=False;self.closed=False;self.next_check=0.
        self.preferred=None;self.value=None;self.state='waiting';self.revision=0
        self.device=None
        self.generation=0;self.interval=self.NORMAL_INTERVAL

    def tick(self,paused=False,preferred=None):
        if self.closed:return
        if preferred!=self.preferred:
            self.preferred=preferred;self.next_check=0.;self.generation+=1
            self.state='waiting';self.value=None;self.interval=self.NORMAL_INTERVAL
            self.device=None
        try:packet=self.results.get_nowait()
        except queue.Empty:pass
        else:
            generation,state,value=packet[:3]
            device=packet[3] if len(packet)>3 else None
            self.busy=False
            if generation==self.generation:
                self.state,self.value=state,value;self.revision+=1
                self.device=device if state=='ready' and value is not None else None
                self.interval=(self.LOW_INTERVAL if value['percent']<=20 else self.NORMAL_INTERVAL) if state=='ready' and value is not None else self.RETRY_INTERVAL
                self.next_check=time.monotonic()+self.interval
        if paused or self.busy or time.monotonic()<self.next_check:return
        self.busy=True
        generation=self.generation
        def work():
            device=None
            try:
                rows=devices();paths=[item['path'] for item in rows]
                path=preferred if preferred in paths else paths[0] if preferred is None and len(paths)==1 else None
                if path is None:result=('multiple' if len(paths)>1 else 'disconnected',None)
                else:
                    data=run_device(path,action='read_battery')
                    result=('ready' if data is not None else 'no_data',data)
                    if data is not None:device=next(item for item in rows if item['path']==path)
            except Exception:result=('unavailable',None)
            self.results.put((generation,*result,device))
        try:start_thread(threading.Thread(target=work,name='DS5Light-battery-read',daemon=True))
        except Exception:self.results.put((generation,'unavailable',None,None))

    def close(self):
        self.closed=True
