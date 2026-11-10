"""Bounded read-only recovery after a macro apply/flash transaction."""
from studio_i18n import text as _ui_tr
import time
from studio_slots import devices,_DEVICE_LOCK
from studio_snapshot import snapshot
from studio_settings_protocol import SettingsClient
from device_binding import resolve_hid


def wait_for_macros(path,serial,cancel,timeout=30):
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
                before=client.profile()
                macros=client.read_macros()
                after=client.profile()
                expected={k:result['profile'][k] for k in ('index','name','edited')}
                if before!=after or after!=expected:
                    raise RuntimeError(_ui_tr('재연결 조회 중 프로필이 변경되었습니다.'))
                client.check_cancel()
                result['macros']=macros
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
