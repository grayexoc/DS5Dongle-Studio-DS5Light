"""Recent high-risk UI flows. Fake HID results only; no device/profile writes."""
import copy,time,unittest,threading,tkinter as tk
from unittest.mock import patch,Mock
import test_studio_settings as fixture
from studio_slots import Slot
from studio_search import FEATURES,feature_matches,field_matches,normalized
from studio_fields import FIELDS

class SearchTests(unittest.TestCase):
    def test_recommended_and_spacing_and_choices(self):
        self.assertTrue(any(feature_matches(f,'추천') and f[0]=='추천 프리셋' for f in FEATURES))
        self.assertTrue(any(feature_matches(f,'오디오 햅틱 안정형') for f in FEATURES))
        self.assertTrue(field_matches(FIELDS['gyro_mode'],'Gyro Aiming','터치패드'))
        self.assertEqual(normalized('오디오 햅틱'),normalized('오디오햅틱'))
    def test_tooltip_prose_is_not_in_index(self):
        query='음악·대사를 정확히 분리하는 기능은 아닙니다'
        self.assertFalse(any(feature_matches(f,query) for f in FEATURES))
        self.assertFalse(field_matches(FIELDS['auto_haptics_gain'],'Auto-Haptics & Speaker Effect Leak',query))

class PriorityUITests(unittest.TestCase):
    setUp=fixture.NativeUITests.setUp
    tearDown=fixture.NativeUITests.tearDown
    editor=fixture.NativeUITests.editor
    def ready(self):
        ui=self.editor();self.errors=[]
        self.root.report_callback_exception=lambda *args:self.errors.append(args)
        return ui
    def finish(self,ui):
        deadline=time.monotonic()+3
        while ui.busy and time.monotonic()<deadline:
            self.root.update();time.sleep(.005)
        self.assertFalse(ui.busy);self.assertFalse(self.errors,self.errors)
    def snapshot(self,ui,values=None):
        ui.path=b'fake';ui.profile_stamp=dict(index=0,name='Current',edited=False)
        return dict(rows=[dict(path=b'fake',product_string='DualSense',serial_number='fake')],
                    path=b'fake',profile=dict(ui.profile_stamp,auto_haptics_enable=1),cfg=19,
                    values=dict(ui.doc.values if values is None else values),unsupported=[],version='1.42.0')
    def test_read_preserves_widgets_fills_missing_and_does_not_stage_changes(self):
        ui=self.ready();ui.doc.values.pop('speaker_volume');ui.doc.baseline.pop('speaker_volume')
        ui.render_fields();ids=[str(w) for w in ui.body.winfo_children()]
        snap=self.snapshot(ui,dict(ui.doc.values,speaker_volume=72))
        with patch.object(self.ui.studio,'_observe_profile'),patch.object(self.ui.studio,'_sync_current_profile'),patch.object(self.ui.studio,'enforce_haptics_policy'):
            ui.task('entry_read',lambda:snap)
            self.assertEqual(str(ui.range_controls['speaker_volume'][0].cget('state')),'disabled')
            self.finish(ui)
        self.assertEqual(ids,[str(w) for w in ui.body.winfo_children()])
        self.assertEqual(float(ui.vars['speaker_volume'].get()),72)
        self.assertFalse(ui.doc.changes)
        self.assertEqual(str(ui.range_controls['speaker_volume'][0].cget('state')),'normal')
    def test_existing_draft_and_invalid_text_survive_entry_read(self):
        ui=self.ready();ui.changed('auto_haptics_gain',123)
        ui.vars['auto_haptics_smooth'].set('invalid')
        before=dict(ui.doc.changes);snap=self.snapshot(ui)
        with patch.object(self.ui.studio,'_observe_profile'),patch.object(self.ui.studio,'_sync_current_profile'),patch.object(self.ui.studio,'enforce_haptics_policy'):
            ui.task('entry_read',lambda:snap);self.finish(ui)
        self.assertEqual(ui.doc.changes,before);self.assertEqual(ui.vars['auto_haptics_smooth'].get(),'invalid')
        self.assertEqual(float(ui.vars['auto_haptics_gain'].get()),123)
    def test_failed_read_restores_controls_and_clears_busy(self):
        ui=self.ready();entry=ui.range_controls['auto_haptics_gain'][0]
        def fail():raise RuntimeError('simulated read failure')
        ui.task('entry_read',fail);self.finish(ui)
        self.assertNotIn('disabled',ui.read_button.state())
        self.assertEqual(str(entry.cget('state')),'normal')
        self.assertEqual(ui.cancel_button.winfo_manager(),'')
    def test_tab_switch_during_slot_read_unlocks_new_controls(self):
        ui=self.ready();ui.select_category(5);gate=threading.Event()
        try:
            ui.task('slots',lambda:(gate.wait(2),[Slot(0,'saved','Native')])[1])
            ui.select_category(1)
            self.assertEqual(str(ui.range_controls['auto_haptics_gain'][0].cget('state')),'disabled')
            gate.set();self.finish(ui)
            self.assertEqual(str(ui.range_controls['auto_haptics_gain'][0].cget('state')),'normal')
        finally:gate.set()
    def test_search_during_read_and_jump_preserve_edit(self):
        ui=self.ready();ui.changed('auto_haptics_gain',124);before=dict(ui.doc.changes)
        gate=threading.Event()
        try:
            ui.task('slots',lambda:(gate.wait(2),[])[1])
            ui.search.set('추천');ui.render_fields()
            self.assertIn('프로필 슬롯 › 추천 프리셋',ui.search_targets)
            gate.set();self.finish(ui)
            ui.jump_to_search_result(5,'추천 프리셋');self.root.update()
            self.assertEqual(ui.category,5);self.assertEqual(ui.search.get(),'')
            self.assertIn('추천 프리셋',ui.search_targets);self.assertEqual(ui.doc.changes,before)
        finally:gate.set()
    def test_dropdown_update_does_not_rebuild_or_stage_other_fields(self):
        ui=self.ready();ui.doc.values['auto_haptics_enable']=0;ui.doc.baseline['auto_haptics_enable']=0
        ui.render_fields();ids=[str(w) for w in ui.body.winfo_children()]
        ui.select_value('auto_haptics_enable',1)
        self.assertEqual(ids,[str(w) for w in ui.body.winfo_children()])
        self.assertEqual(set(ui.doc.changes),{'auto_haptics_enable','disable_speaker'})
    def test_lock_preparation_failure_restores_ui_without_starting_worker(self):
        ui=self.ready();op=Mock()
        with patch.object(ui,'read_view_lock',side_effect=RuntimeError('UI failure')):
            with self.assertRaises(RuntimeError):ui.task('slots',op)
        op.assert_not_called();self.assertFalse(ui.busy)
        self.assertNotIn('disabled',ui.read_button.state())

if __name__=='__main__':unittest.main()
