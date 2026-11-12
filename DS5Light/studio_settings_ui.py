"""Lazy native Studio editor. Local edits, explicit serialized HID jobs."""
from thread_start import start_thread
from studio_i18n import text as _ui_tr
import copy,json,queue,threading,tkinter as tk
from tkinter import ttk,filedialog
from studio_dialogs import messagebox
from pathlib import Path
from studio_fields import SECTIONS,FIELDS
from studio_scope import EDITABLE,CONSTRUCTION,FAST_TRIGGER_FIELDS,TRIGGER_FIELDS,trigger_display,trigger_raw
from studio_range import RangeSlider
from studio_help import reference_point
from studio_macro_tools import MacroTools
from studio_shift_ui import ShiftUI
from studio_entry import EntryQueries
from studio_read_view import StableReadView,READ_JOBS
from studio_option_groups import OptionGroups
from studio_lightbar import LightbarUI
from studio_search import normalized,field_matches,category_for,FEATURES,feature_matches
from studio_gyro_calibration import GyroCalibration
from studio_help import GROUPS,TITLES,label,options,help_text
from localization import LANGUAGE
def ui_text(ko,en):return en if LANGUAGE=='en' else ko
from studio_document import SettingsDocument
from studio_save_flow import SaveFlow
from studio_recommended import RecommendedPresets
from studio_settings_protocol import SettingsClient,needs_reconnect,validate_changes
from studio_slots import devices,_DEVICE_LOCK
from studio_power import blocked as power_blocked
from controller_glyphs import ControllerChoice,GlyphStrip
from ui_controls import RoundedCard,CircleCheck,Switch,AutoScrollbar,widget_trace
BG='#0b0b0b';CARD='#151515';FG='#eee9df';MUTED='#aaa393';GOLD='#d6ad52';BORDER='#363126'
FAST_TRIGGER_DEPTH=(9,64)
FAST_TRIGGER_DEFAULT=14
FAST_TRIGGER_RESISTANCE_START=2


def fast_trigger_keys(prefix):
    stage, button = ('t2_l2_',9) if prefix == 'at_l2_' else ('t2_',10)
    return stage + 'mode', stage + 'pos', stage + 'button', button


def fast_trigger_active(values, prefix):
    mode, depth, output, button = fast_trigger_keys(prefix)
    return (values.get(mode) == 1 and values.get(output) == button
            and FAST_TRIGGER_DEPTH[0] <= values.get(depth,0) <= FAST_TRIGGER_DEPTH[1])
_CircleCheck=CircleCheck
def CircleCheck(parent,**kw):
    return _CircleCheck(parent,foreground=FG,muted=MUTED,accent=GOLD,disabled='#666257',**kw)
BUTTONS=['↑','↓','←','→','□','×','○','△','L1','R1','L2','R2','Create','Options','L3','R3','PS','Touch','Mute']
BUTTONS+=[_ui_tr('왼쪽 Fn'),_ui_tr('오른쪽 Fn'),_ui_tr('왼쪽 패들'),_ui_tr('오른쪽 패들'),_ui_tr('터치 왼쪽'),_ui_tr('터치 오른쪽')]
OUT_BUTTONS=[_ui_tr('키보드'),'×','○','□','△','L1','R1','L3','R3','L2','R2',_ui_tr('마우스 왼쪽'),_ui_tr('마우스 오른쪽'),_ui_tr('마우스 중간'),_ui_tr('위로 스크롤'),_ui_tr('아래로 스크롤'),'Create','Options',_ui_tr('터치 클릭'),_ui_tr('방향 ↑'),_ui_tr('방향 ↓'),_ui_tr('방향 ←'),_ui_tr('방향 →')]
HID_KEYS={_ui_tr('없음'):0,**{chr(65+i):4+i for i in range(26)},**{str(i):29+i for i in range(1,10)},'0':39,'Enter':40,'Esc':41,'Backspace':42,'Tab':43,'Space':44,**{f'F{i}':57+i for i in range(1,13)},'Delete':76,'Right':79,'Left':80,'Down':81,'Up':82,'Ctrl':224,'Shift':225,'Alt':226,'Win':227}
HID_KEYS.update({'RightCtrl':228,'RightShift':229,'RightAlt':230,'RightWin':231,
 **{f'F{i}':91+i for i in range(13,25)},
 **dict(zip(['Minus','Equal','LeftBracket','RightBracket','Backslash','NonUSHash','Semicolon','Quote','Grave','Comma','Period','Slash','CapsLock'],range(45,58))),
 **dict(zip(['PrintScreen','ScrollLock','Pause','Insert','Home','PageUp','Delete','End','PageDown'],range(70,79))),
 **dict(zip(['NumLock','KPDivide','KPMultiply','KPSubtract','KPAdd','KPEnter','KP1','KP2','KP3','KP4','KP5','KP6','KP7','KP8','KP9','KP0','KPDecimal'],range(83,100)))})
class FieldTip:
    def __init__(self,widget,text):
        self.widget=widget;self.text=text;self.job=None;self.popup=None
        widget.bind('<Enter>',self.enter,add='+');widget.bind('<Leave>',self.hide,add='+');widget.bind('<Destroy>',self.hide,add='+')
    def enter(self,event=None):self.hide();self.show()
    def show(self):
        self.job=None
        if not self.widget.winfo_exists():return
        p=tk.Toplevel(self.widget);self.popup=p;p.overrideredirect(True);p.attributes('-topmost',True)
        text = self.text() if callable(self.text) else self.text
        if LANGUAGE != 'en':
            from studio_help import compact_ko_help
            text = compact_ko_help(text)
        tk.Label(p,text=text,bg='#24211b',fg=FG,justify='left',wraplength=390,padx=14,pady=12,font=(_ui_tr('맑은 고딕'),10),relief='solid',bd=1).pack()
        p.update_idletasks();x=min(self.widget.winfo_pointerx()+16,self.widget.winfo_screenwidth()-p.winfo_reqwidth()-12);y=min(self.widget.winfo_pointery()+16,self.widget.winfo_screenheight()-p.winfo_reqheight()-12)
        p.geometry(f'+{max(0,x)}+{max(0,y)}')
    def hide(self,event=None):
        if self.job:
            try:self.widget.after_cancel(self.job)
            except tk.TclError:pass
            self.job=None
        if self.popup:
            try:self.popup.destroy()
            except tk.TclError:pass
            self.popup=None
class StatusMessage:
    """Compatibility sink for Studio job messages; the footer owns rendering."""
    def __init__(self,owner):self.owner=owner;self.text='';self.kind='info'
    def clear(self):self.text='';self.kind='info'
    def configure(self,**options):
        if 'text' in options:
            self.text=str(options['text']).replace(_ui_tr('오토햅틱'),_ui_tr('오디오햅틱')).replace(_ui_tr('오토 햅틱'),_ui_tr('오디오햅틱'))
            self.kind=options.get('kind','action')
            if hasattr(self.owner,'notice'):self.owner.update_state()
    def cget(self,option):
        if option=='text':return self.text
        raise KeyError(option)
class StudioSettings(ShiftUI,OptionGroups,LightbarUI,StableReadView,RecommendedPresets,SaveFlow,EntryQueries,GyroCalibration,MacroTools):
    def __init__(self,app,parent):
        self.app=app;self.parent=parent;self.built=False;self.busy=False;self.closed=False;self.uncertain=False;self.reconnect_wait=False;self.external_stale=False;self.pico_recognized=False;self.profile_save_needed=False
        self.init_entry_queries();self.recording=False;self.closing_recording=False;self.doc=SettingsDocument();self.path=None;self.profile_stamp=None;self.device_rows=[];self.results=queue.SimpleQueue();self.cancel=threading.Event()
        self.poll_id=None;self.search_job=None;self.vars={};self.invalid={};self.loaded=False;self.write_ready=False;self.category=0;self.slots_expanded=False;self.live_enabled=False;self.live_job=None;self.live_result=None;self.slots=[];self.resume=False;self.tips=[]
        self.return_list_job=None;self.search_targets={};self._display_fields={}
        self._option_groups=[]
        self._open_option_groups={('triggers','common')}
    def open(self):
        # If the user opens settings immediately, its serialized snapshot also
        # supplies current-profile identity. Do not launch a redundant 32-slot
        # startup sweep behind it. The main profile menu loads slots on demand.
        startup=getattr(self.app.studio,'startup_id',None)
        if startup is not None:
            self.app.root.after_cancel(startup);self.app.studio.startup_id=None
        if not self.built:self.build()
        self.begin_entry()
    def _open_if_visible(self):
        if not self.closed and self.app.selected_tab==2:self.open()
    def invalidate_profile(self):
        # Keep drafts, but never apply the previous profile's cached values.
        self.external_stale=True;self.write_ready=False
        self.standby_policy=(None,None)
        if self.built:
            self.identity.set(_ui_tr('프로필 변경됨 · 다시 조회 필요'))
            self.progress.configure(text=_ui_tr('이전 편집값 보관 중 · 새로 고침으로 확인하세요.') if self.doc.dirty else _ui_tr('다음 Studio설정 진입 시 다시 읽습니다.'))
            if 'disable_usb_sn' in self.field_views:self.render_fields()
            else:self.refresh_read_extras()
            self.update_state()
    def build(self):
        self.built=True;self.parent.columnconfigure(0,weight=1);self.parent.rowconfigure(1,weight=1)
        header=self.make_card(self.parent,16);header.grid(row=0,column=0,sticky='ew',pady=(0,12));row=header.content;row.columnconfigure(1,weight=1)
        self.identity=tk.StringVar(value=_ui_tr('Studio 장치를 읽어 주세요.'))
        self.device_header=row
        self.identity_label=tk.Label(row,textvariable=self.identity,bg=CARD,fg=FG,font=(_ui_tr('맑은 고딕'),9,'bold'),anchor='w',justify='left')
        self.identity_label.grid(row=0,column=0,sticky='w')
        self.read_button=ttk.Button(row,text=ui_text(_ui_tr('새로 고침'),'Refresh'),command=lambda:self.read(),width=10);self.read_button.grid(row=0,column=2,padx=(10,0))
        self.cancel_button=ttk.Button(row,text=_ui_tr('취소'),command=self.cancel_task,width=7)
        self.cancel_button.grid(row=0,column=3,padx=(6,0));self.cancel_button.grid_remove()
        self.device_choice=ttk.Combobox(row,state='readonly',width=12,justify='right')
        self.device_choice.grid(row=0,column=1,sticky='ew',padx=(10,0))
        self.device_choice.bind('<<ComboboxSelected>>',self.choose_device)
        row.bind('<Configure>',self.fit_device_header,add='+')
        self.progress=StatusMessage(self)
        FieldTip(row,lambda:self.identity.get())
        middle=tk.Frame(self.parent,bg=BG);middle.grid(row=1,column=0,sticky='nsew');middle.columnconfigure(1,weight=1);middle.rowconfigure(0,weight=1)
        nav=tk.Frame(middle,bg=BG);nav.grid(row=0,column=0,sticky='ns',padx=(0,12));self.nav=[]
        style=ttk.Style(self.parent)
        # Eliminate Button.focus from all inherited button styles, including
        # normal/Accent/navigation buttons in Studio and its editor dialogs.
        style.layout('TButton',style.layout('Filter.TButton'))
        style.configure('Disconnected.Studio.TButton',background='#602d30',foreground='#f0c2c4',bordercolor='#a44b52')
        style.map('Disconnected.Studio.TButton',background=[('active','#79363c'),('!disabled','#602d30')],foreground=[('!disabled','#f0c2c4')],bordercolor=[('!disabled','#a44b52')])
        style.configure('StudioNav.TButton',font=(_ui_tr('맑은 고딕'),9),padding=(6,6),foreground=MUTED,background=CARD)
        style.configure('Selected.StudioNav.TButton',font=(_ui_tr('맑은 고딕'),9,'bold'),padding=(6,6),foreground=GOLD,background='#302819')
        from ui_dpi import scale_styles
        scale_styles(self.parent._root(),style,('StudioNav.TButton','Selected.StudioNav.TButton'))
        self.nav_icons=('⚙','≋','⇄','⌖','⌨','▤')
        from localization import LANGUAGE
        nav_titles=('Device','Haptics','Triggers','Gyro & stick','Mapping','Profiles')
        for i,(title,_) in enumerate(GROUPS):
            title=nav_titles[i] if LANGUAGE=='en' else title
            b=ttk.Button(nav,text=self.nav_icons[i]+'  '+title,width=13,command=lambda i=i:self.select_category(i),style='StudioNav.TButton');b.pack(fill='x',pady=(0,5));self.nav.append(b)
        right=tk.Frame(middle,bg=BG);right.grid(row=0,column=1,sticky='nsew');right.columnconfigure(0,weight=1);right.rowconfigure(0,weight=1)
        self.search=tk.StringVar();entry=ttk.Entry(nav,style='Studio.TEntry',textvariable=self.search,width=13);entry.pack(fill='x',pady=(12,0));self.search_entry=entry
        self.web_warning=tk.Label(nav,text=ui_text(_ui_tr('⚠ 브라우저에서 Studio 웹 설정이 켜져 있으면 조회 및 저장이 충돌할 수 있습니다.'),'⚠ Studio in a browser may conflict with reading or saving.'),bg=BG,fg=GOLD,wraplength=135,justify='left',anchor='w',font=(_ui_tr('맑은 고딕'),8));self.web_warning.pack(fill='x',pady=(12,0))
        self.search_hint=tk.Label(entry,text=ui_text(_ui_tr('설정 검색'),'Search settings'),bg='#111111',fg='#77736a',font=(_ui_tr('맑은 고딕'),9),cursor='xterm')
        def hint(*_):
            if self.search.get() or entry.focus_get() is entry:self.search_hint.place_forget()
            else:self.search_hint.place(x=10,rely=.5,anchor='w')
        self.search_hint.bind('<Button-1>',lambda e:entry.focus_set());entry.bind('<FocusIn>',hint,add='+');entry.bind('<FocusOut>',hint,add='+')
        self.search.trace_add('write',hint);self.search.trace_add('write',self.queue_search);hint()
        holder=tk.Frame(right,bg=BG);holder.grid(row=0,column=0,sticky='nsew');holder.columnconfigure(0,weight=1);holder.rowconfigure(0,weight=1)
        self.canvas=tk.Canvas(holder,bg=BG,highlightthickness=0,bd=0,width=1);self.scroll=AutoScrollbar(holder,orient='vertical',command=self.canvas.yview);self.canvas.configure(yscrollcommand=self.scroll.set)
        self.canvas.grid(row=0,column=0,sticky='nsew');self.scroll.grid(row=0,column=1,sticky='ns')
        self.editor_holder=tk.Frame(holder,bg=BG);self.editor_holder.grid(row=0,column=0,columnspan=2,sticky='nsew');self.editor_holder.columnconfigure(0,weight=1);self.editor_holder.rowconfigure(0,weight=1);self.editor_holder.grid_remove()
        self.body=tk.Frame(self.canvas,bg=BG);self.body_window=self.canvas.create_window(0,0,window=self.body,anchor='nw')
        self.canvas.bind('<Configure>',self.resize_canvas);self.body.bind('<Configure>',self.sync_scrollregion)
        self.parent.bind_all('<MouseWheel>',self.wheel,add='+')
        footer=self.make_card(self.parent,14);footer.grid(row=2,column=0,sticky='ew',pady=(12,0));footer.content.columnconfigure(0,weight=1)
        self.save_target=tk.StringVar()
        target=tk.Label(footer.content,textvariable=self.save_target,bg=CARD,fg=MUTED,anchor='w',width=1,pady=0,font=(_ui_tr('맑은 고딕'),9))
        target.grid(row=0,column=0,sticky='ew',padx=(0,10))
        FieldTip(target,lambda:self.save_target.get())
        self.notice=tk.StringVar(value=_ui_tr('옵션을 편집한 뒤 임시 적용하거나 현재 프로필에 저장하세요.'))
        self.notice_display=tk.StringVar()
        self.notice_label=tk.Label(footer.content,textvariable=self.notice_display,bg=CARD,fg=GOLD,anchor='w',width=1,height=1,pady=0,font=(_ui_tr('맑은 고딕'),9));self.notice_label.grid(row=1,column=0,sticky='ew',padx=(0,10))
        self.notice_label.bind('<Configure>',self.fit_notice)
        FieldTip(self.notice_label,lambda:self.notice.get())
        actions=tk.Frame(footer.content,bg=CARD);actions.grid(row=0,column=1,rowspan=2,sticky='e')
        self.revert_button=ttk.Button(actions,text=ui_text(_ui_tr('되돌리기'),'Revert'),command=self.revert,width=8);self.revert_button.pack(side='left',padx=(0,6))
        FieldTip(self.revert_button,_ui_tr('마지막 조회 또는 적용 이후의 미적용 편집을 되돌립니다. 이미 장치에 적용하거나 저장한 값은 되돌리지 않습니다.'))
        self.apply_button=ttk.Button(actions,text=ui_text(_ui_tr('임시 적용'),'Apply temporarily'),command=lambda:self.apply(False),width=9);self.apply_button.pack(side='left',padx=(0,6))
        self.save_button=ttk.Button(actions,text=ui_text(_ui_tr('현재 프로필에 저장'),'Save to profile'),command=lambda:self.apply(True),style='Accent.TButton',width=17);self.save_button.pack(side='left')
        FieldTip(self.apply_button,_ui_tr('현재 프로필의 설정과 매크로 사용 체크를 지금 연결에만 적용합니다. 유지하려면 현재 프로필에 저장하세요. 공유 매크로 정의는 전송하지 않습니다.'))
        FieldTip(self.save_button,_ui_tr('현재 슬롯과 Pico 시작 설정에 저장합니다.\n다른 앱의 Pico 오디오 출력을 중지하세요.\n공유 매크로는 별도 저장'))
        self.render_fields();self.update_state()
    def fit_device_header(self,event=None):
        width=self.device_header.winfo_width()
        if width<=1:return
        reserved=self.read_button.winfo_reqwidth()+self.device_choice.winfo_reqwidth()+20
        if self.cancel_button.winfo_manager():reserved+=self.cancel_button.winfo_reqwidth()+6
        available=max(80,width-reserved)
        if getattr(self,'_header_wraplength',None)!=available:
            self.identity_label.configure(wraplength=available)
            self._header_wraplength=available
    def fit_slot_label(self,event):
        widget=event.widget;width=max(1,event.width)
        if getattr(widget,'_slot_wraplength',None)!=width:
            widget.configure(wraplength=width)
            widget._slot_wraplength=width
    def fit_notice(self,event=None):
        if not hasattr(self,'notice_label'):return
        from tkinter import font as tkfont
        text=' '.join(self.notice.get().split());width=max(0,self.notice_label.winfo_width()-4)
        key=(text,width)
        if key==getattr(self,'_notice_fit_key',None):return
        self._notice_fit_key=key
        font=tkfont.Font(font=self.notice_label.cget('font'))
        if font.measure(text)>width:
            low,high=0,len(text)
            while low<high:
                middle=(low+high+1)//2
                if font.measure(text[:middle]+'…')<=width:low=middle
                else:high=middle-1
            text=text[:low]+'…' if width>=font.measure('…') else ''
        self.notice_display.set(text)
    def resize_canvas(self,event):
        self.canvas.itemconfigure(self.body_window,width=event.width);self.sync_scrollregion()
    def sync_scrollregion(self,event=None):
        # A short list must never let Canvas retain a negative scroll origin.
        self.canvas.coords(self.body_window,0,0)
        self.canvas.configure(scrollregion=(0,0,max(1,self.canvas.winfo_width()),max(self.body.winfo_reqheight(),self.canvas.winfo_height())))
    def restore_scroll_offset(self,offset):
        self.body.update_idletasks()
        self.sync_scrollregion()
        height=max(1,self.body.winfo_reqheight(),self.canvas.winfo_height())
        self.canvas.yview_moveto(max(0,offset)/height)
    def update_editor_view(self):
        if self.closed or not self.built:return
        editor=getattr(self,'macro_editor',None)
        active=editor is not None and getattr(editor,'embedded',False) and not editor.closed and self.category==4 and not self.search.get()
        if active:
            self.canvas.grid_remove();self.scroll.grid_remove();self.editor_holder.grid()
        else:
            self.editor_holder.grid_remove();self.canvas.grid();self.sync_scrollregion()
        self.search_entry.configure(state='disabled' if active else 'normal')
        self.update_state()
    def restore_macro_list(self):
        if self.closed:return
        if self.return_list_job:self.app.root.after_cancel(self.return_list_job)
        self.update_editor_view()
        self.return_list_job=self.app.root.after_idle(self._render_macro_list)
    def _render_macro_list(self):
        self.return_list_job=None
        if not self.closed:self.render_fields()
    def help_icon(self,parent,text):
        icon=tk.Canvas(parent,width=19,height=19,bg=parent.cget('bg'),highlightthickness=0,bd=0,cursor='question_arrow')
        icon.create_oval(2,2,16,16,outline='#716b5d',width=1)
        icon.create_text(9,9,text='?',fill='#827c6f',font=(_ui_tr('맑은 고딕'),8,'bold'))
        icon._studio_help_icon=True
        tip=FieldTip(icon,text);self.tips.append(tip)
        def release_tip(event):
            if event.widget is icon and tip in self.tips:self.tips.remove(tip)
        icon.bind('<Destroy>',release_tip,add='+')
        return icon
    def option_title(self,parent,key,text=None,foreground=FG,wraplength=270):
        box=tk.Frame(parent,bg=CARD)
        tk.Label(box,text=label(key) if text is None else text,bg=CARD,fg=foreground,anchor='w',justify='left',wraplength=wraplength).pack(side='left')
        from studio_option_help import option_help
        self.help_icon(box,lambda k=key:option_help(self,k)).pack(side='left',padx=(5,0))
        return box
    def make_card(self,parent,padding=18):return RoundedCard(parent,background=BG,surface=CARD,outline=BORDER,inset_x=padding,inset_y=padding)
    def wheel(self,event):
        if self.built and not self.closed and self.app.selected_tab==2 and self.canvas.winfo_viewable() and not isinstance(event.widget,(ttk.Combobox,ttk.Spinbox,tk.Text)):
            self.canvas.yview_scroll(-int(event.delta/120),'units')
    def queue_search(self,*_):
        if self.search_job:self.parent.after_cancel(self.search_job)
        self.search_job=self.parent.after(180,self.render_fields)
    @property
    def transfer_locked(self):
        return getattr(self,'_transfer_job',None) in ('backup','restore')

    def select_category(self,index):
        if self.transfer_locked:return
        if index==self.category and not self.search.get():return
        self.stop_live();self.category=index;self.search.set('');self.render_fields();self.begin_entry()
    def card(self,title):
        card=self.make_card(self.body);card.pack(fill='x',pady=(0,12));content=card.content;content.columnconfigure(0,weight=1)
        self.search_targets[title]=card
        tk.Label(content,text=title,bg=CARD,fg=FG,font=(_ui_tr('맑은 고딕'),11,'bold'),anchor='w').grid(row=0,column=0,columnspan=2,sticky='w',pady=(0,12));return content
    def jump_to_search_result(self,category,target=None,key=None):
        self.select_category(category)
        def reveal():
            if self.closed or self.category!=category or self.search.get():return
            for group,rows,button,conditional,note in getattr(self,'_option_groups',()):
                if any(field==key for field,row in rows):
                    self._open_option_groups.add(group)
                    self.refresh_option_groups()
                    for field,row in rows:
                        if field==key:
                            row.master.grid();row.grid()
            view=getattr(self,'field_views',{}).get(key)
            widget=view[0] if view else self.search_targets.get(target)
            if widget is None or not widget.winfo_exists():return
            self.body.update_idletasks()
            offset=max(0,widget.winfo_rooty()-self.body.winfo_rooty()-8)
            self.canvas.yview_moveto(offset/max(1,self.body.winfo_height()))
        self.parent.after_idle(reveal)
    def visible(self,key):
        # Keep the full supported gyro/stick set visible, even while disabled.
        return key in EDITABLE and key!='ps_shortcut_enabled' and (key!='disable_usb_sn' or self.edge_serial_visible())
    def edge_serial_visible(self):
        return ('disable_usb_sn' in self.doc.values and 'disable_usb_sn' not in self.unsupported_fields
                and not self.external_stale and getattr(self.app.studio,'controller_connected',None) is not False)
    def enabled_for(self,key):
        values=self.doc.values
        if key=='disable_usb_sn':return self.edge_serial_visible()
        if key=='haptics_gain':return values.get('auto_haptics_enable')==0
        if key=='haptics_aa':return values.get('auto_haptics_enable') in (1,2)
        if key in ('rumble_haptic_strength','mix_native_level'):return values.get('auto_haptics_enable')==1
        if key=='mix_native_filter':return values.get('auto_haptics_enable')==1 and values.get('mix_native_level',0)>0
        if key=='rumble_mode':
            return key in values and key not in getattr(self,'unsupported_fields',()) and values.get('auto_haptics_enable')==0
        if key in ('rumble_gain','rumble_release'):
            return all(k in values for k in ('rumble_gain','rumble_release')) and values.get('auto_haptics_enable')==0
        from studio_scope import AUDIO_HAPTIC_CHILDREN
        if key in AUDIO_HAPTIC_CHILDREN and values.get('auto_haptics_enable',0)==0:return False
        if key=='enable_wake':
            mode=self.standby_value()
            return mode==0 if mode is not None else not getattr(getattr(self.app,'studio_power',None),'supported',False)
        if key in ('lightbar_fixed','lightbar_rgb'):
            supported=getattr(self,'lightbar_supported',all(k in values for k in ('lightbar_fixed','lightbar_rgb')))
            return supported
        if key in ('speaker_volume','speaker_gain'):return not values.get('disable_speaker',0)
        if key in ('auto_mute_mix','auto_mute_replace'):
            mode=1 if key=='auto_mute_mix' else 2
            return values.get('auto_haptics_enable')==mode and not values.get('disable_speaker',0)
        if key in ('r2t_on_press','r2t_strength','r2t_frequency'):return values.get('r2t_mode',0) in (1,2,3)
        if key in ('ah_low_gain','ah_high_gain'):return 30<=values.get('ah_xover_hz',0)<=200
        if key.startswith('gyro_') and key not in ('gyro_mode','gyro_output') and not values.get('gyro_mode',0):return False
        mouse=values.get('gyro_output',0)>=1
        natural=mouse and values.get('gyro_sens_mode',0)==1
        if key in ('gyro_sens','gyro_sens_y'):return not natural
        if key in ('gyro_natural_x10','gyro_natural_y_x10','gyro_scale_trim_x100'):return natural
        if key=='gyro_sens_mode':return mouse and bool(values.get('gyro_mode',0))
        if key=='flick_angle':return values.get('gyro_output',0)==2
        if key=='flick_counts_360':return values.get('gyro_output',0)==2 or (bool(values.get('gyro_mode',0)) and natural)
        if key.startswith('stick_mouse_'):return bool(values.get('stick_mouse',0))
        return True
    def render_fields(self):
        if self.search_job:
            try:self.parent.after_cancel(self.search_job)
            except tk.TclError:pass
        self.search_job=None
        if self.closed or not self.built:return
        context=(self.category,self.search.get().strip().casefold())
        position=self.canvas.canvasy(0) if context==getattr(self,'_render_context',None) else 0
        self._render_context=context
        for tip in self.tips:tip.hide()
        self.tips=[];self.vars={};self.speaker_recommendations=[];self.range_controls={};self.field_views={}
        self.search_targets={};self._display_fields={}
        self._option_groups=[]
        self._extra_body=None;self._extra_signature=None
        for child in self.body.winfo_children():child.destroy()
        for i,b in enumerate(self.nav):b.configure(style='Selected.StudioNav.TButton' if i==self.category else 'StudioNav.TButton')
        query=normalized(self.search.get());sections=GROUPS[self.category][1];count=0
        for section in SECTIONS:
            if not query and (section['title'] not in sections or section['title']=='Rumble → Trigger'):continue
            ordered=[f for f in section['fields'] if f[1] not in FAST_TRIGGER_FIELDS and f[1] not in ('rumble_gain','rumble_mode','rumble_release','enable_wake') and (query or f[1] not in TRIGGER_FIELDS)]
            if section['title']=='Auto-Haptics & Speaker Effect Leak':
                ordered=[f for f in ordered if f[1] not in ('auto_mute_mix','auto_mute_replace')]
            elif section['title']=='General Haptics & Audio':
                gain_at=next(i for i,f in enumerate(ordered) if f[1]=='haptics_gain')+1
                ordered[gain_at:gain_at]=[FIELDS['rumble_gain'],FIELDS['rumble_mode'],FIELDS['rumble_release']]
                at=next(i for i,f in enumerate(ordered) if f[1]=='disable_speaker')+1
                ordered[at:at]=[FIELDS['auto_mute_mix'],FIELDS['auto_mute_replace']]
            if not query and section['title']=='Device & Connection':
                ordered=[f for f in ordered if f[1] not in self.LIGHTING_FIELDS]
            fields=[f for f in ordered if self.visible(f[1]) and (not query or field_matches(f,section['title'],query))]
            if section['title']=='General Haptics & Audio' and any(f[1] in ('auto_mute_mix','auto_mute_replace') for f in fields):
                if not any(f[1]=='disable_speaker' for f in fields):
                    fields.insert(next(i for i,f in enumerate(fields) if f[1] in ('auto_mute_mix','auto_mute_replace')),FIELDS['disable_speaker'])
            if not fields:continue
            if section['title']=='Macros':
                if query:
                    box=self.card(_ui_tr('매핑·매크로 › 프로필별 사용 설정'))
                    ttk.Button(box,text=_ui_tr('매핑·매크로 열기'),command=lambda:self.select_category(4)).grid(row=1,column=0,sticky='w')
                else:self.render_macro_enable()
                count+=len(fields);continue
            if not query and self.render_option_groups(section['title'],fields):
                count+=len(fields);continue
            from localization import LANGUAGE
            english_titles={'Device & Connection':'Device','Auto-Haptics & Speaker Effect Leak':'Audio haptics','Native Haptics Filter':'Haptic waveform','General Haptics & Audio':'Haptics & speaker','Trigger Strength':'Adaptive triggers','Rumble → Trigger':'Rumble to triggers'}
            title=english_titles.get(section['title'],section['title']) if LANGUAGE=='en' else TITLES.get(section['title'],section['title'])
            if query:
                category=next((name for name,sections in GROUPS if section['title'] in sections),_ui_tr('Studio설정'))
                title=category+' › '+title
            box=self.card(title)
            if query:
                destination=category_for(section['title'])
                if destination is not None:
                    ttk.Button(box,text=ui_text(_ui_tr('탭 열기'),'Open tab'),command=lambda i=destination,k=fields[0][1]:self.jump_to_search_result(i,key=k)).grid(row=0,column=1,sticky='e',padx=(12,0))
            speaker_children=None
            for n,f in enumerate(fields,1):
                if f[1] in ('auto_mute_mix','auto_mute_replace'):
                    if speaker_children is None:
                        speaker_children=tk.Frame(box,bg=CARD)
                        speaker_children.grid(row=n,column=0,columnspan=2,sticky='ew',padx=(20,0),pady=(0,4))
                        speaker_children.columnconfigure(0,weight=1)
                    self.field_row(speaker_children,0 if f[1]=='auto_mute_mix' else 1,f)
                else:self.field_row(box,n,f)
                count+=1
        if not query and self.category==0:self.render_lighting()
        if query and 'enable_wake' in self.doc.values and field_matches(FIELDS['enable_wake'],'Device & Connection',query):
            self.render_standby_policy();count+=1
        if query:
            for feature in FEATURES:
                if not feature_matches(feature,query):continue
                title,category,target,names=feature
                box=self.card(GROUPS[category][0]+' › '+title)
                ttk.Button(box,text=ui_text(_ui_tr('열기'),'Open'),command=lambda i=category,t=target:self.jump_to_search_result(i,t)).grid(row=0,column=1,sticky='e',padx=(12,0))
                matches=[name for name in names if query in normalized(name)]
                if matches:
                    tk.Label(box,text=' · '.join(matches),bg=CARD,fg=MUTED,anchor='w',justify='left',wraplength=420).grid(row=1,column=0,columnspan=2,sticky='ew',pady=(0,4))
                count+=1
        if not query:
            self._extra_body=tk.Frame(self.body,bg=BG);self._extra_body.pack(fill='x')
            self.refresh_read_extras()
            if self.category==2:
                section=next(section for section in SECTIONS if section['title']=='Rumble → Trigger')
                self.render_option_groups(section['title'],section['fields'])
        elif not count:tk.Label(self.body,text=ui_text(_ui_tr('검색 결과가 없습니다.'),'No results found.'),bg=BG,fg=MUTED,pady=24).pack()
        self.refresh_option_groups()
        self.align_choices(self.body)
        self.update_editor_view()
        self.restore_scroll_offset(position);self.update_state()
        if self.busy and getattr(self,'_read_view_kind',None):self.read_view_lock()
    def standby_value(self, policy='standby_policy'):
        path,mode=getattr(self,policy,(None,None))
        if (not path or path!=self.path or not self.pico_recognized
                or self.external_stale or self.reconnect_wait
                or self.app.studio.controller_connected is False):
            return None
        return mode

    def render_standby_policy(self):
        box=self.card(ui_text('전원 관리','Power management'))
        heading=box.grid_slaves(row=0)[0]
        heading.grid_configure(columnspan=1)
        tk.Label(box,text=ui_text('Pico 공통 · 프로필과 별도','Pico-wide · Separate from profiles'),
            bg=CARD,fg=GOLD).grid(row=0,column=1,sticky='e',pady=(0,12))
        mode=self.standby_value()
        var=tk.BooleanVar(master=box,value=mode==1)
        row=tk.Frame(box,bg=CARD)
        row.grid(row=1,column=0,columnspan=2,sticky='w',pady=(8,0))
        toggle=CircleCheck(row,text=ui_text(
            '미연결 시 최대 절전','Deep sleep when disconnected'),
            variable=var,command=lambda:self.change_standby_policy(var),background=CARD)
        toggle.pack(side='left')
        self.help_icon(row,ui_text(
            '사용 버튼\nBOOTSEL · OLED 장착 시 OLED 2번 버튼도 사용 가능\n\n'
            '버튼 용도\n깨우기 및 장치 검색 / 최대 절전 진입',
            'Buttons\nBOOTSEL or OLED button 2, if fitted\n\n'
            'Functions\nWake and device search / enter deep sleep'
        )).pack(side='left',padx=(6,0))
        toggle.set_enabled(mode is not None and not self.busy)
        note=ui_text('끄면 대기 모드를 사용합니다. 선택하면 Pico에 바로 저장됩니다.',
                     'Off uses standby mode. Changes save to Pico immediately.')
        if mode is None:
            note=ui_text('절전 정책을 조회하지 못했습니다. 지원 펌웨어와 연결을 확인하세요.',
                         'Standby policy unavailable. Check firmware support and connection.')
        note=getattr(self,'_policy_save_errors',{}).get('standby_policy',note)
        tk.Label(box,text=note,bg=CARD,fg=MUTED,wraplength=500,justify='left').grid(row=2,column=0,columnspan=2,sticky='w',pady=(4,0))

        if 'enable_wake' in self.doc.values:
            wake=tk.Frame(box,bg=CARD);wake.grid(row=3,column=0,columnspan=2,sticky='ew',padx=(20,0),pady=(4,0));wake.columnconfigure(0,weight=1)
            self.field_row(wake,0,FIELDS['enable_wake'])

        dock=self.standby_value('dock_policy')
        dock_var=tk.BooleanVar(master=box,value=dock==1)
        dock_toggle=CircleCheck(box,text=ui_text('충전독 장착 시 연결 해제','Disconnect when docked'),
            variable=dock_var,command=lambda:self.change_standby_policy(dock_var,'dock_policy'),background=CARD)
        dock_toggle.grid(row=4,column=0,columnspan=2,sticky='w',pady=(8,0))
        dock_toggle.set_enabled(dock is not None and not self.busy)
        dock_error=getattr(self,'_policy_save_errors',{}).get('dock_policy')
        if dock is None or dock_error:
            tk.Label(box,text=dock_error or ui_text('충전독 정책 미지원 또는 조회 실패','Dock policy unavailable'),
                bg=CARD,fg=MUTED,wraplength=500,justify='left').grid(row=5,column=0,columnspan=2,sticky='w')

    def change_standby_policy(self,var,policy='standby_policy'):
        mode=self.standby_value(policy)
        requested=int(var.get())
        var.set(mode==1)
        if mode is None or requested==mode or self.busy or self.app.studio.busy:
            return
        method='dock_disconnect' if policy=='dock_policy' else 'standby_mode'
        self.stopped_task(policy,lambda:self.with_client(lambda client:getattr(client,method)(requested)))

    def align_choices(self,parent):
        for widget in parent.winfo_children():
            if isinstance(widget,ttk.Combobox):widget.configure(justify='right')
            self.align_choices(widget)
    def field_row(self,parent,row,f,title_text=None,dropdown_width=22,default=None):
        if f[1]=='mix_native_level':
            f=[*f[:4],'mix_toggle']
            title_text=ui_text('Mix 네이티브 햅틱 혼합','Mix native haptics')
        self._display_fields = getattr(self, '_display_fields', {})
        self._display_fields[f[1]] = f
        key=f[1];valid=key in self.doc.values and self.enabled_for(key);value=self.doc.values.get(key)
        if key=='lightbar_rgb':self.lightbar_colour_row(parent,row,f);return
        if f[4]=='number' or key=='trigger_reduce':
            self.range_row(parent,row,f,value,valid,default=default)
            return
        title=self.option_title(parent,key,text=title_text if title_text is not None else f[3] if key.startswith("at_") else None,foreground=FG if valid else MUTED);title.grid(row=row,column=0,sticky='w',padx=(18 if key in ('disable_inactive_disconnect','speaker_gain') else 0,12),pady=8)
        var=tk.StringVar(value='' if value is None else format(value,'.5g') if f[2]=='f32' else str(value));self.vars[key]=var
        controls=[];bits=[]
        if f[4]=='mix_toggle':
            box=tk.Frame(parent,bg=CARD);box.grid(row=row,column=1,sticky='e',pady=6)
            active=tk.BooleanVar(value=bool(value));self.vars[key]=active
            control=Switch(box,active,lambda:self.select_value(key,100 if active.get() else 0))
            control.set_enabled(valid and not self.busy);control.pack(side='right')
            control.status=tk.Label(box,bg=CARD,fg=MUTED);control.status.pack(side='right',padx=(0,5))
            self.update_mix_toggle_text(control,value)
        elif f[4]=='bool':
            box=tk.Frame(parent,bg=CARD);box.grid(row=row,column=1,sticky='e',pady=6)
            bv=tk.BooleanVar(value=bool(value));self.vars[key]=bv;control=CircleCheck(box,text='',variable=bv,command=lambda:None,background=CARD)
            control.pack(side='left');control.set_enabled(valid and not self.busy);widget_trace(control,bv,lambda *_,k=key,v=bv:self.changed(k,int(v.get())))
            if key=='disable_speaker':
                note=tk.Label(box,text=ui_text(_ui_tr('스피커 끄기 권장'),'Speaker off recommended'),bg=CARD,fg=GOLD,font=(_ui_tr('맑은 고딕'),8))
                self.speaker_recommendations.append(note)
        elif f[4]=='select':
            opts=options(f);mapping={str(v):k for k,v in opts};var.set(dict(opts).get(value,_ui_tr('밝기 선택') if key=='player_led_bright' and value==3 else _ui_tr('미지원') if value is None else str(value)))
            if key=='gyro_mode':
                control=ControllerChoice(parent,textvariable=var,values=list(mapping),compact=True,state='readonly' if valid and not self.busy else 'disabled')
                control.grid(row=row,column=1,sticky='ew',pady=6)
            else:
                control=ttk.Combobox(parent,textvariable=var,values=list(mapping),width=dropdown_width,justify='right',state='readonly' if valid and not self.busy else 'disabled');control.grid(row=row,column=1,sticky='e',pady=6)
            control.bind('<<ComboboxSelected>>',lambda e,k=key,v=var,m=mapping:self.select_value(k,m.get(v.get())))
        elif f[4]=='bits':
            box=tk.Frame(parent,bg=CARD);box.grid(row=row,column=1,sticky='e')
            for index,name in enumerate(f[5]):
                bv=tk.BooleanVar(value=bool((int(value or 0))&(1<<index)));control=CircleCheck(box,text=('X' if index==0 else 'Y'),variable=bv,command=lambda:None,background=CARD);control.pack(side='left',padx=(8,0));control.set_enabled(valid and not self.busy)
                widget_trace(control,bv,lambda *_,k=key,v=bv,i=index:self.changed(k,(int(self.doc.values.get(k,0))&~(1<<i))|((1<<i) if v.get() else 0)))
                controls.append(control);bits.append((bv,index))
        else:
            control=ttk.Entry(parent,style='Studio.TEntry',textvariable=var,width=24,state='normal' if valid and not self.busy else 'disabled',justify='right');control.grid(row=row,column=1,sticky='e',pady=6)
            widget_trace(control,var,lambda *_,k=key,v=var:self.number_changed(k,v.get()));control.bind('<Return>',lambda e:self.render_fields())
        if not controls:controls=[control]
        self.field_views[key]=(title,controls,bits)
    @staticmethod
    def update_mix_toggle_text(control,value):
        text=ui_text('켜짐','On') if value else ui_text('꺼짐','Off') if value==0 else ui_text('미확인','Unknown')
        if value is not None and 0<value<100:text+=f' · {value}%'
        control.status.configure(text=text)
    def number_changed(self,key,value):
        if getattr(self,'_syncing_fields',False):return
        try:
            from studio_settings_protocol import encode
            field=getattr(self,'_display_fields',{}).get(key,FIELDS[key])
            number=float(value) if field[2]=='f32' else int(value);encode(field,number);self.invalid.pop(key,None);self.changed(key,number)
        except (ValueError,OverflowError):self.invalid[key]=label(key)+_ui_tr('의 입력값을 확인하세요.');self.update_state()
    def select_value(self,key,value):
        if value is not None:
            self.changed(key,value);self.refresh_read_values()
            if self.category==2 and not self.search.get():
                if key in ('at_mode','at_l2_mode') and value==1:
                    self.reveal_trigger_field(key[:-4]+'threshold')
                elif key in ('at_kick_style','at_l2_kick_style') and value==0:
                    self.reveal_trigger_field(key[:-10]+'pushback_freq')
    def changed(self,key,value):
        if self.transfer_locked or getattr(self,'_syncing_fields',False):return
        self.progress.clear()
        previous=self.doc.values.get(key);self.doc.values[key]=value
        if key in ('auto_haptics_enable','haptics_gain'):
            self.doc.normalize_haptic_gain(stage=key=='auto_haptics_enable' and previous!=value)
            if self.doc.values.get('auto_haptics_enable') in (1,2):self.invalid.pop('haptics_gain',None)
        self.doc.companion_edit(key,previous,value)
        for child in ('disable_speaker','lightbar_off'):
            variable=self.vars.get(child)
            if variable is not None and child in self.doc.values and bool(variable.get())!=bool(self.doc.values[child]):
                variable.set(bool(self.doc.values[child]))
        if key in ('ah_xover_hz','disable_speaker','auto_haptics_enable'):self.update_band_controls()
        if key in ('disable_speaker','auto_haptics_enable'):self.update_speaker_controls()
        if key in self.LIGHTING_FIELDS:self.refresh_lighting()
        if key in ('auto_haptics_enable','lightbar_fixed'):self.refresh_read_values()
        if key=='mix_native_level':self.refresh_read_values(keys=('mix_native_level','mix_native_filter','ah_dsp_source'))
        if self.category==3 and key in ('gyro_mode','gyro_output','gyro_sens_mode'):self.refresh_read_extras()
        self.update_state()
        if key in ('auto_haptics_enable','gyro_mode','gyro_output','gyro_sens_mode','stick_mouse','r2t_mode','mix_native_level'):
            self.refresh_option_groups()
    def update_speaker_controls(self):
        for key in ('auto_mute_mix','auto_mute_replace'):
            view=getattr(self,'field_views',{}).get(key)
            if view is None:continue
            title,controls,_=view
            valid=key in self.doc.values and self.enabled_for(key)
            for control in controls:control.set_enabled(valid and not self.busy)
            for child in title.winfo_children():
                if isinstance(child,tk.Label):child.configure(fg=FG if valid else MUTED)
    def update_band_controls(self):
        # Update dependent controls in place so dragging the crossover retains
        # its widget, focus and scroll position. Stored gains are preserved.
        for key in ('ah_low_gain','ah_high_gain','speaker_volume','speaker_gain'):
            controls=getattr(self,'range_controls',{}).get(key)
            if controls is None:continue
            entry,slider,title=controls
            valid=key in self.doc.values and self.enabled_for(key)
            enabled=valid and not self.busy
            entry.configure(state='normal' if enabled else 'disabled')
            slider.enabled=enabled;slider.configure(takefocus=enabled);slider.draw()
            for child in title.winfo_children():
                if isinstance(child,tk.Label):child.configure(fg=FG if valid else MUTED)
    def update_state(self):
        if self.built and self.transfer_locked!=getattr(self,'_transfer_ui_lock',None):
            self._transfer_ui_lock=self.transfer_locked
            for button in self.nav:button.configure(state='disabled' if self.transfer_locked else 'normal')
            self.search_entry.configure(state='disabled' if self.transfer_locked else 'normal')
            gain_slider=getattr(self.app,'gain_slider',None)
            if gain_slider is not None:gain_slider.set_enabled(not self.transfer_locked)
            language_choice=getattr(self.app,'language_choice',None)
            if language_choice is not None:language_choice.configure(state='disabled' if self.transfer_locked else 'readonly')
        if not self.built or self.closed:return
        recommend=self.doc.values.get('auto_haptics_enable') in (1,2) and self.doc.values.get('disable_speaker')==0
        for note in getattr(self,'speaker_recommendations',()):
            if recommend:note.pack(side='left',padx=(8,0))
            else:note.pack_forget()
        editor=getattr(self,'macro_editor',None)
        editing=editor is not None and getattr(editor,'embedded',False) and not editor.closed
        if editing:editor.sync_ps_shortcut()
        target=self.current_save_target()
        self.save_target.set(_ui_tr('저장 대상: ')+(f'{target[0]+1:02d} · '+(target[1] or _ui_tr('이름 없음')) if target else _ui_tr('미지정 · 프로필 슬롯에서 저장 대상을 선택하세요.')))
        detail=' '.join(self.progress.cget('text').split())
        detail_kind=self.progress.kind
        if self.reconnect_wait:text=_ui_tr('Pico 재연결 대기 중 · 연결 후 목록 자동 갱신')
        elif self.busy:text=detail or _ui_tr('Studio 처리 중…')
        elif self.uncertain:text=detail or _ui_tr('결과 미확인 · 새로 고침 필요')
        elif self.invalid:text=next(iter(self.invalid.values()))
        elif self.external_stale:
            text=(_ui_tr('프로필 변경됨 · 이전 편집 확인 후 새로 고침') if self.doc.dirty else _ui_tr('프로필 변경됨 · 새로 고침 필요')) if self.pico_recognized else _ui_tr('듀얼센스를 Pico에 연결한 뒤 새로 고침하세요')
        elif editing:text=_ui_tr('매크로 편집 중 · 편집에 반영하세요')
        elif detail and detail_kind in ('action','error','warning'):text=detail
        elif not self.pico_recognized:text=_ui_tr('듀얼센스를 Pico에 연결한 뒤 새로 고침하세요')
        elif self.doc.dirty:
            parts=[]
            if self.doc.macro_changes:parts.append(_ui_tr('공유 매크로 변경 {0}개').format(f'{len(self.doc.macro_changes)}'))
            if self.doc.user_changes:parts.append(_ui_tr('현재 프로필 설정 변경 {0}개').format(f'{len(self.doc.user_changes)}'))
            if self.doc.policy_changes:parts.append(_ui_tr('햅틱 파형 증폭 기본값 복구 필요'))
            text=' · '.join(parts)+_ui_tr(' · 아직 저장되지 않음')
        elif self.doc.policy_changes:text=_ui_tr('햅틱 파형 증폭 기본값 복구 필요 · 적용 또는 프로필 저장 시 반영')
        elif self.doc.macros_pending_flash:text=_ui_tr('공유 매크로 임시 적용됨 · Pico 매핑·매크로 저장 필요')
        elif self.doc.unsaved or self.loaded and self.profile_save_needed:text=_ui_tr('임시 적용됨 · 유지하려면 현재 프로필에 저장하세요.')
        elif self.doc.save_requested:text=detail or _ui_tr('프로필 슬롯 저장 확인 · Pico 시작 설정 저장 확인')
        elif self.write_ready and self.doc.values.get('auto_haptics_enable') in (1,2) and self.doc.values.get('haptics_gain',1)!=1:text=_ui_tr('기존 네이티브 햅틱 세기 유지 중 · 중복 증폭에 주의하세요')
        elif self.loaded:text=(detail or _ui_tr('조회 완료')) if self.write_ready else _ui_tr('읽기 전용 · 현재 프로필 확인 필요')
        else:text=_ui_tr('장치 설정을 읽어 주세요')
        self.notice.set(text);self.fit_notice();enabled=self.loaded and self.write_ready and not self.busy and not self.app._close_requested and not editing
        self.device_choice.configure(state='disabled' if self.busy or editing else 'readonly')
        self.read_button.configure(style='Disconnected.Studio.TButton' if not self.pico_recognized and not self.busy else 'TButton')
        save_needed=self.profile_changes_pending()
        self.read_button.configure(state='disabled' if editing or self.busy else 'normal')
        if self.busy:
            self.cancel_button.grid()
            self.cancel_button.configure(text=_ui_tr('취소 중…') if self.cancel.is_set() else _ui_tr('취소'),state='disabled' if self.cancel.is_set() else 'normal')
        else:self.cancel_button.grid_remove()
        self.fit_device_header()
        self.apply_button.configure(state='normal' if enabled and self.doc.changes and not self.invalid else 'disabled');self.save_button.configure(state='normal' if enabled and save_needed and not self.invalid else 'disabled');self.revert_button.configure(state='normal' if enabled and (self.doc.dirty or self.invalid) else 'disabled')
        shared_button=getattr(self,'shared_save_button',None)
        if shared_button is not None and shared_button.winfo_exists():shared_button.configure(state='normal' if enabled and self.shared_changes_pending() and not self.invalid else 'disabled')
    def cancel_task(self):
        if self.busy:
            self.cancel.set();self.update_state()
    def read_or_cancel(self):
        if self.busy:self.cancel_task()
        else:self.read()
    def choose_device(self,event=None):
        i=self.device_choice.current()
        if 0<=i<len(self.device_rows):
            if self.doc.dirty and not messagebox.askyesno(_ui_tr('편집 취소'),_ui_tr('다른 장치를 읽으면 미적용 변경이 취소됩니다.'),parent=self.parent):return
            target=self.device_rows[i]['path']
            def choose():
                self.doc=SettingsDocument();self.profile_stamp=None;self.path=target;self.external_stale=False;self.loaded=False;self.write_ready=False;self.read(confirm=False)
            if self.app.engine and target!=self.path:self.app.stop(on_complete=choose)
            else:choose()
    def read(self,confirm=True):
        if self.busy:return
        if confirm and self.doc.dirty and not messagebox.askyesno(_ui_tr('설정 새로 고침'),_ui_tr('미적용 변경을 취소하고 장치에서 다시 읽을까요?'),parent=self.parent):return
        from studio_snapshot import snapshot
        preferred=self.path or self.app.studio.profile_path
        binding=self.app.studio.binding
        if self.external_stale:
            preferred=binding.snapshot().hid_path or self.app.studio.profile_path
        selected_binding=binding if self.path is None or self.path==binding.snapshot().hid_path else None
        if self.external_stale:selected_binding=binding
        self.task('read',lambda:snapshot(preferred,self.cancel.is_set,binding=selected_binding))
    def task(self,kind,operation):
        if power_blocked(self.app):return
        if self.closed or self.busy:return
        if self.app.studio.busy:
            if self.built:self.progress.configure(text=_ui_tr('프로필 조회가 끝난 후 다시 시도하세요.'))
            return
        self.stop_live()
        self.progress.clear()
        self._transfer_job=kind if kind in ('backup','restore') else None
        self.busy=True;self.cancel.clear()
        if kind in ('read','entry_read'):
            self.entry_failed=False;self.entry_attempts.add('fields')
        try:
            self._read_view_kind=kind if kind in READ_JOBS else None
            if self._read_view_kind:self.read_view_lock()
            else:self.render_fields()
            self.update_state();self.app.last_render=None;self.app.render()
        except Exception:
            self.abort_task_setup()
            raise
        def worker():
            try:self.results.put((kind,operation(),None))
            except Exception as exc:
                from studio_settings_protocol import PolicySaveError
                self.results.put((kind,exc.current if isinstance(exc,PolicySaveError) else None,str(exc)))
        try:start_thread(threading.Thread(target=worker,name='DS5Light-Studio-settings',daemon=True))
        except Exception:
            self.abort_task_setup()
            raise
        self.poll_id=self.parent.after(60,self.poll)
    def abort_task_setup(self):
        # A failed UI preparation must not leave a job marked busy when no
        # worker was started. Keep the original exception visible to the caller.
        self._transfer_job=None
        self.busy=False;self.resume=False;self.cancel.set()
        self.read_view_unlock();self._read_view_kind=None
        self.after_profile_save=None;self.after_shared_save=None
        if self.built and not self.closed:
            try:
                self.read_button.configure(state='normal');self.cancel_button.grid_remove()
                self.notice.set(_ui_tr('화면 준비 중 오류가 발생했습니다. 새로 고침으로 다시 시도하세요.'))
                self.fit_notice()
            except tk.TclError:pass
    def with_client(self,operation):
        if not self.path:raise ValueError(_ui_tr('Studio 장치를 선택하세요.'))
        import hid
        import time
        deadline=time.monotonic()+3
        while not _DEVICE_LOCK.acquire(timeout=.1):
            if self.cancel.is_set():raise RuntimeError(_ui_tr('Studio 작업 취소됨'))
            if time.monotonic()>=deadline:raise TimeoutError(_ui_tr('Studio 조회 대기 시간 초과'))
        try:
            if self.cancel.is_set():raise RuntimeError(_ui_tr('Studio 작업 취소됨'))
            if power_blocked(self.app):raise RuntimeError(_ui_tr('Pico 절전 요청 중에는 장치 작업을 실행할 수 없습니다.'))
            d=hid.device()
            try:d.open_path(self.path);return operation(SettingsClient(d,cancel=self.cancel.is_set))
            finally:d.close()
        finally:_DEVICE_LOCK.release()
    def stopped_task(self,kind,operation):
        if power_blocked(self.app):return
        if self.busy or self.app.studio.busy:return
        self.resume=self.app.engine is not None
        self._resume_token=None
        if self.app.engine:
            route=self.app._run_route()
            self.cancel.clear();self.progress.clear()
            self.busy=True
            try:
                self.render_fields()
                self.progress.configure(text=_ui_tr('오디오 전송 정지 대기 중…'),kind='progress')
            except Exception:
                self.abort_task_setup()
                raise
            def begin():
                self.busy=False
                if self.app._close_requested:self.resume=False;return
                if self.cancel.is_set():
                    self.resume=False;self.progress.configure(text=_ui_tr('작업을 취소했습니다.'),kind='info')
                    self.render_fields();self.app.last_render=None;self.app.render()
                    return
                self.task(kind,operation)
            self.app.stop(on_complete=begin)
            self._resume_token=(self.app.run_intent.generation,route)
        else:self.task(kind,operation)
    def apply(self,persist=False,target=None,after=None):
        if self.invalid or not self.loaded or not self.write_ready or self.busy:return
        if persist:
            target=target or self.current_save_target()
            if target is None:
                self.select_category(5);self.progress.configure(text=_ui_tr('저장할 슬롯의 현재 설정 저장을 눌러 주세요.'));return
        if 'macro_disable' in self.doc.changes and self.shared_changes_pending():
            messagebox.showinfo(_ui_tr('매크로 저장 순서'),_ui_tr('Pico 매핑·매크로를 먼저 저장한 뒤 현재 프로필의 사용 체크를 적용하거나 저장하세요.'),parent=self.parent);return
        try:
            validate_changes(self.doc.baseline,self.doc.changes)
            from studio_shift import validate_reserved_inputs
            validate_reserved_inputs(self.doc.macros,self.doc.values)
        except ValueError as exc:messagebox.showerror(_ui_tr('설정 확인'),str(exc),parent=self.parent);return
        baseline=dict(self.doc.baseline);changes=dict(self.doc.changes);effects=copy.deepcopy(self.doc.effect_changes)
        effect_baseline=copy.deepcopy(self.doc.effect_baseline)
        pending_macros=self.doc.macros_pending_flash;profile_stamp=self.profile_stamp
        refresh_macros='macro_disable' in changes
        self.after_profile_save=after
        edge_serial_changed='disable_usb_sn' in changes
        binding=self.app.studio.binding
        reconnect_path=self.path
        reconnect_serial=next((d.get("serial_number") for d in self.device_rows if d["path"]==self.path),None) or self.app.studio.device_serials.get(self.path)
        reconnect=needs_reconnect(baseline,dict(baseline,**changes),self.doc.macro_baseline)
        def op(client):
            if profile_stamp is not None and client.profile()!=profile_stamp:raise RuntimeError(_ui_tr('현재 프로필이 바뀌었습니다. 다시 읽어 주세요.'))
            current,missing=client.read_fields([FIELDS[k] for k in baseline])
            for key in baseline:
                if key not in current or current[key]!=baseline[key]:raise RuntimeError(_ui_tr('외부에서 설정이 변경되었습니다. 다시 읽어 주세요.'))
            reconnect_needed=reconnect
            if refresh_macros:
                try:macros=client.read_macros()
                except (OSError,RuntimeError,TimeoutError):macros=None
                reconnect_needed=needs_reconnect(current,dict(current,**changes),macros)
            if effects:
                actual=client.read_effects()
                for (trig,index) in effects:
                    if actual[str(trig)][index]!=effect_baseline[str(trig)][index]:raise RuntimeError(_ui_tr('효과가 외부에서 변경되었습니다. 새로 고침을 누르세요.'))
            checked=client.write_fields(changes,current)
            for (trig,index),state in effects.items():client.write_effect(trig,index,state)
            if effects:
                verified=client.read_effects()
                if any(verified[str(t)][i]!=s for (t,i),s in effects.items()):raise RuntimeError(_ui_tr('효과 적용값 불일치 · 새로 고침을 누르세요.'))
            # Read metadata before a flash/reset can remove the USB handle.
            profile=client.profile()
            profile_saved=False
            if persist:
                # Recheck the source identity after applying fields. Do not
                # silently save an OLED-selected different profile to our slot.
                if profile_stamp is not None and any(profile.get(k)!=profile_stamp.get(k) for k in ('index','name')):
                    raise RuntimeError(_ui_tr('저장 전 프로필이 바뀌었습니다. 새로 고침으로 확인하세요.'))
                self.results.put(('progress',_ui_tr('{0} · {1}에 저장 중…').format(f'{target[0] + 1:02d}',f"{target[1] or '이름 없음'}"),None))
                client.save_slot(*target)
                profile=client.profile()
                if profile.get('index')!=target[0] or profile.get('name')!=target[1] or profile.get('edited'):
                    raise RuntimeError(_ui_tr('프로필 저장 후 상태가 다릅니다. 새로 고침으로 확인하세요.'))
                profile_saved=True
            if refresh_macros or persist or reconnect_needed:self.results.put(('progress',dict(reconnecting=True),None))
            save_uncertain=False;save_error=None
            try:
                if persist:
                    self.results.put(('progress',_ui_tr('Pico 저장 확인 중 · 다른 앱의 Pico 오디오 출력을 중지하세요.'),None))
                    client.save_flash()
            except (OSError,TimeoutError) as exc:
                if self.cancel.is_set():raise
                save_uncertain=True;save_error=str(exc)
            reset_uncertain=False
            if reconnect_needed and not save_uncertain:
                if edge_serial_changed:binding.expect_edge_serial_reconnect(hidden=bool(changes['disable_usb_sn']))
                try:client.reconnect_usb()
                except (OSError,RuntimeError):
                    if self.cancel.is_set():raise
                    reset_uncertain=True
            return dict(values=dict(current,**checked),saved=persist and not save_uncertain,reconnect=reconnect_needed,
                        profile=profile,profile_saved=profile_saved,target=target,macros_pending=pending_macros,
                        trigger_changed=bool(TRIGGER_FIELDS.intersection(changes)),
                        save_uncertain=save_uncertain,save_error=save_error,reset_uncertain=reset_uncertain,
                        edge_serial_reconnect=edge_serial_changed and reconnect_needed and not save_uncertain)
        def operation():
            result=self.with_client(op)
            if refresh_macros or persist or reconnect or result.get('save_uncertain'):
                from studio_reconnect import wait_for_macros
                try:
                    if result['edge_serial_reconnect']:
                        result['reloaded']=wait_for_macros(reconnect_path,reconnect_serial,self.cancel,
                            edge_binding=binding,serial_hidden=bool(changes['disable_usb_sn']))
                    else:
                        result['reloaded']=wait_for_macros(reconnect_path,reconnect_serial,self.cancel)
                except Exception as exc:
                    result['reload_error']=str(exc)
                    if result['edge_serial_reconnect']:
                        try:
                            from studio_slots import devices
                            result['reconnect_rows']=devices()
                        except (OSError,ImportError):
                            pass
            return result
        if reconnect or refresh_macros or persist:self.app.studio.binding.expect_reconnect()
        self.stopped_task('apply',operation)
    def poll(self):
        self.poll_id=None
        if self.closed:return
        try:kind,result,error=self.results.get_nowait()
        except queue.Empty:self.poll_id=self.parent.after(60,self.poll);return
        if kind=='progress':
            if isinstance(result,dict) and result.get('reconnecting'):
                self.reconnect_wait=True;self.write_ready=False
                self.progress.configure(text=_ui_tr('Pico 재연결 대기 중'))
                self.update_state()
            else:self.progress.configure(text=result,kind='progress')
            self.poll_id=self.parent.after(60,self.poll);return
        self.busy=False;self.reconnect_wait=False
        if kind in READ_JOBS:
            edge_row_present='disable_usb_sn' in self.field_views
            self.read_view_unlock();self._read_view_kind=None
        if error:
            if kind in ('read','entry_read'):
                self.entry_failed=True;self.close_entry_queries()
            self.progress.configure(text=_ui_tr('작업 실패 · ')+error,kind='error')
            if kind in ('standby_policy','dock_policy'):
                setattr(self,kind,(self.path,result if type(result)is int and result in (0,1) else None))
                self._policy_save_errors=getattr(self,'_policy_save_errors',{})
                self._policy_save_errors[kind]=error
            if kind=='macros':self._discard_macro_mask_on_read=False
            if kind in ('read','entry_read'):self.pico_recognized=False
            if kind in ('apply','shared_save','recommended','restore','slot_save'):self.resume=False;self.loaded=False;self.write_ready=False;self.uncertain=True
            if kind=='read':self.write_ready=False
        elif kind=='dock_policy':
            getattr(self,'_policy_save_errors',{}).pop(kind,None)
            self.dock_policy=(self.path,result)
            self.progress.configure(text=ui_text('충전독 정책 저장 완료','Dock policy saved.'),kind='info')
        elif kind=='standby_policy':
            getattr(self,'_policy_save_errors',{}).pop(kind,None)
            self.standby_policy=(self.path,result)
            self.progress.configure(text=ui_text(
                'Pico 절전 정책 저장 완료','Pico standby policy saved.'),kind='info')
        elif kind=='entry_read':self.merge_entry_snapshot(result)
        elif kind=='read':
            self.lightbar_supported=all(k in result.get('values',{}) for k in ('lightbar_fixed','lightbar_rgb'))
            self.unsupported_fields=set(result.get('unsupported',()))
            self.pico_recognized=not result.get('choose',False)
            if result.get('choose') and not result['rows']:self.app.studio.controller_connected=False
            self.device_rows=result['rows'];self.device_choice.configure(values=[d.get('product_string','DualSense')+f' · {i+1:02d}' for i,d in enumerate(self.device_rows)])
            if result.get('choose'):self.progress.configure(text=_ui_tr('연결 장치를 선택한 뒤 새로 고침을 누르세요.'));self.loaded=False
            else:
                if self.path is not None and self.path!=result['path']:self.doc=SettingsDocument()
                self.path=result['path'];self.device_choice.current(next(i for i,d in enumerate(self.device_rows) if d['path']==self.path));self.doc.revert();self.doc.load(result['values']);self.doc.effects={};self.doc.effect_baseline={};self.doc.macros={};self.doc.macro_baseline={};self.invalid.clear();self.loaded=True
                self.entry_attempts.discard('macros')
                self._policy_save_errors={}
                self.standby_policy=(self.path,result.get('standby'))
                self.dock_policy=(self.path,result.get('dock'))
                self.uncertain=False;self.external_stale=False
                profile=result.get('profile')
                self.write_ready=profile is not None and result.get('cfg') in (19,20,21,22)
                self.profile_stamp={k:profile[k] for k in ('index','name','edited')} if profile else None
                self.profile_save_needed=bool(profile and profile.get('edited'))
                from studio_snapshot import device_labels
                self.device_choice.configure(values=device_labels(self.device_rows,self.path,profile))
                if profile:self.app.studio._observe_profile(self.path,profile);self.app.studio._sync_current_profile(self.path,profile);self.app.studio.enforce_haptics_policy()
                serial=next((d.get('serial_number') for d in self.device_rows if d['path']==self.path),None)
                if serial:self.app.studio.device_serials[self.path]=serial
                self.identity.set('Studio · '+str(result['version'])+' · '+((profile or {}).get('name') or _ui_tr('현재 설정')));self.progress.configure(text=_ui_tr('설정 {0}개 읽음').format(f"{len(result['values'])}")+(_ui_tr(' · {0}개 미지원/미확인').format(f"{len(result['unsupported'])}") if result['unsupported'] else ''),kind='loaded')
        elif kind=='apply':
            if result.get('edge_serial_reconnect'):
                self.resume=False
                if result.get('reloaded'):
                    self.app._edge_audio_recheck=True
            self.profile_save_needed=not result.get('profile_saved',False)
            self.profile_stamp=result.get('profile');self.doc.macros_pending_flash=result.get('macros_pending',False)
            self.doc.load(result['values']);self.doc.effect_baseline=copy.deepcopy(self.doc.effects);self.doc.unsaved=not result['saved'];self.doc.save_requested=result['saved']
            self.progress.configure(text=_ui_tr('프로필 슬롯 저장 확인 · Pico 시작 설정 저장 확인') if result['saved'] else _ui_tr('현재 프로필 설정을 임시 적용했습니다.'),kind='saved' if result['saved'] else 'applied');self.app.studio.auto_haptics_mode=self.doc.values.get('auto_haptics_enable')
            if result.get('trigger_changed') and not result['saved']:
                self.progress.configure(text=ui_text('트리거 설정 적용 확인 · 반응이 없으면 Pico 효과 상태 확인',
                                                     'Trigger settings verified · Check Pico effect status if there is no response'),kind='action')
            if result.get('reloaded'):
                fresh=result['reloaded'];self.uncertain=False
                self.doc.load(fresh['values']);self.merge_entry_snapshot(fresh)
                if not self.doc.macro_changes:
                    self.doc.macros=copy.deepcopy(fresh['macros']);self.doc.macro_baseline=copy.deepcopy(fresh['macros'])
                self.doc.macros_pending_flash=result.get('macros_pending',False)
                self.doc.unsaved=not result['saved'];self.doc.save_requested=result['saved']
                if result.get('save_uncertain'):
                    self.uncertain=True;self.write_ready=False;self.resume=False
                    self.progress.configure(text=result.get('save_error') or _ui_tr('저장 응답 미확인 · 현재 설정만 조회됨 · 새로 고침 후 확인하세요.'),kind='warning')
                else:self.progress.configure(text=_ui_tr('프로필 슬롯 저장 확인 · Pico 시작 설정 저장 확인') if result.get('profile_saved') else _ui_tr('임시 적용 확인 · 유지하려면 현재 프로필에 저장하세요.'),kind='info')
                if result['reconnect']:self.app.refresh_devices()
            elif result.get('reload_error'):
                self.resume=False;self.loaded=False;self.write_ready=False;self.uncertain=True
                if result.get('edge_serial_reconnect'):
                    self.path=None;self.pico_recognized=False
                    self.device_rows=result.get('reconnect_rows',[])
                    from studio_snapshot import device_labels
                    self.device_choice.configure(values=device_labels(self.device_rows,None,None))
                    self.device_choice.set('')
                    self.progress.configure(text=_ui_tr('Edge 재연결 후 Pico를 확인하지 못했습니다. 장치 목록에서 같은 Pico를 선택하세요.'),kind='warning')
                else:self.progress.configure(text=_ui_tr('재연결 조회 미완료 · 새로 고침을 눌러 주세요.'))
            elif result['reconnect']:
                self.loaded=False;self.path=None;self.doc.effects={};self.doc.effect_baseline={};self.doc.macros={};self.doc.macro_baseline={};self.app.refresh_devices()
            if self.path and result.get('profile') and not result.get('reloaded') and not result.get('reload_error'):
                state=dict(result['profile'],auto_haptics_enable=self.doc.baseline.get('auto_haptics_enable'))
                state.update({key:self.doc.baseline[key] for key in ('mix_native_level','ah_dsp_source') if key in self.doc.baseline})
                self.app.studio._observe_profile(self.path,state)
            if result.get('profile_saved'):
                self.profile_save_needed=False
                self.app.studio.catalog_invalid=True;self.app.studio.last_read=-1e9
                target=result.get('target')
                if target:
                    from studio_slots import Slot
                    self.slots=[Slot(s.index,'saved',target[1]) if s.index==target[0] else s for s in self.slots]
                profile=result.get('profile')
                if profile:
                    self.app.studio._sync_current_profile(self.path,profile)
        elif kind=='shared_save':self.finish_shared_save(result)
        elif kind=='recommended':self.finish_recommended(result)
        elif kind=='effects':self.doc.effects=copy.deepcopy(result);self.doc.effect_baseline=copy.deepcopy(result)
        elif kind=='macros':
            self.doc.macros=copy.deepcopy(result);self.doc.macro_baseline=copy.deepcopy(result)
            if getattr(self,'_discard_macro_mask_on_read',False):
                if 'macro_disable' in self.doc.baseline:self.doc.values['macro_disable']=self.doc.baseline['macro_disable']
                self._discard_macro_mask_on_read=False
            self.progress.configure(text=_ui_tr('매핑 목록 새로 고침 완료'),kind='info')
        elif kind=='profile_data':
            if not self.doc.effects:self.doc.effects=copy.deepcopy(result['effects']);self.doc.effect_baseline=copy.deepcopy(result['effects'])
            if not self.doc.macros:self.doc.macros=copy.deepcopy(result['macros']);self.doc.macro_baseline=copy.deepcopy(result['macros'])
        elif kind=='gyro_measure':self.show_gyro_result(result)
        elif kind=='calibration_send':self.calibration_sent(result);self.progress.configure(text=_ui_tr('{0}카운트 전송 요청 완료 · 회전각을 입력하세요.').format(f'{result}'))
        elif kind=='timeline_arm':self.recording=True;self.progress.configure(text=_ui_tr('트리거 녹화 중 · 게임에서 효과를 발생시키세요.'))
        elif kind=='timeline_stop':self.recording=False;self.show_timeline(result)
        elif kind=='history':self.show_history(result)
        elif kind=='macro_live':self.live_result=result
        elif kind=='trigger_status':
            side,flags,signal=result
            left=side=='L2'
            if flags & (1 if left else 2):
                status=ui_text('게임 효과 우선 · L2/R2 공통 설정에서 내 설정 우선으로 시험',
                               'Game effect has priority · Test with Prefer my settings under Shared L2/R2 settings')
            elif flags & (4 if left else 8):status=ui_text('장치 효과 출력 중','Device effect active')
            else:status=ui_text('활성 효과 없음 · 작동 조건 또는 게임 실행 후 다시 확인',
                                'No active effect · Check activation conditions or start a game and try again')
            self.progress.configure(text=ui_text('Pico 현재 상태','Current Pico status')+f' · {side} · {status} · '+
                                    ui_text(f'공통 반동 신호 {signal}/255',f'Shared recoil signal {signal}/255'),kind='action')
        elif kind=='chime_preview':self.progress.configure(text=_ui_tr('전환 신호음 요청 완료 · 프로필은 바뀌지 않았습니다.'),kind='info')
        elif kind=='slots':self.slots=result;self.progress.configure(text=_ui_tr('슬롯 목록 새로 고침 완료'),kind='info')
        elif kind=='slot_save':
            self.profile_save_needed=False;self.progress.configure(text=_ui_tr('프로필 슬롯 저장 응답 확인'));self.app.studio.last_read=-1e9;self.app.studio.catalog_invalid=True
            if isinstance(result,dict):
                from studio_slots import Slot
                self.slots=[Slot(s.index,'saved',result['name']) if s.index==result['index'] else s for s in self.slots]
        elif kind=='bootloader':self.progress.configure(text=_ui_tr('Pico UF2 설치 모드 요청 완료'));self.loaded=False;self.write_ready=False;self.path=None;self.pico_recognized=False
        elif kind=='restore':self.progress.configure(text=_ui_tr('프로필 {0}개 복원 응답 확인').format(f'{len(result)}'));self.app.studio.last_read=-1e9;self.loaded=False
        elif kind=='backup':
            name=filedialog.asksaveasfilename(parent=self.parent,defaultextension='.json',initialfile='ds5dongle-slots.json',filetypes=[('JSON','*.json')])
            if name:
                try:Path(name).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
                except OSError as exc:self.progress.configure(text=_ui_tr('작업 실패 · ')+str(exc),kind='error')
        if kind=='macro_live':
            if not error:self.show_live_result(result)
            else:self.stop_live()
            self.update_state();self.app.last_render=None;self.app.render();return
        self._transfer_job=None
        if kind in READ_JOBS:
            query=normalized(self.search.get())
            show_edge=self.edge_serial_visible() and (field_matches(FIELDS['disable_usb_sn'],'Device & Connection',query)
                if query else self.category==0)
            if edge_row_present==show_edge:self.refresh_read_values()
            else:self.render_fields()
        else:self.render_fields()
        self.update_state();self.app.last_render=None;self.app.render();resume,self.resume=self.resume,False
        if kind in ('apply','shared_save'):
            attribute='after_profile_save' if kind=='apply' else 'after_shared_save'
            callback=getattr(self,attribute,None);setattr(self,attribute,None)
            verified=(not error and not self.uncertain and self.loaded and self.write_ready
                      and (kind=='shared_save' or result.get('profile_saved') and result.get('saved')))
            if callback and verified and not self.app._close_requested:
                self.parent.after_idle(callback);return
            if not verified and (error or self.uncertain):resume=False
        if kind=='macros' and not error and not self.app._close_requested:
            callback=getattr(self,'after_macro_read',None);self.after_macro_read=None
            if callback:self.parent.after_idle(callback)
        if kind=='macros' and error:self.after_macro_read=None
        if kind=='profile_data' and not error and not self.app._close_requested:
            callback,self.after_records=self.after_records,None
            if callback:self.parent.after_idle(callback)
        if kind in ('read','entry_read','slots','macros'):self.schedule_entry()
        if resume and not error and not self.app._close_requested:
            token=getattr(self,'_resume_token',None)
            def resume_audio():
                if (token is None or self.closed or self.busy or self.cancel.is_set()
                        or self.app._close_requested
                        or token!=(self.app.run_intent.generation,self.app._run_route())):return
                self.app.start()
            self.parent.after(700 if isinstance(result,dict) and result.get('reconnect') and not result.get('reloaded') else 0,resume_audio)
    def revert(self):
        self.doc.revert();self.invalid.clear();self.progress.clear();self.render_fields()
        if self.external_stale:self.begin_entry()
    def render_files(self):
        row=self.card(_ui_tr('현재 설정 파일'))
        tools=tk.Frame(row,bg=CARD);tools.grid(row=1,column=0,columnspan=2,sticky='ew')
        for i,(text,action) in enumerate([(_ui_tr('JSON 가져오기'),self.import_file),(_ui_tr('JSON 내보내기'),self.export_file),(_ui_tr('HTML 내보내기'),self.export_html)]):
            ttk.Button(tools,text=text,command=action).grid(row=0,column=i,sticky='ew',padx=(0,8),pady=4);tools.columnconfigure(i,weight=1)
        reboot=self.card(_ui_tr('Pico 펌웨어 설치'))
        ttk.Button(reboot,text=_ui_tr('부트로더 재시작'),command=self.bootloader).grid(row=1,column=0,columnspan=2,sticky='ew')
    def import_file(self):
        if self.busy or not self.loaded:return
        if not self.doc.macros:self.load_profile_data(self.import_file);return
        name=filedialog.askopenfilename(parent=self.parent,filetypes=[('JSON','*.json')])
        if not name:return
        try:
            data=json.loads(Path(name).read_text(encoding='utf-8-sig'))
            raw=data.get('fields',data.get('settings',data));take=False
            if isinstance(raw,dict) and 'macro_disable' in raw and self.doc.macro_baseline:
                take=messagebox.askyesno(_ui_tr('매크로 선택'),_ui_tr('파일의 매크로 활성 선택도 편집에 반영할까요? 정의를 확인한 경우에만 선택하세요.'),parent=self.parent)
            n,skip=self.doc.import_json(data,take_macro_mask=take);self.invalid.clear();self.progress.configure(text=_ui_tr('{0}개 편집에 반영 · {1}개 제외 · 아직 장치에 적용되지 않음').format(f'{n}',f'{skip}'),kind='edit');self.render_fields()
        except Exception as exc:messagebox.showerror(_ui_tr('프로필 파일'),str(exc),parent=self.parent)
    def export_file(self):
        if self.busy or not self.loaded:return
        if not self.doc.macros:self.load_profile_data(self.export_file);return
        name=filedialog.asksaveasfilename(parent=self.parent,defaultextension='.json',initialfile='ds5light-studio-profile.json',filetypes=[('JSON','*.json')])
        if name:Path(name).write_text(json.dumps(self.doc.export_json(),ensure_ascii=False,indent=2),encoding='utf-8')
    def load_profile_data(self,callback):
        self.after_records=callback
        self.task('profile_data',lambda:self.with_client(lambda c:dict(effects={},macros=c.read_macros())))
    def render_macro_enable(self):
        pass # Per-profile switches live beside the definitions they enable.
    def render_macros(self):
        from studio_macro_design import category,populated
        box=self.card(_ui_tr('Pico 매핑·매크로'))
        ttk.Button(box,text=_ui_tr('매핑 목록 새로 고침'),command=self.read_macro_table).grid(row=1,column=0,sticky='w',pady=(0,8))
        ttk.Button(box,text=_ui_tr('+ 매핑·매크로 추가'),style='Accent.TButton',command=self.new_macro,state='normal' if self.loaded and not self.busy else 'disabled').grid(row=1,column=1,sticky='e',pady=(0,8))
        tk.Label(box,text=_ui_tr('내용을 수정하거나 삭제하면 모든 프로필에 영향을 줍니다.\n체크한 항목만 현재 프로필에서 사용합니다.'),bg=CARD,fg=GOLD,wraplength=420,justify='left').grid(row=2,column=0,columnspan=2,sticky='w',pady=(0,8))
        shared=tk.Frame(box,bg=CARD);shared.grid(row=3,column=0,columnspan=2,sticky='ew',pady=(0,12));shared.columnconfigure(0,weight=1)
        tk.Label(shared,text=_ui_tr('현재 프로필에서 사용 ↓'),bg=CARD,fg=MUTED,anchor='w').grid(row=0,column=0,sticky='w')
        self.shared_save_button=ttk.Button(shared,text=_ui_tr('Pico 매핑·매크로 저장'),style='Accent.TButton',command=self.save_shared_macros)
        self.shared_save_button.grid(row=0,column=1,sticky='e')
        FieldTip(self.shared_save_button,_ui_tr('매크로 동작은 모든 프로필이 공유합니다. 이 버튼은 동작만 저장합니다. 프로필별 사용 체크는 하단의 현재 프로필에 저장을 누르세요.'))
        self.macro_warning=tk.StringVar();self.macro_warning_label=tk.Label(box,textvariable=self.macro_warning,bg=CARD,fg=GOLD,wraplength=430,justify='left',anchor='w')
        self.macro_warning_label.grid(row=4,column=0,columnspan=2,sticky='ew',pady=(0,12))
        self.macro_warning_button=ttk.Button(box,text=_ui_tr('겹치는 입력 모두 보기'),command=self.show_macro_conflicts);self.macro_warning_button.grid(row=5,column=0,columnspan=2,sticky='w',pady=(0,8))
        self.render_shift_controls(box)
        mask=int(self.doc.values.get('macro_disable',0xffffffff));n=0
        for i in range(32):
            data=self.doc.macros.get(str(i))
            if not populated(data) or data[17]==31 or bool(data[5]&32)!=getattr(self,'macro_layer',False):continue
            name=bytes(data[19:35]).split(b'\0')[0].decode('utf-8','replace')
            row=tk.Frame(box,bg=CARD);row.grid(row=7+n,column=0,columnspan=2,sticky='ew',pady=9);row.columnconfigure(1,weight=1);n+=1
            index_box=tk.Frame(row,bg=CARD);index_box.grid(row=0,column=0,rowspan=3,padx=(0,10),sticky='n')
            v=tk.BooleanVar(value=not bool(mask&(1<<i)));check=CircleCheck(index_box,text=f'{i+1:02d}',variable=v,command=lambda:None,background=CARD);check.pack(side='bottom',pady=(4,0));check.set_enabled(not self.busy and 'macro_disable' in self.doc.values)
            status=tk.StringVar(value=category(data)+' · '+(_ui_tr('활성') if v.get() else _ui_tr('비활성')))
            widget_trace(check,v,lambda *_,v=v,i=i,status=status,kind=category(data):self.toggle_macro(i,v.get(),status,kind))
            tk.Label(row,text=name or _ui_tr('이름 없는 매핑'),bg=CARD,fg=FG,font=(_ui_tr('맑은 고딕'),10,'bold'),anchor='w').grid(row=0,column=1,sticky='w')
            summary=tk.Frame(row,bg=CARD);summary.grid(row=1,column=1,sticky='ew')
            from studio_button_names import NAMES
            chord=int.from_bytes(bytes(data[:4]),'little')
            source=[_ui_tr('오른쪽 스틱') if data[4]&64 else _ui_tr('왼쪽 스틱')] if data[4]&32 else [_ui_tr('터치패드 클릭')] if data[4]&128 else [name for bit,name in enumerate(NAMES) if chord&(1<<bit)]
            if source:
                symbols=tk.Frame(index_box,bg=CARD);symbols.pack(side='top',pady=(0,2))
                GlyphStrip(symbols,source,limit=3).pack(side='left')
                if data[17] and data[17]<len(OUT_BUTTONS):
                    tk.Label(symbols,text='→',bg=CARD,fg=GOLD).pack(side='left',padx=6)
                    GlyphStrip(symbols,[OUT_BUTTONS[data[17]]]).pack(side='left')
            tk.Label(summary,text=self.macro_summary(data),bg=CARD,fg=MUTED,wraplength=255,justify='left',anchor='w').pack(anchor='w')
            tk.Label(row,textvariable=status,bg=CARD,fg=GOLD,font=(_ui_tr('맑은 고딕'),8),anchor='w').grid(row=2,column=1,sticky='w',pady=(3,0))
            ttk.Button(row,text=_ui_tr('편집'),command=lambda i=i:self.edit_macro(i),width=5).grid(row=0,column=2,rowspan=3,padx=4)
            ttk.Button(row,text=_ui_tr('삭제'),command=lambda i=i:self.delete_macro(i),width=5).grid(row=0,column=3,rowspan=3)
        if not n:
            text=_ui_tr('아직 추가한 매핑·매크로가 없습니다. + 매핑·매크로 추가로 시작하세요.') if self.doc.macros else _ui_tr('목록을 읽어 표시합니다. + 매핑·매크로 추가를 누르면 먼저 목록을 읽습니다.')
            tk.Label(box,text=text,bg=CARD,fg=MUTED,wraplength=420,justify='left',pady=16).grid(row=7,column=0,columnspan=2,sticky='ew')
        self.update_macro_warnings()
    def edit_macro(self,index,initial=None):
        if self.busy:return
        data=initial if initial is not None else self.doc.macros.get(str(index))
        if data is None:return
        if data[4]&16:self.progress.configure(text=_ui_tr('모션 제스처는 편집 대상에서 제외했습니다.'));return
        from studio_macro_editor import MacroEditor
        old=getattr(self,'macro_editor',None)
        if old and not old.closed:old.close()
        self.macro_editor=MacroEditor(self,index,embedded=True,initial=initial);self.update_editor_view()
    def copy_trigger(self, source, target):
        if self.busy:
            return
        values=self.doc.values
        target_mode,target_depth,target_output,target_button=fast_trigger_keys(target)
        copy_fast=fast_trigger_active(values,source)
        if copy_fast:
            if not all(k in values for k in (target_mode,target_depth,target_output)):return
            if not self.confirm_fast_trigger(target):return
        for key in TRIGGER_FIELDS:
            if key.startswith(source) and not (source == 'at_' and key.startswith('at_l2_')):
                destination = target + key[len(source):]
                if destination in TRIGGER_FIELDS and key in self.doc.values and destination in self.doc.values:
                    self.doc.values[destination] = self.doc.values[key]
        if copy_fast:
            values.update({target_mode:1,target_depth:values[fast_trigger_keys(source)[1]],target_output:target_button})
        elif fast_trigger_active(values,target):
            values[target_mode]=0
        self.stage_trigger_priority()
        self.update_state()
        self.render_fields()

    def stage_trigger_priority(self):
        values = self.doc.values
        if 'synth_force' in values:
            values['synth_force'] = int(any(
                values.get(prefix+'mode') or fast_trigger_active(values,prefix)
                for prefix in ('at_l2_', 'at_')
            ))

    def confirm_fast_trigger(self, prefix):
        mode, depth, _, _ = fast_trigger_keys(prefix)
        values = self.doc.values
        if not (values.get(mode,0) & 3 and values.get(depth)) or fast_trigger_active(values,prefix):
            return True
        side = 'L2' if prefix == 'at_l2_' else 'R2'
        return messagebox.askyesno(ui_text('단축 트리거','Short-pull trigger'),
            ui_text(f'{side}에 설정된 2단계 입력을 단축 트리거로 바꿀까요?',
                    f'Replace the existing two-stage input on {side} with Short-pull trigger?'), parent=self.parent)

    def render_construction(self):
        effects = [ui_text('끔', 'Off'), ui_text('일정한 저항', 'Constant resistance'),
                   ui_text('점점 무거워짐', 'Increasing resistance'),
                   ui_text('2단계 저항', 'Two-stage resistance'), ui_text('눌러 넘는 벽', 'Breakable wall')]
        sides = {'L2': 'at_l2_', 'R2': 'at_'}
        side = getattr(self, '_trigger_side', 'L2')
        prefix = sides[side]
        other = 'R2' if side == 'L2' else 'L2'
        values = self.doc.values
        fast_mode, fast_depth, fast_output, fast_button = fast_trigger_keys(prefix)
        fast_available = all(key in values for key in (fast_mode,fast_depth,fast_output,prefix+'start_pos',prefix+'strength',prefix+'pushback'))
        fast_active = fast_trigger_active(values,prefix)
        fast_name = ui_text('단축 트리거','Short-pull trigger')
        mode = values.get(prefix + 'mode', 0)
        shape = values.get(prefix + 'shape', 0)
        enabled = not self.busy and prefix + 'mode' in values and prefix + 'shape' in values
        box = self.card(ui_text('커스텀 트리거', 'Custom triggers'))
        tabs = tk.Frame(box, bg=CARD)
        tabs.grid(row=1, column=0, columnspan=2, sticky='ew', pady=(0, 8))

        def switch(target):
            self._trigger_side = target
            self.refresh_read_extras()

        for column, (name, key) in enumerate(sides.items()):
            active = values.get(key + 'mode', 0)
            form = values.get(key + 'shape', 0)
            summary = (ui_text('미확인', 'Unknown') if key + 'mode' not in values
                       else fast_name if fast_trigger_active(values,key)
                       else effects[form + 1] if active and form in range(4) else effects[0])
            if any(field in self.doc.changes for field in (key+'mode',key+'shape',*fast_trigger_keys(key)[:3])):
                summary += ' · ' + ui_text('편집 중','Edited')
            ttk.Button(tabs, text=f'{name} · {summary}', command=lambda name=name:switch(name),
                       style='Selected.Filter.TButton' if name == side else 'Filter.TButton').grid(
                           row=0, column=column, sticky='ew', padx=(0, 5))
            tabs.columnconfigure(column, weight=1)

        available_effects = effects[:1] + ([fast_name] if fast_available else []) + effects[1:]
        selected = tk.StringVar(value=fast_name if fast_active else effects[shape + 1] if mode and shape in range(4) else effects[0])
        choice = ttk.Combobox(box, textvariable=selected, values=available_effects, state='readonly' if enabled else 'disabled')
        choice.grid(row=2, column=1, sticky='ew', pady=8)
        tk.Label(box, text=ui_text('효과', 'Effect'), bg=CARD, fg=FG).grid(row=2, column=0, sticky='w')

        def defaults_for(form):
            from studio_help import reference_point
            if form == 'fast':
                return {'strength':100,'start_pos':FAST_TRIGGER_RESISTANCE_START,'pushback':0}
            defaults={'strength':reference_point(prefix+'strength')[0],
                      'start_pos':2 if form==3 else 0}
            if form in (1,2):
                defaults.update(strength=0 if form==1 else 40,strength_b=100)
            if form in (2,3):defaults['detent_pos']=reference_point(prefix+'detent_pos')[0]
            return defaults

        def select(_event):
            if self.busy:return
            defaults={}
            if selected.get() == fast_name and fast_available:
                if not fast_active:
                    if not self.confirm_fast_trigger(prefix):
                        selected.set(effects[shape + 1] if mode and shape in range(4) else effects[0])
                        return
                    values.update({fast_mode:1,fast_depth:FAST_TRIGGER_DEFAULT,fast_output:fast_button,
                                   prefix+'mode':2,prefix+'shape':0})
                    self.invalid.pop(fast_depth,None)
                    defaults=defaults_for('fast')
            else:
                index = effects.index(selected.get())
                if fast_active:values[fast_mode]=0
                if index == 0:values[prefix + 'mode']=0
                else:
                    new_shape=index-1
                    values[prefix + 'shape']=new_shape
                    if not mode or fast_active or new_shape!=shape:
                        defaults=defaults_for(new_shape)
                    if not mode:values[prefix + 'mode']=2
            for suffix,default in defaults.items():
                key=prefix+suffix
                if key in values and default is not None:
                    values[key]=default
                    self.invalid.pop(key,None)
            self.stage_trigger_priority()
            self.progress.clear()
            self.refresh_read_extras()
            self.update_state()
            if values.get(prefix+'mode'):
                self.reveal_trigger_field(fast_depth if selected.get()==fast_name else prefix+'strength')

        choice.bind('<<ComboboxSelected>>', select)
        row = 3
        open_groups = self._open_option_groups

        def toggle(group, first_field):
            open_groups.symmetric_difference_update({group})
            self.refresh_read_extras()
            if group in open_groups and first_field in self.field_views:
                self.reveal_trigger_field(first_field)

        def field(key, ko, en, choices=None, limits=None, default=None):
            nonlocal row
            spec = list(EDITABLE[key]);spec[3] = ui_text(ko,en)
            if choices is not None:spec[5] = choices
            if limits is not None:spec[5] = limits
            self.field_row(box, row, spec, default=default)
            row += 1

        if fast_active or mode:
            preview = tk.Canvas(box, height=24, bg=CARD, highlightthickness=0)
            preview.grid(row=row, column=0, columnspan=2, sticky='ew');row += 1

            def preview_value(key):
                try:return int(self.vars[key].get())
                except (KeyError,ValueError):return values.get(key,0)

            def draw_preview(*_):
                start, end = (preview_value(prefix + key) for key in ('start_pos','detent_pos'))
                start, end = max(0,min(9,start)), max(0,min(9,end))
                if shape == 3:
                    start = max(2,min(7,start));end = max(start + 1,min(8,end))
                width = max(preview.winfo_width(), 40) / 10
                has_resistance=not fast_active or preview_value(prefix+'strength')>0
                preview.delete('all')
                for step in range(10):
                    active = has_resistance and step >= start and (shape != 3 or step < end)
                    fill = FG if shape in (2,3) and step == end else GOLD if active else BORDER
                    preview.create_rectangle(step*width,5,(step+1)*width-3,20,fill=fill,outline='')

            preview.bind('<Configure>', draw_preview)
            legend=ui_text('금색 · 저항 구간','Gold: resistance range') if fast_active else ui_text(
                '얕게 눌림 → 깊게 눌림 · 밝은 칸은 저항 또는 걸림 위치','Shallow → deep press · highlights show resistance and break points')
            tk.Label(box, text=legend,
                     bg=CARD, fg=MUTED, wraplength=420, justify='left').grid(row=row,column=0,columnspan=2,sticky='w')
            row += 1
        if fast_active:
            field(fast_depth,'100%로 인식되는 깊이','Depth for full input',limits=FAST_TRIGGER_DEPTH,default=FAST_TRIGGER_DEFAULT)
            field(prefix+'start_pos','저항 시작 위치','Resistance starts at',default=FAST_TRIGGER_RESISTANCE_START)
            field(prefix+'strength','저항 세기','Resistance strength',default=100)
            for key in (prefix+'start_pos',prefix+'strength'):
                widget_trace(preview,self.vars[key],draw_preview)
        elif mode:
            defaults=defaults_for(shape)
            field(prefix + 'strength', '시작 세기' if shape in (1,2) else '저항 세기', 'Starting force' if shape in (1,2) else 'Resistance strength',default=defaults['strength'])
            field(prefix + 'start_pos', '저항 시작 위치', 'Resistance starts at',
                  limits=(2,7) if shape == 3 else None, default=defaults['start_pos'])
            if shape in (1,2):field(prefix + 'strength_b', '끝 세기', 'End force',default=defaults['strength_b'])
            if shape in (2,3):
                field(prefix + 'detent_pos', '벽 통과 위치' if shape == 3 else '걸림 위치',
                      'Break point' if shape == 3 else 'Detent position', limits=(3,8) if shape == 3 else None, default=defaults['detent_pos'])
            for key in ('start_pos','detent_pos'):
                if prefix + key in self.vars:widget_trace(preview,self.vars[prefix + key],draw_preview)
            field(prefix + 'mode','저항이 켜지는 조건','When resistance is active',
                  [(2,ui_text('항상','Always')),(1,ui_text(f'{other}를 누르는 동안',f'While {other} is held')),
                   (3,ui_text(f'{other[0]}1을 누르는 동안',f'While {other[0]}1 is held'))])
            if mode == 1:field(prefix + 'threshold',f'{other}를 눌러야 하는 깊이',f'Required {other} pull depth')
            if values.get('ce_l2_enable' if side == 'L2' else 'ce_r2_enable'):
                tk.Label(box,text=ui_text('장치에 설정된 사용자 효과가 저항보다 우선할 수 있습니다.',
                                         'A stored custom effect may take priority over resistance.'),
                         bg=CARD,fg=MUTED,wraplength=420,justify='left').grid(row=row,column=0,columnspan=2,sticky='w')
                row += 1

            recoil = (side,'recoil')
            ttk.Button(box,text=('▾ ' if recoil in open_groups else '▸ ')+ui_text('반동 설정','Recoil settings'),
                       command=lambda:toggle(recoil,prefix+'pushback')).grid(row=row,column=0,columnspan=2,sticky='ew',pady=4)
            row += 1
            if recoil in open_groups:
                field(prefix + 'pushback','반동 세기 · 0이면 끔','Recoil strength · 0 turns it off')
                recoil_enabled = bool(values.get(prefix + 'pushback', 0))
                entry, slider, _title = self.range_controls[prefix + 'pushback']
                def refresh_recoil(_event):
                    if recoil_enabled != bool(values.get(prefix + 'pushback', 0)):
                        self.parent.after_idle(self.refresh_read_extras)
                entry.bind('<FocusOut>', refresh_recoil, add='+')
                entry.bind('<Return>', refresh_recoil, add='+')
                slider.bind('<ButtonRelease-1>', refresh_recoil, add='+')
                slider.bind('<KeyRelease>', refresh_recoil, add='+')
                if recoil_enabled:
                    field(prefix + 'kick_style','반동 느낌','Recoil feel',
                          [(0,ui_text('진동','Vibration')),(1,ui_text('손가락을 밀어냄','Pushes back'))])
                    if not values.get(prefix + 'kick_style', 0):
                        field(prefix + 'pushback_freq','진동 주파수','Vibration frequency')
                tk.Label(box,text=ui_text('반동에는 진동 또는 오디오햅틱 신호가 필요합니다.',
                                         'Recoil needs a rumble or audio haptics signal.'),bg=CARD,fg=MUTED).grid(row=row,column=0,columnspan=2,sticky='w')
                row += 1
        common = ('triggers','common')
        ttk.Button(box,text=('▾ ' if common in open_groups else '▸ ')+ui_text('L2/R2 공통 설정','Shared L2/R2 settings'),
                   command=lambda:toggle(common,'at_pushback_src')).grid(row=row,column=0,columnspan=2,sticky='ew',pady=4)
        row += 1
        if common in open_groups:
            field('at_pushback_src','반동을 일으키는 신호','Recoil signal',
                  [(0,ui_text('일반 진동','Game rumble')),(1,ui_text('오디오햅틱','Audio haptics')),
                   (2,ui_text('둘 중 강한 신호','Stronger of the two'))])
            self.field_row(box,row,EDITABLE['synth_force'],title_text=ui_text('게임 효과보다 내 설정 우선','Prefer my settings over game effects'))
            row += 1
        ttk.Button(box,text=ui_text(f'{side} 설정을 {other}에 복사',f'Copy {side} settings to {other}'),
                   command=lambda:self.copy_trigger(prefix,sides[other]),
                   state='normal' if enabled and sides[other] + 'mode' in values and
                   (not fast_active or all(key in values for key in fast_trigger_keys(sides[other])[:3])) else 'disabled').grid(row=row,column=0,sticky='w',pady=6)
        ttk.Button(box,text=ui_text('Pico 효과 상태 확인','Check Pico effect status'),
                   command=lambda:self.check_trigger_status(side),
                   state='normal' if self.path and self.loaded and not self.busy else 'disabled').grid(row=row,column=1,sticky='e',pady=6)

    def reveal_trigger_field(self,key):
        view=self.field_views.get(key)
        if view is not None:
            widget=view[0]
            self.restore_scroll_offset(widget.winfo_rooty()-self.body.winfo_rooty()-8)

    def check_trigger_status(self, side):
        def read(client):
            fields = bytes((2,0x36,0x3c))
            reply = client.command(0x0c,fields,echo=bytes((2,)))
            if len(reply) < 10 or reply[2:6] != bytes((0,2,0x36,1)) or reply[7:9] != bytes((0x3c,1)):
                raise ValueError(ui_text('장치가 트리거 상태 조회를 지원하지 않습니다.', 'Trigger status is unavailable on this device.'))
            return side, reply[6], reply[9]
        self.task('trigger_status',lambda:self.with_client(read))

    def render_effects(self):self.render_construction()
    def edit_effect(self,trig,index):
        self.progress.configure(text=_ui_tr('커스텀 트리거는 공사 중입니다.'))
    def show_history(self,records):
        self.progress.configure(text=_ui_tr('커스텀 트리거는 공사 중입니다.'))
    def render_slots(self):
        box=self.card(_ui_tr('Studio 프로필 슬롯'))
        tools=tk.Frame(box,bg=CARD);tools.grid(row=1,column=0,columnspan=2,sticky='ew')
        for i,(title,action) in enumerate([(_ui_tr('슬롯 목록 새로 고침'),lambda:self.task('slots',lambda:self.with_client(lambda c:c.slots()))),(_ui_tr('전체 슬롯 내보내기'),self.backup),(_ui_tr('전체 슬롯 가져오기'),self.restore_backup)]):
            ttk.Button(tools,text=title,command=action).grid(row=0,column=i,sticky='ew',padx=(0,6));tools.columnconfigure(i,weight=1)
        tk.Label(box,text=_ui_tr('백업 범위: 현재 편집 가능한 설정·일반 매크로'),bg=CARD,fg=MUTED,wraplength=440,justify='left').grid(row=2,column=0,columnspan=2,sticky='w',pady=10)
        visible=self.slots if self.slots_expanded else self.slots[:8]
        for n,slot in enumerate(visible):
            index=slot.index
            row=tk.Frame(box,bg=CARD);row.grid(row=n+3,column=0,columnspan=2,sticky='ew',pady=4);row.columnconfigure(0,weight=1)
            active=bool(self.current_save_target() and self.current_save_target()[0]==index)
            slot_label=tk.Label(row,text=slot.label(),bg=CARD,fg=GOLD if active else FG,anchor='w',justify='left',width=1)
            slot_label.grid(row=0,column=0,sticky='ew')
            slot_label.bind('<Configure>',self.fit_slot_label)
            ttk.Button(row,text=_ui_tr('현재 설정 저장'),command=lambda i=index:self.save_slot(i),width=0,padding=(12,6)).grid(row=0,column=2,padx=4)
            ttk.Button(row,text=_ui_tr('불러오기'),command=lambda i=index:self.activate_slot(i),width=9,state='normal' if slot.state=='saved' else 'disabled').grid(row=0,column=3)
            if self.current_save_target() and self.current_save_target()[0]==index:
                ttk.Button(row,text=_ui_tr('이름 변경'),command=self.rename_current_profile,width=9).grid(row=0,column=1,padx=(4,0))
        if len(self.slots)>8:
            ttk.Button(box,text=_ui_tr('9–32번 슬롯 접기') if self.slots_expanded else _ui_tr('9–32번 슬롯 펼치기'),command=self.toggle_slots).grid(row=len(visible)+3,column=0,columnspan=2,sticky='ew',pady=(12,0))
    def toggle_slots(self):self.slots_expanded=not self.slots_expanded;self.render_fields()
    def save_slot(self,index):
        if self.busy or not self.write_ready:return
        from studio_dialogs import profile_name
        existing=next((s for s in self.slots if s.index==index and s.state=='saved'),None)
        previous=existing.name if existing is not None else ''
        target=self.current_save_target()
        if existing is not None and (target is None or target[0]!=index):
            if not messagebox.askyesno(_ui_tr('다른 프로필에 저장'),_ui_tr('{0} · {1}을 현재 설정으로 덮어쓸까요?\n공유 매크로 정의는 저장하지 않습니다.').format(f'{index + 1:02d}',f"{previous or '이름 없음'}"),parent=self.parent):return
        name=previous if existing is not None else profile_name(self.parent,initial=previous)
        if name is not None:
            self.apply(True,target=(index,name))
    def rename_current_profile(self):
        target=self.current_save_target()
        if target is None or self.busy or not self.write_ready:return
        if self.doc.dirty:
            messagebox.showinfo(_ui_tr('프로필 이름 변경'),_ui_tr('편집 중인 변경을 먼저 저장하거나 되돌린 뒤 이름을 변경하세요.'),parent=self.parent);return
        from studio_dialogs import profile_name
        name=profile_name(self.parent,initial=target[1])
        if name is not None and name!=target[1]:self.apply(True,target=(target[0],name))
    def activate_slot(self,index):
        if self.busy or self.app.studio.busy or not self.write_ready:return
        def activate():
            position=next((i for i,s in enumerate(self.slots) if s.index==index),None)
            if position is None:return
            self.app.studio.slot_paths=[self.path for _ in self.slots];self.app.studio.slots=list(self.slots);self.app.studio.choice.configure(values=[s.label() for s in self.slots]);self.app.studio.choice.current(position);self.doc.revert();self.app.studio.activate(confirmed=True);self.loaded=False;self.progress.configure(text=_ui_tr('프로필 전환 중 · 완료 후 설정 자동 조회'),kind='progress')
        def proceed():
            if self.app.engine:self.app.stop(on_complete=activate)
            else:activate()
        self.request_profile_switch(proceed)
    def backup(self):
        from studio_backup import backup_all
        self.task('backup',lambda:self.with_client(lambda c:backup_all(c,lambda t:self.results.put(('progress',t,None)))))
    def restore_backup(self):
        if self.busy or not self.loaded or not self.write_ready:return
        from studio_backup import validate_backup,restore_all
        name=filedialog.askopenfilename(parent=self.parent,filetypes=[(_ui_tr('슬롯 백업 JSON'),'*.json')])
        if not name:return
        try:rows,macros=validate_backup(json.loads(Path(name).read_text(encoding='utf-8-sig')))
        except Exception as exc:messagebox.showerror(_ui_tr('백업 확인'),str(exc),parent=self.parent);return
        if not messagebox.askyesno(_ui_tr('Pico 슬롯 덮어쓰기'),_ui_tr('{0}개 유효 슬롯과 포함된 일반 매크로 정의를 덮어씁니다.\n\n지원 필드만 복원합니다. 제외된 트리거 등은 현재 연결의 값으로 슬롯에 저장됩니다. 전체 설정을 보존하려면 원본 Studio 백업을 사용하세요.\n\n빈 슬롯은 삭제하지 않습니다. 계속할까요?').format(f'{len(rows)}'),parent=self.parent):return
        self.stopped_task('restore',lambda:self.with_client(lambda c:restore_all(c,rows,macros,lambda t:self.results.put(('progress',t,None)))))
    def close(self):
        self.close_entry_queries();self.stop_live();self.closed=True;self.cancel.set()
        if self.return_list_job:
            try:self.app.root.after_cancel(self.return_list_job)
            except tk.TclError:pass
            self.return_list_job=None
        editor=getattr(self,'macro_editor',None)
        if editor and not editor.closed:editor.close()
        if self.poll_id:
            try:self.parent.after_cancel(self.poll_id)
            except tk.TclError:pass
        if self.search_job:
            try:self.parent.after_cancel(self.search_job)
            except tk.TclError:pass
        for tip in self.tips:tip.hide()
    def effect_builder(self,parent,raw):
        self.progress.configure(text=_ui_tr('커스텀 트리거는 공사 중입니다.'))
    def timeline_start(self):
        self.progress.configure(text=_ui_tr('커스텀 트리거는 공사 중입니다.'))
    def timeline_stop(self):
        self.progress.configure(text=_ui_tr('커스텀 트리거는 공사 중입니다.'))
    def show_timeline(self,records):
        self.progress.configure(text=_ui_tr('커스텀 트리거는 공사 중입니다.'))
    def finish_recording_for_close(self):
        self.recording=False # No trigger recording is started in this editor scope.
