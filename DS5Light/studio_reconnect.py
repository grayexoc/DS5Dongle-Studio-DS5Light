"""Bounded read-only recovery after a macro apply/flash transaction."""
from studio_i18n import text as _ui_tr
import time
from studio_slots import devices,_DEVICE_LOCK
from studio_snapshot import snapshot
from studio_settings_protocol import SettingsClient
from device_binding import resolve_hid


def capture_reconnect_binding(rows,path):
    from device_binding import DeviceBinding
    row=next((row for row in rows if row['path']==path),None)
    if row is None:return None
    binding=DeviceBinding()
    binding.bind_hid(row)
    return binding


def wait_for_macros(path,serial,cancel,timeout=30,*,edge_binding=None,serial_hidden=None,
                    usb_mode_binding=None,usb_mode=None,device_binding=None,recovery_read=None):
    """Reopen only the selected Pico; never repeat apply/flash/reset commands."""
    import hid
    deadline=time.monotonic()+timeout
    attempt=0;last_error=None
    while time.monotonic()<deadline:
        delay=(.8,1.2,2.,3.)[min(attempt,3)]
        if cancel.wait(min(delay,max(0.,deadline-time.monotonic()))):
            raise RuntimeError(_ui_tr('Studio 재연결 확인 취소됨'))
        if time.monotonic()>=deadline:break
        attempt+=1
        try:
            rows=devices()
            if edge_binding is not None:
                target=edge_binding.resolve_edge_reconnect(rows,not serial_hidden)
            elif usb_mode_binding is not None:
                vendor=0x1209 if usb_mode==1 else 0x054c
                target=usb_mode_binding.resolve_hid(row for row in rows if row.get('vendor_id')==vendor)
            elif device_binding is not None:
                target=device_binding.resolve_hid(rows,allow_mode_change=False)
            else:
                target=resolve_hid(rows,path,serial)
            if target is None:continue
            result=snapshot(target['path'],cancel.is_set,deadline=deadline)
            if time.monotonic()>=deadline:break
            if result.get('choose') or result.get('path')!=target['path']:continue
            if result.get('cfg') not in (19,20,21,22) or not result.get('profile'):
                raise RuntimeError(_ui_tr('Studio 설정/프로필 응답을 확인하지 못했습니다.'))
            while not _DEVICE_LOCK.acquire(timeout=.1):
                if cancel.is_set():raise RuntimeError(_ui_tr('Studio 재연결 확인 취소됨'))
                if time.monotonic()>=deadline:raise TimeoutError(_ui_tr('재연결 조회 대기 시간 초과'))
            device=None
            try:
                device=hid.device();device.open_path(target['path'])
                client=SettingsClient(device,cancel=cancel.is_set)
                client.deadline=min(deadline,time.monotonic()+6)
                before=client.profile(include_revision=True)
                macros=client.read_macros()
                after=client.profile(include_revision=True)
                expected={k:result['profile'][k] for k in ('index','name','edited')}
                if 'config_token' in result['profile']:expected['config_token']=result['profile']['config_token']
                if before!=after or after!=expected:
                    raise RuntimeError(_ui_tr('재연결 조회 중 프로필이 변경되었습니다.'))
                client.check_cancel()
                result['macros']=macros
                if recovery_read is not None:result['recovery']=recovery_read(client,result)
                return result
            finally:
                try:
                    if device is not None:device.close()
                finally:_DEVICE_LOCK.release()
        except Exception as exc:
            if cancel.is_set():raise RuntimeError(_ui_tr('Studio 재연결 확인 취소됨')) from exc
            last_error=exc
    message=_ui_tr('Pico 재연결 확인 시간 초과 · 연결 후 새로 고침을 눌러 주세요.')
    if last_error:message+=' '+str(last_error)
    raise TimeoutError(message)
