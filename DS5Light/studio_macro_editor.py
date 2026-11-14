"""Two-step local macro editor with verified Pico save on completion."""
from studio_i18n import text as _ui_tr
import tkinter as tk
import copy
from tkinter import ttk
from itertools import permutations
from studio_macro_design import MacroDraft,KINDS,CONDITIONS,OUTPUTS,conflicts
from studio_shift import POWER_OFF
from studio_range import RangeSlider
from ui_controls import AutoScrollbar,widget_trace
from studio_macro_capture import InlineCapture
from controller_glyphs import ControllerChoice,GlyphStrip

BG='#0b0b0b';CARD='#151515';FG='#eee9df';MUTED='#aaa393';GOLD='#d6ad52'

class MacroEditor(InlineCapture):
    def __init__(self,ui,index,embedded=False,initial=None):
        from studio_settings_ui import BUTTONS,OUT_BUTTONS,HID_KEYS,CircleCheck
        self.ui=ui;self.index=index;self.draft=MacroDraft(initial if initial is not None else ui.doc.macros[str(index)])
        self.profile_stamp=copy.deepcopy(ui.profile_stamp);self.device_path=ui.path
        self.BUTTONS=BUTTONS;self.HID_KEYS=HID_KEYS
        self.OUT_BUTTONS=list(OUT_BUTTONS)+[_ui_tr('프로필 {0}번').format(i) for i in range(1,9)]
        self.OUT_BUTTONS.extend(['',_ui_tr('듀얼센스 전원')])  # Shift marker, then power output.
        OUT_BUTTONS=self.OUT_BUTTONS
        self.updating=False;self.closed=False;self.step=0;self.step_hosts=[]
        old=self.draft.initial
        self.embedded=embedded
        if embedded:
            self.dialog=d=tk.Frame(ui.editor_holder,bg=BG);d.grid(row=0,column=0,sticky='nsew')
        else:
            self.dialog=d=tk.Toplevel(ui.parent);d.transient(ui.parent.winfo_toplevel());d.grab_set()
            d.title(_ui_tr('매크로 {0} · 입력과 동작').format(f'{index + 1:02d}'));d.configure(bg=BG);d.resizable(True,True)
            width=min(760,d.winfo_screenwidth()-80);height=min(900,d.winfo_screenheight()-120)
            d.geometry(f'{width}x{height}');d.minsize(min(640,width),min(420,height))
            from app import apply_windows_titlebar_theme
            d.bind('<Map>',lambda event:d.after_idle(lambda:apply_windows_titlebar_theme(d)) if event.widget is d else None,add='+')
        d.columnconfigure(0,weight=1);d.rowconfigure(1,weight=1)
        top=self.top=tk.Frame(d,bg=BG,padx=18,pady=14);top.grid(row=0,column=0,sticky='ew');top.columnconfigure(1,weight=1)
        self.name=tk.StringVar(value=old['name'])
        self.caption(top,_ui_tr('이름'),_ui_tr('모든 프로필이 공유하는 매크로 이름입니다. UTF-8 기준 16바이트까지 저장합니다.')).grid(row=0,column=0,padx=(0,12))
        ttk.Entry(top,style='Studio.TEntry',textvariable=self.name).grid(row=0,column=1,sticky='ew')
        activation=tk.Frame(top,bg=BG);activation.grid(row=1,column=0,columnspan=2,sticky='w',pady=(8,0))
        tk.Label(activation,text=_ui_tr('완료하면 Pico에 저장하고 현재 프로필의 사용 체크를 자동 선택합니다.'),bg=BG,fg=MUTED,wraplength=560,justify='left').pack(side='left')
        ui.help_icon(activation,_ui_tr('매핑 동작은 모든 프로필이 공유합니다. Pico 저장 확인 후 현재 프로필에 사용 여부를 저장할지 묻습니다. 다른 프로필에서 이미 사용하는 동작을 수정하면 그 프로필에도 반영됩니다.')).pack(side='left',padx=5)
        layerbar=tk.Frame(top,bg=BG);layerbar.grid(row=5,column=0,columnspan=2,sticky='w',pady=6)
        self._layerbar=layerbar
        stepbar=tk.Frame(top,bg=BG);stepbar.grid(row=2,column=0,columnspan=2,sticky='ew',pady=(12,0));self.step_buttons=[]
        for i,text in enumerate((_ui_tr('⌘ 실행 조건'),_ui_tr('▶ 실행 동작'))):
            button=ttk.Button(stepbar,text=text,command=lambda i=i:self.go_step(i),style='Filter.TButton');button.grid(row=0,column=i,sticky='ew',padx=(0,6));stepbar.columnconfigure(i,weight=1);self.step_buttons.append(button)
        self.summary=tk.StringVar(value=_ui_tr('입력과 실행할 동작을 선택하세요.'))
        tk.Label(top,textvariable=self.summary,bg=BG,fg=GOLD,wraplength=660,anchor='w',justify='left').grid(row=3,column=0,columnspan=2,sticky='ew',pady=(10,0))
        self.build_capture(top,4)
        host=tk.Frame(d,bg=BG);host.grid(row=1,column=0,sticky='nsew',padx=18);host.columnconfigure(0,weight=1);host.rowconfigure(0,weight=1)
        self.canvas=tk.Canvas(host,bg=BG,highlightthickness=0,width=1,height=450)
        self.scroll=AutoScrollbar(host,orient='vertical',command=self.canvas.yview);self.canvas.configure(yscrollcommand=self.scroll.set)
        self.canvas.grid(row=0,column=0,sticky='nsew');self.scroll.grid(row=0,column=1,sticky='ns')
        self.body=tk.Frame(self.canvas,bg=BG);self.window=self.canvas.create_window(0,0,window=self.body,anchor='nw')
        self.canvas.bind('<Configure>',self.resize_canvas)
        self.body.bind('<Configure>',self.sync_scrollregion)
        d.bind('<MouseWheel>',self.wheel,add='+')
        if not embedded:d.protocol('WM_DELETE_WINDOW',self.close)
        d.bind('<Destroy>',self.destroyed,add='+')
        # Values use the original firmware representation. UI labels are separate.
        self.kind=tk.StringVar(value=KINDS[old['kind']]);self.mode=tk.StringVar(value=CONDITIONS[old['condition']])
        self.output_kind=tk.StringVar(value=OUTPUTS[old['output_kind']]);self.output=tk.StringVar(value=OUT_BUTTONS[old['output']] if old['output']<len(OUT_BUTTONS) else '')
        self.hold=tk.StringVar(value=str(old['hold']));self.threshold=tk.StringVar(value=str(old['threshold'] or 48));self.release=tk.StringVar(value=str(old['release']))
        self.hide=tk.BooleanVar(value=old['hide']);self.always=tk.BooleanVar(value=old['always'])
        self.layer=tk.BooleanVar(value=old['layer']);self.chime=tk.BooleanVar(value=old['chime'])
        CircleCheck(self._layerbar,text=_ui_tr('시프트 레이어에서 사용'),variable=self.layer,command=lambda:None,background=BG).pack(side='left')
        self.buttons=[tk.BooleanVar(value=bool(old['chord']&(1<<i))) for i in range(len(BUTTONS))]
        self.keys=[tk.StringVar(value=next((k for k,v in HID_KEYS.items() if v==code),f'HID {code}')) for code in old['keys']]
        self.gestures={_ui_tr('왼쪽 스틱'):160,_ui_tr('오른쪽 스틱'):224}
        self.gestures.update({_ui_tr('{0} · {1}손가락 · {2}').format(f'{zone}',f'{fingers}',f'{direction}'):128|z|f|i for zone,z in [(_ui_tr('터치 왼쪽'),0),(_ui_tr('터치 오른쪽'),4)] for fingers,f in [(1,0),(2,8)] for i,direction in enumerate([_ui_tr('위'),_ui_tr('아래'),_ui_tr('왼쪽'),_ui_tr('오른쪽')])})
        self.gesture=tk.StringVar(value=next((k for k,v in self.gestures.items() if v==old['gesture']),_ui_tr('왼쪽 스틱')))
        one=self.card(_ui_tr('⌘ 실행 조건'));kindbar=tk.Frame(one,bg=CARD);self.kind_buttons=[]
        for i,(key,title) in enumerate(KINDS.items()):
            button=ttk.Button(kindbar,text=title,command=lambda title=title:self.kind.set(title),style='Filter.TButton');button.grid(row=0,column=i,sticky='ew',padx=(0,5));kindbar.columnconfigure(i,weight=1,uniform='kind');self.kind_buttons.append((title,button))
        self.form(one,1,_ui_tr('입력 종류'),_ui_tr('버튼 하나·조합, 스틱 방향, 터치패드 스와이프 중 실행할 입력을 고릅니다.'),kindbar)
        self.button_area=tk.Frame(one,bg=CARD);self.button_area.grid(row=2,column=0,columnspan=2,sticky='ew',pady=8)
        self.input_summary=tk.StringVar();tk.Label(self.button_area,textvariable=self.input_summary,bg=CARD,fg=GOLD,anchor='w',wraplength=540).pack(fill='x')
        self.input_glyphs=GlyphStrip(self.button_area);self.input_glyphs.pack(anchor='w',pady=(4,0))
        from studio_button_names import NAMES
        self.button_names=NAMES
        bar=tk.Frame(self.button_area,bg=CARD);bar.pack(fill='x',pady=6);bar.columnconfigure(1,weight=1)
        choice_caption=tk.Frame(bar,bg=CARD);choice_caption.grid(row=0,column=0,padx=(0,10))
        tk.Label(choice_caption,text=_ui_tr('버튼 선택:'),bg=CARD,fg=FG).pack(side='left')
        ui.help_icon(choice_caption,_ui_tr('선택판에서 아이콘과 이름을 보고 여러 버튼을 조합할 수 있습니다. 선택한 버튼을 다시 누르면 해제됩니다. 선택 초기화는 전체 선택을 지웁니다.')).pack(side='left',padx=4)
        self.button_choice=tk.StringVar(value=_ui_tr('버튼을 선택하세요'))
        display_names=[*NAMES[:17], *NAMES[18:23], NAMES[17], *NAMES[23:]]
        self.button_dropdown=ControllerChoice(bar,textvariable=self.button_choice,values=display_names,multiple=True,
            selected=lambda value:self.buttons[self.button_names.index(value)].get())
        self.button_dropdown.grid(row=0,column=1,sticky='ew')
        self.button_dropdown.bind('<<ComboboxSelected>>',self.choose_button)
        ttk.Button(bar,text=_ui_tr('선택 초기화'),command=self.clear_buttons).grid(row=1,column=0,sticky='w',pady=(8,0))
        ttk.Button(bar,text=_ui_tr('버튼 눌러 지정'),command=lambda:self.start_capture('input')).grid(row=1,column=1,sticky='e',pady=(8,0))
        self.ps_shortcut_row=tk.Frame(self.button_area,bg=CARD)
        self.ps_shortcut=tk.BooleanVar(value=bool(ui.doc.values.get('ps_shortcut_enabled')))
        self.ps_shortcut_control=CircleCheck(self.ps_shortcut_row,text=_ui_tr('PS 기본 단축키'),variable=self.ps_shortcut,
                                            command=self.change_ps_shortcut,background=CARD)
        self.ps_shortcut_control.pack(side='left')
        ui.help_icon(self.ps_shortcut_row,_ui_tr('짧게 Win+G · 길게 Win+Tab. PS를 매핑에 쓰려면 끄세요. 변경값은 현재 프로필에 편집되고 임시 적용 또는 저장할 때 Pico에 전송됩니다.')).pack(side='left',padx=5)
        self.gesture_area=tk.Frame(one,bg=CARD);self.gesture_area.columnconfigure(1,weight=1);self.gesture_area.grid(row=3,column=0,columnspan=2,sticky='ew',pady=8)
        self.gesture_control=ControllerChoice(self.gesture_area,textvariable=self.gesture,values=list(self.gestures));self.form(self.gesture_area,0,_ui_tr('방향·동작'),_ui_tr('스틱은 네 방향을 각각 키로 보냅니다. 스와이프는 지정한 방향·터치 위치·손가락 수가 일치할 때 한 번 실행합니다.'),self.gesture_control)
        self.mode_control=self.combo(one,self.mode,list(CONDITIONS.values()));self.form(one,4,_ui_tr('누르는 방식'),_ui_tr('길게 누르기·두 번 누르기·유지 중 하나만 선택합니다. 스틱은 유지, 스와이프는 단발 동작을 사용합니다.'),self.mode_control)
        self.mode_widgets=one.grid_slaves(row=4)
        self.swipe_click_row=tk.Frame(one,bg=CARD)
        self.swipe_click_row.grid(row=4,column=0,columnspan=2,sticky='ew',pady=6)
        CircleCheck(self.swipe_click_row,text=_ui_tr('터치패드 클릭 차단'),variable=self.hide,command=lambda:None,background=CARD).pack(anchor='w')
        tk.Label(self.swipe_click_row,text=_ui_tr('게임으로 전달되는 물리 클릭을 차단합니다. Pico의 클릭 매핑은 계속 작동합니다.'),bg=CARD,fg=MUTED,wraplength=480,justify='left').pack(anchor='w',pady=4)

        two=self.card(_ui_tr('▶ 실행 동작'));self.output_kind_control=tk.Frame(two,bg=CARD);self.output_kind_buttons=[]
        for i,title in enumerate(OUTPUTS.values()):
            button=ttk.Button(self.output_kind_control,text=title,command=lambda title=title:self.output_kind.set(title),style='Filter.TButton')
            button.grid(row=0,column=i,sticky='ew',padx=(0,5))
            self.output_kind_control.columnconfigure(i,weight=1,uniform='out')
            self.output_kind_buttons.append((title,button))
        self.form(two,1,_ui_tr('출력 종류'),_ui_tr('스틱 방향 매핑은 키보드로 출력합니다.'),self.output_kind_control)
        self.output_area=tk.Frame(two,bg=CARD);self.output_area.columnconfigure(1,weight=1);self.output_area.grid(row=2,column=0,columnspan=2,sticky='ew')
        self.output_control=ControllerChoice(self.output_area,textvariable=self.output,values=[]);self.form(self.output_area,0,_ui_tr('실행할 동작'),_ui_tr('원래 버튼 대신 보낼 단일 버튼 또는 마우스 동작입니다. 듀얼센스 출력 조합키는 현재 펌웨어 형식에서 지원하지 않습니다.'),self.output_control)
        self.output_record=ttk.Button(self.output_area,text=_ui_tr('버튼 눌러 지정'),command=lambda:self.start_capture('output'));self.output_record.grid(row=1,column=1,sticky='e',pady=6)
        self.chime_area=tk.Frame(two,bg=CARD);self.chime_area.grid(row=5,column=0,columnspan=2,sticky='ew',pady=8)
        CircleCheck(self.chime_area,text=_ui_tr('전환 신호음'),variable=self.chime,command=lambda:None,background=CARD).pack(side='left')
        ttk.Button(self.chime_area,text=_ui_tr('미리듣기'),command=self.preview_chime).pack(side='left',padx=10)
        tk.Label(self.chime_area,text=_ui_tr('듀얼센스 스피커 · 프로필 스피커 음량 적용'),bg=CARD,fg=MUTED).pack(side='left')
        self.key_area=tk.Frame(two,bg=CARD);self.key_area.grid(row=3,column=0,columnspan=2,sticky='ew',pady=8)
        self.key_controls=[];self.key_captions=[]
        for i,var in enumerate(self.keys):
            cell=tk.Frame(self.key_area,bg=CARD);cell.grid(row=0,column=i,sticky='ew',padx=(0,8));self.key_area.columnconfigure(i,weight=1)
            header=tk.Frame(cell,bg=CARD);header.pack(anchor='w')
            caption=tk.Label(header,text=_ui_tr('키 {0}').format(f'{i + 1}'),bg=CARD,fg=MUTED);caption.pack(side='left');self.key_captions.append(caption)
            ui.help_icon(header,_ui_tr('일반 키와 Ctrl·Shift·Alt·Win을 같은 입력 칸에 지정합니다. 조합은 최대 4키이며 스틱 방향 매핑은 위·오른쪽·아래·왼쪽 키를 각각 지정합니다. 목록에 없는 키는 HID 숫자 형식으로 입력할 수 있습니다.')).pack(side='left',padx=(4,0))
            control=self.combo(cell,var,list(HID_KEYS),width=9,editable=True);control.pack(fill='x');self.key_controls.append(control)
        self.record_key_button=ttk.Button(self.key_area,text=_ui_tr('키보드 입력 지정'),command=lambda:self.start_capture('keys'));self.record_key_button.grid(row=1,column=0,columnspan=4,sticky='w',pady=(10,0))
        three=tk.Frame(two,bg=CARD);three.grid(row=4,column=0,columnspan=2,sticky='ew',pady=(12,0));three.columnconfigure(1,weight=1)
        tk.Label(three,text=_ui_tr('동작 규칙'),bg=CARD,fg=GOLD,font=(_ui_tr('맑은 고딕'),10,'bold')).grid(row=0,column=0,columnspan=2,sticky='w',pady=(0,6))
        self.form(three,1,_ui_tr('조건 버튼 전달'),_ui_tr('켜면 선택한 버튼은 게임에 보내지 않고 지정한 동작만 보냅니다. 예를 들어 L3를 R3로 바꾸면 게임에는 R3만 전달됩니다. 누르는 동안 유지에서 사용할 수 있습니다.'),None)
        self.hide_control=CircleCheck(three,text=_ui_tr('조건 버튼 숨기기'),variable=self.hide,command=lambda:None,background=CARD);self.hide_control.grid(row=1,column=1,sticky='e')
        self.hide_widgets=three.grid_slaves(row=1)
        self.always_control=CircleCheck(three,text=_ui_tr('스틱을 항상 게임에서 숨김'),variable=self.always,command=lambda:None,background=CARD);self.always_control.grid(row=2,column=0,columnspan=2,sticky='w',pady=6)
        self.rules=tk.StringVar();tk.Label(three,textvariable=self.rules,bg=CARD,fg=MUTED,wraplength=560,justify='left').grid(row=3,column=0,columnspan=2,sticky='ew',pady=8)
        self.release_details=tk.Frame(self.key_area,bg=CARD);self.release_details.grid(row=2,column=0,columnspan=4,sticky='ew',pady=(8,0));self.release_details.columnconfigure(1,weight=1)
        self.hold_row=self.numeric(one,5,_ui_tr('길게 누르기 기준'),_ui_tr('1단위는 10ms입니다. 0은 기본 750ms를 사용합니다.'),self.hold,0,255)
        self.threshold_row=self.numeric(one,6,_ui_tr('스틱 작동 경계'),_ui_tr('각 축에서 스틱을 얼마나 기울이면 지정한 키를 누를지 정합니다. 기본값 48은 최대 이동량의 약 38%입니다. 낮추면 조금만 기울여도 작동하고, 높이면 더 많이 기울여야 합니다. 기본값에서는 48 이상에서 작동하고 38 미만으로 돌아오면 해제되어 경계에서 입력이 반복되는 것을 줄입니다.'),self.threshold,10,120,marker=48,marker_label=_ui_tr('기본값'))
        self.orders={' → '.join(str(n+1) for n in p):sum(n<<(2*i) for i,n in enumerate(p)) for p in permutations(range(4))}
        self.release_name=tk.StringVar(value=next((k for k,v in self.orders.items() if v==old['release']),_ui_tr('기존 순서 {0}').format(f"{old['release']}")))
        self.release_row=tk.Frame(self.release_details,bg=CARD);self.release_row.columnconfigure(1,weight=1);self.release_row.grid(row=0,column=0,columnspan=2,sticky='ew')
        control=self.combo(self.release_row,self.release_name,list(self.orders));control.bind('<<ComboboxSelected>>',lambda e:self.release.set(str(self.orders[self.release_name.get()])))
        self.form(self.release_row,0,_ui_tr('키를 놓는 순서'),_ui_tr('숫자는 위 키 입력 칸의 위치입니다. 일반적인 조합은 누른 순서의 역순이며 키보드 기록을 쓰면 해제 순서도 기록합니다.'),control)
        footer=self.footer=tk.Frame(d,bg=BG,padx=18,pady=12);footer.grid(row=2,column=0,sticky='ew');footer.columnconfigure(0,weight=1)
        self.feedback=tk.StringVar();tk.Label(footer,textvariable=self.feedback,bg=BG,fg=GOLD,wraplength=560,justify='right',anchor='e').grid(row=0,column=0,columnspan=2,sticky='ew',pady=(0,10))
        actions=tk.Frame(footer,bg=BG);actions.grid(row=1,column=1,sticky='e')
        ttk.Button(actions,text=_ui_tr('취소'),command=self.close,width=12).pack(side='left',padx=(0,8))
        self.previous=ttk.Button(actions,text=_ui_tr('이전'),command=lambda:self.go_step(self.step-1),width=10);self.previous.pack(side='left',padx=(0,8))
        self.next_button=ttk.Button(actions,text=_ui_tr('다음'),command=lambda:self.go_step(self.step+1),width=14);self.next_button.pack(side='left',padx=(0,8))
        self.save=ttk.Button(actions,text=_ui_tr('완료 · Pico 저장'),command=self.commit,width=18,style='Accent.TButton');self.save.pack(side='left')
        self.variables=[self.name,self.kind,self.mode,self.output_kind,self.output,self.hold,self.threshold,self.release,self.hide,self.always,self.layer,self.chime,self.gesture,*self.buttons,*self.keys]
        for variable in self.variables:widget_trace(d,variable,self.refresh)
        self.last_kind=old['kind'];self.last_output_kind=old['output_kind'];self.refresh()
    def preview_chime(self):
        if self.ui.busy:return
        self.ui.task('chime_preview',lambda:self.ui.with_client(lambda client:client.macro_features(preview=True)))

    def caption(self,parent,text,help_text):
        box=tk.Frame(parent,bg=parent.cget('bg'));tk.Label(box,text=text,bg=parent.cget('bg'),fg=FG,anchor='w').pack(side='left')
        self.ui.help_icon(box,help_text).pack(side='left',padx=(5,0));return box
    def card(self,title):
        card=self.ui.make_card(self.body,16);self.step_hosts.append(card);card.pack(fill='x',pady=(0,12));box=card.content;box.columnconfigure(1,weight=1)
        tk.Label(box,text=title,bg=CARD,fg=GOLD,font=(_ui_tr('맑은 고딕'),11,'bold'),anchor='w').grid(row=0,column=0,columnspan=2,sticky='w',pady=(0,10));return box
    def form(self,parent,row,text,tip,control):
        self.caption(parent,text,tip).grid(row=row,column=0,sticky='w',padx=(0,14),pady=6)
        if control:control.grid(row=row,column=1,sticky='ew',pady=6)
    def combo(self,parent,var,values,width=24,editable=False):
        return ttk.Combobox(parent,textvariable=var,values=values,width=width,justify='right',state='normal' if editable else 'readonly')
    def numeric(self,parent,row,text,tip,var,low,high,allowed=None,marker=0,marker_label=_ui_tr('기본')):
        box=tk.Frame(parent,bg=CARD);box.columnconfigure(0,weight=1);box.grid(row=row,column=0,columnspan=2,sticky='ew',pady=6)
        self.caption(box,text,tip).grid(row=0,column=0,sticky='w');ttk.Entry(box,style='Studio.TEntry',textvariable=var,width=4,justify='right').grid(row=0,column=1,sticky='e')
        RangeSlider(box,var,low,high,marker=marker,marker_label=marker_label,allowed=allowed).grid(row=1,column=0,columnspan=2,sticky='ew');return box
    def wheel(self,event):
        if not isinstance(event.widget,(ttk.Combobox,ttk.Entry)):
            self.canvas.yview_scroll(-int(event.delta/120),'units')
        return 'break' # Stop the underlying settings page's global wheel binding.
    def choose_button(self,event=None):
        name=self.button_choice.get()
        if name in self.button_names:
            index=self.button_names.index(name);self.buttons[index].set(not self.buttons[index].get())
        self.button_choice.set(_ui_tr('버튼을 선택하세요'))
    def clear_buttons(self):
        for variable in self.buttons:variable.set(False)
    def ps_shortcut_writable(self):
        ui=self.ui
        return ('ps_shortcut_enabled' in ui.doc.values and ui.loaded and ui.write_ready
                and not ui.busy and not ui.transfer_locked and not ui.external_stale and not ui.uncertain)

    def sync_ps_shortcut(self):
        self.ps_shortcut.set(bool(self.ui.doc.values.get('ps_shortcut_enabled')))
        self.ps_shortcut_control.set_enabled(self.ps_shortcut_writable())

    def change_ps_shortcut(self):
        if self.ps_shortcut_writable():
            self.ui.changed('ps_shortcut_enabled',int(self.ps_shortcut.get()))
        self.sync_ps_shortcut()
        self.refresh()
    def threshold_value(self):
        value=int(self.threshold.get())
        if not 10<=value<=120:raise ValueError(_ui_tr('스틱 작동 경계는 10~120으로 지정하세요.'))
        return 0 if value==48 and self.draft.initial['threshold']==0 else value
    def state(self):
        kind=next(k for k,v in KINDS.items() if v==self.kind.get());outkind=next(k for k,v in OUTPUTS.items() if v==self.output_kind.get())
        keys=tuple(self.HID_KEYS[v.get()] if v.get() in self.HID_KEYS else int(v.get().removeprefix('HID ')) for v in self.keys)
        known=sum(1<<i for i,var in enumerate(self.buttons) if var.get());unknown=self.draft.initial['chord']&~((1<<len(self.buttons))-1)
        return dict(name=self.name.get(),kind=kind,gesture=0 if kind=='button' else self.gestures[self.gesture.get()],chord=known|unknown,
            condition=next(k for k,v in CONDITIONS.items() if v==self.mode.get()),hold=int(self.hold.get()),output_kind=outkind,
            output=0 if outkind=='keyboard' else self.OUT_BUTTONS.index(self.output.get()),keys=keys,release=int(self.release.get()),threshold=self.threshold_value(),hide=self.hide.get(),always=self.always.get(),layer=self.layer.get(),chime=self.chime.get())
    def refresh(self,*_):
        if self.updating or self.closed:return
        self.updating=True
        try:
            kind=next(k for k,v in KINDS.items() if v==self.kind.get());outkind=next(k for k,v in OUTPUTS.items() if v==self.output_kind.get())
            if kind!=self.last_kind:
                self.stop_capture()
                if kind=='button':self.mode.set(CONDITIONS['tap'])
                elif kind=='stick':self.mode.set(CONDITIONS['hold']);self.gesture.set(_ui_tr('왼쪽 스틱'));self.output_kind.set(OUTPUTS['keyboard']);outkind='keyboard'
                else:self.mode.set(CONDITIONS['tap']);self.gesture.set(_ui_tr('터치 왼쪽 · 1손가락 · 위'))
                self.last_kind=kind
            self.button_area.grid() if kind=='button' else self.button_area.grid_remove()
            if kind=='button' and self.buttons[16].get() and 'ps_shortcut_enabled' in self.ui.doc.values:
                self.ps_shortcut_row.pack(anchor='w',pady=(0,6))
                self.sync_ps_shortcut()
            else:self.ps_shortcut_row.pack_forget()
            self.gesture_area.grid_remove() if kind=='button' else self.gesture_area.grid()
            self.gesture_control.configure(values=[name for name,value in self.gestures.items() if bool(value&32)==(kind=='stick')])
            self.mode_control.configure(state='readonly' if kind=='button' else 'disabled')
            for widget in self.mode_widgets:
                widget.grid_remove() if kind=='swipe' else widget.grid()
            self.swipe_click_row.grid() if kind=='swipe' else self.swipe_click_row.grid_remove()
            for widget in self.hide_widgets:
                widget.grid_remove() if kind=='swipe' else widget.grid()
            for title,button in self.kind_buttons:button.configure(style='Selected.Filter.TButton' if title==self.kind.get() else 'Filter.TButton')
            for title,button in self.output_kind_buttons:button.configure(state='disabled' if kind=='stick' else 'normal',style='Selected.Filter.TButton' if title==self.output_kind.get() else 'Filter.TButton')
            self.input_summary.set(' + '.join(name for name,v in zip(self.button_names,self.buttons) if v.get()) or _ui_tr('실행할 버튼을 선택하세요.'))
            self.input_glyphs.set_values(name for name,v in zip(self.button_names,self.buttons) if v.get())
            self.button_dropdown.refresh()
            indices=list(range(11,16)) if outkind=='mouse' else list(range(23,31)) if outkind=='profile' else [*range(1,11),*range(16,23),POWER_OFF]
            choices=[self.OUT_BUTTONS[i] for i in indices];self.output_control.configure(values=choices)
            if outkind!=self.last_output_kind:
                self.stop_capture()
                if outkind!='keyboard':self.output.set(choices[0])
            self.last_output_kind=outkind
            self.output_area.grid_remove() if outkind=='keyboard' else self.output_area.grid()
            power_selected=outkind=='controller' and self.output.get()==self.OUT_BUTTONS[POWER_OFF]
            if power_selected and self.capture and self.capture['mode']=='output':
                self.stop_capture()
            self.output_record.grid() if outkind=='controller' and not power_selected else self.output_record.grid_remove()
            self.chime_area.grid() if outkind=='profile' else self.chime_area.grid_remove()
            self.key_area.grid() if outkind=='keyboard' else self.key_area.grid_remove()
            self.record_key_button.grid_remove() if kind=='stick' else self.record_key_button.grid()
            for i,caption in enumerate(self.key_captions):caption.configure(text=[_ui_tr('위 ↑'),_ui_tr('오른쪽 →'),_ui_tr('아래 ↓'),_ui_tr('왼쪽 ←')][i] if kind=='stick' else _ui_tr('키 {0}').format(f'{i + 1}'))
            held=self.mode.get()==CONDITIONS['hold'];self.hide_control.set_enabled(held)
            self.always_control.grid() if kind=='stick' else self.always_control.grid_remove();self.always_control.set_enabled(held and self.hide.get())
            has_key_order=outkind=='keyboard' and kind!='stick'
            self.release_details.grid() if has_key_order else self.release_details.grid_remove()
            self.hold_row.grid() if self.mode.get()==CONDITIONS['long'] else self.hold_row.grid_remove()
            self.threshold_row.grid() if kind=='stick' else self.threshold_row.grid_remove()
            self.release_row.grid() if outkind=='keyboard' and kind!='stick' else self.release_row.grid_remove()
            self.rules.set((_ui_tr('입력을 놓으면 유지한 출력을 해제합니다. 조건 버튼 숨기기를 켜도 지정한 동작은 게임에 전달됩니다.') if held else _ui_tr('조건이 맞으면 한 번 실행하고 출력을 해제합니다. 조건 버튼 숨기기는 누르는 동안 유지에서 사용할 수 있습니다.'))+(_ui_tr('\n키보드·마우스로 동작을 보내면 게임 화면의 버튼 안내가 키보드·마우스용으로 바뀔 수 있습니다.') if outkind in ('keyboard','mouse') else ''))
            if kind=='swipe':self.rules.set(_ui_tr('스와이프를 감지하면 지정한 동작을 한 번 실행합니다. 클릭 차단은 이 프로필·레이어에서 해당 매핑이 활성인 동안 계속 적용됩니다.'))
            if power_selected:
                self.rules.set(self.rules.get()+'\n'+_ui_tr('조건이 충족되면 듀얼센스 전원을 끕니다. 실수로 끄지 않으려면 길게 누르기를 선택하세요.'))
            self.rules.set(self.rules.get()+'\n'+_ui_tr('마이크 버튼을 Pico 매핑·시프트로 사용하면 PC로 보내는 기본 음소거 입력과 마이크 LED 표시를 억제합니다. Edge FN 기본 조합과 PS + Create는 사용할 수 없습니다.'))
            self.release_name.set(next((k for k,v in self.orders.items() if v==int(self.release.get())),_ui_tr('기존 순서 {0}').format(f'{self.release.get()}')))
            preview=self.draft.build(self.state());self.summary.set(self.ui.macro_summary(preview).replace('\n',' · '))
            raw=self.draft.build(self.state(),strict=True)
            records=dict(self.ui.doc.macros);records[str(self.index)]=raw;mask=int(self.ui.doc.values.get('macro_disable',0xffffffff))
            mask=mask&~(1<<self.index)
            from studio_shift import reserved_input
            reason=reserved_input(raw,records,mask,bool(self.ui.doc.values.get('ps_shortcut_enabled',0)))
            if reason:raise ValueError(reason)
            warnings=[s for s in conflicts(records,mask) if f'{self.index+1:02d} ·' in s or f'· {self.index+1:02d} ·' in s]
            self.feedback.set('\n'.join(warnings[:2]) or _ui_tr('완료하면 미저장 공용 매핑을 모두 Pico에 저장합니다. 프로필 사용 여부는 다음 확인창에서 저장합니다.'))
            self.save.configure(state='normal' if not self.ui.busy else 'disabled')
        except (ValueError,KeyError,StopIteration) as exc:
            self.feedback.set(str(exc) or _ui_tr('입력과 출력 항목을 확인하세요.'));self.save.configure(state='disabled')
        finally:self.updating=False;self.sync_step()
    def fit_dialog(self):
        if self.closed:return
        self.body.update_idletasks()
        if self.embedded:
            self.sync_scrollregion();return
        d=self.dialog;owner=self.ui.parent.winfo_toplevel()
        width=min(760,d.winfo_screenwidth()-80)
        height=min(d.winfo_screenheight()-100,max(420,self.top.winfo_reqheight()+self.body.winfo_reqheight()+self.footer.winfo_reqheight()+28))
        x=max(0,min(d.winfo_screenwidth()-width-8,owner.winfo_rootx()+owner.winfo_width()-width))
        y=max(0,min(d.winfo_screenheight()-height-48,owner.winfo_rooty()+owner.winfo_height()-height))
        geometry=(width,height,x,y)
        if geometry!=getattr(self,'last_geometry',None):
            self.last_geometry=geometry;d.geometry(f'{width}x{height}+{x}+{y}')
        self.sync_scrollregion()
    def resize_canvas(self,event):
        self.canvas.itemconfigure(self.window,width=event.width)
        if self.embedded and event.width>100:
            def wrap(parent):
                for child in parent.winfo_children():
                    if isinstance(child,tk.Label) and float(str(child.cget('wraplength')))>0:child.configure(wraplength=max(180,event.width-56))
                    wrap(child)
            wrap(self.body)
        self.sync_scrollregion()
    def sync_scrollregion(self,event=None):
        self.canvas.coords(self.window,0,0)
        self.canvas.configure(scrollregion=(0,0,max(1,self.canvas.winfo_width()),max(self.body.winfo_reqheight(),self.canvas.winfo_height())))
    def sync_step(self):
        for i,host in enumerate(self.step_hosts):
            host.pack_forget()
            if i==self.step:host.pack(fill='x',pady=(0,12))
        for i,button in enumerate(self.step_buttons):button.configure(style='Selected.Filter.TButton' if i==self.step else 'Filter.TButton')
        self.previous.configure(state='disabled' if self.step==0 else 'normal')
        if self.step==0:
            self.save.pack_forget();self.next_button.pack(side='left',padx=(0,8));self.next_button.configure(text=_ui_tr('다음: 실행 동작'))
        else:self.next_button.pack_forget();self.save.pack(side='left')
        self.fit_dialog()
    def go_step(self,index):
        if not 0<=index<=1:return
        if index==1:
            try:
                # Conditions must be checked independently of unfinished output.
                kind=next(k for k,v in KINDS.items() if v==self.kind.get())
                if kind=='button' and not any(v.get() for v in self.buttons):raise ValueError(_ui_tr('실행 조건에서 버튼을 먼저 지정하세요.'))
                if kind=='button' and self.mode.get()==CONDITIONS['long'] and not 0<=int(self.hold.get())<=255:raise ValueError(_ui_tr('길게 누르기 기준을 확인하세요.'))
                if kind=='stick' and int(self.threshold.get()) not in range(10,121):raise ValueError(_ui_tr('스틱 작동 경계를 확인하세요.'))
            except (ValueError,KeyError) as exc:self.feedback.set(str(exc));return
        self.stop_capture();self.step=index;self.sync_step();self.canvas.yview_moveto(0)
    def commit(self):
        if self.closed or self.ui.busy:return
        from studio_power import blocked
        if (not self.ui.loaded or not self.ui.write_ready or self.ui.external_stale
                or self.ui.app.studio.busy or self.ui.invalid or self.ui.app._close_requested
                or blocked(self.ui.app) or 'macro_disable' not in self.ui.doc.values):
            self.feedback.set(_ui_tr('저장할 수 없는 상태입니다. 다른 작업이 끝난 뒤 설정을 확인하세요.'));return
        if self.device_path!=self.ui.path or self.profile_stamp!=self.ui.profile_stamp:
            self.feedback.set(_ui_tr('현재 프로필이 바뀌었습니다. 다시 읽어 주세요.'));return
        if self.ui.current_save_target() is None:
            self.feedback.set(_ui_tr('저장할 프로필 슬롯을 먼저 선택하세요.'));return
        try:
            raw=self.draft.build(self.state(),strict=True)
            from studio_shift import reserved_input
            records=dict(self.ui.doc.macros);records[str(self.index)]=raw
            mask=int(self.ui.doc.values.get('macro_disable',0xffffffff)) & ~(1<<self.index)
            reason=reserved_input(raw,records,mask,bool(self.ui.doc.values.get('ps_shortcut_enabled',0)))
            if reason:raise ValueError(reason)
        except (ValueError,KeyError) as exc:self.feedback.set(str(exc));return
        self.ui.doc.macros[str(self.index)]=raw
        self.close()
        if not self.embedded:self.ui.render_fields()
        try:self.ui.save_registered_macro(self.index,raw,self.profile_stamp)
        except Exception as exc:
            self.ui.progress.configure(text=_ui_tr('매핑 저장 시작 실패 · 편집값은 유지됩니다. ')+str(exc),kind='error')
            self.ui.update_state()
    def close(self):
        if self.closed:return
        self.closed=True;self.stop_capture()
        if self.dialog.winfo_exists():self.dialog.destroy()
        if self.embedded and not self.ui.closed:
            if getattr(self.ui,'macro_editor',None) is self:self.ui.macro_editor=None
            # Let removal of the editor settle before rebuilding the grid.
            # Doing both inside the button callback can leave Canvas unmapped.
            self.ui.restore_macro_list()
    def destroyed(self,event):
        if event.widget is self.dialog:self.closed=True;self.stop_capture()
