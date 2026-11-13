# DS5 Light

[English](README.md) · [설치 안내](SETUP_KO.md) · [사용설명서(TXT)](README_KO.txt)

**[DS5Dongle-Studio](https://github.com/artzox/DS5Dongle-Studio)용 경량 Windows 오디오햅틱 전처리기**입니다.

동글로 보내는 게임 오디오 복사본에 적응형 필터를 적용합니다. BGM·대사로 생기는 불필요한 진동을 줄이면서 효과음의 타이밍과 촉감을 살리는 것이 목표입니다. 귀로 듣는 게임 소리는 바꾸지 않습니다.

## 주요 기능

- 검정·금색 테마를 유지하는 고배율 컨트롤과 창 크기 제한. 팝업은 메인 창 배율을 따릅니다.
- Studio 설정 통합, 기본/시프트 매핑과 프로필 1~8 전환 동작·선택적 신호음/미리듣기.
- 설정 작업 후 재시작 제어, 장치 잠금 대기 제한, 스레드 시작 보호와 한국어·영어 설명/컨트롤러 버튼 아이콘.

저장 순서와 호환성은 [매핑 안내](MAPPING_GUIDE_KO.md), 배율 동작은 [DPI 안내](DPI_LAYOUT_KO.md)를 참고하세요.

- 선택한 게임 또는 출력 장치 전체의 오디오 캡처
- 디테일·균형·억제 스타일과 억제 강도 조절
- 5.1/7.1 입력에서 후방·측면·센터·LFE 기여도 선택
- 게임별 설정을 저장하는 12개 프리셋 슬롯
- 한국어·영어 UI
- Studio용 **Audio Haptics**와 **DS Native** 프로필 제공

## 필터의 핵심 원리

시간에 따른 소리 변화를 살펴 Studio 처리 전에 한 번 더 조절합니다.

1. **적응형 배경 추정:** 소리를 네 개 대역으로 나눠 최근의 에너지 수준을 기억합니다. 배경 수준에 머무르는 소리는 더 줄이고, 그보다 새롭게 커지는 소리는 상대적으로 덜 줄입니다.
2. **순간적인 변화 보호:** 갑작스러운 음량 증가를 최근 변화와 비교해 타격·총격 같은 짧은 효과가 과하게 약해지는 것을 줄입니다. 순간음이라고 필터를 완전히 우회하지는 않습니다.
3. **제한적이고 부드러운 감쇠:** 대역별 감소량에 한도를 두고 서서히 바꿉니다. 좌우에는 공통 제어값을 사용하며 자동으로 출력 볼륨을 끌어올리지는 않습니다.

기본 경로는 대형 AI 모델이나 GPU 추론을 사용하지 않는 CPU 신호 처리입니다. 악기나 목소리를 인식해 따로 분리하는 방식은 아니므로 음악의 타격음이 남거나 지속 효과음이 약해질 수도 있습니다. 게임·오디오 구성·Studio 설정에 따라 결과가 달라집니다.

## 준비물

- Windows 10/11 64비트. 선택한 게임만 캡처하려면 Windows 빌드 20348 이상이 필요하며, 이전 Windows 10에서는 장치 전체 캡처를 사용할 수 있습니다.
- DS5Dongle-Studio가 설치된 지원 동글과 DualSense
- Studio 오디오햅틱 설정. 처음에는 제공하는 Audio Haptics 프로필을 기준으로 사용하세요.

## 다운로드와 실행

로컬 시험 빌드는 `DS5Light-win-x64-v1.0.12-Experimental.zip`과 Pico 2 W용 `ds5-studio-light_v43.uf2`입니다.

**통합 릴리즈 v1.0.6 · DS5Light v1.0.6 · Studio 펌웨어 v34**

[Releases](https://github.com/grayexoc/DS5Dongle-Studio-DS5Light/releases)에서 `DS5Light-win-x64-v1.0.6.zip` 전체를 받아 풀고 `DS5Light.exe`를 실행하세요. `_internal` 폴더를 함께 유지해야 하며 Python 설치는 필요하지 않습니다. Pico 2 W용 펌웨어는 별도 파일 `ds5-studio-light_v34.uf2`입니다.

앱의 **Studio설정 → 추천 프리셋 → 저장 후 사용**을 이용하세요. 파일은 `Studio Presert/DS_Native.json`, `Studio Presert/Audio_Haptic_01.json`, `Studio Presert/Audio_Haptic_02.json`입니다. 현재 오디오햅틱 항목만 바꾸고 다른 현재 설정을 유지한 구성을 선택한 슬롯에 저장합니다. 슬롯 덮어쓰기 전 대상을 확인하세요.

새 설정의 기본값은 PC 필터 켬·균형·억제량 55%·타격 보존 85%·세기 100%이며, 기존 저장 설정이 우선합니다. 채널은 자동이 기본이고 스테레오·5.1·7.1 수동 선택도 가능합니다. 캡처 형식이 게임 내부 오디오 설정을 확정하는 것은 아닙니다.

[설치 안내](SETUP_KO.md) · [사용법](README_KO.txt) · [버전 및 릴리즈 안내](RELEASE_NOTES.md) · [구성요소 출처](SOURCES.md)

### 소스 빌드

`requirements-build.txt`의 빌드 의존성을 준비하고 `powershell -ExecutionPolicy Bypass -File build.ps1`을 실행합니다. 앱 제목과 `DS5Light-win-x64-v<버전>.zip`의 버전은 `app_version.py`를 사용합니다. 중간 출력은 `dist/DS5Light`이며 `START.bat`로 실행할 수 있습니다. 기존 ZIP은 덮어쓰지 않으므로 새 릴리즈에는 앱 버전을 올려야 합니다. `DS5LIGHT_EXPERIMENTAL=1`이면 파일명에 `-Experimental`이 추가됩니다. 버전 정책은 [RELEASE_NOTES.md](RELEASE_NOTES.md)를 참고하세요.

## 출처와 라이선스

DS5 Light는 [DS5Dongle-Studio](https://github.com/artzox/DS5Dongle-Studio)와 함께 사용하는 비공식 보조 프로그램입니다. 독립적으로 관리되며 Studio의 공식 배포판이 아닙니다. 원 프로젝트 개발자와 기여자분들께 감사드립니다.

| 프로젝트·구성요소 | 라이선스 | 사용한 부분 |
|---|---|---|
| [DS5Dongle-Studio](https://github.com/artzox/DS5Dongle-Studio) | MIT | `ds5audio.py` 오디오 브리지 일부 재사용. awalol·artzox의 원저작권 고지 보존 |
| [NumPy](https://numpy.org/) | BSD-3-Clause 및 포함 구성요소별 추가 고지 | 수치·배열 연산 |
| [SciPy](https://scipy.org/) | BSD-3-Clause 및 포함 구성요소별 추가 고지 | 디지털 필터와 신호 처리 |
| [PyAudioWPatch](https://github.com/s0d3s/PyAudioWPatch) | 포크 기여분 Apache-2.0, 기존 PyAudio·PortAudio MIT 고지 유지 | Windows 오디오 캡처·출력 |
| [Python](https://www.python.org/) | PSF 라이선스 및 포함 구성요소별 고지 | 실행 환경 |
| [PyInstaller](https://pyinstaller.org/) | GPL-2.0-or-later와 배포 예외, 구성요소별 조건 | 실행 프로그램 패키징 |
| DS5 Light 자체 코드 | [사용자 정의 무료 이용 라이선스](LICENSE.txt) | UI·처리·통합 코드. 판매·유료 통합 제한 |

주요 구성요소를 요약한 표이며 모든 포함 의존성의 목록은 아닙니다. Studio 원문 고지는 [vendor/LICENSE-Studio.txt](vendor/LICENSE-Studio.txt), 상세 출처는 [SOURCES.md](SOURCES.md), 관련 원문은 [upstream 고지](licenses/upstream)와 실행 배포본의 `THIRD_PARTY` 폴더에서 확인할 수 있습니다. 외부 구성요소의 라이선스는 그대로 유지되며, DS5 Light 자체 코드의 제한이 이를 덮어쓰지 않습니다.

배경 추정 개념은 [noisereduce](https://github.com/timsainb/noisereduce)도 참고했습니다. 해당 구현을 런타임에 복사한 것은 아니며, 코드 의존성과 구분되는 설계 참고입니다.

## 라이선스

[DS5 Light 라이선스](LICENSE.txt)에 따라 무료 사용·수정·무료 재배포를 허용합니다. 프로그램 판매 또는 유료 제품·서비스에 통합하려면 별도 허락이 필요합니다. 수익형 게임 방송·영상 제작에 도구로 사용하는 것은 허용합니다.

[영어 번역](LICENSE_EN.txt) · [배포 정책](DISTRIBUTION_POLICY_KO.md)

한국어 라이선스 원문을 기준으로 하며, OSI 승인 오픈소스 라이선스는 아닙니다.
