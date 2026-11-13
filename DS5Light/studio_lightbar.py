"""Local RGB palette and fixed-colour editor; no device I/O or timers."""
from studio_i18n import text as _ui_tr
import tkinter as tk
from localization import LANGUAGE
def ui_text(ko,en):return en if LANGUAGE=='en' else ko
from tkinter import ttk
from studio_range import RangeSlider
from ui_controls import widget_trace
from studio_dialogs import _show,_styles

BG='#151515';FG='#eee9df';GOLD='#d6ad52';MUTED='#aaa393'

def rgb_palette(parent,initial):
    owner=parent.winfo_toplevel();dialog=tk.Toplevel(owner);dialog.withdraw()
    dialog.title(ui_text(_ui_tr('듀얼센스 라이트바 색상'),'DualSense lightbar color'));dialog.configure(bg=BG);dialog.transient(owner);dialog.resizable(False,False)
    _styles(dialog);result=[None]
    box=tk.Frame(dialog,bg=BG,padx=18,pady=18);box.pack(fill='both',expand=True)
    values=[tk.StringVar(value=str((initial>>shift)&255)) for shift in (16,8,0)]
    preview=tk.Label(box,bg=f'#{initial:06X}',width=34,height=2,bd=1,relief='solid')
    preview.grid(row=0,column=0,columnspan=3,sticky='ew',pady=(0,10))
    caption=tk.StringVar(value=f'#{initial:06X}');hint=tk.StringVar()
    hex_bar=tk.Frame(box,bg=BG);hex_bar.grid(row=1,column=0,columnspan=3,sticky='ew')
    hex_entry=ttk.Entry(hex_bar,textvariable=caption,width=10,justify='left',style='Studio.TEntry')
    hex_entry.pack(side='left')
    tk.Label(hex_bar,textvariable=hint,bg=BG,fg=GOLD,anchor='w',width=1,height=2,
             wraplength=220,justify='left').pack(side='left',fill='x',expand=True,padx=(10,0))
    syncing=[False];hex_invalid=[False]
    def selected():
        channels=[int(v.get()) for v in values]
        if any(not 0<=v<=255 for v in channels):raise ValueError()
        return (channels[0]<<16)|(channels[1]<<8)|channels[2]
    def repaint(*_):
        if syncing[0]:return
        try:
            rgb=selected();preview.configure(bg=f'#{rgb:06X}')
            syncing[0]=True
            try:caption.set(f'#{rgb:06X}')
            finally:syncing[0]=False
            hex_invalid[0]=False;hint.set('')
        except (ValueError,tk.TclError):hint.set(_ui_tr('R · G · B는 각각 0~255로 입력하세요.'))
    def choose(rgb):
        syncing[0]=True
        try:
            for variable,shift in zip(values,(16,8,0)):variable.set(str((rgb>>shift)&255))
        finally:syncing[0]=False
        repaint()
    def enter_hex(*_):
        if syncing[0]:return
        text=caption.get().strip()
        if text.startswith('#'):text=text[1:]
        elif text.lower().startswith('0x'):text=text[2:]
        if len(text)!=6 or any(c not in '0123456789abcdefABCDEF' for c in text):
            hex_invalid[0]=True;hint.set(_ui_tr('#RRGGBB 형식의 색상값을 입력하세요.'));return
        hex_invalid[0]=False;choose(int(text,16))
    widget_trace(dialog,caption,enter_hex)
    swatches=tk.Frame(box,bg=BG);swatches.grid(row=2,column=0,columnspan=3,sticky='ew',pady=(10,14))
    colours=(0xff3333,0xff8800,0xffcc00,0x66cc33,0x00cc99,0x00cccc,0x3399ff,0x3366cc,
             0x6633cc,0x9933ff,0xcc33cc,0xff66aa,0xffffff,0xaaaaaa,0x555555,0x000000)
    for index,rgb in enumerate(colours):
        tk.Button(swatches,bg=f'#{rgb:06X}',activebackground=f'#{rgb:06X}',relief='flat',
                  highlightthickness=1,highlightbackground='#68645b',bd=0,width=4,height=1,
                  command=lambda rgb=rgb:choose(rgb)).grid(row=index//8,column=index%8,padx=2,pady=2,sticky='ew')
        swatches.columnconfigure(index%8,weight=1)
    for row,(name,variable) in enumerate(zip(('R','G','B'),values),3):
        tk.Label(box,text=name,bg=BG,fg=FG).grid(row=row,column=0,sticky='nw',pady=5)
        RangeSlider(box,variable,0,255).grid(row=row,column=1,sticky='ew',padx=10)
        ttk.Entry(box,textvariable=variable,width=4,justify='right',style='Studio.TEntry').grid(row=row,column=2,sticky='ne',pady=5)
        widget_trace(dialog,variable,repaint)
    box.columnconfigure(1,weight=1)
    bar=tk.Frame(box,bg=BG);bar.grid(row=6,column=0,columnspan=3,pady=(8,0))
    def confirm():
        if hex_invalid[0]:
            hint.set(_ui_tr('#RRGGBB 형식의 색상값을 입력하세요.'));hex_entry.focus_set();return
        try:result[0]=selected()
        except ValueError:repaint();return
        dialog.destroy()
    ttk.Button(bar,text=ui_text(_ui_tr('취소'),'Cancel'),style='Dialog.TButton',width=12,command=dialog.destroy).pack(side='left',padx=(0,8))
    accept=ttk.Button(bar,text=ui_text(_ui_tr('확인'),'OK'),style='Accent.Dialog.TButton',width=12,command=confirm);accept.pack(side='left')
    dialog.protocol('WM_DELETE_WINDOW',dialog.destroy);dialog.bind('<Escape>',lambda _:dialog.destroy())
    hex_entry.bind('<Return>',lambda _:confirm())
    repaint();_show(dialog,owner,accept)
    return result[0]

class LightbarUI:
    LIGHTING_FIELDS=('disable_pico_led','lightbar_off','lightbar_fixed','lightbar_rgb','player_led_mode','player_led_bright')

    def render_lighting(self):
        from studio_fields import FIELDS
        box=self.card(ui_text('조명','Lighting'))
        self.field_row(box,1,FIELDS['disable_pico_led'])
        title,controls,_=self.field_views['disable_pico_led']
        for child in title.winfo_children():
            if isinstance(child,tk.Label):child.configure(text='PICO LED')
        pico=controls[0];pico._lighting_inverse=True;raw=self.vars['disable_pico_led']
        pico.variable=tk.BooleanVar(master=pico,value=not bool(self.doc.values.get('disable_pico_led',1)))
        pico.command=lambda:raw.set(not pico.variable.get())
        tk.Label(box,text=ui_text('듀얼센스','DualSense'),bg=BG,fg=FG,font=(_ui_tr('맑은 고딕'),10,'bold')).grid(row=2,column=0,columnspan=2,sticky='w',pady=(12,4))
        children=tk.Frame(box,bg=BG);children.grid(row=3,column=0,columnspan=2,sticky='ew',padx=(18,0));children.columnconfigure(1,weight=1)
        self.field_row(children,0,FIELDS['lightbar_fixed'])
        title,controls,_=self.field_views['lightbar_fixed']
        for child in title.winfo_children():
            if isinstance(child,tk.Label):child.configure(text=ui_text('라이트바','Lightbar'))
        basic=controls[0];basic._lighting_default=True;basic.text=ui_text('기본','Default');basic.configure(width=basic.font.measure(basic.text)+30)
        basic.variable=tk.BooleanVar(master=basic)
        basic.command=lambda:self.set_lightbar_mode('default')
        for key,caption in [('lightbar_off',ui_text('끄기','Off')),('lightbar_rgb',None)]:
            host=tk.Frame(basic.master,bg=BG);host.pack(side='left',padx=(5,0))
            self.field_row(host,0,FIELDS[key]);self.field_views[key][0].grid_remove()
            control=self.field_views[key][1][0]
            if caption:
                control.text=caption;control.configure(width=control.font.measure(caption)+30)
                control.command=lambda:self.set_lightbar_mode('off' if self.vars['lightbar_off'].get() else 'default')
                control.draw()
        self.field_row(children,1,FIELDS['player_led_mode'])
        self.field_row(children,2,FIELDS['player_led_bright'])
        self.refresh_lighting()

    def refresh_lighting(self):
        views=getattr(self,'field_views',{})
        if 'disable_pico_led' in views:
            control=views['disable_pico_led'][1][0]
            if getattr(control,'_lighting_inverse',False):
                control.variable.set(not bool(self.doc.values.get('disable_pico_led',1)))
                control.text=ui_text('켜기','ON') if control.variable.get() else ui_text('끄기','OFF')
                control.configure(width=control.font.measure(control.text)+30);control.draw()
        basic=views.get('lightbar_fixed')
        if basic and getattr(basic[1][0],'_lighting_default',False):
            control=basic[1][0]
            control.variable.set(not self.doc.values.get('lightbar_fixed',0) and not self.doc.values.get('lightbar_off',0))
            control.draw()

    def set_lightbar_mode(self,mode):
        if self.busy or self.transfer_locked or 'lightbar_off' not in self.doc.values:return
        if 'lightbar_fixed' in self.doc.values:self.changed('lightbar_fixed',0)
        self.changed('lightbar_off',int(mode=='off'))
        self.refresh_read_values()

    def lightbar_colour_row(self,parent,row,field):
        key=field[1];valid=key in self.doc.values and self.enabled_for(key)
        title=self.option_title(parent,key,foreground=FG if valid else MUTED)
        title.grid(row=row,column=0,sticky='w',padx=(0,12),pady=8)
        variable=tk.StringVar(value=str(self.doc.values[key]) if key in self.doc.values else '')
        self.vars[key]=variable
        selection=tk.Frame(parent,bg=BG)
        selection.grid(row=row,column=1,sticky='e',pady=6)
        tk.Label(selection,text=ui_text('선택:','Select:'),bg=BG,fg=FG,font=(_ui_tr('맑은 고딕'),10)).pack(side='left',padx=(0,8))
        button=tk.Button(selection,command=self.choose_lightbar_colour,relief='flat',bd=0,
                         highlightthickness=1,highlightbackground='#68645b',padx=12,pady=3,
                         font=(_ui_tr('맑은 고딕'),10),state='normal' if valid and not self.busy else 'disabled')
        button.pack(side='left')
        def paint(*_):
            supported=getattr(self,'lightbar_supported',all(k in self.doc.values for k in ('lightbar_fixed','lightbar_rgb')))
            signature=(self.enabled_for(key),variable.get(),supported)
            if getattr(button,"_colour_signature",None)==signature:return
            button._colour_signature=signature
            if not signature[0]:
                supported=getattr(self,'lightbar_supported',all(k in self.doc.values for k in ('lightbar_fixed','lightbar_rgb')))
                try:text=f'#{int(variable.get()):06X}' if supported else '—'
                except ValueError:text='—'
                button.configure(text=text,bg='#242321',fg=MUTED,disabledforeground=MUTED);return
            try:rgb=int(variable.get())
            except ValueError:
                button.configure(text=ui_text(_ui_tr('미지원 · 펌웨어 확인 필요'),'Unsupported · check firmware'),bg='#242321',fg=MUTED);return
            colour=f'#{rgb:06X}';brightness=((rgb>>16)*299+((rgb>>8)&255)*587+(rgb&255)*114)/1000
            button.configure(text=colour,bg=colour,activebackground=colour,
                             fg='#111111' if brightness>140 else '#ffffff')
        button._paint_colour=paint
        widget_trace(button,variable,paint);paint()
        self.field_views[key]=(title,[button],[])
    def choose_lightbar_colour(self):
        if self.busy or not self.enabled_for('lightbar_rgb') or 'lightbar_rgb' not in self.doc.baseline:return
        path=self.path;stamp=self.profile_stamp
        colour=rgb_palette(self.parent,self.doc.values['lightbar_rgb'])
        if colour is None:return
        if self.path!=path or self.profile_stamp!=stamp or 'lightbar_rgb' not in self.doc.baseline:
            self.progress.configure(text=_ui_tr('프로필이 바뀌었습니다. 새로 고침 후 색상을 선택하세요.'));return
        self.changed('lightbar_fixed',1)
        self.changed('lightbar_off',0)
        self.changed('lightbar_rgb',colour)
        self.refresh_read_values()
