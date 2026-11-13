"""Staged settings document: no HID side effects during editing or import."""
from studio_i18n import text as _ui_tr
import copy
import json
from studio_fields import FIELDS
from studio_scope import EDITABLE,LIGHTBAR_FIELDS,RUMBLE_FIELDS,config_version
from studio_settings_protocol import validate_changes
from studio_records import effect_states,macro_records
class SettingsDocument:
    def __init__(self):
        self._companions={};self._gain_before_policy=None;self.baseline={};self.values={};self.effects={};self.effect_baseline={};self.macros={};self.macro_baseline={};self.extra={};self.unsaved=False;self.save_requested=False;self.macros_pending_flash=False
    def load(self,values):
        baseline={k:v for k,v in values.items() if k in EDITABLE}
        if baseline!=self.baseline:self.save_requested=False
        self._companions={};self._gain_before_policy=None;self.baseline=baseline;self.values=dict(self.baseline)
        self.normalize_haptic_gain()
    def companion_edit(self,key,previous,value):
        if key=='sync_spk_headset_volume' and previous!=1 and value==1:
            if 'speaker_volume' in self.values and 'headset_volume' in self.values:
                self.values['headset_volume']=self.values['speaker_volume']
        if key in ('speaker_volume','headset_volume') and self.values.get('sync_spk_headset_volume')==1:
            other='headset_volume' if key=='speaker_volume' else 'speaker_volume'
            if other in self.values:self.values[other]=value
        for state in self._companions.values():
            if key==state[0]:state[3]=True
        links=[]
        if key=='auto_haptics_enable':links.append(('disable_speaker',previous,value,int(value in (1,2)),True))
        if key=='lightbar_fixed':links.append(('lightbar_off',previous,value,0,value==1))
        if key=='mix_native_level':links.append(('mix_native_filter',bool(previous),bool(value),0,bool(value)))
        if key in ('auto_haptics_enable','mix_native_level'):
            old_mix=(previous==1 and bool(self.values.get('mix_native_level'))) if key=='auto_haptics_enable' else (
                self.values.get('auto_haptics_enable')==1 and bool(previous))
            new_mix=self.values.get('auto_haptics_enable')==1 and bool(self.values.get('mix_native_level'))
            links.append(('ah_dsp_source',old_mix,new_mix,0,new_mix))
        for child,old,new,target,can_start in links:
            if old==new:continue
            if child not in self.values:continue
            if child not in self._companions:
                if not can_start:continue
                self._companions[child]=[child,old,self.values[child],False]
            state=self._companions[child]
            if new==state[1]:
                if not state[3]:self.values[child]=state[2]
                del self._companions[child]
            elif not state[3]:self.values[child]=target

    def normalize_haptic_gain(self,stage=False):
        # Stage the policy locally; preserve the true device baseline for Apply.
        if self.values.get('auto_haptics_enable') in (1,2) and 'haptics_gain' in self.baseline and (stage or self._gain_before_policy is not None):
            if self._gain_before_policy is None:self._gain_before_policy=self.values['haptics_gain']
            self.values['haptics_gain']=1.0
        elif self._gain_before_policy is not None:
            self.values['haptics_gain']=self._gain_before_policy
            self._gain_before_policy=None
    @property
    def changes(self):return {k:v for k,v in self.values.items() if k in EDITABLE and k in self.baseline and v!=self.baseline[k]}
    @property
    def policy_changes(self):
        return {'haptics_gain':1.0} if self._gain_before_policy is not None and self._gain_before_policy==self.baseline.get('haptics_gain') and 'haptics_gain' in self.changes else {}
    @property
    def user_changes(self):
        return {k:v for k,v in self.changes.items() if k not in self.policy_changes}
    def merge_read_values(self,values):
        edited=set(self.user_changes)
        pending_policy=self._gain_before_policy is not None
        if self._gain_before_policy is not None:
            self.values['haptics_gain']=self._gain_before_policy
            self._gain_before_policy=None
        for key,value in values.items():
            if key in EDITABLE and key not in edited:
                self.values[key]=value;self.baseline[key]=value
        self.normalize_haptic_gain(stage=pending_policy)
    @property
    def effect_changes(self):return {} # Trigger construction area is inert, including imported records.
    @property
    def macro_changes(self):return {int(k):v for k,v in self.macros.items() if not v[4]&16 and not self.macro_baseline.get(k,[0]*35)[4]&16 and v!=self.macro_baseline.get(k)}
    @property
    def dirty(self):return bool(self.user_changes or self.effect_changes or self.macro_changes)
    def revert(self):
        self._companions={};self._gain_before_policy=None;self.values=dict(self.baseline);self.normalize_haptic_gain();self.effects=copy.deepcopy(self.effect_baseline);self.macros=copy.deepcopy(self.macro_baseline)
    def import_json(self,data,take_macro_mask=False):
        if not isinstance(data,dict):raise ValueError(_ui_tr('JSON 객체가 필요합니다.'))
        raw=data.get('fields',data.get('settings',data))
        if not isinstance(raw,dict):raise ValueError(_ui_tr('설정 형식 오류'))
        changes={k:v for k,v in raw.items() if k in EDITABLE and k in self.baseline and (k!='macro_disable' or take_macro_mask)}
        if 'cfgVersion' in data and 'lightbar_fixed' in self.baseline and 'lightbar_fixed' not in raw:
            changes['lightbar_fixed']=0
        if any(k in raw and k not in self.baseline for k in LIGHTBAR_FIELDS):
            raise ValueError(_ui_tr('현재 펌웨어에서 라이트바 색상 고정 지원을 확인하지 못했습니다.'))
        if any(k in raw and k not in self.baseline for k in RUMBLE_FIELDS):
            raise ValueError(_ui_tr('현재 펌웨어에서 일반 진동 조절 지원을 확인하지 못했습니다.'))
        if 'rumble_mode' in self.baseline:
            if 'cfgVersion' in data and 'rumble_mode' not in raw:
                changes['rumble_mode']=0
        elif raw.get('rumble_mode',0)!=0:
            raise ValueError(_ui_tr('일반 진동 모드 지원을 확인하지 못했습니다.'))
        if 'usb_gamepad_mode' in self.baseline:
            if 'cfgVersion' in data and 'usb_gamepad_mode' not in raw:
                changes['usb_gamepad_mode']=0
        elif raw.get('usb_gamepad_mode',0)!=0:
            raise ValueError(_ui_tr('XBOX 모드 지원을 확인하지 못했습니다.'))
        validate_changes(self.baseline,changes)
        if take_macro_mask:
            if not self.macro_baseline:raise ValueError(_ui_tr('활성화할 매크로 정의를 먼저 읽으세요.'))
            mask=int(changes.get('macro_disable',0xffffffff))
            for key,record in self.macros.items():
                if record[4]&16 and not mask&(1<<int(key)) and int(self.baseline.get('macro_disable',0xffffffff))&(1<<int(key)):
                    raise ValueError(_ui_tr('실험 기능인 모션 매크로는 새로 활성화하지 않습니다.'))
        effects={};macros=macro_records(data.get('macros',{}))
        macros={k:v for k,v in macros.items() if not self.macro_baseline.get(k,[0]*35)[4]&16}
        from studio_macro_tools import normalize_macro
        for record in macros.values():normalize_macro(record)
        if effects and not self.effect_baseline:raise ValueError(_ui_tr('트리거 분류에서 효과를 먼저 읽은 후 가져오세요.'))
        if macros and not self.macro_baseline:raise ValueError(_ui_tr('매크로 정의를 먼저 읽은 후 가져오세요.'))
        self._companions.clear()
        self.values.update(changes)
        if 'haptics_gain' in changes:self._gain_before_policy=None
        self.normalize_haptic_gain();self.extra={k:v for k,v in raw.items() if k not in FIELDS}
        for trig,states in effects.items():
            for index,state in enumerate(states):self.effects[trig][index]=state
        self.macros.update(macros)
        return len(changes),len(raw)-sum(k in raw for k in changes)
    def export_json(self):
        values={k:v for k,v in self.values.items() if k in EDITABLE}
        return dict(name='DS5Light Studio',version=2,cfgVersion=config_version(values),fields=values,settings=values,effects={},macros={k:v for k,v in self.macros.items() if not v[4]&16})
