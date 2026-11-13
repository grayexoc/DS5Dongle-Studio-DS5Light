"""Validated Studio settings wire protocol. All caller transactions share _DEVICE_LOCK."""
from studio_i18n import text as _ui_tr
import math
import struct
import secrets
import time
from studio_slots import StudioClient
from studio_fields import FIELDS
from studio_scope import EDITABLE,CONSTRUCTION,LIGHTBAR_FIELDS,RUMBLE_FIELDS,USB_MODE_FIELDS,RUMBLE_MODE_FIELDS,EDGE_SERIAL_FIELDS,OPTIONAL_FIELDS

FORMATS={'u8':'B','u16':'H','u32':'I','f32':'f'}
ENUM_FIELDS={'usb_gamepad_mode','controller_mode','polling_rate_mode','audio_buffer_length','disable_mic','disable_speaker','enable_wake'}
class PartialApplyError(RuntimeError):pass
class USBModeUnsupported(ValueError):pass
class RumbleModeUnsupported(ValueError):pass
class EdgeSerialUnsupported(ValueError):pass

EDGE_SERIAL_STORAGE_FIELD=[0xC8,*FIELDS['disable_usb_sn'][1:]]

class PolicySaveError(ValueError):
    def __init__(self, message, current):
        super().__init__(message)
        self.current = current

def encode(field,value):
    _,key,typ,_,kind,*opts=field
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value):raise ValueError(key+_ui_tr(': 숫자가 아닙니다.'))
    if typ!='f32' and int(value)!=value:raise ValueError(key+_ui_tr(': 정수만 입력하세요.'))
    if kind=='number' and not opts[0][0]<=value<=opts[0][1]:raise ValueError(key+_ui_tr(': 허용 범위를 벗어났습니다.'))
    if kind=='bool' and value not in (0,1):raise ValueError(key+_ui_tr(': 0 또는 1이어야 합니다.'))
    if key=='lightbar_rgb' and not 0<=value<=0xffffff:raise ValueError(_ui_tr('RGB 색상은 0x000000~0xFFFFFF 범위여야 합니다.'))
    if kind=='bits' and not 0<=value<(1<<len(opts[0])):raise ValueError(key+_ui_tr(': 잘못된 비트 값입니다.'))
    if kind=='select':
        choices=opts[0];keys=[int(k) for k in choices] if isinstance(choices,dict) else [v[0] for v in choices]
        if value not in keys:raise ValueError(key+_ui_tr(': 지원하지 않는 선택값입니다.'))
    try:return struct.pack('<'+FORMATS[typ],float(value) if typ=='f32' else int(value))
    except (struct.error,OverflowError) as exc:raise ValueError(key+_ui_tr(': 자료형 범위 오류')) from exc

def decode(field,data,*,raw_slot=False):
    fmt='<'+FORMATS[field[2]]
    if len(data)!=struct.calcsize(fmt):raise ValueError(_ui_tr('Studio 응답 자료형 길이 불일치'))
    value=struct.unpack(fmt,data)[0]
    if not raw_slot and not math.isfinite(value):raise ValueError(_ui_tr('Studio 응답에 유한하지 않은 값'))
    if raw_slot and field[1]=='usb_gamepad_mode' and value==255:return 0
    return value

def validate_changes(values,changes,*,profile_snapshot=False):
    for key,value in changes.items():
        if key not in FIELDS:raise ValueError(_ui_tr('지원하지 않는 설정: ')+key)
        encode(FIELDS[key],value)
    merged=dict(values,**changes)
    if (not profile_snapshot and 'disable_usb_sn' in changes and
            (merged.get('usb_gamepad_mode')==1 or merged.get('controller_mode')==0)):
        raise ValueError(_ui_tr('Edge USB 시리얼 설정은 DualSense Edge USB 모드에서 적용하세요.'))
    if (not profile_snapshot and any(k in changes and changes[k]!=values.get(k)
                                     for k in ('auto_haptics_enable','mix_native_level','ah_dsp_source'))
            and merged.get('auto_haptics_enable')==1 and merged.get('mix_native_level',0)>0
            and merged.get('ah_dsp_source')==1):
        raise ValueError(_ui_tr('네이티브 햅틱을 혼합하려면 햅틱 입력 채널을 앞 채널로 선택하세요.'))
    split=merged.get('ah_xover_hz',0)
    cutoff=merged.get('auto_haptics_lowpass_hz')
    split_edited=any(key in changes and changes[key]!=values.get(key)
                     for key in ('ah_xover_hz','auto_haptics_lowpass_hz'))
    if split and split_edited and (split<30 or (not profile_snapshot and cutoff is not None and split>=cutoff)):
        raise ValueError(_ui_tr('주파수 분리 기준은 30Hz 이상이며 저역 통과 기준보다 낮아야 합니다.'))
    return merged

def needs_reconnect(before,after,macros=None):
    if 'disable_usb_sn' in before and before['disable_usb_sn']!=after.get('disable_usb_sn',before['disable_usb_sn']):return True
    if any(before.get(k)!=after.get(k) for k in ENUM_FIELDS if k in after and k in before):return True
    for key in ('gyro_output','stick_mouse','touch_mouse'):
        if bool(before.get(key,0))!=bool(after.get(key,0)):return True
    old_mask=before.get('macro_disable',0xffffffff)
    new_mask=after.get('macro_disable',0xffffffff)
    if old_mask==new_mask:return False
    # Older firmware exposes a keyboard for any enabled macro.
    if (old_mask==0xffffffff)!=(new_mask==0xffffffff):return True
    if not macros or len(macros)!=32:return True

    def interfaces(values,mask):
        keys=mouse=False
        for index,record in macros.items():
            if mask & (1<<int(index)):continue
            output=record[17]
            mouse |= 11<=output<=15
            keys |= output==0 and any(record[:5]) and any(record[7:11])
        mouse |= any(values.get(key,0) for key in ('gyro_output','stick_mouse','touch_mouse'))
        keyboard=mouse or keys or bool(values.get('enable_wake') or values.get('ps_shortcut_enabled'))
        return keyboard,mouse

    return interfaces(before,old_mask)!=interfaces(after,new_mask)

class SettingsClient(StudioClient):
    def __init__(self,device,sleep=time.sleep,cancel=lambda:False):
        super().__init__(device,sleep);self.cancel=cancel;self.bulk=None;self.deadline=None
        self.lightbar_supported=None;self._lightbar_values={}
    def check_cancel(self):
        if self.cancel():raise RuntimeError(_ui_tr('Studio 작업 취소됨'))
        if self.deadline is not None and time.monotonic()>=self.deadline:raise RuntimeError(_ui_tr('Studio 조회 제한 시간 초과 · 다른 설정창의 조회를 중지한 뒤 새로 고침을 누르세요.'))
    def command(self,command,payload=b'',report=0x81,echo=b'',echo_offset=3,*,accept=None,attempts=12):
        self.check_cancel()
        if len(payload)>61:raise ValueError(_ui_tr('Studio 명령 길이 초과'))
        packet=bytes([0x80,0x66,command])+bytes(payload)
        if self.device.send_feature_report(packet.ljust(64,b'\0'))!=64:raise OSError(_ui_tr('Studio 명령 전송 실패'))
        mismatched=False
        for attempt in range(attempts):
            self.check_cancel()
            # Retry only idempotent reads; never repeat settings/flash writes.
            if attempt==6 and command in (4,12,13,23):
                if self.device.send_feature_report(packet.ljust(64,b'\0'))!=64:raise OSError(_ui_tr('Studio 재조회 전송 실패'))
            self.sleep(.06)
            try:raw=bytes(self.device.get_feature_report(report,64))
            except OSError:continue
            if len(raw)<5 or raw[:3]!=bytes([report,0x66,command]):
                if len(raw)>=3 and raw[:2]==bytes([report,0x66]):mismatched=True
                continue
            body=raw[1:]
            if body[2]==0xfe:continue
            # A negative bulk reply echoes only the successfully read prefix,
            # not the requested count. Waiting for a success echo here turns
            # each unsupported field into a timeout (and an unnecessary retry).
            # Accept failure only as failure; callers still validate any data.
            if command==12 and body[2]==1:return body
            if echo and body[echo_offset:echo_offset+len(echo)]!=echo:mismatched=True;continue
            if accept is not None and not accept(body):continue
            return body
        raise TimeoutError(_ui_tr('Studio 응답 충돌 또는 지연 · 브라우저 웹 설정의 장치 연결을 해제한 뒤 새로 고침하세요.') if mismatched else _ui_tr('Studio 응답 대기 시간 초과'))
    def dock_disconnect(self, mode=None):
        return self.standby_mode(mode, command=0x1d)

    def standby_mode(self, mode=None, *, command=0x1c):
        """Read or persist the device-wide policy, independently of profiles."""
        if mode not in (None, 0, 1):
            raise ValueError('Invalid standby mode')
        payload = bytes([0]) if mode is None else bytes([1, mode])
        # Optional reads get a short probe window; writes keep full verification.
        attempts = 3 if mode is None else 12
        reply = self.command(command, payload, 0x84, attempts=attempts, accept=lambda r: mode is None or len(r)<5 or r[2]!=0 or r[3]!=1 or r[4]==mode)
        if len(reply) < 5 or reply[3] != 1 or reply[4] not in (0, 1):
            raise ValueError(_ui_tr('충전독 정책 응답 오류') if command==0x1d else _ui_tr('Pico 절전 정책 응답 오류'))
        if reply[2] == 2:
            message=(_ui_tr('충전독 정책 저장 실패') if command==0x1d else _ui_tr('Pico 절전 정책 저장 실패'))
            raise PolicySaveError(message+_ui_tr(' · 다른 앱의 Pico 오디오 출력을 중지한 뒤 다시 시도하세요. 오디오 사용 중에는 저장이 제한될 수 있습니다.'),reply[4])
        if reply[2] != 0 or (mode is not None and reply[4] != mode):
            raise ValueError(_ui_tr('충전독 정책 응답 오류') if command==0x1d else _ui_tr('Pico 절전 정책 응답 오류'))
        return reply[4]

    def read_lightbar(self,refresh=False):
        if self.lightbar_supported is False:return {}
        if self.lightbar_supported is True and not refresh:return dict(self._lightbar_values)
        try:
            r=self.command(12,b'\x02\xc1\xc2',echo=b'\x02\xc1')
            if len(r)<13 or r[2:6]!=b'\x00\x02\xc1\x01' or r[7:9]!=b'\xc2\x04':
                raise ValueError(_ui_tr('라이트바 묶음 응답 불일치'))
            fixed=r[6];rgb=int.from_bytes(r[9:13],'little')
            if fixed not in (0,1) or rgb>0xffffff:raise ValueError(_ui_tr('라이트바 응답 범위 오류'))
            self._lightbar_values=dict(lightbar_fixed=fixed,lightbar_rgb=rgb)
            self.lightbar_supported=True;self.bulk=True
        except (OSError,ValueError,TimeoutError):
            self.lightbar_supported=False;self._lightbar_values={}
        return dict(self._lightbar_values)
    def read_rumble(self,refresh=False):
        cached=getattr(self,'_rumble_values',None)
        if cached is not None and not refresh:return dict(cached)
        try:
            reply=self.command(12,bytes([2,0xc3,0xc4]),echo=bytes([2,0xc3]))
            if len(reply)<10 or reply[2:6]!=bytes([0,2,0xc3,1]) or reply[7:9]!=bytes([0xc4,1]):
                raise ValueError(_ui_tr('일반 진동 묶음 응답 불일치'))
            gain,release=reply[6],reply[9]
            if not 100<=gain<=200 or release not in (0,1,2):raise ValueError(_ui_tr('일반 진동 응답 범위 오류'))
            self._rumble_values=dict(rumble_gain=gain,rumble_release=release);self.bulk=True
        except (OSError,ValueError,TimeoutError):self._rumble_values={}
        return dict(self._rumble_values)
    def read_one(self,field,slot=None):
        if field[1] in FIELDS and field[1] not in EDITABLE:raise ValueError(_ui_tr('제외된 설정은 읽지 않습니다.'))
        if field[1] in LIGHTBAR_FIELDS:
            values=self.read_lightbar(refresh=slot is None)
            if not values:raise ValueError(_ui_tr('라이트바 색상 고정 미지원 · 펌웨어 업데이트가 필요합니다.'))
            if slot is None:return values[field[1]]
        if field[1] in RUMBLE_FIELDS:
            values=self.read_rumble(refresh=slot is None)
            if not values:raise ValueError(_ui_tr('일반 진동 조절 미지원 · 펌웨어 확인 필요'))
            if slot is None:return values[field[1]]
        fid=field[0]
        if field[1] in (USB_MODE_FIELDS | RUMBLE_MODE_FIELDS | EDGE_SERIAL_FIELDS) and slot is None:
            if field[1] in EDGE_SERIAL_FIELDS:
                reply=self.command(12,bytes([1,fid]),echo=bytes([1,fid]),attempts=3)
                if reply[2:4]==b'\x01\x00':
                    raise EdgeSerialUnsupported(_ui_tr('Edge USB 시리얼 숨기기'))
                if len(reply)<7 or reply[2:6]!=bytes([0,1,fid,1]) or reply[6]>1:
                    raise ValueError(_ui_tr('Studio 필드 응답 불일치'))
                self.bulk=True
                return reply[6]
            rumble_mode = field[1] in RUMBLE_MODE_FIELDS
            error = _ui_tr('일반 진동 모드 지원을 확인하지 못했습니다.') if rumble_mode else _ui_tr('XBOX 모드 지원을 확인하지 못했습니다.')
            reply=self.command(12,bytes([1,fid]),echo=bytes([1,fid]))
            if reply[2:4]==b'\x01\x00':
                raise (RumbleModeUnsupported if rumble_mode else USBModeUnsupported)(error)
            if len(reply)<7 or reply[2:6]!=bytes([0,1,fid,1]) or reply[6] > (2 if rumble_mode else 1):
                raise ValueError(error)
            self.bulk=True
            return reply[6]
        if slot is not None:
            r=self.command(13,bytes([slot,fid]),0x84,bytes([slot,fid]))
            if r[2]!=0:raise ValueError(_ui_tr('슬롯 설정 읽기 미지원'))
            return decode(field,r[5:5+struct.calcsize('<'+FORMATS[field[2]])],raw_slot=True)
        # command 4 echoes fid in the status position, not a status byte.
        r=self.command(4,bytes([fid]),echo=bytes([fid]),echo_offset=2)
        if r[2]!=fid:raise ValueError(_ui_tr('Studio 필드 응답 불일치'))
        return decode(field,r[3:3+struct.calcsize('<'+FORMATS[field[2]])])
    def read_fields(self,fields=None):
        fields=list(EDITABLE.values() if fields is None else fields)
        if any(f[1] in FIELDS and f[1] not in EDITABLE for f in fields):raise ValueError(_ui_tr('공사 중 또는 제외된 설정은 읽지 않습니다.'))
        out={};unsupported=[]
        optional=[f for f in fields if f[1] in LIGHTBAR_FIELDS]
        rumble=[f for f in fields if f[1] in RUMBLE_FIELDS]
        modes=[f for f in fields if f[1] in (USB_MODE_FIELDS | RUMBLE_MODE_FIELDS | EDGE_SERIAL_FIELDS)]
        fields=[f for f in fields if f[1] not in OPTIONAL_FIELDS]
        for f in modes:
            try:out[f[1]]=self.read_one(f)
            except (OSError,ValueError,TimeoutError):unsupported.append(f[1])
        if rumble:
            values=self.read_rumble(refresh=True)
            for f in rumble:
                if f[1] in values:out[f[1]]=values[f[1]]
                else:unsupported.append(f[1])
        if optional:
            values=self.read_lightbar(refresh=True)
            for f in optional:
                if f[1] in values:out[f[1]]=values[f[1]]
                else:unsupported.append(f[1])
        for start in range(0,len(fields),12):
            group=fields[start:start+12];got={}
            if self.bulk is not False:
                try:
                    r=self.command(12,bytes([len(group),*[f[0] for f in group]]),echo=bytes([len(group),group[0][0]]))
                    count=r[3] if len(r)>3 else -1
                    if r[2] not in (0,1) or not 0<=count<=len(group) or r[2]==0 and count!=len(group) or r[2]==1 and count==len(group):
                        raise ValueError(_ui_tr('묶음 읽기 개수 불일치'))
                    off=4
                    for f in group[:count]:
                        if off+2>len(r):raise ValueError(_ui_tr('잘린 Studio 응답'))
                        fid,size=r[off:off+2];off+=2
                        if fid!=f[0] or off+size>len(r):raise ValueError(_ui_tr('Studio 필드 묶음 불일치'))
                        got[f[1]]=decode(f,r[off:off+size]);off+=size
                    # One unsupported field must not disable bulk reads for
                    # every later group. Retain a validated partial prefix.
                    self.bulk=True if count or r[2]==0 or self.bulk is True else False
                except (OSError,ValueError,TimeoutError):self.bulk=False;got={}
            if len(got)!=len(group):
                for f in group:
                    if f[1] in got:continue
                    try:got[f[1]]=self.read_one(f)
                    except (OSError,ValueError,TimeoutError):unsupported.append(f[1])
            out.update(got)
        if not out and fields:raise RuntimeError(_ui_tr('Studio 설정을 읽지 못했습니다. 연결을 확인하고 새로 고침을 누르세요.'))
        return out,unsupported
    def write_fields(self,values,baseline,*,profile_snapshot=False):
        if any(k not in EDITABLE for k in values):raise ValueError(_ui_tr('공사 중 또는 제외된 설정은 쓰지 않습니다.'))
        validate_changes(baseline,values,profile_snapshot=profile_snapshot)
        serial_field=EDGE_SERIAL_STORAGE_FIELD if profile_snapshot else FIELDS['disable_usb_sn']
        for key in (USB_MODE_FIELDS | RUMBLE_MODE_FIELDS | EDGE_SERIAL_FIELDS).intersection(values):
            self.read_one(serial_field if key in EDGE_SERIAL_FIELDS else FIELDS[key])
        if RUMBLE_FIELDS.intersection(values):
            if not self.read_rumble():raise ValueError(_ui_tr('일반 진동 조절 미지원 · 새로 고침과 펌웨어 확인이 필요합니다.'))
            self.bulk=True
        if LIGHTBAR_FIELDS.intersection(values):
            if not self.read_lightbar():raise ValueError(_ui_tr('라이트바 색상 고정 미지원 · 새로 고침과 펌웨어 확인이 필요합니다.'))
            self.bulk=True
            # Set RGB/off ownership before enabling; bulk application is not rollback-safe.
            order={'lightbar_rgb':0,'lightbar_off':1,'lightbar_fixed':2}
            values=dict(sorted(values.items(),key=lambda item:order.get(item[0],3)))
        # Probe the read side before choosing the write protocol.
        if self.bulk is None and values:self.read_fields([FIELDS[next(iter(values))]])
        entries=[(serial_field if k in EDGE_SERIAL_FIELDS else FIELDS[k],encode(FIELDS[k],v))
                 for k,v in values.items()]
        groups=[];chunk=[];size=1
        for field,data in entries:
            if size+2+len(data)>58:groups.append(chunk);chunk=[];size=1
            chunk.append((field,data));size+=2+len(data)
        if chunk:groups.append(chunk)
        try:
            for group in groups:
                if self.bulk:
                    payload=bytes([len(group)])+b''.join(bytes([f[0],len(data)])+data for f,data in group)
                    r=self.command(11,payload)
                    if r[2]!=0 or r[3]!=len(group):raise PartialApplyError(_ui_tr('일부 설정만 적용되었을 수 있습니다. 다시 읽어 확인하세요.'))
                else:
                    for f,data in group:
                        r=self.command(1,bytes([f[0]])+data)
                        if r[2]!=0:raise PartialApplyError(_ui_tr('설정 적용 응답 오류'))
            checked,missing=self.read_fields([f for f,_ in entries]) if entries else ({},[])
            for key,value in values.items():
                actual=checked.get(key)
                matches=(actual==value if key in OPTIONAL_FIELDS else actual is not None and math.isclose(actual,value,rel_tol=1e-5,abs_tol=1e-5))
                if not matches:raise PartialApplyError(_ui_tr('장치가 값을 보정했거나 적용 결과가 다릅니다: ')+key)
            return checked
        except Exception as exc:
            raise PartialApplyError(str(exc)+_ui_tr(' · 적용 상태를 다시 읽어 확인하세요.')) from exc
    def save_flash(self):
        if self.cancel():raise RuntimeError(_ui_tr('Studio 저장 취소됨'))
        tag=(secrets.randbelow(0xffffffff)+1).to_bytes(4,'little')
        try:
            reply=self.command(2,tag,0x84,echo=tag,echo_offset=4,attempts=40,
                accept=lambda r:len(r)>=8 and r[3]==1 and r[2] in (0,2))
        except TimeoutError as exc:
            raise TimeoutError(_ui_tr('Pico 저장 응답 미확인 · 구형 펌웨어는 저장 확인 미지원 · 다른 설정창을 닫고 상태를 확인하세요.')) from exc
        if reply[2]==2:raise RuntimeError(_ui_tr('Pico 설정 저장 실패 · 연결과 저장 상태를 확인하세요.'))
        return True

    def reconnect_usb(self):
        if self.cancel():raise RuntimeError(_ui_tr('Studio 재연결 취소됨'))
        return super().reconnect_usb()
    def save_slot(self,index,name):
        if not 0<=index<32:raise ValueError(_ui_tr('슬롯 범위 오류'))
        raw=name.encode('utf-8')
        if len(raw)>16:raise ValueError(_ui_tr('프로필 이름은 UTF-8 16바이트 이내로 입력하세요.'))
        r=self.command(8,bytes([index])+raw,0x84,bytes([index]))
        if r[2]!=0:raise RuntimeError(_ui_tr('슬롯 저장 실패 · 적용 결과를 조회하세요.'))
    def read_effects(self,slot=None):
        raise RuntimeError(_ui_tr('커스텀 트리거는 공사 중이므로 읽지 않습니다.'))
    def write_effect(self,trig,index,state):
        raise RuntimeError(_ui_tr('커스텀 트리거는 공사 중이므로 쓰지 않습니다.'))
    def history(self):
        raise RuntimeError(_ui_tr('커스텀 트리거는 공사 중이므로 조회하지 않습니다.'))
    def read_macros(self):
        r=self.command(23,b'\xff',0x84,b'\xff')
        if r[2]!=0:raise RuntimeError(_ui_tr('매크로 테이블 조회 미지원'))
        mask=int.from_bytes(r[4:8],'little');out={}
        for index in range(32):
            if not mask&(1<<index):out[str(index)]=[0]*35;continue
            row=self.command(23,bytes([index]),0x84,bytes([index]))
            if row[2]!=0 or len(row)<39:raise RuntimeError(_ui_tr('매크로 읽기 실패'))
            out[str(index)]=list(row[4:39])
        return out
    def macro_features(self, preview=False):
        token=secrets.token_bytes(4);sub=int(preview)
        try:row=self.command(0x20,bytes([sub])+token,0x84,bytes([sub])+token,echo_offset=4)
        except TimeoutError as exc:
            raise RuntimeError(_ui_tr('시프트·프로필 전환 지원을 확인하지 못했습니다. v31 이상 실험 펌웨어를 확인하세요.')) from exc
        if preview and row[2]==2:
            raise RuntimeError(_ui_tr('듀얼센스를 연결하고 PC 절전을 해제한 뒤 미리듣기를 눌러 주세요.'))
        if row[2] or len(row)<10 or row[3]!=1 or not preview and row[9]&7!=7:
            raise RuntimeError(_ui_tr('시프트·프로필 전환은 v31 이상 실험 펌웨어가 필요합니다.'))
        if not preview:
            self._macro_extensions=True
            self._macro_feature_bits=row[9]
        return row

    def require_macro_features(self, records):
        from studio_shift import POWER_OFF,POWER_OFF_CAPABILITY,extended,validate_extension
        for row in records:validate_extension(row)
        needs_power_off=any(row[17] == POWER_OFF for row in records)
        power_off_error=_ui_tr('듀얼센스 전원 끄기는 지원 펌웨어 업데이트 후 사용할 수 있습니다.')
        if any(extended(row) for row in records) and not getattr(self,'_macro_extensions',False):
            try:self.macro_features()
            except RuntimeError as exc:
                if needs_power_off:raise RuntimeError(power_off_error) from exc
                raise
        if needs_power_off and not getattr(self, '_macro_feature_bits', 0) & POWER_OFF_CAPABILITY:
            raise RuntimeError(power_off_error)
        if any(r[4]&128 and not r[4]&48 and r[5]&4 for r in records):
            if not hasattr(self,'_macro_feature_bits'):self.macro_features()
            if not self._macro_feature_bits&8:
                raise RuntimeError(_ui_tr('터치패드 클릭 차단은 지원 펌웨어 업데이트 후 사용할 수 있습니다.'))

    def write_macro(self,index,data):
        if not 0<=index<32 or len(data)!=35:raise ValueError(_ui_tr('매크로 형식 오류'))
        if data[4]&0x10:raise ValueError(_ui_tr('실험 기능인 모션 제스처는 편집하지 않습니다.'))
        self.require_macro_features([data])
        r=self.command(24,bytes([index])+bytes(data),0x84,bytes([index]))
        if r[2]!=0:raise RuntimeError(_ui_tr('매크로 적용 실패'))
    def commit_macros(self):
        if self.command(25,report=0x84)[2]!=0:raise RuntimeError(_ui_tr('매크로 영구 저장 실패'))
