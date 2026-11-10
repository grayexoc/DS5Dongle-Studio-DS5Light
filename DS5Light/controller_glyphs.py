"""User-supplied DualSense sprite, rendered once per Tk interpreter/size.

Presentation only: names/firmware codes remain separate and unchanged.
"""
from studio_i18n import text as _ui_tr
from pathlib import Path
import tkinter as tk
from ui_controls import widget_trace
from ui_dpi import px,watch_scale

CARD='#151515';FG='#eee9df';MUTED='#aaa393';GOLD='#d6ad52';BORDER='#363126'
SOURCE=Path(__file__).resolve().parent/'assets'/'dualsense-controls.svg'
CROPS={
    _ui_tr('트라이앵글'):(0,0),_ui_tr('서클'):(42,0),_ui_tr('크로스'):(84,0),_ui_tr('스퀘어'):(126,0),
    'L1':(0,84),'R1':(42,84),'L2':(84,84),'R2':(126,84),
    'L3':(0,126),'R3':(0,210),_ui_tr('왼쪽 스틱'):(0,294),_ui_tr('오른쪽 스틱'):(0,378),
    _ui_tr('십자키 위'):(42,504),_ui_tr('십자키 아래'):(42,462),
    _ui_tr('십자키 왼쪽'):(84,462),_ui_tr('십자키 오른쪽'):(126,462),
    _ui_tr('터치패드 클릭'):(126,504),'Options':(0,630),'Create':(42,630),
}
ALIASES={'△':_ui_tr('트라이앵글'),'○':_ui_tr('서클'),'×':_ui_tr('크로스'),'□':_ui_tr('스퀘어'),
    '↑':_ui_tr('십자키 위'),'↓':_ui_tr('십자키 아래'),'←':_ui_tr('십자키 왼쪽'),'→':_ui_tr('십자키 오른쪽'),
    _ui_tr('방향 ↑'):_ui_tr('십자키 위'),_ui_tr('방향 ↓'):_ui_tr('십자키 아래'),_ui_tr('방향 ←'):_ui_tr('십자키 왼쪽'),_ui_tr('방향 →'):_ui_tr('십자키 오른쪽'),
    'Touch':_ui_tr('터치패드 클릭'),_ui_tr('터치 클릭'):_ui_tr('터치패드 클릭'),_ui_tr('터치 왼쪽'):_ui_tr('터치패드 왼쪽 클릭'),
    _ui_tr('터치 오른쪽'):_ui_tr('터치패드 오른쪽 클릭'),'PS':_ui_tr('PS 버튼'),'Mute':_ui_tr('마이크 버튼')}


def readable(value):return ALIASES.get(str(value),str(value))


def icon_key(value):
    name=readable(value)
    if name in CROPS:return name
    if _ui_tr('터치') in name:return _ui_tr('터치패드 클릭')
    for key in ('L1','R1','L2','R2','L3','R3'):
        if name.startswith(key):return key
    return None


def glyph(master,value,size=28):
    size=max(1,px(master,size))
    extra={_ui_tr('왼쪽 Fn'):'FN',_ui_tr('오른쪽 Fn'):'FN',
           _ui_tr('왼쪽 패들'):'LB',_ui_tr('오른쪽 패들'):'RB',_ui_tr('PS 버튼'):'PS',_ui_tr('마이크 버튼'):'Mute'}
    filename=extra.get(readable(value))
    if filename:
        root=master._root()
        if not hasattr(root,'_extra_controller_glyph_cache'):root._extra_controller_glyph_cache={}
        cache=root._extra_controller_glyph_cache;key=(filename,size)
        if key not in cache:
            try:
                root.tk.call('lappend','auto_path',str(SOURCE.parent.parent/'vendor'/'tksvg0.16'))
                root.tk.call('package','require','tksvg','0.16')
                cache[key]=tk.PhotoImage(master=root,data=(SOURCE.parent/'edge'/(filename+'.svg')).read_text(encoding='utf-8'),format=('svg','-scaletoheight',size))
            except (OSError,tk.TclError):cache[key]=None
        return cache[key]
    key=icon_key(value)
    if key is None:return None
    root=master._root()
    caches=getattr(root,'_controller_glyph_cache',None)
    if caches is None:root._controller_glyph_cache=caches={}
    if size not in caches:
        # Reuse the application's existing SVG dependency, no new package.
        root.tk.call('lappend','auto_path',str(SOURCE.parent.parent/'vendor'/'tksvg0.16'))
        try:
            root.tk.call('package','require','tksvg','0.16')
            svg=SOURCE.read_text(encoding='utf-8').replace('#0F0E17',CARD)
            atlas=tk.PhotoImage(master=root,data=svg,format=('svg','-scaletoheight',round(662*size/32)))
            scale=atlas.height()/662
            images={}
            for name,(x,y) in CROPS.items():
                if name in ('Options','Create'):
                    # The sprite's tiny English captions become noise at UI
                    # size; render only the button silhouette from the vector.
                    fragment=svg.replace('width="158" height="662" viewBox="0 0 158 662"',
                        f'width="{size}" height="{size}" viewBox="{x+10} {y+13} 12 18"',1)
                    images[name]=tk.PhotoImage(master=root,data=fragment,format=('svg','-scaletoheight',size))
                    continue
                image=tk.PhotoImage(master=root,width=size,height=size)
                left,top=round(x*scale),round(y*scale)
                right,bottom=min(left+size,atlas.width()),min(top+size,atlas.height())
                root.tk.call(str(image),'copy',str(atlas),'-from',left,top,right,bottom,'-to',0,0)
                images[name]=image
            caches[size]=images
        except (OSError,tk.TclError):
            # Missing/unsupported artwork never blocks editing or changes IDs.
            caches[size]={}
    return caches[size].get(key)


class GlyphStrip(tk.Frame):
    """Compact visual supplement. Complete names remain in adjacent text."""
    def __init__(self,parent,values=(),limit=5,background=CARD):
        super().__init__(parent,bg=background)
        self.background=background;self.limit=limit;self.signature=None
        self.set_values(values)
        watch_scale(self,self._scale_glyphs)

    def _scale_glyphs(self):
        values=self.signature;self.signature=None
        self.set_values(values or ())

    def set_values(self,values):
        values=tuple(values)
        if values==self.signature:return
        self.signature=values
        for child in self.winfo_children():child.destroy()
        for index,value in enumerate(values[:self.limit]):
            if index:tk.Label(self,text='+',bg=self.background,fg=MUTED).pack(side='left',padx=3)
            image=glyph(self,value,24)
            label=tk.Label(self,image=image,bg=self.background) if image else tk.Label(self,text=readable(value),bg=self.background,fg=FG,font=(_ui_tr('맑은 고딕'),9,'bold'))
            label.image=image;label.pack(side='left',padx=2)
        if len(values)>self.limit:tk.Label(self,text=f'+{len(values)-self.limit}',bg=self.background,fg=GOLD).pack(side='left',padx=4)


class ControllerChoice(tk.Frame):
    """Inline icon/name palette: no small native popup, modal, timer or HID.

    Values stay in the caller's original representation. Emit the same virtual
    event as a Combobox so existing selection handlers/recording keep working.
    """
    def __init__(self,parent,textvariable,values=(),state='readonly',multiple=False,selected=None,compact=False,**kw):
        super().__init__(parent,bg=CARD)
        self.variable=textvariable;self.values=tuple(values);self.enabled=state!='disabled'
        self.compact=compact;self.multiple=multiple;self.selected=selected;self.expanded=False;self.tiles=[];self.columns=0;self.active=0
        self.columnconfigure(0,weight=1,minsize=px(self,340) if compact else 0)
        self.heading=tk.Frame(self,bg='#111111',highlightbackground=BORDER,highlightcolor=BORDER,highlightthickness=1)
        self.heading.grid(row=0,column=0,sticky='ew');self.heading.columnconfigure(1,weight=1)
        self.preview=tk.Label(self.heading,bg='#111111',width=32,height=32)
        self.preview.grid(row=0,column=0,padx=(6,0))
        self.display=tk.StringVar()
        # Label-based header wraps long names and has no native dotted focus
        # rectangle. Explicit mouse/keyboard bindings retain accessibility.
        self.button=tk.Label(self.heading,textvariable=self.display,bg='#111111',fg=FG,
            disabledforeground='#666257',font=(_ui_tr('맑은 고딕'),10),anchor='w',justify='left',
            padx=8,pady=8,wraplength=260,takefocus=True,width=1,cursor='hand2')
        self.button.grid(row=0,column=1,sticky='ew')
        self.button.bind('<Button-1>',lambda _:self.toggle())
        self.button.bind('<space>',lambda _:self.toggle())
        self.arrow=tk.Label(self.heading,text='▾',bg='#111111',fg=GOLD,padx=8,cursor='hand2')
        self.arrow.grid(row=0,column=2,sticky='ns')
        for widget in (self.preview,self.arrow):widget.bind('<Button-1>',lambda _:self.toggle())
        for key,delta in (('<Down>',1),('<Right>',1),('<Up>',-1),('<Left>',-1)):
            self.button.bind(key,lambda e,d=delta:self.navigate(d))
        self.button.bind('<Return>',self.enter);self.button.bind('<Escape>',lambda _:self.collapse())
        self.panel=tk.Frame(self,bg=CARD,padx=4,pady=6)
        self.panel.bind('<Configure>',self.reflow)
        self.bind('<Configure>',self.reflow,add='+')
        widget_trace(self,self.variable,lambda *_:self.refresh())
        self.refresh()
        watch_scale(self,self._scale_choice)
        self._scale_choice()

    def _scale_choice(self):
        self.columnconfigure(0,minsize=px(self,340) if self.compact else 0)
        self.button.configure(padx=px(self,8),pady=px(self,8))
        self.arrow.configure(padx=px(self,8))
        self.panel.configure(padx=px(self,4),pady=px(self,6))
        if self.expanded:self.build_tiles()
        self.refresh()

    def configure(self,cnf=None,**kw):
        if cnf:kw.update(cnf)
        if 'values' in kw:
            values=tuple(kw.pop('values'))
            if values!=self.values:
                self.values=values;self.active=0
                if self.expanded:self.build_tiles()
        if 'state' in kw:
            self.enabled=kw.pop('state')!='disabled'
            if not self.enabled:self.collapse()
        kw.pop('justify',None);kw.pop('width',None)
        if kw:super().configure(**kw)
        if hasattr(self,'button'):self.refresh()
    config=configure

    def cget(self,key):
        if key=='values':return self.values
        if key=='state':return 'readonly' if self.enabled else 'disabled'
        return super().cget(key)

    def get(self):return self.variable.get()
    def set(self,value):self.variable.set(value)
    def current(self,index=None):
        if index is not None:self.variable.set(self.values[index])
        return self.values.index(self.get()) if self.get() in self.values else -1

    def refresh(self):
        value=self.get();self.display.set(readable(value))
        image=glyph(self,value)
        self.preview.configure(image=image if image else '',width=px(self,32) if image else 0,height=px(self,32) if image else 0)
        self.preview.image=image
        self.preview.grid() if image else self.preview.grid_remove()
        self.button.configure(state='normal' if self.enabled else 'disabled')
        self.arrow.configure(fg=GOLD if self.enabled else MUTED)
        self.paint_tiles()

    def toggle(self):
        if not self.enabled:return 'break'
        if self.expanded:return self.collapse()
        self.expanded=True;self.panel.grid(row=1,column=0,sticky='ew',pady=(4,0));self.arrow.configure(text='▴')
        self.build_tiles();self.button.focus_set();return 'break'

    def collapse(self):
        self.expanded=False;self.panel.grid_remove();self.arrow.configure(text='▾');return 'break'

    def build_tiles(self):
        for child in self.panel.winfo_children():child.destroy()
        self.tiles=[];self.columns=0
        for index,value in enumerate(self.values):
            image=glyph(self,value)
            button=tk.Button(self.panel,text=readable(value),image=image if image else '',compound='left',
                font=(_ui_tr('맑은 고딕'),10),anchor='w',justify='left',padx=px(self,9),pady=px(self,3 if self.compact else 7),width=1,wraplength=px(self,120),bg='#20201e',fg=FG,
                activebackground='#302819',activeforeground=GOLD,relief='flat',bd=0,
                highlightthickness=1,highlightbackground=BORDER,highlightcolor=GOLD,takefocus=0,
                command=lambda index=index:self.choose(index))
            button.image=image;self.tiles.append(button)
        self.reflow();self.paint_tiles()

    def reflow(self,event=None):
        if self.winfo_width()>1:
            self.button.configure(wraplength=max(px(self,80),self.winfo_width()-px(self,48 if self.preview.image else 12)-px(self,28)))
        if not self.expanded:return
        width=max(self.winfo_width(),self.panel.winfo_width())
        columns=3 if width>=px(self,620) else 2 if width>=px(self,340 if self.compact else 370) else 1
        # Text wraps within the actual tile width, including room for icons.
        # Recalculate on every width change even when column count is unchanged.
        tile_width=max(1,(width-px(self,8))//columns-px(self,6))
        for button in self.tiles:
            text_width=max(px(self,40),tile_width-px(self,24)-px(self,34 if button.image else 0))
            if str(button.cget('wraplength'))!=str(text_width):button.configure(wraplength=text_width)
        if columns==self.columns:return
        # Empty columns must leave the uniform group. Tk gives even zero-weight
        # columns a share of a uniform group, squeezing a one-column menu into
        # a fraction of its available width while wrapping for the full width.
        for i in range(3):
            self.panel.columnconfigure(i,weight=1 if i<columns else 0,
                                       uniform='controller_choices' if i<columns else '',minsize=0)
        for i in range(len(self.tiles)):self.panel.rowconfigure(i,minsize=0,uniform='')
        self.columns=columns
        for i,button in enumerate(self.tiles):
            self.panel.rowconfigure(i//columns,minsize=40 if self.compact else 54,uniform='controller_rows')
            button.grid(row=i//columns,column=i%columns,sticky='nsew',padx=3,pady=3)

    def paint_tiles(self):
        for index,(value,button) in enumerate(zip(self.values,self.tiles)):
            selected=self.selected(value) if self.selected else self.get()==value
            button.configure(bg='#302819' if selected else '#20201e',fg=GOLD if selected else FG,
                             highlightbackground=GOLD if selected or index==self.active else BORDER)

    def choose(self,index):
        if not self.enabled or not 0<=index<len(self.values):return 'break'
        self.active=index;self.variable.set(self.values[index])
        if not self.winfo_exists():return 'break'
        if not self.multiple:self.collapse()
        self.paint_tiles();self.button.focus_set()
        # A Studio selection handler may synchronously rebuild/destroy this
        # entire row. Do not touch child widgets after delivering the event.
        self.event_generate('<<ComboboxSelected>>')
        return 'break'

    def navigate(self,delta):
        if not self.expanded:self.toggle()
        elif self.values:self.active=(self.active+delta)%len(self.values);self.paint_tiles()
        return 'break'

    def enter(self,event=None):return self.choose(self.active) if self.expanded else self.toggle()
