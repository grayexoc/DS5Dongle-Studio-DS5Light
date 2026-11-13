"""Optional Studio power command. Never retry a power request or change profiles."""
from thread_start import start_thread
from studio_i18n import text as _ui_tr
import queue
import threading
import time
from dataclasses import dataclass
from studio_slots import _DEVICE_LOCK,devices
from device_binding import resolve_hid


@dataclass(frozen=True)
class PowerReply:
    state:int
    reason:int
    flags:int


def power_command(device,action,sleep=time.sleep):
    if action not in (0,1):raise ValueError('Invalid power action')
    payload=bytes([0x80,0x66,0x1b,action])+(b'\x53\x4c' if action else b'')
    send_error=None
    try:
        if device.send_feature_report(payload.ljust(64,b'\0'))!=64:
            send_error=OSError(_ui_tr('절전 요청 전송 길이 불일치'))
    except OSError as exc:send_error=exc
    # A write exception can follow successful delivery. Read the acknowledgement
    # anyway, without resending: GET_REPORT itself schedules firmware shutdown.
    for _ in range(12):
        sleep(.06)
        try:raw=bytes(device.get_feature_report(0x84,64))
        except OSError:continue
        if len(raw)<9 or raw[:3]!=b'\x84\x66\x1b' or raw[4]!=action:continue
        if raw[3]!=0:raise ValueError(_ui_tr('Pico가 절전 명령을 거부했습니다.'))
        if raw[5]!=1:raise ValueError(_ui_tr('지원하지 않는 Pico 절전 프로토콜입니다.'))
        if raw[6] not in range(5) or raw[7] not in range(4):raise ValueError(_ui_tr('잘못된 Pico 절전 상태입니다.'))
        return PowerReply(raw[6],raw[7],raw[8])
    raise TimeoutError(_ui_tr('절전 응답 미확인 · 자동 재전송하지 않습니다.')) from send_error


def exchange(path,action):
    import hid
    if not _DEVICE_LOCK.acquire(timeout=3):
        raise TimeoutError(_ui_tr('Studio 조회 대기 시간 초과'))
    try:
        device=hid.device()
        try:
            device.open_path(path)
            if action==1:
                capability=power_command(device,0)
                if capability.state!=0 or not capability.flags&8:
                    raise ValueError(_ui_tr('Pico 절전 기능을 사용할 수 없습니다.'))
            return power_command(device,action)
        finally:device.close()
    finally:_DEVICE_LOCK.release()


def blocked(app):
    return bool(getattr(getattr(app,'studio_power',None),'blocked',False))


class StudioPower:
    def __init__(self,app):
        self.app=app;self.state='idle';self.supported=False;self.key=None
        self.busy=False;self.results=queue.SimpleQueue();self.next_check=0.
        self.identity=None;self.seen_absent=False;self.requested_at=0.
        self.acknowledged=False
        self.click_identity=None

    @property
    def blocked(self):return self.state!='idle'

    def worker(self,kind,operation):
        if self.busy:return
        self.busy=True
        def work():
            try:self.results.put((kind,operation(),None))
            except Exception as exc:self.results.put((kind,None,str(exc)))
        try:start_thread(threading.Thread(target=work,name='DS5Light-power',daemon=True))
        except Exception as exc:self.results.put((kind,None,str(exc)))

    def click(self,event=None):
        a=self.app
        if (self.busy or self.blocked or a.studio.busy or a.studio_settings.busy
                or a._closing or a._close_requested or a._stopping):return
        identity=a.studio.binding.snapshot()
        if not identity.hid_path:
            a.status.set(_ui_tr('Pico를 먼저 조회한 뒤 다시 시도하세요.'));return
        if not self.supported or (identity.hid_path,identity.serial)!=self.key:
            # A transient initial read failure must not permanently disable the
            # invisible button. An explicit click can query even during audio.
            # This sends only action=0, never a speculative sleep command.
            self.click_identity=identity;self.state='checking'
            a.status.set(_ui_tr('Pico 절전 기능 확인 중…'))
            self.worker('click_probe',lambda:exchange(identity.hid_path,0))
            return
        self.identity=identity;self.state='stopping';self.acknowledged=False
        self.seen_absent=False;self.supported=False
        a.studio_settings.resume=False
        a.studio_settings.stop_live()
        editor=getattr(a.studio_settings,'macro_editor',None)
        if editor is not None and not editor.closed:editor.stop_capture()
        if hasattr(a,'mute_shortcut'):
            a.mute_shortcut.configure(dict(a.mute_binding,enabled=False))
        a.stop(on_complete=self.send,message=_ui_tr('듀얼센스 연결 해제 및 Pico 절전 요청 준비 중…'),reason='intentional_sleep')

    def send(self):
        if self.app._closing or self.app._close_requested:return
        self.state='request';self.requested_at=time.monotonic()
        self.worker('request',lambda:exchange(self.identity.hid_path,1))

    def invalidate(self):
        a=self.app;a.studio.controller_connected=False;a.studio._show_disconnected()
        a.studio_settings.write_ready=False;a.studio_settings.pico_recognized=False
        a.studio_settings.external_stale=True
        a.studio_settings.invalidate_slot_cache()
        a.battery.generation+=1;a.battery.state='disconnected';a.battery.value=None
        a.brand_wordmark.show_status(a.battery.state,None)
        if a.studio_settings.built:a.studio_settings.update_state()
        a.last_render=None;a.render()

    def release(self):
        self.state='idle';self.key=None;self.supported=False
        a=self.app
        a.battery.next_check=0.;a.studio.catalog_invalid=True
        if hasattr(a,'mute_shortcut'):a.mute_shortcut.configure(a.mute_binding)
        a.last_render=None;a.render()

    def tick(self):
        a=self.app;now=time.monotonic()
        try:kind,value,error=self.results.get_nowait()
        except queue.Empty:pass
        else:
            self.busy=False
            if kind=='probe':
                self.supported=error is None and value.state==0 and bool(value.flags&8)
                editor=a.studio_settings
                if editor.built and not editor.busy:editor.refresh_read_values()
            elif kind=='click_probe':
                self.state='idle'
                expected=self.click_identity;self.click_identity=None
                current=a.studio.binding.snapshot()
                self.supported=(error is None and value.state==0 and bool(value.flags&8)
                                and current==expected)
                self.key=(expected.hid_path,expected.serial)
                if self.supported:self.click()
                else:
                    a.status.set(_ui_tr('Pico 절전 기능을 확인하지 못했습니다. 지원 펌웨어와 연결을 확인하세요.'))
                    return
            elif kind=='request':
                self.acknowledged=error is None and value.state in (1,2,3)
                if self.acknowledged:
                    # GET_REPORT has acknowledged/scheduled the request. Exit
                    # through normal cleanup, without another notice or probe.
                    self.state='closing'
                    a.request_close()
                    return
                self.state='waiting';self.next_check=now+.4
                a.status.set(_ui_tr('절전 결과 미확인 · 자동 재전송하지 않습니다.'))
                if error is None and value.state==4:
                    self.failure(value.reason);return
            elif kind=='observe':
                present,reply=value if error is None else (None,None)
                if present is False:
                    self.seen_absent=True;self.state='sleeping';self.invalidate()
                    a.status.set(_ui_tr('듀얼센스 연결 해제됨 · Pico 절전 요청됨') if self.acknowledged else
                                 _ui_tr('장치 분리됨 · 절전 결과 미확인'))
                elif present and self.seen_absent and reply is not None and reply.state==0:
                    self.release()
                    a.status.set(_ui_tr('Pico 재연결됨 · 듀얼센스 연결을 확인하세요.'))
                    a.studio.discover(allow_running=True)
                elif reply is not None and reply.state==4:
                    self.failure(reply.reason)
        if a._closing or a._close_requested or self.busy:return
        if self.blocked:
            if self.state not in ('waiting','sleeping') or now<self.next_check:return
            self.next_check=now+(15. if self.state=='waiting' and now-self.requested_at>=6 else 3.)
            # No reopen/activation/reset/retry. Only enumerate the pinned Pico;
            # poll its power state briefly while it remains visible after request.
            def observe():
                rows=devices();identity=self.identity
                if identity.container_id and not identity.serial:
                    from windows_device_identity import hid_container
                    rows=[dict(row,container_id=row.get('container_id') or hid_container(row['path'])) for row in rows]
                target=resolve_hid(rows,identity.hid_path,identity.serial,identity.container_id)
                if target is None:return False,None
                if self.seen_absent or self.state=='waiting':
                    try:return True,exchange(target['path'],0)
                    except Exception:return True,None
                return True,None
            self.worker('observe',observe)
            return
        if a.studio.busy or a.studio_settings.busy or a.engine is not None:return
        identity=a.studio.binding.snapshot();key=(identity.hid_path,identity.serial)
        if not identity.hid_path or a.studio.observed_profile is None:return
        if key!=self.key:
            self.key=key;self.supported=False
            self.worker('probe',lambda:exchange(identity.hid_path,0))

    def failure(self,reason):
        messages={1:_ui_tr('예약 설정 저장 실패'),2:_ui_tr('오디오 처리 정지 실패'),3:_ui_tr('접수 응답 확인 시간 초과')}
        self.release()
        self.app.status.set(_ui_tr('Pico 절전 실패 · ')+messages.get(reason,_ui_tr('상태 확인 필요')))
