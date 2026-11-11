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
