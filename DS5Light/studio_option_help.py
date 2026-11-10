"""Local, on-hover dependency guidance. No device access or timers."""
from studio_i18n import text as _ui_tr
from studio_help import compact_ko_help, help_text
from studio_scope import AUDIO_HAPTIC_CHILDREN


def inactive_reason(editor,key):
    values=editor.doc.values
    if key not in values:
        if key in ('rumble_gain','rumble_release'):
            return _ui_tr('일반 진동 조절 지원을 확인하지 못했습니다. 지원 펌웨어를 설치한 뒤 새로 고침하세요.')
        if key in ('lightbar_fixed','lightbar_rgb'):
            return _ui_tr('라이트바 색상 고정 지원을 확인하지 못했습니다. 지원 펌웨어를 설치한 뒤 새로 고침하세요.')
        return _ui_tr('설정값을 아직 읽지 못했습니다. 듀얼센스를 연결한 뒤 새로 고침하세요.')
    if editor.enabled_for(key):
        return _ui_tr('조회·저장 작업이 끝나면 조절할 수 있습니다.') if editor.busy else ''
    mode=values.get('auto_haptics_enable')
    if key=='haptics_gain':return _ui_tr('기존 증폭값은 유지합니다. Mix·Replace로 전환할 때 기본값 1을 예약합니다. 별도 조절은 오디오햅틱 끔에서 가능합니다.')
    if key in ('rumble_gain','rumble_release'):
        if not all(k in values for k in ('rumble_gain','rumble_release')):
            return _ui_tr('일반 진동 조절 지원을 확인하지 못했습니다. 지원 펌웨어에서 새로 고침하세요.')
        return _ui_tr('오디오햅틱 모드를 끔으로 변경하면 사용할 수 있습니다.')
    if key in ('rumble_haptic_strength','mix_native_level'):
        return _ui_tr('오디오햅틱 모드를 Mix로 변경하면 사용할 수 있습니다.')
    if key=='mix_native_filter':
        if mode!=1:return _ui_tr('오디오햅틱 모드를 Mix로 변경하고 네이티브 햅틱 혼합량을 0보다 높이세요.')
        return _ui_tr('네이티브 햅틱 혼합량을 0보다 높이면 사용할 수 있습니다.')
    if key in ('auto_mute_mix','auto_mute_replace'):
        target='Mix' if key=='auto_mute_mix' else 'Replace'
        steps=[]
        if mode!=(1 if key=='auto_mute_mix' else 2):steps.append(_ui_tr('오디오햅틱 모드를 ')+target+_ui_tr('로 변경하세요.'))
        if values.get('disable_speaker'):steps.append(_ui_tr('듀얼센스 스피커 끄기를 해제하세요. 현재는 전체 음소거가 우선합니다.'))
        return ' '.join(steps)
    if key in AUDIO_HAPTIC_CHILDREN and not mode:
        return _ui_tr('오디오햅틱 모드를 Mix 또는 Replace로 변경하면 사용할 수 있습니다.')
    if key in ('ah_low_gain','ah_high_gain'):
        return _ui_tr('저음·고음 분리 기준을 0보다 높게 설정하면 사용할 수 있습니다.')
    if key in ('speaker_volume','speaker_gain'):return _ui_tr('듀얼센스 스피커 끄기를 해제하면 음량을 조절할 수 있습니다.')
    if key=='enable_wake':return _ui_tr('최대절전이 켜져 있으면 사용할 수 없습니다. 최대절전을 끈 대기 모드에서 사용하며, PC의 USB 깨우기 지원이 필요합니다.')
    if key in ('lightbar_fixed','lightbar_rgb'):
        if not getattr(editor,'lightbar_supported',True):return _ui_tr('지원 펌웨어에서 새로 고침하여 라이트바 색상 고정 지원을 확인하세요.')
        return _ui_tr('듀얼센스 라이트바 색상 고정을 체크하면 색상을 선택할 수 있습니다.')
    if key in ('r2t_on_press','r2t_strength','r2t_frequency'):
        return _ui_tr('일반 진동을 트리거에 연동에서 끔 이외의 항목 선택')
    if key=='flick_angle':return _ui_tr('자이로 작동 기준을 마우스 + Flick Stick으로 변경하면 사용할 수 있습니다.')
    if key=='flick_counts_360':
        return _ui_tr('마우스 + Flick Stick을 선택하거나, 자이로를 켜고 마우스 출력과 자연 감도를 선택하세요.')
    if key.startswith('gyro_'):
        if not values.get('gyro_mode'):return _ui_tr('자이로 작동 조건을 끔 이외의 항목으로 변경하세요.')
        if key in ('gyro_sens','gyro_sens_y'):return _ui_tr('자연 감도 사용 중에는 자연 감도 배율을 조절하세요. 이 항목은 수동 감도 또는 스틱 출력에서 사용할 수 있습니다.')
        if key in ('gyro_natural_x10','gyro_natural_y_x10','gyro_scale_trim_x100'):
            return _ui_tr('자이로 작동 기준을 마우스 계열로 변경하고 자연 감도를 선택하세요.')
        if key=='gyro_sens_mode':return _ui_tr('자이로 작동 기준을 마우스 계열로 변경하면 사용할 수 있습니다.')
    if key.startswith('stick_mouse_'):return _ui_tr('스틱 마우스에서 사용할 스틱을 선택하면 조절할 수 있습니다.')
    return _ui_tr('연계된 상위 옵션을 활성화하면 사용할 수 있습니다.')


def option_help(editor,key):
    reason=inactive_reason(editor,key)
    text=help_text(key)
    from localization import LANGUAGE
    if getattr(editor,'category',None)==0 and not editor.search.get():
        lighting={
            'disable_pico_led':('Pico 보드의 LED를 켜거나 끕니다. 금색 원은 ON, 빈 원은 OFF입니다.','Turn the Pico board LED on or off. A gold circle means ON; an empty circle means OFF.'),
            'lightbar_fixed':('기본은 게임·기기의 라이트바 제어를 사용합니다. 색상 박스에서 색상을 확인하면 고정 모드로 바뀝니다.','Default uses game/device lightbar control. Confirm a color in the color box to enable fixed color.'),
            'lightbar_rgb':('박스를 눌러 고정할 색상을 선택합니다. 확인하면 라이트바 끄기를 해제하고 색상을 고정하며, 취소하면 기존 상태를 유지합니다.','Choose a color. Confirming enables fixed color and clears Off; cancelling keeps the previous state.')}
        if key in lighting:text=lighting[key][LANGUAGE=='en']
    if LANGUAGE=='en' and reason:
        values=editor.doc.values
        if key not in values:
            reason='This setting is unavailable. Connect the device and refresh; a firmware update may be required.'
        elif editor.busy:reason='Available when the current operation finishes.'
        elif key in ('rumble_gain','rumble_release'):reason='Set audio haptics to Off.'
        elif key=='haptics_gain':reason='Existing gain is preserved. Switching to Mix or Replace stages 1. Adjust separately with audio haptics off.'
        elif key in ('rumble_haptic_strength','mix_native_level'):reason='Select Mix mode.'
        elif key=='mix_native_filter':reason='Select Mix mode and set native haptic mix above zero.'
        elif key in ('auto_mute_mix','auto_mute_replace'):reason='Select the corresponding audio haptic mode and turn off the speaker-disable option.'
        elif key in AUDIO_HAPTIC_CHILDREN:reason='Select Mix or Replace mode.'
        elif key in ('ah_low_gain','ah_high_gain'):reason='Set the low/high crossover above zero.'
        elif key=='speaker_volume':reason='Turn off the DualSense speaker-disable option.'
        elif key=='enable_wake':reason='Available in standby with deep sleep off; the PC must support USB wake.'
        elif key in ('lightbar_fixed','lightbar_rgb'):reason='Check firmware support and enable fixed lightbar color.'
        elif key.startswith('r2t_'):reason='Enable rumble to triggers.'
        elif key=='flick_angle':reason='Select Mouse + Flick Stick output.'
        elif key=='flick_counts_360':reason='Select Flick Stick or enable gyro mouse with natural sensitivity.'
        elif key.startswith('gyro_'):reason='Enable gyro and choose the relevant output and sensitivity mode.'
        elif key.startswith('stick_mouse_'):reason='Select a stick for stick-to-mouse.'
        else:reason='Enable the related parent option.'
        return 'Unavailable · '+reason+'\n\n'+text
    return _ui_tr('현재 비활성')+'\n'+compact_ko_help(reason)+'\n\n'+text if reason else text
