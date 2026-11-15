"""Read-only initial discovery and bounded slot history in existing preferences."""
import time
from studio_slots import Slot, devices, _DEVICE_LOCK


def clean_slot_history(value):
    # Optional history must never make the user's actual preferences unreadable.
    if not isinstance(value,list) or len(value)>8:return []
    result=[];serials=set()
    for record in value:
        if not isinstance(record,dict):return []
        serial=record.get('serial');slots=record.get('slots')
        if not isinstance(serial,str) or not serial.strip() or len(serial)>256 or serial in serials:return []
        if not isinstance(slots,list) or not slots or len(slots)>32:return []
        indices=set();rows=[]
        for slot in slots:
            if not isinstance(slot,dict):return []
            index,state,name=slot.get('index'),slot.get('state'),slot.get('name','')
            if type(index)is not int or not 0<=index<32 or index in indices or state not in ('saved','empty'):return []
            if not isinstance(name,str) or len(name)>128:return []
            indices.add(index);rows.append(dict(index=index,state=state,name=name))
        serials.add(serial);result.append(dict(serial=serial,slots=sorted(rows,key=lambda s:s['index'])))
    return result


def initial_profile(binding,cancel,deadline):
    import hid
    from studio_settings_protocol import SettingsClient
    if cancel() or time.monotonic()>=deadline:return None
    rows=devices();target=binding.resolve_hid(rows,allow_unique=True)
    if target is None or cancel() or time.monotonic()>=deadline:return None
    if not _DEVICE_LOCK.acquire(blocking=False):return None
    device=None
    try:
        device=hid.device();device.open_path(target['path'])
        client=SettingsClient(device,cancel=cancel)
        client.deadline=min(deadline,time.monotonic()+1.5)
        profile=client.profile_state()
        if profile.get('auto_haptics_enable') not in (0,1,2):return None
        # A duplicated serial is not safe for persistent list reuse.
        cache_ok=bool(target.get('serial_number')) and sum(r.get('serial_number')==target['serial_number'] for r in rows)==1
        return target,profile,cache_ok
    finally:
        try:
            if device is not None:device.close()
        finally:_DEVICE_LOCK.release()


class StartupDiscovery:
    def initial_read(self):
        self.startup_id=None
        if self.closed or self.app._closing or self.app._close_requested or self.initial_connected:return
        now=time.monotonic()
        if self.initial_deadline is None:self.initial_deadline=now+10
        if now>=self.initial_deadline:return
        if self.busy or self.app.studio_settings.busy:
            self.startup_id=self.app.root.after(200,self.initial_read);return
        self.task('startup',lambda:initial_profile(self.binding,self._cancel.is_set,self.initial_deadline),allow_running=True)

    def finish_initial_read(self,result):
        if not result:
            if not self.initial_connected and time.monotonic()<self.initial_deadline:
                self.startup_id=self.app.root.after(600,self.initial_read)
            return None
        device,profile,reuse=result
        slots=self.cached_slots(device) if reuse else []
        return [(device,slots,profile)],[]

    def cached_slots(self,device):
        serial=device.get('serial_number')
        if not serial:return []
        history=self.app.preference_store.data.get('studio_slots',[])
        record=next((r for r in history if r['serial']==serial),None)
        return [Slot(**s) for s in record['slots']] if record else []

    def remember_slots(self,device,slots):
        store=getattr(self.app,'preference_store',None)
        serial=device.get('serial_number')
        if store is None or not serial or not slots or any(s.state not in ('saved','empty') for s in slots):return
        record=dict(serial=serial,slots=[dict(index=s.index,state=s.state,name=s.name) for s in slots])
        history=[record]+[r for r in store.data.get('studio_slots',[]) if r['serial']!=serial]
        store.data['studio_slots']=clean_slot_history(history[:8])
        self.app.schedule_preferences_save()

    def forget_slot_history(self,path):
        self.catalog_invalid=True
        store=getattr(self.app,'preference_store',None)
        if store is None:return
        serial=self.device_serials.get(path)
        if serial:
            store.data['studio_slots']=[r for r in store.data.get('studio_slots',[]) if r['serial']!=serial]
            self.app.schedule_preferences_save()
