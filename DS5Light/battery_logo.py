"""SVG logo with a clipped battery pulse and a cached moving highlight."""
from studio_i18n import text as _ui_tr
import time
import tkinter as tk
from localization import LANGUAGE
from ui_dpi import px,watch_scale


class HoverHint:
    def __init__(self,widget,text):
        self.widget=widget;self.text=text;self.job=None;self.popup=None
        widget.bind('<Enter>',self._enter,add='+')
        widget.bind('<Leave>',self.hide,add='+')
        widget.bind('<ButtonPress>',self.hide,add='+')
        widget.bind('<Destroy>',self.hide,add='+')
    def _enter(self,event):
        self.hide();self.show()
    def show(self):
        self.job=None
        self.popup=tk.Toplevel(self.widget);self.popup.overrideredirect(True)
        self.popup.configure(bg='#363126')
        tk.Label(self.popup,text=self.text() if callable(self.text) else self.text,
                 bg='#24211b',fg='#eee9df',wraplength=390,justify='left',
                 font=(_ui_tr('맑은 고딕'),9),padx=9,pady=6).pack(padx=1,pady=1)
        self.popup.update_idletasks()
        x=min(self.widget.winfo_rootx()+self.widget.winfo_width()+12,
              max(0,self.widget.winfo_screenwidth()-self.popup.winfo_reqwidth()-8))
        y=max(0,min(self.widget.winfo_rooty()+(self.widget.winfo_height()-self.popup.winfo_reqheight())//2,
                    self.widget.winfo_screenheight()-self.popup.winfo_reqheight()-8))
        self.popup.geometry(f'+{x}+{y}')
    def hide(self,event=None):
        if self.job:
            self.widget.after_cancel(self.job);self.job=None
        if self.popup:
            self.popup.destroy();self.popup=None
    def update(self,text):
        if text==self.text:return
        self.text=text
        if self.popup:
            for child in self.popup.winfo_children():child.configure(text=text)


class BatteryLogo(tk.Canvas):
    SWEEP_MS=50
    SWEEP_SECONDS=1.4
    SWEEP_PAUSE_MS=2500
    PULSE_LEFT=406-62
    PULSE_RIGHT=864-62
    PULSE_HEIGHT=190-70
    SWEEP_COLORS=('#dbb76a','#e5c98b','#f0daa9','#fff0cb')

    def __init__(self,parent,path,background,height=64):
        svg=path.read_text(encoding='utf-8')
        self._svg=svg;self._logical_height=height;self._status=('waiting',None)
        height=px(parent,height)
        self.full=tk.PhotoImage(master=parent,data=svg,format=('svg','-scaletoheight',height))
        # Only the gold pulse becomes subdued when its status is unknown.
        # TkSVG ignores stroke-opacity on this gradient stroke. Gradient stop
        # opacity is rendered correctly, and changes only the pulse artwork.
        muted=svg.replace('stop-opacity="1"','stop-opacity="0.25"')
        self.unknown=tk.PhotoImage(master=parent,data=muted,format=('svg','-scaletoheight',height))
        super().__init__(parent,width=self.full.width(),height=self.full.height(),
                         bg=background,borderwidth=0,highlightthickness=0,takefocus=0)
        self._background=background;self._last=None;self._scale=height/188
        self._sweep_job=None;self._sweep_strip=None;self._sweep_sources=()
        self._sweep_item=None;self._sweep_cutoff=0
        self._focus_job=None
        self._window=self.winfo_toplevel()
        self._focus_bindings={event:self._window.bind(event,self._queue_focus_check,add='+')
                              for event in ('<FocusIn>','<FocusOut>')}
        self.bind('<Map>',self._start_sweep,add='+')
        self.bind('<Unmap>',self._stop_sweep,add='+')
        self.bind('<Destroy>',self._destroy_sweep,add='+')
        self.hint=HoverHint(self,_ui_tr('배터리 정보 조회 대기') if LANGUAGE=='ko' else 'Battery status pending')
        self.show_status('waiting',None)
        watch_scale(self,self._scale_logo)

    def _scale_logo(self):
        self._sweep_strip=None;self._sweep_sources=()
        height=px(self,self._logical_height)
        self.full=tk.PhotoImage(master=self,data=self._svg,format=('svg','-scaletoheight',height))
        muted=self._svg.replace('stop-opacity="1"','stop-opacity="0.25"')
        self.unknown=tk.PhotoImage(master=self,data=muted,format=('svg','-scaletoheight',height))
        self.configure(width=self.full.width(),height=self.full.height())
        self._scale=height/188;self._last=None
        self.show_status(*self._status)

    def show_status(self,state,value):
        self._status=(state,dict(value) if value is not None else None)
        key=(state,tuple(sorted(value.items())) if value else None)
        if key==self._last:return
        self._stop_sweep()
        self._last=key;self.delete('all')
        self._sweep_item=None;self._sweep_cutoff=0
        known=state=='ready' and value is not None
        self._display=self.full if known else self.unknown
        if known:
            percent=max(0,min(100,value['percent']))
            start=self.PULSE_LEFT*self._scale
            end=self.PULSE_RIGHT*self._scale
            self._sweep_cutoff=int(start+(end-start)*percent/100)
            # Keep the consumed part of the pulse visible at 25% opacity.
            # Both images have identical white typography and dimensions.
            if percent<100:
                # Full pulse range includes the decorative tail: SVG gradient
                # x2=864 is the completely faded right edge and represents 100%.
                self._display=self.unknown.copy()
                self.tk.call(self._display,'copy',self.full,'-from',0,0,self._sweep_cutoff,self.full.height(),
                             '-to',0,0,'-compositingrule','set')
            labels={0:(_ui_tr('사용 중'),'on battery'),1:(_ui_tr('충전 중'),'charging'),2:(_ui_tr('완충'),'full'),15:(_ui_tr('충전 오류'),'charging error')}
            label=labels.get(value['state'],(_ui_tr('상태 미확인'),'unknown status'))[0 if LANGUAGE=='ko' else 1]
            text=_ui_tr('배터리 {0}% · {1}').format(f'{percent}',f'{label}') if LANGUAGE=='ko' else f'Battery {percent}% · {label}'
        else:
            labels={'waiting':(_ui_tr('조회 대기'),'pending'),'multiple':(_ui_tr('대상 장치 미지정'),'select a Studio profile device'),
                    'disconnected':(_ui_tr('연결 없음'),'disconnected'),'no_data':(_ui_tr('정보 없음'),'no data'),'unavailable':(_ui_tr('조회 실패'),'unavailable')}
            label=labels.get(state,labels['unavailable'])[0 if LANGUAGE=='ko' else 1]
            text=(_ui_tr('배터리 정보 없음 · ') if LANGUAGE=='ko' else 'Battery unknown · ')+label
        self.create_image(0,0,image=self._display,anchor='nw')
        if known:
            self._sweep_item=self.create_image(0,0,anchor='nw',state='hidden')
            # Full-charge reference is visible only with a known percentage.
            # SVG x=864 is the 100% edge; keep the dot wholly inside it.
            radius=max(1.5,4*self._scale)
            x=(864-62)*self._scale-radius-1
            y=(130-70)*self._scale
            self.create_oval(x-radius,y-radius,x+radius,y+radius,
                             fill='#d6ad52',outline='',tags='battery-full-marker')
        self.hint.update(text)
        self._start_sweep()

    def _start_sweep(self,event=None):
        if (self._sweep_job is None and self._sweep_item is not None
                and self._sweep_cutoff>int(self.PULSE_LEFT*self._scale) and self._foreground()):
            self._sweep_job=self.after(self.SWEEP_PAUSE_MS,self._begin_sweep)

    def _foreground(self):
        try:
            if not self.winfo_viewable():return False
            # Native combobox popups have Tcl paths but no Python widget object.
            focus=self.tk.call('focus','-displayof',self._w)
            return bool(focus) and str(self.tk.call('winfo','toplevel',focus))==str(self._window)
        except tk.TclError:return False

    def _queue_focus_check(self,event):
        if self._focus_job is None:
            self._focus_job = self._window.after_idle(self._check_focus)

    def _check_focus(self):
        self._focus_job=None
        if self._foreground():self._start_sweep()
        else:self._stop_sweep()

    def _destroy_sweep(self,event):
        self._stop_sweep(event)
        if self._focus_job is not None:
            self._window.after_cancel(self._focus_job)
            self._focus_job = None
        for sequence,binding in self._focus_bindings.items():self._window.unbind(sequence,binding)

    def _stop_sweep(self,event=None):
        if self._sweep_job is not None:
            self.after_cancel(self._sweep_job)
            self._sweep_job=None
        if self._sweep_item is not None and (event is None or event.type!=tk.EventType.Destroy):
            self.itemconfigure(self._sweep_item,state='hidden')

    def _begin_sweep(self):
        self._sweep_job=None
        if not self._foreground():return
        if not self._sweep_sources:
            left=int(self.PULSE_LEFT*self._scale)
            height=round(self.PULSE_HEIGHT*self._scale)
            width=self.full.width()-left
            sources=[]
            for color in self.SWEEP_COLORS:
                bright=tk.PhotoImage(master=self,data=self._svg.replace('#d6ad52',color),
                                     format=('svg','-scaletoheight',self.full.height()))
                source=tk.PhotoImage(master=self,width=width,height=height)
                source.put(self._background,to=(0,0,width,height))
                self.tk.call(source,'copy',bright,'-from',left,0,left+width,height,
                             '-compositingrule','overlay')
                sources.append(source)
            self._sweep_sources=tuple(sources)
            self._sweep_strip=tk.PhotoImage(master=self,width=7*max(1,px(self,2)),height=height)
        self._sweep_started=time.monotonic()
        self._sweep_x=None
        self._sweep_frame()

    def _sweep_frame(self):
        self._sweep_job=None
        if not self._foreground():
            self._stop_sweep()
            return
        t=(time.monotonic()-self._sweep_started)/self.SWEEP_SECONDS
        if t>=1:
            self.itemconfigure(self._sweep_item,state='hidden')
            self._sweep_job=self.after(self.SWEEP_PAUSE_MS,self._begin_sweep)
            return
        # Cubic Bézier easing with evenly spaced time control points.
        eased=t*t*(3-2*t)
        left=int(self.PULSE_LEFT*self._scale)
        strip=self._sweep_strip
        band=strip.width()//7
        x=round(left-strip.width()+(self._sweep_cutoff-left+strip.width())*eased)
        self._sweep_job=self.after(self.SWEEP_MS,self._sweep_frame)
        if x==self._sweep_x:return
        self._sweep_x=x
        strip.blank()
        for index,level in enumerate((0,1,2,3,2,1,0)):
            start=max(left,x+index*band)
            end=min(self._sweep_cutoff,x+(index+1)*band)
            if start<end:
                self.tk.call(strip,'copy',self._sweep_sources[level],'-from',start-left,0,end-left,strip.height(),
                             '-to',start-x,0,'-compositingrule','set')
        self.coords(self._sweep_item,x,0)
        self.itemconfigure(self._sweep_item,image=strip,state='normal')
