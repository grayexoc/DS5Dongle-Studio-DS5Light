"""Bounded stress checks without device writes; run under an external timeout."""
import gc
import threading
import time
import unittest
from unittest.mock import patch

import test_studio_settings as fixture
from studio_macro_editor import MacroEditor
from test_studio_macro_flow import record
from thread_start import start_thread


class StartupStress(unittest.TestCase):
    def test_concurrent_and_nested_starts(self):
        completed = []
        def parent():
            for _ in range(50):
                child = threading.Thread(target=lambda: completed.append(1), daemon=True)
                start_thread(child)
                child.join(2)
        workers = [threading.Thread(target=parent, daemon=True) for _ in range(8)]
        enabled = gc.isenabled()
        for worker in workers:
            start_thread(worker)
        for worker in workers:
            worker.join(10)
        self.assertFalse(any(worker.is_alive() for worker in workers))
        self.assertEqual(len(completed), 400)
        self.assertEqual(gc.isenabled(), enabled)


class UIStartupStress(unittest.TestCase):
    setUp = fixture.NativeUITests.setUp
    tearDown = fixture.NativeUITests.tearDown
    editor = fixture.NativeUITests.editor

    def test_rebuild_edit_cancel_then_start_real_worker(self):
        ui = self.editor()
        ui.doc.macros['0'] = record(chord=1, keys=[4])
        enabled = gc.isenabled()
        thresholds = gc.get_threshold()
        try:
            gc.set_threshold(30, 5, 5)
            with patch.object(self.ui, 'render'), patch('hid.device') as device:
                for index in range(30):
                    ui.category = index % 6
                    ui.render_fields()
                    ui.macro_editor = MacroEditor(ui, 0, embedded=True)
                    ui.macro_editor.close()
                    ui.task('stress_probe', lambda: 'finished')
                    answer = ui.results.get(timeout=3)
                    self.assertEqual(answer, ('stress_probe', 'finished', None))
                    ui.parent.after_cancel(ui.poll_id)
                    ui.poll_id = None
                    ui.busy = False
                    self.assertEqual(gc.isenabled(), enabled)
                device.assert_not_called()
        finally:
            gc.set_threshold(*thresholds)

    def test_close_cancels_worker_without_waiting_for_it(self):
        ui = self.editor()
        finished = threading.Event()
        def operation():
            ui.cancel.wait(3)
            finished.set()
        with patch.object(self.ui, 'render'), patch('hid.device') as device:
            ui.task('stress_probe', operation)
            started = time.monotonic()
            ui.close()
            self.assertLess(time.monotonic() - started, .5)
            self.assertTrue(finished.wait(1))
            device.assert_not_called()


if __name__ == '__main__':
    unittest.main()
