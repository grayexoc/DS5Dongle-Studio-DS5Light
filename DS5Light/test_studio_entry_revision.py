import unittest
from unittest.mock import Mock,patch
from types import SimpleNamespace
from studio_entry import EntryQueries
from studio_document import SettingsDocument
from studio_gyro_calibration import counts_result
from studio_scope import EDITABLE
from studio_settings_ui import FieldTip
import test_studio_settings as fixture
import test_studio_macro_flow as macro_fixture

class EntryTests(unittest.TestCase):
    def editor(self,category=0):
        e=EntryQueries();e.closed=False;e.entry_failed=False;e.unsupported_fields=set();e.entry_generation=1;e.entry_job=None;e.entry_attempts=set()
        e.busy=False;e.app=SimpleNamespace(selected_tab=2,studio=SimpleNamespace(busy=False))
        e.slots_cache_path=None
        e.category=category;e.path=b'device';e.doc=SettingsDocument();e.doc.load({k:0 for k in EDITABLE});e.task=Mock()
        return e
    def test_slots_reused_until_cache_is_invalidated(self):
        e=self.editor(5);e.entry_step(1);e.entry_step(1)
        self.assertEqual(e.task.call_count,1);self.assertEqual(e.task.call_args.args[0],'slots')
        e.slots_cache_path=e.path
        e.entry_generation=2;e.entry_attempts=set();e.entry_step(2)
        self.assertEqual(e.task.call_count,1)
        e.invalidate_slot_cache();e.entry_step(2)
        self.assertEqual(e.task.call_count,2)
    def test_missing_values_each_category_and_zero_is_valid(self):
        for category in range(6):
            e=self.editor(category);e.doc=SettingsDocument();e.entry_step(1);e.entry_step(1)
            self.assertEqual(e.task.call_args_list[0].args[0],'entry_read')
            self.assertEqual(sum(c.args[0]=='entry_read' for c in e.task.call_args_list),1)
        e=self.editor();e.entry_step(1);e.task.assert_not_called()
    def test_stale_entry_does_not_query(self):
        e=self.editor(5);e.entry_step(0);e.task.assert_not_called()
    def test_immediate_tooltip(self):
        tip=FieldTip.__new__(FieldTip);tip.hide=Mock();tip.show=Mock()
        tip.enter();tip.hide.assert_called_once();tip.show.assert_called_once()
    def test_calibration_comparison_and_validation(self):
        n,rows,ratio=counts_result(6500,180,{})
        self.assertEqual(n,13000);self.assertIsNone(ratio)
        n,rows,ratio=counts_result(3250,90,rows)
        self.assertEqual((n,ratio),(13000,2))
        for angle in (0,-1,'nan','inf',.1,'1e-310'):
            with self.assertRaises(ValueError):counts_result(6500,angle,rows)
        self.assertEqual(rows,{6500:180,3250:90})

class RevisionUITests(unittest.TestCase):
    setUp=fixture.NativeUITests.setUp
    tearDown=fixture.NativeUITests.tearDown
    editor=fixture.NativeUITests.editor
    def test_merge_keeps_staged_values(self):
        e=self.editor();e.path=b'device';e.profile_stamp={'index':0,'name':'Test','edited':False}
        key='auto_haptics_gain';original=e.doc.baseline[key];e.doc.values[key]=original+1
        e.doc.values.pop('audio_buffer_length');e.doc.baseline.pop('audio_buffer_length')
        result=dict(rows=[dict(path=b'device',product_string='DualSense')],path=b'device',values={key:10,'audio_buffer_length':48},profile=dict(e.profile_stamp),version='Test',cfg=19)
        with patch.object(e.app.studio,'_observe_profile'),patch.object(e.app.studio,'_sync_current_profile'),patch.object(e.app.studio,'enforce_haptics_policy'):
            e.merge_entry_snapshot(result)
        self.assertEqual(e.doc.values[key],original+1);self.assertEqual(e.doc.baseline[key],original)
        self.assertEqual(e.doc.values['audio_buffer_length'],48)
        result['profile']['index']=1;e.merge_entry_snapshot(result)
        self.assertFalse(e.write_ready);self.assertEqual(e.doc.values[key],original+1)
    def test_mix_before_replace_and_gyro_panels(self):
        e=self.editor();keys=list(e.vars)
        self.assertLess(keys.index('auto_mute_mix'),keys.index('auto_mute_replace'))
        e.select_category(3)
        self.assertTrue(hasattr(e,'gyro_angle'))
        e.path=b'device';e.app.studio.controller_connected=True
        e.doc.baseline.update(gyro_mode=0,gyro_output=1,gyro_sens_mode=1)
        self.assertEqual(e.gyro_calibration_ready(),(False,False))
        e.doc.baseline.update(gyro_mode=2,gyro_output=1,gyro_sens_mode=1)
        e.doc.values.update(gyro_mode=2,gyro_output=1,gyro_sens_mode=1)
        self.assertEqual(e.gyro_calibration_ready(),(True,True))
        e.write_ready=False;e.uncertain=True
        with patch.object(e,'task') as task:
            e.send_calibration(6500)
            task.assert_not_called()
        e.write_ready=True;e.uncertain=False
        with patch.object(e,'with_client') as hid:
            e.gyro_angle.set('180');e.compute_calibration();e.apply_calibration()
            self.assertEqual(e.doc.values['flick_counts_360'],13000);hid.assert_not_called()
    def test_macro_wizard_one_panel_and_navigation(self):
        ui,e=macro_fixture.MacroFlowUITests.macro(self,macro_fixture.record(chord=1,keys=[4]))
        try:
            for index in (0,1,0,1,0):
                e.go_step(index)
                self.assertEqual(e.step,index)
                self.assertEqual([bool(w.winfo_manager()) for w in e.step_hosts],[i==index for i in range(2)])
            self.assertTrue(e.summary.get())
        finally:e.close()

if __name__=='__main__':unittest.main()
