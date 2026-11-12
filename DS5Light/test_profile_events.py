import struct
import unittest
from unittest.mock import Mock,patch
from device_binding import DeviceIdentity
import studio_profile_events as events
import studio_profile_watch as watch
from test_oled_integration import binding,AH

def frame(seq=1):return b'\x8fSLP1\x01'+struct.pack('<I',seq)+bytes([1,0,1,0,0,0])

class EventTests(unittest.TestCase):
 def test_strict_frame(self):
  self.assertEqual(events.decode(frame()),1)
  for raw in (b'',frame()[:-1],frame()+b'\0',b'\x8fFAIL'+frame()[5:],frame()[:12]+b'\x03'+frame()[13:]):
   with self.assertRaises(ValueError):events.decode(raw)
 def test_same_device_collection_only(self):
  identity=DeviceIdentity(b'pad','ours')
  row=dict(path=b'event',usage_page=0xff00,usage=0x52,serial_number='ours')
  self.assertTrue(events.same_device(row,identity))
  for change in (dict(usage=1),dict(serial_number='other')):
   self.assertFalse(events.same_device(dict(row,**change),identity))
  self.assertTrue(events.same_device(dict(row,path=b'HID&col02#same',serial_number=None),DeviceIdentity(b'HID&col01#same')))
 def test_unsupported_does_not_open_gamepad_and_retries_are_bounded(self):
  monitor=events.ProfileEvents()
  class Immediate:
   def __init__(self,target,**kw):self.target=target
   def start(self):self.target()
  with patch.object(events.threading,'Thread',Immediate),patch('hid.enumerate',return_value=[]) as scan,patch('hid.device') as opened,patch.object(events.time,'monotonic') as clock:
   for clock.return_value in (0,0,1,1,3,3,30):monitor.tick(DeviceIdentity(b'pad','ours'))
   self.assertEqual(scan.call_count,3);opened.assert_not_called()
  monitor.close()
 def test_listener_deduplicates_and_falls_back_on_disconnect(self):
  monitor=events.ProfileEvents()
  class Immediate:
   def __init__(self,target,**kw):self.target=target
   def start(self):self.target()
  row=dict(path=b'event',usage_page=0xff00,usage=0x52,serial_number='ours')
  device=Mock();device.get_feature_report.return_value=frame()
  device.read.side_effect=[frame(1),frame(1),frame(2),OSError('unplug')]
  with patch.object(events.threading,'Thread',Immediate),patch('hid.enumerate',return_value=[row]),patch('hid.device',return_value=device):
   monitor.tick(DeviceIdentity(b'pad','ours'))
  messages=[]
  while not monitor.results.empty():messages.append(monitor.results.get()[1])
  self.assertEqual(messages,['ready','changed','changed','failed'])
  device.close.assert_called_once()
  monitor.close()
 def test_event_forces_read_and_busy_lock_retries_promptly(self):
  monitor=watch.ProfileWatch();fake=Mock(changed=False)
  monitor.events=fake;fake.tick=Mock()
  b=binding();clock=[100.]
  class Immediate:
   def __init__(self,target,**kw):self.target=target
   def start(self):self.target()
  data=dict(path=b'ours',profile=AH,full=True,row=None)
  with patch.object(watch.time,'monotonic',lambda:clock[0]),patch.object(watch.threading,'Thread',Immediate),patch.object(watch,'read_current',side_effect=[data,None,data]) as read:
   monitor.tick(b,True,1,seed=AH);clock[0]=103;monitor.tick(b,True,1,seed=AH)
   clock[0]=104;monitor.tick(b,True,1,seed=AH);read.assert_called_once()
   clock[0]=105;monitor.tick(b,True,1,seed=AH);read.assert_called_once()
   fake.changed=True;monitor.tick(b,True,1,seed=AH)
   self.assertEqual(read.call_count,2);self.assertTrue(read.call_args.args[2])
   fake.changed=False;clock[0]=105.2;monitor.tick(b,True,1,seed=AH)
   clock[0]=105.5;monitor.tick(b,True,1,seed=AH)
   self.assertEqual(read.call_count,3);self.assertTrue(read.call_args.args[2])
  monitor.close()
