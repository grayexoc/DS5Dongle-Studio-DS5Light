"""Failure injection only; no real devices or user settings are accessed."""
import gc
import queue
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import Mock, patch

from preferences import PreferenceStore, default_preferences
from device_diagnostics_ui import DeviceDiagnosticsDialog
from studio_panel import StudioPanel
from studio_power import StudioPower


class BackupRecoveryTests(unittest.TestCase):
    def test_backup_failure_never_overwrites_original(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'ui.json'
            path.write_bytes(b'broken original')
            store = PreferenceStore(path)
            from os import replace
            def fail_backup_only(source, destination):
                if Path(source) == path:
                    raise PermissionError('locked')
                return replace(source, destination)
            with patch('preferences.os.replace', side_effect=fail_backup_only):
                store.load()
                with self.assertRaises(OSError):
                    store.save(default_preferences())
            self.assertEqual(path.read_bytes(), b'broken original')

    def test_save_retries_backup_after_lock_is_released(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'ui.json'
            path.write_bytes(b'broken original')
            store = PreferenceStore(path)
            with patch('preferences.os.replace', side_effect=PermissionError('locked')):
                store.load()
            store.save(default_preferences())
            self.assertIsNotNone(store.recovered_backup)
            self.assertEqual(store.recovered_backup.read_bytes(), b'broken original')
            self.assertEqual(PreferenceStore(path).load(), default_preferences())


class WorkerRecoveryTests(unittest.TestCase):
    def test_diagnostics_failure_is_polled_and_close_completes(self):
        dialog = DeviceDiagnosticsDialog.__new__(DeviceDiagnosticsDialog)
        dialog.app = NS(studio=NS(binding=Mock()), device_diagnostics=dialog)
        dialog.available = Mock(return_value=True)
        dialog.stop_input_monitor = Mock(return_value=True)
        dialog.busy = False
        dialog.cancel = threading.Event()
        dialog.buttons = []; dialog.confirm_buttons = []
        dialog.stop_button = Mock(); dialog.status = Mock()
        dialog.window = Mock(); dialog.results = queue.SimpleQueue()
        dialog.test_results = []; dialog.update_test_buttons = Mock()
        dialog.closing = True; dialog.last_test = None
        with patch('threading.Thread.start', side_effect=RuntimeError('start failed')):
            dialog.start('test', Mock())
        dialog.window.after.assert_called_once()
        dialog.poll()
        self.assertFalse(dialog.busy)
        self.assertIsNone(dialog.app.device_diagnostics)
        dialog.window.destroy.assert_called_once()
        self.assertIn('start failed', dialog.test_results[-1]['error'])

    def test_profile_failure_posts_result_and_schedules_poll(self):
        panel = StudioPanel.__new__(StudioPanel)
        panel.app = NS(_closing=False, engine=None, render=Mock(), root=Mock(),
                       studio_settings=NS(busy=False), studio_power=NS(blocked=False))
        panel.closed = False; panel.busy = False
        panel.render = Mock(); panel.results = queue.SimpleQueue(); panel.poll = Mock()
        operation = Mock()
        with patch('threading.Thread.start', side_effect=RuntimeError('start failed')):
            panel.task('discover', operation)
        self.assertEqual(panel.results.get_nowait(), ('discover', None, 'start failed'))
        panel.app.root.after.assert_called_once_with(80, panel.poll)
        operation.assert_not_called()

    def test_background_monitors_clear_busy_after_start_failure(self):
        from battery_status import BatteryMonitor
        from controller_presence import ControllerPresence, IdleControllerPresence
        from studio_profile_watch import ProfileWatch
        from device_binding import DeviceIdentity
        binding = Mock(); binding.snapshot.return_value = DeviceIdentity(b'pad', 'serial')
        battery = BatteryMonitor()
        presence = ControllerPresence()
        engine = NS(phase='error', errors=1, last_block_time=None, stop_event=threading.Event())
        idle = IdleControllerPresence(); idle.arm(); idle.next_check = 0
        watch = ProfileWatch(); watch.events = Mock(changed=True, healthy=False)
        with patch('threading.Thread.start', side_effect=RuntimeError('start failed')):
            battery.tick(preferred=b'pad'); battery.tick(paused=True, preferred=b'pad')
            presence.tick(engine, b'pad'); presence.tick(engine, b'pad', paused=True)
            idle.tick(binding, enabled=True); idle.tick(binding, enabled=True)
            watch.tick(binding, True, 1); watch.tick(binding, True, 1)
        for monitor in (battery, presence, idle, watch):
            self.assertFalse(monitor.busy)
            monitor.close()
        self.assertEqual(battery.state, 'unavailable')
        self.assertFalse(presence.disconnected)
        self.assertFalse(idle.absent)
        self.assertEqual(watch.failures, 1)

    def test_event_start_failure_rearms_retry(self):
        from studio_profile_events import ProfileEvents
        from device_binding import DeviceIdentity
        events = ProfileEvents()
        with patch('threading.Thread.start', side_effect=RuntimeError('start failed')):
            events.tick(DeviceIdentity(b'pad', 'serial'))
            events.tick(DeviceIdentity(b'pad', 'serial'))
        self.assertFalse(events.healthy)
        self.assertNotEqual(events.retry_at, float('inf'))
        events.close()

    def test_power_failure_clears_busy_without_a_command(self):
        app = NS(_closing=True, studio_settings=NS(built=False))
        power = StudioPower(app); operation = Mock()
        enabled = gc.isenabled()
        with patch('threading.Thread.start', side_effect=RuntimeError('start failed')):
            power.worker('probe', operation)
        power.tick()
        self.assertFalse(power.busy)
        self.assertFalse(power.supported)
        self.assertEqual(gc.isenabled(), enabled)
        operation.assert_not_called()


if __name__ == '__main__':
    unittest.main()
