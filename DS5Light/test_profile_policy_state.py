import unittest
from unittest.mock import MagicMock
from studio_document import SettingsDocument
from studio_entry import EntryQueries

class PolicyTests(unittest.TestCase):
 def test_xbox_replace_rear_uses_standard_usb_audio(self):
  from studio_panel import StudioPanel
  from types import SimpleNamespace
  panel=StudioPanel.__new__(StudioPanel)
  panel.binding=MagicMock()
  panel.observed_profile=dict(auto_haptics_enable=2,ah_dsp_source=1)
  panel.binding.snapshot.return_value=SimpleNamespace(hid_path=b'hid#vid_1209&pid_0001')
  self.assertFalse(panel.rear_control_required())
  panel.binding.snapshot.return_value=SimpleNamespace(hid_path=b'hid#vid_054c&pid_0ce6')
  self.assertTrue(panel.rear_control_required())

 def test_first_haptics_enable_stages_the_mode_preset_on_both_usb_modes(self):
  from studio_recommended import FACTORY_AUDIO_HAPTIC_FIELDS,PRESETS,load_preset
  for usb_mode in (0,1):
   for mode in (1,2):
    with self.subTest(usb_mode=usb_mode,mode=mode):
     d=SettingsDocument()
     d.load(dict(FACTORY_AUDIO_HAPTIC_FIELDS,auto_haptics_enable=0,usb_gamepad_mode=usb_mode))
     d.values['auto_haptics_enable']=mode
     d.companion_edit('auto_haptics_enable',0,mode)
     self.assertEqual({k:d.values[k] for k in load_preset(PRESETS[mode][0])[1]},load_preset(PRESETS[mode][0])[1])
     self.assertNotIn('usb_gamepad_mode',d.changes)
     d.values['auto_haptics_enable']=0
     d.companion_edit('auto_haptics_enable',mode,0)
     self.assertFalse(d.changes)
 def test_first_haptics_enable_keeps_the_customized_profile(self):
  from studio_recommended import FACTORY_AUDIO_HAPTIC_FIELDS
  d=SettingsDocument()
  d.load(dict(FACTORY_AUDIO_HAPTIC_FIELDS,auto_haptics_enable=0,usb_gamepad_mode=1,auto_haptics_gate=27))
  d.values['auto_haptics_enable']=1
  d.companion_edit('auto_haptics_enable',0,1)
  self.assertEqual(d.changes,{'auto_haptics_enable':1})
 def test_pc_filter_defaults_follow_the_mode_and_preserve_overrides(self):
  from app import App
  app=MagicMock()
  app.follow_studio_filter_defaults=True
  app.gain.get.return_value=100
  app.filter_on.get.return_value=True
  app.strength.get.return_value=40
  app.impact.get.return_value=90
  App.apply_studio_filter_defaults(app,2)
  app.strength.set.assert_called_once_with(50)
  app.impact.set.assert_called_once_with(95)
  app.strength.set.reset_mock()
  app.strength.get.return_value=41
  App.apply_studio_filter_defaults(app,2)
  app.strength.set.assert_not_called()
  app.strength.get.return_value=40
  app.follow_studio_filter_defaults=False
  App.apply_studio_filter_defaults(app,2)
  app.strength.set.assert_not_called()

 def doc(self,mode=1,gain=1.7):
  d=SettingsDocument();d.load(dict(auto_haptics_enable=mode,haptics_gain=gain,auto_haptics_gate=16));return d
 def test_read_and_revert_do_not_count_policy_as_edit(self):
  d=self.doc();self.assertFalse(d.dirty);self.assertFalse(d.changes);self.assertEqual(d.export_json()['fields']['haptics_gain'],1.7)
  d.values['auto_haptics_gate']=20;self.assertTrue(d.dirty);d.revert()
  self.assertFalse(d.dirty);self.assertEqual(d.baseline['haptics_gain'],1.7)
 def test_mode_roundtrip_restores_gain(self):
  d=self.doc(0);d.values['auto_haptics_enable']=1;d.normalize_haptic_gain(stage=True)
  d.values['auto_haptics_enable']=0;d.normalize_haptic_gain()
  self.assertEqual(d.values['haptics_gain'],1.7);self.assertFalse(d.changes)
 def test_read_updates_untouched_values_and_keeps_conflict_baseline(self):
  d=self.doc(0);d.values['auto_haptics_gate']=20
  d.merge_read_values(dict(auto_haptics_gate=18,haptics_gain=1.2))
  self.assertEqual(d.values['haptics_gain'],1.2)
  self.assertEqual(d.values['auto_haptics_gate'],20)
  self.assertEqual(d.baseline['auto_haptics_gate'],16)
 def test_other_edit_does_not_send_existing_gain(self):
  d=self.doc();d.values['auto_haptics_gate']=24
  self.assertEqual(d.changes,{'auto_haptics_gate':24})
 def test_user_transition_survives_read_then_reverts(self):
  d=self.doc(0);d.values['auto_haptics_enable']=1;d.normalize_haptic_gain(stage=True)
  d.merge_read_values(dict(d.baseline))
  self.assertEqual(d.changes,{'auto_haptics_enable':1,'haptics_gain':1.0})
  d.revert();self.assertFalse(d.changes);self.assertEqual(d.values['haptics_gain'],1.7)
 def test_existing_replace_profile_is_preserved(self):
  d=self.doc(2);self.assertFalse(d.changes);self.assertEqual(d.export_json()['fields']['haptics_gain'],1.7)
 def test_confirmed_apply_clears_policy(self):
  d=self.doc();d.load(dict(d.baseline,**d.changes));self.assertFalse(d.changes);self.assertFalse(d.dirty)
 def test_external_profile_can_replace_policy_only_document(self):
  e=EntryQueries();e.doc=self.doc();e.path=b'ours';e.profile_stamp=dict(index=0,name='A',edited=False)
  e.external_stale=False;e.uncertain=False;e.write_ready=True;e.profile_save_needed=False
  e.device_choice=MagicMock();e.progress=MagicMock();e.identity=MagicMock();e.app=MagicMock()
  e.merge_entry_snapshot(dict(rows=[dict(path=b'ours')],path=b'ours',profile=dict(index=1,name='B',edited=False),values=dict(auto_haptics_enable=0,haptics_gain=1.4),cfg=21,version='test'))
  self.assertTrue(e.write_ready);self.assertEqual(e.profile_stamp['name'],'B');self.assertFalse(e.doc.dirty)
 def test_companion_roundtrips_and_manual_override(self):
  for parent,child,old,new,original in [('auto_haptics_enable','disable_speaker',0,1,1),('lightbar_fixed','lightbar_off',0,1,1)]:
   d=SettingsDocument();d.load({parent:old,child:original})
   def edit(k,v):
    previous=d.values[k];d.values[k]=v;d.companion_edit(k,previous,v)
   edit(parent,new);edit(parent,old);self.assertFalse(d.changes)
   edit(parent,new);edit(child,0);edit(parent,old);self.assertEqual(d.values[child],0)
   d.revert();self.assertFalse(d._companions);self.assertFalse(d.changes)
 def test_partial_import_preserves_missing_lightbar(self):
  d=SettingsDocument();d.load(dict(lightbar_fixed=1,lightbar_rgb=123,auto_haptics_enable=0))
  d.import_json({'fields':{'auto_haptics_enable':0}})
  self.assertFalse(d.changes)

if __name__=='__main__':unittest.main()
