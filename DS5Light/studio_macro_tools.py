"""Native macro presentation, local recording and explicitly enabled diagnostics."""
from thread_start import start_thread
from studio_i18n import text as _ui_tr
from ui_controls import widget_trace
import json,threading,time,queue,tkinter as tk
from pathlib import Path
from tkinter import ttk,filedialog
from studio_dialogs import messagebox
from studio_records import macro_records
from studio_slots import _DEVICE_LOCK
from studio_settings_protocol import SettingsClient
from studio_shift import POWER_OFF

BG='#151515';FG='#eee9df';MUTED='#aaa393';GOLD='#d6ad52'

def structured_macros(records):
    out=[]
    for key,r in records.items():
        if r[4]&16 or not any(r):continue
        out.append(dict(index=int(key),label=bytes(r[19:35]).split(b'\0')[0].decode('utf-8','replace'),
            chord=int.from_bytes(bytes(r[:4]),'little'),gesture=r[4],flags=r[5],hold_cs=r[6],keys=r[7:11],
            rel_order=r[11],out_btn=r[17],stick_thresh=r[18]))
    return out

def input_snapshot(raw):
    """USB input report 1, payload offsets match the upstream tester."""
    if len(raw)<11 or raw[0]!=1:return None
    d=raw[1:];hat=d[7]&15
    mask=0
    for h,bits in {0:1,1:1|8,2:8,3:8|2,4:2,5:2|4,6:4,7:4|1}.items():
        if hat==h:mask|=bits
    mask|=(d[7]>>4)<<4
    mask|=d[8]<<8
    mask|=(d[9]&7)<<16
    # Edge buttons are the upper nibble of the system byte.
    mask|=((d[9]>>4)&15)<<19
    # Match firmware half-click qualification: landing X, not current X.
    point=None
    if len(d)>=36:
        point=dict(down=not bool(d[32]&128),x=d[33]|((d[34]&15)<<8),y=(d[34]>>4)|(d[35]<<4))
    return dict(mask=mask,lx=d[0],ly=d[1],rx=d[2],ry=d[3],l2=d[4],r2=d[5],touch=point)

def normalize_macro(record):
    gesture=record[4];flags=record[5];chord=int.from_bytes(bytes(record[:4]),'little')
    if gesture&32: # stick-to-keys is always held; no keyboard chord gate
        flags=(flags|2)&~(1|16);record[:4]=bytes(4);record[17]=0
    elif gesture&128: # a swipe is an event, never held
        flags&=~(1|2|8|16)
    if flags&16 and flags&(1|2):raise ValueError(_ui_tr('두 번 누름은 길게 누름·유지와 함께 사용할 수 없습니다.'))
    if flags&1 and flags&2:raise ValueError(_ui_tr('길게 누름과 누르는 동안 유지는 동시에 선택할 수 없습니다.'))
    if not flags&2 and not gesture&128:flags&=~(4|8)
    if not (gesture&32 and flags&4):flags&=~8
    if gesture==0 and not chord and any(record[7:11]+[record[17]]):raise ValueError(_ui_tr('입력 버튼을 선택하세요.'))
    if record[18] and not 10<=record[18]<=120:raise ValueError(_ui_tr('스틱 작동 깊이는 0(기본값) 또는 10~120입니다.'))
    record[5]=flags
    return record

class LiveMonitor:
    """One opt-in read-only observer. Feature requests serialize with Studio jobs."""
    def __init__(self,path,diagnostics=True):
        self.path=path;self.diagnostics=diagnostics;self.stop=threading.Event();self.results=queue.Queue(maxsize=1);self.thread=None
    def start(self):
        self.thread=threading.Thread(target=self.run,name='DS5Light-Studio-live',daemon=True);start_thread(self.thread)
    def publish(self,data):
        try:self.results.get_nowait()
        except queue.Empty:pass
        try:self.results.put_nowait(data)
        except queue.Full:pass
    def run(self):
        import hid
        device=hid.device();diag={};snapshot=None;next_diag=0;landing=None;half=0;received_at=None
        try:
            device.open_path(self.path);device.set_nonblocking(1)
            client=SettingsClient(device,cancel=self.stop.is_set)
            while not self.stop.wait(.04):
                # Drain a bounded queue; redraw at 10 Hz instead of per USB packet.
                until=time.monotonic()+.004
                while time.monotonic()<until:
                    raw=device.read(64)
                    if not raw:break
                    current=input_snapshot(raw)
                    if current:
                        t=current['touch']
                        if t and t['down'] and landing is None:landing=t['x']
                        if t and not t['down']:landing=None
                        if current['mask']&(1<<17):
                            if not half and landing is not None:half=(1<<23) if landing<800 else (1<<24) if landing>1118 else 0
                            current['mask']|=half
                        else:half=0
                        snapshot=current
                        received_at=time.monotonic()
                now=time.monotonic()
                if self.diagnostics and now>=next_diag and _DEVICE_LOCK.acquire(blocking=False):
                    try:
                        for fid,key,typ in [(0x7b,'touch_x','u16'),(0x7c,'touch_info','u8'),(0x88,'suppress_low','u16'),(0x89,'suppress_high','u16'),(0x8a,'inject_low','u16'),(0x8b,'inject_high','u16'),(0x8c,'stick','u8'),(0x8d,'keyboard','u16')]:
                            if self.stop.is_set():break
                            diag[key]=client.read_one([fid,key,typ,key,'number',[0,65535]])
                    finally:_DEVICE_LOCK.release()
                    next_diag=now+1
                self.publish(dict(input=snapshot,diag=dict(diag),received_at=received_at))
        except Exception as exc:self.publish(dict(error=str(exc)))
        finally:device.close()

class MacroTools:
    normalize_macro=staticmethod(normalize_macro)
    def read_macro_table(self):
        if self.busy or self.app.studio.busy:return
        mask_changed='macro_disable' in self.doc.changes
        if (self.doc.macro_changes or mask_changed) and not messagebox.askyesno(_ui_tr('매핑 목록 새로 고침'),_ui_tr('미적용 매핑 편집과 사용 여부를 취소하고 다시 읽을까요? 다른 설정의 편집값은 유지됩니다.'),parent=self.parent):return
        self._discard_macro_mask_on_read=mask_changed
        self.task('macros',lambda:self.with_client(lambda c:c.read_macros()))
    def filter_macros(self,kind):self.render_fields() # All definitions remain visible.
    def toggle_macro(self,index,enabled,status=None,kind=''):
        mask=int(self.doc.values.get('macro_disable',0xffffffff))
        if enabled:
            from studio_shift import validate_reserved_inputs
            try:validate_reserved_inputs(self.doc.macros,dict(self.doc.values,macro_disable=mask&~(1<<index)))
            except ValueError as exc:
                messagebox.showinfo(_ui_tr('입력 조합 제한'),str(exc),parent=self.parent)
                self.render_fields();return
        self.changed('macro_disable',mask&~(1<<index) if enabled else mask|(1<<index))
        if status:status.set(kind+' · '+(_ui_tr('활성') if enabled else _ui_tr('비활성')))
        self.update_macro_warnings()
    def macro_conflicts(self):
        from studio_macro_design import conflicts
        messages=conflicts(self.doc.macros,int(self.doc.values.get('macro_disable',0xffffffff)))
        from studio_shift import reserved_input
        mask=int(self.doc.values.get('macro_disable',0xffffffff))
        for key,row in self.doc.macros.items():
            if not mask&(1<<int(key)):
                reason=reserved_input(row,self.doc.macros,mask,bool(self.doc.values.get('ps_shortcut_enabled',0)))
                if reason:messages.append(f'{int(key)+1:02d} · '+reason)
        if getattr(self.app,'mute_binding',{}).get('enabled'):
            for key,record in self.doc.macros.items():
                if int.from_bytes(bytes(record[:4]),'little')&(1<<18) and not int(self.doc.values.get('macro_disable',0xffffffff))&(1<<int(key)):
                    messages.append(_ui_tr('{0} · Studio 매크로가 우선하며 앱의 마이크 버튼 키보드매핑은 비활성화됩니다.').format(f'{int(key) + 1:02d}'))
        return messages
    def update_macro_warnings(self):
        if not hasattr(self,'macro_warning_label') or not self.macro_warning_label.winfo_exists():return
        messages=self.macro_conflicts()
        if messages:
            expanded=getattr(self,'macro_conflicts_expanded',False)
            self.macro_warning.set(_ui_tr('입력 조건 확인\n')+'\n'.join(messages if expanded else messages[:3])+(_ui_tr('\n외 {0}건').format(f'{len(messages) - 3}') if len(messages)>3 and not expanded else ''))
            self.macro_warning_button.configure(text=_ui_tr('겹치는 입력 접기') if expanded else _ui_tr('겹치는 입력 모두 보기'))
            self.macro_warning_label.grid();self.macro_warning_button.grid()
        else:self.macro_warning_label.grid_remove();self.macro_warning_button.grid_remove()
    def show_macro_conflicts(self):
        self.macro_conflicts_expanded=not getattr(self,'macro_conflicts_expanded',False)
        self.update_macro_warnings()
    def macro_summary(self,data):
        from studio_settings_ui import BUTTONS,OUT_BUTTONS,HID_KEYS
        from studio_macro_design import condition,CONDITIONS
        chord=int.from_bytes(bytes(data[:4]),'little')
        from studio_button_names import NAMES
        source=' + '.join(n for i,n in enumerate(NAMES) if chord&(1<<i)) or _ui_tr('입력 미지정')
        keyname=lambda c:next((k for k,v in HID_KEYS.items() if v==c),f'HID {c}') if c else _ui_tr('미지정')
        OUT_BUTTONS=list(OUT_BUTTONS)+[_ui_tr('프로필 {0}번').format(i) for i in range(1,9)]
        target=OUT_BUTTONS[data[17]] if data[17] and data[17]<len(OUT_BUTTONS) else ' + '.join(keyname(c) for c in data[7:11] if c) or _ui_tr('출력 미지정')
        if data[17]==POWER_OFF:target=_ui_tr('듀얼센스 전원')
        if data[4]&32:
            source=_ui_tr('오른쪽 스틱') if data[4]&64 else _ui_tr('왼쪽 스틱')
            target=' · '.join(d+' '+keyname(c) for d,c in zip(('↑','→','↓','←'),data[7:11]))
        elif data[4]&128:source=(_ui_tr('오른쪽') if data[4]&4 else _ui_tr('왼쪽'))+_ui_tr(' 터치 · ')+[_ui_tr('위'),_ui_tr('아래'),_ui_tr('왼쪽'),_ui_tr('오른쪽')][data[4]&3]+_ui_tr(' 밀기')
        return (_ui_tr('[시프트] ') if data[5]&32 else '')+source+' → '+target+'\n'+(_ui_tr('스와이프 감지 시') if data[4]&128 and not data[4]&48 else CONDITIONS[condition(data)])+(_ui_tr(' · 전환 신호음') if data[5]&64 else '')+((_ui_tr(' · 터치패드 클릭 차단') if data[4]&128 and not data[4]&48 else _ui_tr(' · 조건 버튼 숨김')) if data[5]&4 else '')
    def new_macro(self):
        if self.busy or not self.loaded:return
        if 'macro_disable' not in self.doc.values:self.progress.configure(text=_ui_tr('매크로 사용 설정을 먼저 읽어 주세요.'));return
        if not self.doc.macro_baseline:
            self.after_macro_read=self.new_macro
            self.task('macros',lambda:self.with_client(lambda c:c.read_macros()))
            return
        index=next((i for i in range(32) if str(i) in self.doc.macros and not any(self.doc.macros[str(i)])),None)
        if index is None:self.progress.configure(text=_ui_tr('32개 매크로가 모두 사용 중입니다.'));return
        row=[0]*35;row[11]=27;row[5]=32 if getattr(self,'macro_layer',False) else 0;row[19:35]=_ui_tr('새 매크로 {0}').format(f'{index + 1:02d}').encode('utf-8').ljust(16,b'\0')
        # Keep a new row entirely inside the editor until explicitly committed.
        self.edit_macro(index,initial=row)
    def delete_macro(self,index):
        if self.busy:return
        from studio_dialogs import confirm_delete
        if not confirm_delete(self.parent):return
        self.doc.macros[str(index)]=[0]*35
        if 'macro_disable' in self.doc.values:self.changed('macro_disable',int(self.doc.values['macro_disable'])|(1<<index))
        self.render_fields()
    def bootloader(self):
        if self.busy or not self.path:return
        from studio_dialogs import confirm_bootloader
        if not confirm_bootloader(self.parent):return
        def op(client):
            if self.cancel.is_set():raise RuntimeError(_ui_tr('취소됨'))
            packet=bytes([0x80,0x66,7])+bytes(61)
            if client.device.send_feature_report(packet)!=64:raise RuntimeError(_ui_tr('부트로더 요청 실패'))
            return {}
        self.resume=False
        def run():self.task('bootloader',lambda:self.with_client(op))
        if self.app.engine:self.app.stop(on_complete=run)
        else:run()
    def export_html(self):
        if not self.loaded:return
        from studio_html_export import profile_html
        name=filedialog.asksaveasfilename(parent=self.parent,defaultextension='.html',initialfile='DS5Light-profile.html',filetypes=[('HTML','*.html')])
        if name:Path(name).write_text(profile_html(self.doc.export_json()),encoding='utf-8')
    def range_row(self,parent,row,f,value,valid,default=None):
        from studio_range import RangeSlider
        from studio_help import label,help_text,reference_point
        from studio_settings_ui import FieldTip
        key=f[1];box=tk.Frame(parent,bg=BG);box.grid(row=row,column=0,columnspan=2,sticky='ew',pady=(4,12));box.columnconfigure(0,weight=1)
        title=self.option_title(box,key,text=_ui_tr('1 가장 약함 · 10 기본') if key=='trigger_reduce' else f[3] if key.startswith(('at_','t2_')) else label(key),foreground=FG if valid else MUTED,wraplength=320)
        title.grid(row=0,column=0,sticky='w',padx=(0,10))
        variable=tk.StringVar(value='' if value is None else format(value,'.5g'));self.vars[key]=variable
        lo,hi=(0,10) if key=='trigger_reduce' else f[5]
        varentry=variable
        if key in ('trigger_reduce','rumble_gain'):
            from studio_scope import trigger_display,trigger_raw
            display=lambda v:trigger_display(v) if key=='trigger_reduce' else v/100
            varentry=tk.StringVar(value='' if value is None else f'{display(value):g}')
            def change(*_):
                if getattr(self,'_syncing_fields',False):return
                try:
                    v=float(varentry.get())
                    if not 1<=v<=(10 if key=='trigger_reduce' else 2):raise ValueError()
                    variable.set(str(trigger_raw(v) if key=='trigger_reduce' else round(v*100)))
                except ValueError:self.invalid[key]=_ui_tr('적응형 트리거 세기는 1~10입니다.') if key=='trigger_reduce' else _ui_tr('일반 진동 세기는 1~2입니다.');self.update_state()
            widget_trace(box,varentry,change)
        valuebox=tk.Frame(box,bg=BG);valuebox.grid(row=0,column=1,sticky='e')
        entry=ttk.Entry(valuebox,style='Studio.TEntry',textvariable=varentry,width=4,justify='right',state='normal' if valid and not self.busy else 'disabled');entry.pack(side='left')
        if key=='inactive_time':tk.Label(valuebox,text=_ui_tr('분'),bg=BG,fg=MUTED).pack(side='left',padx=(5,0))
        if f[2]=='f32':lo=float(lo);hi=float(hi)
        marker,kind=reference_point(key)
        if default is not None:marker,kind=default,_ui_tr('기본')
        slider=RangeSlider(box,variable,lo,hi,enabled=valid and not self.busy,marker=marker,marker_label=kind,
                           trigger=key=='trigger_reduce',display_scale=100 if key=='rumble_gain' else 1,
                           reset_to_marker=key.startswith(('at_','t2_')) and marker is not None and lo<=marker<=hi)
        entry.display_variable = varentry
        self.range_controls[key]=(entry,slider,title)
        self.field_views[key]=(title,[entry,slider],[])
        slider.grid(row=1,column=0,columnspan=2,sticky='ew',pady=(4,0))
        if key=='speaker_volume':
            from studio_volume import estimated_windows_percent
            estimate=tk.Label(title,bg=BG,fg=MUTED,anchor='w',font=(_ui_tr('맑은 고딕'),8))
            estimate.pack(side='left',padx=(8,0))
            def update_estimate(*_):
                from localization import LANGUAGE
                try:percent=str(estimated_windows_percent(int(variable.get())))+'%'
                except ValueError:percent='—'
                estimate.configure(text=(_ui_tr('Windows 예상 음량: 약 {0}') if LANGUAGE=='ko' else 'Estimated Windows volume: ~{0}').format(percent))
            widget_trace(box,variable,update_estimate)
            update_estimate()
        def changed(*_):
            self.number_changed(key,variable.get())
            if key in ('trigger_reduce','rumble_gain'):
                try:
                    shown=f'{slider.display(float(variable.get())):g}'
                    if varentry.get()!=shown:varentry.set(shown)
                except ValueError:pass
        widget_trace(box,variable,changed)
    def render_macro_tools(self):
        box=self.card(_ui_tr('매핑 파일 · 입력 확인'))
        bar=tk.Frame(box,bg=BG);bar.grid(row=1,column=0,columnspan=2,sticky='ew')
        for i,(title,command) in enumerate([(_ui_tr('가져오기'),self.import_macros),(_ui_tr('내보내기'),self.export_macros),(_ui_tr('입력 확인 중지') if self.live_enabled else _ui_tr('실시간 입력 확인'),self.toggle_live)]):
            ttk.Button(bar,text=title,command=command).grid(row=0,column=i,padx=(0,6),sticky='ew');bar.columnconfigure(i,weight=1)
        self.live_text=tk.StringVar(value=_ui_tr('게임에 전달되는 입력과 현재 매핑 처리 상태를 확인합니다. 확인을 켠 동안에만 조회합니다.'))
        tk.Label(box,textvariable=self.live_text,bg=BG,fg=MUTED,wraplength=425,justify='left',anchor='w').grid(row=2,column=0,columnspan=2,sticky='ew',pady=(12,0))
        if self.live_result:self.show_live_result(self.live_result)
    def import_macros(self):
        if self.busy or not self.doc.macro_baseline:
            self.progress.configure(text=_ui_tr('매크로 정의를 먼저 읽으세요.'));return
        name=filedialog.askopenfilename(parent=self.parent,filetypes=[(_ui_tr('매핑·매크로 JSON'),'*.json')])
        if not name:return
        try:
            data=json.loads(Path(name).read_text(encoding='utf-8-sig'));records=macro_records(data.get('macros',{}))
            for record in records.values():normalize_macro(record)
            if not messagebox.askyesno(_ui_tr('공유 매핑 교체'),_ui_tr('모든 프로필이 공유하는 일반 매크로 정의를 편집에 불러옵니다. Pico 매핑·매크로 저장 전에는 전송되지 않습니다. 계속할까요?'),parent=self.parent):return
            # Motion definitions are excluded and remain untouched.
            for key,old in self.doc.macro_baseline.items():
                if not old[4]&16:self.doc.macros[key]=records.get(key,[0]*35)
            self.render_fields()
        except Exception as exc:messagebox.showerror(_ui_tr('매핑 파일'),str(exc),parent=self.parent)
    def export_macros(self):
        if not self.doc.macros:self.progress.configure(text=_ui_tr('매크로 정의를 먼저 읽으세요.'));return
        name=filedialog.asksaveasfilename(parent=self.parent,defaultextension='.json',initialfile='ds5dongle-macros.json',filetypes=[('JSON','*.json')])
        if name:Path(name).write_text(json.dumps(dict(format='ds5dongle-macros',version=1,macros=structured_macros(self.doc.macros)),ensure_ascii=False,indent=2),encoding='utf-8')
    def toggle_live(self):
        from studio_power import blocked
        if blocked(self.app):return
        if self.live_enabled:self.stop_live();self.render_fields();return
        if not self.path or self.busy:return
        self.live_enabled=True;self.monitor=LiveMonitor(self.path);self.monitor.start();self.render_fields();self.live_poll()
    def stop_live(self):
        self.live_enabled=False
        monitor=getattr(self,'monitor',None)
        if monitor:monitor.stop.set()
        if getattr(self,'live_job',None):
            try:self.parent.after_cancel(self.live_job)
            except tk.TclError:pass
        self.live_job=None
    def live_poll(self):
        self.live_job=None
        if not self.live_enabled:return
        from studio_help import GROUPS
        if self.closed or self.app.selected_tab!=2 or GROUPS[self.category][0]!=_ui_tr('매핑·매크로') or not self.parent.winfo_viewable():self.stop_live();return
        try:
            result=self.monitor.results.get_nowait()
            if result.get('error'):self.stop_live();self.live_text.set(_ui_tr('입력 확인 실패 · ')+result['error']);return
            self.live_result=result;self.show_live_result(result)
        except queue.Empty:pass
        self.live_job=self.parent.after(100,self.live_poll)
    def show_live_result(self,result):
        if not hasattr(self,'live_text'):return
        from studio_settings_ui import BUTTONS,OUT_BUTTONS
        d=result.get('diag',{});s=result.get('input')
        names=lambda mask:' + '.join(n for i,n in enumerate(BUTTONS) if mask&(1<<i)) or _ui_tr('없음')
        text=_ui_tr('게임에 전달되는 입력: ')+(names(s['mask']) if s else _ui_tr('입력 보고 대기 중'))
        if s:text+=_ui_tr('\n스틱 L {0}/{1} · R {2}/{3} · 트리거 L {4} / R {5}').format(f"{s['lx']}",f"{s['ly']}",f"{s['rx']}",f"{s['ry']}",f"{s['l2']}",f"{s['r2']}")
        if d:
            hidden=d.get('suppress_low',0)|(d.get('suppress_high',0)<<16);injected=d.get('inject_low',0)|(d.get('inject_high',0)<<16);kb=d.get('keyboard',0)
            outputs=' + '.join(OUT_BUTTONS[i+1] if i+1<len(OUT_BUTTONS) else str(i+1) for i in range(32) if injected&(1<<i)) or _ui_tr('없음')
            sticks=' + '.join(name for bit,name in [(1,_ui_tr('왼쪽 스틱')),(2,_ui_tr('오른쪽 스틱'))] if d.get('stick',0)&bit)
            mouse=' + '.join(name for bit,name in [(1,_ui_tr('왼쪽')),(2,_ui_tr('오른쪽')),(4,_ui_tr('가운데'))] if ((kb>>4)&15)&bit) or _ui_tr('없음')
            text+=_ui_tr('\n현재 매핑 처리 상태 (약 1초 간격):\n게임에서 숨긴 입력: ')+names(hidden)+(' · '+sticks if sticks else '')
            text+=_ui_tr('\n전달한 버튼: ')+outputs+_ui_tr(' · 키보드 {0}키 · 마우스 {1}').format(f'{kb & 15}',f'{mouse}')
            text+=_ui_tr('\n게임 입력 치환: ')+(_ui_tr('적용 중') if d.get('stick',0)&4 else _ui_tr('꺼짐'))
        self.live_text.set(text)
    def record_keys(self,parent,variables,release):
        editor=getattr(self,'macro_editor',None)
        if editor and not editor.closed:editor.start_capture('keys')
    def record_buttons(self,parent,checks):
        editor=getattr(self,'macro_editor',None)
        if editor and not editor.closed:editor.start_capture('input')
