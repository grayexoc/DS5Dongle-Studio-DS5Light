"""Read-only Windows container identity lookup, only on selection/recovery."""
import ctypes as C
from ctypes import wintypes as W
import os,uuid
from threading import Lock

CONTAINER_FMTID='8c7ed206-3f8a-4827-b3ab-ae9e1faefc6c'
class Key(C.Structure):
    _fields_=[('guid',C.c_ubyte*16),('pid',W.DWORD)]
    def __init__(self,guid,pid):
        super().__init__();C.memmove(C.addressof(self),uuid.UUID(guid).bytes_le,16);self.pid=pid

_cache={};_cache_lock=Lock()
def hid_container(path):
    with _cache_lock:
        if path in _cache:return _cache[path]
    if os.name!='nt' or not path:return None
    try:
        text=path.decode('utf-8') if isinstance(path,bytes) else path
        if not text.startswith('\\\\?\\'):return None
        cm=C.WinDLL('cfgmgr32')
        get_interface=cm.CM_Get_Device_Interface_PropertyW
        get_interface.argtypes=[W.LPCWSTR,C.POINTER(Key),C.POINTER(W.ULONG),C.c_void_p,C.POINTER(W.ULONG),W.ULONG]
        get_interface.restype=W.ULONG
        key=Key('78c34fc8-104a-4aca-9ea4-524d52996e57',256)
        kind=W.ULONG();buf=C.create_unicode_buffer(1024);size=W.ULONG(C.sizeof(buf))
        if get_interface(text,C.byref(key),C.byref(kind),buf,C.byref(size),0)!=0 or kind.value!=18:return None
        locate=cm.CM_Locate_DevNodeW;locate.argtypes=[C.POINTER(W.ULONG),W.LPWSTR,W.ULONG];locate.restype=W.ULONG
        node=W.ULONG()
        if locate(C.byref(node),buf,0)!=0:return None
        get_node=cm.CM_Get_DevNode_PropertyW
        get_node.argtypes=[W.ULONG,C.POINTER(Key),C.POINTER(W.ULONG),C.c_void_p,C.POINTER(W.ULONG),W.ULONG];get_node.restype=W.ULONG
        key=Key(CONTAINER_FMTID,2);guid=(C.c_ubyte*16)();size=W.ULONG(16)
        if get_node(node,C.byref(key),C.byref(kind),guid,C.byref(size),0)!=0 or kind.value!=13 or size.value!=16:return None
        value=str(uuid.UUID(bytes_le=bytes(guid)))
        if value=='00000000-0000-0000-0000-000000000000':return None
        with _cache_lock:
            if len(_cache)>=32:_cache.pop(next(iter(_cache)))
            _cache[path]=value
        return value
    except (OSError,ValueError,UnicodeError,AttributeError):return None


def _usb_ancestor(node, parent, instance):
    seen=set()
    for _ in range(12):
        if node is None or node in seen:return None
        seen.add(node)
        value=instance(node)
        if value:
            hardware=value.upper().split('\\')[0:2]
            if len(hardware)==2 and hardware[0]=='USB' and 'VID_' in hardware[1] and 'PID_' in hardware[1] and '&MI_' not in hardware[1]:
                return value.casefold()
        node=parent(node)
    return None


def usb_parent_id(path, endpoint=False):
    """Physical USB instance identity, not a port-derived substring or device name."""
    if os.name!='nt' or not path:return None
    key=('usb_parent',endpoint,path)
    with _cache_lock:
        if key in _cache:return _cache[key]
    try:
        cm=C.WinDLL('cfgmgr32')
        locate=cm.CM_Locate_DevNodeW
        locate.argtypes=[C.POINTER(W.ULONG),W.LPWSTR,W.ULONG];locate.restype=W.ULONG
        text=path.decode('utf-8') if isinstance(path,bytes) else str(path)
        if endpoint:
            text='SWD\\MMDEVAPI\\'+text
        else:
            if not text.startswith('\\\\?\\'):return None
            get=cm.CM_Get_Device_Interface_PropertyW
            get.argtypes=[W.LPCWSTR,C.POINTER(Key),C.POINTER(W.ULONG),C.c_void_p,C.POINTER(W.ULONG),W.ULONG];get.restype=W.ULONG
            prop=Key('78c34fc8-104a-4aca-9ea4-524d52996e57',256)
            kind=W.ULONG();buffer=C.create_unicode_buffer(1024);size=W.ULONG(C.sizeof(buffer))
            if get(text,C.byref(prop),C.byref(kind),buffer,C.byref(size),0) or kind.value!=18:return None
            text=buffer.value
        node=W.ULONG()
        if locate(C.byref(node),C.create_unicode_buffer(text),0):return None
        get_parent=cm.CM_Get_Parent;get_parent.argtypes=[C.POINTER(W.ULONG),W.ULONG,W.ULONG];get_parent.restype=W.ULONG
        get_id=cm.CM_Get_Device_IDW;get_id.argtypes=[W.ULONG,W.LPWSTR,W.ULONG,W.ULONG];get_id.restype=W.ULONG
        def parent(n):
            value=W.ULONG()
            return None if get_parent(C.byref(value),n,0) else value.value
        def instance(n):
            value=C.create_unicode_buffer(1024)
            return None if get_id(n,value,len(value),0) else value.value
        result=_usb_ancestor(node.value,parent,instance)
        if result:
            with _cache_lock:
                if len(_cache)>=32:_cache.pop(next(iter(_cache)))
                _cache[key]=result
        return result
    except (OSError,ValueError,UnicodeError,AttributeError):return None
