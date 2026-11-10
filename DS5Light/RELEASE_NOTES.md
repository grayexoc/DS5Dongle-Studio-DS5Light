# Versions and release notes / 버전 및 릴리즈 안내

## Current baseline / 현재 기준

| Component / 구분 | Version / 버전 | Source / 기준 |
| --- | --- | --- |
| Combined release / 통합 릴리즈 | v1.0.0 | GitHub release tag / 릴리즈 태그 |
| DS5Light | v1.0.0 | `app_version.py` → `APP_VERSION` |
| Studio firmware / 펌웨어 | v30 | `CMakeLists.txt` → `VERSION` |

App package: `DS5Light-win-x64-v1.0.0.zip`
Pico 2 W firmware: `ds5-studio-light_v30.uf2`

The former `dist-0.9.0` directory and `DS5Light-XInput-win-x64-V<number>` names are historical build labels, not the current app/release version. Existing artifacts remain unchanged. Current builds use `dist/DS5Light`; the app window title and ZIP version come from `APP_VERSION`.

기존 `dist-0.9.0` 폴더와 `DS5Light-XInput-win-x64-V숫자`는 과거 빌드 표기이며 현재 앱·릴리즈 버전이 아닙니다. 기존 산출물은 변경하지 않습니다. 이후 빌드는 `dist/DS5Light`를 사용하고 앱 창 제목과 ZIP 버전은 `APP_VERSION`을 따릅니다.

## Next release / 다음 배포

1. Update `APP_VERSION` in `app_version.py` for an app release, and use that same version in the ZIP filename, combined release tag and release description. Update this table and the download examples in the setup/readme documents together. The build rejects an existing ZIP instead of overwriting it; experimental builds use the same version with an `-Experimental` suffix.
2. Studio keeps an independent firmware version. For a firmware update, change `VERSION` in its CMake source and record the exact firmware version alongside the app version in the combined release description. If only firmware changes, keep the unchanged app package's version and explicitly list that pairing.
3. Include both versions, supported board, included files, changes and actual verification scope in the release description.

1. 앱 배포 시 `app_version.py`의 `APP_VERSION`을 올리고 ZIP 파일명·통합 릴리즈 태그·설명에 같은 버전을 사용합니다. 위 표와 SETUP/README의 다운로드 예시도 함께 갱신합니다. 기존 ZIP은 덮어쓰지 않으며 실험 빌드는 같은 버전에 `-Experimental` 접미사를 사용합니다.
2. Studio는 독립적인 펌웨어 버전을 유지합니다. 펌웨어 변경 시 CMake 소스의 `VERSION`을 올리고 통합 릴리즈 설명에 앱 버전과 펌웨어 버전을 함께 기록합니다. 펌웨어만 바뀌면 앱 패키지 버전은 유지하고 조합을 명시합니다.
3. 릴리즈 설명에 두 버전, 대상 보드, 첨부 파일, 변경점과 실제 검증 범위를 포함합니다.

## Local source changes after the initial release / 초기 릴리즈 이후 로컬 소스 정리

- Replaced portal-first setup instructions with the integrated Studio settings workflow.
- Documented the three files in `Studio Presert` and the limited scope of recommended presets.
- Corrected first-run PC filter defaults; saved preferences remain unchanged.
- Unified app title and future package naming through `APP_VERSION`; moved future build output to `dist/DS5Light`.
- Added setup documents and preset instructions to future packages.

- 웹 포털 중심 안내를 앱의 Studio설정 절차로 통일했습니다.
- `Studio Presert`의 실제 파일 3개와 추천 프리셋의 적용 범위를 명시했습니다.
- 첫 실행 필터 기본값 안내를 바로잡았으며 기존 사용자 설정은 변경하지 않습니다.
- `APP_VERSION`으로 앱 제목과 이후 패키지 파일명을 맞추고 빌드 출력을 `dist/DS5Light`로 정리했습니다.
- 이후 패키지에 설치 안내와 프리셋 설명을 포함합니다.

The initial v1.0.0 release is rebuilt from the updated sources, including the integrated setup guides, current version display and package naming.
초기 v1.0.0 릴리즈는 통합 앱 설치 안내, 현재 버전 표시와 패키지 파일명 정리를 포함한 최신 소스로 다시 빌드합니다.
