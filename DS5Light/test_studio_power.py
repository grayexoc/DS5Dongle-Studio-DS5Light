"""Power integration tests use fake HID only; never contact hardware."""
import unittest
from types import SimpleNamespace as NS
from unittest.mock import Mock,patch
from studio_power import power_command,StudioPower,PowerReply,exchange
from device_binding import DeviceIdentity

def reply(action=0,state=0,version=1,status=0,reason=0):
    return bytes([0x84,0x66,0x1b,status,action,version,state,reason,11])+bytes(55)

class Device:
    def __init__(self,answers):self.answers=list(answers);self.sent=[];self.fail=False
    def send_feature_report(self,data):
        self.sent.append(data)
        if self.fail:raise OSError('ambiguous write')
        return 64
    def get_feature_report(self,*args):return self.answers.pop(0) if self.answers else b''
    def open_path(self,path):pass
    def close(self):pass

class ProtocolTests(unittest.TestCase):
    def test_query_and_request_wire(self):
        for action in (0,1):
            d=Device([reply(action,state=action)])
            self.assertEqual(power_command(d,action,lambda _:None).state,action)
            self.assertEqual(len(d.sent),1);self.assertEqual(len(d.sent[0]),64)
            self.assertEqual(d.sent[0][:4],bytes([128,102,27,action]))
            if action:self.assertEqual(d.sent[0][4:6],b'SL')
    def test_stale_short_wrong_prefix_action_are_not_success(self):
        for raw in (b'',reply()[:8],b'\x84\x66\x0a'+bytes(61),reply(action=1)):
            with self.subTest(raw=raw[:9]):
                d=Device([raw]*12)
                with self.assertRaises(TimeoutError):power_command(d,0,lambda _:None)
                self.assertEqual(len(d.sent),1)
    def test_unknown_version_and_invalid_status_state_reason(self):
        for kwargs in ({'version':2},{'status':1},{'state':5},{'reason':4}):
            with self.subTest(kwargs=kwargs),self.assertRaises(ValueError):
                power_command(Device([reply(**kwargs)]),0,lambda _:None)
    def test_ambiguous_send_reads_ack_without_retry(self):
        d=Device([reply(1,1)]);d.fail=True
        self.assertEqual(power_command(d,1,lambda _:None).state,1)
        self.assertEqual(len(d.sent),1)
    def test_same_lock_preflight_then_single_request(self):
        import studio_power
        d=Device([reply(),reply(1,1)])
        with patch.dict('sys.modules',hid=NS(device=lambda:d)),patch.object(studio_power.time,'sleep'):
            # Default sleep is bound; replace protocol wrapper to keep this test fast.
            original=power_command
            with patch.object(studio_power,'power_command',side_effect=lambda dev,action:original(dev,action,lambda _:None)):
                self.assertEqual(exchange(b'path',1).state,1)
        self.assertEqual([p[3] for p in d.sent],[0,1])
    def test_preflight_rejects_unknown_firmware_without_power_request(self):
        import studio_power
        d=Device([reply(version=2)])
        with patch.dict('sys.modules',hid=NS(device=lambda:d)):
            with patch.object(studio_power,'power_command',side_effect=lambda dev,action:power_command(dev,action,lambda _:None)):
                with self.assertRaises(ValueError):exchange(b'path',1)
        self.assertEqual([p[3] for p in d.sent],[0])

class StateTests(unittest.TestCase):
    def setUp(self):
        self.identity=DeviceIdentity(b'p','serial')
        self.app=NS(studio=NS(busy=False,binding=NS(snapshot=lambda:self.identity),observed_profile={},discover=Mock(),
                              _show_disconnected=Mock()),
                    studio_settings=NS(busy=False,built=False,stop_live=Mock(),invalidate_slot_cache=Mock()),engine=None,
                    _closing=False,_close_requested=False,_stopping=False,status=NS(set=Mock()),
                    battery=NS(generation=0),brand_wordmark=NS(show_status=Mock()),render=Mock())
        self.power=StudioPower(self.app);self.app.studio_power=self.power
    def test_unsupported_no_write_and_duplicate_click_blocked(self):
        self.app.stop=Mock()
        with patch.object(self.power,'worker') as worker:
            self.power.click();self.app.stop.assert_not_called()
            self.assertEqual(worker.call_args.args[0],'click_probe')
        self.power.state='idle'
        self.power.supported=True;self.power.key=(b'p','serial')
        self.power.click();self.power.click()
        self.app.stop.assert_called_once();self.assertTrue(self.power.blocked)
        self.assertEqual(self.app.stop.call_args.kwargs['reason'],'intentional_sleep')
    def test_busy_setting_blocks_click(self):
        self.power.supported=True;self.power.key=(b'p','serial');self.app.stop=Mock()
        self.app.studio_settings.busy=True;self.power.click();self.app.stop.assert_not_called()
    def test_initial_query_failure_can_be_rechecked_while_audio_runs(self):
        self.app.engine=object();self.app.stop=Mock()
        with patch.object(self.power,'worker') as worker:
            self.power.click();self.assertEqual(worker.call_args.args[0],'click_probe')
        self.power.results.put(('click_probe',PowerReply(0,0,11),None))
        self.power.tick();self.app.stop.assert_called_once()
    def test_failed_click_query_never_stops_audio_or_sends_sleep(self):
        self.app.stop=Mock();self.power.state='checking';self.power.click_identity=self.identity
        self.power.results.put(('click_probe',None,'unsupported'))
        with patch.object(self.power,'worker') as worker:
            self.power.tick();worker.assert_not_called()
        self.app.stop.assert_not_called();self.assertFalse(self.power.blocked)
        self.assertIn('지원 펌웨어',self.app.status.set.call_args.args[0])
    def test_acknowledged_and_unknown_disconnect_are_distinct(self):
        for ack in (True,False):
            self.power.state='waiting';self.power.acknowledged=ack;self.power.busy=True
            self.power.results.put(('observe',(False,None),None))
            with patch.object(self.power,'worker'):self.power.tick()
            text=self.app.status.set.call_args.args[0]
            self.assertEqual('결과 미확인' in text,not ack)
            self.assertTrue(self.power.seen_absent)
    def test_failed_reply_releases_without_resending(self):
        self.power.state='waiting';self.power.busy=True
        self.power.results.put(('observe',(True,PowerReply(4,2,8)),None))
        with patch.object(self.power,'worker'):self.power.tick()
        self.assertFalse(self.power.blocked);self.assertIn('오디오 처리',self.app.status.set.call_args.args[0])
    def test_reappearance_refreshes_not_restarts_engine(self):
        self.power.state='sleeping';self.power.seen_absent=True;self.power.busy=True
        self.power.results.put(('observe',(True,PowerReply(0,0,11)),None))
        with patch.object(self.power,'worker'):self.power.tick()
        self.assertFalse(self.power.blocked);self.app.studio.discover.assert_called_once()
    def test_unsupported_probe_is_cached_per_identity(self):
        self.power.key=(b'p','serial');self.power.busy=True
        self.power.results.put(('probe',None,'unsupported'))
        with patch.object(self.power,'worker') as worker:
            self.power.tick();self.power.tick();worker.assert_not_called()

import test_studio_settings as fixture
class HiddenButtonTests(unittest.TestCase):
    setUp=fixture.NativeUITests.setUp
    tearDown=fixture.NativeUITests.tearDown
    def test_hitbox_is_blank_nonfocusable_with_no_hover_or_cursor(self):
        box=self.ui.power_hitbox
        self.assertEqual(box.cget('bg'),self.root.cget('bg'))
        self.assertEqual(str(box.cget('cursor')),'')
        self.assertEqual(int(box.cget('highlightthickness')),0)
        self.assertEqual(int(box.cget('bd')),0)
        self.assertEqual(str(box.cget('takefocus')),'0')
        self.assertFalse(box.winfo_children())
        self.assertFalse(box.bind('<Enter>'));self.assertFalse(box.bind('<Leave>'))
        placement=box.place_info()
        self.assertEqual(placement['anchor'],'sw');self.assertEqual(float(placement['rely']),1)
        self.assertEqual(int(placement['x']),0)
    def test_click_reaches_hitbox_handler(self):
        # Native hit-testing requires an on-screen point; the user's default
        # 1000px client height may extend below a scaled desktop.
        self.root.minsize(1,1)
        width=min(860,self.root.winfo_screenwidth()-80)
        height=min(860,self.root.winfo_screenheight()-120)
        self.root.geometry(f'{width}x{height}+0+0')
        self.root.deiconify();self.root.lift();self.root.update()
        self.assertTrue(self.ui.power_hitbox.winfo_viewable())
        box=self.ui.power_hitbox
        self.assertIs(self.root.winfo_containing(box.winfo_rootx()+12,box.winfo_rooty()+8),box)
        self.ui.studio_power.supported=False
        with patch.object(self.ui.studio_power,'worker'),patch.object(self.ui.studio.binding,'snapshot',return_value=DeviceIdentity(b'p','serial')):
            self.ui.power_hitbox.event_generate('<Button-1>',x=12,y=8)
        self.assertEqual(self.ui.studio_power.state,'checking')

if __name__=='__main__':unittest.main()
