import unittest
from unittest.mock import MagicMock
from studio_document import SettingsDocument
from studio_entry import EntryQueries

class PolicyTests(unittest.TestCase):
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
