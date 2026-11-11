# Studio release versions / Studio 릴리즈 버전

Current pairing / 현재 조합: combined release v1.0.6 · DS5Light v1.0.6 · Studio v34.

- Firmware source of truth: `CMakeLists.txt`, `VERSION` (currently `34`). CMake's output name and the Windows/macOS build scripts use this value: `ds5-studio-light_v34.uf2`. Nonstandard variants collected by the Windows script add the variant suffix; they must be built for their own board.
- The supplied v1.0.6 UF2 is a Pico 2 W build with XInput support. It is not a Waveshare/RP2040 build. Do not infer that an ordinary default build enables the same optional features.
- App source of truth: the companion's `app_version.py`, `APP_VERSION` (`1.0.6`), used for its title and ZIP name. It is independent of the firmware number.
- On a firmware change, bump `VERSION` deliberately and record the app/firmware pairing in the combined release description. Keep previous versioned artifacts. App updates use the app version for the package and combined release tag; a firmware-only release lists the unchanged app version explicitly.
- Keep this pairing, README download examples and the companion RELEASE_NOTES.md synchronized for the next release. Changes to documentation alone do not rebuild or replace published artifacts.

- 펌웨어 버전 기준은 `CMakeLists.txt`의 `VERSION`이며 현재 `34`입니다. CMake 출력과 Windows/macOS 빌드 안내는 `ds5-studio-light_v34.uf2` 형태를 사용합니다. Windows 스크립트의 별도 변형 출력에는 변형 접미사가 붙으며 보드별 빌드가 필요합니다.
- v1.0.6 UF2는 XInput을 포함한 Pico 2 W 빌드입니다. Waveshare/RP2040용이 아니며 일반 기본 빌드가 같은 선택 기능을 켠다고 가정하지 마세요.
- 앱은 별도의 `app_version.py` → `APP_VERSION` (`1.0.6`)을 창 제목과 ZIP 파일명에 사용합니다. 펌웨어 번호와 별개입니다.
- 펌웨어 변경 시 `VERSION`을 명시적으로 올리고 릴리즈 설명에 앱·펌웨어 조합을 기록합니다. 기존 버전 파일은 보존합니다. 앱 업데이트 시 앱 버전을 ZIP과 통합 릴리즈 태그에 사용하고, 펌웨어만 배포하면 그대로인 앱 버전을 명시합니다.
- 다음 배포에서 이 조합과 README 다운로드 예시, 앱의 RELEASE_NOTES.md를 함께 갱신하세요. 문서 수정만으로 기존 배포 파일을 다시 빌드하거나 교체하지 않습니다.
