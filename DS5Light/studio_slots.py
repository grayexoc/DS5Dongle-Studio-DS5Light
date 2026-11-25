"""Studio slot protocol ported from DS5Light-OG; see vendor/LICENSE-Studio.txt.
Slot enumeration, profile activation and read-only battery status are exposed.
"""
from dataclasses import dataclass, field, replace
import secrets
import time
import threading
_DEVICE_LOCK=threading.Lock()


def profile_matches_revision(profile, revision):
    token = profile.get('config_token', '')
    return (isinstance(token, str) and len(token) == 16
            and type(revision) is int and 0 <= revision <= 0xffffffff
            and token[:8] == revision.to_bytes(4, 'little').hex())


@dataclass(frozen=True)
class Slot:
    index: int
    state: str
    name: str = ''
    catalog_revision: int | None = field(default=None, compare=False)

    def label(self):
        value = self.name if self.state == 'saved' else 'Empty' if self.state == 'empty' else 'Unavailable'
        return f'{self.index + 1:02d} · {value}'

class StudioClient:

    def __init__(self, device, sleep=time.sleep):
        self.device, self.sleep = (device, sleep)
        self.bulk_slot_catalog = False

    def check_cancel(self):
        """SettingsClient supplies the cancellation/deadline policy."""
        pass

    def request(self, command, index, tries=30):
        if command not in (10, 9) or not 0 <= index < 32:
            raise ValueError('Invalid slot command')
        packet = bytes([128, 102, command, index]) + bytes(60)
        self.check_cancel()
        if self.device.send_feature_report(packet) != 64:
            raise RuntimeError('Studio HID write failed')
        for _ in range(tries):
            self.check_cancel()
            self.sleep(0.06)
            self.check_cancel()
            try:
                raw = bytes(self.device.get_feature_report(132, 64))
            except OSError:
                continue
            self.check_cancel()
            if len(raw) < 7 or raw[:3] != bytes([132, 102, command]):
                continue
            r = raw[1:]
            if r[2] == 254 or r[3] != index:
                continue
            return r
        raise TimeoutError('Studio reply timeout; close the portal and refresh. Activation outcome may be unknown.')

    def metadata(self, command, payload=b''):
        if command not in (103, 5):
            raise ValueError('Invalid metadata command')
        self.check_cancel()
        packet=bytes([128,102,command])+payload
        if self.device.send_feature_report(packet.ljust(64,b'\0')) != 64:
            raise RuntimeError('Studio HID read request failed')
        for _ in range(10):
            self.check_cancel()
            self.sleep(0.06)
            self.check_cancel()
            try:
                raw = bytes(self.device.get_feature_report(129, 64))
            except OSError:
                continue
            self.check_cancel()
            if len(raw) >= 22 and raw[:3] == bytes([129, 102, command]):
                if payload and raw[30:34]==b'REV1' and raw[42:46]!=payload[2:]:continue
                return raw
        raise TimeoutError('Studio metadata unavailable')

    def profile(self, include_mute=False, include_state=False, *, include_revision=False):
        if include_revision:
            tag=(secrets.randbelow(0xffffffff)+1).to_bytes(4,'little')
            raw=self.metadata(103,b'R1'+tag)
        else:raw=self.metadata(103)
        if raw[3] != 0 or raw[5] not in (0, 1):
            raise RuntimeError('Invalid active profile response')
        profile = dict(index=None if raw[4] == 255 else raw[4], edited=bool(raw[5]), name=raw[6:22].decode('utf-8', errors='replace').rstrip('\x00').strip())
        if include_mute and len(raw) > 22 and raw[22] in (1, 2):
            profile['mute_macro'] = raw[22] == 2
        if include_state and len(raw) >= 30 and raw[23:27] == b'SLP2':
            mode, mix_level, dsp_source = raw[27:30]
            if mode in (0,1,2) and mix_level <= 100 and dsp_source in (0,1):
                profile['auto_haptics_enable'] = mode
                if mode == 1:
                    profile.update(mix_native_level=mix_level, ah_dsp_source=dsp_source)
                elif mode == 2:
                    profile['ah_dsp_source'] = dsp_source
        if include_state and len(raw) >= 47 and raw[46] & 0xFC == 0xA0:
            profile.update(auto_mute_mix=bool(raw[46] & 1), auto_mute_replace=bool(raw[46] & 2))
        if include_revision and len(raw)>=46 and raw[30:34]==b'REV1':
            profile['config_token']=raw[34:42].hex()
        if include_revision and len(raw)>=55 and raw[47:51]==b'SLT1':
            profile['catalog_revision']=int.from_bytes(raw[51:55],'little')
        return profile

    def profile_state(self, header=None):
        # Read the active RAM configuration, not a merely highlighted saved slot.
        # Bracket the field read with metadata to reject a concurrent slot change.
        before=header if header is not None else self.profile(include_mute=True,include_state=True)
        for _ in range(2):
            if 'auto_haptics_enable' in before:return before
            packet=bytes([0x80,0x66,4,0x12])+bytes(60)
            self.check_cancel()
            if self.device.send_feature_report(packet)!=64:
                raise RuntimeError('Studio autohaptics read request failed')
            mode=None
            for _ in range(10):
                self.check_cancel()
                self.sleep(.06)
                self.check_cancel()
                try:raw=bytes(self.device.get_feature_report(0x81,64))
                except OSError:continue
                self.check_cancel()
                if len(raw)<5 or raw[:4]!=bytes([0x81,0x66,4,0x12]):continue
                if raw[4] not in (0,1,2):raise RuntimeError('Invalid Studio autohaptics mode')
                mode=raw[4];break
            if mode is None:raise TimeoutError('Studio autohaptics state unavailable')
            def optional_field(field, maximum):
                self.check_cancel()
                try:
                    if self.device.send_feature_report(bytes((0x80,0x66,4,field))+bytes(60))==64:
                        for _attempt in range(4):
                            self.sleep(.06);self.check_cancel()
                            try:raw=bytes(self.device.get_feature_report(0x81,64))
                            except OSError:continue
                            if len(raw)>=5 and raw[:4]==bytes((0x81,0x66,4,field)) and raw[4]<=maximum:
                                return raw[4]
                except OSError:pass
                return None
            mix_level=optional_field(0x55,100) if mode==1 else None
            dsp_source=optional_field(0x64,1) if mode==2 or mix_level else None
            after=self.profile(include_mute=True,include_state=True)
            if 'auto_haptics_enable' in after:return after
            if all(before[key]==after[key] for key in ('index','name','edited')):
                state=dict(after,auto_haptics_enable=mode)
                if mix_level is not None:state['mix_native_level']=mix_level
                if dsp_source is not None:state['ah_dsp_source']=dsp_source
                return state
            before=after
        raise RuntimeError('Studio profile changed during read; refresh again')

    def battery(self):
        # Same identity preflight and read-only field as the upstream port.
        self.info(0)
        packet=bytes([0x80,0x66,4,0x68])+bytes(60)
        self.check_cancel()
        if self.device.send_feature_report(packet)!=64:
            raise RuntimeError('Studio battery read request failed')
        for _ in range(10):
            self.check_cancel()
            self.sleep(.06)
            self.check_cancel()
            try:raw=bytes(self.device.get_feature_report(0x81,64))
            except OSError:continue
            self.check_cancel()
            if len(raw)<8 or raw[:4]!=bytes([0x81,0x66,4,0x68]):continue
            value=raw[4]
            if value==0:return None
            level,state=value&15,value>>4
            if level>10:raise RuntimeError('Invalid Studio battery level')
            return dict(percent=level*10,state=state)
        raise TimeoutError('Studio battery response unavailable')

    def info(self, index):
        r = self.request(10, index, 10)
        self.bulk_slot_catalog = len(r)>=26 and r[22:26]==b'SLT1'
        if r[2] != 0:
            return Slot(index, 'unavailable')
        if len(r) < 22 or r[4] not in (0, 1):
            raise RuntimeError('Invalid Studio slot response')
        if not r[4]:
            return Slot(index, 'empty')
        return Slot(index, 'saved', r[6:22].decode('utf-8', errors='replace').rstrip('\x00').strip())

    def slots(self):
        first=self.info(0)
        if not self.bulk_slot_catalog:
            return [first]+[self.info(i) for i in range(1,32)]
        for _ in range(2):
            rows=[];revision=None
            for start in range(0,32,3):
                page_token,page=self.catalog_page(start)
                if revision is not None and page_token!=revision:break
                revision=page_token
                rows.extend(page)
            if len(rows)==32:return [replace(slot,catalog_revision=revision) for slot in rows]
        raise RuntimeError('Studio slot catalog changed during refresh')

    def catalog_page(self, start):
        tag=secrets.token_bytes(3)
        packet=bytes((128,102,0x27,start))+tag+bytes(57)
        self.check_cancel()
        if self.device.send_feature_report(packet)!=64:
            raise OSError('Studio catalog request failed')
        for attempt in range(10):
            self.check_cancel()
            if attempt:self.sleep(.02)
            try:raw=bytes(self.device.get_feature_report(132,64))
            except OSError:continue
            if len(raw)!=64 or raw[:3]!=bytes((132,102,0x27)) or raw[4]!=start or raw[61:64]!=tag:
                continue
            count=min(3,32-start)
            if raw[3]!=0 or raw[5]!=count:raise RuntimeError('Studio catalog page unavailable')
            slots=[]
            for i in range(count):
                offset=10+17*i
                if raw[offset] not in (0,1):raise RuntimeError('Invalid Studio catalog page')
                name=raw[offset+1:offset+17].decode('utf-8',errors='replace').rstrip('\0').strip()
                slots.append(Slot(start+i,'saved' if raw[offset] else 'empty',name if raw[offset] else ''))
            return int.from_bytes(raw[6:10],'little'),slots
        raise TimeoutError('Studio catalog reply timeout')

    def activate(self, index):
        slot = self.info(index)
        if slot.state != 'saved':
            raise ValueError('Slot is empty or unavailable')
        r = self.request(9, index)
        if r[2] not in (0, 2):
            raise RuntimeError('Studio rejected slot activation')
        if r[4] not in (0, 1):
            raise RuntimeError('Invalid activation response')
        return dict(slot=slot, reconnect=bool(r[4]), deferred=r[2] == 2)

    def reconnect_usb(self):
        # Supported firmware command 0x03, not a Bluetooth disconnect/power-off.
        # It has no acknowledgement. Never retry this command: the subsequent
        # read-only enumeration decides whether the interface came back.
        self.check_cancel()
        if self.device.send_feature_report(bytes([0x80,0x66,3])+bytes(61))!=64:
            raise RuntimeError('Studio USB reconnect request failed')

def devices():
    import hid
    sony = [d for d in hid.enumerate(1356, 0) if d.get('product_id') in (3302, 3570) and d.get('usage_page') == 1 and d.get('usage') in (4, 5)]
    xinput = [d for d in hid.enumerate(0x1209, 1)
              if d.get('product_string') in ('Studio XInput Experiment', 'DualSense Wireless Controller', 'DualSense Edge Wireless Controller')
              and d.get('usage_page') == 0xff00 and d.get('usage') == 1]
    return sony + xinput
def run_device(path,index=None,action=None):
    import hid
    if action not in (None,'read_profile','read_profile_state','read_usb_mode','read_battery','reconnect_usb'):raise ValueError('Unsupported Studio operation')
    if not _DEVICE_LOCK.acquire(timeout=3):
        from studio_i18n import text
        raise TimeoutError(text('Studio 조회 대기 시간 초과'))
    try:
        device=hid.device()
        try:
            device.open_path(path)
            client=StudioClient(device)
            if action=='read_profile':return client.profile()
            if action=='read_profile_state':
                from studio_settings_protocol import SettingsClient
                client=SettingsClient(device)
                return dict(client.profile_state(),controller_ready=client.controller_ready())
            if action=='read_battery':return client.battery()
            if action=='read_usb_mode':
                from studio_fields import FIELDS
                from studio_settings_protocol import SettingsClient
                return SettingsClient(device).read_one(FIELDS['usb_gamepad_mode'])
            if action=='reconnect_usb':return client.reconnect_usb()
            return client.slots() if index is None else client.activate(index)
        finally:device.close()
    finally:_DEVICE_LOCK.release()
