"""Read only current profile: no full slot scan, no normal HID enumeration."""
from thread_start import start_thread
from studio_i18n import text as _ui_tr
import queue,threading,time
from studio_slots import StudioClient,_DEVICE_LOCK,devices
from device_binding import resolve_hid
from studio_profile_events import ProfileEvents


def read_current(identity,previous=None,full=False):
    import hid
    if not _DEVICE_LOCK.acquire(blocking=False):return None
    try:
        target=None;device=None
        try:
            device=hid.device();device.open_path(identity.hid_path)
        except OSError:
            if device is not None:device.close();device=None
            rows=devices()
            if identity.container_id and (not identity.serial or not any(row.get('serial_number')==identity.serial for row in rows)):
                from windows_device_identity import hid_container
                rows=[dict(row,container_id=row.get('container_id') or hid_container(row['path'])) for row in rows]
            target=resolve_hid(rows,identity.hid_path,identity.serial,identity.container_id)
            if target is None:raise RuntimeError(_ui_tr('선택한 Pico 재연결 대기'))
            device=hid.device()
            try:device.open_path(target['path'])
            except Exception:
                device.close();raise
        try:
            client=StudioClient(device)
            header=client.profile(include_mute=True)
            old={k:previous.get(k) for k in ('index','name','edited')} if previous else None
            stamp={k:header[k] for k in ('index','name','edited')}
            checked=full or stamp!=old or previous.get('auto_haptics_enable') not in (0,1,2)
            profile=client.profile_state() if checked else dict(header,auto_haptics_enable=previous['auto_haptics_enable'])
            if stamp == {k:profile[k] for k in stamp} and 'mute_macro' in header:
                profile['mute_macro'] = header['mute_macro']
            return dict(path=target['path'] if target else identity.hid_path,row=target,profile=profile,full=checked)
        finally:device.close()
    finally:_DEVICE_LOCK.release()

class ProfileWatch:
    INTERVAL=3.
    MODE_INTERVAL=10.
    def __init__(self):
        self.events=ProfileEvents()
        self.results=queue.SimpleQueue();self.busy=False;self.closed=False;self.key=None;self.generation=0
        self.next_check=0.;self.next_full=0.;self.profile=None;self.failures=0;self.was_paused=False
    def tick(self,binding,enabled,token,seed=None,paused=False):
        now=time.monotonic();identity=binding.snapshot();key=(token,identity.serial,identity.hid_path) if enabled else None
        if enabled:self.events.tick(identity)
        else:
            self.events.stop.set();self.events.key=None
        if key!=self.key or paused!=self.was_paused:
            rebound=bool(key and self.key and key[:2]==self.key[:2] and key[2]!=self.key[2])
            self.key=key;self.was_paused=paused;self.generation+=1
            self.next_check=now+self.INTERVAL;self.next_full=now+self.MODE_INTERVAL
            if rebound:self.next_check=self.next_full=now
            self.profile=dict(seed) if seed else None;self.failures=0
        result=None
        try:generation,data,error=self.results.get_nowait()
        except queue.Empty:pass
        else:
            self.busy=False
            if generation==self.generation and key is not None and not paused:
                if data:
                    self.profile=data['profile'];self.failures=0;result=data
                    if data['full']:self.next_full=now+self.MODE_INTERVAL
                elif error:
                    self.failures+=1
                delay=.2 if not data and not error else min(12.,self.INTERVAL*max(1,self.failures))
                self.next_check=now+delay
        if self.events.changed:self.next_check=now;self.next_full=now
        if (self.closed or key is None or paused or self.busy or now<self.next_check or not identity.hid_path):return result
        self.events.changed=False
        generation=self.generation;previous=dict(self.profile) if self.profile else None;full=now>=self.next_full
        self.busy=True;self.next_check=now+self.INTERVAL
        def work():
            try:self.results.put((generation,read_current(identity,previous,full),None))
            except Exception as exc:self.results.put((generation,None,str(exc)))
        start_thread(threading.Thread(target=work,name='DS5Light-profile-watch',daemon=True))
        return result
    def close(self):self.closed=True;self.generation+=1;self.events.close()
