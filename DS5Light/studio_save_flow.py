"""Explicit profile-local and shared macro persistence flows."""
from studio_i18n import text as _ui_tr
import copy
from studio_dialogs import messagebox,profile_switch


class SaveFlow:
    def macro_edit_ready(self):
        from studio_power import blocked
        if (self.closed or self.busy or self.app._close_requested or self.app.studio.busy
                or not self.loaded or not self.write_ready or self.external_stale or self.uncertain
                or self.invalid or blocked(self.app) or not self.doc.macro_baseline
                or 'macro_disable' not in self.doc.values):
            self.progress.configure(text=_ui_tr('매핑을 저장할 수 없습니다. 다른 작업을 마친 뒤 장치와 매핑 목록을 새로 고침하세요.'),kind='warning');self.update_state();return False
        return True

    def save_registered_macro(self,index,record,stamp):
        mask=int(self.doc.values['macro_disable'])&~(1<<index)
        self.save_macro_edits(stamp,mask=mask,record=(index,record))

    def save_macro_edits(self,stamp,*,mask=None,record=None):
        """Enable only after the shared definition has survived save/reconnect."""
        def complete():
            if (self.closed or self.busy or self.app._close_requested or not self.loaded
                    or not self.write_ready or self.external_stale or self.uncertain
                    or self.cancel.is_set()):return
            if self.profile_stamp!=stamp or (record is not None and self.doc.macros.get(str(record[0]))!=record[1]):
                self.progress.configure(text=_ui_tr('매핑은 Pico에 저장됐지만 프로필이 변경되어 자동 활성화를 중단했습니다. 새로 고침으로 확인하세요.'),kind='warning');self.update_state();return
            if mask is None:return
            target=self.current_save_target()
            if target is None:return
            self.changed('macro_disable',mask)
            self.render_fields()
            self.progress.configure(text=_ui_tr('Pico 매핑 저장 확인 · 현재 프로필 사용 체크 변경됨 · 프로필 저장 대기'),kind='action');self.update_state()
            from studio_dialogs import confirm_macro_profile
            other_changes=len(set(self.doc.user_changes)-{'macro_disable'})
            accepted=confirm_macro_profile(self.parent,target,other_changes)
            if self.closed or self.app._close_requested:return
            if (self.busy or not self.loaded or not self.write_ready or self.external_stale
                    or self.uncertain or self.profile_stamp!=stamp):
                self.progress.configure(text=_ui_tr('프로필 상태가 변경되어 저장을 중단했습니다. 새로 고침으로 확인하세요.'),kind='warning');self.update_state();return
            if accepted:
                try:self.apply(True,target=target)
                except Exception as exc:
                    self.progress.configure(text=_ui_tr('프로필 저장 시작 실패 · 편집값은 유지됩니다. ')+str(exc),kind='error');self.update_state()
            else:
                self.progress.configure(text=_ui_tr('매핑 동작은 Pico에 저장됨 · 프로필 저장은 보류했습니다. 변경된 사용 체크는 아직 적용·저장되지 않았습니다.'),kind='action');self.update_state()
        try:self.save_shared_macros(after=complete)
        except Exception as exc:
            self.render_fields()
            self.progress.configure(text=_ui_tr('매핑 저장 시작 실패 · 편집값은 유지됩니다. ')+str(exc),kind='error');self.update_state()

    def current_save_target(self):
        profile=self.profile_stamp or {}
        index=profile.get('index')
        if not isinstance(index,int) or not 0<=index<32:return None
        return index,profile.get('name') or ''

    def profile_changes_pending(self):
        return bool(self.doc.changes or self.doc.unsaved or self.profile_save_needed)

    def shared_changes_pending(self):
        return bool(self.doc.macro_changes or self.doc.macros_pending_flash)

    def request_profile_switch(self,callback):
        if self.busy:return
        if self.uncertain:
            self.progress.configure(text=_ui_tr('저장 결과를 확인하지 못해 프로필 전환을 중단했습니다. 미저장 매핑은 내보내기로 보관한 뒤 새로 고침하세요.'),kind='warning');self.update_state();return
        profile_pending=self.profile_changes_pending();shared_pending=self.shared_changes_pending()
        if not (profile_pending or shared_pending):callback();return
        decision=profile_switch(self.parent,profile=profile_pending,shared=shared_pending,
                                profile_applied=self.doc.unsaved or self.profile_save_needed,
                                shared_applied=self.doc.macros_pending_flash)
        if decision=='discard':
            if self.doc.macros_pending_flash:
                messagebox.showinfo(_ui_tr('공유 매크로'),_ui_tr('이미 장치에 적용된 공용 매핑은 프로필 전환으로 되돌릴 수 없습니다. 내보내기로 보관한 뒤 새로 고침으로 확인하세요.'),parent=self.parent)
                return
            self.doc.revert();self.invalid.clear();callback()
        elif decision=='save':
            if profile_pending and self.current_save_target() is None:
                self.select_category(5);self.progress.configure(text=_ui_tr('저장할 프로필 슬롯을 먼저 선택하세요.'));return
            def save_profile():
                if profile_pending:self.apply(True,after=callback)
                else:callback()
            if shared_pending:self.save_shared_macros(after=save_profile)
            else:save_profile()

    def save_shared_macros(self,after=None):
        if not self.loaded or not self.write_ready or self.busy or self.invalid:return
        from studio_shift import validate_reserved_inputs
        try:validate_reserved_inputs(self.doc.macros,self.doc.values)
        except ValueError as exc:
            messagebox.showinfo(_ui_tr('입력 조합 제한'),str(exc),parent=self.parent);return
        changes=copy.deepcopy(self.doc.macro_changes)
        if not changes and not self.doc.macros_pending_flash:
            if after:after()
            return
        before=copy.deepcopy(self.doc.macro_baseline)
        stamp=copy.deepcopy(self.profile_stamp);path=self.path
        serial=next((d.get('serial_number') for d in self.device_rows if d['path']==path),None) or self.app.studio.device_serials.get(path)
        self.after_shared_save=after
        def send(client):
            self.results.put(('progress',_ui_tr('Pico 매핑 저장 전 상태 확인 중…'),None))
            if stamp is not None and client.profile()!=stamp:raise RuntimeError(_ui_tr('현재 프로필이 바뀌었습니다. 새로 고침으로 확인하세요.'))
            actual=client.read_macros()
            for index in changes:
                if actual.get(str(index))!=before.get(str(index)):
                    raise RuntimeError(_ui_tr('공유 매크로가 외부에서 변경되었습니다. 새로 고침으로 확인하세요.'))
            from studio_shift import extended
            if any(extended(row) for row in changes.values()):
                client.require_macro_features(list(changes.values()))
            for number,(index,record) in enumerate(changes.items(),1):
                self.results.put(('progress',_ui_tr('Pico 매핑 전송 중… {0}/{1}').format(number,len(changes)),None))
                client.write_macro(index,record)
            self.results.put(('progress',_ui_tr('Pico 매핑 적용값 확인 중…'),None))
            verified=client.read_macros()
            if any(verified.get(str(i))!=r for i,r in changes.items()):raise RuntimeError(_ui_tr('공유 매크로 적용값 불일치 · 새로 고침으로 확인하세요.'))
            self.results.put(('progress',_ui_tr('Pico 매핑·매크로 저장 중…'),None))
            client.commit_macros()  # Acknowledged global table save; never retry.
            self.results.put(('progress',dict(reconnecting=True),None))
            reset_uncertain=False
            try:client.reconnect_usb()
            except (OSError,RuntimeError):
                if self.cancel.is_set():raise
                reset_uncertain=True
            return dict(macros=verified,reset_uncertain=reset_uncertain)
        def operation():
            result=self.with_client(send)
            self.results.put(('progress',_ui_tr('Pico 재연결 및 매핑 저장 결과 확인 중…'),None))
            from studio_reconnect import wait_for_macros
            try:
                fresh=wait_for_macros(path,serial,self.cancel)
                if fresh['macros']!=result['macros']:raise RuntimeError(_ui_tr('공유 매크로 저장 후 조회값이 다릅니다.'))
                result['reloaded']=fresh
            except Exception as exc:result['reload_error']=str(exc)
            return result
        self.app.studio.binding.expect_reconnect()
        self.stopped_task('shared_save',operation)

    def finish_shared_save(self,result):
        if not result.get('reloaded'):
            self.resume=False;self.uncertain=True;self.write_ready=False
            self.progress.configure(text=_ui_tr('공유 매크로 저장 후 확인하지 못했습니다. 새로 고침으로 확인하세요.'),kind='warning')
            return False
        fresh=result['reloaded']
        old_serial=next((row.get('serial_number') for row in self.device_rows if row['path']==self.path),None) or self.app.studio.device_serials.get(self.path)
        new_serial=next((row.get('serial_number') for row in fresh['rows'] if row['path']==fresh['path']),None)
        stamp={k:fresh['profile'].get(k) for k in ('index','name','edited')}
        # The recovery reader already pinned the physical Pico. A changed HID
        # path alone must not label the preserved profile draft as external.
        # Require a stable serial AND unchanged profile; never relax stale edits.
        if (not self.external_stale and old_serial and old_serial==new_serial
                and self.profile_stamp==stamp):self.path=fresh['path']
        # Keep unrelated profile edits staged. The shared action never sends
        # fields, the per-profile enable mask, save_flash or save_slot.
        self.doc.macros=copy.deepcopy(fresh['macros']);self.doc.macro_baseline=copy.deepcopy(fresh['macros'])
        self.doc.macros_pending_flash=False
        self.merge_entry_snapshot(fresh)
        self.doc.macros=copy.deepcopy(fresh['macros']);self.doc.macro_baseline=copy.deepcopy(fresh['macros'])
        if self.external_stale or not self.write_ready:
            self.resume=False
            self.progress.configure(text=_ui_tr('공유 매크로 저장 확인 · 프로필이 변경되어 새로 고침 필요'),kind='warning')
            return False
        self.progress.configure(text=_ui_tr('Pico 매핑·매크로 저장 확인 · 모든 프로필이 공유'),kind='info')
        return True
