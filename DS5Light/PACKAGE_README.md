# DS5Light v1.2.4

## English

Use DS5Light v1.2.4 with Studio v55 for Raspberry Pi Pico 2 W. Extract the entire ZIP to a writable folder and run DS5Light.exe with _internal beside it. No separate Python installation is required.

Choose whole-device or selected-game capture. Selected-game capture requires Windows build 20348 or later. Select a Mix or Replace Studio profile to start audio haptics. If the controller appears as a two-channel output, set it to four channels in Windows. After reconnection, the app waits up to eight seconds for the same Pico output.

After updating, we strongly recommend applying a supplied Mix or Replace preset under **Studio settings → Profile slots → Recommended presets**, then adjusting it to the game and your preference. Start with the app filter enabled, background reduction / impact preservation at 40% / 90% for Mix or 50% / 95% for Replace, and app strength at **1x (100%)**. Both presets use Front input; Mix also combines the game's raw rear native haptics.

Existing saved slots retain their settings. Stop dongle audio and back up the destination slot before **Save and use**. This writes the current configuration with the preset's audio-haptics settings to that slot, replacing its previous contents.

Use these recommended presets as the reference when comparing audio-haptics changes. Perceived response varies with Windows and game/application volume. Unless otherwise specified, other settings assume their defaults. If controller-speaker auto-mute is off or unconfirmed on shared output, the app stays at 1x; adjust **Audio Haptics Strength in Studio settings** instead.

Studio Presert contains DS_Native.json, Audio_Haptic_01.json and Audio_Haptic_02.json. default_config.json holds app defaults. User preferences are created beside the executable. Licenses and component notices are in LICENSES/.

## 한국어

DS5Light v1.2.4은 Raspberry Pi Pico 2 W용 Studio v55와 함께 사용합니다. ZIP 전체를 쓰기 가능한 폴더에 풀고 _internal을 유지한 채 DS5Light.exe를 실행하세요. Python은 별도로 설치하지 않아도 됩니다.

장치 전체 또는 선택한 게임의 캡처를 지정하세요. 게임별 캡처에는 Windows 빌드 20348 이상이 필요합니다. 오디오 햅틱을 시작하려면 Studio에서 Mix 또는 대체 프로필을 선택하세요. 패드 출력이 2채널이면 Windows에서 4채널로 설정하세요. 재연결 후 앱은 같은 Pico의 출력을 최대 8초간 확인합니다.

업데이트 후 **Studio 설정 → 프로필 슬롯 → 추천 프리셋**에서 동봉 Mix·Replace 프리셋을 기본 설정으로 다시 적용할 것을 강력히 권장합니다. **앱 필터 켬·배경 억제/충격 보존은 믹스 40%/90%, 대체 50%/95%·앱 세기 1x(100%)**를 시작점으로 삼아 게임과 취향에 맞게 조절하세요. 두 프리셋 모두 Front 입력을 사용하며 Mix는 게임의 Rear 네이티브 햅틱 원본도 혼합합니다.

기존 저장 슬롯은 자동으로 바뀌지 않습니다. 동글 오디오 전송을 멈추고 대상 슬롯을 백업한 뒤 **저장 후 사용**을 선택하세요. 현재 구성에 프리셋의 오디오 햅틱 설정을 반영한 결과로 대상 슬롯을 덮어씁니다.

오디오 햅틱의 개선 사항은 이 추천 프리셋을 기준으로 확인해 주세요. 체감은 Windows 음량과 게임·앱 음량에 영향을 받으며, 별도 안내가 없는 기타 설정은 기본값을 기준으로 합니다. 공유 출력에서 패드 스피커 자동 음소거가 꺼져 있거나 확인되지 않으면 앱 출력은 1x로 유지되므로 **Studio 설정의 오디오햅틱 세기**를 조절하세요.

Studio Presert에는 DS_Native.json, Audio_Haptic_01.json, Audio_Haptic_02.json이 있습니다. default_config.json은 앱 기본 설정입니다. 사용자 설정은 실행 파일 옆에 생성됩니다. 라이선스와 제3자 고지는 LICENSES/ 폴더에 있습니다.
