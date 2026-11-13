"""Optional event-only vendor collection; legacy gamepad input is never opened."""
import queue
import re
import threading
import time
from thread_start import start_thread


def decode(raw):
    raw=bytes(raw)
    if (len(raw)!=16 or raw[:6]!=b'\x8fSLP1\x01' or raw[10] not in (*range(32),255)
            or raw[11] not in (0,1) or raw[12] not in (0,1,2) or raw[13] not in (0,1)
            or any(raw[14:])):raise ValueError('Invalid Studio profile event')
    return int.from_bytes(raw[6:10],'little')


def same_device(row,identity):
    if row.get('usage_page')!=0xff00 or row.get('usage')!=0x52:return False
    if identity.edge_serial_present is False:
        if row.get('serial_number'):return False
    elif identity.serial:return row.get('serial_number')==identity.serial
    # Windows collection paths differ only by &colNN on the same HID interface.
    normalize=lambda path:re.sub(rb'&col[0-9a-f]{2}',b'',path.lower())
    return bool(identity.hid_path and normalize(row['path'])==normalize(identity.hid_path))


class ProfileEvents:
    def __init__(self):
        self.key=None;self.stop=threading.Event();self.results=queue.SimpleQueue()
        self.changed=False;self.healthy=False;self.retry_at=0.;self.closed=False
        self.missing=0
    def tick(self,identity):
        key=(identity.hid_path,identity.serial,identity.edge_serial_present)
        if self.closed:return
        if key!=self.key:
            self.stop.set();self.stop=threading.Event();self.key=key
            self.changed=False;self.healthy=False;self.retry_at=0.;self.missing=0
        while not self.results.empty():
            token,kind=self.results.get()
            if token is not self.stop:continue
            if kind=='ready':self.missing=0;self.healthy=True
            elif kind=='changed':self.changed=True
            elif kind=='missing':
                self.missing+=1
                if self.missing<3:self.retry_at=time.monotonic()+self.missing
            elif kind=='failed':self.healthy=False;self.retry_at=time.monotonic()+3
        if not identity.hid_path or time.monotonic()<self.retry_at:return
        self.retry_at=float('inf');token=self.stop
        def listen():
            import hid
            device=None
            try:
                rows=[r for r in hid.enumerate() if same_device(r,identity)]
                if len(rows)!=1:
                    self.results.put((token,'missing'))
                    return
                device=hid.device();device.open_path(rows[0]['path'])
                decode(device.get_feature_report(0x8f,16))
                last=None;now=time.monotonic();renew=now+30;ack_until=now+3
                while not token.is_set():
                    now=time.monotonic()
                    if ack_until is not None and now>=ack_until:
                        raise TimeoutError('Studio profile notification unavailable')
                    if now>=renew:
                        decode(device.get_feature_report(0x8f,16))
                        now=time.monotonic();renew=now+30;ack_until=now+3
                    raw=device.read(16,1000)
                    if not raw:continue
                    seq=decode(raw)
                    ack_until=None
                    if last is None:self.results.put((token,'ready'))
                    if seq!=last:self.results.put((token,'changed'));last=seq
            except Exception:self.results.put((token,'failed'))
            finally:
                if device is not None:device.close()
        start_thread(threading.Thread(target=listen,name='DS5Light-profile-events',daemon=True))
    def close(self):self.closed=True;self.stop.set()
