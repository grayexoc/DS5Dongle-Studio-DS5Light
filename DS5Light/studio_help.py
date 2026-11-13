"""Native Studio presentation metadata; recommendations are starting points, never auto-written."""

from studio_i18n import text as _ui_tr
from studio_fields import FIELDS

LABELS = {}

for line in _ui_tr('\nauto_haptics_enable|오디오햅틱 모드\nauto_haptics_gain|오디오햅틱 세기\nauto_haptics_smooth|진동 부드러움\nauto_haptics_gate|작은 소리 차단\nmix_native_level|기본 햅틱 혼합량\nmix_native_filter|기본 햅틱 누설 억제\nah_dsp_source|햅틱 입력 채널\nauto_haptics_lowpass_hz|저역 통과 기준\nauto_haptics_slope|주파수 차단 기울기\nah_xover_hz|저음·고음 분리 기준\nah_low_gain|저음 충격 세기\nah_high_gain|고음 대역 세기\nauto_mute_replace|Replace 모드 스피커 음소거\nauto_mute_mix|Mix 모드 스피커 음소거\nrumble_haptic_strength|Mix 일반 진동 혼합 세기\neffect_leak_volume|스피커 효과음 세기\neffect_leak_sensitivity|효과음 감지 민감도\neffect_leak_decay|효과음 잔향 길이\neffect_leak_attack|효과음 시작 속도\neffect_leak_output_hp_hz|스피커 저음 차단\neffect_leak_hp_hz|효과음 감지 주파수\neffect_leak_lp_hz|스피커 고음 차단\neffect_leak_max_burst|효과음 최대 길이\neffect_leak_hold|효과음 유지 시간\nhaptics_gain|햅틱 파형 증폭\nspeaker_volume|듀얼센스 스피커 음량\nheadset_volume|듀얼센스 헤드셋 음량\nspeaker_gain|스피커 증폭\nsync_spk_headset_volume|스피커·헤드셋 음량 연동\nlock_volume|음량 고정\ndisable_mic|듀얼센스 마이크 끄기\ndisable_speaker|듀얼센스 오디오 끄기\nmacro_disable|활성 매크로\ncontroller_mode|듀얼센스 종류\npolling_rate_mode|입력 보고 주기\naudio_buffer_length|동글 오디오 버퍼\ninactive_time|자동 연결 해제 대기\ndisable_inactive_disconnect|자동 연결 해제 사용 안 함\ndisable_pico_led|Pico LED 끄기\nlightbar_off|라이트바 끄기\nplayer_led_mode|플레이어 LED 표시\nplayer_led_bright|플레이어 LED 밝기\nenable_wake|PS 버튼으로 PC 깨우기\nbatt_notify_enable|라이트바 배터리 알림\ntouch_mouse|터치패드 마우스\ntouch_mouse_sens|터치패드 이동 속도\ntouch_mouse_min|터치패드 미세 움직임 차단\ntouch_mouse_invert|터치패드 방향 반전\ntouch_mouse_trackball|트랙볼 관성\ntouch_mouse_friction|트랙볼 감속\nhaptics_aa|햅틱 파형 부드러움\ntrigger_reduce|트리거 힘 줄이기\nr2t_mode|일반 진동을 트리거에 연동\nr2t_on_press|트리거를 누를 때만 진동\nr2t_strength|트리거 진동 세기\nr2t_frequency|트리거 진동 주파수\nsynth_force|게임 트리거 효과 덮어쓰기\nat_mode|R2 저항 작동 조건\nat_strength|R2 기본 저항\nat_threshold|R2 작동을 허용할 L2 깊이\nat_start_pos|R2 저항 시작 위치\nat_shape|R2 저항 형태\nat_strength_b|R2 두 번째 저항\nat_detent_pos|R2 벽·스냅 위치\nat_deadzone|R2 입력 시작 구간\nt2_mode|R2 2단계 입력\nt2_pos|R2 2단계 경계\nt2_button|R2 2단계 버튼\nat_pushback|R2 반동 세기\nat_kick_style|R2 반동 형태\nat_pushback_freq|R2 반동 주파수\nat_pushback_src|반동 감지 소스\nat_l2_mode|L2 저항 작동 조건\nat_l2_strength|L2 기본 저항\nat_l2_threshold|L2 작동을 허용할 R2 깊이\nat_l2_start_pos|L2 저항 시작 위치\nat_l2_shape|L2 저항 형태\nat_l2_strength_b|L2 두 번째 저항\nat_l2_detent_pos|L2 벽·스냅 위치\nat_l2_deadzone|L2 입력 시작 구간\nt2_l2_mode|L2 2단계 입력\nt2_l2_pos|L2 2단계 경계\nt2_l2_button|L2 2단계 버튼\nat_l2_pushback|L2 반동 세기\nat_l2_kick_style|L2 반동 형태\nat_l2_pushback_freq|L2 반동 주파수\ngyro_mode|자이로 작동 조건\ngyro_sens|자이로 가로 감도\ngyro_axis|자이로 회전 기준\ngyro_invert|자이로 방향 반전\ngyro_sens_y|자이로 세로 감도\ngyro_output|자이로 출력 방식\nflick_angle|Flick Stick 회전 각도\nflick_counts_360|360도 회전 마우스 이동량\ngyro_sens_mode|자이로 감도 기준\ngyro_natural_x10|자연 감도 배율 ×10\ngyro_natural_y_x10|자연 세로 배율 ×10\ngyro_scale_trim_x100|자이로 회전 보정 ×100\nrstick_invert|오른쪽 스틱 방향 반전\nstick_mouse|스틱 마우스\nstick_mouse_sens|스틱 마우스 가로 속도\nstick_mouse_sens_y|스틱 마우스 세로 속도\nstick_mouse_deadzone|스틱 마우스 데드존\nstick_mouse_curve|스틱 마우스 반응 곡선\nstick_mouse_invert|스틱 마우스 방향 반전\n').strip().splitlines():

    key,label=line.split('|');LABELS[key]=label

for n in range(3):

    for suffix,title in [('on',_ui_tr('사용')),('level',_ui_tr('알림 잔량')),('blinks',_ui_tr('깜박임 횟수')),('r',_ui_tr('빨강')),('g',_ui_tr('초록')),('b',_ui_tr('파랑'))]:

        key=f'batt_stage_{suffix}_{n}';LABELS[key]=_ui_tr('{0}단계 · {1}').format(f'{n + 1}',f'{title}')

for side in ('r2','l2'):

    for suffix,title in [('enable',_ui_tr('커스텀 효과 사용')),('condition',_ui_tr('커스텀 효과 작동 조건')),('thresh',_ui_tr('효과 작동·재준비 위치')),('rate',_ui_tr('효과 전환 속도')),('state_count',_ui_tr('효과 단계 수')),('yield',_ui_tr('기본 저항과 효과 우선순위'))]:

        LABELS[f'ce_{side}_{suffix}']=f'{side.upper()} {title}'

GROUPS=[(_ui_tr('햅틱·오디오'),['Auto-Haptics & Speaker Effect Leak','Native Haptics Filter','General Haptics & Audio']),

 (_ui_tr('트리거'),['Trigger Strength','Rumble → Trigger','Adaptive Triggers — R2 (right trigger)','Adaptive Triggers — L2 (left trigger)']),

 (_ui_tr('자이로·스틱'),['Gyro Aiming','Right Stick','Stick to Mouse','Touchpad as Mouse']),

 (_ui_tr('매크로'),['Macros']),(_ui_tr('장치·배터리'),['Device & Connection','Battery Notification']),(_ui_tr('프로필 슬롯'),[])]

TITLES={'Auto-Haptics & Speaker Effect Leak':_ui_tr('오디오에서 만드는 햅틱'),'Native Haptics Filter':_ui_tr('햅틱 파형 질감'),

 'General Haptics & Audio':_ui_tr('음량·오디오 장치'),'Trigger Strength':_ui_tr('트리거 기본 세기'),'Rumble → Trigger':_ui_tr('게임 진동 → 트리거'),

 'Adaptive Triggers — R2 (right trigger)':_ui_tr('R2 · 오른쪽 트리거'),'Adaptive Triggers — L2 (left trigger)':_ui_tr('L2 · 왼쪽 트리거'),

 'Gyro Aiming':_ui_tr('자이로 조준'),'Right Stick':_ui_tr('오른쪽 스틱'),'Stick to Mouse':_ui_tr('스틱 → 마우스'),'Touchpad as Mouse':_ui_tr('터치패드 → 마우스'),

 'Device & Connection':_ui_tr('연결·전원·표시'),'Battery Notification':_ui_tr('배터리 알림'),'Macros':_ui_tr('프로필별 매크로 선택')}

CHOICES={'Off':_ui_tr('끔'),'On':_ui_tr('켬'),'None':_ui_tr('없음'),'Both':_ui_tr('양쪽'),'Auto-detect':_ui_tr('자동 인식'),'Always on':_ui_tr('항상'),

 'Mix with native':_ui_tr('Mix · 기본 진동과 혼합'),'Replace (audio only)':_ui_tr('Replace · 오디오만'),

 'DualSense (DS5)':'DualSense','DualSense Edge (DSE)':'DualSense Edge',

 'Right stick (works everywhere)':_ui_tr('오른쪽 스틱'),'Mouse (finer aim; needs the pad hidden in most games)':_ui_tr('마우스'),

 'Mouse + Flick Stick (right stick flicks to a bearing)':_ui_tr('마우스 + Flick Stick'),

 'Passthrough':_ui_tr('게임 설정 따름'),'Battery gauge':_ui_tr('배터리 잔량'),'Bright':_ui_tr('밝게'),'Mid':_ui_tr('중간'),'Dim':_ui_tr('어둡게')}

def label(key):

    from localization import LANGUAGE

    if LANGUAGE=='en':

        from studio_english_strings import FIELD_LABELS
        return FIELD_LABELS.get(key,FIELDS[key][3])

    return LABELS.get(key,FIELDS[key][3])

def options(f):

    raw=f[5] if len(f)>5 else {}
    if f[1]=='player_led_bright':raw={k:v for k,v in raw.items() if int(k)!=3}

    from localization import LANGUAGE

    if f[1]=='mix_native_filter':
        return [(1,'Filtered'),(0,'Raw')] if LANGUAGE=='en' else [(1,'억제'),(0,'원본')]

    from studio_english_strings import OPTION_TEXT
    translated={**OPTION_TEXT, _ui_tr('끔'):'Off',_ui_tr('짧게 · 20ms'):'Short · 20ms',_ui_tr('보통 · 40ms'):'Medium · 40ms'}

    return [(int(k),translated.get(str(v),str(v)) if LANGUAGE=='en' else CHOICES.get(str(v),str(v))) for k,v in (raw.items() if isinstance(raw,dict) else raw)]

CHOICES.update({
 'Follow game':_ui_tr('게임 설정 따름'),'Classic':_ui_tr('클래식'),'Improved':_ui_tr('개선형'),

 'Add button (keep trigger held)':_ui_tr('버튼 추가 · 트리거 유지'),'Add button + rescale below':_ui_tr('버튼 추가 · 하단 재배율'),

 'Swap to button (release trigger)':_ui_tr('버튼 전환 · 트리거 해제'),'Swap to button + rescale below':_ui_tr('버튼 전환 · 하단 재배율'),

 'Always on — touch touchpad to pause (ratchet)':_ui_tr('항상 · 터치하면 일시 정지'),

 'Audio haptics only':_ui_tr('오디오햅틱만'),'Both triggers':_ui_tr('양쪽 트리거'),'Bow snap (mechanical push-back)':_ui_tr('스냅 · 밀어내기'),

 'Circle':'○','Cross':'×','Square':'□','Triangle':'△','Constant':_ui_tr('일정한 저항'),

 'Custom effect always owns L2':_ui_tr('커스텀 효과 우선'),'Custom effect always owns R2':_ui_tr('커스텀 효과 우선'),

 'Custom effect while gated, sliders otherwise':_ui_tr('조건 만족 시 커스텀 효과'),'Sliders while gated, custom effect otherwise':_ui_tr('조건 만족 시 기본 저항'),

 'Filtered (default) — blocks 4ch mirror leakage':_ui_tr('필터 · 복제 신호 누설 억제'),

 'Raw — keep native haptics intact':_ui_tr('원본 네이티브 햅틱 유지'),

 'Gated by L1 (shoulder)':_ui_tr('L1을 누를 때'),'Gated by L2 (aim trigger)':_ui_tr('L2를 누를 때'),

 'Gated by R1 (shoulder)':_ui_tr('R1을 누를 때'),'Gated by R2 (fire trigger)':_ui_tr('R2를 누를 때'),

 'Only while L1 held':_ui_tr('L1을 누르는 동안'),'Only while L2 (aim) held':_ui_tr('L2를 누르는 동안'),

 'Only while R1 held':_ui_tr('R1을 누르는 동안'),'Only while R2 (fire) held':_ui_tr('R2를 누르는 동안'),

 'Only while touchpad touched':_ui_tr('터치패드에 손댈 때'),'L2 (click)':_ui_tr('L2 클릭'),'R2 (click)':_ui_tr('R2 클릭'),

 'Left stick':_ui_tr('왼쪽 스틱'),'Right stick':_ui_tr('오른쪽 스틱'),'Left trigger only':_ui_tr('왼쪽 트리거만'),'Right trigger only':_ui_tr('오른쪽 트리거만'),

 'Light — kills grit, keeps snap (recommended)':_ui_tr('약하게 · 추천'),'Strong — maximum smooth (can feel muted)':_ui_tr('강하게 · 부드러움 우선'),

 'Manual — tune by feel, no calibration needed':_ui_tr('수동 감도'),'Natural — real-world ratio (default; needs counts per 360°)':_ui_tr('자연 감도 · 회전 비율'),

 'Off — full strength':_ui_tr('끔 · 기본 세기'),'Off — raw & gritty (pre-1.0.4 texture)':_ui_tr('끔 · 원본 질감'),

 'On press':_ui_tr('누를 때'),'On release':_ui_tr('놓을 때'),'While held':_ui_tr('누르는 동안'),

 'Player space (follows how you hold it)':_ui_tr('잡은 방향 기준'),'Yaw (turn controller)':_ui_tr('좌우 회전'),'Roll (tilt sideways)':_ui_tr('좌우 기울임'),

 'Ramp (A → B)':_ui_tr('저항 A → B'),'Two-stage detent':_ui_tr('2단계 벽'),'Weapon break (snap-through)':_ui_tr('무기 방아쇠 · 돌파'),

 'Vibration thump (buzz)':_ui_tr('진동 반동'),'Rumble + audio (strongest)':_ui_tr('일반 진동 + 오디오'),'Rumble only':_ui_tr('일반 진동만'),'Real-time':_ui_tr('실시간'),

 'ch0/1 (default) — same feed as speaker + leak':_ui_tr('0/1 채널 · 기본'),'ch2/3 — script feed only (run ds5audio --map rear)':_ui_tr('2/3 채널 · 후방 입력'),

 '6 dB/oct (gentle)':_ui_tr('6 dB/oct · 완만'),'12 dB/oct (default)':_ui_tr('12 dB/oct · 기본'),'24 dB/oct (steep)':_ui_tr('24 dB/oct · 급격'),'10 — weakest':_ui_tr('10 · 가장 약함'),

})

DESCRIPTIONS={

 'auto_haptics_enable':_ui_tr('게임 소리를 진동으로 바꿀지와 원래 진동을 함께 쓸지를 정합니다.'),

 'auto_haptics_gain':_ui_tr('동글이 만드는 오디오햅틱의 크기입니다. 앱 상단 햅틱 세기와는 별도 배율입니다.'),

 'auto_haptics_smooth':_ui_tr('소리가 끝난 뒤 진동이 가라앉는 정도입니다. 높일수록 부드럽지만 짧은 충격이 뭉개질 수 있습니다.'),

 'auto_haptics_gate':_ui_tr('조용한 소리에 대한 반응을 줄입니다. 올리면 작은 발소리·약한 효과도 줄어들 수 있습니다.'),

 'auto_haptics_lowpass_hz':_ui_tr('이 값보다 높은 주파수를 약하게 만들어 낮은 충격 위주로 전달합니다.'),

 'ah_xover_hz':_ui_tr('햅틱 대역을 저음과 고음으로 나누는 경계입니다. 0이면 분리하지 않습니다.'),

 'ah_low_gain':_ui_tr('저음·고음 분리 기준보다 낮은 대역의 세기입니다. 분리 기준이 0이면 적용되지 않습니다.'),

 'ah_high_gain':_ui_tr('저음·고음 분리 기준보다 높은 햅틱 대역의 세기입니다. 분리 기준이 0이면 적용되지 않습니다.'),

 'haptics_aa':_ui_tr('Mix·Replace에서 생성된 오디오햅틱과 Mix의 변환 진동 파형을 다듬습니다.'),

 'audio_buffer_length':_ui_tr('동글 안에서 오디오를 쌓는 양입니다. 앱의 PC 전송 블록과는 다릅니다.'),

 'polling_rate_mode':_ui_tr('듀얼센스 입력 보고 주기입니다. 오디오 블록 크기를 바꾸는 옵션은 아닙니다.'),

 'synth_force':_ui_tr('게임이 직접 보내는 트리거 효과보다 동글에서 만든 효과를 우선할지 정합니다.'),

 'trigger_reduce':_ui_tr('게임의 트리거 저항을 약하게 만듭니다. 단계가 높을수록 약해집니다.'),

 'effect_leak_volume':_ui_tr('감지한 짧은 효과음을 듀얼센스 스피커로 내보내는 크기입니다. 0이면 사용하지 않습니다.'),

 'effect_leak_attack':_ui_tr('감지 후 효과음 출력을 여는 속도입니다. 크게 하면 빠르게 반응합니다.'),

 'effect_leak_decay':_ui_tr('효과음이 감지된 뒤 소리가 줄어드는 꼬리 길이입니다.'),

 'effect_leak_max_burst':_ui_tr('한 번 출력할 효과음 길이의 상한입니다. 단위는 5ms이며 0은 제한 없음입니다.'),

 'effect_leak_hold':_ui_tr('효과음 출력을 유지하는 최소 시간입니다. 단위는 5ms입니다.'),

 'gyro_scale_trim_x100':_ui_tr('센서 회전량을 보정합니다. 100은 명목 배율이며 360도 회전 결과로 보정합니다.'),

 'gyro_natural_x10':_ui_tr('실제 듀얼센스 회전과 게임 화면 회전의 비율입니다. 10은 1:1, 25는 2.5배입니다.'),

 'flick_counts_360':_ui_tr('현재 게임에서 화면을 한 바퀴 돌리는 데 필요한 마우스 이동량입니다.'),

}

DESCRIPTIONS.update({

 'mix_native_level':_ui_tr('Mix에서 게임이 직접 보내는 햅틱을 얼마나 섞을지 정합니다. 0이면 오디오에서 만든 햅틱 위주입니다.'),

 'mix_native_filter':_ui_tr('복제 오디오가 기본 햅틱 신호로 새어 들어오는 성분을 걸러냅니다.'),

 'ah_dsp_source':_ui_tr('동글이 진동을 만들 때 분석할 USB 오디오 채널 쌍입니다. 앱의 캡쳐 채널 구성과 구분하세요.'),

 'auto_haptics_slope':_ui_tr('차단 주파수보다 높은 소리를 얼마나 급하게 줄일지 정합니다.'),

 'auto_mute_replace':_ui_tr('Replace에서 듀얼센스 스피커의 일반 소리를 자동으로 끕니다.'),

 'auto_mute_mix':_ui_tr('Mix에서 듀얼센스 스피커의 일반 소리를 자동으로 끕니다.'),

 'rumble_haptic_strength':_ui_tr('일반 모터 진동을 햅틱으로 바꿀 때의 크기입니다. 100을 넘으면 포화될 수 있습니다.'),

 'effect_leak_sensitivity':_ui_tr('높이면 더 많은 소리를 짧은 효과음으로 감지합니다.'),

 'effect_leak_output_hp_hz':_ui_tr('스피커 출력의 낮은 주파수를 잘라 파열음과 저음 부담을 줄입니다.'),

 'effect_leak_hp_hz':_ui_tr('효과음 발생을 판단할 감지 주파수 대역의 시작점입니다.'),

 'effect_leak_lp_hz':_ui_tr('스피커 효과음에서 너무 높은 소리를 줄이는 상한입니다.'),

 'haptics_gain':_ui_tr('네이티브 햅틱 파형과 생성된 오디오햅틱의 증폭 배율입니다. 일반 진동은 별도 설정입니다.'),

 'speaker_volume':_ui_tr('듀얼센스 스피커의 음량입니다. PC의 일반 출력 음량은 바꾸지 않습니다.'),

 'headset_volume':_ui_tr('듀얼센스에 연결한 헤드셋의 음량입니다.'),

 'speaker_gain':_ui_tr('듀얼센스 스피커의 추가 증폭 단계입니다. 높으면 소리가 거칠어질 수 있습니다.'),

 'sync_spk_headset_volume':_ui_tr('스피커와 헤드셋 음량을 함께 조절합니다.'),

 'lock_volume':_ui_tr('게임이 보낸 볼륨 설정을 무시하고 지정한 듀얼센스 스피커·헤드셋 음량을 유지합니다.'),
 'disable_usb_sn':_ui_tr('DualSense Edge의 Windows 햅틱·스피커 호환 옵션입니다. 적용하면 USB가 재연결되며 4채널 출력을 다시 선택해야 할 수 있습니다.'),

 'disable_mic':_ui_tr('듀얼센스 마이크 입력을 끕니다. USB 재연결이 필요할 수 있습니다.'),

 'disable_speaker':_ui_tr('듀얼센스 오디오를 끕니다. DS5Light 오디오 전송도 영향을 받습니다.'),

 'macro_disable':_ui_tr('공유 매크로 정의 중 이 프로필에서 사용할 행을 고릅니다.'),

 'controller_mode':_ui_tr('PC에 노출할 듀얼센스 종류입니다. 자동은 일반형과 Edge를 판단합니다.'),

 'inactive_time':_ui_tr('입력이 없는 상태가 이 시간(분) 이어지면 연결을 해제합니다.'),

 'disable_inactive_disconnect':_ui_tr('유휴 시간이 지나도 자동으로 연결을 끊지 않습니다.'),

 'disable_pico_led':_ui_tr('Pico 보드 LED를 끕니다. 듀얼센스 라이트바와는 별개입니다.'),

 'lightbar_off':_ui_tr('듀얼센스 라이트바의 기본 점등을 끕니다.'),

 'player_led_mode':_ui_tr('플레이어 LED를 게임에 맡기거나 끄거나 배터리 표시로 사용합니다.'),

 'player_led_bright':_ui_tr('플레이어 표시 LED의 밝기입니다. 라이트바 RGB와는 다릅니다.'),

 'enable_wake':_ui_tr('지원 PC에서 PS 버튼으로 절전 해제를 요청합니다. PC 전원 설정도 영향을 줍니다.'),

 'batt_notify_enable':_ui_tr('설정한 잔량에 도달하면 듀얼센스 라이트바로 알립니다.'),

 'touch_mouse':_ui_tr('터치패드 움직임을 마우스로 변환합니다.'),

 'touch_mouse_sens':_ui_tr('값이 클수록 손가락 이동에 대한 포인터 속도가 빨라집니다.'),

 'touch_mouse_min':_ui_tr('작은 손떨림을 무시합니다. 높이면 작은 의도적 움직임도 무시할 수 있습니다.'),

 'touch_mouse_invert':_ui_tr('터치패드 마우스의 가로·세로 방향을 반전합니다.'),

 'touch_mouse_trackball':_ui_tr('손가락을 뗀 뒤에도 포인터가 관성으로 움직입니다.'),

 'touch_mouse_friction':_ui_tr('관성 이동이 멈추는 정도입니다. 높이면 빠르게 감속합니다.'),

 'r2t_mode':_ui_tr('게임의 일반 진동을 어느 트리거의 떨림으로 보낼지 정합니다.'),

 'r2t_on_press':_ui_tr('트리거를 실제로 누르는 동안만 변환 진동을 전달합니다.'),

 'r2t_strength':_ui_tr('트리거로 전달되는 진동 크기입니다. 저항 세기와는 별도입니다.'),

 'r2t_frequency':_ui_tr('떨림 빠르기입니다. 낮추면 묵직하고 높이면 가늘게 느껴질 수 있습니다.'),

 'at_pushback_src':_ui_tr('반동을 일반 진동, 오디오햅틱 또는 두 신호에서 얻습니다.'),

 'gyro_mode':_ui_tr('자이로를 항상 쓰거나 버튼·터치 조건에서만 사용할지 정합니다.'),

 'gyro_sens':_ui_tr('수동 모드의 가로 반응 크기입니다. 자연 감도 배율과 구분하세요.'),

 'gyro_axis':_ui_tr('좌우 조준에 사용할 회전축입니다. 잡은 방향 기준은 자세에 맞춰 기준을 바꿉니다.'),

 'gyro_invert':_ui_tr('자이로 가로·세로 조준 방향을 반전합니다.'),

 'gyro_sens_y':_ui_tr('수동 모드의 세로 반응입니다. 0이면 가로 감도를 따릅니다.'),

 'gyro_output':_ui_tr('자이로를 스틱 또는 마우스로 보냅니다. 게임의 입력 설정도 맞춰야 합니다.'),

 'flick_angle':_ui_tr('Flick Stick 조작 한 번의 기준 회전 각도입니다.'),

 'gyro_sens_mode':_ui_tr('감도를 임의 수치 또는 실제 회전 비율로 맞춥니다.'),

 'gyro_natural_y_x10':_ui_tr('자연 감도 세로 배율입니다. 0이면 가로 배율을 따릅니다.'),

 'rstick_invert':_ui_tr('오른쪽 스틱의 가로·세로 방향을 반전합니다.'),

 'stick_mouse':_ui_tr('왼쪽 또는 오른쪽 스틱으로 마우스를 조작합니다.'),

 'stick_mouse_sens':_ui_tr('끝까지 기울였을 때 초당 마우스 이동량입니다. 0은 기본 속도입니다.'),

 'stick_mouse_sens_y':_ui_tr('세로 이동 속도입니다. 0은 가로 속도를 따릅니다.'),

 'stick_mouse_deadzone':_ui_tr('중심에서 무시할 범위입니다. 올리면 드리프트와 미세 조작이 함께 줄어듭니다.'),

 'stick_mouse_curve':_ui_tr('기울기와 속도 사이의 곡선입니다. 10은 선형이며 높은 값은 중심 부근을 세밀하게 만듭니다.'),

 'stick_mouse_invert':_ui_tr('스틱 마우스의 가로·세로 방향을 반전합니다.'),

})

for n in range(3):

    for part,desc in [('on',_ui_tr('이 알림 단계를 사용할지 선택합니다.')),('level',_ui_tr('이 단계의 알림을 낼 배터리 잔량입니다.')),('blinks',_ui_tr('알림이 깜박이는 횟수입니다.')),('r',_ui_tr('라이트바 색상의 빨강 성분입니다.')),('g',_ui_tr('라이트바 색상의 초록 성분입니다.')),('b',_ui_tr('라이트바 색상의 파랑 성분입니다.'))]:DESCRIPTIONS[f'batt_stage_{part}_{n}']=desc

for side,prefix in [('R2','at_'),('L2','at_l2_')]:

    for suffix,desc in {'mode':_ui_tr('어떤 버튼 조건에서 저항을 사용할지 정합니다.'),'strength':_ui_tr('기본 저항의 크기입니다.'),'threshold':_ui_tr('반대 트리거를 이 깊이까지 누르면 저항이 작동합니다.'),'start_pos':_ui_tr('0~9 구간 중 저항이 시작될 위치입니다.'),'shape':_ui_tr('일정·점진적 저항, 벽 또는 돌파 형태입니다.'),'strength_b':_ui_tr('점진적 저항의 끝 또는 두 번째 벽의 저항입니다.'),'detent_pos':_ui_tr('벽 또는 스냅이 생기는 구간입니다.'),'deadzone':_ui_tr('게임에 입력을 보내기 시작할 구간입니다.'),'pushback':_ui_tr('기본 저항에 더할 반동 크기입니다.'),'kick_style':_ui_tr('반동을 떨림 또는 스냅으로 표현합니다.'),'pushback_freq':_ui_tr('반동의 빠르기입니다. 낮으면 묵직해질 수 있습니다.')}.items():DESCRIPTIONS[prefix+suffix]=side+' '+desc

for side,prefix in [('R2','t2_'),('L2','t2_l2_')]:

    for suffix,desc in [('mode',_ui_tr('깊게 눌렀을 때 버튼을 추가하거나 트리거를 버튼으로 전환합니다.')),('pos',_ui_tr('두 번째 입력으로 전환할 깊이입니다. 0은 사용하지 않습니다.')),('button',_ui_tr('두 번째 단계에서 발생시킬 듀얼센스 버튼입니다.'))]:DESCRIPTIONS[prefix+suffix]=side+' '+desc

for side in ('r2','l2'):

    for suffix,desc in [('enable',_ui_tr('저장된 커스텀 효과를 사용합니다.')),('condition',_ui_tr('누르는 동안·누를 때·놓을 때 중 발생 조건입니다.')),('thresh',_ui_tr('작동 또는 벽 효과 재준비 깊이입니다. 0은 완전히 놓았을 때입니다.')),('rate',_ui_tr('진동 단계 사이 전환 속도입니다. 유지 시간이 0인 단계에서 씁니다.')),('state_count',_ui_tr('사용할 효과 단계 수입니다. 실제 데이터는 효과 읽기·편집으로 관리합니다.')),('yield',_ui_tr('버튼 조건에 따라 기본 저항과 커스텀 효과의 우선순위를 선택합니다.'))]:DESCRIPTIONS[f'ce_{side}_{suffix}']=side.upper()+' '+desc





# Native layout revision: references are documented values, not app-authored presets.

from studio_reference import DEFAULTS,DEFAULT_SOURCES,REFERENCE,WEB_HELP

GROUPS=[(_ui_tr('장치'),['Device & Connection']),

 (_ui_tr('햅틱·스피커'),['Auto-Haptics & Speaker Effect Leak','Native Haptics Filter','General Haptics & Audio']),

 (_ui_tr('트리거'),['Trigger Strength','Rumble → Trigger']),

 (_ui_tr('자이로·스틱'),['Gyro Aiming','Right Stick','Stick to Mouse']),

 (_ui_tr('매핑·매크로'),['Macros']),(_ui_tr('프로필 슬롯'),[])]

TITLES.update({'Auto-Haptics & Speaker Effect Leak':_ui_tr('오디오햅틱'),

 'General Haptics & Audio':_ui_tr('듀얼센스 햅틱 파형·스피커 설정'),

 'Trigger Strength':_ui_tr('적응형 트리거 세기'),'Rumble → Trigger':_ui_tr('그립 진동과 트리거 연동')})

LABELS.update({'auto_haptics_enable':_ui_tr('오디오햅틱 모드'),'auto_haptics_gain':_ui_tr('오디오햅틱 세기'),

 'disable_mic':_ui_tr('듀얼센스 마이크 끄기 (배터리 절약)'),'disable_speaker':_ui_tr('듀얼센스 스피커 끄기'),

 'controller_mode':_ui_tr('듀얼센스 유형'),'polling_rate_mode':_ui_tr('폴링율'),'audio_buffer_length':_ui_tr('오디오 버퍼'),

 'lightbar_off':_ui_tr('듀얼센스 라이트바 끄기'),'trigger_reduce':_ui_tr('적응형 트리거 세기'),

 'synth_force':_ui_tr('게임 적응형 트리거 효과 대체')})

CHOICES['Replace (audio only)']=_ui_tr('Replace · 완전히 대체')

for _k in LABELS:LABELS[_k]=LABELS[_k].replace(_ui_tr('동글'),'Pico').replace(_ui_tr('오토햅틱'),_ui_tr('오디오햅틱')).replace(_ui_tr('오토 햅틱'),_ui_tr('오디오햅틱'))

def reference_point(key):

    if key=='rumble_gain':return (100,_ui_tr('기본값'))

    if key=='haptics_gain':return (1.0,_ui_tr('기본값'))

    if key in REFERENCE:return REFERENCE[key],_ui_tr('추천')

    if key in DEFAULTS:return DEFAULTS[key],_ui_tr('기본')

    return None,''

def format_value(key,value):

    f=FIELDS[key]

    if f[4]=='bool':return _ui_tr('체크') if value else _ui_tr('체크 해제')

    if f[4]=='select':return str(dict(options(f)).get(value,value))

    return format(value,'.5g') if isinstance(value,(int,float)) else str(value)

from studio_tooltip_ko import TRANSLATED_HELP

REFERENCE=dict(REFERENCE,audio_buffer_length=48,polling_rate_mode=1)

TITLES['Device & Connection']=_ui_tr('장치')

LABELS.update({'haptics_gain':_ui_tr('네이티브 햅틱 세기'),'gyro_output':_ui_tr('자이로 작동 기준')})

DESCRIPTIONS.update(TRANSLATED_HELP)

def compact_ko_help(text):
    """One instruction per line. Keep the effect, conditions and essential cautions."""
    import re
    endings = (
        ('할 수 없습니다', ' 불가'), ('할 수 있습니다', ' 가능'),
        ('하지 않습니다', '하지 않음'), ('입니다', ''),
        ('합니다', ''), ('됩니다', '됨'), ('수 있습니다', '수 있음'), ('있습니다', '있음'),
        ('없습니다', '없음'), ('선택하세요', '선택'),
        ('높이세요', '높이기'), ('낮추세요', '낮추기'), ('확인하세요', '확인'),
        ('하세요', ''), ('지 않습니다', '지 않음'),
        ('줄어듭니다', '감소'), ('늘어납니다', '증가'),
        ('따릅니다', '따름'), ('바뀝니다', '변경'), ('끕니다', '끔'),
        ('둡니다', '둠'), ('고릅니다', '선택'), ('얻습니다', '얻음'),
        ('만듭니다', '만듦'), ('쉽습니다', '쉬움'),
    )
    lines = re.split(r'(?<=\.)[ \t]+|\n', text.strip())
    result = []
    for line in lines:
        line = line.rstrip('.')
        for suffix, replacement in endings:
            if line.endswith(suffix):
                line = line[:-len(suffix)].rstrip() + replacement
                break
        result.append(line)
    return '\n'.join(result)


def help_text(key):

    from localization import LANGUAGE

    if LANGUAGE=='en':

        from studio_reference import WEB_HELP

        extra={

            'rumble_gain':'Adjusts XInput or DS4-compatible rumble. 100% is unchanged; applies only when audio haptics is off.',

            'rumble_release':'Adds a short decay to ordinary rumble: Off, 20 ms or 40 ms. Applies only when audio haptics is off.',

            'rumble_haptic_strength':'Sets converted game rumble mixed with audio haptics. Works in Mix mode only.',

            'haptics_gain':'Amplifies native haptic waveforms and generated audio haptics. In Mix or Replace, DS5Light stages the default value 1 until applied.',

            'haptics_aa':'Smooths generated audio haptics in Mix and Replace, and converted rumble in Mix.',

            'lightbar_fixed':'Keeps the selected lightbar color. The lightbar-off setting takes precedence.',

            'lightbar_rgb':'Choose the fixed lightbar color. Apply or save the profile to send it.'}

        from studio_english_strings import FIELD_HELP
        desc=FIELD_HELP.get(key, DESCRIPTIONS.get(key) or extra.get(key,WEB_HELP.get(key,'')))
        if key in REFERENCE and key!='audio_buffer_length': desc+='\n\nRecommended: '+format_value(key,REFERENCE[key])

        return label(key)+(('\n\n'+desc) if desc else '')

    f=FIELDS[key]

    title=label(key)+' · '+f[3]

    desc=DESCRIPTIONS.get(key,'').replace(_ui_tr('동글'),'Pico').replace(_ui_tr('오토햅틱'),_ui_tr('오디오햅틱')).replace(_ui_tr('오토 햅틱'),_ui_tr('오디오햅틱'))

    text=title+('\n\n'+compact_ko_help(desc) if desc else '')

    if key in REFERENCE:text+=_ui_tr('\n\n추천 시작값: ')+format_value(key,REFERENCE[key])

    elif key in DEFAULTS:

        value=DEFAULTS[key]

        if key=='trigger_reduce':value=10-value*.9

        text+=_ui_tr('\n\n기본값 기준: ')+(_ui_tr('{0} · 기본 세기').format(f'{value:g}') if key=='trigger_reduce' else format_value(key,value))



    return text



LABELS.update({'mix_native_filter':_ui_tr('네이티브 햅틱 누설 억제'),'mix_native_level':_ui_tr('Mix 네이티브 햅틱 혼합')})

LABELS.update({'lightbar_fixed':_ui_tr('듀얼센스 라이트바 색상 고정'),'lightbar_rgb':_ui_tr('라이트바 색상')})

DESCRIPTIONS.update({

 'lightbar_fixed':_ui_tr('게임이 보내는 색상 대신 선택한 색상을 유지합니다. 켤 때 라이트바 끄기를 해제하며, 변경은 적용 또는 프로필 저장을 눌러 전송합니다.'),

 'lightbar_rgb':_ui_tr('RGB 팔레트로 색상을 선택합니다. 검정도 사용할 수 있습니다. 라이트바 끄기가 켜져 있으면 색상 고정보다 우선합니다.'),

})

CHOICES.update({'Mix with native':_ui_tr('Mix · 게임 진동과 혼합'),'Only while touchpad touched':_ui_tr('터치패드 터치시')})



LABELS.update({'rumble_gain':_ui_tr('일반 진동 세기'),'rumble_mode':_ui_tr('일반 진동 모드'),'rumble_release':_ui_tr('일반진동 잔향')})

DESCRIPTIONS.update({

 'rumble_gain':_ui_tr('XInput·DS4 호환 방식으로 전달되는 일반 진동을 강화합니다. 1은 원래 세기이며, 이미 최대인 진동은 더 강해지지 않습니다. 오디오햅틱 끔에서만 작동하며 네이티브 햅틱에는 영향을 주지 않습니다.'),

 'rumble_mode':_ui_tr('장치 진단에서 두 모드를 시험할 수 있습니다. 클래식(V1)은 로터리 모터의 강한 질감, 개선형(V2)은 햅틱에 가까운 부드러운 질감입니다.'),
 'rumble_release':_ui_tr('진동이 약해지거나 끝날 때 짧은 여운을 남깁니다. 짧게는 20ms, 보통은 40ms입니다. 연속 타격이 뭉개지면 끔이나 짧게를 선택하세요.'),

})



DEFAULTS.update({'rumble_gain':100,'rumble_release':0,'rumble_haptic_strength':100,
                 'at_strength':70,'at_strength_b':70,'at_pushback':0,'at_pushback_freq':35,
                 'mix_native_filter':1,'mix_native_level':0,'haptics_gain':1.0})
REFERENCE['rumble_haptic_strength'] = 100
REFERENCE['disable_mic'] = 1



DESCRIPTIONS['rumble_haptic_strength']=_ui_tr('Mix 모드에서 게임의 일반 진동을 오디오햅틱과 함께 재생할 때의 세기입니다. 오디오햅틱 끔과 Replace에서는 작동하지 않습니다. 100%를 넘기면 큰 진동이 포화될 수 있습니다.')



DESCRIPTIONS['haptics_gain']+=_ui_tr(' 기존 프로필의 증폭값은 유지합니다. 사용자가 Mix·Replace로 전환하면 중복 증폭 방지를 위해 기본값 1을 예약하며, 적용 또는 프로필 저장 시 반영합니다. 별도 조절은 오디오햅틱 끔에서 가능합니다.')


from localization import LANGUAGE as _USB_MODE_LANGUAGE
LABELS['usb_gamepad_mode'] = 'XBOX Mode' if _USB_MODE_LANGUAGE=='en' else 'XBOX 모드'
DEFAULTS['usb_gamepad_mode'] = 0
LABELS['disable_usb_sn'] = _ui_tr('Edge USB 시리얼 숨기기')
DEFAULTS['disable_usb_sn'] = 0
DESCRIPTIONS['usb_gamepad_mode'] = ('On presents an XInput gamepad. Off uses DualSense or Edge. Applying a mode change reconnects USB. Save it to the profile to retain it.' if _USB_MODE_LANGUAGE=='en' else '켜면 XInput, 끄면 DualSense 또는 Edge로 연결됩니다. 모드를 적용하면 USB가 재연결됩니다. 유지하려면 프로필에 저장하세요.')


# Keep operational details here; general save guidance belongs on the save controls.
if _USB_MODE_LANGUAGE != 'en':
    DESCRIPTIONS.update({
        'auto_haptics_enable': '끔 · 게임의 일반 진동과 네이티브 햅틱 사용\nMix · 오디오햅틱과 게임 진동 혼합\nReplace · 오디오햅틱만 사용',
        'auto_haptics_gain': '오디오햅틱 전체 세기\n앱 상단의 오디오햅틱 세기와 함께 높이면 포화 가능',
        'auto_haptics_smooth': '오디오햅틱 세기 변화의 부드러움\n낮을수록 짧은 충격이 선명',
        'auto_haptics_gate': '오디오햅틱을 만드는 최소 소리 크기\n너무 높으면 작은 발소리나 효과음도 제외',
        'mix_native_level': 'Mix에서 섞는 네이티브 햅틱의 양\n0% · 혼합 안 함',
        'mix_native_filter': '복제 오디오에 섞인 대사·고음 억제\n원본 · 게임의 네이티브 햅틱 유지',
        'ah_dsp_source': '오디오햅틱 분석에 사용할 USB 오디오 채널\n0/1 · 일반 스피커 채널\n2/3 · 후방 채널',
        'auto_haptics_lowpass_hz': '지정 주파수보다 높은 소리를 억제\n낮을수록 저음 위주로 반응',
        'ah_xover_hz': '저음·고음 세기를 따로 조절할 분리 주파수\n0 · 대역 분리 끔\n저역 통과 기준보다 낮게 설정',
        'auto_haptics_slope': '저역 통과 기준보다 높은 소리의 감쇠 기울기\n높을수록 고음 억제 증가',
        'disable_mic': '듀얼센스 마이크 입력 차단\nUSB 장치 구성이 바뀌면 재연결 필요',
        'lock_volume': '게임이 보낸 볼륨 설정을 무시하고 지정한 듀얼센스 스피커·헤드셋 음량을 유지합니다.',
        'disable_speaker': '듀얼센스 스피커와 본체 단자에 연결한 헤드셋 끄기\nMix·Replace 선택 시 자동 켜짐, 끔 선택 시 자동 해제\n수동 변경 가능 · 켜진 동안 모드별 음소거 미적용',
        'controller_mode': 'PC에 표시할 듀얼센스 유형\n자동 · 듀얼센스 또는 Edge 감지\nXBOX 모드에서도 USB 오디오 구성에 적용',
        'polling_rate_mode': 'PC에 입력을 보고하는 빈도\n높을수록 보고 간격 감소, USB·무선 처리량 증가',
        'inactive_time': '입력 없이 유지된 뒤 듀얼센스 연결을 끊기까지의 시간(분)',
        'enable_wake': '듀얼센스 PS 버튼으로 PC 절전 해제\nPC의 USB 절전 해제 지원 필요',
        'trigger_reduce': '게임 효과의 형태를 유지하며 적응형 트리거 힘 감소\n1 · 가장 약함 / 10 · 기본 세기',
        'r2t_mode': '게임의 일반 진동을 전달할 트리거 선택',
        'r2t_frequency': '트리거 떨림 주파수\n낮을수록 묵직한 떨림',
        'gyro_mode': '자이로 조준이 작동할 버튼·터치 조건 선택',
        'gyro_axis': '수평 조준에 사용할 회전축\n잡은 방향 기준 · 듀얼센스 자세에 맞춰 자동 보정',
        'gyro_sens_y': '수동 감도의 세로 조준 세기\n0 · 가로 감도 사용',
        'gyro_output': '자이로 입력을 스틱 또는 마우스로 출력\n변경 시 USB 재연결',
        'flick_counts_360': '게임 화면을 한 바퀴 돌리는 데 필요한 마우스 이동량\n게임 감도를 변경하면 다시 보정',
        'gyro_sens_mode': '수동 · 게임별 감도 조절\n자연 · 듀얼센스와 화면의 회전 비율로 조절\n자연 감도는 마우스 출력과 360도 이동량 보정 필요',
        'gyro_natural_y_x10': '자연 감도의 세로 회전 배율\n0 · 가로 배율 사용',
        'stick_mouse_sens_y': '스틱 마우스의 세로 이동 속도\n0 · 가로 속도 사용',
        'audio_buffer_length': '오디오 버퍼 크기. 소리가 끊기면 64로 조정',
        'lightbar_fixed': '선택한 라이트바 색상 유지. 켤 때 라이트바 끄기 해제',
        'lightbar_rgb': '고정 색상 지정. 라이트바 끄기가 색상 고정보다 우선',
        'rumble_gain': 'XInput·DS4 호환 일반 진동 세기 조정. 오디오햅틱 끔에서만 작동. 1은 원래 세기',
        'rumble_release': '일반 진동이 줄거나 끝날 때 여운 추가. 짧게 20ms · 보통 40ms',
        'rumble_haptic_strength': 'Mix에서 오디오햅틱과 함께 재생하는 일반 진동 세기',
        'haptics_gain': '네이티브 햅틱 세기. 오디오햅틱 끔에서만 조절. Mix·Replace로 바꾸면 기본값 1을 적용 대기',
        'usb_gamepad_mode': '켜면 XInput · 끄면 DualSense 또는 Edge. 모드 적용 시 USB 재연결',
    })

LABELS['speaker_gain']=_ui_tr('듀얼센스 스피커 증폭')
TITLES['Native Haptics Filter']=_ui_tr('햅틱 질감')
DESCRIPTIONS['speaker_gain']=_ui_tr('음량이 부족할 때 조절\n높이면 왜곡될 수 있음')

LABELS['disable_inactive_disconnect']=_ui_tr('자동 연결 해제 안함')
DESCRIPTIONS['mix_native_level']=_ui_tr('게임이 보낸 네이티브 햅틱을 함께 출력\n적용하면 DS5Light의 오디오를 앞 채널로 전송')

DESCRIPTIONS['ps_shortcut_enabled']=_ui_tr('PS 기본 단축키: 짧게 Win+G, 길게 Win+Tab. 켜져 있으면 PS를 포함한 Pico 매핑·시프트 조합은 비활성화됩니다. 해당 매핑을 사용하려면 기본 단축키를 끄세요.')

LABELS['ps_shortcut_enabled']=_ui_tr('PS 기본 단축키')
