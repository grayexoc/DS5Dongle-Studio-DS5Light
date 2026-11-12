"""Recent dependency/help regression checks. Fake transport and native Tk only."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch
import test_studio_settings as fixture
from studio_settings_protocol import SettingsClient,needs_reconnect
from studio_fields import FIELDS
from studio_option_help import option_help
from studio_settings_ui import StudioSettings

class ProtocolTests(unittest.TestCase):
    def test_reconnect_tracks_keyboard_and_mouse_outputs(self):
        rows={str(i):[0]*35 for i in range(32)}
        rows['0'][0]=rows['1'][0]=rows['2'][0]=1
        rows['0'][7]=4
        rows['1'][17]=1
        rows['2'][17]=11
        pad_only={'macro_disable':0xfffffffd}
        with_keyboard={'macro_disable':0xfffffffc}
        with_mouse={'macro_disable':0xfffffff9}
        self.assertTrue(needs_reconnect(with_keyboard,pad_only,rows))
        self.assertTrue(needs_reconnect(pad_only,with_keyboard,rows))
        self.assertTrue(needs_reconnect(with_keyboard,with_mouse,rows))
        self.assertFalse(needs_reconnect(dict(with_keyboard,enable_wake=1),
                                         dict(pad_only,enable_wake=1),rows))
        self.assertTrue(needs_reconnect(with_keyboard,pad_only,{}))

    def test_probe_write_readback_and_legacy_rejection(self):
        device=fixture.Device();device.values.update(rumble_gain=100,rumble_release=0)
        client=SettingsClient(device,sleep=lambda _:None)
        self.assertEqual(client.read_rumble(),dict(rumble_gain=100,rumble_release=0))
        self.assertEqual(client.write_fields(dict(rumble_gain=150,rumble_release=2),device.values),dict(rumble_gain=150,rumble_release=2))
        legacy=SettingsClient.__new__(SettingsClient);legacy.bulk=None
        legacy.command=lambda *a,**k:bytes([0x66,12,0,2,0xc3,1,0,0xc4,1,0])
        self.assertFalse(legacy.read_rumble())
        with self.assertRaises(ValueError):legacy.write_fields({'rumble_gain':150},{'rumble_gain':100})
    def test_rumble_mode_probe_write_and_legacy_fallback(self):
        device=fixture.Device();device.values['rumble_mode']=0
        client=SettingsClient(device,sleep=lambda _:None)
        self.assertEqual(client.read_one(FIELDS['rumble_mode']),0)
        self.assertEqual(client.write_fields({'rumble_mode':2},device.values),{'rumble_mode':2})
        with patch.object(client,'command',return_value=bytes([0x66,12,1,0])) as command:
            self.assertEqual(client.read_fields([FIELDS['rumble_mode']]),({},['rumble_mode']))
            with self.assertRaises(ValueError):
                client.write_fields({'rumble_mode':1},device.values)
            self.assertTrue(all(call.args[0]==12 for call in command.call_args_list))

    def test_dependency_help_matches_conditions(self):
        for mode in (0,1,2):
            for level in (0,50):
                values=dict(auto_haptics_enable=mode,haptics_aa=3,mix_native_level=level,mix_native_filter=1,rumble_gain=100,rumble_release=0,rumble_haptic_strength=50)
                view=SimpleNamespace(doc=SimpleNamespace(values=values),busy=False)
                view.enabled_for=lambda key:StudioSettings.enabled_for(view,key)
                self.assertEqual(view.enabled_for('haptics_aa'),mode in (1,2))
                for key in ('haptics_aa','mix_native_filter','rumble_gain','rumble_release','rumble_haptic_strength'):
                    self.assertEqual(option_help(view,key).startswith('현재 비활성'),not view.enabled_for(key))

class UITests(unittest.TestCase):
    setUp=fixture.NativeUITests.setUp
    tearDown=fixture.NativeUITests.tearDown
    editor=fixture.NativeUITests.editor
    def test_live_slider_dependency_and_values_preserved(self):
        ui=self.editor();ui.select_value('auto_haptics_enable',1)
        before=ui.doc.values['mix_native_filter']
        with patch.object(ui,'with_client') as wire:
            ui.vars['mix_native_level'].set('0')
            self.assertEqual(str(ui.field_views['mix_native_filter'][1][0].cget('state')),'disabled')
            self.assertIn('0보다',option_help(ui,'mix_native_filter'))
            ui.vars['mix_native_level'].set('50')
            self.assertEqual(str(ui.field_views['mix_native_filter'][1][0].cget('state')),'readonly')
            self.assertFalse(option_help(ui,'mix_native_filter').startswith('현재 비활성'))
            wire.assert_not_called()
        self.assertEqual(ui.doc.values['mix_native_filter'],before)
    def test_device_rumble_mode_switch(self):
        ui=self.editor();ui.doc.values.update(rumble_gain=125,rumble_release=1,rumble_mode=2)
        ui.doc.baseline.update(rumble_gain=125,rumble_release=1,rumble_mode=2)
        ui.select_category(1)
        for mode in (0,1,2,0):
            ui.changed('auto_haptics_enable',mode)
            self.assertEqual(str(ui.range_controls['rumble_gain'][0].cget('state')),'normal' if mode==0 else 'disabled')
            self.assertEqual(ui.doc.values['rumble_gain'],125)
            self.assertEqual(ui.doc.values['rumble_release'],1)
            self.assertEqual(ui.doc.values['rumble_mode'],2)
            self.assertEqual(str(ui.field_views['rumble_mode'][1][0].cget('state')),'readonly' if mode==0 else 'disabled')
            self.assertIn('장치 진단',option_help(ui,'rumble_mode'))

    def test_haptic_texture_mode_switch_preserves_saved_value(self):
        ui=self.editor()
        ui.doc.values['haptics_aa']=ui.doc.baseline['haptics_aa']=3
        ui.select_category(1)
        for mode in (0,1,2,0):
            ui.select_value('auto_haptics_enable',mode)
            control=ui.field_views['haptics_aa'][1][0]
            self.assertEqual(str(control.cget('state')),'readonly' if mode in (1,2) else 'disabled')
            self.assertEqual(ui.doc.values['haptics_aa'],3)
            self.assertNotIn('haptics_aa',ui.doc.changes)

if __name__=='__main__':unittest.main()
