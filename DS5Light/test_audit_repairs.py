import unittest,threading
from types import SimpleNamespace
from unittest.mock import patch,Mock
from studio_settings_ui import StudioSettings
from studio_slots import _DEVICE_LOCK,Slot
from studio_snapshot import identity_fields
from studio_backup import backup_all,_SLOT_DEFAULTS
from test_studio_settings import defaults

class AuditRepairs(unittest.TestCase):
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
   def read_lightbar(self):return {}
   def read_rumble(self):return {}
   def slots(self):return [Slot(0,'saved','Legacy')]
   def read_one(self,field,slot=None):return values.get(field[1],_SLOT_DEFAULTS.get(field[1],0))
   def read_macros(self):return {}
  saved=backup_all(Client())['slots'][0]['fields']
  self.assertEqual((saved['gyro_output'],saved['stick_mouse']),(2,1))
