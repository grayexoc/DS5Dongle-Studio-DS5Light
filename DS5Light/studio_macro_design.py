"""Presentation-only macro rules. No HID, timers or output engine."""
from studio_i18n import text as _ui_tr
from studio_shift import POWER_OFF
import copy

CONDITIONS={'tap':_ui_tr('짧게 누르기'),'long':_ui_tr('길게 누르기'),'double':_ui_tr('빠르게 두 번 누르기'),'hold':_ui_tr('누르는 동안 유지')}
KINDS={'button':_ui_tr('버튼 입력'),'stick':_ui_tr('스틱 방향'),'swipe':_ui_tr('터치패드 스와이프')}
OUTPUTS={'controller':_ui_tr('듀얼센스 버튼'),'keyboard':_ui_tr('키보드'),'mouse':_ui_tr('마우스'),'profile':_ui_tr('프로필 전환')}

def condition(record):
    if record[4]&128 and not record[4]&32:return 'tap'
    if record[4]&32 or record[5]&2:return 'hold'
    if record[5]&16:return 'double'
    if record[5]&1:return 'long'
    return 'tap'

def category(record):
    chord=int.from_bytes(bytes(record[:4]),'little')
    return _ui_tr('버튼 매핑') if record[4]==0 and chord.bit_count()==1 and condition(record)=='hold' else _ui_tr('조건 매크로')

def populated(record):return record is not None and any(record) and not record[4]&16

def conflicts(records,disable_mask=0xffffffff):
    """Only enabled rows; warn rather than changing firmware precedence."""
    active=[(int(i),r) for i,r in records.items() if populated(r) and not disable_mask&(1<<int(i))]
    active.sort();out=[]
    for n,(i,a) in enumerate(active):
        ca=int.from_bytes(bytes(a[:4]),'little')
        for j,b in active[n+1:]:
            cb=int.from_bytes(bytes(b[:4]),'little');pair=f'{i+1:02d} · {j+1:02d}'
            if a[4]!=b[4] or bool(a[5]&32)!=bool(b[5]&32) or 31 in (a[17],b[17]):continue
            if a[4]&32:
                out.append(pair+_ui_tr(' · 같은 스틱의 방향 매핑이 겹칩니다. 여러 출력이 필요한지 확인하세요.'));continue
            if a[4]&128:
                out.append(pair+_ui_tr(' · 같은 터치 스와이프입니다. 먼저 일치하는 행이 실행됩니다.'));continue
            if not ca or not cb:continue
            if ca==cb:
                modes={condition(a),condition(b)}
                if modes=={'tap','double'}:
                    out.append(pair+_ui_tr(' · 같은 입력의 한 번/두 번 누르기입니다. 한 번 누르기 판정이 최대 250ms 대기할 수 있습니다.'))
                elif modes!={'tap','long'}:
                    out.append(pair+_ui_tr(' · 실행 입력이 같습니다. 의도한 조건 구분인지 확인하세요.'))
            elif ca&cb in (ca,cb):
                out.append(pair+_ui_tr(' · 단독 입력과 조합 입력이 겹칩니다. 단독 입력을 먼저 누르면 조합이 실행되지 않을 수 있습니다.'))
    return out

class MacroDraft:
    """Preserve unused and unknown bytes when the corresponding UI is untouched."""
    def __init__(self,record):
        if len(record)!=35 or record[4]&16:raise ValueError(_ui_tr('편집 가능한 일반 매크로가 아닙니다.'))
        self.original=list(record)
        g=record[4];o=record[17]
        self.initial=dict(name=bytes(record[19:35]).split(b'\0')[0].decode('utf-8','replace'),
            kind='stick' if g&32 else 'swipe' if g&128 else 'button',gesture=g,
            chord=int.from_bytes(bytes(record[:4]),'little'),condition=condition(record),hold=record[6],
            output_kind='profile' if 23<=o<=30 else 'keyboard' if o==0 else 'mouse' if 11<=o<=15 else 'controller',output=o,
            keys=tuple(record[7:11]),release=record[11],threshold=record[18],hide=bool(record[5]&4),always=bool(record[5]&8),layer=bool(record[5]&32),chime=bool(record[5]&64))
    def build(self,state,strict=False):
        s=dict(state);before=self.initial;raw=list(self.original)
        if s['kind'] not in KINDS or s['condition'] not in CONDITIONS or s['output_kind'] not in OUTPUTS:raise ValueError(_ui_tr('실행 조건과 출력 종류를 확인하세요.'))
        if strict:
            if s['kind']=='button' and not s['chord']:raise ValueError(_ui_tr('01 · 실행할 입력 버튼을 선택하세요.'))
            if s['kind']=='stick' or s['output_kind']=='keyboard':
                if not any(s['keys']):raise ValueError(_ui_tr('02 · 출력할 키를 한 개 이상 지정하세요.'))
            elif not s['output']:raise ValueError(_ui_tr('02 · 출력 동작을 선택하세요.'))
        name=s['name'].encode('utf-8')
        if s['name']!=before['name']:
            if len(name)>16:raise ValueError(_ui_tr('이름은 UTF-8 기준 16바이트까지 저장할 수 있습니다.'))
            raw[19:35]=name.ljust(16,b'\0')
        if s['kind']!=before['kind'] or s['gesture']!=before['gesture']:
            raw[4]=0 if s['kind']=='button' else s['gesture']
        if s['chord']!=before['chord'] or s['kind']!=before['kind']:
            raw[:4]=(0 if s['kind']=='stick' else int(s['chord'])).to_bytes(4,'little')
        rule_changed=any(s[k]!=before[k] for k in ('kind','condition','hide','always'))
        if rule_changed:
            flags=(self.original[5]&~31)|{'tap':0,'long':1,'double':16,'hold':2}[s['condition']]
            if s['kind']=='stick':flags=(flags&~17)|2
            if s['kind']=='swipe':flags=(flags&~31)|(4 if s['hide'] else 0)
            if flags&2 and s['hide']:flags|=4
            if s['kind']=='stick' and flags&4 and s['always']:flags|=8
            raw[5]=flags
        for key,offset,maximum in [('hold',6,255),('release',11,255),('threshold',18,120)]:
            value=s[key]
            if type(value)is not int or not 0<=value<=maximum:raise ValueError(_ui_tr('세부 설정의 숫자 범위를 확인하세요.'))
            if key=='threshold' and value and value<10:raise ValueError(_ui_tr('스틱 경계는 0(기본값) 또는 10~120입니다.'))
            if value!=before[key]:raw[offset]=value
        if tuple(s['keys'])!=before['keys']:
            if len(s['keys'])!=4 or any(type(v)is not int or not 0<=v<=255 for v in s['keys']):raise ValueError(_ui_tr('키는 최대 4개이며 HID 코드 범위는 0~255입니다.'))
            raw[7:11]=s['keys']
        if s['output']!=before['output'] or s['output_kind']!=before['output_kind'] or s['kind']!=before['kind']:
            output=0 if s['kind']=='stick' or s['output_kind']=='keyboard' else s['output']
            if (not 0<=output<=30 and output!=POWER_OFF) or output==0 and s['output_kind']!='keyboard' and s['kind']!='stick':raise ValueError(_ui_tr('출력 동작을 확인하세요.'))
            if s['output_kind']=='mouse' and output not in range(11,16):raise ValueError(_ui_tr('마우스 출력을 선택하세요.'))
            if s['output_kind']=='controller' and output!=POWER_OFF and (output in range(11,16) or output>=23):raise ValueError(_ui_tr('듀얼센스 출력을 선택하세요.'))
            if s['output_kind']=='profile' and output not in range(23,31):raise ValueError(_ui_tr('프로필 1~8을 선택하세요.'))
            raw[17]=output
        raw[5]=(raw[5]&~96)|(32 if s.get('layer',before['layer']) else 0)|(64 if s['output_kind']=='profile' and s.get('chime',before['chime']) else 0)
        from studio_shift import validate_extension
        validate_extension(raw)
        bytes(raw)
        return raw
