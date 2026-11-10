"""Recent dependency/help regression checks. Fake transport and native Tk only."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch
import test_studio_settings as fixture
from studio_settings_protocol import SettingsClient
from studio_fields import FIELDS
from studio_option_help import option_help
from studio_settings_ui import StudioSettings

class ProtocolTests(unittest.TestCase):
    def test_probe_write_readback_and_legacy_rejection(self):
        device=fixture.Device();device.values.update(rumble_gain=100,rumble_release=0)
        client=SettingsClient(device,sleep=lambda _:None)
        self.assertEqual(client.read_rumble(),dict(rumble_gain=100,rumble_release=0))
        self.assertEqual(client.write_fields(dict(rumble_gain=150,rumble_release=2),device.values),dict(rumble_gain=150,rumble_release=2))
        legacy=SettingsClient.__new__(SettingsClient);legacy.bulk=None
        legacy.command=lambda *a,**k:bytes([0x66,12,0,2,0xc3,1,0,0xc4,1,0])
        self.assertFalse(legacy.read_rumble())
        with self.assertRaises(ValueError):legacy.write_fields({'rumble_gain':150},{'rumble_gain':100})
    def test_dependency_help_matches_conditions(self):
        for mode in (0,1,2):
            for level in (0,50):
                values=dict(auto_haptics_enable=mode,mix_native_level=level,mix_native_filter=1,rumble_gain=100,rumble_release=0,rumble_haptic_strength=50)
                view=SimpleNamespace(doc=SimpleNamespace(values=values),busy=False)
                view.enabled_for=lambda key:StudioSettings.enabled_for(view,key)
                for key in ('mix_native_filter','rumble_gain','rumble_release','rumble_haptic_strength'):
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
        ui=self.editor();ui.doc.values.update(rumble_gain=125,rumble_release=1)
        ui.doc.baseline.update(rumble_gain=125,rumble_release=1)
        ui.select_category(1)
        for mode in (0,1,2,0):
            ui.changed('auto_haptics_enable',mode)
            self.assertEqual(str(ui.range_controls['rumble_gain'][0].cget('state')),'normal' if mode==0 else 'disabled')
            self.assertEqual(ui.doc.values['rumble_gain'],125)
            self.assertEqual(ui.doc.values['rumble_release'],1)

if __name__=='__main__':unittest.main()
