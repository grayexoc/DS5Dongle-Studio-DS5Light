"""Extensions inside existing 35-byte Pico macro records."""
from studio_i18n import text as _ui_tr

SHIFT = 0x20
CHIME = 0x40
PROFILE_FIRST = 23
PROFILE_LAST = 30
SHIFT_KEY = 31


def extended(record):
    return bool(record[5] & (SHIFT | CHIME) or record[17] >= PROFILE_FIRST)


def shift_key(records):
    return next(((int(i), r) for i, r in records.items() if r[17] == SHIFT_KEY), None)


def set_shift_key(records, mask, bit):
    if bit is not None and (type(bit) is not int or not 0 <= bit <= 22):
        raise ValueError(_ui_tr('시프트키는 컨트롤러 버튼 하나를 선택하세요.'))
    indices = [int(i) for i, r in records.items() if r[17] == SHIFT_KEY]
    index = indices[0] if indices else next((i for i in range(32) if str(i) in records and not any(records[str(i)])), None)
    if bit is not None and index is None:
        raise ValueError(_ui_tr('시프트키를 저장하려면 매크로 한 칸이 필요합니다.'))
    result = {k: list(v) for k, v in records.items()}
    for i in indices:
        result[str(i)] = [0] * 35
        mask |= 1 << i
    if bit is not None:
        row = [0] * 35
        row[:4] = (1 << bit).to_bytes(4, 'little')
        row[5] = 2 | 4
        row[17] = SHIFT_KEY
        row[19:35] = b'Pico Shift'.ljust(16, b'\0')
        result[str(index)] = row
        mask &= ~(1 << index)
    return result, mask


def validate_extension(row):
    if row[17] > SHIFT_KEY:
        raise ValueError('매크로 출력 범위 오류')
    if row[17] == SHIFT_KEY:
        chord = int.from_bytes(bytes(row[:4]), 'little')
        if row[4] or not chord or chord & (chord - 1) or chord >= 1 << 23 or row[5] & (SHIFT | CHIME):
            raise ValueError(_ui_tr('시프트키 레코드 형식 오류'))
    if row[5] & CHIME and not PROFILE_FIRST <= row[17] <= PROFILE_LAST:
        raise ValueError(_ui_tr('신호음은 프로필 전환에서만 사용합니다.'))
    return row


def reserved_input(row, records, disable_mask, ps_shortcut=False):
    """Keep controller/system shortcuts; do not rewrite firmware precedence."""
    if row[4] != 0:
        return ''
    chord = int.from_bytes(bytes(row[:4]), 'little')
    if row[5] & SHIFT:
        for key, shift in records.items():
            if shift[17] == SHIFT_KEY and not disable_mask & (1 << int(key)):
                chord |= int.from_bytes(bytes(shift[:4]), 'little')
                break
    ps, create, fn = 1 << 16, 1 << 12, (1 << 19) | (1 << 20)
    if ps_shortcut and chord & ps:
        return _ui_tr('PS 기본 단축키가 켜져 있어 PS 매핑을 사용할 수 없습니다. 기본 단축키를 끄거나 다른 입력을 선택하세요.')
    if chord & ps and chord & create:
        return _ui_tr('PS + Create는 컨트롤러 페어링 조합이므로 매핑에 사용할 수 없습니다.')
    if chord & fn and chord & (0x0f | 0xf0 | (1 << 13)):
        return _ui_tr('FN + 얼굴 버튼·방향키·Options는 Edge 기본 기능과 충돌할 수 있어 사용할 수 없습니다. 다른 조합을 선택하세요.')
    return ''


def validate_reserved_inputs(records, values):
    mask = int(values.get('macro_disable', 0xffffffff))
    for key, row in records.items():
        if mask & (1 << int(key)):
            continue
        reason = reserved_input(row, records, mask, bool(values.get('ps_shortcut_enabled', 0)))
        if reason:
            raise ValueError(f'{int(key)+1:02d} · ' + reason)
