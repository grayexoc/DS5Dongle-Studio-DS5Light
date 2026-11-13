"""One read attempt per user entry, with no background retry after failure."""
from studio_i18n import text as _ui_tr
import sys
from studio_fields import SECTIONS
from studio_scope import EDITABLE
from studio_help import GROUPS

class EntryQueries:
    def init_entry_queries(self):
        self.entry_queries_enabled='--smoke-test' not in sys.argv
        self.entry_generation=0;self.entry_attempts=set();self.entry_job=None
        self.entry_failed=False;self.unsupported_fields=set()
        self.slots_cache_path=None
    def begin_entry(self):
        if not self.entry_queries_enabled:return
        self.entry_generation+=1;self.entry_attempts=set();self.entry_failed=False;self.schedule_entry()
    def schedule_entry(self):
        if not self.entry_queries_enabled or self.closed or self.entry_failed:return
        if self.entry_job:
            try:self.parent.after_cancel(self.entry_job)
            except Exception:pass
        generation=self.entry_generation
        self.entry_job=self.parent.after_idle(lambda:self.entry_step(generation))
    def entry_step(self,generation):
        self.entry_job=None
        if self.closed or self.entry_failed or generation!=self.entry_generation or self.app.selected_tab!=2:return
        if self.busy or self.app.studio.busy:
            self.entry_job=self.parent.after(200,lambda:self.entry_step(generation));return
        sections=GROUPS[self.category][1]
        expected=[f[1] for s in SECTIONS if s['title'] in sections for f in s['fields'] if f[1] in EDITABLE and f[1] not in self.unsupported_fields]
        need_fields=getattr(self,'external_stale',False) or not self.doc.values or any(k not in self.doc.values for k in expected)
        need_identity=self.category in (4,5) and not self.path
        if (need_fields or need_identity) and 'fields' not in self.entry_attempts:
            self.entry_attempts.add('fields');self.task('entry_read',self.entry_snapshot);return
        if getattr(self,'external_stale',False):return
        if not self.path:return
        if self.category==5 and self.slots_cache_path!=self.path and 'slots' not in self.entry_attempts:
            self.entry_attempts.add('slots');self.task('slots',lambda:self.with_client(lambda c:c.slots()));return
        if self.category==4 and not self.doc.macros and 'macros' not in self.entry_attempts:
            self.entry_attempts.add('macros');self.task('macros',lambda:self.with_client(lambda c:c.read_macros()))
    def entry_snapshot(self):
        from studio_snapshot import snapshot
        binding=self.app.studio.binding
        if getattr(self,'external_stale',False):
            return snapshot(binding.snapshot().hid_path or self.app.studio.profile_path,self.cancel.is_set,binding=binding)
        selected_binding=binding if self.path is None or self.path==binding.snapshot().hid_path else None
        return snapshot(self.path or self.app.studio.profile_path,self.cancel.is_set,binding=selected_binding)
    def invalidate_slot_cache(self):
        self.slots_cache_path=None
        self.entry_attempts.discard('slots')
    def merge_entry_snapshot(self,result):
        """Keep staged values and read only missing values into their baseline."""
        self.lightbar_supported=all(k in result.get('values',{}) for k in ('lightbar_fixed','lightbar_rgb'))
        self.unsupported_fields=set(result.get('unsupported',()))
        self.device_rows=result['rows'];self.device_choice.configure(values=[d.get('product_string','DualSense')+f' · {i+1:02d}' for i,d in enumerate(self.device_rows)])
        self.pico_recognized=not result.get('choose',False)
        if result.get('choose'):
            if not result['rows']:self.app.studio.controller_connected=False
            self.progress.configure(text=_ui_tr('Pico 장치를 연결하거나 목록에서 선택하세요.'));return
        self._policy_save_errors={}
        self.standby_policy=(result['path'],result.get('standby'))
        self.dock_policy=(result['path'],result.get('dock'))
        profile=result.get('profile');stamp={k:profile[k] for k in ('index','name','edited')} if profile else None
        changed=getattr(self,'external_stale',False) or (self.path is not None and self.path!=result['path']) or (self.profile_stamp is not None and any((stamp or {}).get(k)!=self.profile_stamp.get(k) for k in ('index','name')))
        if self.doc.dirty and changed:
            self.write_ready=False;self.progress.configure(text=_ui_tr('장치 프로필이 바뀌었습니다. 편집을 확인한 뒤 새로 고침을 눌러 주세요.'));return
        if changed and not self.doc.dirty:
            from studio_document import SettingsDocument
            self.doc=SettingsDocument()
        if self.path!=result['path']:
            self.slots=[]
            self.invalidate_slot_cache()
        if 'disable_usb_sn' not in result['values'] and 'disable_usb_sn' not in self.doc.changes:
            self.doc.baseline.pop('disable_usb_sn',None)
            self.doc.values.pop('disable_usb_sn',None)
        self.doc.merge_read_values(result['values'])
        self.path=result['path'];self.profile_stamp=stamp;self.loaded=bool(self.doc.values);self.external_stale=False
        self.profile_save_needed=bool(profile and profile.get('edited')) or getattr(self,'profile_save_needed',False) and not changed
        from studio_snapshot import device_labels
        self.device_choice.configure(values=device_labels(self.device_rows,self.path,profile))
        self.write_ready=profile is not None and result.get('cfg') in (19,20,21,22) and not self.uncertain
        self.device_choice.current(next(i for i,d in enumerate(self.device_rows) if d['path']==self.path))
        self.identity.set('Studio · '+str(result['version'])+' · '+((profile or {}).get('name') or _ui_tr('현재 설정')))
        self.progress.configure(text=_ui_tr('설정 {0}개 조회').format(f"{len(result['values'])}"),kind='loaded')
        if profile:self.app.studio._observe_profile(self.path,profile);self.app.studio._sync_current_profile(self.path,profile);self.app.studio.enforce_haptics_policy()
    def close_entry_queries(self):
        self.entry_generation+=1
        if self.entry_job:
            try:self.parent.after_cancel(self.entry_job)
            except Exception:pass
        self.entry_job=None
