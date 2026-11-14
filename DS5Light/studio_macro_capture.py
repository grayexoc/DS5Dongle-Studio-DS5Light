"""Temporary input capture inside the macro editor; no hooks or extra windows."""
from studio_i18n import text as _ui_tr
import queue
import tkinter as tk
from tkinter import ttk
from studio_macro_tools import LiveMonitor

class InlineCapture:
    def build_capture(self,parent,row):
        self.capture=None;self.capture_job=None;self.capture_monitor=None
        self.capture_frame=tk.Frame(parent,bg='#242018',padx=10,pady=10)
        self.capture_frame.grid(row=row,column=0,columnspan=2,sticky='ew',pady=(10,0));self.capture_frame.columnconfigure(0,weight=1)
        self.capture_text=tk.StringVar()
        tk.Label(self.capture_frame,textvariable=self.capture_text,bg='#242018',fg='#eee9df',wraplength=450,justify='left',anchor='w').grid(row=0,column=0,sticky='ew')
        ttk.Button(self.capture_frame,text=_ui_tr('지정'),command=self.keep_capture,width=6).grid(row=0,column=1,padx=6)
        ttk.Button(self.capture_frame,text=_ui_tr('취소'),command=self.stop_capture,width=6).grid(row=0,column=2)
        self.capture_frame.grid_remove()
        self.dialog.bind('<KeyPress>',self.capture_down,add='+');self.dialog.bind('<KeyRelease>',self.capture_up,add='+')
    def start_capture(self,mode):
        from studio_power import blocked
        if blocked(self.ui.app):return
        self.stop_capture()
        if mode!='keys' and (not self.ui.path or self.ui.busy):
            self.feedback.set(_ui_tr('Pico 설정을 먼저 읽어 연결을 확인하세요.'));return
        self.capture={'mode':mode,'mask':0,'output':None,'pressed':[],'released':[]}
        self.capture_text.set(_ui_tr('키를 최대 4개 눌렀다 떼고 지정하세요.') if mode=='keys' else _ui_tr('버튼을 누른 뒤 지정하세요. 기존 매핑이 숨긴 입력은 기록되지 않을 수 있습니다.'))
        self.capture_frame.grid();self.dialog.focus_set()
        if mode!='keys':
            self.ui.stop_live();self.capture_monitor=LiveMonitor(self.ui.path,diagnostics=False)
            try:self.capture_monitor.start()
            except Exception as exc:
                self.stop_capture();self.feedback.set(_ui_tr('입력 확인 시작 실패 · ')+str(exc));return
            self.poll_capture()
        self.fit_dialog()
    def poll_capture(self):
        self.capture_job=None
        if not self.capture or not self.capture_monitor or self.closed:return
        try:
            result=self.capture_monitor.results.get_nowait()
            if result.get('error'):
                self.capture_text.set(_ui_tr('조회 실패 · ')+result['error']);self.capture_monitor.stop.set();return
            snapshot=result.get('input');mask=snapshot['mask'] if snapshot else 0
            if mask:
                if self.capture['mode']=='output':
                    # Firmware out_btn stores one controller output, not a chord.
                    mapping={0:19,1:20,2:21,3:22,4:3,5:1,6:2,7:4,8:5,9:6,10:9,11:10,12:16,13:17,14:7,15:8,17:18}
                    candidates=[out for bit,out in mapping.items() if mask&(1<<bit)]
                    if mask.bit_count()==1 and len(candidates)==1:
                        self.capture['output']=candidates[0];self.capture_text.set(self.OUT_BUTTONS[candidates[0]])
                    else:
                        self.capture['output']=None;self.capture_text.set(_ui_tr('출력으로 사용할 지원 버튼 하나만 누르세요. 듀얼센스 출력은 단일 버튼입니다.'))
                elif mask.bit_count()>=self.capture['mask'].bit_count():
                    self.capture['mask']=mask;self.capture_text.set(' + '.join(n for i,n in enumerate(self.BUTTONS) if mask&(1<<i)))
        except queue.Empty:pass
        self.capture_job=self.dialog.after(100,self.poll_capture)
    def capture_code(self,event):
        aliases={'Control_L':'Ctrl','Shift_L':'Shift','Alt_L':'Alt','Super_L':'Win','Control_R':'RightCtrl','Shift_R':'RightShift','Alt_R':'RightAlt','Super_R':'RightWin','Return':'Enter','Escape':'Esc','BackSpace':'Backspace','space':'Space','minus':'Minus','equal':'Equal','bracketleft':'LeftBracket','bracketright':'RightBracket','backslash':'Backslash','semicolon':'Semicolon','apostrophe':'Quote','grave':'Grave','comma':'Comma','period':'Period','slash':'Slash','Caps_Lock':'CapsLock','Prior':'PageUp','Next':'PageDown','Print':'PrintScreen','Scroll_Lock':'ScrollLock','Num_Lock':'NumLock',**{'KP_'+str(i):'KP'+str(i) for i in range(10)},'KP_Divide':'KPDivide','KP_Multiply':'KPMultiply','KP_Subtract':'KPSubtract','KP_Add':'KPAdd','KP_Enter':'KPEnter','KP_Decimal':'KPDecimal'}
        return self.HID_KEYS.get(aliases.get(event.keysym,event.keysym.upper() if len(event.keysym)==1 else event.keysym))
    def capture_down(self,event):
        if not self.capture or self.capture['mode']!='keys':return
        c=self.capture_code(event);pressed=self.capture['pressed']
        if c and c not in pressed and len(pressed)<4:pressed.append(c)
        self.capture_text.set(' + '.join(next((k for k,v in self.HID_KEYS.items() if v==c),str(c)) for c in pressed) or _ui_tr('지원하는 키를 눌러 주세요.'))
        return 'break'
    def capture_up(self,event):
        if not self.capture or self.capture['mode']!='keys':return
        c=self.capture_code(event)
        if c in self.capture['pressed'] and c not in self.capture['released']:self.capture['released'].append(c)
        return 'break'
    def keep_capture(self):
        state=self.capture
        if not state:return
        if state['mode']=='keys' and not state['pressed'] or state['mode']=='input' and not state['mask'] or state['mode']=='output' and state['output'] is None:
            self.capture_text.set(_ui_tr('지정할 입력을 먼저 눌러 주세요.'));return
        self.stop_capture()
        if state['mode']=='keys':
            pressed,released=state['pressed'],state['released']
            for i,var in enumerate(self.keys):var.set(next((k for k,v in self.HID_KEYS.items() if v==(pressed+[0]*4)[i]),_ui_tr('없음')))
            order=[pressed.index(c) for c in released if c in pressed]+[i for i in reversed(range(4)) if i>=len(pressed) or pressed[i] not in released]
            self.release.set(str(sum(v<<(2*i) for i,v in enumerate(order[:4]))))
        elif state['mode']=='output':self.output.set(self.OUT_BUTTONS[state['output']])
        else:
            for i,var in enumerate(self.buttons):var.set(bool(state['mask']&(1<<i)))
        self.feedback.set(_ui_tr('입력을 지정했습니다. 완료 · Pico 저장을 누르면 저장합니다.'))
    def stop_capture(self):
        if getattr(self,'capture_monitor',None):self.capture_monitor.stop.set();self.capture_monitor=None
        if getattr(self,'capture_job',None):
            try:self.dialog.after_cancel(self.capture_job)
            except tk.TclError:pass
        self.capture_job=None;self.capture=None
        if hasattr(self,'capture_frame') and self.capture_frame.winfo_exists():self.capture_frame.grid_remove()
        if hasattr(self,'footer') and not self.closed:self.fit_dialog()
