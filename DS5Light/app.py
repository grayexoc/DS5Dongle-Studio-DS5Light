from thread_start import start_thread
from studio_i18n import text as _ui_tr
import os

os.environ.setdefault('OPENBLAS_NUM_THREADS','1')

os.environ.setdefault('OMP_NUM_THREADS','1')

import threading

import time

import json

import sys

import ctypes

import queue

import random

import tkinter as tk

import tkinter.font as tkfont

from tkinter import ttk

from studio_dialogs import messagebox, simpledialog

from pathlib import Path

from dataclasses import asdict, replace

from audio import Engine, InstanceLock, devices

from core import Controls
from app_version import APP_VERSION

from process_audio import ProcessSampler

from process_filter import is_excluded_process

from presets import PresetStore, SLOT_COUNT, match_game

from preferences import PreferenceStore

from studio_panel import StudioPanel

from studio_settings_ui import FieldTip, StudioSettings, ui_text

from localization import tr, LANGUAGE, save_language, canonical_device, display_device

from ui_controls import circle_image, RadioChoice, CircleCheck, SectionTitle, AutoScrollbar, install_combobox_selection_cleanup

from mute_shortcut import MuteShortcut, KEYS, MODIFIERS, binding_label, validate_binding

from ui_controls import GlobalCaptureOverlay, RoundedCard, DiagnosticCanvas, draw_ui_symbol
from ui_dpi import enable_dpi_awareness,install_dpi,fit_window,px,watch_scale,scale_styles

from battery_status import BatteryMonitor

from battery_logo import BatteryLogo, HoverHint

from controller_presence import ControllerPresence,IdleControllerPresence

from studio_profile_watch import ProfileWatch

from run_intent import RunIntent

from studio_power import StudioPower,blocked as power_blocked
from device_diagnostics_ui import open_diagnostics, update_diagnostics_button



BG='#0b0b0c'; CARD='#151515'; FG='#f2f0e9'; MUTED='#a7a297'; BORDER='#303030'; ACCENT='#d6ad52'; DISABLED='#969187'

SPACE=8; SPACE_LG=12; PAGE_MARGIN_X=18; PAGE_MARGIN_Y=12; CARD_INSET_X=20; CARD_INSET_Y=20

AUTO=_ui_tr('자동 선택 · 기존 BAT 방식')

CHANNELS={_ui_tr('자동'):0,_ui_tr('2채널 (스테레오)'):2,_ui_tr('5.1채널 (홈시어터)'):6,_ui_tr('7.1채널 (서라운드)'):8}

LIMITERS={_ui_tr('초과분 자르기'):'hard',_ui_tr('부드러운 제한'):'soft'}

PROCESS_SORTS={_ui_tr('최근 실행'):'recent',_ui_tr('CPU 사용률'):'cpu',_ui_tr('오디오 출력'):'audio'}

AUDIO_STATES={'playing':_ui_tr('출력 중'),'active':_ui_tr('세션 활성'),'inactive':'·','unknown':_ui_tr('확인 불가')}



def apply_windows_titlebar_theme(root):

    """Apply the app's dark palette to the top-level DWM window, not Tk's child HWND."""

    if os.name != 'nt': return

    try:

        user32=ctypes.WinDLL('user32',use_last_error=True)

        user32.GetAncestor.argtypes=[ctypes.c_void_p,ctypes.c_uint]

        user32.GetAncestor.restype=ctypes.c_void_p

        child=ctypes.c_void_p(root.winfo_id())

        hwnd=user32.GetAncestor(child,2) or child

        # The caption icon is set through Tk; NULL would restore the class icon.

        dwm=ctypes.WinDLL('dwmapi',use_last_error=True)

        setter=dwm.DwmSetWindowAttribute

        setter.argtypes=[ctypes.c_void_p,ctypes.c_uint,ctypes.c_void_p,ctypes.c_uint]

        setter.restype=ctypes.c_long

        dark=ctypes.c_int(1)

        for attribute in (20,19):

            result=setter(hwnd,attribute,ctypes.byref(dark),ctypes.sizeof(dark))

            if result==0: break

        def colorref(hex_color):

            value=int(hex_color.lstrip('#'),16)

            red,green,blue=(value>>16)&255,(value>>8)&255,value&255

            return ctypes.c_int(red|(green<<8)|(blue<<16))

        for attribute,value in ((35,colorref(BG)),(36,colorref(FG))):

            setter(hwnd,attribute,ctypes.byref(value),ctypes.sizeof(value))

        # DWMWA_COLOR_NONE suppresses the native frame stroke on Windows 11.

        # Older systems retain their caption behavior, with a matching dark edge.

        no_border=ctypes.c_uint(0xfffffffe)

        if setter(hwnd,34,ctypes.byref(no_border),ctypes.sizeof(no_border))!=0:

            edge=colorref(BG)

            setter(hwnd,34,ctypes.byref(edge),ctypes.sizeof(edge))

        # Leave native caption painting and geometry entirely to Windows.

        # Never subclass the wrapper, draw into its DC, or change thread DPI.

    except Exception:

        pass



class Switch(tk.Canvas):

    """Static native Tk switch: no animation, web engine or polling."""

    def __init__(self,parent,variable,command):

        super().__init__(parent,width=px(parent,44),height=px(parent,26),bg=CARD,highlightthickness=1,

                         highlightbackground=CARD,highlightcolor=ACCENT,takefocus=1,cursor='hand2')

        self.variable=variable; self.command=command; self.enabled=True

        self.bind('<Button-1>',lambda e:self.invoke())

        self.bind('<space>',lambda e:self.invoke())

        self.bind('<Return>',lambda e:self.invoke())

        variable.trace_add('write',lambda *args:self.draw())

        watch_scale(self,self._scale_switch)
        self.draw()

    def _scale_switch(self):
        self.configure(width=px(self,44),height=px(self,26));self.draw()

    def invoke(self):

        if self.enabled:

            self.variable.set(not self.variable.get()); self.command()

        return 'break'

    def set_enabled(self,enabled):

        if self.enabled==enabled: return

        self.enabled=enabled; self.configure(takefocus=int(enabled),cursor='hand2' if enabled else 'arrow'); self.draw()

    def draw(self):

        self.delete('all')

        on=self.variable.get(); color=ACCENT if on and self.enabled else '#3a3832'

        self.create_oval(*(px(self,v) for v in (2,3,22,23)),fill=color,outline=color)

        self.create_oval(*(px(self,v) for v in (22,3,42,23)),fill=color,outline=color)

        self.create_rectangle(*(px(self,v) for v in (12,3,32,23)),fill=color,outline=color)

        x=25 if on else 5

        knob='#2b2110' if on and self.enabled else '#c4c0b6' if self.enabled else '#77736b'

        self.create_oval(*(px(self,v) for v in (x,6,x+14,20)),fill=knob,outline=knob)



def draw_open_top_round_box(canvas,left,top,right,bottom,radius,fill,outline,tag):

    """Draw rounded upper corners and side strokes, leaving the bottom open."""

    radius=min(radius,(right-left)/2,(bottom-top)/2)

    options=dict(tags=(tag,))

    canvas.create_rectangle(left,top+radius,right,bottom,fill=fill,outline='',**options)

    canvas.create_rectangle(left+radius,top,right-radius,top+radius,fill=fill,outline='',**options)

    for x,start in ((left,90),(right-2*radius,0)):

        canvas.create_arc(x,top,x+2*radius,top+2*radius,start=start,extent=90,

                          style='pieslice',fill=fill,outline='',**options)

        canvas.create_arc(x,top,x+2*radius,top+2*radius,start=start,extent=90,

                          style='arc',outline=outline,width=1,**options)

    canvas.create_line(left+radius,top,right-radius,top,fill=outline,width=1,**options)

    canvas.create_line(left,top+radius,left,bottom,fill=outline,width=1,**options)

    canvas.create_line(right,top+radius,right,bottom,fill=outline,width=1,**options)



class PageOutline(tk.Canvas):

    """Borderless page host retaining consistent spacing around section cards."""

    def __init__(self,parent):

        super().__init__(parent,bg=BG,highlightthickness=0,borderwidth=0,takefocus=0)

        self.content=tk.Frame(self,bg=BG,highlightbackground=BORDER,highlightcolor=BORDER,

                              highlightthickness=0,borderwidth=0,takefocus=0)

        self._body=self.create_window(0,0,anchor='nw',window=self.content)

        self.bind('<Configure>',self._resize)

    def _resize(self,event):

        self.itemconfigure(self._body,width=max(1,event.width),height=max(1,event.height))

        self.delete('outline')



class TabStrip(tk.Canvas):

    """Rectangular tabs sharing the PC filter preset palette."""

    def __init__(self,parent,labels,on_select):

        super().__init__(parent,height=44,bg=BG,highlightthickness=0,borderwidth=0,cursor='hand2')

        self.labels=list(labels);self.icons=('waveform','gear','sliders'); self.on_select=on_select; self.selected=0; self.hover=-1

        self.style=ttk.Style(parent)

        self.font=tkfont.Font(family=_ui_tr('맑은 고딕'),size=12,weight='bold')

        self._measure_tabs()

        self.bind('<Configure>',lambda _event:self.draw())

        self.bind('<Motion>',self._motion); self.bind('<Leave>',self._leave); self.bind('<Button-1>',self._click)

        watch_scale(self,self._scale_tabs)
        self.draw()

    def _measure_tabs(self):
        self.icon_widths=[px(self,18) if icon in ('waveform','gear','sliders') else self.font.measure(icon) for icon in self.icons]

        self.tab_padding=max(px(self,8),round((px(self,41)-self.font.metrics('linespace'))/2))

        self.tab_widths=[self.font.measure(label)+self.icon_widths[i]+px(self,8)+2*self.tab_padding for i,label in enumerate(self.labels)]

        self.label_tracking=[0.0]*len(self.labels)

        if LANGUAGE=='ko' and len(self.labels)>=2:

            # Use Settings/Diagnostics as the base, with extra room for Studio.

            shared_width=self.tab_widths[1]

            self.tab_widths=[shared_width]*len(self.labels)

            if len(self.labels)==3:

                self.tab_widths[2]+=px(self,12)

            for i,label in enumerate(self.labels):

                if i==1: continue

                label_room=self.tab_widths[i]-self.icon_widths[i]-px(self,8)-2*self.tab_padding

                text_width=sum(self.font.measure(ch) for ch in label)

                self.label_tracking[i]=(label_room-text_width)/max(1,len(label)-1)

        self.tab_width=self.tab_widths[-1]

        self.configure(height=px(self,44),width=sum(self.tab_widths)+px(self,8)*(len(self.labels)-1))

    def _scale_tabs(self):
        self._measure_tabs();self.draw()

    def _motion(self,event):

        hover=self._hit(event.x)

        if hover!=self.hover:

            self.hover=hover; self.draw()

    def _leave(self,_event):

        if self.hover!=-1:

            self.hover=-1; self.draw()

    def _hit(self,x):

        for index in range(len(self.labels)):

            left=self._left(index)

            if left<=x<=left+self.tab_widths[index]: return index

        return -1

    def _click(self,event):

        index=self._hit(event.x)

        if index>=0: self.on_select(index)

    def select(self,index): self.selected=index; self.draw()

    def _left(self,index):

        left=sum(self.tab_widths[:index])+index*px(self,8)

        return max(left,self.winfo_width()-self.tab_widths[index]) if len(self.labels)==3 and index==2 else left

    def draw(self):

        self.delete('all'); x=0

        for index,label in enumerate(self.labels):

            x=self._left(index)

            width=self.tab_widths[index]; y=px(self,1); bottom=px(self,42)

            selected=index==self.selected

            preset_style='Selected.Filter.TButton' if selected else 'Filter.TButton'

            state=('active',) if index==self.hover else ()

            fill=self.style.lookup(preset_style,'background',state=state)

            outline=self.style.lookup(preset_style,'bordercolor',state=state)

            foreground=self.style.lookup(preset_style,'foreground',state=state)

            left=x+1;right=x+width-1;tag=f'tab-{index}'

            self.create_rectangle(left,y,right,bottom,fill=fill,outline=outline,tags=tag)

            icon=self.icons[index];icon_width=self.icon_widths[index]

            tracking=self.label_tracking[index]

            tracked=abs(tracking)>.001

            label_width=(sum(self.font.measure(ch) for ch in label)+tracking*(len(label)-1)

                         if tracked else self.font.measure(label))

            start=x+(width-icon_width-px(self,8)-label_width)/2

            center_y=(y+bottom)/2

            if icon in ('waveform','gear','sliders'):

                icon_size=px(self,18)*.9 if icon in ('gear','sliders') else px(self,18)

                draw_ui_symbol(self,icon,start+(icon_width-icon_size)/2,center_y-icon_size/2+px(self,2),icon_size,ACCENT,tags=(tag,f'icon-{index}'))

            else:

                self.create_text(start,center_y+px(self,2),text=icon,font=self.font,fill=ACCENT,anchor='w',tags=(tag,f'icon-{index}'))

            if tracked:

                text_x=start+icon_width+px(self,8)

                for character in label:

                    self.create_text(text_x,center_y,text=character,font=self.font,

                                     anchor='w',fill=foreground,tags=(tag,))

                    text_x+=self.font.measure(character)+tracking

            else:

                self.create_text(start+icon_width+px(self,8),center_y,text=label,font=self.font,

                                 anchor='w',fill=foreground,tags=(tag,))

            x+=width+8



class HapticSlider(tk.Canvas):

    """Compact gold range control matching the app's visual theme."""

    def __init__(self,parent,variable,command,maximum=100,reference=None,background=CARD,width=200):

        super().__init__(parent,width=px(parent,width),height=px(parent,36 if reference is not None else 24),bg=background,highlightthickness=0,borderwidth=0,takefocus=1,cursor='hand2')

        self.variable=variable; self.command=command; self.enabled=True

        self.label_font=tkfont.Font(family=_ui_tr('맑은 고딕'),size=7)

        self.pad=max(px(self,9),(self.label_font.measure(f'{maximum}%')+1)//2+px(self,2)) if reference is not None else px(self,9)

        self.maximum=maximum; self.reference=reference;self._logical_width=width
        watch_scale(self,self._scale_slider)

        self.bind('<Configure>',lambda _event:self.draw()); self.bind('<Button-1>',self._click); self.bind('<B1-Motion>',self._drag)

        self.bind('<KeyPress>',self._key); variable.trace_add('write',lambda *_:self.draw()); self.draw()

    def _scale_slider(self):
        self.pad=max(px(self,9),(self.label_font.measure(f'{self.maximum}%')+1)//2+px(self,2)) if self.reference is not None else px(self,9)
        self.configure(width=px(self,self._logical_width),height=px(self,36 if self.reference is not None else 24));self.draw()

    def _set_from_x(self,x):

        width=max(self.winfo_width()-2*self.pad,1)

        value=max(0,min(self.maximum,(x-self.pad)*self.maximum/width)); self.variable.set(round(value,1)); self.command()

    def _click(self,event):

        if self.enabled: self.focus_set(); self._set_from_x(event.x)

    def _drag(self,event):

        if self.enabled: self._set_from_x(event.x)

    def _key(self,event):

        if not self.enabled: return 'break'

        value=self.variable.get()

        if event.keysym=='Home': value=0

        elif event.keysym=='End': value=self.maximum

        elif event.keysym in ('Left','Down','Prior'): value-=10 if event.keysym=='Prior' else 1

        elif event.keysym in ('Right','Up','Next'): value+=10 if event.keysym=='Next' else 1

        else: return

        self.variable.set(max(0,min(self.maximum,value))); self.command(); return 'break'

    def set_enabled(self,enabled):

        if self.enabled==enabled:return
        self.enabled=enabled; self.configure(takefocus=int(enabled),cursor='hand2' if enabled else 'arrow'); self.draw()

    def draw(self):

        self.delete('all'); width=max(self.winfo_width(),2*self.pad+1); y=px(self,12); left=self.pad; right=width-self.pad

        knob=left+(right-left)*max(0,min(self.maximum,self.variable.get()))/self.maximum

        self.create_rectangle(left,y-px(self,3),right,y+px(self,3),fill='#242321',outline=BORDER,width=1)

        edge=ACCENT if self.enabled else DISABLED

        if knob>left: self.create_rectangle(left,y-px(self,2),knob,y+px(self,2),fill=edge,outline=edge,width=0)

        self.create_oval(knob-px(self,7),y-px(self,7),knob+px(self,7),y+px(self,7),fill=CARD,outline=edge,width=px(self,2))

        self.create_oval(knob-px(self,2),y-px(self,2),knob+px(self,2),y+px(self,2),fill=edge,outline=edge)

        if self.reference is not None:

            ref=left+(right-left)*self.reference/self.maximum

            self.create_line(ref,px(self,19),ref,px(self,23),fill=ACCENT)

            for x,label,anchor in ((left,'0%','nw'),(ref,f'{self.reference}%','n'),(right,f'{self.maximum}%','ne')):

                self.create_text(x,px(self,23),text=label,anchor=anchor,fill=MUTED,font=self.label_font)



class App:

    def _scale_cards(self):
        self._dpi_cards.configure(height=px(self.root,256))

    def __init__(self,root):

        install_dpi(root)
        self.root=root; self.engine=None; self.connection=None; self.last_render=None; self.device_channel_cache={}

        self.active_process_pid=None; self.active_process_started=None; self.active_process_name=None

        self.process_check_interval=5.0; self.next_process_check=0.0

        self._stopping=False; self._stop_callbacks=[]; self._stop_results=queue.SimpleQueue()

        self._stop_message=None; self._closing=False; self._close_requested=False; self._saved_preferences=None; self._next_stop_retry=0.

        self.selected_tab=0; self._diagnostics_text=None
        self._refresh_results=queue.SimpleQueue()

        self._diagnostic_spacing_job=None;self._diagnostic_spacing=None

        self._preset_selection=None; self._applying_preset=False

        self.mute_shortcut=MuteShortcut(); self._shortcut_dialog=None

        root.title(f'DS5Light v{APP_VERSION} - Modified'); root.configure(bg=BG,borderwidth=0,highlightthickness=0)

        root.iconbitmap(default=str(Path(__file__).resolve().parent/'assets'/'dslight.ico'))

        fit_window(root,860,1000,logical=True,min_width=px(root,860),min_height=px(root,860))

        root.bind('<Map>',lambda event:root.after_idle(lambda:apply_windows_titlebar_theme(root)) if event.widget is root else None,add='+')

        root.after(150,lambda:apply_windows_titlebar_theme(root))

        style=ttk.Style(root); style.theme_use('clam')

        style.configure('.',font=(_ui_tr('맑은 고딕'),10),background=CARD,foreground=FG)

        style.configure('TFrame',background=CARD)

        style.configure('TLabel',background=CARD,foreground=FG)

        style.configure('Muted.TLabel',foreground=MUTED)

        style.configure('TButton',padding=(12,6),background='#242321',foreground=FG,bordercolor=BORDER,relief='flat')

        style.map('TButton',background=[('disabled','#202020'),('active','#303030')],foreground=[('disabled',DISABLED)])

        style.configure('Accent.TButton',background=ACCENT,foreground='#211a0d',font=(_ui_tr('맑은 고딕'),10,'bold'))

        style.map('Accent.TButton',background=[('disabled','#242424'),('active','#e7c875')],foreground=[('disabled',DISABLED)])

        style.configure('Selected.TButton',background='#332b19',foreground='#f1d58c',bordercolor=ACCENT)

        # Omit Button.focus so these choices never draw a dotted inner rectangle.

        style.layout('Filter.TButton',[('Button.border',{'sticky':'nswe','children':[

            ('Button.padding',{'sticky':'nswe','children':[('Button.label',{'sticky':'nswe'})]})]})])

        style.layout('Footer.TButton',style.layout('Filter.TButton'))

        style.configure('Accent.Footer.TButton',background=ACCENT,foreground='#211a0d',font=(_ui_tr('맑은 고딕'),10,'bold'))

        style.map('Accent.Footer.TButton',background=[('disabled','#242424'),('active','#e7c875')],foreground=[('disabled',DISABLED)])

        style.configure('Filter.TButton',padding=(12,6),borderwidth=1,relief='solid',

                        bordercolor=BORDER,lightcolor=BORDER,darkcolor=BORDER)

        style.map('Filter.TButton',bordercolor=[('!disabled',BORDER)],

                  lightcolor=[('!disabled',BORDER)],darkcolor=[('!disabled',BORDER)])

        style.configure('Selected.Filter.TButton',background='#332b19',foreground='#f1d58c',

                        bordercolor=ACCENT,lightcolor=ACCENT,darkcolor=ACCENT)

        style.map('Selected.Filter.TButton',background=[('active','#42351d'),('!disabled','#332b19')],

                  bordercolor=[('disabled',BORDER),('!disabled',ACCENT)],

                  lightcolor=[('disabled',BORDER),('!disabled',ACCENT)],darkcolor=[('disabled',BORDER),('!disabled',ACCENT)])

        self.filter_corner=tk.PhotoImage(master=root,width=11,height=11)

        for y in range(11):self.filter_corner.put(ACCENT,to=(0,y,11-y,y+1))

        style.element_create('Filter.corner','image',self.filter_corner)

        style.layout('Selected.Filter.TButton',[('Button.border',{'sticky':'nswe','children':[

            ('Filter.corner',{'sticky':'nw'}),

            ('Button.padding',{'sticky':'nswe','children':[('Button.label',{'sticky':'nswe'})]})]})])

        style.configure('TCombobox',fieldbackground='#111110',background='#242321',arrowcolor=MUTED,bordercolor=BORDER,lightcolor=BORDER,darkcolor=BORDER,focuscolor=ACCENT,padding=7)

        style.configure('Limiter.TCombobox',padding=(8,10),font=(_ui_tr('맑은 고딕'),10))

        style.map('TCombobox',fieldbackground=[('disabled','#201f1c'),('readonly','#111110')],foreground=[('disabled',DISABLED),('readonly',FG)],bordercolor=[('focus',ACCENT),('!focus',BORDER)])

        install_combobox_selection_cleanup(root,FG,'#111110',DISABLED,'#201f1c')

        style.configure('TEntry',fieldbackground='#111110',bordercolor=BORDER,padding=6)

        entry_border='#3b3b3b';entry_disabled_border='#2c2c2c'

        style.configure('Studio.TEntry',fieldbackground='#111110',foreground=FG,

                        bordercolor=entry_border,lightcolor=entry_border,darkcolor=entry_border,

                        focuscolor=entry_border,borderwidth=1,padding=6)

        for option in ('bordercolor','lightcolor','darkcolor','focuscolor'):

            style.map('Studio.TEntry',**{option:[('disabled',entry_disabled_border),('!disabled',entry_border)]})

        style.configure('TCheckbutton',background=CARD,foreground=FG,indicatorcolor='#111110')

        style.map('TCheckbutton',foreground=[('disabled',DISABLED)],background=[('active',CARD)],

                  indicatorcolor=[('disabled','#242321'),('selected',ACCENT),('active','#332b19'),('!selected','#111110')])

        style.configure('TRadiobutton',background=CARD,foreground=FG,indicatorcolor='#111110')

        style.map('TRadiobutton',foreground=[('disabled',DISABLED)],background=[('active',CARD)],

                  indicatorcolor=[('disabled','#242321'),('selected',ACCENT),('active','#332b19'),('!selected','#111110')])

        style.configure('Process.Treeview',background='#111110',fieldbackground='#111110',foreground=FG,rowheight=28,borderwidth=0,relief='flat',bordercolor=BORDER,lightcolor=BORDER,darkcolor=BORDER,focuscolor=ACCENT)

        style.map('Process.Treeview',background=[('selected','#4a3b1c')],foreground=[('selected','#f6e6b9')],

                  bordercolor=[('focus',BORDER),('!focus',BORDER)],lightcolor=[('focus',BORDER),('!focus',BORDER)],darkcolor=[('focus',BORDER),('!focus',BORDER)])

        self.process_inset=tk.PhotoImage(master=root,width=8,height=1)

        style.element_create('Process.leading','image',self.process_inset)

        style.layout('Process.Treeview.Item',[('Treeitem.padding',{'sticky':'nswe','children':[

            ('Process.leading',{'side':'left','sticky':''}),

            ('Treeitem.image',{'side':'left','sticky':''}),('Treeitem.text',{'side':'left','sticky':''})]})])

        style.configure('Treeview.Heading',background='#242321',foreground=MUTED,font=(_ui_tr('맑은 고딕'),9,'bold'),relief='flat',bordercolor=BORDER)

        style.map('Treeview.Heading',background=[('active','#303030')],foreground=[('active',FG)])

        style.configure('Horizontal.TScale',background=CARD,troughcolor=BORDER)

        style.configure('TScrollbar',background='#242424',troughcolor='#111110',arrowcolor=MUTED,bordercolor=BORDER,lightcolor=BORDER,darkcolor=BORDER,gripcount=0,relief='flat')

        style.map('TScrollbar',background=[('disabled','#202020'),('pressed','#484848'),('active','#363636')],arrowcolor=[('disabled',DISABLED),('active',FG)])
        scale_styles(root,style,('.', 'Accent.Footer.TButton', 'Accent.TButton', 'Filter.TButton', 'Horizontal.TScale', 'Limiter.TCombobox', 'Muted.TLabel', 'Process.Treeview', 'Selected.Filter.TButton', 'Selected.TButton', 'Studio.TEntry', 'TButton', 'TCheckbutton', 'TCombobox', 'TEntry', 'TFrame', 'TLabel', 'TRadiobutton', 'TScrollbar', 'Treeview.Heading'))

        root.option_add('*TCombobox*Listbox.background','#111110'); root.option_add('*TCombobox*Listbox.foreground',FG)

        root.option_add('*TCombobox*Listbox.selectBackground','#4a3b1c')

        config_path=Path(sys.executable).parent/'default_config.json' if getattr(sys,'frozen',False) else Path(__file__).with_name('default_config.json')

        self.config_error=None

        try:

            self.controls=Controls(**json.loads(config_path.read_text(encoding='utf-8'))) if config_path.exists() else Controls()

            if (self.controls.mode not in ('normal','pure') or not 0<=self.controls.strength<=1 or self.controls.limiter not in ('soft','hard')

                or type(self.controls.gain) not in (int,float) or not 0<=self.controls.gain<=1.5):

                raise ValueError(_ui_tr('PC 기본 설정 오류'))

        except Exception as exc:

            self.controls=Controls(); self.config_error=str(exc)

        app_directory=Path(sys.executable).resolve().parent if getattr(sys,'frozen',False) else Path(__file__).resolve().parent

        preference_path=app_directory/'preferences.json'

        if '--preferences-test-path' in sys.argv:

            preference_path=Path(sys.argv[sys.argv.index('--preferences-test-path')+1])

        self.preference_store=PreferenceStore(preference_path)

        # Portable settings are authoritative. Missing local settings use the

        # current defaults instead of silently importing an older AppData copy.

        prefs=self.preference_store.load()

        if prefs['remember_last']:

            try: self.controls=Controls(**prefs['controls'])

            except (TypeError,ValueError): pass

        self.controls=replace(self.controls,mode='normal')

        saved_width=max(860,min(10000,int(prefs.get('window_width',px(root,860)))))

        saved_height=max(860,min(10000,int(prefs.get('window_height',px(root,1000)))))

        fit_window(root,saved_width,saved_height,min_width=px(root,860),min_height=px(root,860))

        self._preferences_ready=False; self._preferences_job=None

        self._process_refresh_running=False; self._process_snapshot=[]; self._process_sampler=ProcessSampler()

        self._next_process_refresh=0.; self._auto_start_attempted=False

        preset_path=Path(os.environ.get('LOCALAPPDATA',str(Path.home())))/'DS5Light'/'presets.json'

        if '--preset-test-path' in sys.argv: preset_path=Path(sys.argv[sys.argv.index('--preset-test-path')+1])

        self.store=PresetStore(preset_path); self.desired_game=prefs['game_exe'] if prefs['remember_last'] else ''; self.game_map={}; self.game_names={}

        self.device_error=None

        try: self.ds=devices()

        except Exception as exc: self.ds=[]; self.device_error=str(exc)

        self.inputs=[AUTO]+[d['name'] for d in self.ds if d.get('isLoopbackDevice') and not any(name in d['name'].lower() for name in ('dualsense','studio xinput experiment'))]

        self.outputs=[AUTO]+[d['name'] for d in self.ds if d['maxOutputChannels']>=4 and not d.get('isLoopbackDevice')]

        c=self.controls

        restore=prefs if prefs['remember_last'] else {}

        scope=restore.get('scope','device')

        channel_value=0 if restore.get('channel_auto',True) else restore.get('channels',0)

        self.scope=tk.StringVar(value=scope); self.channel=tk.StringVar(value=next((k for k,v in CHANNELS.items() if v==channel_value),list(CHANNELS)[0]))

        source=display_device(restore.get('input','')) if restore.get('input') else AUTO

        destination=display_device(restore.get('output','')) if restore.get('output') else AUTO

        self.source=tk.StringVar(value=source if source in self.inputs else AUTO); self.destination=tk.StringVar(value=destination if destination in self.outputs else AUTO)

        self.mode=tk.StringVar(value=c.mode); self.filter_on=tk.BooleanVar(value=not c.bypass)

        self.strength=tk.DoubleVar(value=c.strength*100); self.bg=tk.BooleanVar(value=c.background); self.transient=tk.BooleanVar(value=c.transient)

        self.gain=tk.DoubleVar(value=c.gain*100); self.impact=tk.DoubleVar(value=c.impact*100)

        self.auto_apply_game=tk.BooleanVar(value=False); self.binding_text=tk.StringVar(value='')

        self.center=tk.BooleanVar(value=c.center); self.rear=tk.BooleanVar(value=c.rear); self.lfe=tk.BooleanVar(value=c.lfe)

        self.limiter=tk.StringVar(value=next(k for k,v in LIMITERS.items() if v==c.limiter))

        self.remember_last=tk.BooleanVar(value=prefs['remember_last']); self.auto_start=tk.BooleanVar(value=prefs['auto_start'])

        self.mute_binding=validate_binding(prefs['mute_shortcut'])

        self.mute_enabled=tk.BooleanVar(value=self.mute_binding['enabled'])

        self.mute_key_label=tk.StringVar(value=binding_label(self.mute_binding))

        self.process_sort=tk.StringVar(value=restore.get('process_sort','audio'))

        self.process_sort_label=tk.StringVar(value=next((k for k,v in PROCESS_SORTS.items() if v==self.process_sort.get()),_ui_tr('오디오 출력')))

        self.slot_name=tk.StringVar(value=_ui_tr('게임 설정')); self.notice=tk.StringVar(value='')

        self.status=tk.StringVar(value=_ui_tr('정지'))

        # Organized two-tab layout: process capture, haptics, then device and launch settings.

        outer=tk.Frame(root,bg=BG); outer.pack(fill='both',expand=True,padx=PAGE_MARGIN_X,pady=(PAGE_MARGIN_Y,PAGE_MARGIN_X)); outer.columnconfigure(0,weight=1); outer.rowconfigure(1,weight=1)

        self.header=head=tk.Frame(outer,bg=BG)

        head.grid(row=0,column=0,sticky='ew',pady=(0,SPACE_LG))

        head.columnconfigure(0,weight=1);head.rowconfigure(0,weight=1)

        brand=tk.Frame(head,bg=BG);brand.grid(row=0,column=0,sticky='w',padx=(15,0))

        root.tk.call('lappend','auto_path',str(Path(__file__).resolve().parent/'vendor'/'tksvg0.16'))

        root.tk.call('package','require','tksvg','0.16')

        self.battery=BatteryMonitor()

        self.controller_presence=ControllerPresence()

        self.idle_presence=IdleControllerPresence()

        self._reconnect_wait_engine=None;self._reconnect_wait_since=None

        self.run_intent=RunIntent();self.profile_watch=ProfileWatch();self.profile_watch_enabled='--smoke-test' not in sys.argv

        self.brand_wordmark=BatteryLogo(brand,Path(__file__).resolve().parent/'assets'/'ds5-light-logo.svg',BG)

        self.brand_wordmark.pack(side='left')

        self.header_controls=controls=tk.Frame(head,bg=BG);controls.grid(row=0,column=1,sticky='e')

        gain_frame=tk.Frame(controls,bg=BG);gain_frame.grid(row=0,column=0,padx=(SPACE_LG,SPACE_LG))

        self.gain_frame=gain_frame

        gain_heading=tk.Frame(gain_frame,bg=BG);gain_heading.pack(fill='x')

        tk.Label(gain_heading,text=_ui_tr('오디오햅틱 세기'),bg=BG,fg=MUTED,font=(_ui_tr('맑은 고딕'),9,'bold'),padx=0,pady=0,borderwidth=0,anchor='w').pack(side='left')

        self.filter_help_icon(gain_heading,_ui_tr('앱이 오디오를 전송할 때만 적용되며 프로필은 바꾸지 않습니다. 반응을 먼저 맞춘 뒤 세기를 조절하세요. 기본 100%. Studio 오디오햅틱 세기와 함께 높이면 포화될 수 있습니다.'),background=BG).pack(side='left',padx=(5,0))

        self.gain_value=tk.Label(gain_heading,text='100%',bg=BG,fg=ACCENT,font=(_ui_tr('맑은 고딕'),9,'bold'),padx=0,pady=0,borderwidth=0,anchor='e');self.gain_value.pack(side='right')

        self.gain_slider=HapticSlider(gain_frame,self.gain,self.update_controls,maximum=150,reference=100,background=BG,width=200)

        self.gain_slider.pack(fill='x')

        gain_heading.pack_configure(padx=self.gain_slider.pad)

        self.language_choice=ttk.Combobox(controls,values=['한국어','English'],state='readonly',width=10)

        self.language_choice.set('한국어' if LANGUAGE=='ko' else 'English')

        self.language_choice.grid(row=0,column=1,padx=(SPACE_LG,0))

        self.language_choice.bind('<<ComboboxSelected>>',self.change_language)



        tab_area=tk.Frame(outer,bg=BG); tab_area.grid(row=1,column=0,sticky='nsew'); tab_area.columnconfigure(0,weight=1); tab_area.rowconfigure(1,weight=1)

        self.page_outline=PageOutline(tab_area); self.page_outline.grid(row=1,column=0,sticky='nsew')

        self.pages=self.page_outline.content

        self.game_page=tk.Frame(self.pages,bg=BG); self.device_page=tk.Frame(self.pages,bg=BG)

        self.game_page.grid(row=0,column=0,sticky='nsew'); self.device_page.grid(row=0,column=0,sticky='nsew')

        self.game_page.configure(height=620); self.game_page.grid_propagate(False)

        self.device_page.configure(height=620); self.device_page.grid_propagate(False)

        self.studio_page=tk.Frame(self.pages,bg=BG);self.studio_page.grid(row=0,column=0,sticky='nsew')

        self.studio_settings=StudioSettings(self,self.studio_page)

        self.tabs=TabStrip(tab_area,[_ui_tr('오디오햅틱'),_ui_tr('설정·진단'),_ui_tr('Studio설정')],self.select_tab); self.tabs.grid(row=0,column=0,sticky='ew',pady=(0,16))

        self.pages.rowconfigure(0,weight=1); self.pages.columnconfigure(0,weight=1)

        self.select_tab(0)

        self.game_page.columnconfigure(0,weight=1); self.game_page.rowconfigure(0,weight=1)



        capture_box=self.card(self.game_page); capture_box.grid(row=0,column=0,sticky='nsew',pady=(0,SPACE_LG))

        capture=capture_box.content; capture.columnconfigure(0,weight=1); capture.rowconfigure(2,weight=1)

        caphead=ttk.Frame(capture); caphead.grid(row=0,column=0,sticky='ew')

        self.section_title(caphead,_ui_tr('캡쳐 모드')).pack(side='left')

        self.scope_buttons=[]

        for text,value in [(_ui_tr('장치 전체'),'device'),(_ui_tr('선택한 게임만'),'process')]:

            b=RadioChoice(caphead,text=text,value=value,variable=self.scope,command=self.scope_changed,

                          background=CARD,foreground=FG,muted=MUTED,accent=ACCENT,disabled=DISABLED)

            b.pack(side='right',padx=(SPACE_LG,0)); self.scope_buttons.append(b)

        proc_head=ttk.Frame(capture); proc_head.grid(row=1,column=0,sticky='ew',pady=(SPACE,4))

        ttk.Label(proc_head,text=_ui_tr('실행 중인 프로세스'),style='Muted.TLabel').pack(side='left')

        self.refresh_button=ttk.Button(proc_head,text=_ui_tr('↻ 새로 고침'),command=self.refresh_games); self.refresh_button.pack(side='right')

        self.process_sort_box=ttk.Combobox(proc_head,textvariable=self.process_sort_label,values=list(PROCESS_SORTS),state='readonly',width=13,

                                        postcommand=self.scroll_processes_to_top)

        self.process_sort_box.pack(side='right',padx=(0,8)); self.process_sort_box.bind('<<ComboboxSelected>>',self.process_sort_changed)

        tablewrap=tk.Frame(capture,bg='#111110',highlightbackground=BORDER,highlightcolor=BORDER,highlightthickness=1,takefocus=0)

        tablewrap.grid(row=2,column=0,sticky='nsew')

        self.process_table=ttk.Treeview(tablewrap,columns=('audio','cpu','started'),show='tree headings',height=5,selectmode='browse',style='Process.Treeview')

        self.process_table.tag_configure('process',font=(_ui_tr('맑은 고딕'),10,'bold'))

        self.process_dots=[circle_image(root,color) for color in ('#e1b65d','#6cbfb0','#a49be2','#e59177','#9fc47b','#da8fc1','#82b5df','#d7c078')]

        self.process_dot_colors={}; self._dot_random=random.Random()

        self.process_table.heading('#0',text=_ui_tr('프로세스')); self.process_table.heading('cpu',text=_ui_tr('CPU 사용률')); self.process_table.heading('started',text=_ui_tr('실행 시작'))

        self.process_table.heading('audio',text=_ui_tr('오디오 출력'))

        self.process_table.heading('cpu',text='CPU')

        self.process_table.column('#0',width=420,anchor='w',stretch=True,minwidth=180)

        metric_font=tkfont.Font(family=_ui_tr('맑은 고딕'),size=10,weight='bold')

        metric_width=max(100,*(metric_font.measure(label)+24 for label in (_ui_tr('오디오 출력'),'CPU',_ui_tr('실행 시작'))))

        for column in ('audio','cpu','started'):

            self.process_table.column(column,width=metric_width,minwidth=metric_width,anchor='center',stretch=False)

            self.process_table.heading(column,anchor='center')

        scroll=ttk.Scrollbar(tablewrap,orient='vertical',command=self.process_table.yview); self.process_table.configure(yscrollcommand=scroll.set)

        self.process_table.pack(side='left',fill='both',expand=True); scroll.pack(side='right',fill='y')

        self.process_table.bind('<<TreeviewSelect>>',self.process_selected)

        self.global_capture_overlay=GlobalCaptureOverlay(tablewrap,text=_ui_tr('전역 캡쳐'))
        FieldTip(self.global_capture_overlay.label,lambda:_ui_tr('오디오햅틱을 사용하려면 Studio 프로필의 오디오햅틱 모드를 Mix 또는 Replace로 변경하세요.') if self.studio.auto_haptics_mode==0 else '')

        self.game=ttk.Combobox(capture,state='disabled'); self.game.bind('<<ComboboxSelected>>',self.game_selected)

        self.notice_label=ttk.Label(capture,textvariable=self.notice,style='Muted.TLabel',font=(_ui_tr('맑은 고딕'),9)); self.notice_label.grid(row=3,column=0,sticky='ew',pady=(4,0))

        self.notice.trace_add('write',lambda *_:self._update_notice_layout()); self._update_notice_layout()

        presetbar=ttk.Frame(capture); presetbar.grid(row=4,column=0,sticky='ew',pady=(CARD_INSET_Y,0))

        ttk.Label(presetbar,text=_ui_tr('게임 프리셋'),style='Muted.TLabel').pack(side='left',padx=(0,SPACE))

        self.slot=ttk.Combobox(presetbar,state='readonly',width=14); self.slot.pack(side='left',fill='x',expand=True); self.slot.bind('<<ComboboxSelected>>',self.slot_selected)

        self.load_button=ttk.Button(presetbar,text=_ui_tr('불러오기'),command=self.load_slot); self.load_button.pack(side='left',padx=SPACE)

        self.game_save_button=ttk.Button(presetbar,text=_ui_tr('저장'),command=self.save_prompt);self.game_save_button.pack(side='left')

        HoverHint(self.game_save_button,_ui_tr('현재 DS5Light 설정을 이 PC의 게임 프리셋에 저장합니다.'))

        bindingbar=presetbar

        self.binding_check=CircleCheck(bindingbar,text=_ui_tr('이 게임에 자동 적용'),variable=self.auto_apply_game,command=self._update_binding_display,

                                      background=CARD,foreground=FG,muted=BORDER,accent=ACCENT,disabled=DISABLED)

        self.binding_check.pack(side='left',padx=(SPACE,0))



        self.studio_card=self.card(self.game_page);self.studio_card.grid(row=1,column=0,sticky='ew',pady=(0,SPACE_LG))

        self.studio=StudioPanel(self,self.studio_card.content)

        cards=tk.Frame(self.game_page,bg=BG,height=px(root,256)); cards.grid(row=2,column=0,sticky='ew'); cards.grid_propagate(False); cards.columnconfigure(0,weight=1,uniform='cards'); cards.columnconfigure(1,weight=1,uniform='cards'); cards.rowconfigure(0,weight=1)
        self._dpi_cards=cards;watch_scale(cards,self._scale_cards)

        left_box=self.card(cards); left_box.grid(row=0,column=0,sticky='nsew',padx=(0,SPACE_LG//2)); left=left_box.content

        right_box=self.card(cards); right_box.grid(row=0,column=1,sticky='nsew',padx=(SPACE_LG//2,0)); right=right_box.content

        channel_head=ttk.Frame(left);channel_head.pack(fill='x')

        self.section_title(channel_head,_ui_tr('채널 구성')).pack(side='left')

        self.channel_note=ttk.Label(channel_head,style='Muted.TLabel',font=(_ui_tr('맑은 고딕'),8),width=1,anchor='e');self.channel_note.pack(side='right',fill='x',expand=True,padx=(8,0))

        self.channel_choice=ttk.Combobox(left,values=list(CHANNELS),textvariable=self.channel,state='readonly')

        self.channel_choice.pack(fill='x',pady=(SPACE,4)); self.channel_choice.bind('<<ComboboxSelected>>',lambda e:self.update_controls())

        self.channel_auto_status=tk.Frame(left,bg=CARD)

        self.channel_status_label=tk.Label(self.channel_auto_status,text=_ui_tr('자동 적용 중..'),bg=CARD,fg=ACCENT,

                 font=(_ui_tr('맑은 고딕'),10),borderwidth=0,highlightthickness=0,

                 padx=0,pady=0)

        self.channel_status_label.place(relx=.5,rely=.5,anchor='center')

        self.channel_details=ttk.Frame(left)

        self.channel_labels=[];self.mix_switches=[]

        for label,var in [(_ui_tr('센터'),self.center),(_ui_tr('후방 L / R'),self.rear),(_ui_tr('LFE · 저음'),self.lfe)]:

            row=ttk.Frame(self.channel_details);row.pack(fill='x')

            lab=ttk.Label(row,text=label);lab.pack(side='left');self.channel_labels.append(lab)

            sw=Switch(row,var,self.update_controls);sw.pack(side='right');self.mix_switches.append(sw)

        limit_row=ttk.Frame(self.channel_details);limit_row.pack(fill='x',pady=(SPACE,0))

        limit_row.columnconfigure(1,weight=1)

        self.limit_label=ttk.Label(limit_row,text=_ui_tr('합산 제한'),style='Muted.TLabel');self.limit_label.grid(row=0,column=0,sticky='w',padx=(0,SPACE))

        self.limiter_box=ttk.Combobox(limit_row,values=list(LIMITERS),textvariable=self.limiter,state='readonly',width=16,style='Limiter.TCombobox')

        self.limiter_box.grid(row=0,column=1,sticky='ew');self.limiter_box.bind('<<ComboboxSelected>>',lambda e:self.update_controls())

        self.mix_note=ttk.Label(left,style='Muted.TLabel',wraplength=390)

        fh=ttk.Frame(right); fh.pack(fill='x')

        self.section_title(fh,_ui_tr('PC 억제 필터')).pack(side='left')

        self.filter_switch=Switch(fh,self.filter_on,self.update_controls); self.filter_switch.pack(side='right')

        self.filter_badge=ttk.Label(fh); self.filter_badge.pack(side='right',padx=7)

        self.filter_widgets=[]; self.style_buttons=[]

        sr=ttk.Frame(right); sr.pack(fill='x',pady=(SPACE,4))

        for i,(label,v) in enumerate([(_ui_tr('디테일'),30),(_ui_tr('균형'),55),(_ui_tr('억제'),80)]):

            sr.columnconfigure(i,weight=1,uniform='filter_presets')

            b=ttk.Button(sr,text=label,style='Filter.TButton',command=lambda value=v:self.set_strength(value))

            b.grid(row=0,column=i,sticky='ew',padx=(0,SPACE) if i<2 else 0)

            self.filter_widgets.append(b); self.style_buttons.append((b,v))

        for label,var,key in [(_ui_tr('배경 억제량'),self.strength,'strength'),(_ui_tr('충격 보존'),self.impact,'impact')]:

            row=ttk.Frame(right); row.pack(fill='x',pady=(4,0))

            ttk.Label(row,text=label,style='Muted.TLabel').pack(side='left')

            description=(_ui_tr('높일수록 배경음의 지속적인 진동을 줄입니다. 너무 높이면 약한 효과음도 줄어들 수 있습니다.') if key=='strength'

                         else _ui_tr('높일수록 타격·충격의 순간적인 진동을 더 살립니다. 배경 대역 억제와 변화량 보호가 켜져 있을 때 적용됩니다.'))

            self.filter_help_icon(row,description).pack(side='left',padx=(5,0))

            value=ttk.Label(row);value.pack(side='right')

            slider=HapticSlider(right,var,self.update_controls);slider.pack(fill='x',pady=(0,4))

            if key=='strength':self.scale=slider;self.value_label=value

            else:self.impact_slider=slider;self.impact_label=value

            self.filter_widgets.append(slider)

        self.advanced=ttk.Frame(right);self.advanced.pack(fill='x',pady=(4,0));self.advanced_open=True

        self.advanced_checks=[]

        for text,var in [(_ui_tr('배경 대역 억제'),self.bg),(_ui_tr('변화량 보호'),self.transient)]:

            group=ttk.Frame(self.advanced);group.pack(side='left',padx=(0,SPACE))

            check=CircleCheck(group,text=text,variable=var,command=self.update_controls,

                              background=CARD,foreground=FG,muted=BORDER,accent=ACCENT,disabled=DISABLED)

            check.pack(side='left');self.filter_widgets.append(check);self.advanced_checks.append(check)

            description=(_ui_tr('계속 이어지는 소리의 진동을 줄입니다. 배경음이 너무 많이 느껴질 때 켜세요.') if var is self.bg

                         else _ui_tr('배경음을 줄이는 동안, 타격처럼 갑자기 커지는 소리의 반응을 살립니다.'))

            self.filter_help_icon(group,description).pack(side='left',padx=(4,0))

        self.filter_note=ttk.Label(right,style='Muted.TLabel',wraplength=390)



        self.device_page.columnconfigure(0,weight=1);self.device_page.rowconfigure(3,weight=1)

        devices_box=self.card(self.device_page);devices_box.grid(row=0,column=0,sticky='ew',pady=(0,SPACE_LG));devices_card=devices_box.content

        ttk.Label(devices_card,text=_ui_tr('장치 설정'),font=(_ui_tr('맑은 고딕'),12,'bold')).pack(anchor='w',pady=(0,SPACE))

        device_fields=ttk.Frame(devices_card);device_fields.pack(fill='x')

        device_fields.columnconfigure(0,weight=1,uniform='device_fields');device_fields.columnconfigure(1,weight=1,uniform='device_fields')

        self.conn_widgets={};self.device_refresh_buttons=[]

        for column,(label,var,values,key) in enumerate([(_ui_tr('입력 장치'),self.source,self.inputs,'source'),(_ui_tr('출력 장치 · DualSense'),self.destination,self.outputs,'output')]):

            cell=ttk.Frame(device_fields);cell.grid(row=0,column=column,sticky='ew',padx=(0,SPACE_LG//2) if column==0 else (SPACE_LG//2,0))

            ttk.Label(cell,text=label,style='Muted.TLabel').pack(anchor='w',pady=(0,4))

            row=ttk.Frame(cell);row.pack(fill='x')

            box=ttk.Combobox(row,values=values,textvariable=var,state='readonly',width=16)

            box.pack(side='left',fill='x',expand=True);box.bind('<<ComboboxSelected>>',lambda e:self.update_controls());self.conn_widgets[key]=box

            HoverHint(box,_ui_tr('사용할 오디오 장치를 자동으로 선택합니다.') if LANGUAGE=='ko' else 'Automatically select the audio device to use.')

            button=ttk.Button(row,text=_ui_tr('새로 고침'),command=self.refresh_devices,style='Footer.TButton')

            button.pack(side='left',padx=(SPACE,0));self.device_refresh_buttons.append(button)

        self.conn_widgets['channel']=self.channel_choice

        self.run_card=self.card(self.device_page);self.run_card.grid(row=1,column=0,sticky='ew',pady=(0,SPACE_LG));run_card=self.run_card.content

        ttk.Label(run_card,text=_ui_tr('실행 옵션'),font=(_ui_tr('맑은 고딕'),12,'bold')).pack(side='left',padx=(0,SPACE_LG*2))

        self.launch_checks=[]

        for text,var,command in [(_ui_tr('마지막 설정 복원'),self.remember_last,self.schedule_preferences_save),(_ui_tr('실행 시 자동 시작'),self.auto_start,self.auto_start_changed)]:

            check=CircleCheck(run_card,text=text,variable=var,command=command,

                              background=CARD,foreground=FG,muted=BORDER,accent=ACCENT,disabled=DISABLED)

            check.pack(side='left',padx=(0,SPACE_LG*2));self.launch_checks.append(check)

        self.mute_card=self.card(self.device_page);self.mute_card.grid(row=2,column=0,sticky='ew',pady=(0,SPACE_LG));mute_card=self.mute_card.content

        mute_card.columnconfigure(2,weight=1)

        ttk.Label(mute_card,text=_ui_tr('마이크 버튼 키보드매핑'),font=(_ui_tr('맑은 고딕'),12,'bold')).grid(row=0,column=0,sticky='w',padx=(0,SPACE_LG*2))

        self.mute_check=CircleCheck(mute_card,text=_ui_tr('사용'),variable=self.mute_enabled,command=self.mute_shortcut_changed,

                                   background=CARD,foreground=FG,muted=BORDER,accent=ACCENT,disabled=DISABLED)

        self.mute_check.grid(row=0,column=1,sticky='w',padx=(0,SPACE_LG))

        ttk.Label(mute_card,textvariable=self.mute_key_label,anchor='w',width=1).grid(row=0,column=2,sticky='ew',padx=(0,SPACE_LG))

        self.mute_configure=ttk.Button(mute_card,text=_ui_tr('키 지정'),command=self.configure_mute_shortcut,style='Footer.TButton')

        self.mute_configure.grid(row=0,column=3,sticky='e',padx=(0,SPACE_LG))

        self.mute_state=tk.StringVar(value=_ui_tr('꺼짐'))

        FieldTip(self.mute_configure,self.mute_state.get)

        diagnostics_box=self.card(self.device_page);diagnostics_box.grid(row=3,column=0,sticky='nsew');diagnostics_card=diagnostics_box.content

        diagnostic_header=ttk.Frame(diagnostics_card);diagnostic_header.pack(fill='x',pady=(0,SPACE))
        ttk.Label(diagnostic_header,text=_ui_tr('오디오 진단'),font=(_ui_tr('맑은 고딕'),12,'bold')).pack(side='left')
        self.device_diagnostics_button=ttk.Button(diagnostic_header,text=_ui_tr('장치 진단 시험'),command=lambda:open_diagnostics(self))
        self.device_diagnostics_button.pack(side='right')
        FieldTip(self.device_diagnostics_button,lambda:getattr(self,'device_diagnostics_hint',_ui_tr('지원 펌웨어에서 사용할 수 있습니다.')))

        diagnostic_content=tk.Frame(diagnostics_card,bg=CARD);diagnostic_content.pack(fill='both',expand=True)

        diagnostic_content.columnconfigure(0,weight=1);diagnostic_content.rowconfigure(0,weight=1)

        self._diagnostic_font=tkfont.Font(family=_ui_tr('맑은 고딕'),size=10)

        self._diagnostic_images=[tk.PhotoImage(master=root,file=str(Path(__file__).resolve().parent/'assets'/f'diagnostic-bg-{size}.png')) for size in (120,160,240,320)]

        self.diagnostics_body=DiagnosticCanvas(diagnostic_content,font=self._diagnostic_font,

                                              foreground=MUTED,background=CARD,images=self._diagnostic_images)

        self.diagnostics_body.set_text(_ui_tr('오디오 엔진이 정지 상태입니다.'))

        diagnostic_scroll=AutoScrollbar(diagnostic_content,orient='vertical',command=self.diagnostics_body.yview)

        diagnostic_scroll.grid(row=0,column=1,sticky='ns',padx=(SPACE,0));diagnostic_scroll.grid_remove()

        self.diagnostics_body.set_scrollcommand(diagnostic_scroll.set)

        self.diagnostics_body.grid(row=0,column=0,sticky='nsew')

        self.diagnostics_body.bind('<Configure>',self._schedule_diagnostic_spacing,add='+')

        self.connection=self.device_page



        self.footer=self.card(outer); self.footer.grid(row=2,column=0,sticky='ew',pady=(16,0))

        footer=self.footer.content

        footer.columnconfigure(0,weight=1)

        footer.rowconfigure(0,weight=1,uniform='footer'); footer.rowconfigure(1,weight=1,uniform='footer')

        self._status_font=tkfont.Font(family=_ui_tr('맑은 고딕'),size=11,weight='bold')

        self._status_small_font=tkfont.Font(family=_ui_tr('맑은 고딕'),size=9)

        self._status_display=tk.StringVar(value=self.status.get())

        self.status_label=ttk.Label(footer,textvariable=self._status_display,style='Muted.TLabel',width=1,anchor='w',font=self._status_font)

        self.status_label.grid(row=0,column=0,sticky='ew',padx=(0,SPACE_LG))

        self.status_label.bind('<Configure>',self._fit_status_text)

        HoverHint(self.status_label,lambda:self.status.get())

        self.status.trace_add('write',self._fit_status_text)

        footer_meta=ttk.Frame(footer); footer_meta.grid(row=1,column=0,sticky='ew')

        self.connection_summary=tk.Label(footer_meta,bg=CARD,fg=MUTED,width=1,anchor='w',font=(_ui_tr('맑은 고딕'),10)); self.connection_summary.pack(side='left',fill='x',expand=True)

        buttons=ttk.Frame(footer); buttons.grid(row=0,column=1,rowspan=2,sticky='e')

        buttons.columnconfigure(0,weight=1,uniform='transport');buttons.columnconfigure(1,weight=1,uniform='transport')

        self.stop_button=ttk.Button(buttons,text=_ui_tr('정지'),command=self.stop,style='Footer.TButton',width=12,state='disabled'); self.stop_button.grid(row=0,column=0,sticky='ew',padx=(0,4))

        self.start_button=ttk.Button(buttons,text=_ui_tr('▶  시작'),command=self.start,style='Accent.Footer.TButton',width=12); self.start_button.grid(row=0,column=1,sticky='ew',padx=(4,0))

        self.studio_power=StudioPower(self)

        # An unpainted hit area in the bottom-left outer margin. No focus,

        # hover handlers, tooltip, outline or special pointer cursor.

        self.power_hitbox=tk.Frame(root,bg=BG,width=24,height=16,bd=0,highlightthickness=0,takefocus=0,cursor='')

        self.power_hitbox.place(x=0,rely=1,anchor='sw',width=24,height=16)

        self.power_hitbox.bind('<Button-1>',self.studio_power.click)

        self.refresh_slots(); self.render()

        for variable in (self.scope,self.channel,self.source,self.destination,self.mode,self.filter_on,self.strength,self.gain,self.impact,self.bg,self.transient,self.center,self.rear,self.lfe,self.limiter,self.remember_last,self.auto_start):

            variable.trace_add('write',self.schedule_preferences_save)

        self._preferences_ready=True

        self._update_mute_state()

        root.bind('<Configure>',self._root_configured,add='+')

        if self.store.error: root.after(100,lambda:messagebox.showerror(_ui_tr('프리셋 파일 오류'),str(self.store.path)+'\n'+tr(self.store.error)+_ui_tr('\n기존 파일을 보존하기 위해 저장이 차단됩니다.'),parent=root))

        if self.preference_store.error:

            root.after(150,lambda:messagebox.showwarning(_ui_tr('설정 복구'),tr(self.preference_store.error),parent=root))

        if self.config_error:

            root.after(200,lambda:messagebox.showwarning(_ui_tr('기본 설정 오류'),tr(self.config_error)+_ui_tr('\n안전한 기본값으로 실행합니다.'),parent=root))

        if self.device_error: self.status.set(_ui_tr('장치 목록 조회 실패: ')+tr(self.device_error))

        root.after(150,lambda:self.refresh_games(initial=True)); root.after(1000,self.tick)

        if '--smoke-test' not in sys.argv:self.studio.schedule_initial_read()

    def mute_shortcut_changed(self):

        self.mute_binding=validate_binding(dict(self.mute_binding,enabled=bool(self.mute_enabled.get())))

        self._update_mute_state()

        self.schedule_preferences_save()

    def _update_mute_state(self):

        path=self.studio.binding.snapshot().hid_path
        path_text=path.decode('ascii',errors='ignore') if isinstance(path,bytes) else str(path or '')
        xbox=getattr(self.studio,'xbox_hid_path',None)==path and path is not None
        xbox=xbox or 'vid_1209&pid_0001' in path_text.lower()
        observed_path, macro = getattr(self, '_mute_macro_policy', (None, False))
        macro_blocked = bool(macro and path and observed_path == path and self.studio.controller_connected is not False)
        xbox_blocked = xbox and self.studio.controller_connected is not False
        blocked = xbox_blocked or macro_blocked
        if blocked != getattr(self, '_mute_shortcut_blocked', None):
            self._mute_shortcut_blocked = blocked
            self.mute_check.set_enabled(not blocked)
            self.mute_configure.configure(state='disabled' if blocked else 'normal')
        binding=dict(self.mute_binding,enabled=False) if blocked else self.mute_binding
        if binding!=getattr(self,'_mute_effective_binding',None):
            self.mute_shortcut.configure(binding)
            self._mute_effective_binding=dict(binding)
        if macro_blocked:
            text = ui_text('현재 Studio 프로필의 마이크 버튼 매크로가 우선합니다.',
                           'The active Studio profile’s microphone-button macro takes priority.')
        elif xbox_blocked:
            text = tr(_ui_tr('XBOX 모드에서는 마이크 버튼 키보드매핑을 사용할 수 없습니다.'))
        else:
            text = tr(self.mute_shortcut.status())

        if self.mute_state.get()!=text:self.mute_state.set(text)

    def configure_mute_shortcut(self):

        if self._shortcut_dialog is not None and self._shortcut_dialog.winfo_exists():

            self._shortcut_dialog.lift();return

        dialog=self._shortcut_dialog=tk.Toplevel(self.root)

        dialog.title(_ui_tr('마이크 버튼 키보드매핑'));dialog.configure(bg=BG)

        dialog.transient(self.root);dialog.resizable(False,False)

        dialog.bind('<Map>',lambda event:dialog.after_idle(lambda:apply_windows_titlebar_theme(dialog)) if event.widget is dialog else None,add='+')

        content_box=self.card(dialog);content_box.pack(fill='both',expand=True,padx=PAGE_MARGIN_X,pady=PAGE_MARGIN_Y);content=content_box.content

        ttk.Label(content,text=_ui_tr('단축키'),font=(_ui_tr('맑은 고딕'),11,'bold')).pack(anchor='w',pady=(0,SPACE_LG))

        modifier_row=ttk.Frame(content);modifier_row.pack(fill='x',pady=(0,SPACE_LG))

        variables={key:tk.BooleanVar(value=key in self.mute_binding['modifiers']) for key in MODIFIERS}

        for key,var in variables.items():

            check=CircleCheck(modifier_row,text=key,variable=var,command=lambda:None,

                              background=CARD,foreground=FG,muted=BORDER,accent=ACCENT,disabled=DISABLED)

            check.pack(side='left',padx=(0,SPACE_LG))

        selected=tk.StringVar(value=self.mute_binding['key'])

        choice=ttk.Combobox(content,textvariable=selected,values=list(KEYS),state='readonly',width=24,height=12)

        choice.pack(fill='x',pady=(0,SPACE_LG))

        buttons=ttk.Frame(content);buttons.pack(anchor='center')

        buttons.columnconfigure(0,weight=1,uniform='shortcut_actions')

        buttons.columnconfigure(1,weight=1,uniform='shortcut_actions')

        def dismiss():

            dialog.grab_release();dialog.destroy();self._shortcut_dialog=None

        def apply():

            try:

                candidate=validate_binding(dict(enabled=self.mute_enabled.get(),key=selected.get(),

                                                modifiers=[key for key,var in variables.items() if var.get()]))

            except ValueError as exc:

                messagebox.showerror(_ui_tr('단축키 설정 오류'),tr(str(exc)),parent=dialog);return

            self.mute_binding=candidate;self.mute_key_label.set(binding_label(candidate))

            self.mute_shortcut_changed();dismiss()

        ttk.Button(buttons,text=_ui_tr('취소'),command=dismiss,style='Footer.TButton',width=12).grid(row=0,column=0,sticky='ew',padx=(0,SPACE//2))

        ttk.Button(buttons,text=_ui_tr('적용'),command=apply,style='Accent.Footer.TButton',width=12).grid(row=0,column=1,sticky='ew',padx=(SPACE//2,0))

        dialog.protocol('WM_DELETE_WINDOW',dismiss);dialog.bind('<Escape>',lambda _e:dismiss())

        dialog.update_idletasks()

        x=self.root.winfo_rootx()+max(0,(self.root.winfo_width()-dialog.winfo_reqwidth())//2)

        y=self.root.winfo_rooty()+max(0,(self.root.winfo_height()-dialog.winfo_reqheight())//2)

        dialog.geometry(f'+{x}+{y}');dialog.grab_set();choice.focus_set()

    def change_language(self,event=None):

        code='ko' if self.language_choice.get()=='한국어' else 'en'

        try:

            save_language(code)

            self.notice.set(_ui_tr('다음 실행부터 한국어로 표시됩니다.') if code=='ko' else 'English will be used next time you open the app.')

        except Exception as exc:

            messagebox.showerror(_ui_tr('저장 실패'),tr(str(exc)),parent=self.root)

    def card(self,parent,inset_y=CARD_INSET_Y):

        return RoundedCard(parent,background=BG,surface=CARD,outline=BORDER,

                           inset_x=CARD_INSET_X,inset_y=inset_y,radius=10)

    def _fit_status_text(self,*_):

        text=self.status.get().replace('\n',' ')

        color=ACCENT if text==_ui_tr('연결된 듀얼센스가 없습니다.') else MUTED

        if str(self.status_label.cget('foreground'))!=color:

            self.status_label.configure(foreground=color)

        width=self.status_label.winfo_width()-4

        if width<=0:return

        font=self._status_small_font if self._status_font.measure(text)>width else self._status_font

        if str(self.status_label.cget('font'))!=str(font):self.status_label.configure(font=font)

        shown=text

        if font.measure(text)>width:

            # Keep the process name and final instructions within the text column.

            def shorten(count):

                left=count//3;right=count-left

                return text[:left]+'…'+(text[-right:] if right else '')

            low,high=0,len(text)

            while low<high:

                count=(low+high+1)//2

                if font.measure(shorten(count))<=width:low=count

                else:high=count-1

            shown=shorten(low) if font.measure('…')<=width else ''

        if self._status_display.get()!=shown:self._status_display.set(shown)

    def _update_notice_layout(self):

        if not hasattr(self,'notice_label') or not self.notice_label.winfo_exists(): return

        if self.notice.get(): self.notice_label.grid()

        else: self.notice_label.grid_remove()

    def select_tab(self,index):

        if getattr(getattr(self,'studio_settings',None),'transfer_locked',False):return

        self.selected_tab=index
        if self.engine: self.engine.diagnostics_enabled=(index==1)

        self.tabs.select(index)

        (self.game_page if index==0 else self.device_page if index==1 else self.studio_page).tkraise()

        if index==2:self.studio_settings.open()

        if index==1 and hasattr(self,'diagnostics_body'):

            self.root.after_idle(self._update_diagnostics)

    def filter_help_icon(self,parent,text,background=CARD):

        icon=tk.Canvas(parent,width=17,height=17,bg=background,highlightthickness=0,bd=0,takefocus=0,cursor='question_arrow')

        icon.create_oval(1.5,1.5,15,15,outline='#716b5d')

        icon.create_text(8.5,8,text='?',fill='#8a8374',font=(_ui_tr('맑은 고딕'),8,'bold'))

        icon._filter_help_hint=HoverHint(icon,text)

        return icon

    def section_title(self,parent,key):

        symbol={_ui_tr('캡쳐 모드'):'camera',_ui_tr('채널 구성'):'channels',_ui_tr('PC 억제 필터'):'filter'}[key]

        return SectionTitle(parent,symbol,tr(key),background=CARD,foreground=FG,accent=ACCENT)

    def _root_configured(self,event):

        if event.widget is self.root and self._preferences_ready: self.schedule_preferences_save()

    def capture_channels(self):

        if self.engine: return self.engine.capture_channels

        if self.scope.get()=='process': return CHANNELS[self.channel.get()] or None

        matches=[d for d in self.ds if d['name']==self.source.get() and d.get('isLoopbackDevice')]

        return int(matches[0]['maxInputChannels']) if len(matches)==1 else self.device_channel_cache.get(self.source.get())

    def update_controls(self):

        self.controls=Controls(mode=self.mode.get(),bypass=not self.filter_on.get(),strength=self.strength.get()/100,

            background=self.bg.get(),transient=self.transient.get(),rear=self.rear.get(),lfe=self.lfe.get(),center=self.center.get(),limiter=LIMITERS[self.limiter.get()],gain=self.gain.get()/100,impact=self.impact.get()/100)

        if self.engine: self.engine.controls=self.controls

        self.render()

    def render(self):

        ch=self.capture_channels(); active=bool(self.engine); filtering=self.filter_on.get()

        self.global_capture_overlay.label.configure(text=_ui_tr('네이티브 햅틱') if self.studio.auto_haptics_mode==0 else _ui_tr('전역 캡쳐'))
        self.global_capture_overlay.set_visible(self.scope.get()=='device' or self.studio.auto_haptics_mode==0)

        if self.scope.get()=='device' and ch in (2,6,8):

            self.device_channel_cache[self.source.get()]=ch

            actual_channel=next(k for k,v in CHANNELS.items() if v==ch)

            if CHANNELS[self.channel.get()]!=0 and self.channel.get()!=actual_channel: self.channel.set(actual_channel)

        state=(ch,active,self._stopping,filtering,self.scope.get(),self.channel.get(),self.source.get(),self.destination.get(),self.mode.get(),round(self.strength.get(),3),round(self.gain.get(),3),round(self.impact.get(),3),self.bg.get(),self.transient.get(),self.rear.get(),self.lfe.get(),self.center.get(),self.limiter.get())

        if state==self.last_render: return

        self.last_render=state

        available=(ch in (6,8) or ch is None and CHANNELS[self.channel.get()] in (0,6,8)) and getattr(self.engine,'mix_supported',True)

        if CHANNELS[self.channel.get()] in (6,8):self.channel_details.pack(fill='x',pady=(4,0))

        else:self.channel_details.pack_forget()

        if CHANNELS[self.channel.get()] in (0,2):

            self.channel_status_label.configure(text=_ui_tr('자동 적용 중..') if CHANNELS[self.channel.get()]==0 else _ui_tr('2채널 스테레오 적용중..'))

            self.channel_auto_status.pack(fill='both',expand=True)

        else:self.channel_auto_status.pack_forget()

        for sw in self.mix_switches: sw.set_enabled(available)

        for lab in self.channel_labels+[self.limit_label]: lab.configure(foreground=FG if available else DISABLED)

        self.limiter_box.configure(state='readonly' if available else 'disabled')

        self.channel_note.configure(text=(_ui_tr('캡처 형식 · ')+f'{ch}ch') if ch else _ui_tr('시작 시 자동 확인') if CHANNELS[self.channel.get()]==0 else '')

        choices=[key for key,value in CHANNELS.items() if value in (0,ch)] if self.scope.get()=='device' and ch in (2,6,8) else list(CHANNELS)

        self.channel_choice.configure(values=choices,state='disabled' if active else 'readonly')

        self.mix_note.configure(text='')

        self.filter_badge.configure(text=_ui_tr('켜짐') if filtering else _ui_tr('꺼짐'),foreground=ACCENT if filtering else MUTED)

        for w in self.filter_widgets:

            if isinstance(w,(HapticSlider,CircleCheck)): w.set_enabled(filtering)

            else: w.configure(state='normal' if filtering else 'disabled')

        for b,v in self.style_buttons: b.configure(style='Selected.Filter.TButton' if abs(self.strength.get()-v)<.1 and filtering else 'Filter.TButton')

        self.value_label.configure(text=f'{self.strength.get():.0f}%',foreground=FG if filtering else DISABLED)

        self.impact_label.configure(text=f'{self.impact.get():.0f}%',foreground=FG if filtering else DISABLED)

        self.gain_value.configure(text=f'{self.gain.get():.0f}%')

        self._update_binding_display()

        self.filter_note.configure(text='')

        for b in self.scope_buttons: b.set_enabled(not active)

        self.process_sort_box.configure(state='disabled' if active or self.scope.get()!='process' else 'readonly')

        self.game.configure(state='readonly' if self.scope.get()=='process' and not active else 'disabled')

        self.process_table.state(['disabled'] if active or self.scope.get()!='process' else ['!disabled'])

        self.refresh_button.configure(state='normal' if self.scope.get()=='process' and not active and not self._process_refresh_running else 'disabled')

        self.load_button.configure(state='disabled' if active else 'normal')

        self.start_button.configure(state='disabled' if active or self.studio.busy or self.studio_settings.busy or self._close_requested or power_blocked(self) else 'normal'); self.stop_button.configure(state='normal' if active and not self._stopping else 'disabled')

        capture_text=f'{self.engine.capture_channels}ch' if self.engine and self.engine.capture_channels else _ui_tr('대기')

        mode_prefix=_ui_tr('퓨어 · 무음')+'  ·  ' if self.mode.get()=='pure' else ''

        channel_text=_ui_tr('자동 채널') if CHANNELS[self.channel.get()]==0 else self.channel.get()

        self.connection_summary.configure(text=mode_prefix+channel_text+'  ·  '+_ui_tr('캡처 ')+capture_text+'  ·  '+_ui_tr('출력: ')+(_ui_tr('자동 선택') if self.destination.get()==AUTO else self.destination.get()[:20]))

        if self.connection and self.connection.winfo_exists(): self.render_connection()

        if hasattr(self,'studio'): self.studio.render()

    def set_strength(self,value): self.strength.set(value); self.update_controls()

    def toggle_details(self):

        # Kept for integrations; advanced options are always visible.

        return

    def schedule_preferences_save(self,*_):

        if not self._preferences_ready: return

        if self._preferences_job:

            try: self.root.after_cancel(self._preferences_job)

            except tk.TclError: pass

        self._preferences_job=self.root.after(450,self._save_preferences)

    def _preference_snapshot(self):

        data={'remember_last':self.remember_last.get(),'auto_start':self.auto_start.get(),

              'mute_shortcut':dict(self.mute_binding),

              'window_width':max(860,self.root.winfo_width()),'window_height':max(860,self.root.winfo_height())}

        if data['remember_last']:

            self.update_controls()

            data.update(scope=self.scope.get(),channels=CHANNELS[self.channel.get()],channel_auto=CHANNELS[self.channel.get()]==0,input=canonical_device(self.source.get()),

                output=canonical_device(self.destination.get()),game_exe=self.game_names.get(self.game.get(),self.desired_game),

                process_sort=self.process_sort.get(),controls=asdict(self.controls))

        return data

    def _save_preferences(self):

        self._preferences_job=None

        try:

            data=self._preference_snapshot()

            if data!=self._saved_preferences:

                self.preference_store.save(data); self._saved_preferences=data

        except Exception as exc:

            self.notice.set(_ui_tr('설정 저장 실패: ')+tr(str(exc)))

    def flush_preferences(self):

        if self._preferences_job:

            try: self.root.after_cancel(self._preferences_job)

            except tk.TclError: pass

            self._preferences_job=None

        self._save_preferences()

    def game_selected(self,event=None):

        self.desired_game=self.game_names.get(self.game.get(),'')

        self._sync_game_preset()

        self._update_process_selection_status()

        self.schedule_preferences_save()

    def process_selected(self,event=None):

        if self.engine: return

        selected=self.process_table.selection()

        if not selected: return

        pid=int(selected[0]); key=next((name for name,value in self.game_map.items() if value==pid),None)

        if key is None: return

        self.game.set(key); self.desired_game=self.game_names.get(key,'')

        self._sync_game_preset()

        self._update_process_selection_status()

        self.schedule_preferences_save()

    def scope_changed(self):

        self._preset_selection=None; self._sync_game_preset(); self._update_process_selection_status(); self.render()



    def _process_selection_hint(self):

        if self.scope.get()!='process' or self.engine or self.game_map.get(self.game.get()) is not None:return ''

        if not self.desired_game or is_excluded_process(self.desired_game):

            return _ui_tr('목록에서 캡쳐할 프로세스를 선택하세요.')

        count=sum(name.casefold()==self.desired_game.casefold() for name in self.game_names.values())

        if count>1:return ''

        return _ui_tr('게임 실행 후 새로 고침을 눌러 주세요.')



    def _update_process_selection_status(self,base=None):

        # Only replace a selection hint we own, a stopped status or a verified

        # connection-success notice. Never mask audio/HID failures or OFF mode.

        current=self.status.get();owned=current==getattr(self,'_process_hint_message',None)

        hint=self._process_selection_hint()

        if not hint:

            if owned:self.status.set(getattr(self,'_process_hint_base',_ui_tr('정지')))

            self._process_hint_message=None

            return

        success=(_ui_tr('Studio 프로필 조회 완료'),_ui_tr('Studio 연결 확인 완료'),_ui_tr('듀얼센스 연결됨'))

        if base is None:

            if owned:base=getattr(self,'_process_hint_base',_ui_tr('정지'))

            elif current in success:base=_ui_tr('듀얼센스 연결됨')

            elif current==_ui_tr('정지'):base=current

            else:return

        elif base in success:base=_ui_tr('듀얼센스 연결됨')

        self._process_hint_base=base

        self._process_hint_message=base+' · '+hint

        if current!=self._process_hint_message:self.status.set(self._process_hint_message)

    def _update_binding_display(self):

        exe=self.game_names.get(self.game.get(),'')

        enabled=bool(exe) and self.scope.get()=='process' and not self.engine

        self.binding_check.set_enabled(enabled)

        if not exe or self.scope.get()!='process':

            self.binding_text.set(''); return

        bound=self.store.bound_slot(exe); selected=self.slot.current()

        if self.auto_apply_game.get() and bound==selected:

            self.binding_text.set(f'→ {bound+1:02d} · '+self.store.slots[bound]['name'][:18])

        else:

            self.binding_text.set(_ui_tr('저장 시 연결') if self.auto_apply_game.get() else _ui_tr('저장 시 연결 해제') if bound is not None else _ui_tr('연결된 프리셋 없음'))

    def _sync_game_preset(self):

        if self.engine or self._applying_preset: return

        exe=self.game_names.get(self.game.get(),''); pid=self.game_map.get(self.game.get())

        if self.scope.get()!='process' or not exe:

            self.auto_apply_game.set(False); self._preset_selection=None; self._update_binding_display(); return

        identity=(pid,exe.casefold())

        if self._preset_selection==identity: return

        self._preset_selection=identity

        index=self.store.bound_slot(exe)

        self.auto_apply_game.set(index is not None)

        if index is not None: self._apply_slot(index,automatic=True)

        self._update_binding_display()

    def auto_start_changed(self):

        if self.auto_start.get() and not self.remember_last.get(): self.remember_last.set(True)

        self.schedule_preferences_save()

    def scroll_processes_to_top(self):

        self.process_table.yview_moveto(0)

    def process_sort_changed(self,event=None):

        self.process_sort.set(PROCESS_SORTS.get(self.process_sort_label.get(),'audio'))

        self.render_games()

        self.scroll_processes_to_top()

        self.schedule_preferences_save()

    def render_games(self,selected_pid=None):

        rows=[row for row in self._process_snapshot if row['pid']!=os.getpid() and not is_excluded_process(row['name'])]

        if self.process_sort.get()=='cpu':

            rows.sort(key=lambda row:(row['cpu'] is not None,row['cpu'] if row['cpu'] is not None else -1,row['started'] or 0,row['pid']),reverse=True)

        elif self.process_sort.get()=='audio':

            priority={'playing':3,'active':2,'unknown':1,'inactive':0}

            rows.sort(key=lambda row:(priority.get(row.get('audio','unknown'),1),row['started'] or 0),reverse=True)

        else:

            rows.sort(key=lambda row:(row['started'] or 0,row['pid']),reverse=True)

        old_pid=selected_pid if selected_pid is not None else self.game_map.get(self.game.get())

        self.game_map.clear(); self.game_names.clear(); values=[]

        for row in rows:

            if row['pid']==os.getpid(): continue

            cpu='—' if row['cpu'] is None else f"{row['cpu']:.1f}%"

            started=self._process_sampler.started_label(row['started'])

            key=f"{row['name']} · CPU {cpu} · {started} · PID {row['pid']}"

            self.game_map[key]=row['pid']; self.game_names[key]=row['name']; values.append(key)

        self.game.configure(values=values)

        self.process_table.delete(*self.process_table.get_children())

        rows_by_pid={row['pid']:row for row in rows}

        live_keys={(row['pid'],row['started']) for row in rows}

        self.process_dot_colors={key:value for key,value in self.process_dot_colors.items() if key in live_keys}

        previous_color=None

        for key,pid in self.game_map.items():

            row=rows_by_pid.get(pid)

            if row is None: continue

            cpu='—' if row['cpu'] is None else f"{row['cpu']:.1f}%"

            identity=(pid,row['started'])

            if identity not in self.process_dot_colors:

                self.process_dot_colors[identity]=self._dot_random.choice([i for i in range(len(self.process_dots)) if i!=previous_color])

            color_index=self.process_dot_colors[identity]; previous_color=color_index

            self.process_table.insert('', 'end', iid=str(pid),text='  '+row['name'],values=(AUDIO_STATES.get(row.get('audio','unknown'),AUDIO_STATES['unknown']),cpu,self._process_sampler.started_label(row['started'])),

                                      image=self.process_dots[color_index],tags=('process',))

        selected=next((key for key,pid in self.game_map.items() if pid==old_pid),None)

        if not selected and self.desired_game:

            pid=match_game(self.desired_game,[(self.game_names[key],value) for key,value in self.game_map.items()])

            selected=next((key for key,value in self.game_map.items() if value==pid),None)

        self.game.set(selected or '')

        if selected and self.game_map.get(selected) is not None:

            self.process_table.selection_set(str(self.game_map[selected])); self.process_table.focus(str(self.game_map[selected]))

        else:

            self.process_table.selection_remove(*self.process_table.selection())

        if selected: self.desired_game=self.game_names[selected]

        self._update_process_selection_status()

        self._sync_game_preset()

    def refresh_games(self,initial=False):

        self.scroll_processes_to_top()

        if self._process_refresh_running: return

        self._process_refresh_running=True

        self.refresh_button.configure(state='disabled')

        selected_pid=self.game_map.get(self.game.get())

        def collect():

            try: result=self._process_sampler.snapshot(); error=None

            except Exception as exc: result=None; error=exc

            self._refresh_results.put(("games",result,error,selected_pid,initial))

        start_thread(threading.Thread(target=collect,daemon=True))

    def _finish_game_refresh(self,rows,error,selected_pid,initial):

        self._process_refresh_running=False

        if error:

            self.refresh_button.configure(state='normal' if self.scope.get()=='process' and not self.engine else 'disabled')

            self.status.set(_ui_tr('게임 목록 조회 실패: ')+tr(str(error)))

        else:

            self._process_snapshot=rows

            self.render_games(selected_pid)

            self._next_process_refresh=time.monotonic()+2.5

            if self.scope.get()=='process' and not self.engine: self.refresh_button.configure(state='normal')

        self.scroll_processes_to_top()

        if initial and not self._auto_start_attempted:

            self._auto_start_attempted=True

            if self.auto_start.get() and '--smoke-test' not in sys.argv:

                if error:

                    self.status.set(_ui_tr('자동 시작을 건너뛰었습니다 · 프로세스 목록을 확인하세요.'))

                elif self.controls.mode!='normal':

                    self.status.set(_ui_tr('자동 시작을 건너뛰었습니다 · 퓨어 모드는 현재 지원하지 않습니다.'))

                elif self.scope.get()=='process' and not self.game.get():

                    self.status.set(_ui_tr('자동 시작을 건너뛰었습니다 · 저장된 게임이 실행 중인지 확인하세요.'))

                else:

                    self.root.after(100,self.start)

    def refresh_devices(self):

        if getattr(self,'_device_refresh_running',False): return

        self._device_refresh_running=True

        for button in getattr(self,'device_refresh_buttons',[]):

            if button.winfo_exists(): button.configure(state='disabled')

        def collect():

            try: result=devices(); error=None

            except Exception as exc: result=None; error=exc

            self._refresh_results.put(("devices",result,error))

        start_thread(threading.Thread(target=collect,daemon=True))

    def _finish_device_refresh(self,rows,error):

        self._device_refresh_running=False

        if error:

            self.status.set(_ui_tr('장치 목록 조회 실패: ')+tr(str(error)))

        else:

            self._diagnostics_support=None
            update_diagnostics_button(self)
            self.ds=rows

            self.inputs=[AUTO]+[d['name'] for d in rows if d.get('isLoopbackDevice') and not any(name in d['name'].lower() for name in ('dualsense','studio xinput experiment'))]

            self.outputs=[AUTO]+[d['name'] for d in rows if d['maxOutputChannels']>=4 and not d.get('isLoopbackDevice')]

            if self.source.get() not in self.inputs: self.source.set(AUTO)

            # Keep an explicitly selected missing output instead of silently routing elsewhere.

            if self.connection and self.connection.winfo_exists():

                if 'source' in self.conn_widgets: self.conn_widgets['source'].configure(values=self.inputs)

                if 'output' in self.conn_widgets: self.conn_widgets['output'].configure(values=self.outputs)

            self.status.set(_ui_tr('장치 목록을 갱신했습니다.'))

        for button in getattr(self,'device_refresh_buttons',[]):

            if button.winfo_exists(): button.configure(state='normal')

    def _diagnostics_visible(self):

        return (self.selected_tab==1 and self.root.state() not in ('iconic','withdrawn')

                and self.device_page.winfo_exists() and self.device_page.winfo_viewable())

    def _schedule_diagnostic_spacing(self,event=None):

        if self._diagnostic_spacing_job is None and not self._closing:

            self._diagnostic_spacing_job=self.root.after_idle(self._fit_diagnostic_spacing)

    def _fit_diagnostic_spacing(self):

        self._diagnostic_spacing_job=None

        if not self._diagnostics_visible():return

        self.diagnostics_body.fit_text()

    def _update_diagnostics(self):

        # Reuse the main one-second tick. Never compute percentiles in a hidden tab.

        if not self._diagnostics_visible(): return

        if not self.engine:

            text=_ui_tr('오디오 엔진이 정지 상태입니다.')

        else:

            stats=self.engine.stats(); dsp=stats.get('dsp_ms',{}); latency=stats.get('stream_latency',{})

            timing=stats.get('latency_ms',{});buffer=stats.get('capture_buffer',{})

            def milliseconds(value):return '—' if value is None else f'{value*1000:.1f} ms'

            def timing_text(key):

                values=timing.get(key,{})

                return f"{values['p50']:.1f} / {values['p95']:.1f} / {values['max']:.1f} ms" if values else '—'

            health=stats.get('health',{}); seconds=health.get('seconds',0)

            status=stats.get('status','')

            if self.active_process_name and status.startswith(_ui_tr('지정 프로세스 PID ')):

                status=status.replace(_ui_tr('지정 프로세스 PID ')+str(self.active_process_pid),_ui_tr('지정 프로세스 · ')+self.active_process_name,1)

            lines=[_ui_tr('전송 상태: ')+tr(health.get('label','—'))+' · '+tr(status),_ui_tr('처리 블록: ')+str(stats.get('blocks',0))+_ui_tr(' · 오류: ')+str(stats.get('errors',0)),

                _ui_tr('DSP 지연 p50/p95/p99/max: ')+f"{dsp.get('p50',0):.2f} / {dsp.get('p95',0):.2f} / {dsp.get('p99',0):.2f} / {dsp.get('max',0):.2f} ms",

                _ui_tr('드라이버 보고 입력/출력: ')+milliseconds(latency.get('input_s'))+' / '+milliseconds(latency.get('output_s')),

                _ui_tr('PC 대기 p50/p95/max: ')+timing_text('pc_queue_ms'),

                _ui_tr('캡처 → 출력 호출 p50/p95/max: ')+timing_text('capture_to_output_call_ms'),

                _ui_tr('출력 호출 대기 p50/p95/max: ')+timing_text('output_write_wait_ms'),

                _ui_tr('최근 손실/오래된 패킷: ')+(f"{health.get('drops',0)} / {health.get('stale',0)} ({seconds:.1f}s)" if seconds else '—'),

                _ui_tr('입력 피크: ')+f"{stats.get('peak',0)*100:.1f}% · "+_ui_tr('재연결: ')+str(stats.get('reconnect_count',0)),

                _ui_tr('햅틱 세기: ')+f"{self.gain.get():.0f}% · "+_ui_tr('출력 제한 샘플: ')+str(stats.get('output_limited_samples',0))]

            if buffer:

                lines.append(_ui_tr('PC 수신 버퍼: ')+f"{buffer['buffer_ms']:.1f} ms · "+_ui_tr('시작 시 폐기 프레임: ')+str(buffer['prefill_discarded_frames'])+

                             ' · '+_ui_tr('캡처 시각 오류: ')+str(buffer['timestamp_errors']))

            if stats.get('capture_timing_source')=='device_queue_estimate':

                lines.append(_ui_tr('장치 전체: 큐 길이 기반 추정 · 하드웨어 시각/손실 횟수 미계측'))

            lines.append(_ui_tr('PC 내부 계측 · USB 이후 지연 미측정'))

            text='\n'.join(lines)

        if text!=self._diagnostics_text:

            self.diagnostics_body.set_text(text);self._diagnostics_text=text

        self._schedule_diagnostic_spacing()

    def refresh_slots(self,index=0):

        self.slot.configure(values=[f'{i+1:02d} · '+(item['name'] if item else _ui_tr('빈 슬롯')) for i,item in enumerate(self.store.slots)]); self.slot.current(index)

    def slot_selected(self,event=None):

        item=self.store.slots[self.slot.current()]; self.slot_name.set(item['name'] if item else _ui_tr('게임 설정'))

        self._update_binding_display()

    def save_prompt(self):

        name=simpledialog.askstring(_ui_tr('프리셋 저장'),tr(_ui_tr('{0}번 슬롯 이름\n저장하면 해당 슬롯의 설정을 교체합니다.').format(f'{self.slot.current() + 1:02d}')),initialvalue=self.slot_name.get(),parent=self.root)

        if name is not None: self.slot_name.set(name.strip()); self.save_slot()

    def save_slot(self):

        try:

            self.update_controls(); i=self.slot.current()

            exe=self.game_names.get(self.game.get()) if self.scope.get()=='process' else None

            self.store.save(i,dict(name=self.slot_name.get(),game_exe=self.game_names.get(self.game.get(),self.desired_game),

                scope=self.scope.get(),channels=CHANNELS[self.channel.get()],input=canonical_device(self.source.get()),output=canonical_device(self.destination.get()),controls=asdict(self.controls)),

                bind_game=exe,auto_apply=self.auto_apply_game.get() if exe else None)

            self.refresh_slots(i); self._update_binding_display(); self.notice.set(tr(_ui_tr('{0}번 저장됨 · ').format(f'{i + 1:02d}'))+self.slot_name.get())

        except Exception as exc: messagebox.showerror(_ui_tr('프리셋 저장 실패'),tr(str(exc)),parent=self.root)

    def load_slot(self):

        if self.engine: return

        self._apply_slot(self.slot.current())

    def _apply_slot(self,index,automatic=False):

        if self.engine: return

        item=self.store.slots[index]

        if item is None: self.notice.set(_ui_tr('빈 슬롯입니다. 설정을 맞춘 뒤 저장을 누르세요.')); return

        self._applying_preset=True

        try:

            self.slot.current(index)

            if not automatic:

                self.desired_game=item['game_exe']; self.game.set(''); self.scope.set(item['scope'])

                self.source.set(display_device(item['input'])); self.destination.set(display_device(item['output']))

            self.channel.set(next(k for k,v in CHANNELS.items() if v==item['channels']))

            c=Controls(**item['controls'])

            self.mode.set('normal'); self.filter_on.set(not c.bypass); self.strength.set(c.strength*100); self.gain.set(c.gain*100); self.impact.set(c.impact*100)

            self.bg.set(c.background); self.transient.set(c.transient); self.rear.set(c.rear); self.lfe.set(c.lfe); self.center.set(c.center)

            self.limiter.set(next(k for k,v in LIMITERS.items() if v==c.limiter)); self.slot_name.set(item['name'])

            if not automatic: self.render_games()

            exe=self.game_names.get(self.game.get(),'')

            self.auto_apply_game.set(self.store.bound_slot(exe)==index)

            self._preset_selection=(self.game_map.get(self.game.get()),exe.casefold()) if exe else None

            self.update_controls(); self._update_binding_display()

            self.notice.set((_ui_tr('자동 불러옴 · ') if automatic else _ui_tr('불러옴 · '))+item['name'])

        finally: self._applying_preset=False

        if (self.scope.get()=='device' and self.source.get() not in self.inputs) or self.destination.get() not in self.outputs:

            self.status.set(_ui_tr('저장한 장치가 없습니다. 연결 설정에서 직접 선택하세요.'))

    def open_connection(self):

        self.select_tab(1)

        self.render_connection()

    def render_connection(self):

        active=bool(self.engine)

        for key,w in self.conn_widgets.items():

            enabled=not active and (key=='output' or key=='source' and self.scope.get()=='device' or key=='channel')

            if key=='channel':

                ch=self.capture_channels()

                w.configure(values=[key for key,value in CHANNELS.items() if value in (0,ch)] if self.scope.get()=='device' and ch in (2,6,8) else list(CHANNELS))

                enabled=enabled

            w.configure(state='readonly' if enabled else 'disabled')

    def _run_route(self):

        scope=self.scope.get();pid=self.game_map.get(self.game.get()) if scope=='process' else None

        started=next((row.get('started') for row in self._process_snapshot if row['pid']==pid),None) if pid else None

        return (scope,pid,started,self.source.get(),self.destination.get(),self.channel.get())

    def start(self,automatic=False):

        if power_blocked(self):return
        if getattr(self,'device_diagnostics',None) is not None:return

        if self.engine or self._closing or self._close_requested or self.studio_settings.busy:return

        route=self._run_route()

        if automatic:

            if not self.run_intent.can_resume(route):return

        else:self.run_intent.request(route)

        self.studio.check_before_start(self._start_after_profile_check)



    def _start_after_profile_check(self, hid_rows=None):

        if power_blocked(self):return
        if getattr(self,'device_diagnostics',None) is not None:return

        if (self.engine or self._closing or self._close_requested or self.studio_settings.busy
                or self.studio.busy or not self.run_intent.requested):return

        pinned_resume=(self.run_intent.profile_paused and self.run_intent.can_resume(self._run_route())

                       and self.studio.binding.snapshot().endpoint_id is not None)

        if (self.destination.get() not in self.outputs and not pinned_resume) or self.scope.get()=='device' and self.source.get() not in self.inputs:

            self.run_intent.stop('invalid_route')

            messagebox.showerror(_ui_tr('장치 선택'),_ui_tr('연결 설정에서 입출력 장치를 선택하세요.'),parent=self.root); return

        pid=self.game_map.get(self.game.get()) if self.scope.get()=='process' else None

        if self.scope.get()=='process' and not pid:

            self.run_intent.stop('invalid_route')

            messagebox.showerror(_ui_tr('게임 선택'),_ui_tr('게임을 실행하고 새로 고침 후 실제 게임 exe를 선택하세요.'),parent=self.root); return

        row=next((item for item in self._process_snapshot if item['pid']==pid),None) if pid else None

        started=row['started'] if row else None

        if pid and self._process_sampler.is_running(pid,started) is False:

            self.run_intent.stop('process_exit')

            self.status.set(_ui_tr('선택한 프로세스가 종료되었거나 변경되었습니다. 새로 고침 후 선택하세요.')); return

        from output_debug import record
        record('start_output_check', self.ds, self.studio.binding, self.destination.get())
        requested=None if self.destination.get()==AUTO else self.destination.get()
        binding=self.studio.binding
        if binding.output(self.ds,requested) is None:
            matches=[d for d in self.ds if (d.get('name')==requested if requested is not None else 'dualsense' in d.get('name','').lower()) and d.get('maxOutputChannels',0)>=4 and not d.get('isLoopbackDevice')]
            identity=binding.snapshot()
            eligible=(len(matches)==1 and matches[0].get('endpoint_id') and identity.hid_path)
            if hid_rows is None:
                if getattr(self,'_pair_lookup_pending',False):return
                self._pair_lookup_pending=True
                results=queue.SimpleQueue()
                generation=self.run_intent.generation
                lookup_deadline=time.monotonic()+10
                def collect_pair():
                    from studio_slots import devices as studio_devices
                    try: rows=studio_devices()
                    except Exception: rows=[]
                    refreshed=None
                    error=None
                    try:
                        for delay in (0, .3, .6):
                            time.sleep(delay)
                            try:
                                refreshed=devices()
                                error=None
                            except (OSError,RuntimeError) as exc:
                                error=str(exc)
                                continue
                            if binding.output(refreshed,requested) is not None or any(
                                d.get("maxOutputChannels",0)>=4 and not d.get("isLoopbackDevice")
                                and ("dualsense" in d.get("name","").lower() or d.get("name")==requested)
                                for d in refreshed):break
                    except Exception as exc:
                        error=str(exc)
                    finally:
                        results.put((rows,refreshed,error))
                def finish_pair():
                    if self._closing or self._close_requested:
                        self._pair_lookup_pending=False;return
                    try: rows,refreshed,error=results.get_nowait()
                    except queue.Empty:
                        if time.monotonic()<lookup_deadline:
                            self.root.after(50,finish_pair)
                            return
                        rows,refreshed,error=[],None,_ui_tr('시간 초과')
                    self._pair_lookup_pending=False
                    if error and self.run_intent.generation==generation:
                        self.run_intent.stop('output_lookup_error')
                        self.status.set(_ui_tr('장치 목록 조회 실패: ')+tr(error))
                        self.render()
                        return
                    if binding.snapshot()==identity and self.run_intent.requested and self.run_intent.generation==generation:
                        if refreshed is not None:self.ds=refreshed
                        self._start_after_profile_check(rows)
                start_thread(threading.Thread(target=collect_pair,daemon=True))
                self.root.after(50,finish_pair)
                return
            if not eligible:
                self.run_intent.stop('invalid_route')
                if not any(d.get('maxOutputChannels',0)>=4 and not d.get('isLoopbackDevice') for d in self.ds):
                    messagebox.showerror(_ui_tr('출력 확인'),_ui_tr('Windows에서 듀얼센스 오디오 출력을 찾지 못했습니다. Pico USB 연결과 Windows 소리 설정을 확인하세요.'),parent=self.root);return
                messagebox.showerror(_ui_tr('출력 확인'),_ui_tr('선택한 출력을 안전하게 식별할 수 없습니다. 장치 이름을 구분하고 새로 고침하세요.'),parent=self.root);return
            auto_paired=binding.auto_pair_output(self.ds,hid_rows,requested)
            if auto_paired:
                record('single_device_auto_pair',self.ds,binding,requested)
            if not auto_paired and not messagebox.askyesno(_ui_tr('출력 확인'),_ui_tr('선택한 출력이 현재 Pico의 듀얼센스 오디오 장치인지 확인하세요. 이 출력으로 연결할까요?')+'\n'+matches[0]['name'],parent=self.root):
                self.run_intent.stop('output_confirmation_cancelled');return
            if not auto_paired and not binding.confirm_output(matches[0],allow_container_mismatch=True):
                self.run_intent.stop('invalid_route');return
        self.update_controls()

        candidate=Engine(None if self.source.get()==AUTO else self.source.get(),None if self.destination.get()==AUTO else self.destination.get(),self.controls,process_pid=pid,process_channels=CHANNELS[self.channel.get()],binding=self.studio.binding)

        try:

            candidate.start(); self.engine=candidate;self.run_intent.profile_paused=False

            if pid:

                self.active_process_pid=pid

                self.active_process_name=Path(self.game_names.get(self.game.get(),'')).stem or self.game_names.get(self.game.get(),'')

                self.active_process_started=started

                self.next_process_check=time.monotonic()+self.process_check_interval

            self.studio.discover(allow_running=True,after_start=True)

            self.status.set(_ui_tr('연결 중…')); self.render()

        except Exception as exc:

            record('start_failed', self.ds, self.studio.binding, self.destination.get(), error=exc)
            self.run_intent.stop('start_error')

            messagebox.showerror(_ui_tr('시작 실패'),tr(str(exc)),parent=self.root)

    def _finish_stop(self,message=None):

        self.engine=None; self._stopping=False

        self._reconnect_wait_engine=None;self._reconnect_wait_since=None

        self.active_process_pid=None; self.active_process_started=None; self.active_process_name=None

        self.status.set(message or _ui_tr('정지')); self.render()

        callbacks,self._stop_callbacks=self._stop_callbacks,[]

        self._stop_message=None

        for callback in callbacks: callback()

    def stop(self,on_complete=None,message=None,reason='manual'):

        self.run_intent.stop(reason)

        self._reconnect_wait_engine=None;self._reconnect_wait_since=None

        if reason!='profile_off':self.studio._start_callback=None

        if on_complete is not None: self._stop_callbacks.append(on_complete)

        if message is not None: self._stop_message=message

        if self._stopping: return False

        if not self.engine:

            self._finish_stop(self._stop_message); return True

        self._stopping=True

        engine=self.engine; engine.stop_event.set()

        self.status.set(_ui_tr('정지 중…')); self.render()

        def shutdown():

            try: self._stop_results.put((engine,engine.stop(),None))

            except Exception as exc: self._stop_results.put((engine,False,str(exc)))

        start_thread(threading.Thread(target=shutdown,daemon=True))

        self.root.after(100,self._poll_stop)

        return False

    def _poll_stop(self):

        try: engine,stopped,error=self._stop_results.get_nowait()

        except queue.Empty:

            self.root.after(100,self._poll_stop); return

        if engine is not self.engine: return

        if stopped:

            self._finish_stop(self._stop_message)

        else:

            self._stopping=False; self._next_stop_retry=time.monotonic()+5

            self.status.set(_ui_tr('정지 대기 중 · 드라이버 응답을 기다립니다.')+((' · '+error) if error else ''))

            self.render()

    def _external_profile(self,result):

        profile=result['profile'];path=result['path'];old=self.studio.observed_profile

        current={k:profile.get(k) for k in ('index','name','edited','auto_haptics_enable')}

        if result.get('row'):

            self.studio.binding.bind_hid(result['row'])

            profile=dict(profile,device_row=result['row'],device_serial=result['row'].get('serial_number'))

        if old==current and self.studio.profile_path==path:return

        editor=self.studio_settings

        if editor.loaded:

            stamp={k:profile.get(k) for k in ('index','name','edited')}

            if editor.profile_stamp!=stamp or editor.doc.values.get('auto_haptics_enable')!=profile.get('auto_haptics_enable'):

                editor.write_ready=False;editor.external_stale=True

                if editor.built:

                    mode={0:'Off',1:'Mix',2:'Replace'}.get(profile.get('auto_haptics_enable'),_ui_tr('미확인'))

                    editor.identity.set(_ui_tr('현재 프로필 · ')+str(profile.get('name') or _ui_tr('미저장 설정'))+_ui_tr(' · 오디오햅틱 ')+mode)

                    editor.progress.configure(text=_ui_tr('외부 프로필 변경 · 새로 고침이 필요합니다.'))

                editor.update_state()

                macro=getattr(editor,'macro_editor',None)

                if (editor.built and self.selected_tab==2 and not editor.doc.dirty and not editor.busy

                        and not (macro is not None and not macro.closed)):

                    editor.task('entry_read',editor.entry_snapshot)

        self.studio._observe_profile(path,profile);self.studio._sync_current_profile(path,profile)

        self.studio.enforce_haptics_policy();self.studio.render();self.last_render=None;self.render()



    def tick(self):
        while True:
            try: item=self._refresh_results.get_nowait()
            except queue.Empty: break
            if self._closing: continue
            if item[0]=="games": self._finish_game_refresh(*item[1:])
            else: self._finish_device_refresh(*item[1:])
        if self.engine:
            self.engine.diagnostics_enabled=self._diagnostics_visible()

        self._update_mute_state()
        update_diagnostics_button(self)

        self.studio_power.tick()

        if self.studio_power.state=='closing':return

        if self.studio_power.blocked and not self._closing:

            self.root.after(1000,self.tick)

            return

        self.controller_presence.tick(self.engine,self.studio.profile_path,

                                      paused=self._closing or self._close_requested or self._stopping or self.studio.busy or self.studio_settings.busy,

                                      serial=self.studio.device_serials.get(self.studio.profile_path),binding=self.studio.binding)

        idle_enabled=(self.engine is None and not self._stopping and self.selected_tab==0

                      and not (self._closing or self._close_requested or self.studio.busy or self.studio_settings.busy)

                      and '--smoke-test' not in sys.argv)

        if self.idle_presence.tick(self.studio.binding,enabled=idle_enabled) is False:

            self.studio.controller_connected=False

            self.status.set(_ui_tr('연결된 듀얼센스가 없습니다.'))

            self.studio.current_profile=None;self.studio.current_profile_name=None

            self.studio.observed_profile=None;self.studio.auto_haptics_mode=None

            self.studio.catalog_invalid=True;self.studio.last_profile_check=-1e9

            editor=self.studio_settings

            editor.write_ready=False;editor.pico_recognized=False;editor.external_stale=True

            if editor.built:

                editor.identity.set(_ui_tr('연결된 듀얼센스가 없습니다.'));editor.update_state()

            self.battery.generation+=1;self.battery.state='disconnected';self.battery.value=None

            self.run_intent.stop('controller_disconnected');self.studio.render();self.last_render=None;self.render()

        # Recover controls if initialization or a running backend exits unexpectedly.

        if self.engine and not self._stopping and not self.engine.thread.is_alive():

            message=tr(self.engine.status)

            if self.controller_presence.disconnected:

                message=_ui_tr('듀얼센스 연결이 해제되어 전송이 중단되었습니다.')

            if self.active_process_pid and self._process_sampler.is_running(self.active_process_pid,self.active_process_started) is False:

                message=(self.active_process_name or _ui_tr('대상 프로세스'))+_ui_tr(' 종료 · 자동 정지')

            if not self.run_intent.profile_paused:self.run_intent.stop('engine_exit')

            self._finish_stop(self._stop_message or message)

            if self._closing: return

        if self._closing and self.engine and not self._stopping and time.monotonic()>=self._next_stop_retry:

            self.stop()

        # One selected PID is checked every five seconds; no repeated process-list scan.

        if self.engine and not self._stopping and self.active_process_pid and time.monotonic()>=self.next_process_check:

            self.next_process_check=time.monotonic()+self.process_check_interval

            alive=self._process_sampler.is_running(self.active_process_pid,self.active_process_started)

            if alive is False:

                ended_name=self.active_process_name or _ui_tr('대상 프로세스')

                self.stop(message=ended_name+_ui_tr(' 종료 · 자동 정지'))

        # Check the existing connection state on the UI tick, even minimized.

        # No additional HID enumeration or audio-thread work is required.

        waiting=(self.engine is not None and not self._stopping and

                 (self.controller_presence.disconnected or self.engine.reconnecting or self.engine.phase=='waiting'))

        if waiting:

            now=time.monotonic()

            if self._reconnect_wait_engine is not self.engine or self._reconnect_wait_since is None:

                self._reconnect_wait_engine=self.engine;self._reconnect_wait_since=now

            elif now-self._reconnect_wait_since>=8.:

                initial=not getattr(self.engine,'blocks',0)
                message=_ui_tr('최초 오디오 연결 대기 8초 초과 · 자동 정지') if initial else _ui_tr('재연결 대기 8초 초과 · 자동 정지')
                detail=getattr(self.engine,'output_wait_reason','')
                self.stop(message=message+(' · '+detail if detail else ''),reason='initial_output_timeout' if initial else 'reconnect_timeout')

        else:

            self._reconnect_wait_engine=None;self._reconnect_wait_since=None

        # No animation or live plots; no hidden/minimized statistics work.

        if self.engine and not self._stopping and not self.engine.stop_event.is_set() and self.root.state()!='iconic':

            engine_status=self.engine.status

            if self.active_process_name and engine_status.startswith(_ui_tr('지정 프로세스 PID ')):

                tail=engine_status.split(' · ',1)

                engine_status=_ui_tr('지정 프로세스 · ')+self.active_process_name+(' · '+tail[1] if len(tail)>1 else '')

            engine_status=tr(engine_status)

            if self.controller_presence.disconnected:

                engine_status=_ui_tr('듀얼센스 연결 해제 · 재연결 대기 중')

            if self.status.get()!=engine_status:self.status.set(engine_status)

            self.render()

        self._update_diagnostics()

        paused=(self._closing or self._close_requested or self._stopping or self.studio.busy or self.studio_settings.busy)

        watch_audio = self.run_intent.requested and (self.engine is not None or self.run_intent.profile_paused)
        watch_mute = self.studio.binding.snapshot().hid_path is not None
        observation=self.profile_watch.tick(self.studio.binding,
            enabled=self.profile_watch_enabled and (watch_audio or watch_mute),
            token=self.run_intent.generation,seed=self.studio.observed_profile,paused=paused)
        if observation:
            self._mute_macro_policy = (observation['path'], observation['profile'].get('mute_macro', False))
            if watch_audio:self._external_profile(observation)
            self._update_mute_state()

        if self.run_intent.profile_paused and self.run_intent.route!=self._run_route():

            self.run_intent.stop('route_changed')

        if (not paused and self.engine is None and self.run_intent.can_resume(self._run_route())

                and self.studio.auto_haptics_mode in (1,2)):

            self.start(automatic=True)

        preferred=self.studio.selected[0] if self.studio.selected else self.studio.paths[0] if len(self.studio.paths)==1 else None

        self.battery.tick(paused=self._closing or self.studio.busy or self.studio_settings.busy or self.idle_presence.absent or '--smoke-test' in sys.argv,preferred=preferred)

        if '--smoke-test' not in sys.argv:self.studio.recover_battery_connection(self.battery)

        self.brand_wordmark.show_status(self.battery.state,self.battery.value)

        self.root.after(1000,self.tick)





def smoke(app,report):

    from types import SimpleNamespace

    results={"default_limiter_hard":app.controls.limiter=="hard", "channel_order": [w.cget("text") for w in app.channel_labels]==[_ui_tr('센터'),_ui_tr('후방 L / R'),_ui_tr('LFE · 저음')]}

    app.scope.set('process'); app.channel.set(next(k for k,v in CHANNELS.items() if v==6)); app.center.set(True); app.rear.set(True); app.lfe.set(True); app.filter_on.set(True); app.strength.set(73); app.limiter.set(_ui_tr('초과분 자르기')); app.update_controls()

    results['six_channel_enabled']=all(s.enabled for s in app.mix_switches) and str(app.limiter_box['state'])=='readonly'

    app.filter_switch.invoke()

    results['filter_off_maps_to_bypass']=app.controls.bypass and all(not w.enabled if isinstance(w,(HapticSlider,CircleCheck)) else str(w['state'])=='disabled' for w in app.filter_widgets) and app.controls.rear and app.controls.lfe

    app.filter_switch.invoke()

    results['filter_on_maps_to_processing']=not app.controls.bypass

    app.channel.set(next(k for k,v in CHANNELS.items() if v==2)); app.render()

    app.mix_switches[0].invoke()

    results['center_enabled_six']=len(app.mix_switches)==3 and app.controls.center

    results['two_channel_disabled']=all(not s.enabled for s in app.mix_switches) and str(app.limiter_box['state'])=='disabled' and app.rear.get() and app.center.get() and not app.controls.bypass

    app.device_channel_cache.clear(); app.channel.set(next(k for k,v in CHANNELS.items() if v==6)); app.scope.set('device'); app.source.set(AUTO); app.render()

    results['unknown_device_five_one_configurable']=all(s.enabled for s in app.mix_switches) and app.capture_channels() is None

    app.engine=SimpleNamespace(capture_channels=2); app.render()

    results['actual_device_two_disabled']=all(not s.enabled for s in app.mix_switches)

    app.engine.capture_channels=6; app.render()

    results['actual_device_six_enabled']=all(s.enabled for s in app.mix_switches)

    app.engine=None; app.scope.set('process'); app.channel.set(next(k for k,v in CHANNELS.items() if v==6)); app.update_controls()

    if '--preset-test-path' in sys.argv:

        app.slot_name.set(_ui_tr('UI 시험')); app.desired_game='test_game.exe'; app.save_slot()

        app.filter_on.set(False); app.strength.set(12); app.center.set(False); app.rear.set(False); app.lfe.set(False); app.limiter.set(_ui_tr('부드러운 제한')); app.update_controls(); app.load_slot()

        results['preset_roundtrip']=app.filter_on.get() and app.strength.get()==73 and app.rear.get() and app.lfe.get() and app.center.get() and app.controls.center and app.controls.limiter=='hard' and app.desired_game=='test_game.exe'

    app.toggle_details(); app.root.update_idletasks()

    clipped=[]

    def bounds(widget):

        for child in widget.winfo_children():

            if child.winfo_viewable() and not isinstance(child,tk.Toplevel):

                x=child.winfo_rootx()-app.root.winfo_rootx(); y=child.winfo_rooty()-app.root.winfo_rooty()

                if x<0 or y<0 or x+child.winfo_width()>app.root.winfo_width()+1 or y+child.winfo_height()>app.root.winfo_height()+1:

                    clipped.append(str(child))

                bounds(child)

    bounds(app.root)

    results['widgets_outside_window']=clipped

    app.open_connection(); app.root.update_idletasks()

    app.scope.set('process'); app.render()

    results['process_connection_fields']=str(app.conn_widgets['source']['state'])=='disabled' and str(app.conn_widgets['channel']['state'])=='readonly'

    app.scope.set('device'); app.render()

    results['device_connection_fields']=str(app.conn_widgets['source']['state'])=='readonly' and str(app.conn_widgets['channel']['state'])=='readonly'

    results['page_focus_border_fixed']=app.pages.cget('highlightcolor')==BORDER

    results['process_icons_visible']='tree' in str(app.process_table['show'])

    results['caption_uses_program_icon']=(Path(__file__).parent/'assets/dslight.ico').is_file() and not hasattr(app,'caption_icon')

    results['redundant_mode_removed']=not hasattr(app,'normal_button') and app.mode.get()=='normal'

    import hid

    results['studio_hid_backend_loaded']=callable(hid.enumerate)

    results['studio_starts_without_hid_polling']=app.studio.poll_id is None and not app.studio.busy

    results['advanced_inline']=not hasattr(app,'details_button') and bool(app.advanced.winfo_ismapped())

    results['impact_control_present']=app.impact_slider.maximum==100

    results['auto_channel_available']=0 in CHANNELS.values() and 8 in CHANNELS.values()

    editor=app.studio_settings

    editor.build();editor.loaded=True

    app.select_tab(2);app.root.update_idletasks()

    results['studio_settings_native_tab']=editor.built and app.selected_tab==2

    results['studio_settings_right_aligned']=app.tabs._left(2)+app.tabs.tab_width==app.tabs.winfo_width()

    from studio_fields import FIELDS

    results['studio_stable_field_count']=len(FIELDS)

    for category in range(6):editor.select_category(category);app.root.update_idletasks()

    results['studio_settings_categories_render']=True

    editor.loaded=False

    app.studio.close(); app.select_tab(0)

    results.update(language=LANGUAGE,controls=asdict(app.controls),tk_window_created=True,audio_started=False,width=app.root.winfo_width(),height=app.root.winfo_height(),requested_height=app.root.winfo_reqheight(),inputs=app.inputs,outputs=app.outputs,preset_slots=SLOT_COUNT)

    report.write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')

    return results





def main():

    enable_dpi_awareness()
    root=tk.Tk(); lock=None

    try:

        isolated_smoke='--smoke-test' in sys.argv and all(flag in sys.argv for flag in ('--preferences-test-path','--preset-test-path','--ui-test-path'))

        lock=InstanceLock('Local\\DS5LightSmoke-'+str(os.getpid())) if isolated_smoke else InstanceLock()

        app=App(root)

    except Exception as exc:

        if '--smoke-test' in sys.argv:

            Path(sys.argv[sys.argv.index('--smoke-test')+1]).write_text(json.dumps({'error':str(exc)},ensure_ascii=False),encoding='utf-8')

        else:
            root.withdraw()
            messagebox.showerror(_ui_tr('실행 실패'),tr(str(exc)),parent=root)

        if lock: lock.close()

        root.destroy(); return

    def close():

        if app._closing: return
        diagnostic=getattr(app,'device_diagnostics',None)
        if diagnostic is not None:
            diagnostic.close()
            if diagnostic.busy:
                root.after(100,close);return

        app._close_requested=True

        if app.studio_settings.recording and not app.studio_settings.busy and not app.studio.busy:

            app.studio_settings.finish_recording_for_close();root.after(100,close);return

        if app.studio_settings.busy:

            if not app.studio_settings.closing_recording:app.studio_settings.cancel.set()

            root.after(100,close);return

        if app.studio.busy:

            root.after(100,close);return

        app._closing=True

        app.battery.close()

        app.controller_presence.close();app.idle_presence.close();app.profile_watch.close()

        app.mute_shortcut.close()

        app.studio.close()

        app.studio_settings.close()

        app.flush_preferences()

        def finish(): lock.close(); root.destroy()

        app.stop(on_complete=finish)

    app.request_close=close

    root.protocol('WM_DELETE_WINDOW',close)

    if '--smoke-test' in sys.argv:

        report=Path(sys.argv[sys.argv.index('--smoke-test')+1])

        def run_smoke():

            try: smoke(app,report)

            except Exception as exc: report.write_text(json.dumps({'error':str(exc)},ensure_ascii=False),encoding='utf-8')

            finally: close()

        root.after(2000,run_smoke)

    if '--silent-probe-report' in sys.argv:

        report=Path(sys.argv[sys.argv.index('--silent-probe-report')+1])

        def begin_probe():

            try:

                app.engine=Engine(controls=Controls(bypass=True),silent=True); app.engine.start()

                root.after(8000,end_probe)

            except Exception as exc:

                report.write_text(json.dumps({'error':str(exc)},ensure_ascii=False),encoding='utf-8'); close()

        def end_probe():

            if app.engine:

                app.engine.stop(); report.write_text(json.dumps(app.engine.stats(),ensure_ascii=False,indent=2),encoding='utf-8')

            close()

        root.after(100,begin_probe)

    if '--process-probe-report' in sys.argv:

        report=Path(sys.argv[sys.argv.index('--process-probe-report')+1])

        def process_probe():

            import time

            from process_audio import ProcessCaptureStream

            stream=None

            try:

                stream=ProcessCaptureStream(os.getpid(),6); until=time.perf_counter()+2; frames=0

                while time.perf_counter()<until:

                    if stream.get_read_available()>=480: stream.read(480); frames+=480

                    else: time.sleep(.001)

                result=dict(process_api_opened=True,frames=frames,channels=6,drops=stream.drops,stale=stream.stale,dongle_output=False,audio_recorded=False)

            except Exception as exc: result=dict(error=str(exc))

            finally:

                if stream: stream.close()

            report.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8'); close()

        root.after(100,process_probe)

    root.mainloop()



if __name__=='__main__': main()

