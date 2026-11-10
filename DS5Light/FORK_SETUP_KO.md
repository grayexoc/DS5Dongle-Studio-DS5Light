# 포크에 포함된 DS5Light

이 폴더는 수정된 DS5Light 앱 소스입니다. Studio 설정 UI와 PC 오디오 햅틱 기능이 같은 앱에 포함되어 있습니다. 실행 패키지는 이 포크의 Releases에서 제공하며, 설치·프리셋 적용은 [SETUP_KO.md](SETUP_KO.md), 버전 관계는 [RELEASE_NOTES.md](RELEASE_NOTES.md)를 참고하세요.

## 소스로 실행

Windows x64, Python 3.12 및 필요한 Windows 오디오/HID 장치를 준비하고 이 폴더에서 실행합니다.

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
& "$env:WINDIR\Microsoft.NET\Framework64\v4.0.30319\csc.exe" /nologo /platform:x64 /target:exe /out:ProcessCapture.exe native\ProcessCapture.cs
.venv\Scripts\python.exe app.py
```

`ProcessCapture.exe`는 선택한 프로세스의 오디오 캡처에 사용합니다. 소스는 `native/ProcessCapture.cs`에 포함되어 있습니다. `START.bat`는 빌드된 앱을 실행하는 용도입니다. 패키지 생성은 기존 `build.ps1`를 사용합니다.

## 포함 및 제외

- 앱 소스, 테스트, 빌드 스크립트, 기본 설정, 제공 프리셋, 필요한 자산과 외부 구성요소 고지를 포함합니다.
- 개인 `preferences.json`, 기기 백업, 로그, 보고서, 캐시, 빌드 결과와 실행 파일은 제외합니다. 설정은 실행 시 생성됩니다.
- TkSVG 런타임 DLL은 기존 앱이 사용하는 외부 구성요소로 출처·라이선스와 함께 포함합니다.


펌웨어는 루트 MIT 라이선스, DS5Light 자체 코드는 이 폴더의 `LICENSE.txt`를 따릅니다. 빌드·테스트 결과와 실제 컨트롤러의 동작·햅틱 체감 검증은 구분하며, 해당 릴리즈에 기록한 검증 범위를 참고하세요.
