"""Validated native/portal effect and macro file formats."""
from studio_i18n import text as _ui_tr
import struct

def effect_states(value):
    if not isinstance(value,dict):raise ValueError(_ui_tr('효과는 R2/L2 목록이어야 합니다.'))
    out={}
    for key,states in value.items():
        target={'r2':'0','l2':'1','0':'0','1':'1'}.get(str(key))
        if target is None:continue
        if not isinstance(states,list) or len(states)>5:raise ValueError(_ui_tr('트리거 효과는 최대 5단계입니다.'))
        parsed=[]
        for state in states:
            if not isinstance(state,dict):raise ValueError(_ui_tr('효과 단계 형식 오류'))
            raw=state.get('bytes');ms=state.get('duration_ms',0)
            if not isinstance(raw,list) or len(raw)!=11 or any(type(v)is not int or not 0<=v<=255 for v in raw):raise ValueError(_ui_tr('효과는 0~255의 11바이트여야 합니다.'))
            if type(ms)is not int or not 0<=ms<=65535:raise ValueError(_ui_tr('효과 길이는 0~65535ms입니다.'))
            parsed.append(dict(bytes=list(raw),duration_ms=ms))
        out[target]=parsed
    return out

def macro_records(value):
    if not isinstance(value,(dict,list)):raise ValueError(_ui_tr('매크로 목록 형식 오류'))
    out={}
    for key,row in (value.items() if isinstance(value,dict) else ((r.get('index'),r) for r in value)):
        index=int(key)
        if not 0<=index<32:raise ValueError(_ui_tr('매크로 번호 범위 오류'))
        if str(index) in out:raise ValueError(_ui_tr('매크로 번호가 중복되었습니다.'))
        if isinstance(row,dict):
            raw=[0]*35;chord=row.get('chord',0)
            if type(chord)is not int or not 0<=chord<=0xffffffff:raise ValueError(_ui_tr('버튼 조합 범위 오류'))
            raw[:4]=struct.pack('<I',chord);raw[4:7]=[row.get('gesture',0),row.get('flags',0),row.get('hold_cs',0)]
            keys=row.get('keys',[0]*4)
            if not isinstance(keys,list) or len(keys)>4:raise ValueError(_ui_tr('매크로는 최대 4키입니다.'))
            raw[7:11]=(keys+[0]*4)[:4];raw[11]=row.get('rel_order',27);raw[17]=row.get('out_btn',0);raw[18]=row.get('stick_thresh',0)
            name=str(row.get('label','')).encode('utf-8')
            if len(name)>16:raise ValueError(_ui_tr('매크로 이름은 UTF-8 16바이트 이내입니다.'))
            raw[19:35]=name.ljust(16,b'\0')
        else:raw=row
        if not isinstance(raw,list) or len(raw)!=35 or any(type(v)is not int or not 0<=v<=255 for v in raw):raise ValueError(_ui_tr('매크로 레코드는 35바이트여야 합니다.'))
        if raw[18]>120:raise ValueError(_ui_tr('매크로 출력/스틱 범위 오류'))
        if raw[4]&16:continue # excluded experimental motion: preserve local definition
        from studio_shift import validate_extension
        validate_extension(raw)
        out[str(index)]=list(raw)
    return out

def build_effect(kind,start,end,strength,frequency=35,snap=50):
    if kind not in ('resistance','vibration','break','bow'):raise ValueError(_ui_tr('효과 종류 오류'))
    if not 0<=start<=9 or not 0<=end<=9 or not 0<=strength<=100 or not 0<=snap<=100 or not 1<=frequency<=255:raise ValueError(_ui_tr('효과 값 범위 오류'))
    wire=lambda v:max(0,min(7,(v*7+50)//100));out=[0]*11
    if kind in ('break','bow'):
        lo=max(2 if kind=='break' else 0,min(7,start));hi=min(8,max(lo+1,end));zones=(1<<lo)|(1<<hi)
        out[0]=0x25 if kind=='break' else 0x22;out[3]=wire(strength)|(wire(snap)<<3 if kind=='bow' else 0)
    else:
        lo,hi=sorted((start,end));zones=sum(1<<i for i in range(lo,hi+1));bits=sum(wire(strength)<<(i*3) for i in range(10) if zones&(1<<i));out[0]=0x26 if kind=='vibration' else 0x21;out[3:7]=bits.to_bytes(4,'little')
        if kind=='vibration':out[9]=frequency
    out[1]=zones&255;out[2]=(zones>>8)&3;return out
