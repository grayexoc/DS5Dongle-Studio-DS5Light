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
    def test_gyro_choice_header_and_options_are_right_aligned(self):
        ui=self.editor();ui.select_category(3)
        control=ui.field_views['gyro_mode'][1][0]
        self.assertEqual(control.button.cget('anchor'),'e')
        self.assertEqual(control.button.cget('justify'),'right')
        control.toggle()
        self.assertTrue(control.tiles)
        for tile in control.tiles:
            self.assertEqual(tile.cget('anchor'),'e')
            self.assertEqual(tile.cget('justify'),'right')
        control.build_tiles()
        self.assertTrue(all(tile.cget('anchor')=='e' for tile in control.tiles))
    def test_windows_volume_estimate_tracks_edit_sync_and_revert_locally(self):
        ui=self.editor()
        ui.doc.load(dict(ui.doc.baseline,speaker_volume=100,headset_volume=80,sync_spk_headset_volume=1,disable_speaker=0))
        ui.render_fields()
        title=ui.range_controls['speaker_volume'][2]
        note=title.winfo_children()[-1]
        self.assertEqual(note.pack_info()['side'],'left')
        self.assertIs(note.master,title)
        self.assertEqual(len(title.pack_slaves()),3)
        self.assertIn('25%',note.cget('text'))
        with patch.object(ui,'with_client') as wire:
            ui.vars['speaker_volume'].set('110')
            self.assertIn('41%',note.cget('text'))
            ui.vars['headset_volume'].set('40')
            self.assertIn('1%',note.cget('text'))
            ui.vars['speaker_volume'].set('')
            self.assertIn('—',note.cget('text'))
            ui.revert()
            note=ui.range_controls['speaker_volume'][2].winfo_children()[-1]
            self.assertIn('25%',note.cget('text'))
            self.assertFalse(ui.doc.changes)
            wire.assert_not_called()
    def test_mode_mute_follows_audio_mode_and_preserves_values(self):
        ui=self.editor()
        ui.doc.load(dict(ui.doc.baseline,auto_haptics_enable=0,disable_speaker=0,auto_mute_mix=1,auto_mute_replace=0))
        ui.render_fields()
        def shown(key):
            return bool(next(row for _,rows,_,_,_ in ui._option_groups for name,row in rows if name==key).grid_info())
        with patch.object(ui,'with_client') as wire:
            for mode in (0,1,2,0):
                ui.changed('auto_haptics_enable',mode)
                self.assertEqual(shown('auto_mute_mix'),mode==1)
                self.assertEqual(shown('auto_mute_replace'),mode==2)
                self.assertEqual(ui.doc.values['auto_mute_mix'],1)
                self.assertEqual(ui.doc.values['auto_mute_replace'],0)
                if mode:
                    self.assertFalse(ui.enabled_for('auto_mute_mix' if mode==1 else 'auto_mute_replace'))
            wire.assert_not_called()
    def test_apply_syncs_windows_only_for_volume_edits_and_keeps_failures_separate(self):
        from unittest.mock import Mock
        ui=self.editor()
        ui.doc.load(dict(ui.doc.baseline,speaker_volume=100,headset_volume=80,disable_speaker=0))
        ui.render_fields()
        client=Mock()
        client.read_fields.side_effect=lambda fields:(dict(ui.doc.baseline),[])
        client.write_fields.side_effect=lambda changes,current:dict(changes)
        client.profile.return_value=dict(index=0,name='A',edited=True)
        ui.profile_stamp=None
        result=[]
        with patch.object(ui,'with_client',side_effect=lambda op:op(client)),patch.object(ui,'stopped_task',side_effect=lambda kind,op:result.append(op())),patch('studio_volume.sync_speaker_volume',side_effect=OSError('sync failed')) as sync:
            ui.changed('speaker_volume',90)
            ui.apply()
            self.assertEqual(result[-1]['values']['speaker_volume'],90)
            self.assertEqual(result[-1]['volume_warning'],'sync failed')
            self.assertEqual(sync.call_args.args[-1],90)
            self.assertEqual(sync.call_count,1)
            ui.doc.revert();ui.changed('headset_volume',70)
            ui.apply()
            self.assertEqual(sync.call_count,1)
            self.assertIsNone(result[-1]['volume_warning'])
    def test_enabling_volume_sync_uses_speaker_and_revert_restores_values(self):
        ui=self.editor()
        ui.doc.load(dict(ui.doc.baseline,sync_spk_headset_volume=0,speaker_volume=100,headset_volume=80))
        ui.render_fields()
        with patch.object(ui,'with_client') as wire:
            ui.changed('sync_spk_headset_volume',1)
            self.assertEqual(ui.doc.changes,dict(sync_spk_headset_volume=1,headset_volume=100))
            self.assertEqual(float(ui.vars['headset_volume'].get()),100)
            self.assertEqual(ui.doc.values['speaker_volume'],100)
            ui.revert()
            self.assertFalse(ui.doc.changes)
            self.assertEqual(float(ui.vars['headset_volume'].get()),80)
            wire.assert_not_called()
    def test_volume_sync_updates_both_controls_without_transmission(self):
        ui=self.editor()
        ui.doc.load(dict(ui.doc.baseline,sync_spk_headset_volume=1,speaker_volume=100,headset_volume=80,disable_speaker=0))
        ui.render_fields()
        self.assertFalse(ui.doc.changes)
        with patch.object(ui,'with_client') as wire:
            for key,value in (('speaker_volume',90),('headset_volume',70)):
                ui.vars[key].set(str(value))
                for linked in ('speaker_volume','headset_volume'):
                    self.assertEqual(ui.doc.values[linked],value)
                    self.assertEqual(float(ui.vars[linked].get()),value)
                self.assertEqual(ui.doc.changes['speaker_volume'],value)
                self.assertEqual(ui.doc.changes['headset_volume'],value)
            ui.revert()
            self.assertFalse(ui.doc.changes)
            self.assertEqual(float(ui.vars['speaker_volume'].get()),100)
            self.assertEqual(float(ui.vars['headset_volume'].get()),80)
            ui.changed('sync_spk_headset_volume',0)
            ui.vars['speaker_volume'].set('60')
            self.assertEqual(ui.doc.values['headset_volume'],80)
            wire.assert_not_called()
    def test_mix_toggle_links_restore_and_preserves_stored_level(self):
        ui=self.editor();ui.doc.load(dict(ui.doc.baseline,auto_haptics_enable=1,mix_native_level=0,mix_native_filter=1,ah_dsp_source=1))
        ui.render_fields()
        with patch.object(ui,'with_client') as wire:
            toggle=ui.field_views['mix_native_level'][1][0]
            self.assertEqual(str(ui.field_views['mix_native_filter'][1][0].cget('state')),'disabled')
            self.assertIn('혼합을 켜',option_help(ui,'mix_native_filter'))
            toggle.invoke()
            self.assertEqual((ui.doc.values['mix_native_level'],ui.doc.values['mix_native_filter'],ui.doc.values['ah_dsp_source']),(100,0,0))
            self.assertEqual(str(ui.field_views['mix_native_filter'][1][0].cget('state')),'readonly')
            toggle.invoke()
            self.assertFalse(ui.doc.changes)
            toggle.invoke();ui.revert()
            self.assertFalse(ui.doc.changes)
            ui.doc.load(dict(ui.doc.baseline,mix_native_level=50));ui.render_fields()
            self.assertEqual(ui.field_views['mix_native_level'][1][0].status.cget('text'),'켜짐 · 50%')
            self.assertFalse(ui.doc.changes)
            wire.assert_not_called()
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
