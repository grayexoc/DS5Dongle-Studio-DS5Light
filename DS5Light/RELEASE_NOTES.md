# v1.2.5

### English

Use `DS5Light-win-x64-v1.2.5.zip` with `ds5-studio-light_v56.uf2` for Raspberry Pi Pico 2 W.

- **Audio haptics.** Refined the onset of short impacts in firmware DSP. Native haptics restore the controller output state when audio resumes, and selected-process capture drops fully expired audio packets while preserving recent samples.
- **Mapping and Shift layer.** The mapping list uses two columns with a customizable display order. Saving a new mapping also activates it in the current profile, with a single Pico reconnection to verify both changes. Enable it separately in other profiles. Active mappings and the assigned Shift key are highlighted in gold.
- **Studio settings and backups.** Fixed a false reconnection timeout after saving. Studio v56 supports reading stored profile fields in batches and checks whether the slot list changes during backup. The app warns before leaving Studio settings with unapplied edits.
- **Language.** The language selector is now under **Settings & diagnostics → Launch options**. Changes apply after restarting the app.

**If you’re using DS5Light for the first time or upgrading from a version earlier than v1.2.2**, we strongly recommend applying the updated Mix or Replace preset under **Studio settings → Profile slots → Recommended presets** before using audio haptics. Back up the destination slot before saving.

Windows and game volume affect haptic strength. Use the bundled Mix and Replace presets as starting points.

### 한국어

Windows 앱 `DS5Light-win-x64-v1.2.5.zip`과 Raspberry Pi Pico 2 W용 펌웨어 `ds5-studio-light_v56.uf2`를 함께 사용하세요.

- **오디오햅틱.** 펌웨어 DSP에서 짧은 타격의 시작 반응을 다듬었습니다. 오디오가 다시 들어오면 네이티브 햅틱의 출력 상태를 복원하고, 선택한 프로세스 캡처에서는 오래된 패킷만 버려 최신 샘플을 유지합니다.
- **매핑과 시프트 레이어.** 매핑 목록을 2열로 표시하고 순서를 바꿀 수 있습니다. 새 매핑을 저장하면 현재 프로필에서도 활성화하고, Pico 재연결 한 번으로 두 결과를 확인합니다. 다른 프로필에서는 별도로 활성화하세요. 활성 매핑과 지정된 시프트키는 금색으로 표시합니다.
- **Studio 설정과 백업.** 저장 뒤 Pico가 정상 응답해도 재연결 확인이 시간 초과되던 문제를 수정했습니다. Studio v56은 저장된 프로필의 설정값을 묶어서 읽고, 백업 도중 슬롯 목록이 바뀌었는지 확인할 수 있습니다. 미적용 편집값이 있는 상태에서 Studio 설정을 벗어날 때 안내합니다.
- **언어 설정.** 언어 선택을 **설정·진단 → 실행 옵션**으로 옮겼습니다. 변경한 언어는 앱을 다시 시작하면 적용됩니다.

처음 사용하거나 **v1.2.2보다 오래된 버전에서 업그레이드하는 경우**, 오디오햅틱을 사용하기 전에 **Studio 설정 → 프로필 슬롯 → 추천 프리셋**에서 변경된 믹스 또는 대체 프리셋을 다시 적용할 것을 강력히 권장합니다. 저장하기 전에 대상 슬롯을 백업하세요.

햅틱 세기는 Windows와 게임 음량의 영향을 받습니다. 동봉된 믹스와 대체 프리셋을 시작점으로 사용할 수 있습니다.

# v1.2.4

### English

Use `DS5Light-win-x64-v1.2.4.zip` with `ds5-studio-light_v55.uf2` for Raspberry Pi Pico 2 W.

**If you’re using DS5Light for the first time or upgrading from a version earlier than v1.2.2**, we strongly recommend applying the updated Mix or Replace preset under **Studio settings → Profile slots → Recommended presets** before using audio haptics. Back up the destination slot before saving.

- Improved Studio device discovery and reconnection. The app can detect when HID devices arrive or are removed, and it retains draft settings when reconnecting.
- Added profile slot deletion on supported firmware. Before saving or deleting a slot, the app and firmware check whether the relevant settings or slot list have changed. The app also reports which settings it could verify after backup restoration.
- Improved selected-process audio capture recovery and refined idle disconnect handling for touchpad and gyro activity. When dock disconnect is enabled, the firmware briefly delays applying it so the settings response can be returned.

Windows and game volume affect haptic strength. The bundled Mix and Replace presets can be used as starting points.

### 한국어

Windows 앱 `DS5Light-win-x64-v1.2.4.zip`과 Raspberry Pi Pico 2 W용 Studio 펌웨어 `ds5-studio-light_v55.uf2`를 함께 사용하세요.

처음 사용 혹은 **v1.2.2보다 오래된 버전에서 업그레이드하는 경우**, 오디오햅틱을 사용하기 전에 **Studio 설정 → 프로필 슬롯 → 추천 프리셋**에서 변경된 믹스 또는 대체 프리셋을 다시 적용할 것을 강력히 권장합니다. 저장하기 전에 대상 슬롯을 백업하세요.

- Studio 장치 검색과 재연결을 개선했습니다. 앱이 HID 장치 연결·해제를 감지하고, 다시 연결할 때 편집 중인 설정을 보관합니다.
- 지원 펌웨어에서 프로필 슬롯 삭제를 추가했습니다. 슬롯을 저장하거나 삭제하기 전 관련 설정이나 슬롯 목록이 바뀌었는지 확인하고, 백업 복원 후 어떤 설정을 확인했는지 표시합니다.
- 선택한 프로세스의 오디오 캡처 복구를 보완하고, 터치패드·자이로 동작이 유휴 연결 해제 판정에 반영되도록 개선했습니다. 충전독 연결 해제 설정을 켤 때는 설정 응답을 보낼 수 있도록 해제를 잠시 지연합니다.

햅틱 세기는 Windows와 게임 음량의 영향을 받습니다. 동봉된 믹스와 대체 프리셋을 시작점으로 사용할 수 있습니다.

# v1.2.3

### English

Use `DS5Light-win-x64-v1.2.3.zip` with `ds5-studio-light_v54.uf2` for Raspberry Pi Pico 2 W.

**Upgrading from a version earlier than v1.2.2?** We strongly recommend reapplying the updated Mix or Replace preset under **Studio settings → Profile slots → Recommended presets** before using audio haptics. Back up the destination slot before saving.

- When a profile switches between DualSense and Xbox mode, the app can recover the same Pico's control connection after USB re-enumeration. Automatic audio selection requires matching device evidence. If the available evidence is incomplete, confirm the output in the app.
- Restoring a slot backup keeps the active profile selected and restores the live settings after the operation. Studio v54 is required for this restore behavior.
- Mix and Replace with Front input separate deep bass and short impact textures more clearly. The firmware also reduces speaker encoding work during sustained mute.

Windows and game volume affect haptic strength. The bundled Mix and Replace presets provide starting points.

### 한국어

Windows 앱 `DS5Light-win-x64-v1.2.3.zip`과 Raspberry Pi Pico 2 W용 Studio 펌웨어 `ds5-studio-light_v54.uf2`를 함께 사용하세요.

**v1.2.2보다 오래된 버전에서 업그레이드하는 경우**, 오디오햅틱을 사용하기 전에 **Studio 설정 → 프로필 슬롯 → 추천 프리셋**에서 변경된 믹스 또는 대체 프리셋을 다시 적용할 것을 강력히 권장합니다. 저장하기 전에 대상 슬롯을 백업하세요.

- 프로필이 DualSense와 Xbox 모드 사이에서 전환되면 USB 재인식 후 같은 Pico의 설정 연결을 복구할 수 있습니다. 같은 장치라는 근거가 있을 때 오디오 출력을 자동 선택합니다. 장치 식별 정보가 부족하면 앱에서 출력을 확인하세요.
- 슬롯 백업을 복원할 때 현재 활성 프로필의 선택을 유지하고, 작업 후 복원 전의 실시간 설정으로 돌아갑니다. 이 복원 기능에는 Studio v54가 필요합니다.
- 전방 입력을 사용하는 믹스와 대체에서 깊은 저음과 짧은 타격의 질감 차이를 키웠습니다. 스피커 음소거가 이어질 때 펌웨어의 인코딩 작업도 줄였습니다.

햅틱 세기는 Windows와 게임 음량의 영향을 받습니다. 동봉된 믹스와 대체 프리셋을 시작점으로 사용할 수 있습니다.

# v1.2.2

### English

Pair `DS5Light-win-x64-v1.2.2.zip` with `ds5-studio-light_v53.uf2` for Raspberry Pi Pico 2 W.

**For audio haptics, we strongly recommend applying the updated recommended preset as your starting configuration, including if you used the previous version.** In Studio profile slot settings, apply Mix or Replace. Turn on the PC filter, set intensity to 1× and use the matching slider marks.

- Mix combines front-channel audio haptics with game rumble. Start with 40% background reduction and 90% impact preservation. Replace uses front-channel audio haptics alone. Start with 50% and 95%, respectively.
- Updated the bundled Studio profiles, added Mix and Replace markers to the filter sliders, and improved English labels and spacing. The presets apply the haptic high-pass setting on supported firmware.
- Reduced repeated filter calculations in the app and firmware, eliminated temporary allocations when reading cached USB HID reports, and reduced packet copying when the oldest Bluetooth audio packet must be discarded.

Windows and game volume both affect haptic strength. The recommendations assume other settings are at their defaults.

### 한국어

Windows 앱 `DS5Light-win-x64-v1.2.2.zip`과 Raspberry Pi Pico 2 W용 펌웨어 `ds5-studio-light_v53.uf2`를 함께 사용하세요.

**오디오햅틱을 사용할 때는 변경된 추천 프리셋을 기본 설정으로 적용할 것을 강력히 권장합니다. 이전 버전의 프리셋을 사용 중인 경우에도 새 프리셋을 다시 적용해 주세요.** Studio의 프로필 슬롯 설정에서 믹스 또는 대체를 적용한 뒤, PC 필터를 켜고 세기를 1배로 설정하고 슬라이더를 해당 모드의 눈금에 맞춰 주세요.

- 믹스는 전방 채널에서 만든 오디오햅틱에 게임의 일반 진동을 섞습니다. 배경 억제 40%, 충격 보존 90%를 권장합니다. 전방 오디오햅틱만 출력하는 대체 모드는 배경 억제 50%, 충격 보존 95%를 권장합니다.
- 동봉 Studio 프로필을 갱신하고 앱 필터 슬라이더에 믹스·대체 권장 위치를 표시했습니다. 영문 탭과 눈금의 글자 간격을 다듬었으며, 지원 펌웨어에서는 프리셋 적용 시 극저음 차단 설정도 반영됩니다.
- 앱과 펌웨어의 필터 반복 연산을 줄였습니다. 캐시된 USB HID 응답의 임시 메모리 할당을 없애고, Bluetooth 혼잡 시 맨 앞의 오디오 패킷을 폐기하는 데 필요한 복사를 줄였습니다.

햅틱 세기는 Windows 볼륨과 게임 볼륨 모두의 영향을 받습니다. 권장값은 그 밖의 설정이 기본값인 경우를 기준으로 합니다.

# v1.2.1

The Windows x64 package `DS5Light-win-x64-v1.2.1.zip` pairs with Studio v52 for Raspberry Pi Pico 2 W. Use the app and firmware from this release together.

- **Follow-up impacts.** Improved quieter-impact detection after a stronger hit in Mix/Front and Replace/Front, while suppressing repeated texture triggers from sustained bass.
- **Rear haptics.** Preserved sustained bass when treble is present, stabilized left/right balance during continuous effects, and retained weaker samples through rounded output conversion.
- **App strength and speaker audio.** Shared output applies app gain only when Studio confirms controller-speaker auto-mute. Otherwise it stays at 1x. Exclusive Rear applies app gain only to the rear haptic signal.
- **Native Mix and smoothing.** Native leakage filtering uses a fixed 120 Hz low-pass independently of the generated-haptics cutoff. Native-mode AA is selectable, with new defaults set to Off; existing saved profiles keep their selected values.
- **Startup and reconnection.** Whole-device automatic capture no longer depends on the process list. After USB reconnection, the app waits up to eight seconds for the same Pico's four-channel output and follows the latest start request. Two-channel recognition now has a specific setup message.
- **Transitions and efficiency.** Reset affected DSP state when changing modes or input routes, reduced duplicate processing, and reused rear-control ramp data.
- **UI and diagnostics.** Clarified Korean and English guidance and gain tooltips, aligned default/recommended slider markers, and separated rear-queue and WASAPI-write timing displays.
- **Experimental cleanup.** Removed the AI prototype, pitch-matching and generic metal-detection paths. Retired speaker-accent controls and rendering are disabled, including profiles that previously enabled them.

**Recommended preset setup**

After updating, we recommend reviewing and applying a supplied Mix or Replace preset under **Studio settings → Profile slots → Recommended presets**, then adjusting it to the game and your preference. Start with the app filter enabled, background reduction at 55%, and app strength at **1x (100%)**. Both presets use Front input; Mix also combines the game's raw rear native haptics.

Existing saved slots retain their settings. Stop dongle audio and back up the destination slot before **Save and use**. This writes the current configuration with the preset's audio-haptics settings to that slot, replacing its previous contents.

Use these recommended presets as the reference when comparing audio-haptics changes. Perceived response varies with Windows and game/application volume. Unless otherwise specified, other settings assume their defaults. If controller-speaker auto-mute is off or unconfirmed on shared output, the app stays at 1x; adjust **Audio Haptics Strength in Studio settings** instead.

## 한국어

Windows x64용 `DS5Light-win-x64-v1.2.1.zip`은 Raspberry Pi Pico 2 W용 Studio v52와 함께 사용합니다. 이번 릴리즈의 앱과 펌웨어를 함께 사용하세요.

- **후속 타격 보완.** Mix/Front·대체/Front에서 강한 타격 뒤의 작은 타격 검출을 개선하고, 지속 저음에서 타격 질감이 반복 발동하는 것을 억제했습니다.
- **Rear 햅틱 개선.** 고음이 함께 재생돼도 지속 저역을 유지하고, 연속 효과의 좌우 출력 비율을 안정화했습니다. 최종 출력 반올림으로 약한 신호의 손실도 줄였습니다.
- **앱 세기와 스피커 출력 처리.** 공유 출력은 Studio의 패드 스피커 자동 음소거가 확인될 때 앱 배율을 적용합니다. 그 외에는 1x로 출력합니다. 독점 Rear에서는 앱 세기가 후방 햅틱 신호에만 적용됩니다.
- **네이티브 Mix·질감 조절.** 네이티브 누설 억제를 고정 120 Hz 저역통과 필터로 분리했습니다. 네이티브 모드에서도 AA를 선택할 수 있으며 새 기본값은 끔입니다. 기존 저장 프로필은 저장된 값을 사용합니다.
- **시작·재연결 보완.** 전역 캡처 자동 시작이 게임 목록 조회에 영향을 받지 않도록 수정했습니다. USB 재연결 후 같은 Pico의 4채널 출력이 나타날 때까지 최대 8초간 확인하며 최신 시작 요청을 따릅니다. 2채널로 인식된 경우에는 별도 설정 안내를 표시합니다.
- **전환·연산 개선.** 모드·입력 경로 전환 시 관련 DSP 상태를 초기화하고, 중복 연산과 Rear 램프 생성 작업을 줄였습니다.
- **UI·진단 보완.** 한·영 안내와 세기 툴팁을 다듬고 기본·추천 슬라이더 표시를 정리했습니다. Rear 큐 대기와 WASAPI 쓰기 시간을 구분해 표시합니다.
- **실험 기능 정리.** AI 시제품, 피치 매칭과 일반 금속음 판정 경로를 제거했습니다. 스피커 순간음 실험의 조작부와 출력을 정리했으며 이전에 켠 프로필에서도 끔으로 처리합니다.

**추천 프리셋 적용 안내**

업데이트 후 **Studio 설정 → 프로필 슬롯 → 추천 프리셋**에서 동봉 Mix·Replace 프리셋을 확인하고 적용해 보는 것을 권장합니다. **앱 필터 켬·배경 억제량 55%·앱 세기 1x(100%)**를 시작점으로 삼아 게임과 취향에 맞게 조절하세요. 두 프리셋 모두 Front 입력을 사용하며 Mix는 게임의 Rear 네이티브 햅틱 원본도 혼합합니다.

기존 저장 슬롯은 자동으로 바뀌지 않습니다. 동글 오디오 전송을 멈추고 대상 슬롯을 백업한 뒤 **저장 후 사용**을 선택하세요. 현재 구성에 프리셋의 오디오 햅틱 설정을 반영한 결과로 대상 슬롯을 덮어씁니다.

오디오 햅틱의 개선 사항은 이 추천 프리셋을 기준으로 확인해 주세요. 체감은 Windows 음량과 게임·앱 음량에 영향을 받으며, 별도 안내가 없는 기타 설정은 기본값을 기준으로 합니다. 공유 출력에서 패드 스피커 자동 음소거가 꺼져 있거나 확인되지 않으면 앱 출력은 1x로 유지되므로 **Studio 설정의 오디오햅틱 세기**를 조절하세요.


---

# v1.2.0

The Windows x64 package `DS5Light-win-x64-v1.2.0.zip` pairs with Studio v51 for Raspberry Pi Pico 2 W. Use the app and firmware from this release together.

- **Impact texture.** Added brief harmonic shaping to audio-generated haptics. Low-dominant hits adjust the blend and decay, while sustained bass is guarded against repeated artificial attacks.
- **Left/right impact response.** Adjusted the initial impact blend using the relative rise of each channel.
- **Low-band output.** Refined sustained bass handling and transitions between continuous vibration and short impacts.
- **Lighting controls.** Clarified Pico LED On/Off selection and improved fixed-color selection and lightbar state handling.
- **Studio settings.** Improved profile-slot loading, expandable slot lists, search-result context, and control layout.
- **Capture and UI.** Refined process-list CPU sampling, reduced unnecessary updates, and adjusted Korean and English labels and guidance.

Use the recommended presets under Studio profile-slot settings as the reference when comparing audio-haptics changes. The perceived response varies with Windows volume and game/application volume. Unless otherwise specified, other settings assume their defaults.

Back up the destination Studio slot before applying a preset or saving over an existing profile.

## 한국어

Windows x64용 DS5Light v1.2.0은 Raspberry Pi Pico 2 W용 Studio v51과 함께 사용합니다. 이번 릴리즈의 앱과 펌웨어를 함께 사용하세요.

- **타격 질감 처리 추가.** 오디오 햅틱의 타격 시작 구간에 짧은 고조파 성분을 혼합합니다. 저역이 우세한 타격은 혼합량과 감쇠를 조절하고, 지속 저음에서 인위적인 타격이 반복되는 것을 억제합니다.
- **좌우 타격 반응 조정.** 양쪽 채널의 상승량을 비교해 타격 시작 시 혼합 비율에 반영합니다.
- **저역 출력 보완.** 지속적인 저음과 짧은 타격 사이의 출력 처리를 다듬었습니다.
- **조명 설정 개선.** Pico LED 켜기·끄기 선택을 명확히 하고 고정 색상 선택과 라이트바 상태 처리를 보완했습니다.
- **Studio 설정 개선.** 프로필 슬롯 로딩, 슬롯 목록 펼치기, 검색 결과의 소속 표시와 조작부 배치를 개선했습니다.
- **캡처·UI 보완.** 프로세스 목록의 CPU 사용량 조회와 불필요한 갱신을 조정하고 한·영 표현과 안내를 다듬었습니다.

오디오 햅틱의 개선 사항은 Studio 프로필 슬롯 설정의 추천 프리셋을 기준으로 확인해 주세요. 체감은 Windows 음량과 게임·앱의 음량 설정에 따라 달라집니다. 별도로 안내한 항목 외의 설정은 기본값을 기준으로 합니다.

프리셋 적용이나 기존 프로필 덮어쓰기 전에 대상 Studio 슬롯을 백업하세요.


---

# v1.1.1

The Windows x64 package `DS5Light-win-x64-v1.1.1.zip` pairs with Studio v50 for Raspberry Pi Pico 2 W. Use the app and firmware from this release together.

- **Rear control and sustained effects.** Preserved low-band continuous haptic output alongside short impacts. Persistent left/right energy differences can steer sustained rear control, while protected impacts retain priority.
- **Filter switching.** Select the Studio rear-control route only while the PC filter is enabled. A filter change that requires a different output route stops capture and asks for a restart.
- **Audio buffering.** Shortened live input collection and limited queued playback in the exclusive renderer to reduce unnecessary buffering.
- **Native haptics.** Adjusted native sample rounding and restarted the Mix low-pass from the current signal after bypass or stream reset.
- **Rear-control settings.** Adjusted the gate transition for PC-generated rear control. The app disables the firmware high-pass control while that route bypasses it and explains why.
- **UI responsiveness.** Reduced repeated redraws during slider adjustment and background status updates, and refined tab spacing and filter guidance.
- **Input processing.** Removed unnecessary square-root calculations from Flick Stick threshold checks and bypassed the power function for a linear stick-to-mouse curve.

The updated Mix and Replace presets remain available in Studio settings. If updating from an older setup, review a supplied preset with the app filter enabled and strength at 100% as a starting point, then adjust it to your game and preference. Stop dongle audio and back up the destination slot before **Save and use**, which overwrites that slot.

## 한국어

Windows x64용 DS5Light v1.1.1은 Raspberry Pi Pico 2 W용 Studio v50과 함께 사용합니다. 이번 릴리즈의 앱과 펌웨어를 함께 사용하세요.

- **Rear 제어·지속 진동 보완.** 짧은 타격과 함께 저역의 지속적인 햅틱 출력을 유지하도록 조정했습니다. 좌우 에너지 차이가 지속되면 연속 Rear 제어에 방향을 반영하며, 보호된 타격 처리를 우선합니다.
- **필터 전환 처리.** PC 필터가 켜져 있을 때 Studio Rear 제어 경로를 선택합니다. 필터 변경으로 출력 경로가 달라지면 캡처를 정지하고 다시 시작하도록 안내합니다.
- **오디오 버퍼링 조정.** 실시간 입력을 모으는 대기 구간을 줄이고 전용 출력의 대기 오디오 양을 제한했습니다.
- **네이티브 햅틱 처리.** 네이티브 샘플의 반올림을 조정하고, 우회·스트림 초기화 후 Mix 저역통과 필터가 현재 신호에서 시작하도록 수정했습니다.
- **Rear 제어 설정 보완.** PC Rear 제어의 게이트 전환을 조정했습니다. 해당 경로에서 우회되는 펌웨어 극저음 차단 옵션은 앱에서 비활성화하고 이유를 표시합니다.
- **UI 응답성 개선.** 슬라이더 조절과 백그라운드 상태 갱신 중 반복 그리기를 줄이고 탭 간격과 필터 안내를 다듬었습니다.
- **입력 연산 정리.** Flick Stick 임계값 판정의 불필요한 제곱근 계산을 제거하고, 스틱 마우스가 선형 곡선일 때 거듭제곱 계산을 생략합니다.

변경된 Mix·Replace 프리셋은 Studio 설정에서 사용할 수 있습니다. 이전 설정에서 업데이트한다면 앱 필터 켬·세기 100%를 시작점으로 동봉 프리셋을 확인하고 적용한 뒤 게임과 취향에 맞게 조절하는 것을 권장합니다. 저장 전 동글 오디오를 멈추고 대상 슬롯을 백업하세요. **저장 후 사용**은 대상 슬롯을 덮어씁니다.


---

# v1.1.0

DS5Light v1.1.0 for Windows x64 pairs with Studio v49 for Raspberry Pi Pico 2 W. Back up your Studio slots before updating and use the app and firmware from this release together.

- **Audio haptics filtering.** Improved protection for quieter hits following louder effects and refined suppression of sustained background audio. The active filter focuses haptic output on the low bands.
- **Studio haptic output.** Added low-band control output with attack shaping and stereo steering when the captured stereo signal provides sufficient directional evidence.
- **Sub-bass filtering.** Added a second-order high-pass filter to reduce very low-frequency content when generating haptics from audio. Refined the crossover in the 24 dB/oct low-pass path.
- **Output protection.** Added adaptive PC gain handling to reduce overload and gradually recover toward the configured strength.
- **Settings synchronization and diagnostics.** Improved detection of external Studio setting changes and guards for preview, apply, and restore operations. Expanded channel and output-route diagnostics.
- **Touchpad mouse settings.** Exposed touchpad mouse operation, movement speed, small-motion rejection, axis inversion, trackball inertia, and friction in Studio settings.
- **Updated haptic presets.** Revised the supplied Mix and Replace presets for the updated audio-haptics path. Mix preserves the raw rear native-haptics signal alongside front audio haptics; Replace generates haptics from front audio. Existing saved slots retain their settings.
- **UI improvements.** Removed the processing-mode selector and refined English labels, wrapping, and control placement.

After updating, we recommend reviewing and applying an included audio-haptics preset as a starting point, with the app filter enabled and app strength at 100%, then adjusting it to your game and preference. Stop dongle audio before saving. Back up the destination slot first: **Save and use overwrites that slot with the current configuration plus the preset's audio-haptics settings.**

## 한국어

Windows x64용 DS5Light v1.1.0은 Raspberry Pi Pico 2 W용 Studio v49와 함께 사용합니다. 업데이트 전 Studio 슬롯을 백업하고, 이번 릴리즈의 앱과 펌웨어를 함께 사용하세요.

- **오디오 햅틱 필터 개선.** 강한 효과 뒤에 이어지는 작은 타격의 보호 처리를 보완하고 지속적인 배경음 억제를 조정했습니다. 활성 필터는 저역을 중심으로 햅틱 출력을 생성합니다.
- **Studio 햅틱 출력 개선.** 저역 기반 제어 출력과 타격 시작 구간의 파형 처리를 추가했습니다. 스테레오 캡처 신호에서 충분한 좌우 차이가 확인되면 방향을 반영합니다.
- **극저음 차단 추가.** 오디오에서 햅틱을 생성할 때 과도한 극저음을 줄이는 2차 하이패스 필터를 추가했습니다. 24 dB/oct 저역통과 경로의 크로스오버 처리도 조정했습니다.
- **출력 보호 개선.** 과도한 출력을 줄이고 신호에 여유가 생기면 설정한 세기로 서서히 복귀하는 PC 게인 적응 처리를 추가했습니다.
- **설정 동기화·진단 보완.** 외부에서 변경된 Studio 설정의 감지를 개선하고 미리보기·적용·복구 과정의 상태 확인을 보강했습니다. 채널별 신호와 출력 경로의 진단 정보도 확장했습니다.
- **터치패드 마우스 설정 표시.** Studio 설정에서 터치패드 마우스 사용, 이동 속도, 미세 움직임 차단, 방향 반전, 트랙볼 관성과 감속을 조절할 수 있도록 표시했습니다.
- **햅틱 프리셋 변경.** 변경된 처리 경로에 맞춰 동봉 Mix·Replace 프리셋을 조정했습니다. Mix는 Front 오디오 햅틱과 Rear 네이티브 햅틱 원본을 함께 사용하고, Replace는 Front 오디오로 햅틱을 생성합니다. 기존 저장 슬롯에는 이전 설정이 유지됩니다.
- **UI 개선.** 처리 모드 선택을 제거하고 영문 표현, 줄바꿈과 조작부 배치를 다듬었습니다.

업데이트 후 동봉 오디오 햅틱 프리셋을 확인하고 적용해 보는 것을 권장합니다. 앱 필터를 켜고 앱 세기 100%를 시작점으로 삼아 게임과 취향에 맞게 조절하세요. 저장 전 동글 오디오 전송을 멈추고 대상 슬롯을 백업하세요. **저장 후 사용은 현재 구성에 프리셋의 오디오 햅틱 설정을 반영한 결과로 대상 슬롯을 덮어씁니다.**


---

# v1.0.19 — Studio reliability and restore recovery / Studio 안정성과 복원 복구

DS5Light-win-x64-v1.0.19.zip · ds5-studio-light_v48.uf2 (Pico 2 W)

- With matching firmware, macros automatically resume if DS5Light stops renewing the pause during a Studio slot restore.
- 지원 펌웨어에서는 Studio 슬롯 복원 도중 DS5Light가 종료되어 일시정지 갱신이 끊겨도 매크로가 자동으로 재개됩니다.

- Studio now limits automatic restarts after repeated wireless initialization failures and logs the error and recovery steps over UART. Repeated Bluetooth control errors are logged at most once per second.
- Studio에서 무선 초기화가 연이어 실패하면 자동 재부팅 횟수를 제한하고 UART에 오류와 복구 절차를 기록합니다. 반복되는 Bluetooth 제어 오류는 초당 한 번까지만 기록합니다.

- Save game presets and export Studio profiles, mappings, and slot backups in the background. Update the preset list only after a successful write, and keep the existing export if it cannot be replaced.
- 게임 프리셋 저장과 Studio 프로필·매핑·슬롯 백업 내보내기를 백그라운드로 옮겼습니다. 저장에 성공한 후 프리셋 목록을 갱신하며, 파일 교체에 실패하면 기존 내보내기 파일을 보존합니다.

- Save last-used settings and read Studio JSON in the background. Open clipped status messages in full, and see when an older preset's audio haptics strength is adjusted to 50%.
- 마지막 사용 설정 저장과 Studio JSON 읽기를 백그라운드로 옮겼습니다. 잘린 상태 메시지는 전체 내용을 열 수 있으며, 예전 프리셋의 오디오햅틱 세기를 50%로 보정하면 안내합니다.

- Continue booting when a slot or macro flash recovery record is damaged. Block further slot and macro writes while keeping the recovery record for inspection.
- 슬롯·공유 매크로의 플래시 복구 기록이 손상돼도 부팅을 계속합니다. 복구 기록을 보존하고 해당 부팅에서 슬롯·공유 매크로 쓰기를 제한합니다.
- Skip the redundant erase of an already clean flash metadata page when saving slots or macros.
- 슬롯·매크로 저장 시 복구 메타데이터 페이지가 이미 비어 있으면 중복 소거를 생략합니다.

- If a device operation delays shutdown, choose whether to keep waiting or close DS5Light with the operation unconfirmed.
- 장치 작업 응답이 늦어 종료가 지연되면 계속 기다리거나 작업 결과를 미확인 상태로 두고 앱을 닫을 수 있습니다.

- Detect settings changes during supported Studio reads and pre-apply checks, even when the profile stays the same.
- 지원 펌웨어에서는 같은 프로필이 유지되더라도 조회 또는 적용 준비 중 설정이 바뀌면 다시 읽도록 안내합니다.

- Distinguish unsupported Studio fields from valid zero values. A failed firmware settings packet now leaves its fields unchanged.
- Studio 미지원 필드를 실제 설정값 0과 구분합니다. 묶음 설정 패킷이 실패하면 해당 패킷의 값은 적용되지 않습니다.

- Report a DualSense connection only after the selected Pico confirms that its Bluetooth HID channels are ready.
- 선택한 Pico에서 Bluetooth HID 준비 상태가 확인될 때 DualSense 연결을 표시합니다.

- Reset the old speaker, microphone, and haptics state on a USB reset or detach so the next audio session starts cleanly.
- USB 리셋이나 연결 해제 시 이전 스피커·마이크·햅틱 상태를 초기화해 다음 오디오 세션에 남지 않도록 합니다.

- End macro suspension when the Pico USB session ends. Recover controller input and clear old Feature reports when either Bluetooth HID channel closes. Retry XInput rumble reception if the OUT endpoint fails to rearm.
- Pico USB 연결이 끝나면 매크로 일시정지를 해제합니다. Bluetooth HID 채널이 끊기면 입력을 초기화하고 이전 Feature 응답을 비웁니다. XInput OUT 재등록이 실패하면 진동 수신을 다시 시도합니다.

- Clean up the process capture helper if startup fails. Navigate the main tabs with the keyboard. Omit device identifier fields from exported diagnostics.
- 프로세스 캡처 시작에 실패하면 헬퍼를 정리합니다. 키보드로 상단 탭을 이동할 수 있으며, 진단 파일에는 장치 식별 필드를 제외합니다.

- **Studio restore.** Save a backup of the target slots and shared macros before writing. If a restore stops partway through, report confirmed saves, the unconfirmed slot, and where to find the backup.
- **Studio 복원.** 쓰기 전에 대상 슬롯과 공유 매크로를 백업합니다. 복원이 중단되면 저장을 확인한 슬롯, 미확인 슬롯, 백업 파일 위치를 표시합니다.

- **Studio saves.** Match each profile, macro, and device policy save to its own firmware response. These saves require the paired Studio firmware.
- **Studio 저장.** 프로필·매크로·Pico 공통 설정을 저장할 때 해당 요청의 펌웨어 응답을 확인합니다. 이 저장 기능은 함께 제공되는 Studio 펌웨어가 필요합니다.

- **Studio settings.** Verify the profile and changed settings after reconnect before confirming a save. If they differ, keep the edits and ask the user to refresh.
- **Studio 설정.** 재연결 후 프로필과 변경값을 확인한 뒤 저장 결과를 표시합니다. 값이 다르면 편집값을 유지하고 새로 고침을 안내합니다.

- **Studio USB.** Keep device identity and descriptors consistent during each USB attachment. Apply late DualSense Edge detection on the next enumeration.
- **Studio USB.** 한 번의 USB 연결에서 장치 식별 정보와 디스크립터를 일관되게 유지합니다. 늦게 확인된 DualSense Edge는 다음 열거에 반영합니다.

- **Studio firmware.** Remove Bluetooth pairing-key bytes from the HCI log. Stored-key and missing-key responses retain their existing behavior. Hardware UART verification is pending.
- **Studio 펌웨어.** HCI 로그의 Bluetooth 페어링 키 바이트 출력을 제거했습니다. 저장된 키가 있을 때와 키가 없을 때의 응답은 유지합니다. 실기기 UART 확인은 남아 있습니다.

# v1.0.18 — Audio processing and Studio connection fixes / 오디오 처리·Studio 연결 개선

DS5Light-win-x64-v1.0.18.zip · ds5-studio-light_v47.uf2 (Pico 2 W)

- **Audio processing.** Load SciPy when PC suppression first needs it, reduce filter overhead and handle sustained process-capture backlog. Audio haptics strength now ranges from 50% to 200%, with a 100% default.
- **Studio settings and discovery.** Simplify Mix controls, improve initial profile discovery and reduce unnecessary updates while monitoring mappings. Remember slot history for each Pico.
- **Studio v47.** Improve Bluetooth disconnection, input reset, Edge detection and USB recovery. Separate Pico command replies from controller replies. Improve microphone cutoff and delivery of the mapped power-off command when the Bluetooth queue is full.

- **오디오 처리.** PC 억제 필터가 처음 필요할 때 SciPy를 불러오고 필터 처리 부담을 줄였습니다. 선택한 프로세스 캡처에서 버퍼 밀림을 보정합니다. 오디오 햅틱 세기는 50~200%이며 기본값은 100%입니다.
- **Studio 설정과 장치 인식.** Mix 설정 배치를 정리하고 최초 프로필 인식을 개선했습니다. 매핑 입력 확인 중 불필요한 화면 갱신을 줄이고, Pico별 슬롯 이력을 기억합니다.
- **Studio v47.** Bluetooth 연결 해제와 입력 중립화, Edge 판별 및 USB 재인식을 보완했습니다. Pico 명령 응답과 컨트롤러 응답을 분리했고, 마이크 차단과 Bluetooth 큐 포화 시 전원 끄기 매핑의 전달을 개선했습니다.

# v1.0.17 — Process capture and haptic strength / 프로세스 캡처·햅틱 세기

DS5Light-win-x64-v1.0.17.zip · App-only update / 앱 단독 업데이트

- Use a moving average of buffered frames to detect and reduce sustained backlog in process capture.
- Set the top audio haptics slider to 50–200%, with 100% as the default. Older values below 50% load at 50%.
- 프로세스별 캡처에서 버퍼량의 이동평균으로 누적 대기를 감지하고 보정합니다.
- 상단 오디오햅틱 세기는 50~200%, 기본값은 100%입니다. 기존 50% 미만 설정은 50%로 불러옵니다.

# v1.0.16 — Initial discovery and resource use / 최초 인식·자원 사용 개선

DS5Light-win-x64-v1.0.16.zip · App-only update / 앱 단독 업데이트

- Reduce single-section filter processing overhead while preserving tested PCM output.
- Keep last observed mapping input/output; skip unchanged redraws and pause hidden monitoring.
- Probe current profile first during a bounded initial connection window. Reuse per-Pico slot history in preferences.json; live state still comes from the device.
- Preserve older preferences and discard only malformed optional history. Invalidate slot history after slot writes/restores.
- 필터 연산 및 입력 확인 갱신 최적화. 최초 연결 탐색과 기존 설정 파일 내 Pico별 슬롯 기록 추가.
- Firmware is not rebuilt or flashed. 펌웨어 빌드·기록 및 실기기 지연 측정은 수행하지 않음.

# v1.0.15 — Mapping saves and input checks / 매핑 자동 저장·입력 확인

DS5Light-win-x64-v1.0.15.zip · ds5-studio-light_v45.uf2 (Pico 2 W)

- Save completed mapping edits, deletion, imports and shift-key changes automatically. Verify Pico reconnection before updating profile activation; show progress and offer export recovery on failure.
- Add observed-button history, last-report age, touch-click qualification and first-key diagnostics. Recover cleanly when input monitoring cannot start.
- Store USB serial hiding as a Pico-wide setting; preserve explicit choices across profiles and show compatibility advice for Edge when hiding is off. Explain Windows default audio output as a possible save restriction.
- Studio v45 adds the versioned OLED title scroll and protects the last complete settings copy across repeated interrupted writes. Native/XInput support remains integrated; the default profile remains Native.

- 매핑 편집 완료·삭제·가져오기·시프트키 변경을 자동 저장합니다. Pico 재연결 확인 후 프로필 사용 체크를 처리하고 진행 상태와 실패 시 내보내기 복구 경로를 표시합니다.
- 감지 버튼 이력·마지막 수신 시각·터치 클릭 판정·키보드 첫 키 표시를 추가하고 입력 확인 시작 실패 후 상태 복구를 보완했습니다.
- USB 시리얼 숨기기를 Pico 공통 설정으로 저장하며 프로필 전환 후에도 선택을 유지합니다. Edge 권장 안내와 Windows 기본 오디오 출력에 따른 저장 제한 안내를 추가했습니다.
- Studio v45는 버전이 포함된 OLED 제목 스크롤과 연속 전원 차단 시 마지막 정상 설정 보존을 포함합니다. Native/XInput 통합을 유지하며 기본 프로필 모드는 Native입니다.

# v1.0.14 — Volume, recovery and UI improvements / 음량·복구·UI 개선

DS5Light-win-x64-v1.0.14.zip · ds5-studio-light_v44.uf2 (Pico 2 W)

- **Speaker and headset volume.** Link their editor values, synchronize explicit speaker-volume changes with the matching Pico Windows audio endpoint, and show an estimated Windows volume percentage. Enabling linking uses the speaker value.
- **Recovery and settings protection.** Preserve corrupt preferences when backup fails and retry preservation before saving. Recover diagnostic, profile, power and monitoring tasks after worker startup failures.
- **Audio capture and mapping UI.** Refresh the process list once when an audio-haptics profile becomes available with selected-process capture, or when that capture option is selected. Tighten combination-key icon spacing and improve audio controls, touchpad icons and gyro alignment.
- **Battery display.** Fix the animation error triggered by opening a native dropdown and refine connection/battery presentation.
- **Audio processing efficiency.** Reuse multichannel mixing and gain buffers to reduce repeated allocations during audio processing.
- **Studio v44.** Restore XInput support in the supplied Pico 2 W build, reduce repeated output-state work, optimize haptic calculations, and simplify the OLED header while retaining status information. Profiles still default to Native mode.
- **Source and documentation cleanup.** Remove unused legacy PNG assets and an unused refresh timer value; align setup instructions and download names with the current app/firmware pair.

- **스피커·헤드셋 음량.** 편집값을 연동하고 스피커 음량을 명시적으로 적용하면 같은 Pico의 Windows 오디오 출력 음량도 동기화합니다. 예상 Windows 음량 퍼센트를 표시하며, 연동을 켜면 스피커 값을 기준으로 맞춥니다.
- **복구와 설정 보호.** 손상된 환경설정의 백업에 실패하면 원본을 보호하고 저장 전에 백업을 재시도합니다. 진단·프로필·전원·감시 작업의 스레드 시작 실패 후 대기 상태가 남는 문제를 보완했습니다.
- **오디오 캡처·매핑 UI.** 선택한 프로세스 캡처 상태에서 오디오햅틱 프로필로 전환하거나 해당 캡처 옵션을 선택하면 프로세스 목록을 한 번 갱신합니다. 조합키 아이콘 간격, 오디오 옵션 배치, 터치패드 아이콘과 자이로 정렬도 개선했습니다.
- **배터리 표시.** 기본 드롭다운을 열 때 발생하던 애니메이션 오류를 수정하고 연결·배터리 표시를 보완했습니다.
- **오디오 처리 효율.** 다채널 믹싱과 출력 게인 버퍼를 재사용해 오디오 처리 중 반복 메모리 할당을 줄였습니다.
- **Studio v44.** 제공 Pico 2 W 빌드의 XInput 지원을 복원하고 중복 출력 상태 처리와 햅틱 계산을 최적화했습니다. OLED 헤더는 상태 정보를 유지하며 간소화했습니다. 기본 프로필 모드는 Native입니다.
- **소스·문서 정리.** 사용하지 않는 구형 PNG와 갱신 예약값을 제거하고 설치 안내·다운로드 파일명을 현재 앱·펌웨어 조합으로 통일했습니다.

## Earlier releases / 이전 릴리즈

# v1.0.12 Experimental · Local test build / 로컬 시험 빌드

DS5Light-win-x64-v1.0.12-Experimental.zip · ds5-studio-light_v43.uf2 (Pico 2 W)

- Device Diagnostics lists Windows audio outputs without the Studio HID, distinguishes the speaker and headset routes, and checks speaker pipeline counters on Studio v43.
- Studio v43 continues USB playback when a stale mic frame is discarded and avoids redundant disconnected audio resets.

- 장치 진단에서 Studio HID 없이 Windows 오디오 출력을 조회합니다. Studio v43에서는 스피커·헤드셋 경로와 오디오 처리 카운터를 확인할 수 있습니다.
- Studio v43은 오래된 마이크 프레임을 폐기해도 USB 재생 처리를 이어가고, 미연결 대기 중 반복 초기화를 줄입니다.

# v1.0.11 Experimental · Local app build / 앱 시험 빌드

- Device Diagnostics can reconnect a verified Pico audio output and explain when Windows needs attention.
- Mapping offers **DualSense power** under DualSense button outputs. Saving this action requires supporting Studio firmware.
- Create and Options use SVG icons. Touchpad click choices appear together, and changing a custom trigger effect reveals its section heading.

- 장치 진단에서 Pico 오디오 출력 연결을 복구하고 Windows에서 확인할 항목을 안내합니다.
- 매핑의 듀얼센스 버튼 출력에 **듀얼센스 전원**을 추가했습니다. 이 동작을 저장하려면 지원 펌웨어가 필요합니다.
- Create·Options 아이콘을 SVG로 통일하고, 터치패드 클릭 항목을 모았습니다. 커스텀 트리거 효과를 선택하면 섹션 제목이 보입니다.

# v1.0.9 Experimental · Local test build / 로컬 시험 빌드

`DS5Light-win-x64-v1.0.9-Experimental.zip` · `ds5-studio-light_v38.uf2` (Pico 2 W)

- Studio v38 separates LED setup from restoration and adds selectable V1/V2 game rumble.
- DS5Light shows the rumble selector on supported firmware and retains the basic diagnostic test on v36.
- Studio v38 defaults converted rumble strength in Mix to 100%. Saved profiles retain their values.

# v1.0.6 — Mapping and audio device compatibility / 매핑·오디오 장치 호환성

**DS5Light v1.0.6 · Studio v34 · Windows x64 · Pico 2 W**

Files: `DS5Light-win-x64-v1.0.6.zip` (experimental build: `DS5Light-win-x64-v1.0.6-Experimental.zip`), `ds5-studio-light_v34.uf2`.

- Swipe mappings can block touchpad clicks while enabled in the current profile/layer. The redundant swipe press-mode control is replaced by this option. Supporting firmware is required.
- Audio startup and diagnostics share the same device matching procedure, with physical USB parent identity recovery and manual confirmation for ambiguous outputs.
- Diagnostic refusal messages distinguish connection, profile and active-audio prerequisites. Selecting an output does not play a waveform.
- Reserved PS/Edge FN input combinations are blocked with explanations. Existing mic-button mapping policy is preserved.
- Firmware restores startup blue/player 1 after profile overrides when no game LED command exists; explicit game colours and off commands take precedence.
- No change to native haptic DSP, transport or buffer policy in this update. Hardware regressions remain separate from code checks.

## 한국어

- 스와이프의 누르는 방식 대신 터치패드 클릭 차단 옵션을 표시합니다. 활성 프로필·레이어에서만 적용하며 구형 펌웨어에는 저장을 거부합니다.
- 오디오 시작·진단의 장치 매칭을 통일하고 부모 USB 장치 정보와 수동 확인으로 연결을 보완합니다.
- PS·Edge FN 충돌 조합 안내 및 제한, 마이크 매핑 정책, 초기 LED 복원 수정을 포함합니다.
- 빌드 후에도 실기기의 클릭 차단·LED 외관·모드 왕복은 별도 확인이 필요합니다.

---

# v1.0.5 — UI and stability fixes / UI·안정성 수정

**DS5Light v1.0.5 · Studio v33 · Windows x64 · Raspberry Pi Pico 2 W**

Files: `DS5Light-win-x64-v1.0.5.zip`, `ds5-studio-light_v33.uf2`.

## Bug fixes

- **Settings-save freeze:** Guard thread startup against a Tk variable finalizer running during the startup handshake, which could leave the UI waiting indefinitely after mapping edits/save. The original GC enabled/disabled state is restored after startup.
- **Device-operation waits:** Limit Studio query/power lock acquisition to three seconds and release the lock on failure. A lock timeout does not open the device or send the operation.
- **Unwanted audio restart:** Recheck the execution intent immediately before a scheduled resume. A later stop, capture-route change, new start, cancellation, closing or a busy settings task prevents the stale callback from starting audio.
- **English UI:** Complete Shift-layer, profile-number and chime labels; refine speaker/idle-disconnect terminology; retain controller-button icons in translated hold conditions.
- **Lightbar restoration:** Improve restoration of game-controlled RGB across fixed/off transitions and queued LED commands, including release/setup ordering and restore acknowledgment.
- **Documentation:** Merge the previous release's DPI, Shift and profile-switch descriptions into the current README feature guide instead of repeating version-specific feature sections. Retain the English-only screenshot and the separately labeled upstream README archive.

## Compatibility and verification

- Back up settings and slots before updating. The UF2 is for Pico 2 W; additional mapping features require supporting firmware.
- Mapping save order remains: stage edits → save Pico mappings/macros → save the current profile. Definitions are global; profile enable states are saved separately.
- Python lock deadlines cannot forcibly interrupt a native HID driver call that has already stopped returning. All real DPI/multi-monitor combinations and physical controller output still require separate device validation.

## 버그 수정

- **매핑 편집·저장 후 UI 멈춤:** 스레드 시작 신호 대기 중 Tk 변수 정리가 겹쳐 UI와 작업 스레드가 서로 기다릴 수 있던 경로를 보호했습니다. 시작 후에는 기존 GC 활성 상태를 복원합니다.
- **장치 작업 대기:** Studio 조회·전원 작업의 잠금 획득을 3초로 제한하고 실패 시 잠금을 해제합니다. 잠금 시간 초과 시 장치를 열거나 해당 명령을 보내지 않습니다.
- **의도하지 않은 오디오 재시작:** 예약된 재시작 직전에 실행 의도를 다시 검사합니다. 이후 정지·캡처 경로 변경·새 시작·취소·종료·설정 작업 진행이 있으면 이전 콜백이 오디오를 시작하지 않습니다.
- **영어 UI 보완:** 시프트 레이어·프로필 번호·전환 신호음 번역, 스피커·유휴 연결 해제 용어와 영문 누르기 조건의 컨트롤러 아이콘을 보완했습니다.
- **라이트바 복원:** 고정/끄기 설정 전환과 대기 중 LED 명령이 겹칠 때 게임 RGB를 복원하는 순서와 확인 처리를 보완했습니다.
- **문서 정리:** 이전 릴리즈의 DPI·시프트·프로필 전환 소개를 README의 현재 기능 설명에 통합했습니다. 영문 전용 그림과 원본 README 보관본은 유지합니다.

## 호환성과 확인 범위

- 업데이트 전 설정·슬롯을 백업하세요. UF2는 Pico 2 W용이며 확장 매핑은 지원 펌웨어가 필요합니다.
- 저장 순서는 편집에 반영 → Pico 매핑·매크로 저장 → 현재 프로필에 저장입니다. 정의는 공통, 사용 체크는 프로필별입니다.
- Python 잠금 시간 제한으로 이미 반환하지 않는 native HID 드라이버 호출을 강제 중단할 수는 없습니다. 실제 컨트롤러 출력과 모든 DPI·다중 모니터 조합은 별도 확인이 필요합니다.
