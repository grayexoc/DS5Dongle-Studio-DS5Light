"""Theme-aware long numeric slider. No HID or background work."""
from studio_i18n import text as _ui_tr
import tkinter as tk
from studio_scope import trigger_display,trigger_raw
from ui_dpi import px,watch_scale
from localization import LANGUAGE

class RangeSlider(tk.Canvas):
    def __init__(self,parent,variable,low,high,enabled=True,marker=None,marker_label='',trigger=False,allowed=None,display_scale=1,reset_to_marker=False,tick_labels=None,**kw):
        super().__init__(parent,height=px(parent,48),width=px(parent,220),bg='#151515',highlightthickness=0,bd=0,takefocus=enabled,**kw)
        self.variable=variable;self.low=low;self.high=high;self.enabled=enabled
        self.marker=marker;self.marker_label=marker_label;self.trigger=trigger;self.allowed=allowed;self.display_scale=display_scale
        self.reset_to_marker=reset_to_marker
        self.tick_labels=tick_labels
        self.bind('<Configure>',self.draw)
        self.bind('<Button-1>',self.move);self.bind('<B1-Motion>',self.move)
        self.bind('<Left>',lambda e:self.step(-1));self.bind('<Right>',lambda e:self.step(1))
        self.trace=variable.trace_add('write',self.draw)
        self.bind('<Destroy>',self.cleanup)
        watch_scale(self,self._scale_slider)
    def _scale_slider(self):
        self.configure(height=px(self,48),width=px(self,220));self.draw()
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
        marker = self.display(self.marker) if self.marker is not None else None
        marker_caption = self.marker_label
        if LANGUAGE == 'en':
            marker_caption = {_ui_tr('추천'): 'REC. ', _ui_tr('기본'): 'DEF. '}.get(marker_caption, marker_caption)
        label_y = px(self,37)
        label_font = (_ui_tr('맑은 고딕'),8)
        labels = self.tick_labels or (f'{lo:g}', f'{hi:g}')
        ticks = []
        for index, label in enumerate(labels):
            fraction = index / (len(labels) - 1)
            anchor = 'w' if fraction == 0 else 'e' if fraction == 1 else 'center'
            endpoint_marker = marker is not None and not self.tick_labels and (
                (fraction == 0 and marker == lo) or (fraction == 1 and marker == hi))
            item = self.create_text(left + fraction * (right - left), label_y,
                                    text=f'{marker_caption}{label}' if endpoint_marker else label,
                                    anchor=anchor, fill=color if endpoint_marker and self.reset_to_marker else '#aaa393',
                                    font=label_font, tags='default_marker' if endpoint_marker else ())
            ticks.append(item)
        if marker is not None:
            mx = left + max(0,min(1,(marker-lo)/(hi-lo))) * (right-left)
            radius = px(self,1)
            dot_y = px(self,25)
            self.create_oval(mx-radius,dot_y-radius,mx+radius,dot_y+radius,
                             fill='#aaa393',outline='',tags='reference_dot')
            if not self.find_withtag('default_marker'):
                item = self.create_text(mx,label_y,text=f'{marker_caption}{marker:g}',
                                        fill=color if self.reset_to_marker else '#aaa393',
                                        font=label_font,tags='default_marker')
                start, _, end, _ = self.bbox(item)
                gap = px(self,4)
                # Move the caption away from nearby tick labels while keeping the mark on the track.
                shifts = []
                for first, second in zip(ticks, ticks[1:]):
                    minimum = self.bbox(first)[2] + gap - start
                    maximum = self.bbox(second)[0] - gap - end
                    if minimum <= maximum:
                        shifts.append(min(max(0,minimum),maximum))
                if shifts:
                    self.coords(item,mx + min(shifts,key=abs),label_y)
        self.create_oval(x-px(self,6),px(self,10),x+px(self,6),px(self,22),fill='#151515',outline=color,width=px(self,2))
    def move(self,event):
        if not self.enabled:return
        self.focus_set()
        if self.reset_to_marker and 'default_marker' in self.gettags('current'):
            if event.type==tk.EventType.ButtonPress:self.variable.set(f'{self.marker:g}')
            return
        if self.reset_to_marker and event.y>px(self,30):return
        lo,hi=self.limits();fraction=max(0,min(1,(event.x-px(self,12))/max(1,self.winfo_width()-px(self,24))))
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
