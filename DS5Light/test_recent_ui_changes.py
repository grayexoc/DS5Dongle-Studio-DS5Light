"""Recent hover and recommended-preset flows; all device operations are mocked."""
import copy,json,time,unittest
from pathlib import Path
from unittest.mock import patch
import test_studio_settings as fixture
from studio_scope import EDITABLE
from studio_fields import SECTIONS
from studio_slots import Slot
from studio_recommended import AUDIO_HAPTIC_FIELDS,PRESETS,load_preset,save_and_activate
from test_studio_recommended import Client


class ScopeTests(unittest.TestCase):
    def test_allowlist_exactly_matches_visible_studio_audio_haptic_fields(self):
        section=next(s for s in SECTIONS if s['title']=='Auto-Haptics & Speaker Effect Leak')
        self.assertEqual(AUDIO_HAPTIC_FIELDS,{f[1] for f in section['fields'] if f[1] in EDITABLE})
    def test_all_three_files_preserve_every_non_audio_live_field(self):
        for filename,_,_ in PRESETS:
            with self.subTest(filename=filename):
                client=Client();client.values={k:v for k,v in fixture.defaults().items() if k in EDITABLE}
                client.values.update(audio_buffer_length=61,polling_rate_mode=2,gyro_mode=1,trigger_reduce=4,
                                     haptics_gain=1.7,disable_speaker=0,disable_mic=0,macro_disable=0xfffffffa)
                before=dict(client.values);name,fields=load_preset(filename)
                save_and_activate(client,fields,name,2,('empty',''),dict(client.stamp),before,lambda _:None)
                self.assertEqual({k:v for k,v in before.items() if k not in AUDIO_HAPTIC_FIELDS},
                                 {k:v for k,v in client.saved_values.items() if k not in AUDIO_HAPTIC_FIELDS})
                written=next(value for kind,value in client.calls if kind=='fields')
                self.assertFalse(set(written)-AUDIO_HAPTIC_FIELDS)
    def test_extra_json_device_values_and_macro_records_are_not_imported(self):
        data=json.loads((Path('Studio Presert')/'Audio_Haptic_01.json').read_text(encoding='utf-8'))
        data['fields'].update(audio_buffer_length=128,gyro_mode=1,macro_disable=0)
        data['settings']=dict(data['fields']);data['macros']={'0':[255]*35}
        with patch.object(Path,'read_text',return_value=json.dumps(data)):
            _,fields=load_preset('Audio_Haptic_01.json')
        self.assertEqual(set(fields),AUDIO_HAPTIC_FIELDS)


class RecentUITests(unittest.TestCase):
    setUp=fixture.NativeUITests.setUp
    tearDown=fixture.NativeUITests.tearDown
    editor=fixture.NativeUITests.editor

    def walk(self,widget):
        for child in widget.winfo_children():
            yield child
            yield from self.walk(child)

    def test_five_question_hovers_show_hide_and_do_not_change_controls(self):
        icons=[w for w in self.walk(self.root) if hasattr(w,'_filter_help_hint')]
        self.assertEqual(len(icons),5)
        before=self.ui.controls
        with patch.object(self.ui,'start') as start,patch.object(self.ui,'update_controls') as edit:
            for icon in icons:
                hint=icon._filter_help_hint;hint.show();self.root.update_idletasks()
                self.assertTrue(hint.popup.winfo_exists())
                self.assertEqual(str(hint.popup.winfo_children()[0].cget('text')),hint.text)
                hint.hide();self.assertIsNone(hint.popup)
            start.assert_not_called();edit.assert_not_called()
        self.assertEqual(self.ui.controls,before)
        gain=next(w for w in icons if '100%' in w._filter_help_hint.text)
        self.assertEqual(gain.cget('bg'),gain.master.cget('bg'))
        self.ui.filter_on.set(False);self.ui.update_controls()
        for icon in icons:icon._filter_help_hint.show();icon._filter_help_hint.hide()

    def test_recommended_buttons_complete_all_three_mock_transactions(self):
        errors=[];self.root.report_callback_exception=lambda *args:errors.append(args)
        for filename,_,_ in PRESETS:
            with self.subTest(filename=filename):
                ui=self.editor();client=Client()
                client.values={k:v for k,v in fixture.defaults().items() if k in EDITABLE}
                client.values.update(audio_buffer_length=61,polling_rate_mode=2,macro_disable=0xfffffffa,disable_speaker=0)
                before=dict(client.values);row=dict(path=b'ours',serial_number='ours',container_id='test',product_string='DualSense')
                ui.doc.load(client.values);ui.path=b'ours';ui.device_rows=[row];ui.profile_stamp=dict(client.stamp)
                ui.profile_save_needed=False;ui.slots=[Slot(0,'saved','Existing'),Slot(2,'empty','')]
                ui.select_category(5);ui.select_recommended(filename)
                ui.recommended_choice.current(1);ui.recommended_choice.event_generate('<<ComboboxSelected>>')
                def reloaded(*args):
                    return dict(rows=[row],path=b'ours',cfg=19,version='v1.42.0',unsupported=[],
                                values=dict(client.values),profile=dict(client.stamp,auto_haptics_enable=client.values['auto_haptics_enable'],device_row=row),
                                macros={'0':[0]*35})
                with patch.object(ui,'with_client',side_effect=lambda op:op(client)),patch('studio_reconnect.wait_for_macros',side_effect=reloaded):
                    ui.recommended_use_button.invoke()
                    deadline=time.monotonic()+4
                    while ui.busy and time.monotonic()<deadline:self.root.update();time.sleep(.01)
                self.assertFalse(ui.busy);self.assertFalse(ui.uncertain);self.assertTrue(ui.write_ready)
                self.assertEqual(ui.profile_stamp['index'],2)
                self.assertEqual([k for k,_ in client.calls].count('activate'),1)
                for key,value in before.items():
                    if key not in AUDIO_HAPTIC_FIELDS:self.assertEqual(ui.doc.values[key],value)
                self.assertEqual(self.ui.studio.current_profile[1],2)
        self.assertFalse(errors,errors)


if __name__=='__main__':unittest.main()
