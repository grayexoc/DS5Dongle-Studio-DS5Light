import unittest,threading,time
from types import SimpleNamespace
from unittest.mock import patch,Mock
from studio_settings_ui import StudioSettings
from studio_slots import _DEVICE_LOCK,Slot
from studio_snapshot import identity_fields,snapshot
from studio_backup import backup_all,_SLOT_DEFAULTS
from test_studio_settings import defaults

class AuditRepairs(unittest.TestCase):
 def test_snapshot_retries_when_known_pico_is_initially_absent(self):
  from device_binding import DeviceBinding,DeviceIdentity
  binding=DeviceBinding()
  binding._identity=DeviceIdentity(hid_path=b'ours',serial='ours')
  row=dict(path=b'ours',serial_number='ours')
  with patch('studio_snapshot.devices',side_effect=[[],[row]]),patch('hid.device') as hid,patch('studio_snapshot.SettingsClient') as create,patch('studio_snapshot.identity_fields',return_value=('v53',22)):
   client=create.return_value
   client.profile.return_value=dict(index=0,name='Xbox',edited=False)
   client.read_fields.return_value=({'usb_gamepad_mode':1},[])
   self.assertEqual(snapshot(b'ours',binding=binding)['path'],b'ours')
   hid.return_value.open_path.assert_called_once_with(b'ours')
 def test_expected_usb_mode_change_matches_same_port_only(self):
  from device_binding import DeviceBinding,DeviceIdentity
  binding=DeviceBinding()
  old=r'USB\VID_054C&PID_0DF2\old'
  xbox=r'USB\VID_1209&PID_0001\new'
  binding._identity=DeviceIdentity(hid_path=b'old',usb_parent_id=old)
  row=dict(path=b'new',usb_parent_id=xbox,vendor_id=0x1209,product_id=1,serial_number='pico')
  other=dict(path=b'other',usb_parent_id='other',vendor_id=0x1209,serial_number='other')
  paths={old:('port-1',),xbox:('port-1',),'other':('port-2',)}
  with patch('windows_device_identity.usb_port_paths',side_effect=lambda p:paths.get(p,())):
   self.assertIsNone(binding.resolve_hid([row]))
   binding.expect_reconnect(usb_mode_change=True)
   del paths[old]
   self.assertEqual(binding.resolve_hid([other,row]),row)
   self.assertIsNone(binding.resolve_hid([other]))
   self.assertIsNone(binding.resolve_hid([row,dict(row,path=b'ambiguous')]))
 def test_legacy_saved_filter_numbers_do_not_enable_auto_follow(self):
  from preferences import default_preferences,validate
  values=default_preferences()
  values.pop('follow_studio_filter_defaults')
  self.assertFalse(validate(dict(version=1,preferences=values))['follow_studio_filter_defaults'])
  values['follow_studio_filter_defaults']=True
  self.assertTrue(validate(dict(version=1,preferences=values))['follow_studio_filter_defaults'])
 def test_snapshot_recovers_when_xinput_replaces_the_old_hid_path(self):
  old=dict(path=b'dualsense',serial_number='ours',vendor_id=0x054c)
  new=dict(path=b'xinput',serial_number='ours',vendor_id=0x1209)
  stale,fresh=Mock(),Mock()
  stale.open_path.side_effect=OSError('open failed')
  with patch('studio_snapshot.devices',side_effect=[[old],[new]]),patch('hid.device',side_effect=[stale,fresh]),patch('studio_snapshot.SettingsClient') as create,patch('studio_snapshot.identity_fields',return_value=('v53',22)):
   client=create.return_value
   client.profile.return_value=dict(index=0,name='Xbox',edited=False)
   client.read_fields.return_value=({'usb_gamepad_mode':1},[])
   result=snapshot(old['path'])
   self.assertEqual(result['path'],new['path'])
   stale.open_path.assert_called_once_with(old['path'])
   fresh.open_path.assert_called_once_with(new['path'])
   stale.close.assert_called_once()
   fresh.close.assert_called_once()
 def test_snapshot_recovery_does_not_open_another_pico(self):
  old=dict(path=b'dualsense',serial_number='ours')
  other=dict(path=b'xinput',serial_number='other')
  stale=Mock()
  stale.open_path.side_effect=OSError('open failed')
  with patch('studio_snapshot.devices',side_effect=[[old],[other],[other]]),patch('hid.device',return_value=stale) as device:
   with self.assertRaisesRegex(OSError,'open failed'):
    snapshot(None,deadline=time.monotonic()+.8)
   device.assert_called_once()
   stale.close.assert_called_once()
 def test_legacy_slot_and_power_lock_timeout_never_opens_device(self):
  from studio_slots import run_device
  from studio_power import exchange
  for module,operation in (('studio_slots',lambda:run_device(b'fake')),('studio_power',lambda:exchange(b'fake',1))):
   lock=Mock();lock.acquire.return_value=False
   with patch(module+'._DEVICE_LOCK',lock),patch('hid.device') as device:
    with self.assertRaises(TimeoutError):operation()
    lock.acquire.assert_called_once_with(timeout=3)
    lock.release.assert_not_called();device.assert_not_called()
 def test_legacy_slot_and_power_release_lock_on_open_failure(self):
  from studio_slots import run_device
  from studio_power import exchange
  for module,operation in (('studio_slots',lambda:run_device(b'fake')),('studio_power',lambda:exchange(b'fake',1))):
   lock=Mock();lock.acquire.return_value=True
   with patch(module+'._DEVICE_LOCK',lock),patch('hid.device') as device:
    device.return_value.open_path.side_effect=OSError('disconnected')
    with self.assertRaises(OSError):operation()
    lock.release.assert_called_once();device.return_value.close.assert_called_once()
 def test_cancelled_wait_never_opens_device(self):
  obj=SimpleNamespace(path=b'fake',app=SimpleNamespace(),cancel=threading.Event())
  errors=[]
  def run():
   try:StudioSettings.with_client(obj,lambda client:self.fail('operation ran'))
   except RuntimeError as exc:errors.append(str(exc))
  with patch('hid.device') as device:
   _DEVICE_LOCK.acquire()
   try:
    t=threading.Thread(target=run,daemon=True);t.start();obj.cancel.set();t.join(.5)
    self.assertFalse(t.is_alive());self.assertTrue(errors);device.assert_not_called()
   finally:_DEVICE_LOCK.release()
 def test_lock_released_when_cancelled_before_open(self):
  obj=SimpleNamespace(path=b'fake',app=SimpleNamespace(),cancel=threading.Event());obj.cancel.set()
  with patch('hid.device') as device:
   with self.assertRaises(RuntimeError):StudioSettings.with_client(obj,lambda client:None)
   device.assert_not_called()
  self.assertTrue(_DEVICE_LOCK.acquire(blocking=False));_DEVICE_LOCK.release()
 def test_numeric_fork_version_and_invalid_fallback(self):
  class Client:
   def read_fields(self,fields):return dict(fw_major=1,fw_minor=42,fw_patch=0,config_version=22),[]
   def metadata(self,command):return (bytes([129,102,5])+self.version).ljust(64,b'\0')
  c=Client()
  for raw,expected in ((b'31','v31'),(b'v31','v31'),(b'1.4.7-exp.26','v1.4.7-exp.26'),(b'<bad>','v1.42.0')):
   c.version=raw;self.assertEqual(identity_fields(c)[0],expected)
 def test_backup_preserves_conflicting_legacy_values(self):
  values=defaults();values.update(gyro_output=2,stick_mouse=1,macro_disable=0xffffffff)
  class Client:
   def read_lightbar(self,*,refresh=False):return {}
   def read_rumble(self,*,refresh=False):return {}
   def slots(self):return [Slot(0,'saved','Legacy')]
   def read_one(self,field,slot=None):return values.get(field[1],_SLOT_DEFAULTS.get(field[1],0))
   def read_macros(self):return {}
  saved=backup_all(Client())['slots'][0]['fields']
  self.assertEqual((saved['gyro_output'],saved['stick_mouse']),(2,1))
