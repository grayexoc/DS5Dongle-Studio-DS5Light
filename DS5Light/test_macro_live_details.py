"""Live diagnostics use existing reports without claiming an output was executed."""
from types import SimpleNamespace
import unittest
from unittest.mock import Mock,patch
from studio_macro_tools import MacroTools,LiveMonitor


class LiveDetailsTests(unittest.TestCase):
    def display(self,**values):
        ui=MacroTools();ui.live_text=Mock()
        report=dict(input=dict(mask=0,lx=128,ly=128,rx=128,ry=128,l2=0,r2=0),received_at=9.8,reports=2,seen_mask=1,diag={})
        report.update(values)
        with patch('studio_macro_tools.time.monotonic',return_value=10):ui.show_live_result(report)
        return ui.live_text.set.call_args.args[0]

    def test_history_is_distinct_from_current_released_input(self):
        text=self.display()
        self.assertIn('PC로 보내는 패드 입력: 없음',text)
        self.assertNotIn('감지한 버튼: 없음',text)
        self.assertIn('수신 보고 2개',text)

    def test_old_snapshot_is_labelled_as_last_received(self):
        text=self.display(received_at=8)
        self.assertIn('마지막 수신 입력:',text);self.assertIn('2.0초 전',text)

    def test_keyboard_touch_and_diagnostic_age_use_existing_fields(self):
        text=self.display(diag=dict(keyboard=(4<<8)|1,touch_x=1500,touch_info=2),diag_at=9)
        self.assertIn('첫 키 A',text);self.assertIn('오른쪽',text);self.assertIn('1500',text)
        self.assertIn('진단 조회 1.0초 전',text)
        self.assertIn('펌웨어 출력 상태',text)

    def test_no_held_key_does_not_show_stale_key_code(self):
        self.assertNotIn('첫 키',self.display(diag={'keyboard':4<<8}))

    def test_pending_report_and_older_optional_fields_are_supported(self):
        text=self.display(input=None,received_at=None,diag={'keyboard':0})
        self.assertIn('입력 보고 대기 중',text);self.assertNotIn('최근 터치 클릭',text)

    def test_press_and_release_in_same_read_batch_are_retained_without_new_queries(self):
        press=[1]+[0]*63;press[8]=0x18;release=press[:];release[8]=8
        device=Mock();device.read.side_effect=[press,release,[]]
        monitor=LiveMonitor(b'test',diagnostics=False)
        monitor.stop=Mock();monitor.stop.wait.side_effect=[False,True];monitor.stop.is_set.return_value=False
        client=Mock()
        with patch('hid.device',return_value=device),patch('studio_macro_tools.SettingsClient',return_value=client),patch('studio_macro_tools.time.monotonic',return_value=10):monitor.run()
        result=monitor.results.get_nowait()
        self.assertEqual(result['reports'],2)
        self.assertEqual(result['input']['mask'],0)
        self.assertEqual(result['seen_mask'],1<<4)
        client.read_one.assert_not_called();device.close.assert_called_once()

    def test_diagnostic_observer_keeps_the_existing_eight_read_fields(self):
        device=Mock();device.read.return_value=[]
        monitor=LiveMonitor(b'test')
        monitor.stop=Mock();monitor.stop.wait.side_effect=[False,True];monitor.stop.is_set.return_value=False
        client=Mock();client.read_one.return_value=0
        lock=Mock();lock.acquire.return_value=True
        with patch('hid.device',return_value=device),patch('studio_macro_tools.SettingsClient',return_value=client),patch('studio_macro_tools._DEVICE_LOCK',lock),patch('studio_macro_tools.time.monotonic',return_value=10):monitor.run()
        self.assertEqual([call.args[0][0] for call in client.read_one.call_args_list],
                         [0x7b,0x7c,0x88,0x89,0x8a,0x8b,0x8c,0x8d])
        self.assertEqual(monitor.results.get_nowait()['diag_at'],10)
        lock.release.assert_called_once()

    def test_starting_a_new_check_discards_the_previous_display(self):
        ui=MacroTools();ui.app=SimpleNamespace();ui.path=b'test';ui.busy=False;ui.live_enabled=False
        ui.live_result={'seen_mask':255};ui.render_fields=Mock();ui.live_poll=Mock()
        with patch('studio_macro_tools.LiveMonitor') as monitor:ui.toggle_live();monitor.return_value.start.assert_called_once()
        self.assertIsNone(ui.live_result);self.assertTrue(ui.live_enabled)

    def test_monitor_start_failure_clears_active_state_and_reports_error(self):
        ui=MacroTools();ui.app=SimpleNamespace();ui.path=b'test';ui.busy=False;ui.live_enabled=False
        ui.render_fields=Mock();ui.update_state=Mock();ui.progress=Mock()
        with patch('studio_macro_tools.LiveMonitor') as monitor:
            monitor.return_value.start.side_effect=RuntimeError('thread start failed');ui.toggle_live()
            monitor.return_value.stop.set.assert_called_once()
        self.assertFalse(ui.live_enabled);self.assertIsNone(ui.live_job)
        self.assertIn('시작 실패',ui.progress.configure.call_args.kwargs['text'])


if __name__=='__main__':unittest.main()
