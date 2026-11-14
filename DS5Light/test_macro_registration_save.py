"""Registration activates only after verified shared save; modal changes are rechecked."""
import copy
import threading
from types import SimpleNamespace
from unittest import TestCase,main
from unittest.mock import Mock,patch
from studio_save_flow import SaveFlow
from studio_dialogs import confirm_macro_profile


class RegistrationTests(TestCase):
    def setUp(self):
        self.ui=ui=SaveFlow()
        ui.closed=ui.busy=ui.external_stale=ui.uncertain=False
        ui.loaded=ui.write_ready=True
        ui.app=SimpleNamespace(_close_requested=False)
        ui.cancel=threading.Event()
        ui.parent=None
        ui.profile_stamp=dict(index=0,name='Native',edited=False)
        ui.doc=SimpleNamespace(macros={'0':[1,2,3]},values={'macro_disable':0xffffffff},user_changes={'speaker_volume':80})
        ui.progress=Mock();ui.render_fields=Mock();ui.update_state=Mock();ui.apply=Mock()
        ui.changed=lambda key,value:ui.doc.values.update({key:value})
        ui.save_shared_macros=Mock()
        self.stamp=copy.deepcopy(ui.profile_stamp)

    def begin(self):
        self.ui.save_registered_macro(0,[1,2,3],self.stamp)
        return self.ui.save_shared_macros.call_args.kwargs['after']

    def test_no_activation_or_confirmation_before_save_verified(self):
        with patch('studio_dialogs.confirm_macro_profile') as confirm:self.begin();confirm.assert_not_called()
        self.assertEqual(self.ui.doc.values['macro_disable'],0xffffffff);self.ui.apply.assert_not_called()

    def test_verified_save_selects_mask_and_later_keeps_profile_unsaved(self):
        done=self.begin()
        with patch('studio_dialogs.confirm_macro_profile',return_value=False) as confirm:done()
        self.assertEqual(self.ui.doc.values['macro_disable'],0xfffffffe)
        confirm.assert_called_once_with(None,(0,'Native'),1);self.ui.apply.assert_not_called()
        self.assertIn('아직 적용·저장',self.ui.progress.configure.call_args.kwargs['text'])

    def test_confirm_saves_only_the_original_target(self):
        done=self.begin()
        with patch('studio_dialogs.confirm_macro_profile',return_value=True):done()
        self.ui.apply.assert_called_once_with(True,target=(0,'Native'))

    def test_profile_save_start_failure_shows_error_and_keeps_activation_edit(self):
        done=self.begin();self.ui.apply.side_effect=RuntimeError('thread start failed')
        with patch('studio_dialogs.confirm_macro_profile',return_value=True):done()
        self.assertEqual(self.ui.doc.values['macro_disable'],0xfffffffe)
        self.assertIn('프로필 저장 시작 실패',self.ui.progress.configure.call_args.kwargs['text'])
        self.assertEqual(self.ui.progress.configure.call_args.kwargs['kind'],'error')

    def test_delete_mask_is_staged_only_after_verified_save(self):
        self.ui.doc.macros['0']=[0,0,0];self.ui.doc.values['macro_disable']=0xfffffffe
        self.ui.save_macro_edits(self.stamp,mask=0xffffffff,record=(0,[0,0,0]))
        self.assertEqual(self.ui.doc.values['macro_disable'],0xfffffffe)
        done=self.ui.save_shared_macros.call_args.kwargs['after']
        with patch('studio_dialogs.confirm_macro_profile',return_value=False):done()
        self.assertEqual(self.ui.doc.values['macro_disable'],0xffffffff);self.ui.apply.assert_not_called()

    def test_import_completion_does_not_change_profile_mask_or_prompt(self):
        self.ui.save_macro_edits(self.stamp)
        done=self.ui.save_shared_macros.call_args.kwargs['after']
        with patch('studio_dialogs.confirm_macro_profile') as confirm:done();confirm.assert_not_called()
        self.assertEqual(self.ui.doc.values['macro_disable'],0xffffffff);self.ui.apply.assert_not_called()

    def test_uncertain_save_cannot_discard_local_edits_and_switch_profiles(self):
        self.ui.uncertain=True;callback=Mock()
        with patch('studio_save_flow.profile_switch') as dialog:self.ui.request_profile_switch(callback);dialog.assert_not_called()
        callback.assert_not_called();self.assertIn('새로 고침',self.ui.progress.configure.call_args.kwargs['text'])

    def test_profile_change_before_completion_blocks_checkbox_and_prompt(self):
        done=self.begin();self.ui.profile_stamp=dict(index=1,name='Other',edited=False)
        with patch('studio_dialogs.confirm_macro_profile') as confirm:done();confirm.assert_not_called()
        self.assertEqual(self.ui.doc.values['macro_disable'],0xffffffff);self.ui.apply.assert_not_called()

    def test_profile_switch_inside_confirmation_cannot_save_new_profile(self):
        done=self.begin()
        def switch(*args):self.ui.profile_stamp=dict(index=1,name='Other',edited=False);return True
        with patch('studio_dialogs.confirm_macro_profile',side_effect=switch):done()
        self.ui.apply.assert_not_called();self.assertIn('저장을 중단',self.ui.progress.configure.call_args.kwargs['text'])

    def test_failed_recovery_close_or_cancel_cannot_continue(self):
        for attribute in ('uncertain','external_stale','closed','busy'):
            with self.subTest(attribute=attribute):
                done=self.begin();setattr(self.ui,attribute,True)
                with patch('studio_dialogs.confirm_macro_profile') as confirm:done();confirm.assert_not_called()
                self.assertEqual(self.ui.doc.values['macro_disable'],0xffffffff)
                setattr(self.ui,attribute,False)
        self.ui.apply.assert_not_called()
        self.ui.cancel.set()
        with patch('studio_dialogs.confirm_macro_profile') as confirm:self.begin()();confirm.assert_not_called()

    def test_other_profile_edits_are_disclosed_and_later_is_default(self):
        with patch('studio_dialogs._message',return_value=False) as dialog:
            self.assertFalse(confirm_macro_profile(None,(0,'Native'),2))
        args=dialog.call_args
        self.assertNotIn('다른 사용 체크와 미저장 설정',args.args[3])
        self.assertNotIn('편집 상태로만 남습니다',args.args[3])
        self.assertIn('2개',args.args[3]);self.assertEqual(args.kwargs['cancel_label'],'나중에')


if __name__=='__main__':main()
