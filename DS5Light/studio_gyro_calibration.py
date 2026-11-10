"""Explicit gyro calibration, ported from the Studio portal's final panel."""
from studio_i18n import text as _ui_tr
import math,tkinter as tk
from tkinter import ttk
from ui_controls import widget_trace

BG='#151515';FG='#eee9df';MUTED='#aaa393';GOLD='#d6ad52'

def counts_result(sent,observed,readings):
    observed=float(observed)
    if not math.isfinite(observed) or observed<=0:raise ValueError(_ui_tr('실제 회전각을 0보다 큰 숫자로 입력하세요.'))
    value=round(sent*360/observed)
    if not 500<=value<=50000:raise ValueError(_ui_tr('계산값이 500~50000 범위를 벗어났습니다. 게임 포커스와 가속 설정을 확인하세요.'))
    recorded=dict(readings);recorded[sent]=observed
    a=recorded.get(6500);b=recorded.get(3250);ratio=a/b if a and b else None
    return value,recorded,ratio

class GyroCalibration:
    def render_calibration(self):
        if not hasattr(self,'gyro_readings'):self.gyro_readings={};self.gyro_amount=6500;self.gyro_result=None;self.gyro_sensor_result=None;self.gyro_observed='180'
        device_ready = bool(self.path) and not self.busy
        mouse_ready = device_ready and int(self.doc.baseline.get('gyro_output', 0)) >= 1
        counts_enabled = self.enabled_for('flick_counts_360')
        box=self.card(_ui_tr('자이로 센서 보정'))
        tk.Label(box,text=_ui_tr('장치 연결 필요 · 자이로 출력 모드 무관'),bg=BG,fg=MUTED,wraplength=440,justify='left',anchor='w').grid(row=1,column=0,columnspan=2,sticky='ew',pady=(0,10))
        tk.Label(box,text=_ui_tr('측정 중 듀얼센스를 수평으로 잡고 오른쪽으로 한 바퀴(360°) 돌려 시작 방향으로 돌아오세요. 남은 시간에는 가만히 유지하고 2~3회 반복해 비교하세요. 반대 방향 움직임도 합산되므로 한 방향으로만 돌리세요.'),bg=BG,fg=MUTED,wraplength=440,justify='left',anchor='w').grid(row=2,column=0,columnspan=2,sticky='ew',pady=(0,10))
        ttk.Button(box,text=_ui_tr('360° 측정 · 8초'),command=self.measure_gyro,state='normal' if device_ready else 'disabled').grid(row=3,column=0,sticky='w')
        self.sensor_text=tk.StringVar(value=self.sensor_description());tk.Label(box,textvariable=self.sensor_text,bg=BG,fg=GOLD,wraplength=440,justify='left',anchor='w').grid(row=4,column=0,columnspan=2,sticky='ew',pady=10)
        ttk.Button(box,text=_ui_tr('보정값을 편집에 반영'),command=self.apply_sensor_trim,state='normal' if self.gyro_sensor_result and self.gyro_sensor_result['degrees']>=60 and device_ready else 'disabled').grid(row=5,column=0,columnspan=2,sticky='w')
        box=self.card(_ui_tr('게임의 360° 마우스 이동량'))
        tk.Label(box,text=_ui_tr('전송: 마우스 계열 출력 적용 필요. 반영: Flick Stick 또는 자이로 켬 + 마우스 + 자연 감도. 전송 후 3초 안에 게임으로 전환하세요.'),bg=BG,fg=MUTED,wraplength=440,justify='left',anchor='w').grid(row=1,column=0,columnspan=2,sticky='ew',pady=(0,10))
        actions=tk.Frame(box,bg=BG);actions.grid(row=2,column=0,columnspan=2,sticky='ew')
        for i,n in enumerate((6500,3250)):ttk.Button(actions,text=_ui_tr('{0} 전송').format(f'{n}')+(_ui_tr(' · 비교') if n==3250 else ''),command=lambda n=n:self.send_calibration(n),state='normal' if mouse_ready else 'disabled').grid(row=0,column=i,sticky='ew',padx=(0,8));actions.columnconfigure(i,weight=1)
        caption=tk.Frame(box,bg=BG);caption.grid(row=3,column=0,sticky='w',pady=12);tk.Label(caption,text=_ui_tr('실제 회전각'),bg=BG,fg=FG).pack(side='left');self.help_icon(caption,_ui_tr('게임 화면이 돌아간 각도를 직접 입력합니다. 이동량 × 360 ÷ 실제 회전각으로 계산합니다. 6500과 3250을 모두 측정해 회전각도 약 2:1인지 비교하세요.')).pack(side='left',padx=5)
        valuebox=tk.Frame(box,bg=BG);valuebox.grid(row=3,column=1,sticky='e');self.gyro_angle=tk.StringVar(value=self.gyro_observed)
        widget_trace(box,self.gyro_angle,lambda *_:setattr(self,'gyro_observed',self.gyro_angle.get()))
        ttk.Entry(valuebox,style='Studio.TEntry',textvariable=self.gyro_angle,width=4,justify='right').pack(side='left');tk.Label(valuebox,text='°',bg=BG,fg=MUTED).pack(side='left',padx=5)
        bar=tk.Frame(box,bg=BG);bar.grid(row=4,column=0,columnspan=2,sticky='ew')
        ttk.Button(bar,text=_ui_tr('회전각 기록·계산'),command=self.compute_calibration,state='disabled' if self.busy else 'normal').pack(side='left',padx=(0,8))
        ttk.Button(bar,text=_ui_tr('기록 초기화'),command=self.reset_calibration,state='disabled' if self.busy else 'normal').pack(side='left')
        self.calibration_text=tk.StringVar(value=self.calibration_description());tk.Label(box,textvariable=self.calibration_text,bg=BG,fg=GOLD,wraplength=440,justify='left',anchor='w').grid(row=5,column=0,columnspan=2,sticky='ew',pady=12)
        ttk.Button(box,text=_ui_tr('계산값을 편집에 반영'),command=self.apply_calibration,state='normal' if self.gyro_result is not None and device_ready and counts_enabled else 'disabled').grid(row=6,column=0,columnspan=2,sticky='w')
    def sensor_description(self):
        result=self.gyro_sensor_result
        if not result:return _ui_tr('아직 측정하지 않았습니다. 기본 보정값은 100입니다.')
        deg=result['degrees'];hz=result.get('hz');text=_ui_tr('측정 {0}° · 샘플 주파수 {1} Hz').format(f'{deg:.1f}',f"{(hz if hz else '미확인')}")
        if deg<60:return text+_ui_tr('\n회전량이 너무 작습니다. 한 바퀴를 돌려 다시 측정하세요.')
        error=(deg-360)/360*100;trim=100 if abs(error)<=5 else round(360/deg*100)
        return text+(_ui_tr('\n오차 {0}% · 보정값 {1}').format(f'{error:+.1f}',f'{trim}')+(_ui_tr(' 유지') if abs(error)<=5 else _ui_tr(' 제안')))
    def measure_gyro(self):
        if self.busy:return
        def run(client):
            client.read_one([0x83,'angle','u16','Angle','number',[0,65535]])
            for n in range(8,0,-1):
                self.results.put(('progress',_ui_tr('오른쪽으로 한 바퀴 돌린 뒤 정지 · {0}초').format(f'{n}'),None))
                if self.cancel.wait(1):raise RuntimeError(_ui_tr('측정 취소됨'))
            degrees=client.read_one([0x83,'angle','u16','Angle','number',[0,65535]])/10
            try:hz=client.read_one([0x85,'gyro_hz','u16','Gyro samples','number',[0,65535]])
            except (OSError,RuntimeError,TimeoutError,ValueError):hz=None
            return dict(degrees=degrees,hz=hz)
        self.task('gyro_measure',lambda:self.with_client(run))
    def show_gyro_result(self,result):
        self.gyro_sensor_result=result if isinstance(result,dict) else dict(degrees=result,hz=None)
    def apply_sensor_trim(self):
        if self.busy or not self.gyro_sensor_result:return
        deg=self.gyro_sensor_result['degrees']
        if deg<60:return
        value=100 if abs(deg-360)<=18 else round(360/deg*100)
        from studio_settings_protocol import encode
        from studio_fields import FIELDS
        try:encode(FIELDS['gyro_scale_trim_x100'],value)
        except ValueError as exc:self.progress.configure(text=str(exc));return
        self.changed('gyro_scale_trim_x100',value);self.render_fields()
    def send_calibration(self,n):
        if self.busy:return
        if int(self.doc.baseline.get('gyro_output',0))<1:self.progress.configure(text=_ui_tr('자이로 작동 기준을 마우스로 적용한 후 사용하세요.'));return
        def op(client):
            for seconds in range(3,0,-1):
                self.results.put(('progress',_ui_tr('게임으로 전환 · {0}초 후 {1}카운트 전송').format(f'{seconds}',f'{n}'),None))
                if self.cancel.wait(1):raise RuntimeError(_ui_tr('보정 신호 취소됨'))
            if client.command(1,bytes([0x86])+n.to_bytes(2,'little'))[2]!=0:raise RuntimeError(_ui_tr('보정 신호 전송 실패'))
            return n
        self.task('calibration_send',lambda:self.with_client(op))
    def calibration_sent(self,n):
        if n==6500:self.gyro_readings={};self.gyro_result=None
        self.gyro_amount=n
    def compute_calibration(self):
        if self.busy:return
        try:self.gyro_result,self.gyro_readings,_=counts_result(self.gyro_amount,self.gyro_angle.get(),self.gyro_readings)
        except ValueError as exc:self.calibration_text.set(str(exc));return
        self.render_fields()
    def calibration_description(self):
        readings=self.gyro_readings
        if not readings:return _ui_tr('현재 측정 이동량 {0} · 전송 후 게임 화면이 돌아간 각도를 입력하세요.').format(f'{self.gyro_amount}')
        text=_ui_tr('기록: ')+' · '.join(f'{n} → {v:g}°' for n,v in sorted(readings.items(),reverse=True))+_ui_tr('\n계산값 {0} 카운트/360°').format(f'{self.gyro_result}')
        a=readings.get(6500);b=readings.get(3250)
        if a and b:
            ratio=a/b
            text+=_ui_tr('\n회전각 비율 {0}:1 · ').format(f'{ratio:.2f}')+(_ui_tr('선형성 확인') if 1.8<ratio<2.2 else _ui_tr('차이 발생 · 마우스 가속·스무딩과 Windows 포인터 정확도 향상을 끄고 다시 측정하세요. 계산값이 과대할 수 있습니다.'))
        else:text+=_ui_tr('\n다른 이동량도 측정하세요. 6500의 회전각은 3250의 약 두 배여야 합니다.')
        return text
    def reset_calibration(self):
        if self.busy:return
        self.gyro_readings={};self.gyro_result=None;self.gyro_amount=6500;self.render_fields()
    def apply_calibration(self):
        if self.busy or self.gyro_result is None:return
        self.changed('flick_counts_360',self.gyro_result);self.render_fields()
