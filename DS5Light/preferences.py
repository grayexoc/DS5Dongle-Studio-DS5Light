"""Last-used UI preferences, stored separately from named game presets."""
from studio_i18n import text as _ui_tr
import json
import os
from pathlib import Path
import tempfile
import time

from core import Controls
from mute_shortcut import default_binding, validate_binding


def default_preferences():
    return {
        'remember_last': True,
        'auto_start': False,
        'scope': 'device',
        'channels': 0,
        'channel_auto': True,
        'input': '',
        'output': '',
        'game_exe': '',
        'process_sort': 'audio',
        'window_width': 860,
        'window_height': 1000,
        'mute_shortcut': default_binding(),
        'controls': Controls().__dict__,
    }


def validate(value):
    if not isinstance(value, dict) or value.get('version') != 1:
        raise ValueError(_ui_tr('설정 파일 형식이 올바르지 않습니다.'))
    data = value.get('preferences')
    if not isinstance(data, dict):
        raise ValueError(_ui_tr('설정 항목이 없습니다.'))
    defaults = default_preferences()
    shortcut = validate_binding(data.get('mute_shortcut', defaults['mute_shortcut']))
    if type(data.get('remember_last', True)) is not bool or type(data.get('auto_start', False)) is not bool:
        raise ValueError(_ui_tr('설정 스위치 값이 올바르지 않습니다.'))
    if data.get('scope', 'device') not in ('device', 'process'):
        raise ValueError(_ui_tr('캡처 범위가 올바르지 않습니다.'))
    if type(data.get('channels', 0)) is not int or data.get('channels', 0) not in (0, 2, 6, 8):
        raise ValueError(_ui_tr('채널 설정이 올바르지 않습니다.'))
    if type(data.get('channel_auto',True)) is not bool:
        raise ValueError(_ui_tr('채널 설정이 올바르지 않습니다.'))
    if data.get('process_sort', 'audio') not in ('recent', 'cpu', 'audio'):
        raise ValueError(_ui_tr('프로세스 정렬 설정이 올바르지 않습니다.'))
    for key, default in (('window_width',860),('window_height',1000)):
        dimension=data.get(key,default)
        if type(dimension) is not int or not 860<=dimension<=10000:
            raise ValueError(_ui_tr('창 크기 설정이 올바르지 않습니다.'))
    for key in ('input', 'output', 'game_exe'):
        if not isinstance(data.get(key, ''), str) or len(data.get(key, '')) > 512:
            raise ValueError(_ui_tr('장치 또는 프로세스 설정이 올바르지 않습니다.'))
    controls = data.get('controls', defaults['controls'])
    if not isinstance(controls, dict):
        raise ValueError(_ui_tr('오디오 옵션 형식이 올바르지 않습니다.'))
    allowed = set(defaults['controls'])
    if set(controls)-allowed or allowed-set(controls)-{'gain','impact'}:
        raise ValueError(_ui_tr('오디오 옵션 항목이 올바르지 않습니다.'))
    controls=dict(controls); controls.setdefault('gain',1.0)
    controls.setdefault('impact',.85)
    c = Controls(**controls)
    if c.mode not in ('normal', 'pure') or type(c.bypass) is not bool or type(c.background) is not bool or type(c.transient) is not bool:
        raise ValueError(_ui_tr('오디오 옵션 값이 올바르지 않습니다.'))
    if type(c.strength) not in (int, float) or not 0 <= c.strength <= 1 or c.limiter not in ('hard', 'soft'):
        raise ValueError(_ui_tr('오디오 옵션 범위가 올바르지 않습니다.'))
    if type(c.gain) not in (int,float) or not 0<=c.gain<=1.5:
        raise ValueError(_ui_tr('진동 세기 범위 오류'))
    if type(c.impact) not in (int,float) or not 0<=c.impact<=1:
        raise ValueError(_ui_tr('충격 보존 범위 오류'))
    for key in ('center', 'rear', 'lfe'):
        if type(getattr(c, key)) is not bool:
            raise ValueError(_ui_tr('채널 옵션 값이 올바르지 않습니다.'))
    out = dict(defaults)
    out.update({key: data.get(key, defaults[key]) for key in defaults})
    out['controls'] = c.__dict__
    out['mute_shortcut'] = shortcut
    return out


class PreferenceStore:
    def __init__(self, path):
        self.path = Path(path)
        self.data = default_preferences()
        self.error = None
        self.recovered_backup = None

    def load(self):
        if not self.path.exists():
            return dict(self.data)
        try:
            self.data = validate(json.loads(self.path.read_text(encoding='utf-8')))
        except Exception as exc:
            self.error = str(exc)
            backup = self.path.with_name(self.path.stem + f'.corrupt-{int(time.time())}' + self.path.suffix)
            try:
                os.replace(self.path, backup)
                self.recovered_backup = backup
                self.error = str(exc) + _ui_tr(' · 손상된 파일을 별도 보관했습니다.')
            except OSError:
                # Keep the unreadable file intact and avoid replacing it on save.
                self.data['remember_last'] = False
            return dict(self.data)
        return dict(self.data)

    def save(self, data):
        wrapped = {'version': 1, 'preferences': data}
        clean = validate(wrapped)
        payload = json.dumps({'version': 1, 'preferences': clean}, ensure_ascii=False, allow_nan=False, indent=2)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        name = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=self.path.parent, delete=False) as f:
                name = f.name
                f.write(payload)
                f.flush()
                os.fsync(f.fileno())
            os.replace(name, self.path)
            self.data = clean
        finally:
            if name and Path(name).exists():
                Path(name).unlink()
