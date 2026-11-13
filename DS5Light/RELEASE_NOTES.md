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
