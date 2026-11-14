"""Search visible names and commands, never help/tooltip prose or device data."""
from studio_i18n import text as _ui_tr
import unicodedata
from studio_help import GROUPS,TITLES,label,options
from studio_recommended import PRESETS

def normalized(text):
    return ''.join(unicodedata.normalize('NFKC',str(text)).casefold().split())

def category_for(section):
    return next((i for i,(_,sections) in enumerate(GROUPS) if section in sections),None)

def field_matches(field,section,query):
    category=category_for(section)
    names=[label(field[1]),field[1],field[3],section,TITLES.get(section,section)]
    if category is not None:names.append(GROUPS[category][0])
    for heading,keys in (
        (_ui_tr('자이로 입력·출력'),('gyro_mode','gyro_output','gyro_axis','gyro_invert')),
        (_ui_tr('자이로 감도'),('gyro_sens_mode','gyro_sens','gyro_sens_y','gyro_natural_x10','gyro_natural_y_x10','gyro_scale_trim_x100')),
        (_ui_tr('Flick Stick · 게임 회전값'),('flick_angle','flick_counts_360')),
    ):
        if field[1] in keys:names.append(heading)
    if field[4]=='select':names.extend(str(value) for _,value in options(field))
    return any(normalized(query) in normalized(name) for name in names)

# title, category, destination card title, additional visible names
FEATURES=(
    (_ui_tr('추천 프리셋'),5,_ui_tr('추천 프리셋'),tuple(title for _,title,_ in PRESETS)+
     tuple(filename for filename,_,_ in PRESETS)+(_ui_tr('저장 슬롯'),_ui_tr('저장 후 사용'))),
    (_ui_tr('Studio 프로필 슬롯'),5,_ui_tr('Studio 프로필 슬롯'),
     (_ui_tr('슬롯 목록 새로 고침'),_ui_tr('전체 슬롯 내보내기'),_ui_tr('전체 슬롯 가져오기'),_ui_tr('현재 설정 저장'),_ui_tr('이름 변경'),_ui_tr('불러오기'),_ui_tr('9–32번 슬롯 펼치기'))),
    (_ui_tr('현재 설정 파일'),5,_ui_tr('현재 설정 파일'),(_ui_tr('JSON 가져오기'),_ui_tr('JSON 내보내기'),_ui_tr('HTML 내보내기'))),
    (_ui_tr('Pico 펌웨어 설치'),5,_ui_tr('Pico 펌웨어 설치'),(_ui_tr('부트로더 재시작'),)),
    (_ui_tr('Pico 매핑·매크로'),4,_ui_tr('Pico 매핑·매크로'),
     (_ui_tr('매핑 목록 새로 고침'),_ui_tr('매핑·매크로 추가'),_ui_tr('자동 저장'),_ui_tr('실행 조건'),_ui_tr('실행 동작'),
      _ui_tr('버튼 입력'),_ui_tr('스틱 방향'),_ui_tr('버튼 선택'),_ui_tr('키보드 입력 지정'),_ui_tr('버튼 눌러 지정'),_ui_tr('키를 놓는 순서'))),
    (_ui_tr('매핑 파일 · 입력 확인'),4,_ui_tr('매핑 파일 · 입력 확인'),(_ui_tr('가져오기'),_ui_tr('내보내기'),_ui_tr('실시간 입력 확인'),_ui_tr('입력 확인 중지'))),
    (_ui_tr('자이로 센서 보정'),3,_ui_tr('자이로 센서 보정'),(_ui_tr('측정'),_ui_tr('보정값을 편집에 반영'))),
    (_ui_tr('게임의 360° 마우스 이동량'),3,_ui_tr('게임의 360° 마우스 이동량'),
     (_ui_tr('6500 전송'),_ui_tr('3250 전송'),_ui_tr('실제 회전각'),_ui_tr('회전각 기록·계산'),_ui_tr('기록 초기화'),_ui_tr('계산값을 편집에 반영'))),
    (_ui_tr('고급 트리거 효과'),2,None,(_ui_tr('웹 설정'),)),
    (_ui_tr('설정 적용·저장'),5,None,(_ui_tr('되돌리기'),_ui_tr('임시 적용'),_ui_tr('현재 프로필에 저장'))),
)

def feature_matches(feature,query):
    title,category,_,names=feature
    return any(normalized(query) in normalized(name) for name in (title,GROUPS[category][0],*names))
