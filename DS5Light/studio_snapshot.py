"""One serialized, bounded read; version fields match the original portal."""
from studio_i18n import text as _ui_tr
import time
from studio_slots import devices,_DEVICE_LOCK
from studio_settings_protocol import SettingsClient
from device_binding import resolve_hid

def identity_fields(client):
    # The portal reads field 0 as u16, but config.h and bulk replies store u8.
    fields=[[n,key,typ,key,'number',[0,65535]] for n,key,typ in ((125,'fw_major','u8'),(126,'fw_minor','u8'),(127,'fw_patch','u8'),(0,'config_version','u8'))]
    values,missing=client.read_fields(fields)
    version=_ui_tr('미확인')
    if not any(key in missing for key in ('fw_major','fw_minor','fw_patch')):
        version='v'+'.'.join(str(values[k]) for k in ('fw_major','fw_minor','fw_patch'))
    # Firmware string includes fork/experimental versions; numeric fields may stay upstream.
    try:
        import re
        raw=client.metadata(5)
        text=raw[3:].split(b'\0',1)[0].decode('ascii').strip()
        if re.fullmatch(r'v?\d+(?:\.\d+){0,2}[A-Za-z0-9 ._+()/-]*',text):
            version=text if text.startswith('v') else 'v'+text
    except (AttributeError,OSError,TimeoutError,UnicodeError):
        pass
    return version,values.get('config_version')

def snapshot(preferred,cancel=lambda:False,binding=None,deadline=None):
    import hid
    # Lock contention at launch is not time spent querying this device.
    rows=devices()
    if deadline is not None and time.monotonic()>=deadline:raise TimeoutError(_ui_tr('Studio 조회 대기 시간 초과'))
    identity=binding.snapshot() if binding is not None else None
    known=identity is not None and (identity.hid_path is not None or identity.serial or identity.container_id)
    target=binding.resolve_hid(rows) if known else resolve_hid(rows,path=preferred,allow_unique=preferred is None)
    if target is None:return dict(rows=rows,choose=True)
    wait_deadline=min(time.monotonic()+3,deadline) if deadline is not None else time.monotonic()+3
    while not _DEVICE_LOCK.acquire(timeout=.1):
        if cancel():raise RuntimeError(_ui_tr('Studio 작업 취소됨'))
        if time.monotonic()>=wait_deadline:raise RuntimeError(_ui_tr('Studio 조회 대기 시간 초과 · 다른 작업이 끝난 뒤 새로 고침을 누르세요.'))
    device=None
    try:
        if deadline is not None and time.monotonic()>=deadline:raise TimeoutError(_ui_tr('Studio 조회 대기 시간 초과'))
        device=hid.device()
        device.open_path(target['path']);client=SettingsClient(device,cancel=cancel);client.deadline=min(time.monotonic()+8,deadline) if deadline is not None else time.monotonic()+8
        version,cfg=identity_fields(client)
        before=client.profile()
        values,unsupported=client.read_fields()
        after=client.profile()
        if before!=after:raise RuntimeError(_ui_tr('조회 중 프로필이 변경되었습니다. 새로 고침을 누르세요.'))
        profile=dict(after,auto_haptics_enable=values.get('auto_haptics_enable'),device_serial=target.get('serial_number'),device_row=target)
        client.check_cancel()
        standby=None
        if client.deadline-time.monotonic()>=1:
            try:standby=client.standby_mode()
            except (OSError,ValueError,TimeoutError):pass
        dock=None
        if client.deadline-time.monotonic()>=1:
            try:dock=client.dock_disconnect()
            except (OSError,ValueError,TimeoutError,AttributeError):pass
        return dict(rows=rows,dock=dock,path=target['path'],standby=standby,values=values,unsupported=unsupported,profile=profile,version=version,cfg=cfg)
    finally:
        try:
            if device is not None:device.close()
        finally:_DEVICE_LOCK.release()

def device_labels(rows,path,profile):
    result=[]
    for i,row in enumerate(rows):
        label=row.get('product_string','DualSense')+f' · {i+1:02d}'
        result.append(label)
    return result
