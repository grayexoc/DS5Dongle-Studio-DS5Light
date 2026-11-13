"""Explicit device checks in a modal dialog; idle application does no extra work."""
from thread_start import start_thread
import json
import os
import queue
import threading
import time
import tkinter as tk
from tkinter import ttk, filedialog
from ui_controls import RoundedCard
from pathlib import Path

from studio_i18n import text as tr
from studio_power import blocked
from device_diagnostics import (collect_snapshot, measure_reports, run_output_test,
                                with_selected_device, RUMBLE_TEST_MODES, audio_recovery_candidates,
                                finish_speaker_measurement)


TEST_NAMES = dict(haptic_left='왼쪽 햅틱', haptic_right='오른쪽 햅틱', speaker='스피커',
                  rumble_left='왼쪽 일반 진동', rumble_right='오른쪽 일반 진동',
                  rumble_both='양쪽 일반 진동', trigger_left='L2 저항', trigger_right='R2 저항')


class DeviceDiagnosticsDialog:
    def __init__(self, app):
        self.app = app
        self.busy = False
        self.closing = False
        self.cancel = threading.Event()
        self.results = queue.SimpleQueue()
        self.report = None
        self.timing = None
        self.job = None
        self.test_results = []
        self.last_test = None
        self.input_monitor=None
        self.input_job=None
        self.input_state=None
        self.window = tk.Toplevel(app.root)
        self.window.title(tr('장치 진단 시험'))
        self.window.transient(app.root)
        self.window.configure(bg='#101010')
        app.root.update_idletasks()
        self.window.geometry(f'980x790{app.root.winfo_x():+d}{app.root.winfo_y():+d}')
        self.window.minsize(920, 760)
        self.window.protocol('WM_DELETE_WINDOW', self.close)
        from studio_dialogs import _styles, _theme
        _styles(self.window)
        style=ttk.Style(self.window)
        style.configure('Diagnostic.TButton', background='#2b2b29', foreground='#eee9df', padding=(10,7), font=('맑은 고딕',10), borderwidth=1, relief='solid')
        style.layout('Diagnostic.TButton', [('Button.border', {'sticky':'nswe', 'children':[('Button.padding', {'sticky':'nswe','children':[('Button.label',{'sticky':'nswe'})]})]})])
        style.map('Diagnostic.TButton', background=[('disabled','#1e1e1d'),('active','#4c422b')], foreground=[('disabled','#77736a')], bordercolor=[('active','#d6ad52'),('!active','#595953')])
        self.window.bind('<Map>', lambda event: self.window.after_idle(
            lambda: _theme(self.window)) if event.widget is self.window else None, add='+')
        body = tk.Frame(self.window, bg='#101010', padx=16, pady=16)
        body.pack(fill='both', expand=True)
        body.columnconfigure(0,weight=1)
        body.rowconfigure(2,weight=1)
        self.identity_text = tk.StringVar(value=tr('상태 새로 고침으로 장치를 확인하세요.'))
        tk.Label(body, textvariable=self.identity_text, bg='#101010', fg='#d6ad52',
                 font=('맑은 고딕', 11, 'bold'), anchor='w').grid(row=0,column=0,sticky='ew')
        notice=RoundedCard(body,background='#101010',surface='#29251a',outline='#b59548',inset_x=12,inset_y=8,radius=7)
        notice.grid(row=1,column=0,sticky='ew',pady=(10,12))
        tk.Label(notice.content,text='ⓘ  '+tr('출력 시험 전 게임과 다른 앱의 Pico 오디오 출력을 중지하세요.'),
                 bg='#29251a',fg='#e7d49c',anchor='w',font=('맑은 고딕',10)).pack(fill='x')
        content = tk.Frame(body, bg='#101010')
        content.grid(row=2,column=0,sticky='nsew')
        content.columnconfigure(0, weight=3, uniform='diagnostics')
        content.columnconfigure(1, weight=2, uniform='diagnostics')
        content.rowconfigure(0, weight=1)
        left_host = self.card(content, '')
        left_host.grid(row=0, column=0, sticky='nsew', padx=(0, 12))
        left = left_host.content
        right = tk.Frame(content, bg='#101010')
        right.grid(row=0, column=1, sticky='nsew')
        self.diagram = tk.Canvas(left, height=205, bg='#151515', highlightthickness=0)
        self.diagram.pack(fill='both', expand=True, pady=(0, 8))
        self.diagram.bind('<Configure>', lambda _: self.draw_controller())
        self.buttons = []
        for title, actions in [
            ('∿ 햅틱', [('왼쪽', 'haptic_left'), ('오른쪽', 'haptic_right')]),
            ('≋ 일반 진동', [('왼쪽', 'rumble_left'), ('오른쪽', 'rumble_right'), ('양쪽', 'rumble_both')]),
            ('↗ 트리거', [('L2 저항', 'trigger_left'), ('R2 저항', 'trigger_right')]),
            ('♫ 스피커', [('스피커 시험', 'speaker')])]:
            row_host = self.card(left, '', inset=7)
            row_host.pack(fill='x', pady=4)
            row = row_host.content
            tk.Label(row, text=tr(title), bg='#151515', fg='#eee9df', font=('맑은 고딕',10,'bold'), width=11, anchor='w').pack(side='left')
            for label, kind in actions:
                button = ttk.Button(row, text=tr(label), style='Diagnostic.TButton',
                                    command=lambda k=kind: self.test(k), width=8)
                button.pack(side='left', fill='x', expand=True, padx=(4, 0))
                self.buttons.append(button)
            if title == '≋ 일반 진동':
                self.rumble_labels = tuple(
                    tr('클래식' if mode == 'classic' else '개선형') + f' · {strength}/255'
                    for mode, strength in RUMBLE_TEST_MODES)
                self.rumble_choice = ttk.Combobox(left, values=self.rumble_labels, state='disabled')
                self.rumble_choice.current(0)
                self.rumble_choice.pack(fill='x', pady=(0, 4))
        self.output_buttons=list(self.buttons)
        tk.Label(left, text=tr('각 시험 최대 2초 · 오디오햅틱 끔 프로필 필요'),
                 bg='#151515', fg='#aaa393', anchor='w').pack(fill='x', pady=(6, 0))
        state_host = self.card(right, tr('▣ 장치 상태'))
        state_host.pack(fill='x', pady=(0, 12))
        state = state_host.content
        self.state_text = tk.StringVar(value=tr('무선 연결 · 미확인'))
        self.state_values=[]
        for title in ('무선 연결','Pico 오디오 스트림','전송 오류 · 누적'):
            line=tk.Frame(state,bg='#151515');line.pack(fill='x',pady=7)
            tk.Label(line,text=tr(title),bg='#151515',fg='#eee9df',font=('맑은 고딕',10)).pack(side='left')
            var=tk.StringVar(value='—');self.state_values.append(var)
            tk.Label(line,textvariable=var,bg='#151515',fg='#d6ad52',font=('맑은 고딕',10,'bold')).pack(side='right')
            tk.Frame(state,bg='#383835',height=1).pack(fill='x')
        button = ttk.Button(state, text=tr('상태 새로 고침'), command=self.snapshot, style='Diagnostic.TButton')
        button.pack(fill='x', pady=(10, 0));self.buttons.append(button);self.snapshot_button=button
        self.speaker_meter_button = ttk.Button(state, text=tr('오디오 전송 5초 검사'),
            command=lambda:self.snapshot(measure_speaker=True), style='Diagnostic.TButton')
        self.speaker_meter_button.pack(fill='x', pady=(6,0));self.buttons.append(self.speaker_meter_button)
        button = ttk.Button(state, text=tr('Pico 오디오 연결 복구'), command=self.select_audio_output, style='Diagnostic.TButton')
        button.pack(fill='x', pady=(6,0));self.buttons.append(button)
        timing_host = self.card(right, tr('◷ 입력 수신 검사'))
        timing_host.pack(fill='both', expand=True)
        timing = timing_host.content
        button = ttk.Button(timing, text=tr('5초 검사 시작'), command=self.measure, style='Diagnostic.TButton')
        button.pack(fill='x');self.buttons.append(button);self.measure_button=button
        self.timing_text = tk.StringVar(value=tr('검사 후 입력 수신 결과를 표시합니다.'))
        tk.Label(timing, textvariable=self.timing_text, bg='#151515', fg='#d6ad52',
                 justify='left', anchor='w', wraplength=300).pack(fill='x', pady=12)
        metrics=tk.Frame(timing,bg='#151515');metrics.pack(fill='x',pady=(0,12))
        self.metric_values=[]
        for label in ('평균 수신 빈도','가장 긴 수신 간격'):
            cell=tk.Frame(metrics,bg='#151515');cell.pack(side='left',fill='x',expand=True)
            tk.Label(cell,text=tr(label),bg='#151515',fg='#eee9df',font=('맑은 고딕',9)).pack()
            value=tk.StringVar(value='—');self.metric_values.append(value)
            tk.Label(cell,textvariable=value,bg='#151515',fg='#d6ad52',font=('맑은 고딕',18,'bold')).pack(pady=(5,0))
        self.graph = tk.Canvas(timing, height=65, bg='#101010', highlightthickness=0)
        self.graph.pack(fill='x');self.graph.bind('<Configure>', lambda _: self.draw_intervals())
        tk.Label(timing, text=tr('PC에서 읽은 간격 · Bluetooth 지연과 다름'),
                 bg='#151515', fg='#aaa393', wraplength=290, justify='left').pack(anchor='w', pady=(8, 0))
        result_host = self.card(body, tr('✓ 시험 결과'), outline='#d6ad52')
        result_host.grid(row=3,column=0,sticky='ew',pady=(12,0))
        result = result_host.content
        self.status = tk.StringVar(value=tr('시험할 항목을 선택하세요.'))
        self.result_label=tk.Label(result, textvariable=self.status, bg='#151515', fg='#eee9df',
                 wraplength=820, justify='left', anchor='w',font=('맑은 고딕',10),pady=4)
        self.result_label.pack(fill='x')
        self.result_label.bind('<Configure>',lambda e:self.result_label.configure(wraplength=max(100,e.width-12)))
        row = tk.Frame(result, bg='#151515');row.pack(fill='x', pady=(8, 0))
        self.confirm_prompt=tk.StringVar(value=tr('실제 반응이 있었나요?'))
        tk.Label(row, textvariable=self.confirm_prompt, bg='#151515', fg='#aaa393').pack(side='left')
        self.confirm_buttons = []
        for label, felt in [('느껴짐', True), ('안 느껴짐', False)]:
            button = ttk.Button(row, text=tr(label), style='Diagnostic.TButton', state='disabled',
                                command=lambda value=felt: self.confirm_response(value))
            button.pack(side='left', padx=(8, 0));self.confirm_buttons.append(button)
        footer = tk.Frame(body, bg='#101010');footer.grid(row=4,column=0,sticky='ew',pady=(12,0))
        self.export_link = tk.Label(footer, text=tr('↓ 진단 로그 저장'), bg='#101010', fg='#aaa393',
                                    cursor='hand2', font=('맑은 고딕', 9, 'underline'), takefocus=True)
        self.export_link.pack(side='left')
        self.export_link.bind('<Button-1>', lambda _: self.export())
        self.export_link.bind('<Return>', lambda _: self.export())
        self.export_link.bind('<space>', lambda _: self.export())
        self.stop_button = ttk.Button(footer, text=tr('중지'), command=self.cancel.set,
                                      state='disabled', style='Diagnostic.TButton', width=10)
        self.stop_button.pack(side='right', padx=(8, 0))
        ttk.Button(footer, text=tr('닫기'), command=self.close,
                   style='Diagnostic.TButton', width=10).pack(side='right')
        self.update_test_buttons()
        from studio_settings_ui import FieldTip
        FieldTip(self.diagram,lambda:tr('XInput 모드에서는 입력 수신 검사를 사용할 수 없습니다.') if (self.report or {}).get('status',{}).get('usb_mode')=='XInput' else tr('버튼·스틱·트리거 입력 시 해당 부분을 강조합니다.'))
        FieldTip(self.speaker_meter_button, lambda:tr('Pico 스피커 처리 카운터의 증가량을 확인합니다. 버퍼 부족에는 시작·무음 처리도 포함됩니다.'))
        FieldTip(self.measure_button,lambda:tr('XInput 모드에서는 입력 수신 검사를 사용할 수 없습니다.')
                 if (self.report or {}).get('status',{}).get('usb_mode')=='XInput' else
                 tr('5초간 PC의 입력 수신 간격을 확인합니다.'))
        self.window.update_idletasks()
        # Reserve the footer and result before allowing the illustration to expand.
        minimum_height=max(760,self.window.winfo_reqheight())
        minimum_height=min(minimum_height,max(600,self.window.winfo_screenheight()-80))
        self.window.minsize(920,minimum_height)
        self.window.geometry(f'980x{max(790,minimum_height)}{app.root.winfo_x():+d}{app.root.winfo_y():+d}')
        self.window.grab_set()

    @staticmethod
    def card(parent, title, inset=14, outline='#474741'):
        box=RoundedCard(parent,background=parent.cget('bg'),surface='#151515',
                        outline=outline,inset_x=inset,inset_y=inset,radius=9)
        if title:
            tk.Label(box.content,text=title,bg='#151515',fg='#eee9df',
                     font=('맑은 고딕',12,'bold'),anchor='w').pack(fill='x',pady=(0,10))
        return box

    def draw_controller(self):
        c=self.diagram
        width,height=max(c.winfo_width(),1),max(c.winfo_height(),1)
        if not hasattr(self,'_controller_art'):
            from diagnostic_art import ControllerArt
            self._controller_art=ControllerArt(self.window)
        from diagnostic_art import active_parts
        signature=(width,height,active_parts(self.input_state))
        if getattr(self,'_controller_drawn',None)==signature:return
        self._controller_drawn=signature
        self._controller_image=self._controller_art.image(width,height,self.input_state)
        c.delete('all')
        c.create_image(width/2,height/2,image=self._controller_image)
        from diagnostic_art import active_parts
        parts=active_parts(self.input_state)
        image_width,image_height=self._controller_image.width(),self._controller_image.height()
        left,top=(width-image_width)/2,(height-image_height)/2
        for fraction,label in ((.24,'L2'),(.76,'R2')):
            x,y=left+image_width*fraction,top+max(9,image_height*.035)
            c.create_rectangle(x-17,y-9,x+17,y+9,fill='#d6ad52' if label in parts else '#151515',outline='#d6ad52')
            c.create_text(x,y,text=label,fill='#151515' if label in parts else '#d6ad52',font=('Segoe UI',9,'bold'))

    def draw_intervals(self):
        c = self.graph;c.delete('all')
        values = (self.timing or {}).get('intervals_ms', [])
        if len(values)<2:return
        step = max(1, len(values)//160)
        values = [max(values[i:i+step]) for i in range(0,len(values),step)]
        width, height = max(c.winfo_width(), 20), max(c.winfo_height(), 20)
        peak = max(max(values), .001)
        points = [coordinate for i,value in enumerate(values) for coordinate in
                  (5+i*(width-10)/(len(values)-1), height-5-value/peak*(height-10))]
        c.create_line(*points, fill='#d6ad52', width=1.5)

    def confirm_response(self, felt):
        if self.busy or self.last_test is None:return
        self.last_test['user_confirmed_response'] = felt
        self.status.set(tr('사용자 확인 · 반응 있음') if felt else tr('사용자 확인 · 반응 없음'))
        for button in self.confirm_buttons:button.configure(state='disabled')

    def available(self, kind):
        a = self.app
        if self.busy or a._closing or a._close_requested:return False
        if ((kind == 'test' and a.engine) or a._stopping or a.studio.busy or a.studio_settings.busy
                or getattr(a.studio_settings, 'recording', False) or blocked(a)):
            self.status.set(tr('DS5Light 오디오와 다른 장치 작업을 정지한 뒤 시도하세요.'))
            return False
        if kind != 'audio_outputs' and not a.studio.binding.snapshot().hid_path:
            self.status.set(tr('Pico를 먼저 조회하세요.'))
            return False
        return True

    def start(self, kind, operation):
        if not self.available(kind):return
        if not self.stop_input_monitor():
            self.status.set(tr('입력 조회 종료를 기다린 뒤 다시 시도하세요.'));return
        self.busy = True
        self.cancel.clear()
        for button in self.confirm_buttons:button.configure(state='disabled')
        identity = self.app.studio.binding.snapshot()
        for button in self.buttons:button.configure(state='disabled')
        self.stop_button.configure(state='normal')
        self.status.set(tr({'timing': '입력 수신 검사 중 · 5초간 기다리세요.',
                            'speaker_meter': '오디오 재생을 유지하고 5초간 기다리세요.'}.get(kind, '진단 작업 중…')))
        def work():
            try:
                binding = self.app.studio.binding
                started = time.monotonic()
                if kind == 'audio_outputs':
                    value = operation(None, identity)
                else:
                    value = with_selected_device(binding, identity,
                        lambda device:operation(device, identity), self.cancel)
                if kind == 'speaker_meter' and 'speaker_counters' in value and not self.cancel.wait(5):
                    try:
                        with_selected_device(binding, identity,
                            lambda device:finish_speaker_measurement(device, value,
                                (time.monotonic() - started + 1) * 1000, self.cancel.is_set), self.cancel)
                    except (OSError, RuntimeError, TimeoutError, ValueError) as exc:
                        value.setdefault('page_errors', {})['speaker_delta'] = str(exc)
                if kind in ('snapshot', 'speaker_meter') and binding.snapshot() != identity:
                    raise RuntimeError('선택한 Pico가 변경됐습니다. 상태를 다시 조회하세요.')
                self.results.put((kind, value, None))
            except Exception as exc:self.results.put((kind, None, str(exc)))
        start_thread(threading.Thread(target=work, name='DS5Light-device-diagnostics', daemon=True))
        self.job = self.window.after(100, self.poll)

    def snapshot(self, measure_speaker=False):
        stats = self.app.engine.stats() if self.app.engine else None
        self.start('speaker_meter' if measure_speaker else 'snapshot',
                   lambda device, identity:collect_snapshot(device, identity, stats, self.cancel.is_set))

    def measure(self):
        def operation(device, identity):
            # The XInput configuration HID has no gamepad input stream.
            from device_diagnostics import decode_status, tagged_command
            from studio_settings_protocol import SettingsClient
            status = decode_status(tagged_command(SettingsClient(device), 0x1e, 0))
            if status['usb_mode'] == 'XInput':
                raise RuntimeError(tr('XInput 설정 HID에는 입력 보고가 없습니다. DualSense 모드에서 측정하세요.'))
            result = measure_reports(device, self.cancel)
            from dataclasses import asdict
            result['device'] = asdict(identity)
            return result
        self.start('timing', operation)

    def select_audio_output(self):
        read_only = self.app.engine is not None
        def operation(device, identity):
            from audio import devices
            from windows_audio import snapshot
            inventory = snapshot(False, include_inactive=True)
            if read_only or not identity.hid_path:
                return dict(outputs=inventory['endpoints'], identity=identity, outcome='inventory')
            try:
                rows = [r for r in devices() if r.get('maxOutputChannels', 0) >= 4
                        and r.get('endpoint_id') and not r.get('isLoopbackDevice')]
            except (OSError, RuntimeError):
                return dict(outputs=inventory['endpoints'], identity=identity, outcome='inventory')
            outcome, rows = audio_recovery_candidates(identity, rows, inventory)
            return dict(outputs=rows, identity=identity, outcome=outcome)
        self.start('audio_outputs',operation)

    def show_audio_outputs(self, value):
        rows=value['outputs'];identity=value['identity']
        outcome=value.get('outcome', 'choose')
        binding=self.app.studio.binding
        if self.cancel.is_set():
            self.status.set(tr('검사 중지됨'))
            return
        if binding.snapshot()!=identity:
            self.status.set(tr('선택한 Pico가 변경됐습니다. 다시 연결을 확인하세요.'))
            return
        if outcome == 'inventory':
            self.status.set(tr('Windows 오디오 출력 목록을 열었습니다.'))
            dialog = tk.Toplevel(self.window)
            dialog.title(tr('Windows 오디오 출력'))
            dialog.transient(self.window)
            tk.Label(dialog, text=tr('Windows 장치 정보입니다. 출력 장치 설정은 변경하지 않습니다.'),
                     wraplength=550, justify='left').pack(fill='x', padx=12, pady=8)
            frame = ttk.Frame(dialog)
            frame.pack(fill='both', expand=True, padx=12)
            output_list = tk.Listbox(frame, width=70, height=min(10, max(1, len(rows))))
            output_list.pack(side='left', fill='both', expand=True)
            scroll = ttk.Scrollbar(frame, command=output_list.yview)
            scroll.pack(side='right', fill='y')
            output_list.configure(yscrollcommand=scroll.set)
            for row in rows:
                state = {1: '활성', 2: '비활성', 4: '장치 없음', 8: '연결 해제'}.get(row.get('state'), '미확인')
                channels = str(row['mix_channels']) if row.get('mix_channels') else '—'
                output_list.insert('end', f"{row.get('name') or row['id']} · {tr(state)} · {channels} ch")
            if not rows:
                output_list.insert('end', tr('조회된 Windows 오디오 출력이 없습니다.'))
            ttk.Button(dialog, text=tr('Windows 소리 설정'),
                       command=lambda:os.startfile('ms-settings:sound')).pack(pady=12)
            return

        def reconnect(row):
            if self.app.engine is not None:
                self.status.set(tr('DS5Light 오디오와 다른 장치 작업을 정지한 뒤 시도하세요.'))
                return
            if binding.confirm_output(row, allow_container_mismatch=True, expected_identity=identity):
                self.app.use_recovered_pico_output(row)
                self.status.set(tr('Pico 4채널 출력을 다시 연결했습니다. 왼쪽·오른쪽 햅틱 시험으로 확인하세요.'))
            else:
                self.status.set(tr('장치 연결 확인 실패 · 상태를 다시 조회하세요.'))
        if outcome=='matched':
            reconnect(rows[0])
            return
        if not rows:
            self.status.set(tr({
                'disabled': 'Pico 오디오 출력이 비활성화되어 있습니다. Windows 소리 설정에서 활성화한 뒤 다시 시도하세요.',
                'channels': 'Pico 오디오가 4채널 미만으로 구성되어 있습니다. Windows 스피커 구성을 4채널로 설정하세요.',
                'missing': 'Windows에서 Pico 오디오 출력을 찾지 못했습니다. Pico USB를 다시 연결하고 상태를 새로 고침하세요.',
                'unavailable': 'Windows 오디오 장치 상태를 읽지 못했습니다. 상태를 새로 고침하고 다시 시도하세요.',
            }.get(outcome, '4채널 출력 장치가 없습니다. Pico 오디오 장치 활성화와 Windows 스피커 구성을 확인하세요.')))
            return
        self.status.set(tr('Pico 오디오 출력을 하나로 확인할 수 없습니다. 아래 목록에서 확인하세요.'))
        dialog=tk.Toplevel(self.window);dialog.title(tr('Pico 오디오 출력 연결'))
        dialog.transient(self.window);dialog.configure(bg='#151515');dialog.grab_set()
        tk.Label(dialog,text=tr('선택한 Pico에 해당하는 4채널 출력을 선택하세요. 다른 컨트롤러나 서라운드 스피커를 선택하지 마세요. 연결 확인만 하며 시험음은 재생하지 않습니다.'),wraplength=480,justify='left',bg='#151515',fg='#eee9df').pack(padx=16,pady=12)
        labels=[f"{r['name']} · {r['endpoint_id']}" for r in rows]
        selected=tk.StringVar(value='')
        box=ttk.Combobox(dialog,textvariable=selected,values=labels,state='readonly',width=65)
        box.pack(padx=16,pady=8)
        def confirm():
            if selected.get() not in labels:return
            if binding.snapshot()!=identity:
                self.status.set(tr('선택한 Pico가 변경됐습니다. 다시 연결을 확인하세요.'));dialog.destroy();return
            row=rows[labels.index(selected.get())]
            reconnect(row)
            dialog.destroy()
        ttk.Button(dialog,text=tr('선택한 Pico의 출력으로 연결 확인'),command=confirm).pack(padx=16,pady=12)

    def test(self, kind):
        rumble_mode = self.rumble_choice.current() if kind.startswith('rumble_') else 0
        def operation(device, identity):
            row = None
            if kind.startswith('haptic_') or kind == 'speaker':
                from audio import devices
                from studio_slots import devices as studio_devices
                binding=self.app.studio.binding
                row=binding.match_output(devices(),studio_devices())
                current=binding.snapshot()
                if current.hid_path!=identity.hid_path or current.serial!=identity.serial:
                    raise RuntimeError(tr('선택한 Pico가 변경됐습니다. 상태를 다시 조회하세요.'))
                identity=current
            return run_output_test(device, kind, self.cancel, self.app.studio.binding, identity, row, rumble_mode)
        self.start('test', operation)

    def poll(self):
        self.job = None
        try:kind, value, error = self.results.get_nowait()
        except queue.Empty:
            self.job = self.window.after(100, self.poll)
            return
        self.busy = False
        for button in self.buttons:button.configure(state='normal')
        self.stop_button.configure(state='disabled')
        if error:
            self.last_test=None
            self.status.set(tr(error))
            if kind in ('snapshot', 'speaker_meter'):self.show(dict(diagnostic_error=error))
            self.test_results.append(dict(operation=kind,completed=False,error=error))
            self.test_results=self.test_results[-64:]
        else:
            if value is None:value={}
            if kind in ('snapshot', 'speaker_meter'):self.report = value
            elif kind == 'timing':self.timing = value
            if kind=='audio_outputs':self.show_audio_outputs(value)
            else:self.show(value)
            if kind == 'test':
                self.confirm_prompt.set(tr('왼쪽 2회와 오른쪽 3회가 모두 들렸나요?') if value.get('test')=='speaker' else tr('실제 반응이 있었나요?'))
                self.last_test = value if value.get('completed') else None
                if value.get('blocked_reason'):
                    self.test_results.append(value)
                    self.test_results=self.test_results[-64:]
                if self.last_test is not None:
                    self.test_results.append(value)
                    self.test_results = self.test_results[-64:]
                    for button in self.confirm_buttons:button.configure(state='normal')
                self.draw_controller()
                title = tr(TEST_NAMES.get(value.get('test'), ''))
                if 'rumble_mode' in value:
                    mode = tr('클래식' if value['rumble_mode'] == 'classic' else '개선형')
                    title += f" · {mode} · {value['rumble_strength']}/255"
                self.status.set(title + ' · ' + tr('전송 요청 완료 · 실제 반응을 확인하세요.')
                                if self.last_test else tr(value.get('blocked_reason', '시험 중지됨')))
            elif kind == 'timing':
                self.status.set(tr('입력 수신 검사 완료') if not value.get('cancelled') else tr('검사 중지됨'))
            elif kind == 'speaker_meter' and 'speaker_delta' in value:
                counts = value['speaker_delta']
                labels = ('PCM 폐기', '인코딩 실패', '버퍼 부족', '만료')
                keys = ('pcm_dropped', 'encode_failed', 'underrun', 'stale')
                self.status.set(tr('5초 증가량') + ' · ' + ' / '.join(
                    f'{tr(label)} {counts[key]}' for label, key in zip(labels, keys)))
            elif kind != 'audio_outputs':
                self.status.set(tr('검사 중지됨') if self.cancel.is_set() else
                                tr('상태 조회 실패') if value.get('diagnostic_error') else
                                tr('일부 진단 정보를 읽지 못했습니다. 진단 로그를 확인하세요.') if value.get('page_errors') else
                                tr('상태 조회 완료'))
        self.update_test_buttons()
        if self.closing:self.close()
        else:self.start_input_monitor()

    def update_test_buttons(self):
        status = (self.report or {}).get('status', {})
        has_hid = bool(self.app.studio.binding.snapshot().hid_path)
        allowed = (has_hid and not self.busy and self.app.engine is None and status.get('ready')
                   and status.get('auto_haptics')==0 and not status.get('audio_processing'))
        for button in self.output_buttons:
            button.configure(state='normal' if allowed else 'disabled')
        comparison = status.get('rumble_comparison', False)
        if not comparison:
            self.rumble_choice.current(0)
        self.rumble_choice.configure(state='readonly' if allowed and comparison else 'disabled')
        self.snapshot_button.configure(state='normal' if has_hid and not self.busy else 'disabled')
        self.speaker_meter_button.configure(state='normal' if has_hid and not self.busy
                                            and status.get('ready') and status.get('speaker_diagnostics') else 'disabled')
        self.measure_button.configure(state='disabled' if self.busy or not has_hid or status.get('usb_mode')=='XInput' else 'normal')

    def show(self, value):
        status = value.get('status')
        if status:
            mode = {0:tr('끔'),1:'Mix',2:'Replace'}.get(status.get('auto_haptics'), tr('미확인'))
            route = {'speaker': '스피커', 'headset': '헤드셋'}.get(status.get('output_route'))
            self.identity_text.set('DualSense · '+tr('연결됨' if status.get('connected') else '연결 해제')+
                                   '    |    '+str(status.get('usb_mode',''))+' · '+tr('오디오햅틱')+' '+mode+
                                   ('    |    '+tr(route) if route else ''))
            connected = tr('연결됨') if status.get('connected') else tr('연결 해제')
            stream = tr('사용 중') if status.get('audio_stream') else tr('사용 안 함')
            errors = value.get('transport',{}).get('send_error')
            self.state_text.set(tr('무선 연결')+'  '+connected+'\n'+tr('Pico 오디오 스트림')+'  '+stream+
                                '\n'+tr('전송 오류 · 누적')+'  '+(str(errors) if errors is not None else '—'))
            for var,text in zip(self.state_values,(connected,stream,str(errors) if errors is not None else '—')):var.set(text)
            self.update_test_buttons()
            self.start_input_monitor()
        if 'reports' in value:
            self.timing = value
            prefix = tr('검사 중지됨') if value.get('cancelled') else tr('측정 완료 · 입력 수신 확인') if value.get('reports') else tr('입력이 수신되지 않았습니다.')
            def number(key, suffix):
                return f"{value[key]:.1f} {suffix}" if value.get(key) is not None else '—'
            self.timing_text.set(prefix)
            for var,text in zip(self.metric_values,(number('hz','Hz'),number('max_ms','ms'))):var.set(text)
            self.draw_intervals()
        if value.get('diagnostic_error'):
            self.stop_input_monitor()
            self.state_text.set(tr('상태 조회 실패')+'\n'+tr(value['diagnostic_error']))
            self.identity_text.set(tr('상태 조회 실패'))
            for var in self.state_values:var.set(tr('미확인'))
            self.report=dict(value,status={})
            self.update_test_buttons()

    @staticmethod
    def json_value(value):
        if isinstance(value, bytes):return value.hex()
        raise TypeError(type(value).__name__)

    def export(self):
        if self.busy:return
        if self.report is None and self.timing is None and not self.test_results:
            self.status.set(tr('상태 조회 또는 시험을 먼저 실행하세요.'))
            return
        path = filedialog.asksaveasfilename(parent=self.window, defaultextension='.json',
                    initialfile='ds5light-device-diagnostics.json', filetypes=[('JSON', '*.json')])
        if not path:return
        try:
            Path(path).write_text(json.dumps(dict(snapshot=self.report, input_timing=self.timing, output_tests=self.test_results),
                ensure_ascii=False, indent=2, default=self.json_value), encoding='utf-8')
            self.status.set(tr('진단 파일 저장 완료 · 장치 식별 정보 포함'))
        except (OSError, TypeError) as exc:self.status.set(str(exc))

    def start_input_monitor(self):
        state=(self.report or {}).get('status',{})
        if self.busy or self.closing or self.input_monitor or not state.get('ready'):return
        if state.get('usb_mode')=='XInput':return
        identity=self.app.studio.binding.snapshot()
        if not identity.hid_path:return
        from studio_macro_tools import LiveMonitor
        self.input_identity=identity
        self.input_monitor=LiveMonitor(identity.hid_path,diagnostics=False)
        self.input_last_received=time.monotonic()
        self.input_monitor.start()
        self.input_job=self.window.after(80,self.poll_input)

    def stop_input_monitor(self):
        if self.input_job:
            self.window.after_cancel(self.input_job);self.input_job=None
        monitor=self.input_monitor
        if monitor:
            monitor.stop.set()
            if monitor.thread:monitor.thread.join(timeout=.2)
            if monitor.thread and monitor.thread.is_alive():return False
        self.input_monitor=None
        self.input_state=None
        return True

    def poll_input(self):
        self.input_job=None
        monitor=self.input_monitor
        if not monitor:return
        if self.app.studio.binding.snapshot()!=self.input_identity:
            self.input_failed(tr('장치가 변경되었습니다. 상태를 새로 고침하세요.'));return
        try:
            value=monitor.results.get_nowait()
            if value.get('error'):
                self.input_failed(tr(value['error']));return
            if value.get('received_at') is not None:self.input_last_received=value['received_at']
            self.input_state=value.get('input')
            self.draw_controller()
        except queue.Empty:pass
        if time.monotonic()-self.input_last_received>.5:
            self.input_failed(tr('입력 수신 중단 · 상태를 새로 고침하세요.'));return
        self.input_job=self.window.after(80,self.poll_input)

    def input_failed(self,message):
        self.status.set(message)
        self.show(dict(diagnostic_error=message))
        self.input_state=None
        self.draw_controller()

    def close(self):
        if not self.stop_input_monitor():
            self.window.after(100,self.close);return
        self.cancel.set()
        self.closing = True
        if self.busy:
            self.status.set(tr('시험 종료와 장치 정리를 기다리는 중…'))
            return
        if self.job:self.window.after_cancel(self.job)
        self.window.grab_release()
        self.window.destroy()
        self.app.device_diagnostics = None


def diagnostic_identity(app):
    identity = app.studio.binding.snapshot()
    return identity.hid_path, identity.serial


def update_diagnostics_button(app):
    button = getattr(app, 'device_diagnostics_button', None)
    if button is None or not button.winfo_exists():return
    support = getattr(app, '_diagnostics_support', None)
    same = support is not None and support['identity']==diagnostic_identity(app)
    pending = getattr(app, '_diagnostics_probe', False)
    disabled = pending or (same and support['supported'] is not True and bool(diagnostic_identity(app)[0]))
    state = 'disabled' if disabled else 'normal'
    if str(button.cget('state'))!=state:button.configure(state=state)
    app.device_diagnostics_hint = (tr('진단 지원 확인 중…') if pending else
        support['hint'] if same else tr('지원 펌웨어에서 장치 상태와 짧은 출력 시험을 확인합니다.'))


def open_diagnostics(app):
    current = getattr(app, 'device_diagnostics', None)
    if current is not None:
        current.window.lift()
        return
    if getattr(app, '_diagnostics_probe', False):return
    if app._closing or app._close_requested or app._stopping or app.studio.busy or app.studio_settings.busy or blocked(app):
        app.status.set(tr('다른 장치 작업이 끝난 뒤 시도하세요.'))
        return
    identity = app.studio.binding.snapshot()
    if not identity.hid_path:
        app.device_diagnostics = DeviceDiagnosticsDialog(app)
        app.device_diagnostics.select_audio_output()
        return
    from device_diagnostics import probe_support, DiagnosticsUnsupported
    app._diagnostics_probe = True
    update_diagnostics_button(app)
    results = queue.SimpleQueue()
    cancel = threading.Event()
    deadline = time.monotonic()+5
    def work():
        try:
            value = with_selected_device(app.studio.binding, identity,
                lambda device:probe_support(device,cancel.is_set),cancel)
            results.put((True,value,None))
        except DiagnosticsUnsupported as exc:results.put((False,None,str(exc)))
        except Exception as exc:results.put((None,None,str(exc)))
    def finish():
        if app._closing or app._close_requested:
            cancel.set();app._diagnostics_probe=False;return
        try:supported,value,error = results.get_nowait()
        except queue.Empty:
            if time.monotonic()<deadline:
                app.root.after(60,finish);return
            cancel.set();supported,value,error=None,None,tr('진단 지원 조회 시간 초과')
        app._diagnostics_probe=False
        if app.studio.binding.snapshot()!=identity:
            update_diagnostics_button(app);return
        if supported is True:
            app._diagnostics_support=dict(identity=diagnostic_identity(app),supported=True,
                hint=tr('장치 진단 시험 열기'))
            app.device_diagnostics = DeviceDiagnosticsDialog(app)
            from dataclasses import asdict
            app.device_diagnostics.report=dict(status=value,device=asdict(identity))
            app.device_diagnostics.show(app.device_diagnostics.report)
        else:
            hint = (tr('현재 펌웨어는 장치 진단을 지원하지 않습니다. 지원 펌웨어 적용 후 장치 목록을 새로 고침하세요.')
                    if supported is False else tr('진단 지원 확인 실패 · 장치 목록을 새로 고침한 뒤 다시 시도하세요.'))
            app._diagnostics_support=dict(identity=diagnostic_identity(app),supported=supported,hint=hint)
            app.status.set(hint+' '+tr(error or ''))
        update_diagnostics_button(app)
    start_thread(threading.Thread(target=work,name='DS5Light-diagnostics-support',daemon=True))
    app.root.after(60,finish)
