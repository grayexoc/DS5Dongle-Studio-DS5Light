"""Coalesce Windows PnP arrivals/removals without opening HID in the callback."""
import ctypes as C
from threading import Lock


class NotifyFilter(C.Structure):
    _fields_=[('size',C.c_uint32),('flags',C.c_uint32),('kind',C.c_uint32),
              ('reserved',C.c_uint32),('data',C.c_uint16*200)]


class HidChanges:
    def __init__(self):
        self._lock=Lock()
        self._pending=False
        self._handle=C.c_void_p()
        self._callback=None
        self._unregister=None

    @property
    def available(self):
        return bool(self._handle.value)

    def start(self):
        try:
            hid=C.WinDLL('hid')
            cm=C.WinDLL('cfgmgr32')
            callback_type=C.WINFUNCTYPE(C.c_uint32,C.c_void_p,C.c_void_p,C.c_uint32,
                                       C.c_void_p,C.c_uint32)
            config=NotifyFilter()
            config.size=C.sizeof(config)
            hid.HidD_GetHidGuid.argtypes=[C.c_void_p]
            hid.HidD_GetHidGuid.restype=None
            hid.HidD_GetHidGuid(C.byref(config,NotifyFilter.data.offset))
            register=cm.CM_Register_Notification
            register.argtypes=[C.POINTER(NotifyFilter),C.c_void_p,callback_type,C.POINTER(C.c_void_p)]
            register.restype=C.c_uint32
            self._unregister=cm.CM_Unregister_Notification
            self._unregister.argtypes=[C.c_void_p]
            self._unregister.restype=C.c_uint32
            self._callback=callback_type(self._notify)
            if register(C.byref(config),None,self._callback,C.byref(self._handle)):
                self._handle=C.c_void_p()
        except (AttributeError,OSError):
            self._handle=C.c_void_p()
        return self.available

    def _notify(self,handle,context,action,data,size):
        if action not in (0,1) or not data or size<26:return 0
        path=C.string_at(data+24,(size-24)//2*2).decode('utf-16-le',errors='replace').lower()
        if any(key in path for key in ('vid_054c&pid_0ce6','vid_054c&pid_0df2','vid_1209&pid_0001')):
            with self._lock:self._pending=True
        return 0

    def take(self):
        with self._lock:
            pending=self._pending
            self._pending=False
            return pending

    def close(self):
        if self.available and self._unregister(self._handle)==0:
            self._handle=C.c_void_p()
            self._callback=None
