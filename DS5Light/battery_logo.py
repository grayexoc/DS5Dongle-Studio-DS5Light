"""Static SVG logo with a clipped pulse; updates only when battery data changes."""
from studio_i18n import text as _ui_tr
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
        self.hint=HoverHint(self,_ui_tr('배터리 정보 조회 대기') if LANGUAGE=='ko' else 'Battery status pending')
        self.show_status('waiting',None)
        watch_scale(self,self._scale_logo)

    def _scale_logo(self):
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
        self._last=key;self.delete('all')
        known=state=='ready' and value is not None
        self._display=self.full if known else self.unknown
        if known:
            percent=max(0,min(100,value['percent']))
            # Keep the consumed part of the pulse visible at 25% opacity.
            # Both images have identical white typography and dimensions.
            if percent<100:
                start=(406-62)*self._scale
                # Full pulse range includes the decorative tail: SVG gradient
                # x2=864 is the completely faded right edge and represents 100%.
                pulse_end=(864-62)*self._scale
                cutoff=start+(pulse_end-start)*percent/100
                self._display=self.unknown.copy()
                self.tk.call(self._display,'copy',self.full,'-from',0,0,int(cutoff),self.full.height(),
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
            # Full-charge reference is visible only with a known percentage.
            # SVG x=864 is the 100% edge; keep the dot wholly inside it.
            radius=max(1.5,4*self._scale)
            x=(864-62)*self._scale-radius-1
            y=(130-70)*self._scale
            self.create_oval(x-radius,y-radius,x+radius,y+radius,
                             fill='#d6ad52',outline='',tags='battery-full-marker')
        self.hint.update(text)
