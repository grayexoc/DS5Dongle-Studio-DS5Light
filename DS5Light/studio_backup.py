"""Explicit slot backup/restore jobs. Excluded experimental fields are never written."""
from studio_i18n import text as _ui_tr
from studio_scope import EDITABLE

# Custom effect records are excluded, so their enable flags must be excluded too.
FIELDS = {key: field for key, field in EDITABLE.items() if not key.startswith('ce_')}
from studio_scope import LIGHTBAR_FIELDS,RUMBLE_FIELDS,USB_MODE_FIELDS,RUMBLE_MODE_FIELDS,OPTIONAL_FIELDS,config_version
from studio_settings_protocol import USBModeUnsupported,RumbleModeUnsupported,encode,validate_changes
from studio_records import effect_states,macro_records

# The slot wire command reads flash directly. Missing legacy tails are
# filled with 0xFF; use the defaults from the firmware's config validation.
_SLOT_DEFAULTS = {
    'auto_haptics_enable': 0, 'auto_haptics_gain': 100, 'auto_haptics_smooth': 40,
    'auto_haptics_gate': 20, 'mix_native_level': 0, 'mix_native_filter': 1,
    'ah_dsp_source': 0, 'auto_haptics_lowpass_hz': 60, 'ah_low_gain': 100,
    'ah_high_gain': 100, 'auto_haptics_slope': 12, 'auto_mute_replace': 1,
    'auto_mute_mix': 0, 'rumble_haptic_strength': 100, 'haptics_gain': 1.0,
    'speaker_volume': 100, 'headset_volume': 100, 'speaker_gain': 2,
    'sync_spk_headset_volume': 1, 'lock_volume': 0, 'disable_mic': 0,
    'disable_speaker': 0, 'controller_mode': 2, 'polling_rate_mode': 0,
    'audio_buffer_length': 64, 'inactive_time': 30, 'disable_inactive_disconnect': 0,
    'disable_pico_led': 0, 'lightbar_off': 0, 'lightbar_fixed': 0,
    'player_led_mode': 0, 'player_led_bright': 0, 'enable_wake': 0,
    'rumble_gain': 100, 'rumble_release': 0, 'rumble_mode': 0, 'haptics_aa': 1, 'trigger_reduce': 0,
    'r2t_mode': 0, 'r2t_on_press': 0, 'r2t_strength': 100, 'r2t_frequency': 60,
    'synth_force': 0, 'gyro_mode': 0, 'gyro_sens': 50, 'gyro_axis': 0,
    'gyro_invert': 0, 'gyro_sens_y': 0, 'gyro_output': 0, 'flick_angle': 90,
    'flick_counts_360': 6500, 'gyro_sens_mode': 1, 'gyro_natural_x10': 10,
    'gyro_natural_y_x10': 0, 'gyro_scale_trim_x100': 100, 'rstick_invert': 0,
    'stick_mouse': 0, 'stick_mouse_sens': 0, 'stick_mouse_sens_y': 0,
    'stick_mouse_deadzone': 8, 'stick_mouse_curve': 18, 'stick_mouse_invert': 0,
}

_SLOT_DEFAULTS['ps_shortcut_enabled']=0

_SLOT_DEFAULTS.update({'at_mode': 0, 'at_strength': 70, 'at_threshold': 30, 'at_start_pos': 0, 'at_shape': 0, 'at_strength_b': 70, 'at_detent_pos': 5, 'at_pushback': 0, 'at_kick_style': 0, 'at_pushback_freq': 35, 'at_l2_mode': 0, 'at_l2_strength': 70, 'at_l2_threshold': 30, 'at_l2_start_pos': 0, 'at_l2_shape': 0, 'at_l2_strength_b': 70, 'at_l2_detent_pos': 5, 'at_l2_pushback': 0, 'at_l2_kick_style': 0, 'at_l2_pushback_freq': 35, 'at_pushback_src': 2, 'ce_r2_enable': 0, 'ce_l2_enable': 0, 'ce_r2_yield': 0, 'ce_l2_yield': 0})

def _slot_value(field,value):
    key=field[1]
    if key=='ah_xover_hz':
        if value in (0,0xffff):return 0
        return min(200,max(30,value))
    try:
        encode(field,value)
    except ValueError:
        if key not in _SLOT_DEFAULTS:raise
        return _SLOT_DEFAULTS[key]
    return value

def backup_all(client,progress=lambda text:None):
    slots=[]
    lightbar=bool(getattr(client,'read_lightbar',lambda:{})())
    rumble=bool(getattr(client,'read_rumble',lambda:{})())
    available={k:f for k,f in FIELDS.items() if (lightbar or k not in LIGHTBAR_FIELDS) and (rumble or k not in RUMBLE_FIELDS)}
    try:client.read_one(FIELDS['usb_gamepad_mode'])
    except USBModeUnsupported:available.pop('usb_gamepad_mode',None)
    try:client.read_one(FIELDS['rumble_mode'])
    except RumbleModeUnsupported:available.pop('rumble_mode',None)
    for slot in client.slots():
        if slot.state!='saved':slots.append(dict(index=slot.index,valid=False));continue
        progress(_ui_tr('슬롯 {0} 백업 중').format(f'{slot.index + 1:02d}'))
        fields={}
        for key,field in available.items():
            try:
                fields[key]=_slot_value(field,client.read_one(field,slot.index))
            except (ValueError,OSError) as exc:
                raise ValueError(f"{slot.index + 1:02d} / {key} · {exc}") from exc
        validate_changes({},fields,profile_snapshot=True)
        effects={} # excluded construction area
        slots.append(dict(index=slot.index,valid=True,name=slot.name,cfgVersion=config_version(fields),fields=fields,effects={('r2' if k=='0' else 'l2'):v for k,v in effects.items()}))
    return dict(format='ds5dongle-slots',version=2,scope='native-editor-fields-only',slots=slots,macros=client.read_macros())

def validate_backup(data):
    if not isinstance(data,dict) or not isinstance(data.get('slots'),list) or len(data['slots'])>32:raise ValueError(_ui_tr('슬롯 백업 형식 오류'))
    rows=[];seen=set();macros=macro_records(data.get('macros',{}))
    for slot in data['slots']:
        if not isinstance(slot,dict):raise ValueError(_ui_tr('슬롯 항목 오류'))
        index=slot.get('index')
        if type(index)is not int or not 0<=index<32 or index in seen:raise ValueError(_ui_tr('슬롯 번호 중복/범위 오류'))
        seen.add(index)
        if not slot.get('valid'):continue
        raw=slot.get('fields',{});name=slot.get('name','')
        if not isinstance(raw,dict) or not isinstance(name,str) or len(name.encode('utf-8'))>16:raise ValueError(_ui_tr('슬롯 이름/필드 형식 오류'))
        values={k:v for k,v in raw.items() if k in FIELDS};validate_changes({},values,profile_snapshot=True)
        if not values:raise ValueError(_ui_tr('슬롯 설정이 비어 있습니다.'))
        values.setdefault('lightbar_fixed',0)
        effects={}
        # Legacy files may contain custom-effect flags without effect records.
        # Preserve the connected device's excluded custom effects on restore.
        enabled=(~int(values.get('macro_disable',0xffffffff)))&0xffffffff
        if enabled and any(str(i) not in macros for i in range(32) if enabled&(1<<i)):raise ValueError(_ui_tr('활성 매크로 정의가 없는 백업입니다.'))
        rows.append(dict(index=index,name=name,fields=values,effects=effects))
    if not rows:raise ValueError(_ui_tr('복원할 유효 슬롯이 없습니다.'))
    return rows,macros

def restore_all(client,rows,macros,progress=lambda text:None):
    from studio_shift import extended
    if any(extended(row) for row in macros.values()):
        client.require_macro_features(list(macros.values()))
    original,missing=client.read_fields();effects={};original_macros=client.read_macros()
    if set(missing)-OPTIONAL_FIELDS:raise RuntimeError(_ui_tr('현재 설정을 완전히 읽지 못해 복원을 시작하지 않습니다.'))
    if not LIGHTBAR_FIELDS.issubset(original):
        if any('lightbar_rgb' in row['fields'] or row['fields'].get('lightbar_fixed',0) for row in rows):
            raise RuntimeError(_ui_tr('복원 대상 펌웨어에서 라이트바 색상 고정을 지원하지 않습니다.'))
        rows=[dict(row,fields={k:v for k,v in row['fields'].items() if k not in LIGHTBAR_FIELDS}) for row in rows]
    if not RUMBLE_FIELDS.issubset(original) and any(RUMBLE_FIELDS.intersection(row['fields']) for row in rows):
        raise RuntimeError(_ui_tr('복원 대상 펌웨어에서 일반 진동 조절을 지원하지 않습니다.'))
    if 'usb_gamepad_mode' not in original:
        if any(row['fields'].get('usb_gamepad_mode',0) for row in rows):
            raise RuntimeError(_ui_tr('복원 대상 펌웨어에서 XInput 전환을 지원하지 않습니다.'))
        rows=[dict(row,fields={k:v for k,v in row['fields'].items() if k not in USB_MODE_FIELDS}) for row in rows]
    else:
        rows=[dict(row,fields={'usb_gamepad_mode':0,**row['fields']}) for row in rows]
    if 'rumble_mode' in original:
        rows=[dict(row,fields={'rumble_mode':0,**row['fields']}) for row in rows]
    elif any(row['fields'].get('rumble_mode',0) for row in rows):
        raise RuntimeError(_ui_tr('일반 진동 모드 지원을 확인하지 못했습니다.'))
    else:
        rows=[dict(row,fields={k:v for k,v in row['fields'].items() if k not in RUMBLE_MODE_FIELDS}) for row in rows]
    if any(original_macros.get(key,[0]*35)[4]&16 for key in macros):raise RuntimeError(_ui_tr('복원 대상 번호에 제외된 모션 매크로가 있습니다. 원본 Studio에서 관리하세요.'))
    # Prevent enabled controller macros from firing while a different mask is
    # transiently live. This is an explicit operation, never background polling.
    if client.command(26,b'\1',0x84)[2]!=0:raise RuntimeError(_ui_tr('매크로 일시 정지 실패'))
    done=[]
    try:
        for key,data in macros.items():client.write_macro(int(key),data)
        if macros:client.commit_macros()
        for row in rows:
            progress(_ui_tr('슬롯 {0} 복원 중').format(f"{row['index'] + 1:02d}"))
            current,_=client.read_fields();client.write_fields(dict(original,**row['fields']),current,profile_snapshot=True)
            for trig,states in row['effects'].items():
                for index,state in enumerate(states):client.write_effect(int(trig),index,state)
            client.save_slot(row['index'],row['name']);done.append(row['index'])
    finally:
        # Restore the pre-operation LIVE settings; active slot flash is not
        # blindly rewritten. Failures are surfaced, not hidden by a success UI.
        cancelled=client.cancel;client.cancel=lambda:False
        try:
            current,_=client.read_fields();client.write_fields(original,current,profile_snapshot=True)
            for trig,states in effects.items():
                for index,state in enumerate(states):client.write_effect(int(trig),index,state)
        finally:
            try:client.command(26,b'\0',0x84)
            finally:client.cancel=cancelled
    if macros:client.reconnect_usb()
    return done
