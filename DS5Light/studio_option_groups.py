"""Presentation-only option groups; never normalize or write profile values."""
import tkinter as tk
from tkinter import ttk
from localization import LANGUAGE

def title(ko, en):
    return en if LANGUAGE == 'en' else ko

# (heading, fields, collapsed detail, require an enabled field)
PLANS = {
    'Gyro Aiming': [
        ('자이로 출력·작동 조건', 'Gyro output & activation', 'gyro_output gyro_mode', False, False),
        ('감도', 'Sensitivity', 'gyro_sens_mode gyro_sens gyro_sens_y gyro_natural_x10 gyro_natural_y_x10', False, True),
        ('방향·회전 보정', 'Direction & calibration', 'gyro_axis gyro_invert gyro_scale_trim_x100', True, True),
        ('Flick·게임 회전값', 'Flick & game rotation', 'flick_angle flick_counts_360', False, True)],
    'Stick to Mouse': [
        ('스틱 마우스', 'Stick mouse', 'stick_mouse', False, False),
        ('이동 속도', 'Movement speed', 'stick_mouse_sens stick_mouse_sens_y', False, True),
        ('세부 조정', 'Fine tuning', 'stick_mouse_deadzone stick_mouse_curve stick_mouse_invert', True, True)],
    'Touchpad as Mouse': [
        ('터치패드 마우스', 'Touchpad mouse', 'touch_mouse', False, False),
        ('', '', 'touch_mouse_sens touch_mouse_min touch_mouse_invert touch_mouse_trackball touch_mouse_friction', False, True)],
    'Auto-Haptics & Speaker Effect Leak': [
        ('오디오햅틱 모드', 'Audio haptics mode', 'auto_haptics_enable', False, False),
        ('', '', 'auto_haptics_gain auto_mute_mix auto_mute_replace mix_native_level mix_native_filter rumble_haptic_strength', False, True),
        ('주파수·반응 세부 조정', 'Frequency & response tuning', 'ah_dsp_source auto_haptics_smooth auto_haptics_gate auto_haptics_lowpass_hz auto_haptics_slope ah_xover_hz ah_low_gain ah_high_gain ah_highpass', True, True)],
    'General Haptics & Audio': [
        ('햅틱및 진동 세기', 'Haptics and rumble strength', 'haptics_gain rumble_gain rumble_mode rumble_release', False, False),
        ('스피커·헤드셋', 'Speaker & headset', 'speaker_gain speaker_volume headset_volume', False, False),
        ('음량 연동·음소거', 'Volume linking & mute', 'sync_spk_headset_volume lock_volume disable_speaker disable_mic', False, False)],
    'Rumble → Trigger': [
        ('그립 진동과 트리거 연동', 'Grip rumble to triggers', 'r2t_mode', False, False),
        ('전달 세기·조건', 'Strength & condition', 'r2t_strength r2t_on_press r2t_frequency', False, True)],
}

class OptionGroups:
    def render_option_groups(self, section, fields):
        plan = PLANS.get(section)
        if plan is None:
            return False
        available = {f[1]: f for f in fields}
        card_titles = {
            'Gyro Aiming': ('자이로', 'Gyro'),
            'Auto-Haptics & Speaker Effect Leak': ('오디오햅틱', 'Audio haptics'),
        }
        heading = card_titles.get(section, plan[0][:2])
        card = self.card(title(*heading))
        for index, (ko, en, names, detail, conditional) in enumerate(plan):
            keys = [key for key in names.split() if key in available]
            if not keys:
                continue
            # Waveform gain is independent of speaker controls.
            if section == 'General Haptics & Audio' and index == 1:
                card = self.card(title(ko, en))
            box = tk.Frame(card, bg='#151515')
            box.columnconfigure(0, weight=1)
            box.grid(row=index+1, column=0, columnspan=2, sticky='ew',
                     padx=(12 if conditional else 0, 0), pady=(6 if index else 0, 0))
            rows = []
            group_id = (section, ko)
            button = None
            if detail:
                button = ttk.Button(box, command=lambda g=group_id: self.toggle_option_group(g))
                button.grid(row=0, column=0, columnspan=2, sticky='w', pady=(0,6))
                button._group_title = title(ko, en)
            elif ko and index and conditional and len(keys) > 1:
                tk.Label(box, text=title(ko, en), bg='#151515', fg='#aaa393',
                         anchor='w').grid(row=0, column=0, columnspan=2, sticky='w', pady=(0,4))
            for n, key in enumerate(keys, 2):
                if key == 'mix_native_filter' and 'mix_native_level' in keys:
                    continue
                row = tk.Frame(box, bg='#151515')
                row.columnconfigure(0, weight=1)
                row.grid(row=n, column=0, columnspan=2, sticky='ew')
                self.field_row(row, 0, available.pop(key))
                rows.append((key, row))
                if key == 'mix_native_level' and 'mix_native_filter' in available:
                    leak = tk.Frame(row, bg='#151515')
                    leak.grid(row=0,column=2,padx=(12,0),sticky='e')
                    self.field_row(leak,0,available.pop('mix_native_filter'),
                                   title_text=title('누설 억제','Leak suppression'),dropdown_width=6)
            self._option_groups.append((group_id, rows, button, conditional, box))
        if section in ('Gyro Aiming', 'Touchpad as Mouse'):
            label = tk.Label(card, bg='#151515', fg='#e0a030', justify='left', anchor='w', wraplength=440)
            label.grid(row=len(plan)+1, column=0, columnspan=2, sticky='ew', pady=(4,0))
            self._touch_gyro_notices.append(label)
        # New firmware fields must remain accessible without changing this plan.
        if available and section != 'Rumble → Trigger':
            self.render_additional_fields(available.values())
        return True

    def render_additional_fields(self, fields):
        box = self.card(title('추가 설정', 'Additional settings'))
        for row, field in enumerate(fields, 1):
            self.field_row(box, row, field)

    def toggle_option_group(self, group_id):
        self._open_option_groups.symmetric_difference_update({group_id})
        self.refresh_option_groups()

    def refresh_option_groups(self):
        for group_id, rows, button, conditional, box in getattr(self, '_option_groups', ()):
            opened = button is None or group_id in self._open_option_groups
            available = not conditional or any(self.enabled_for(key) for key, _ in rows)
            if available or any(key in self.invalid for key, _ in rows):
                box.grid()
            else:
                box.grid_remove()
            if button is not None:
                button.configure(text=('▾ ' if opened else '▸ ') + button._group_title)
            for key, row in rows:
                show = opened and (not conditional or self.enabled_for(key))
                if key in ('auto_mute_mix','auto_mute_replace'):
                    show=opened and self.doc.values.get('auto_haptics_enable')== (1 if key=='auto_mute_mix' else 2)
                # Keep invalid edits accessible, even after changing the mode.
                if show or key in self.invalid:
                    row.grid()
                else:
                    row.grid_remove()
        values = self.doc.values
        notice = ''
        if values.get('touch_mouse'):
            if values.get('gyro_mode') == 3:
                notice = title('터치 중 자이로도 작동합니다. 자이로 출력이 마우스면 손가락과 자이로 이동이 합산됩니다.',
                               'Touch also activates gyro. With mouse output, finger and gyro movement are added.')
            elif values.get('gyro_mode') == 4:
                notice = title('터치하는 동안 자이로가 일시 정지합니다.',
                               'Touch pauses gyro while the finger is on the pad.')
        for label in getattr(self, '_touch_gyro_notices', ()):
            if notice:
                label.configure(text=notice)
                label.grid()
            else:
                label.grid_remove()
        self.sync_scrollregion()
