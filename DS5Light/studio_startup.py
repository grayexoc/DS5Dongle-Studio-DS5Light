"""Read-only discovery and bounded slot history in existing preferences."""
import time
from studio_slots import Slot, devices, _DEVICE_LOCK

NO_HID_CANDIDATE=object()


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
    rows=devices();identity=binding.snapshot()
    known=bool(identity.hid_path or identity.serial or identity.container_id or identity.usb_parent_id)
    target=binding.resolve_hid(rows,allow_unique=True)
    candidates=[target] if target is not None else ([] if known else rows)
    if not candidates:return NO_HID_CANDIDATE
    if cancel() or time.monotonic()>=deadline:return None
    if not _DEVICE_LOCK.acquire(blocking=False):return None
    try:
        verified=[]
        for row in candidates:
            if cancel() or time.monotonic()>=deadline:return None
            device=hid.device()
            try:
                device.open_path(row['path'])
                client=SettingsClient(device,cancel=cancel)
                client.deadline=min(deadline,time.monotonic()+1.5)
                profile=client.profile_state()
                if profile.get('auto_haptics_enable') not in (0,1,2):continue
                if client.deadline-time.monotonic()>=.5:
                    profile=dict(profile,controller_ready=client.controller_ready())
                serial=row.get('serial_number')
                cache_ok=bool(serial) and sum(r.get('serial_number')==serial for r in rows)==1
                verified.append((row,profile,cache_ok))
            except (OSError,RuntimeError,ValueError):
                if len(candidates)==1:raise
            finally:
                device.close()
        return verified[0] if len(verified)==1 and binding.snapshot()==identity else None
    finally:_DEVICE_LOCK.release()


class StartupDiscovery:
    LATE_DISCOVERY_INTERVAL_MS=30000
    initial_notification_pending=False
    initial_retry_empty=False

    def wake_discovery(self):
        if self.initial_connected or self.closed:return
        if self.startup_id is not None:self.app.root.after_cancel(self.startup_id)
        self.initial_notification_pending=True
        self.startup_id=self.app.root.after(150,self.initial_read)

    def initial_read(self):
        self.startup_id=None
        if self.closed or self.app._closing or self.app._close_requested or self.initial_connected:return
        now=time.monotonic()
        if self.initial_deadline is None:self.initial_deadline=now+10
        pending=self.initial_notification_pending
        late=not pending and now>=self.initial_deadline
        if late and getattr(self.app,'hid_events_available',False):return
        if self.busy or self.app.studio_settings.busy or getattr(getattr(self.app,'studio_power',None),'blocked',False):
            self.startup_id=self.app.root.after(self.LATE_DISCOVERY_INTERVAL_MS if late else 200,self.initial_read);return
        if pending:
            self.initial_notification_pending=False
            self.initial_retry_empty=True
            self.initial_deadline=now+5
        deadline=now+2 if late else self.initial_deadline
        self.task('startup',lambda:initial_profile(self.binding,self._cancel.is_set,deadline),allow_running=True)

    def finish_initial_read(self,result):
        absent=result is NO_HID_CANDIDATE
        if absent or not result:
            if not self.initial_connected:
                fast=(not absent or self.initial_retry_empty) and time.monotonic()<self.initial_deadline
                if not fast:self.initial_retry_empty=False
                if self.startup_id is None and (fast or not getattr(self.app,'hid_events_available',False)):
                    self.startup_id=self.app.root.after(600 if fast else self.LATE_DISCOVERY_INTERVAL_MS,self.initial_read)
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
