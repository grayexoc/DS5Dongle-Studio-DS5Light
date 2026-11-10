"""Macro reboot recovery: reads may retry; save/reset must never repeat."""
import copy,threading,unittest
from types import SimpleNamespace
from unittest.mock import Mock,patch
import studio_reconnect as recovery
import test_studio_settings as fixture
from test_studio_macro_flow import record

PROFILE=dict(index=0,name='Mix',edited=False)
ROW=dict(path=b'new',serial_number='ours',product_string='DualSense')
def fresh(macros=None):
    return dict(rows=[ROW],path=b'new',cfg=19,version='v1.42.0',unsupported=[],
                values=fixture.defaults(),profile=dict(PROFILE,auto_haptics_enable=1),
                macros=macros or {'0':record(chord=1,keys=[4])})

class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.clock=0.;self.cancelled=False;self.waits=[]
        def wait(delay):self.waits.append(delay);self.clock+=delay;return self.cancelled
        self.cancel=SimpleNamespace(wait=wait,is_set=lambda:self.cancelled)
    def test_reenumeration_matches_serial_and_reads_macros(self):
        client=Mock();client.profile.return_value=PROFILE;client.read_macros.return_value=fresh()['macros']
        with patch.object(recovery.time,'monotonic',lambda:self.clock),patch.object(recovery,'devices',side_effect=[[],[dict(path=b'other',serial_number='other')],[ROW]]),patch.object(recovery,'snapshot',return_value=fresh()) as snapshot,patch('hid.device',return_value=Mock()),patch.object(recovery,'SettingsClient',return_value=client):
            result=recovery.wait_for_macros(b'old','ours',self.cancel)
        self.assertEqual(result['path'],b'new');self.assertEqual(len(self.waits),3)
        snapshot.assert_called_once();self.assertEqual(snapshot.call_args.kwargs['deadline'],30);client.read_macros.assert_called_once()
        client.write_fields.assert_not_called();client.save_flash.assert_not_called();client.reconnect_usb.assert_not_called()
    def test_wrong_or_ambiguous_device_never_opened_and_wait_is_bounded(self):
        for rows in ([dict(path=b'other',serial_number='other')],[ROW,dict(ROW,path=b'duplicate')]):
            self.clock=0.
            with patch.object(recovery.time,'monotonic',lambda:self.clock),patch.object(recovery,'devices',return_value=rows),patch.object(recovery,'snapshot') as snapshot:
                with self.assertRaises(TimeoutError):recovery.wait_for_macros(b'old','ours',self.cancel,timeout=5)
                snapshot.assert_not_called()
            self.assertLessEqual(self.clock,5)
    def test_cancel_does_not_query(self):
        self.cancelled=True
        with patch.object(recovery,'devices') as query:
            with self.assertRaisesRegex(RuntimeError,'취소'):recovery.wait_for_macros(b'old','ours',self.cancel)
            query.assert_not_called()
    def test_changed_profile_cannot_be_used_for_refreshed_table(self):
        client=Mock();client.profile.return_value=dict(PROFILE,index=1);client.read_macros.return_value={}
        with patch.object(recovery.time,'monotonic',lambda:self.clock),patch.object(recovery,'devices',return_value=[ROW]),patch.object(recovery,'snapshot',return_value=fresh()),patch('hid.device',return_value=Mock()),patch.object(recovery,'SettingsClient',return_value=client):
            with self.assertRaises(TimeoutError):recovery.wait_for_macros(b'old','ours',self.cancel,timeout=3)

class RecoveryUITests(unittest.TestCase):
    setUp=fixture.NativeUITests.setUp
    tearDown=fixture.NativeUITests.tearDown
    editor=fixture.NativeUITests.editor
    def poll(self,e):
        if e.poll_id:
            e.parent.after_cancel(e.poll_id);e.poll_id=None
        e.poll()
    def prepare(self,pending=False):
        refresh=patch.object(self.ui,'refresh_devices');refresh.start();self.addCleanup(refresh.stop)
        e=self.editor();e.path=b'old';e.device_rows=[dict(ROW,path=b'old')];e.profile_stamp=PROFILE
        old={'0':record(chord=1,keys=[4],label='Old')};new={'0':record(chord=1,keys=[4],label='New')}
        e.doc.macros=copy.deepcopy(old if pending else new);e.doc.macro_baseline=copy.deepcopy(old);e.doc.macros_pending_flash=pending
        table=copy.deepcopy(old);c=Mock();c.profile.return_value=PROFILE
        c.read_fields.return_value=(dict(e.doc.baseline),[]);c.write_fields.side_effect=lambda changes,current:changes
        c.read_macros.side_effect=lambda:copy.deepcopy(table)
        c.write_macro.side_effect=lambda index,data:table.update({str(index):list(data)})
        c.save_slot.side_effect=lambda index,name:setattr(c.profile,'return_value',dict(index=index,name=name,edited=False))
        return e,c,new
    def transaction(self,e,c,result,persist=False,shared=False):
        operations=[]
        with patch.object(e,'stopped_task',side_effect=lambda kind,op:operations.append(op)):
            if shared:e.save_shared_macros()
            else:e.apply(persist)
        with patch.object(e,'with_client',side_effect=lambda op:op(c)),patch.object(recovery,'wait_for_macros',return_value=result) as refresh:
            answer=operations[0]()
        return answer,refresh
    def finish(self,e,kind,answer,error=None):
        e.results.put((kind,answer,error))
        while not e.results.empty():self.poll(e)
    def test_profile_apply_and_save_preserve_pending_shared_definition_edits(self):
        e,c,new=self.prepare();e.changed('auto_haptics_gain',100)
        answer,refresh=self.transaction(e,c,fresh(),False)
        c.write_macro.assert_not_called();c.commit_macros.assert_not_called();c.save_flash.assert_not_called()
        refresh.assert_not_called();self.finish(e,'apply',answer)
        self.assertEqual(e.doc.macros,new);self.assertTrue(e.doc.macro_changes);self.assertTrue(e.doc.unsaved)
        c.reset_mock();c.read_fields.return_value=(dict(e.doc.baseline),[]);c.profile.return_value=e.profile_stamp
        reloaded=fresh();reloaded['values'].update(e.doc.baseline)
        answer,refresh=self.transaction(e,c,reloaded,True)
        c.write_macro.assert_not_called();c.commit_macros.assert_not_called();c.save_flash.assert_called_once();c.save_slot.assert_called_once()
        refresh.assert_called_once();self.finish(e,'apply',answer)
        self.assertTrue(e.doc.macro_changes);self.assertEqual(e.doc.macros,new);self.assertFalse(e.doc.unsaved)
    def test_enabling_existing_macro_refreshes_after_interface_reconnect(self):
        e,c,_=self.prepare(pending=True);e.doc.macros_pending_flash=False
        e.doc.values['macro_disable']=0xfffffffe
        reloaded=fresh(e.doc.macros);reloaded['values']['macro_disable']=0xfffffffe
        answer,refresh=self.transaction(e,c,reloaded,False)
        refresh.assert_called_once();c.write_macro.assert_not_called()
        c.commit_macros.assert_not_called();c.save_flash.assert_not_called()
        self.assertTrue(answer['reconnect'])

    def test_uncertain_flash_save_is_not_repeated_or_reported_as_persistent_success(self):
        e,c,new=self.prepare();c.save_flash.side_effect=OSError('reply lost')
        answer,refresh=self.transaction(e,c,fresh(new),True)
        c.save_flash.assert_called_once();c.commit_macros.assert_not_called();c.save_slot.assert_called_once();c.reconnect_usb.assert_not_called()
        self.assertFalse(answer['saved']);self.assertTrue(answer['save_uncertain']);refresh.assert_called_once()
        self.finish(e,'apply',answer)
        self.assertTrue(e.uncertain);self.assertFalse(e.write_ready);self.assertFalse(e.doc.save_requested)
        self.assertTrue(e.doc.macro_changes)

    def test_uncertain_macro_commit_never_repeats_commit_or_sends_dependent_save(self):
        e,c,new=self.prepare();c.commit_macros.side_effect=TimeoutError('commit response lost')
        with self.assertRaises(TimeoutError):self.transaction(e,c,fresh(new),shared=True)
        c.commit_macros.assert_called_once();c.save_flash.assert_not_called();c.save_slot.assert_not_called();c.reconnect_usb.assert_not_called()
        self.finish(e,'shared_save',None,'commit response lost')
        self.assertTrue(e.uncertain);self.assertFalse(e.write_ready);self.assertTrue(e.doc.macro_changes)

    def test_usb_disappearance_after_save_does_not_repeat_writes(self):
        e,c,new=self.prepare();c.reconnect_usb.side_effect=OSError('USB reset')
        answer,refresh=self.transaction(e,c,fresh(new),shared=True)
        c.save_flash.assert_not_called();c.save_slot.assert_not_called();c.commit_macros.assert_called_once();c.reconnect_usb.assert_called_once()
        self.assertIn('reloaded',answer);refresh.assert_called_once()
    def test_recovery_failure_does_not_resume_or_discard_verified_records(self):
        e,c,new=self.prepare();operations=[]
        with patch.object(e,'stopped_task',side_effect=lambda kind,op:operations.append(op)):e.save_shared_macros()
        with patch.object(e,'with_client',side_effect=lambda op:op(c)),patch.object(recovery,'wait_for_macros',side_effect=TimeoutError('retry manually')):
            answer=operations[0]()
        e.resume=True;self.finish(e,'shared_save',answer)
        self.assertFalse(e.resume);self.assertFalse(e.write_ready);self.assertTrue(e.uncertain)
        self.assertEqual(e.doc.macros,new);self.assertIn('확인',e.progress.cget('text'))
        c.save_flash.assert_not_called();c.commit_macros.assert_called_once()
    def test_shared_reconnect_same_serial_keeps_local_profile_draft_writable(self):
        e,c,new=self.prepare();e.changed('auto_haptics_gain',100)
        answer,_=self.transaction(e,c,fresh(new),shared=True)
        self.finish(e,'shared_save',answer)
        self.assertEqual(e.doc.changes,{'auto_haptics_gain':100})
        self.assertTrue(e.write_ready);self.assertFalse(e.uncertain)
    def test_other_serial_recovery_cannot_unlock_local_profile_draft(self):
        e,c,new=self.prepare();e.changed('auto_haptics_gain',100)
        other=fresh(new);other['rows']=[dict(ROW,serial_number='other')]
        answer,_=self.transaction(e,c,other,shared=True)
        self.finish(e,'shared_save',answer)
        self.assertEqual(e.doc.changes,{'auto_haptics_gain':100});self.assertFalse(e.write_ready)

if __name__=='__main__':unittest.main()
