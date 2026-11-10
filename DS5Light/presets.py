"""Versioned PC-only slots. Never persist process IDs or device settings."""
from studio_i18n import text as _ui_tr
import json
import math
import os
import tempfile
from pathlib import Path

SLOT_COUNT = 12


def validate(value):
    if not isinstance(value, dict):
        raise ValueError(_ui_tr('프리셋 형식 오류'))
    keys = {'name', 'game_exe', 'scope', 'channels', 'input', 'output', 'controls'}
    if set(value) != keys:
        raise ValueError(_ui_tr('프리셋 항목 오류'))
    for key in ('name', 'game_exe', 'input', 'output'):
        if not isinstance(value[key], str) or len(value[key]) > 512:
            raise ValueError(_ui_tr('프리셋 문자열 오류: ')+key)
    if not value['name'].strip() or len(value['name']) > 60:
        raise ValueError(_ui_tr('슬롯 이름은 1~60자로 입력하세요'))
    if value['scope'] not in ('device', 'process') or type(value['channels']) is not int or value['channels'] not in (0,2,6,8):
        raise ValueError(_ui_tr('캡처 범위/채널 오류'))
    c = value['controls']
    required = {'mode', 'bypass', 'strength', 'background', 'transient'}
    if not isinstance(c, dict) or not required <= set(c) or set(c) - required - {'rear','lfe','limiter','center','gain','impact'}:
        raise ValueError(_ui_tr('필터 설정 형식 오류'))
    if c.get('limiter','hard') not in ('hard','soft'):
        raise ValueError(_ui_tr('합산 제한 방식 오류'))
    if c['mode'] not in ('normal', 'pure'):
        raise ValueError(_ui_tr('모드 오류'))
    if any(type(c[k]) is not bool for k in ('bypass', 'background', 'transient')):
        raise ValueError(_ui_tr('필터 스위치 오류'))
    if any(type(c.get(k,False)) is not bool for k in ('rear','lfe','center')):
        raise ValueError(_ui_tr('채널 스위치 오류'))
    if type(c['strength']) not in (float, int) or not math.isfinite(c['strength']) or not 0 <= c['strength'] <= 1:
        raise ValueError(_ui_tr('억제 세기 범위 오류'))
    gain=c.get('gain',1.0)
    if type(gain) not in (int,float) or not math.isfinite(gain) or not 0<=gain<=1.5:
        raise ValueError(_ui_tr('진동 세기 범위 오류'))
    impact=c.get('impact',.85)
    if type(impact) not in (int,float) or not math.isfinite(impact) or not 0<=impact<=1:
        raise ValueError(_ui_tr('충격 보존 범위 오류'))
    return value


def match_game(exe, candidates):
    """No arbitrary PID when multiple instances share a name."""
    matches = [pid for name, pid in candidates if exe and name.casefold() == exe.casefold()]
    return matches[0] if len(matches) == 1 else None


class PresetStore:
    def __init__(self, path):
        self.path = Path(path)
        self.slots = [None] * SLOT_COUNT
        self.bindings = {}
        self.error = None
        try:
            if self.path.exists():
                doc = json.loads(self.path.read_text(encoding='utf-8'))
                if doc.get('version') not in (1,2,3,4,5,6) or not isinstance(doc.get('slots'), list) or len(doc['slots']) != SLOT_COUNT:
                    raise ValueError(_ui_tr('지원하지 않는 프리셋 파일 형식'))
                for item in doc['slots']:
                    if item is not None:
                        validate(item)
                self.slots = doc['slots']
                bindings=doc.get('bindings',{})
                if not isinstance(bindings,dict) or any(not isinstance(name,str) or not name or len(name)>512
                    or type(index) is not int or not 0<=index<SLOT_COUNT or self.slots[index] is None
                    for name,index in bindings.items()):
                    raise ValueError(_ui_tr('게임 자동 연결 형식 오류'))
                self.bindings={name.casefold():index for name,index in bindings.items()}
        except Exception as exc:
            self.error = str(exc)

    def bound_slot(self,exe):
        return self.bindings.get(exe.casefold()) if exe else None

    def save(self, index, value, bind_game=None, auto_apply=None):
        if self.error:
            raise ValueError(_ui_tr('기존 파일을 읽지 못해 덮어쓰기를 막았습니다: ')+self.error)
        if not 0 <= index < SLOT_COUNT:
            raise ValueError(_ui_tr('슬롯 번호 오류'))
        validate(value)
        slots = list(self.slots)
        slots[index] = json.loads(json.dumps(value, allow_nan=False))
        bindings=dict(self.bindings)
        if bind_game is not None:
            if not isinstance(bind_game,str) or not bind_game or len(bind_game)>512 or type(auto_apply) is not bool:
                raise ValueError(_ui_tr('게임 자동 연결 형식 오류'))
            if auto_apply: bindings[bind_game.casefold()]=index
            else: bindings.pop(bind_game.casefold(),None)
        payload = json.dumps({'version': 6, 'slots': slots, 'bindings':bindings}, ensure_ascii=False, indent=2)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        old_version=json.loads(self.path.read_text(encoding='utf-8')).get('version') if self.path.exists() else None
        if old_version in (1,2,3,4,5):
            backup=self.path.with_name(self.path.stem+f'.v{old_version}.backup.json')
            if not backup.exists():
                with backup.open('xb') as f: f.write(self.path.read_bytes())
        name = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=self.path.parent, delete=False) as f:
                name = f.name
                f.write(payload)
                f.flush()
                os.fsync(f.fileno())
            os.replace(name, self.path)
            self.slots = slots
            self.bindings = bindings
        finally:
            if name and Path(name).exists():
                Path(name).unlink()
