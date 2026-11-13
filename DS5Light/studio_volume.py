"""One-shot Windows volume sync for the explicitly selected Studio device."""
import ctypes as C
from ctypes import wintypes as W
from studio_i18n import text as _ui_tr
import windows_audio as audio

VOLUME_IID=audio.GUID('5cdf2c82-841e-4546-9722-0cf74078229a')

def estimated_windows_percent(value):
    if type(value) is not int or not 0<=value<=127:raise ValueError('Volume must be 0..127')
    # Display estimate from user-observed points; never used to control volume.
    points=((0,0),(40,1),(80,9),(100,25),(110,41),(127,100))
    for (x0,y0),(x1,y1) in zip(points,points[1:]):
        if value<=x1:return y0+int((value-x0)*(y1-y0)/(x1-x0)+.5)

def volume_db(value):
    if type(value) is not int or not 0<=value<=127:raise ValueError('Volume must be 0..127')
    # Inverse of the Studio USB speaker_level_from_usb mapping, not a scalar %.
    return (value*25600+63)//127/256-100

def select_endpoint(identity,endpoints):
    from windows_device_identity import usb_parent_id
    if identity.expected_edge_serial is not None:raise OSError(_ui_tr('Windows 음량 동기화 실패 · Pico 재연결 후 다시 적용하세요.'))
    matches=[]
    for row in endpoints:
        if row.get('state',1)!=1:continue
        parent=row.get('usb_parent_id') or (usb_parent_id(row['id'],endpoint=True) if identity.usb_parent_id else None)
        if parent and identity.usb_parent_id and parent!=identity.usb_parent_id:continue
        container=row.get('container_id')
        if parent and parent==identity.usb_parent_id:
            matches.append(row);continue
        if container and identity.container_id and container not in (identity.container_id,identity.confirmed_container_id):continue
        if (container and container==identity.container_id) or row['id']==identity.endpoint_id:matches.append(row)
    if len(matches)!=1:raise OSError(_ui_tr('Windows 음량 동기화 실패 · 같은 Pico의 출력 장치를 확인하세요.'))
    return matches[0]['id']

def set_endpoint_volume(endpoint_id,value):
    db=volume_db(value)
    ole=C.WinDLL('ole32')
    ole.CoInitializeEx.argtypes=[C.c_void_p,W.DWORD];ole.CoInitializeEx.restype=C.c_long
    ole.CoCreateInstance.argtypes=[C.POINTER(audio.GUID),C.c_void_p,W.DWORD,C.POINTER(audio.GUID),C.POINTER(C.c_void_p)]
    ole.CoCreateInstance.restype=C.c_long
    initialized=ole.CoInitializeEx(None,0)
    if initialized<0 and initialized&0xffffffff!=0x80010106:raise OSError('Core Audio initialization failed')
    enumerator=C.c_void_p();endpoint=C.c_void_p();volume=C.c_void_p()
    try:
        hr=ole.CoCreateInstance(C.byref(audio.ENUMERATOR_CLASS),None,1,C.byref(audio.ENUMERATOR_IID),C.byref(enumerator))
        if hr<0:raise OSError(f'Core Audio 0x{hr&0xffffffff:08x}')
        audio._call(enumerator,5,(W.LPCWSTR,C.POINTER(C.c_void_p)),endpoint_id,C.byref(endpoint))
        audio._call(endpoint,3,(C.POINTER(audio.GUID),W.DWORD,C.c_void_p,C.POINTER(C.c_void_p)),C.byref(VOLUME_IID),23,None,C.byref(volume))
        low=C.c_float();high=C.c_float();step=C.c_float()
        audio._call(volume,20,(C.POINTER(C.c_float),)*3,C.byref(low),C.byref(high),C.byref(step))
        if not low.value<=db<=high.value:raise OSError(_ui_tr('Windows 출력 장치의 음량 범위가 다릅니다.'))
        audio._call(volume,6,(C.c_float,C.c_void_p),db,None)
    finally:
        audio._release(volume);audio._release(endpoint);audio._release(enumerator)
        if initialized>=0:ole.CoUninitialize()

def sync_speaker_volume(path,binding,rows,value):
    identity=binding.snapshot()
    bound=identity.hid_path==path
    if not bound:
        from device_binding import DeviceBinding
        selected=next((row for row in rows if row['path']==path),None)
        if selected is None:raise OSError(_ui_tr('Windows 음량 동기화 실패 · 같은 Pico의 출력 장치를 확인하세요.'))
        identity=DeviceBinding().bind_hid(selected)
    inventory=audio.snapshot(include_sessions=False)
    endpoint=select_endpoint(identity,inventory['endpoints'])
    if bound and binding.snapshot()!=identity:
        raise OSError(_ui_tr('Windows 음량 동기화 실패 · 장치 연결이 변경되었습니다.'))
    set_endpoint_volume(endpoint,value)
