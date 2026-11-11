import gc,threading,unittest
from unittest.mock import Mock,patch
from thread_start import start_thread

class ThreadStartTests(unittest.TestCase):
 def test_bootstrap_cannot_trigger_automatic_gc(self):
  enabled=gc.isenabled();gc.enable();seen=[]
  try:
   worker=threading.Thread(target=lambda:None)
   original=worker._started.set
   def signal():
    seen.append(gc.isenabled());original()
   worker._started.set=signal
   start_thread(worker);worker.join(1)
   self.assertEqual(seen,[False]);self.assertTrue(gc.isenabled())
  finally:
   if not enabled:gc.disable()
 def test_start_failure_restores_gc(self):
  enabled=gc.isenabled();gc.enable()
  try:
   with self.assertRaises(RuntimeError):start_thread(Mock(start=Mock(side_effect=RuntimeError('start failed'))))
   self.assertTrue(gc.isenabled())
  finally:
   if not enabled:gc.disable()
 def test_disabled_gc_is_preserved(self):
  enabled=gc.isenabled();gc.disable()
  try:
   start_thread(Mock());self.assertFalse(gc.isenabled())
  finally:
   if enabled:gc.enable()
