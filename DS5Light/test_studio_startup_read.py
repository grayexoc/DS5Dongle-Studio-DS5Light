"""Launch-time read regression. Simulated replies/clocks, no actual HID I/O."""
import time,unittest,struct
from types import SimpleNamespace as NS
from unittest.mock import patch,Mock
import test_studio_settings as fixture
from studio_fields import FIELDS
from studio_scope import EDITABLE,LIGHTBAR_FIELDS,OPTIONAL_FIELDS
from studio_settings_protocol import SettingsClient,encode
from studio_snapshot import snapshot

class ReadTests(unittest.TestCase):
    def test_negative_optional_probe_returns_once_without_waiting_for_success_echo(self):
        d=Mock();d.send_feature_report.return_value=64
        d.get_feature_report.return_value=b'\x81\x66\x0c\x01\x00'+bytes(59)
        sleeps=[];c=SettingsClient(d,sleep=sleeps.append)
        self.assertEqual(c.read_lightbar(),{})
        self.assertEqual(sleeps,[.06]);d.send_feature_report.assert_called_once()
    def test_one_unsupported_field_does_not_disable_later_bulk_groups(self):
        fields=[f for k,f in EDITABLE.items() if k not in OPTIONAL_FIELDS][:27]
        bad=fields[3][0]
        class Device(fixture.Device):
            def send_feature_report(self,p):
                if p[2]==12 and bad in p[4:4+p[3]]:
                    self.sent.append(p);body=bytearray([0x66,12,1,0])
                    for fid in p[4:4+p[3]]:
                        if fid==bad:break
                        field=next(f for f in FIELDS.values() if f[0]==fid)
                        data=encode(field,self.values[field[1]])
                        body.extend([fid,len(data)]);body.extend(data);body[3]+=1
                    self.reply=(b'\x81'+body).ljust(64,b'\0');return 64
                return super().send_feature_report(p)
        d=Device();c=SettingsClient(d,sleep=lambda _:None);c.bulk=True
        values,missing=c.read_fields(fields)
        self.assertEqual(len(values),len(fields));self.assertFalse(missing)
        self.assertEqual(sum(p[2]==12 for p in d.sent),3)
        self.assertEqual(sum(p[2]==4 for p in d.sent),9)
    def test_enumeration_and_lock_wait_do_not_consume_active_read_budget(self):
        import studio_snapshot as module
        clock=[0.];calls=[0]
        def now():return clock[0]
        def acquire(**kw):
            clock[0]+=.1;calls[0]+=1;return calls[0]>=20
        lock=NS(acquire=acquire,release=Mock())
        def rows():clock[0]+=2.;return [dict(path=b'fake')]
        class Client:
            def __init__(self,*args,**kw):self.deadline=None
            def profile(self):return dict(index=0,name='Current',edited=False)
            def read_fields(self):
                clock[0]+=3.;self.check_cancel();return {'auto_haptics_enable':1},[]
            def standby_mode(self):return 0
            def check_cancel(self):
                if clock[0]>=self.deadline:raise RuntimeError('read timeout')
        with patch.object(module.time,'monotonic',now),patch.object(module,'devices',side_effect=rows),patch.object(module,'_DEVICE_LOCK',lock),patch.object(module,'SettingsClient',Client),patch.object(module,'identity_fields',return_value=('v1.42.0',19)),patch('hid.device',return_value=Mock()):
            result=snapshot(b'fake')
        self.assertEqual(result['cfg'],19);lock.release.assert_called_once()

class EntryTests(unittest.TestCase):
    setUp=fixture.NativeUITests.setUp
    tearDown=fixture.NativeUITests.tearDown
    editor=fixture.NativeUITests.editor
    def finish(self,ui):
        end=time.monotonic()+3
        while ui.busy and time.monotonic()<end:self.root.update();time.sleep(.005)
        self.assertFalse(ui.busy)
    def test_failure_stops_auto_followups_until_explicit_retry(self):
        ui=self.editor();ui.entry_queries_enabled=True
        def fail():raise RuntimeError('simulated query timeout')
        ui.task('entry_read',fail);self.finish(ui)
        self.assertTrue(ui.entry_failed);self.assertIsNone(ui.entry_job)
        with patch.object(ui,'task') as task:
            ui.schedule_entry();ui.entry_step(ui.entry_generation);self.root.update_idletasks()
            task.assert_not_called()
        ui.task('read',lambda:dict(choose=True,rows=[]));self.finish(ui)
        self.assertFalse(ui.entry_failed)
    def test_missing_optional_fields_are_not_treated_as_unread_on_next_entry(self):
        ui=self.editor();ui.entry_queries_enabled=True;ui.category=0
        ui.unsupported_fields=set(LIGHTBAR_FIELDS)
        for key in LIGHTBAR_FIELDS:ui.doc.values.pop(key);ui.doc.baseline.pop(key)
        with patch.object(ui,'task') as task:
            ui.begin_entry();self.root.update_idletasks();task.assert_not_called()
    def test_open_settings_cancels_pending_startup_slot_sweep(self):
        ui=self.editor();callback=Mock()
        self.ui.studio.startup_id=self.root.after(1,callback)
        ui.open();self.root.update();callback.assert_not_called()
        self.assertIsNone(self.ui.studio.startup_id)

if __name__=='__main__':unittest.main()
