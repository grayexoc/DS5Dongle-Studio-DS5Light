"""UI-only localization. No dependency from the audio processing thread."""
from functools import lru_cache
import ctypes
import json
import locale
import os
from pathlib import Path
import sys
import tempfile
from translations import EN

AUTO_KO = '자동 선택 · 기존 BAT 방식'

def settings_path():
    if '--ui-test-path' in sys.argv:
        return Path(sys.argv[sys.argv.index('--ui-test-path') + 1])
    return Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'DS5Light' / 'ui.json'

def system_language():
    try:
        if os.name == 'nt':
            return 'ko' if ctypes.windll.kernel32.GetUserDefaultUILanguage() & 0x3ff == 0x12 else 'en'
        return 'ko' if (locale.getlocale()[0] or '').startswith('ko') else 'en'
    except Exception:
        return 'en'

def load_language(path=None):
    try:
        value=json.loads((path or settings_path()).read_text(encoding='utf-8'))['language']
        if value in ('ko','en'): return value
    except (OSError,ValueError,KeyError,TypeError):
        pass
    return system_language()

def save_language(value,path=None):
    if value not in ('ko','en'): raise ValueError('Unsupported language')
    path=path or settings_path()
    # Preserve unrelated preferences and never overwrite unreadable user data.
    data=json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    if not isinstance(data,dict): raise ValueError('Invalid UI settings file')
    data['language']=value
    path.parent.mkdir(parents=True,exist_ok=True)
    name=None
    try:
        with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',dir=path.parent,delete=False) as f:
            name=f.name; json.dump(data,f,ensure_ascii=False); f.flush(); os.fsync(f.fileno())
        os.replace(name,path)
    finally:
        if name and Path(name).exists(): Path(name).unlink()

LANGUAGE = sys.argv[sys.argv.index('--language')+1] if '--language' in sys.argv else load_language()
if LANGUAGE not in ('ko','en'): LANGUAGE=system_language()
ORDERED = sorted(EN,key=len,reverse=True)
STUDIO_MESSAGES={'Studio 연결 확인 중…':'Checking Studio connection…',
                 '재연결 대기 8초 초과 · 자동 정지':'Reconnection wait exceeded 8 seconds · Automatically stopped',
                 '듀얼센스 연결이 해제되어 전송이 중단되었습니다.':'Transmission ended after the DualSense disconnected.',
                 '듀얼센스 연결 해제 · 재연결 대기 중':'DualSense disconnected · Waiting for reconnection',
                 '프로필 적용 후 상태를 확인하지 못했습니다. 연결을 확인한 후 다시 조회하세요.':'Could not verify the applied profile. Check the connection and read again.',
                 'Studio 대상 장치를 확인할 수 없습니다.':'Cannot identify the target Studio device.',
                 '현재 Studio 프로필의 오디오햅틱이 꺼져 있어 전송을 정지했습니다.':'Transmission stopped because audio haptics is off in the current Studio profile.',
                 'Studio 프로필 응답 준비 중':'Studio profiles are not ready yet',
                 'Studio 프로필 조회 완료':'Studio profiles loaded'}

def tr(text):
    if LANGUAGE=='en' and text in STUDIO_MESSAGES:return STUDIO_MESSAGES[text]
    if text=='오디오햅틱 세기':return '오디오햅틱 세기' if LANGUAGE=='ko' else 'Audio haptics strength'
    if text=='햅틱 세기':return '햅틱 세기' if LANGUAGE=='ko' else 'Haptic strength'
    if text=='설정 및 진단':return '설정 및 진단' if LANGUAGE=='ko' else 'Settings & diagnostics'
    if text==AUTO_KO:return '자동 선택' if LANGUAGE=='ko' else 'Automatic'
    if LANGUAGE=='ko': return text.replace('캡처','캡쳐').replace('동글','Pico')
    if text in EN: return EN[text]
    if not any('가' <= c <= '힣' for c in text): return text
    return _dynamic_english(text)

@lru_cache(maxsize=512)
def _dynamic_english(text):
    # Bound names and changing counters retained by dynamic message translation.
    for key in ORDERED:
        if key in text:text=text.replace(key,EN[key])
    return text

def canonical_device(value):
    return AUTO_KO if value in (AUTO_KO, EN[AUTO_KO], '자동 선택', 'Automatic') else value

def display_device(value):
    return tr(AUTO_KO) if canonical_device(value)==AUTO_KO else value
