"""Actual Tk geometry callbacks; no device settings or audio are changed."""
import time,unittest,tkinter as tk
from types import SimpleNamespace
from unittest.mock import Mock,patch
import test_studio_settings as fixture
from studio_slots import Slot
from studio_settings_ui import GOLD


def walk(widget):
    for child in widget.winfo_children():
        yield child
        yield from walk(child)


class HeaderRecoveryTests(unittest.TestCase):
    setUp=fixture.NativeUITests.setUp
    tearDown=fixture.NativeUITests.tearDown
    editor=fixture.NativeUITests.editor

    def show(self,ui):
        errors=[];self.root.report_callback_exception=lambda *args:errors.append(args)
        self.root.deiconify();self.root.update_idletasks()
        ui.identity.set('Studio · v1.42.0 · Audio_Haptic_02')
        self.root.update_idletasks()
        return errors

    def wait(self,ui):
        deadline=time.monotonic()+3
        while ui.busy and time.monotonic()<deadline:
            self.root.update();time.sleep(.01)
        self.assertFalse(ui.busy)

    def test_header_dimensions_and_resize_have_no_callback_errors(self):
        ui=self.editor();errors=self.show(ui)
        for width in (860,1100,860):
            self.root.geometry(f'{width}x1000');self.root.update_idletasks()
            ui.fit_device_header();ui.update_state()
            self.assertEqual(ui.identity_label.winfo_pixels(ui.identity_label.cget('wraplength')),ui._header_wraplength)
            self.assertLessEqual(ui.identity_label.winfo_x()+ui.identity_label.winfo_width(),ui.device_choice.winfo_x())
        self.assertFalse(errors,errors)

    def test_current_slot_wrap_color_and_save_button_fit(self):
        ui=self.editor();errors=self.show(ui)
        ui.profile_stamp=dict(index=1,name='Audio_Haptic_02',edited=False)
        ui.slots=[Slot(0,'saved','Native'),Slot(1,'saved','Audio_Haptic_02')]
        ui.select_category(5);self.root.update()
        labels=[w for w in walk(ui.body) if isinstance(w,tk.Label) and str(w.cget('text'))=='02 · Audio_Haptic_02']
        self.assertEqual(len(labels),1);self.assertEqual(str(labels[0].cget('fg')),GOLD)
        self.assertGreater(labels[0].winfo_pixels(labels[0].cget('wraplength')),0)
        self.assertFalse(errors,errors)

    def test_slot_refresh_starts_and_finishes_without_stuck_busy(self):
        ui=self.editor();errors=self.show(ui);ui.select_category(5)
        fake=SimpleNamespace(slots=lambda:[Slot(0,'saved','Native')])
        with patch.object(ui,'with_client',side_effect=lambda op:op(fake)) as client:
            button=next(w for w in walk(ui.body) if 'text' in w.keys() and str(w.cget('text'))=='슬롯 목록 새로 고침')
            button.invoke();self.wait(ui)
            client.assert_called_once()
        self.assertEqual(ui.slots[0].name,'Native');self.assertFalse(errors,errors)
        self.assertEqual(ui.cancel_button.winfo_manager(),'')

    def test_read_preparation_failure_does_not_leave_a_phantom_job(self):
        ui=self.editor();operation=Mock()
        with patch.object(ui,'read_view_lock',side_effect=RuntimeError('simulated UI error')):
            with self.assertRaisesRegex(RuntimeError,'simulated UI error'):ui.task('slots',operation)
        self.assertFalse(ui.busy);self.assertFalse(ui.resume);operation.assert_not_called()
        self.assertEqual(ui.cancel_button.winfo_manager(),'')
        self.assertNotIn('disabled',ui.read_button.state())
        ui.task('slots',lambda:[]);self.wait(ui)

    def test_pre_stop_render_failure_does_not_stop_audio_or_latch_busy(self):
        ui=self.editor();self.ui.engine=SimpleNamespace()
        try:
            with patch.object(ui,'render_fields',side_effect=RuntimeError('simulated UI error')),patch.object(self.ui,'stop') as stop:
                with self.assertRaises(RuntimeError):ui.stopped_task('apply',lambda:None)
                stop.assert_not_called()
            self.assertFalse(ui.busy);self.assertFalse(ui.resume)
        finally:self.ui.engine=None


if __name__=='__main__':unittest.main()
