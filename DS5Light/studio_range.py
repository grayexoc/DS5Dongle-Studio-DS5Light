"""Theme-aware long numeric slider. No HID or background work."""
from studio_i18n import text as _ui_tr
import tkinter as tk
from studio_scope import trigger_display,trigger_raw
from ui_dpi import px,watch_scale

class RangeSlider(tk.Canvas):
    def __init__(self,parent,variable,low,high,enabled=True,marker=None,marker_label='',trigger=False,allowed=None,display_scale=1,**kw):
        super().__init__(parent,height=px(parent,64),width=px(parent,220),bg='#151515',highlightthickness=0,bd=0,takefocus=enabled,**kw)
        self.variable=variable;self.low=low;self.high=high;self.enabled=enabled
        self.marker=marker;self.marker_label=marker_label;self.trigger=trigger;self.allowed=allowed;self.display_scale=display_scale
        self.bind('<Configure>',self.draw)
        self.bind('<Button-1>',self.move);self.bind('<B1-Motion>',self.move)
        self.bind('<Left>',lambda e:self.step(-1));self.bind('<Right>',lambda e:self.step(1))
        self.trace=variable.trace_add('write',self.draw)
        self.bind('<Destroy>',self.cleanup)
        watch_scale(self,self._scale_slider)
    def _scale_slider(self):
        self.configure(height=px(self,64),width=px(self,220));self.draw()
    def cleanup(self,event):
        if event.widget is self:
            try:self.variable.trace_remove('write',self.trace)
            except tk.TclError:pass
    def display(self,value):return trigger_display(value) if self.trigger else value/self.display_scale
    def raw(self,value):return trigger_raw(value) if self.trigger else value*self.display_scale
    def limits(self):return (1,10) if self.trigger else (self.display(self.low),self.display(self.high))
    def draw(self,*_):
        if not self.winfo_exists():return
        self.delete('all');left=px(self,12);right=max(left+1,self.winfo_width()-px(self,12));lo,hi=self.limits()
        color='#d6ad52' if self.enabled else '#68645b'
        self.create_line(left,px(self,16),right,px(self,16),fill='#353128',width=px(self,5))
        try:value=self.display(float(self.variable.get()))
        except (ValueError,tk.TclError):value=lo
        x=left+max(0,min(1,(value-lo)/(hi-lo)))*(right-left)
        self.create_line(left,px(self,16),x,px(self,16),fill=color,width=px(self,5))
        if self.marker is not None:
            m=self.display(self.marker);mx=left+max(0,min(1,(m-lo)/(hi-lo)))*(right-left)
            self.create_line(mx,px(self,24),mx,px(self,27),fill='#aaa393',width=px(self,2))
            anchor='w' if mx<left+px(self,40) else 'e' if mx>right-px(self,40) else 'center'
            self.create_text(mx,px(self,55),text=f'{self.marker_label} {m:g}',fill='#aaa393',font=(_ui_tr('맑은 고딕'),8),anchor=anchor)
        self.create_text(left,px(self,34),text=f'{lo:g}',anchor='w',fill='#aaa393',font=(_ui_tr('맑은 고딕'),8))
        self.create_text(right,px(self,34),text=f'{hi:g}',anchor='e',fill='#aaa393',font=(_ui_tr('맑은 고딕'),8))
        self.create_oval(x-px(self,6),px(self,10),x+px(self,6),px(self,22),fill='#151515',outline=color,width=px(self,2))
    def move(self,event):
        if not self.enabled:return
        self.focus_set();lo,hi=self.limits();fraction=max(0,min(1,(event.x-px(self,12))/max(1,self.winfo_width()-px(self,24))))
        value=self.raw(lo+fraction*(hi-lo))
        if self.allowed:value=min(self.allowed,key=lambda v:abs(value-v))
        self.variable.set(f'{value:.2f}' if isinstance(self.low,float) or isinstance(self.high,float) else str(round(value)))
    def step(self,direction):
        if not self.enabled:return
        try:value=float(self.variable.get())
        except ValueError:return
        step=.01 if isinstance(self.low,float) or isinstance(self.high,float) else 1
        if self.trigger:direction=-direction
        value=max(self.low,min(self.high,value+direction*step))
        if self.allowed:
            candidates=[v for v in self.allowed if v>float(self.variable.get())] if direction>0 else [v for v in self.allowed if v<float(self.variable.get())]
            if not candidates:return
            value=min(candidates) if direction>0 else max(candidates)
        self.variable.set(f'{value:.2f}' if step<1 else str(round(value)))
