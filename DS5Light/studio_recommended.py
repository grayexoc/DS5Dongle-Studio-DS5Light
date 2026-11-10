"""User-selected recommended presets. No writes occur while displaying cards."""
from studio_i18n import text as _ui_tr
import copy,json,math,sys,tkinter as tk
from pathlib import Path
from tkinter import ttk
from studio_dialogs import messagebox
from studio_fields import FIELDS
from studio_scope import EDITABLE,SUPPORTED_CONFIGS
from studio_settings_protocol import needs_reconnect,validate_changes
from studio_document import SettingsDocument

# Exactly the editable fields shown in Studio's "오디오햅틱" section.
# Device/audio-buffer settings, native gain/filtering and macro definitions or
# enable masks are deliberately outside this preset's scope.
AUDIO_HAPTIC_FIELDS=frozenset((
    'auto_haptics_enable','auto_haptics_gain','auto_haptics_smooth','auto_haptics_gate',
    'mix_native_level','mix_native_filter','ah_dsp_source','auto_haptics_lowpass_hz',
    'ah_xover_hz','ah_low_gain','ah_high_gain','auto_haptics_slope',
    'auto_mute_replace','auto_mute_mix','rumble_haptic_strength',
))

PRESETS=(
    ('DS_Native.json',_ui_tr('네이티브 프리셋'),
     _ui_tr('별도 설정을 하지 않았다면 기본값과 같아 적용할 필요가 없습니다. 오디오햅틱을 끄고 게임의 네이티브 햅틱·일반 진동을 사용합니다. 게임·연결 방식이 지원해야 하며 DS5Light 전송은 정지합니다.')),
    ('Audio_Haptic_01.json',_ui_tr('오디오햅틱 안정형'),
     _ui_tr('배경 반응을 줄이는 안정형입니다. 작은 소리 차단 25, 기울기 24dB, 대역 분리 50Hz를 사용합니다. 약한 효과음도 줄 수 있으며 음악·대사를 따로 구분하지는 못합니다.')),
    ('Audio_Haptic_02.json',_ui_tr('오디오햅틱 반응형'),
     _ui_tr('안정형보다 반응을 살립니다. 작은 소리 차단 16, 부드러움 32, 저역 통과 100Hz, 대역 분리 60Hz, 고음 세기 60%입니다. 배경음에도 반응하며 음악·대사를 따로 구분하지는 못합니다.')),
)
COMMON_HELP=_ui_tr('\n\n현재 Pico 설정에서 Studio의 오디오햅틱 항목만 추천값으로 바꿔 선택한 슬롯에 저장합니다. 장치·자이로·트리거 등 다른 설정과 매크로는 유지합니다.')


def load_preset(filename):
    if filename not in {p[0] for p in PRESETS}:raise ValueError(_ui_tr('알 수 없는 추천 프리셋입니다.'))
    root=Path(sys.executable).resolve().parent if getattr(sys,'frozen',False) else Path(__file__).resolve().parent
    data=json.loads((root/'Studio Presert'/filename).read_text(encoding='utf-8-sig'))
    if data.get('cfgVersion') not in SUPPORTED_CONFIGS:raise ValueError(_ui_tr('추천 프리셋의 설정 버전이 맞지 않습니다.'))
    fields=data.get('fields')
    if not isinstance(fields,dict) or fields!=data.get('settings'):raise ValueError(_ui_tr('추천 프리셋의 중복 설정값이 일치하지 않습니다.'))
    # An explicit allowlist prevents later edits to a JSON file from importing
    # device settings, native haptics settings or global/profile macro data.
    fields={k:v for k,v in fields.items() if k in AUDIO_HAPTIC_FIELDS and k in EDITABLE}
    if set(fields)!=AUDIO_HAPTIC_FIELDS:raise ValueError(_ui_tr('추천 프리셋의 오디오햅틱 설정이 누락되었습니다.'))
    validate_changes({},fields)
    name=data.get('name','')
    if not isinstance(name,str) or not name or '\x00' in name or len(name.encode('utf-8'))>16:raise ValueError(_ui_tr('추천 프리셋 이름이 올바르지 않습니다.'))
    return ('Audio Haptic 02' if filename=='Audio_Haptic_02.json' else name),fields


def equal_value(a,b):
    if isinstance(a,int) and isinstance(b,int):return a==b
    return a is not None and b is not None and math.isclose(a,b,rel_tol=1e-5,abs_tol=1e-5)


def save_and_activate(client,fields,name,index,expected_slot,stamp,baseline,progress):
    """One transaction: verify, apply, save, activate once, request persistence."""
    if not fields or set(fields)-AUDIO_HAPTIC_FIELDS:
        raise ValueError(_ui_tr('추천 프리셋은 Studio 오디오햅틱 항목만 변경할 수 있습니다.'))
    if client.profile()!=stamp:raise RuntimeError(_ui_tr('현재 프로필이 바뀌었습니다. 새로 고침으로 확인하세요.'))
    slot=client.info(index)
    if (slot.state,slot.name)!=expected_slot:raise RuntimeError(_ui_tr('저장 대상 슬롯이 변경되었습니다. 목록을 새로 고침하세요.'))
    required=set(baseline)|set(fields)|{'macro_disable'}
    current,missing=client.read_fields([FIELDS[k] for k in required])
    if missing or any(k not in current for k in required):raise RuntimeError(_ui_tr('프리셋 적용에 필요한 설정을 모두 읽지 못했습니다.'))
    if any(not equal_value(current[k],v) for k,v in baseline.items()):raise RuntimeError(_ui_tr('외부에서 설정이 변경되었습니다. 새로 고침으로 확인하세요.'))
    mask=current['macro_disable'];validate_changes(current,fields)
    changes={k:v for k,v in fields.items() if not equal_value(current[k],v)}
    progress(_ui_tr('오디오햅틱 추천값 적용 중…'))
    client.write_fields(changes,current)
    expected=dict(current,**fields)
    profile=client.profile()
    if any(profile.get(k)!=stamp.get(k) for k in ('index','name')):raise RuntimeError(_ui_tr('적용 중 프로필이 바뀌었습니다. 다시 조회하세요.'))
    if client.read_one(FIELDS['macro_disable'])!=mask:raise RuntimeError(_ui_tr('매크로 사용 체크가 외부에서 변경되었습니다. 다시 조회하세요.'))
    slot=client.info(index)
    if (slot.state,slot.name)!=expected_slot:raise RuntimeError(_ui_tr('저장 대상 슬롯이 변경되었습니다. 다시 조회하세요.'))
    progress(_ui_tr('{0} · {1}에 저장 중…').format(f'{index + 1:02d}',f'{name}'))
    client.save_slot(index,name)
    profile=client.profile()
    if profile.get('index')!=index or profile.get('name')!=name or profile.get('edited'):
        raise RuntimeError(_ui_tr('슬롯 저장 상태를 확인하지 못했습니다. 다시 조회하세요.'))
    result=dict(index=index,name=name,expected=expected,mask=mask,verified=False,reconnect=False)
    progress(_ui_tr('저장된 프로필로 전환 중…'))
    try:activation=client.activate(index)  # Never retry an ambiguous activation.
    except (OSError,TimeoutError) as exc:
        result['notice']=_ui_tr('슬롯 저장 확인 · 전환 응답 미확인 · 새로 고침으로 확인하세요.')
        return result
    result['reconnect']=bool(activation.get('reconnect') or activation.get('deferred') or needs_reconnect(current,expected))
    progress(_ui_tr('Pico 저장 확인 중 · 다른 앱의 Pico 오디오 출력을 중지하세요.'))
    try:client.save_flash()
    except (OSError,TimeoutError) as exc:
        result['notice']=_ui_tr('슬롯 저장 확인 · ')+str(exc)
        return result
    if result['reconnect']:
        try:client.reconnect_usb()  # State queries, not a second reset, recover.
        except (OSError,RuntimeError):
            if client.cancel():raise
    return result


class RecommendedPresets:
    def render_recommended_presets(self):
        box=self.card(_ui_tr('추천 프리셋'))
        if not hasattr(self,'recommended_slots'):self.recommended_slots={}
        selected_file=getattr(self,'recommended_selection',None)
        available=[s for s in self.slots if s.state in ('saved','empty')]
        labels=[s.label() for s in available]
        cards=tk.Frame(box,bg='#151515');cards.grid(row=1,column=0,columnspan=2,sticky='ew',pady=(0,12))
        self.recommended_boxes={}
        for n,(filename,title,help_text) in enumerate(PRESETS):
            cards.columnconfigure(n,weight=1,uniform='recommended_presets')
            active=filename==selected_file;surface='#302819' if active else '#1b1a17'
            card=tk.Frame(cards,bg=surface,highlightthickness=1,highlightbackground='#d6ad52' if active else '#363126',
                          highlightcolor='#d6ad52' if active else '#827c6f',takefocus=not self.busy,cursor='hand2',padx=10,pady=10)
            card.grid(row=0,column=n,sticky='nsew',padx=(0,6) if n<2 else 0);card.columnconfigure(0,weight=1)
            title_label=tk.Label(card,text=title,bg=surface,fg='#d6ad52' if active else '#eee9df',width=1,
                                 font=(_ui_tr('맑은 고딕'),9,'bold'),anchor='center',justify='center',cursor='hand2')
            title_label.grid(row=0,column=0,sticky='ew');title_label.bind('<Configure>',self.fit_slot_label)
            self.help_icon(card,help_text+COMMON_HELP).grid(row=0,column=1,padx=(4,0))
            # Child help canvases have their own bindtags: clicking the question
            # mark only opens help and cannot select its parent preset card.
            for widget in (card,title_label):
                widget.bind('<Button-1>',lambda event,f=filename:self.select_recommended(f))
            card.bind('<Return>',lambda event,f=filename:self.select_recommended(f))
            card.bind('<space>',lambda event,f=filename:self.select_recommended(f))
            self.recommended_boxes[filename]=card
        controls=tk.Frame(box,bg='#151515');controls.grid(row=2,column=0,columnspan=2,sticky='ew');controls.columnconfigure(1,weight=1)
        tk.Label(controls,text=_ui_tr('저장 슬롯'),bg='#151515',fg='#aaa393').grid(row=0,column=0,padx=(0,8))
        choice=self.recommended_choice=ttk.Combobox(controls,values=labels,
                    state='readonly' if selected_file and available and not self.busy else 'disabled',width=12,justify='right')
        choice.grid(row=0,column=1,sticky='ew',padx=(0,10))
        selected=self.recommended_slots.get(selected_file) if selected_file else None
        position=next((i for i,s in enumerate(available) if s.index==selected),None)
        if position is not None:choice.current(position)
        else:choice.set(_ui_tr('프리셋을 먼저 선택하세요') if not selected_file else _ui_tr('슬롯 선택') if available else _ui_tr('슬롯 목록 조회 필요'))
        button=self.recommended_use_button=ttk.Button(controls,text=_ui_tr('저장 후 사용'),style='Accent.TButton',width=0,padding=(12,6),
                        command=lambda:self.apply_recommended(self.recommended_selection),
                        state='normal' if self.loaded and self.write_ready and not self.busy and selected_file and position is not None else 'disabled')
        button.grid(row=0,column=2,sticky='e')
        def choose(event):
            i=choice.current()
            if selected_file and 0<=i<len(available):
                self.recommended_slots[selected_file]=available[i].index
                button.configure(state='normal' if self.loaded and self.write_ready and not self.busy else 'disabled')
        choice.bind('<<ComboboxSelected>>',choose)

    def select_recommended(self,filename):
        if self.busy or filename not in {p[0] for p in PRESETS}:return
        if filename!=getattr(self,'recommended_selection',None):
            self.recommended_slots.pop(filename,None)
        self.recommended_selection=filename
        self.render_fields()

    def apply_recommended(self,filename):
        if self.busy or self.app.studio.busy or not self.loaded or not self.write_ready:return
        index=getattr(self,'recommended_slots',{}).get(filename)
        slot=next((s for s in self.slots if s.index==index and s.state in ('empty','saved')),None)
        if slot is None:self.progress.configure(text=_ui_tr('저장할 슬롯을 먼저 선택하세요.'));return
        try:name,fields=load_preset(filename)
        except (OSError,ValueError) as exc:messagebox.showerror(_ui_tr('추천 프리셋'),str(exc),parent=self.parent);return
        def proceed():
            if slot.state=='saved' and not messagebox.askyesno(_ui_tr('추천 프리셋 저장'),_ui_tr('{0} · {1}을 {2}으로 덮어쓰고 사용하겠습니까?\n현재 Pico 설정에서 오디오햅틱 값만 바꿔 저장합니다. 대상 슬롯의 다른 설정을 유지하는 방식은 아닙니다.').format(f'{index + 1:02d}',f"{slot.name or '이름 없음'}",f'{name}'),parent=self.parent):return
            self.begin_recommended(fields,name,index,(slot.state,slot.name))
        self.request_profile_switch(proceed)

    def begin_recommended(self,fields,name,index,expected_slot):
        stamp=copy.deepcopy(self.profile_stamp);baseline=dict(self.doc.baseline);path=self.path
        if self.busy or not self.write_ready or stamp is None:return
        serial=next((d.get('serial_number') for d in self.device_rows if d['path']==path),None) or self.app.studio.device_serials.get(path)
        def progress(text):self.results.put(('progress',text,None))
        def operation():
            result=self.with_client(lambda c:save_and_activate(c,fields,name,index,expected_slot,stamp,baseline,progress))
            result['old_path']=path
            if result.get('notice'):return result
            from studio_reconnect import wait_for_macros
            self.results.put(('progress',dict(reconnecting=True),None))
            try:
                fresh=wait_for_macros(path,serial,self.cancel)
                profile=fresh['profile']
                if profile.get('index')!=index or profile.get('name')!=name or profile.get('edited'):
                    raise RuntimeError(_ui_tr('전환 후 프로필이 저장 대상과 다릅니다.'))
                if any(not equal_value(fresh['values'].get(k),v) for k,v in fields.items()) or fresh['values'].get('macro_disable')!=result['mask']:
                    raise RuntimeError(_ui_tr('프리셋 또는 매크로 사용 체크의 조회값이 다릅니다.'))
                result.update(reloaded=fresh,verified=True)
            except Exception as exc:result['notice']=_ui_tr('슬롯 저장 후 상태 확인 필요 · ')+str(exc)
            return result
        self.app.studio.binding.expect_reconnect()
        self.stopped_task('recommended',operation)

    def finish_recommended(self,result):
        if not result.get('verified'):
            self.resume=False;self.uncertain=True;self.write_ready=False
            self.progress.configure(text=result.get('notice',_ui_tr('저장·전환 상태를 다시 조회하세요.')),kind='warning');return
        fresh=result['reloaded'];self.doc=SettingsDocument();self.invalid.clear();self.uncertain=False;self.external_stale=False
        from studio_slots import Slot
        self.slots=[Slot(s.index,'saved',result['name']) if s.index==result['index'] else s for s in self.slots]
        panel=self.app.studio
        for i,slot in enumerate(panel.slots):
            if panel.slot_paths[i] in (result.get('old_path'),fresh['path']):
                panel.slot_paths[i]=fresh['path']
                if slot.index==result['index']:panel.slots[i]=Slot(slot.index,'saved',result['name'])
        self.profile_stamp=None;self.merge_entry_snapshot(fresh)
        self.doc.macros=copy.deepcopy(fresh['macros']);self.doc.macro_baseline=copy.deepcopy(fresh['macros'])
        self.doc.unsaved=False;self.doc.save_requested=True;self.profile_save_needed=False
        self.app.studio.catalog_invalid=True;self.app.studio.last_read=-1e9
        if fresh['values'].get('auto_haptics_enable')==0:self.resume=False
        self.progress.configure(text=_ui_tr('{0} · {1} 저장·전환 확인 · 시작 설정 저장 확인').format(f"{result['index'] + 1:02d}",f"{result['name']}"),kind='info')
