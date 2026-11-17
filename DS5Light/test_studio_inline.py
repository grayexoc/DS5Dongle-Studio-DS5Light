import unittest,tkinter as tk,copy,time,threading
from pathlib import Path
from unittest.mock import Mock,patch
import test_studio_settings as fixture
from test_studio_slots import Fake
from studio_settings_protocol import SettingsClient
from studio_fields import FIELDS
from studio_snapshot import identity_fields,device_labels

def reply(command,body):return (bytes([0x81,0x66,command])+bytes(body)).ljust(64,b'\0')

class ReadTests(unittest.TestCase):
    def test_version_matches_real_u8_bulk_response(self):
        raw=reply(12,[0,4,125,1,1,126,1,42,127,1,0,0,1,19])
        d=Fake([raw]);c=SettingsClient(d,sleep=lambda _:None)
        self.assertEqual(identity_fields(c),('v1.42.0',19));self.assertTrue(c.bulk)
        self.assertEqual(len(d.sent),2)
    def test_fork_version_string_overrides_upstream_numbers(self):
        raw=reply(12,[0,4,125,1,1,126,1,42,127,1,0,0,1,19])
        d=Fake([raw,reply(5,b'1.4.7-exp.26')]);c=SettingsClient(d,sleep=lambda _:None)
        self.assertEqual(identity_fields(c),('v1.4.7-exp.26',19))
    def test_stale_single_field_response_is_ignored(self):
        d=Fake([reply(4,[19,100]),reply(4,[18,1])]);c=SettingsClient(d,sleep=lambda _:None)
        self.assertEqual(c.read_one(FIELDS['auto_haptics_enable']),1)
        self.assertEqual(len(d.sent),1)
    def test_matching_unsupported_scalar_reply_is_rejected_without_retry(self):
        field=FIELDS['auto_haptics_enable'];fid=field[0]
        d=Fake([reply(4,[0xff,0,0]),reply(4,[0xff,fid+1,1]),reply(4,[0xff,fid,1])])
        c=SettingsClient(d,sleep=lambda _:None)
        with self.assertRaisesRegex(ValueError,'미지원'):c.read_one(field)
        self.assertEqual([p[2] for p in d.sent],[4])
        self.assertFalse(d.replies)

    def test_scalar_zero_remains_valid_when_confirmed_by_legacy_bulk(self):
        field=FIELDS['auto_haptics_enable'];fid=field[0]
        d=Fake([reply(4,[fid,0]),reply(12,[0,1,fid,1,0])]);c=SettingsClient(d,sleep=lambda _:None)
        c.bulk=True
        self.assertEqual(c.read_one(field),0)
        self.assertEqual([p[2] for p in d.sent],[4,12])
        d=Fake([reply(4,[fid,0])]);c=SettingsClient(d,sleep=lambda _:None)
        self.assertEqual(c.read_one(field),0)  # Scalar-only firmware retains its legacy contract.
        self.assertEqual([p[2] for p in d.sent],[4,12])

    def test_old_bulk_capable_firmware_cannot_turn_an_unsupported_field_into_zero(self):
        unsupported=FIELDS['auto_haptics_enable'];other=FIELDS['auto_haptics_gain']
        failure=reply(12,[1,0])
        d=Fake([failure,reply(4,[unsupported[0],0]),failure,reply(4,[other[0],88])])
        c=SettingsClient(d,sleep=lambda _:None)
        self.assertEqual(c.read_fields([unsupported,other]),({other[1]:88},[unsupported[1]]))
        self.assertEqual([p[2] for p in d.sent],[12,4,12,4])
    def test_stale_bulk_group_does_not_trigger_slow_fallback(self):
        d=Fake([reply(12,[0,1,19,1,100]),reply(12,[0,1,18,1,1])]);c=SettingsClient(d,sleep=lambda _:None)
        self.assertEqual(c.read_fields([FIELDS['auto_haptics_enable']]),({'auto_haptics_enable':1},[]))
        self.assertEqual([r[2] for r in d.sent],[12]);self.assertTrue(c.bulk)
    def test_deadline_stops_before_new_packet(self):
        d=Fake([]);c=SettingsClient(d,sleep=lambda _:None);c.deadline=time.monotonic()-1
        with self.assertRaises(RuntimeError):c.read_fields()
        self.assertFalse(d.sent)
    def test_slot_name_on_device_label(self):
        labels=device_labels([dict(path=b'test',product_string='DualSense')],b'test',dict(index=1,name='Audio Haptic'))
        self.assertEqual(labels,['DualSense · 01']);self.assertNotIn('Audio Haptic',labels[0])
    def test_build_does_not_bundle_preferences(self):
        s=Path('build.ps1').read_text(encoding='utf-8')
        self.assertNotIn("Copy-Item -LiteralPath 'package-data/preferences.json'",s)
        self.assertIn('Remove-Item -LiteralPath $ds5OldPreferences',s)

class InlineTests(unittest.TestCase):
    setUp=fixture.NativeUITests.setUp
    tearDown=fixture.NativeUITests.tearDown
    editor=fixture.NativeUITests.editor
    def test_file_parse_is_off_ui_thread_and_discarded_for_another_pico(self):
        ui=self.editor();ui.path=b'old'
        entered=threading.Event();release=threading.Event();ui_thread=threading.get_ident()
        callback=Mock();validate_thread=[]
        def parse(data):
            validate_thread.append(threading.get_ident());entered.set();release.wait(2);return data
        with patch('studio_settings_ui.Path.read_text',return_value='{"slots": []}'):
            try:
                ui.read_json_file('mock.json',callback,parse)
                self.assertTrue(entered.wait(1));self.assertTrue(ui.busy)
                ui.path=b'new';self.root.update()
            finally:release.set()
            end=time.monotonic()+2
            while ui.busy and time.monotonic()<end:self.root.update();time.sleep(.01)
            self.root.update_idletasks()
        self.assertFalse(ui.busy);self.assertNotEqual(validate_thread,[ui_thread]);callback.assert_not_called()
    def test_readonly_draft_stays_open_and_cannot_claim_saved(self):
        ui=self.editor();ui.write_ready=False
        ui.doc.macros={str(i):[0]*35 for i in range(32)};ui.doc.macro_baseline=copy.deepcopy(ui.doc.macros)
        ui.select_category(4)
        with patch('tkinter.Toplevel',side_effect=AssertionError('extra window')),patch.object(ui,'with_client') as hid:
            ui.new_macro();e=ui.macro_editor
            self.assertTrue(e.embedded);self.assertIsInstance(e.dialog,tk.Frame);self.assertFalse(e.closed)
            self.assertIn('disabled',ui.read_button.state());self.assertIn('disabled',ui.apply_button.state())
            e.buttons[0].set(True);e.keys[0].set('A');e.go_step(1);e.commit();hid.assert_not_called()
        self.assertFalse(e.closed);self.assertFalse(ui.doc.dirty);self.assertFalse(ui.write_ready)
        self.assertIn('저장할 수 없는 상태',e.feedback.get());e.close()
        self.assertEqual(ui.editor_holder.winfo_manager(),'')
    def test_draft_survives_parent_list_redraw(self):
        ui=self.editor();ui.doc.macros={str(i):[0]*35 for i in range(32)};ui.doc.macro_baseline=copy.deepcopy(ui.doc.macros);ui.select_category(4)
        ui.new_macro();e=ui.macro_editor;e.name.set('Draft')
        ui.render_fields();self.assertTrue(e.dialog.winfo_exists());self.assertEqual(e.name.get(),'Draft')
        e.close();self.assertEqual(str(ui.search_entry.cget('state')),'normal')

if __name__=='__main__':unittest.main()
