# v1.0.4 — High-DPI UI and controller mapping / 고배율 UI·컨트롤러 매핑

**DS5Light v1.0.4 · Studio v32 · Pico 2 W · Windows x64**

Downloads: `DS5Light-win-x64-v1.0.4.zip`, `ds5-studio-light_v32.uf2`.

## New in v1.0.4 / Studio v32

- **High-DPI UI:** Per-monitor DPI awareness and a matching executable manifest, logical pixel scaling without scaling point fonts twice, DPI-aware shared controls and popup sizing, and window bounds constrained to the monitor work area. Popups share the main window scale; moving only a popup to another monitor does not select an independent scale.
- **Shift layer:** Choose a controller button as a momentary Shift key, then edit Base and Shift mappings. Unassigned Shift bindings inherit Base. The Shift key is suppressed from game input and uses one of the 32 global mapping/macro records; enable states remain profile-specific.
- **Profile-switch mapping:** Bind an action to profile 1–8, with an optional confirmation chime and a preview that does not change profiles. Empty/current slots do not trigger a switch. Source buttons must be released before another switch; chime volume follows the profile's speaker/headset settings.
- **Settings and reliability:** Improved lighting/speaker setting layout and combobox wheel behavior; clearer fork firmware version display; cancellation checks while waiting for a device lock; backup of legacy settings without silently normalizing them. Studio v32 improves PS-shortcut key-up retry and keyboard ownership with wake/macro actions.
- **Source and package cleanup:** Removed legacy web-profile exports, an outdated feature summary, an unused source-artwork duplicate and obsolete upstream firmware binaries from the current source tree. Current presets, tests, recovery firmware, attribution and licenses remain.

See [mapping save order and compatibility](MAPPING_GUIDE_KO.md) and [DPI details](DPI_LAYOUT_KO.md). In the app: **stage edits → save Pico mappings/macros → save the current profile**. Clear or disable extended mapping records before downgrading to firmware that does not support them. Edge onboard Fn+face combinations can conflict with the controller's own profiles.

## Compatibility and verification

- Back up settings and slots before updating. New mapping writes require supporting firmware; the supplied Studio v32 includes that support. Use the Pico 2 W UF2 only on the matching board.
- Profile/macro definitions are global; per-profile enable checks are saved separately. Review the save order above to avoid losing staged changes.
- UI/DPI arithmetic, mapping and firmware host regressions are checked during release preparation. These checks do not establish physical controller behavior, speaker loudness, or every real 100/125/150/200% multi-monitor layout.
- The screenshot in the main README is an earlier example of Audio haptics and Studio settings; it does not show diagnostics or every new mapping control.

## v1.0.4 / Studio v32 추가·개선

- **고배율 DPI 최적화:** 모니터별 DPI 인식과 실행 파일 manifest, 포인트 글꼴의 이중 확대를 피하는 논리 픽셀 변환, 공통 컨트롤·팝업 크기 조절과 모니터 작업 영역 안의 창 배치를 적용했습니다. 팝업은 메인 창 배율을 공유하며 팝업만 다른 모니터로 옮겨도 독립 배율로 바뀌지는 않습니다.
- **시프트 레이어:** 컨트롤러 버튼을 누르는 동안 기본/시프트 매핑을 전환합니다. 지정하지 않은 시프트 입력은 기본 매핑을 상속합니다. 시프트키 자체는 게임으로 보내지 않으며 공통 매핑·매크로 32칸 중 한 칸을 사용합니다. 사용 체크는 프로필별입니다.
- **프로필 전환 매핑:** 동작에 프로필 1~8 전환을 지정하고 선택적으로 전환 신호음·미리듣기를 사용할 수 있습니다. 빈 슬롯·현재 슬롯은 전환하지 않으며 재전환 전 입력 버튼을 놓아야 합니다. 신호음은 프로필의 스피커 음량·헤드셋 경로를 따릅니다.
- **설정·안정성:** 조명·스피커 설정 배치, 콤보박스 휠 동작, 포크 펌웨어 버전 표시, 장치 잠금 대기 중 취소와 기존 설정을 그대로 보존하는 백업 처리를 보완했습니다. Studio v32는 PS 단축키 해제 재시도와 깨우기·매크로 간 키보드 사용 처리를 개선했습니다.
- **소스·패키지 정리:** 구형 웹 프로필, 오래된 기능 요약, 사용하지 않는 원본 그림 중복 파일과 과거 원본 UF2를 현재 소스에서 제거했습니다. 현재 프리셋·테스트·복구용 파일·출처·라이선스는 유지합니다.

앱 저장 순서는 **편집에 반영 → Pico 매핑·매크로 저장 → 현재 프로필에 저장**입니다. [매핑 안내](MAPPING_GUIDE_KO.md)와 [DPI 안내](DPI_LAYOUT_KO.md)를 참고하세요. 구형 펌웨어로 내리기 전 확장 레코드를 제거하거나 사용 체크를 해제하세요. Edge 자체 Fn+도형 버튼은 컨트롤러 내장 프로필과 겹칠 수 있습니다.

## 호환성과 검증 범위

- 업데이트 전 설정·슬롯을 백업하세요. 확장 매핑 쓰기는 지원 펌웨어가 필요하며 동봉 Studio v32에 포함돼 있습니다. Pico 2 W용 UF2는 해당 보드에만 사용하세요.
- 매핑·매크로 정의는 공통이며 프로필별 사용 체크는 별도 저장합니다. 위 저장 순서를 확인하세요.
- 릴리즈 준비 중 UI·DPI 계산, 매핑 및 펌웨어 호스트 회귀 검사를 수행합니다. 실제 컨트롤러 동작·신호음 음량과 모든 실물 100/125/150/200% 다중 모니터 배치의 검증을 대신하지는 않습니다.
- 메인 README의 그림은 이전 오디오햅틱·Studio설정 화면 예시이며 진단 화면과 새 매핑 UI 전체를 보여주지는 않습니다.

## Versions / 버전

App title and ZIP filename use `app_version.py` → `APP_VERSION` (`1.0.4`). Firmware uses its own CMake `VERSION` (`32`). Current output is `dist/DS5Light`; existing ZIP packages are not overwritten. Update the app version, release tag and download examples together for an app release, and state the paired firmware version in its notes.

앱 제목·ZIP은 `app_version.py`의 `APP_VERSION` (`1.0.4`), 펌웨어는 CMake `VERSION` (`32`)을 사용합니다. 빌드 출력은 `dist/DS5Light`이며 기존 ZIP을 덮어쓰지 않습니다. 다음 앱 배포에는 앱 버전·릴리즈 태그·다운로드 예시를 함께 갱신하고 펌웨어 조합을 명시하세요.

Previous public release: [v1.0.0](https://github.com/grayexoc/DS5Dongle-Studio-DS5Light/releases/tag/v1.0.0).
