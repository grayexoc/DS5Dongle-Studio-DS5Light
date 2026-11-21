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
