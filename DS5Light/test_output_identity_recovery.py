import unittest
from device_binding import DeviceBinding,DeviceIdentity
from windows_audio import attach_endpoint_ids
class IdentityTests(unittest.TestCase):
 def binding(self):
  b=DeviceBinding();b._identity=DeviceIdentity(container_id='ours',endpoint_id='out',endpoint_name='Old');return b
 def row(self,**kw):return dict(dict(index=1,name='Renamed',maxOutputChannels=4,endpoint_id='out'),**kw)
 def test_same_endpoint_without_container_recovers(self):
  b=self.binding();r=self.row();self.assertIs(b.output([r],'Old'),r)
 def test_conflicting_container_never_recovers(self):
  self.assertIsNone(self.binding().output([self.row(container_id='other')]))
 def test_unknown_endpoint_without_container_never_recovers(self):
  self.assertIsNone(self.binding().output([self.row(endpoint_id='other')]))
 def test_manual_new_selection_is_respected(self):
  b=self.binding();old=self.row(name='Old',container_id='ours');new=self.row(name='New',endpoint_id='new',container_id='ours')
  self.assertIs(b.output([old,new],'New'),new)
 def test_duplicate_names_are_not_assigned_arbitrary_ids(self):
  rows=[self.row(name='Same'),self.row(name='Same',index=2)]
  for r in rows:r.pop('endpoint_id')
  attach_endpoint_ids(rows,[dict(id='one',name='Same',container_id='ours'),dict(id='two',name='Same',container_id='other')])
  self.assertIsNone(self.binding().output(rows));self.assertEqual(self.binding().output_issue(rows),'ambiguous')
 def test_stale_name_does_not_block_same_container(self):
  b=DeviceBinding();b._identity=DeviceIdentity(container_id='ours')
  r=self.row(container_id='ours');self.assertIs(b.output([r],'Old name'),r)
 def test_manual_confirmation_requires_identified_hid_and_endpoint(self):
  b=self.binding();self.assertFalse(b.confirm_output(self.row()))
  b._identity=DeviceIdentity(hid_path=b'hid',container_id='ours')
  self.assertTrue(b.confirm_output(self.row()))
  self.assertIsNotNone(b.snapshot().endpoint_id)
 def test_manual_confirmation_rejects_other_container_and_stereo(self):
  b=DeviceBinding();b._identity=DeviceIdentity(hid_path=b'hid',container_id='ours')
  self.assertFalse(b.confirm_output(self.row(container_id='other')))
  self.assertFalse(b.confirm_output(self.row(maxOutputChannels=2)))
 def test_manual_confirmation_does_not_enable_automatic_guessing(self):
  b=DeviceBinding();b._identity=DeviceIdentity(hid_path=b'hid',container_id='ours')
  r=self.row();self.assertIsNone(b.output([r]))
  self.assertTrue(b.confirm_output(r));self.assertIs(b.output([r]),r)

class AutoPairTests(unittest.TestCase):
 def setup_pair(self):
  binding=DeviceBinding()
  binding._identity=DeviceIdentity(hid_path=b'hid',serial='pico',container_id='HID')
  output=dict(name='DualSense Edge',maxOutputChannels=4,endpoint_id='audio',container_id='AUDIO')
  return binding,output,[dict(path=b'hid',serial_number='pico')]
 def test_single_device_auto_pair(self):
  binding,output,hids=self.setup_pair()
  self.assertTrue(binding.auto_pair_output([output],hids))
  self.assertIs(binding.output([output]),output)
 def test_multiple_or_other_hid_rejected(self):
  binding,output,hids=self.setup_pair()
  self.assertFalse(binding.auto_pair_output([output],hids*2))
  self.assertFalse(binding.auto_pair_output([output],[dict(path=b'other',serial_number='other')]))
 def test_multiple_outputs_or_other_manual_selection_rejected(self):
  binding,output,hids=self.setup_pair()
  self.assertFalse(binding.auto_pair_output([output,dict(output,endpoint_id='second')],hids))
  self.assertFalse(binding.auto_pair_output([output],hids,'Other output'))

if __name__=='__main__':unittest.main()
