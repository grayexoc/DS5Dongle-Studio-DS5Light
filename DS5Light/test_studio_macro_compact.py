import unittest,tkinter as tk,queue,threading
from tkinter import ttk
from unittest.mock import patch
from types import SimpleNamespace
import test_studio_macro_flow as flow
import test_studio_settings as base
from studio_help import reference_point
from studio_macro_design import KINDS

class Monitor:
    def __init__(self,*a,**kw):self.stop=threading.Event();self.results=queue.Queue()
    def start(self):pass

class CompactTests(unittest.TestCase):
    setUp=base.NativeUITests.setUp
    tearDown=base.NativeUITests.tearDown
    editor=base.NativeUITests.editor
    def macro(self,chord=1):return flow.MacroFlowUITests.macro(self,flow.record(chord=chord,keys=[4]))
    def test_all_button_layouts_omit_focus(self):
        ui,e=self.macro();style=ttk.Style(e.dialog)
        for name in ('TButton','Accent.TButton','Filter.TButton','StudioNav.TButton','Selected.StudioNav.TButton'):
            self.assertNotIn('Button.focus',str(style.layout(name)))
        e.close()
    def test_condition_is_required_even_for_direct_tab(self):
        ui,e=self.macro(0);e.go_step(1)
        self.assertEqual(e.step,0);self.assertIn('버튼을 먼저',e.feedback.get())
        e.buttons[0].set(True);e.go_step(1);self.assertEqual(e.step,1);self.assertEqual(len(e.step_hosts),2);e.close()
    def test_keyboard_capture_inline_local_and_release_order(self):
        ui,e=self.macro();before=e.dialog.winfo_children()
        with patch('tkinter.Toplevel',side_effect=AssertionError('extra window')),patch.object(ui,'with_client') as hid:
            e.start_capture('keys')
            for name in ('Control_L','a'):e.capture_down(SimpleNamespace(keysym=name))
            for name in ('a','Control_L'):e.capture_up(SimpleNamespace(keysym=name))
            e.keep_capture();hid.assert_not_called()
        self.assertEqual([v.get() for v in e.keys],['Ctrl','A','없음','없음'])
        self.assertIsNone(e.capture);self.assertEqual(before,e.dialog.winfo_children());e.close()
    def test_controller_input_and_output_capture_inline_cleanup(self):
        ui,e=self.macro();ui.path=b'test'
        with patch('studio_macro_capture.LiveMonitor',Monitor),patch('tkinter.Toplevel',side_effect=AssertionError('extra window')):
            e.start_capture('input');monitor=e.capture_monitor;monitor.results.put({'input':{'mask':(1<<14)|(1<<7)}});e.poll_capture();e.keep_capture()
            self.assertTrue(e.buttons[14].get() and e.buttons[7].get());self.assertTrue(monitor.stop.is_set())
            e.output_kind.set('컨트롤러 버튼');e.start_capture('output');monitor=e.capture_monitor;monitor.results.put({'input':{'mask':1<<15}});e.poll_capture();e.keep_capture()
            self.assertEqual(e.output.get(),'R3');self.assertTrue(monitor.stop.is_set())
            e.start_capture('input');monitor=e.capture_monitor;e.close();self.assertTrue(monitor.stop.is_set());self.assertIsNone(e.capture_job)
    def test_output_rejects_controller_chord(self):
        ui,e=self.macro();ui.path=b'test'
        with patch('studio_macro_capture.LiveMonitor',Monitor):
            e.start_capture('output');e.capture_monitor.results.put({'input':{'mask':3}});e.poll_capture()
            self.assertIsNone(e.capture['output']);self.assertIn('단일',e.capture_text.get())
        e.close()
    def test_direct_window_destruction_stops_capture(self):
        ui,e=self.macro();ui.path=b'test'
        with patch('studio_macro_capture.LiveMonitor',Monitor):
            e.start_capture('input');monitor=e.capture_monitor;e.dialog.destroy()
        self.assertTrue(e.closed);self.assertTrue(monitor.stop.is_set());self.assertIsNone(e.capture_job)

    def test_capture_start_failure_restores_editor_without_active_capture(self):
        ui,e=self.macro();ui.path=b'test'
        with patch('studio_macro_capture.LiveMonitor') as monitor:
            monitor.return_value.start.side_effect=RuntimeError('thread start failed');e.start_capture('input')
            monitor.return_value.stop.set.assert_called_once()
        self.assertIsNone(e.capture);self.assertIsNone(e.capture_monitor);self.assertIsNone(e.capture_job)
        self.assertIn('시작 실패',e.feedback.get());e.close()
    def test_icon_name_palette_keeps_combinations(self):
        from controller_glyphs import ControllerChoice
        ui,e=self.macro();self.assertIsInstance(e.button_dropdown,ControllerChoice)
        e.clear_buttons();e.button_choice.set('L3');e.choose_button();e.button_choice.set('트라이앵글');e.choose_button()
        self.assertTrue(e.buttons[14].get() and e.buttons[7].get());self.assertFalse(hasattr(e,'picker'));e.close()
    def test_short_macro_list_stays_at_top_after_scroll_and_rebuild(self):
        ui=self.editor();self.root.deiconify();self.root.update()
        ui.select_category(3);self.root.update();ui.canvas.yview_moveto(1)
        for _ in range(3):
            ui.select_category(4);self.root.update();ui.render_fields();self.root.update()
            self.assertEqual(ui.canvas.coords(ui.body_window),[0.,0.])
            self.assertAlmostEqual(ui.canvas.canvasy(0),0.,delta=1)
            self.assertAlmostEqual(ui.body.winfo_rooty()-ui.canvas.winfo_rooty(),0.,delta=1)
    def test_reference_and_slot_title(self):
        self.assertEqual(reference_point('haptics_gain'),(1.,'기본값'))
        ui=self.editor();ui.select_category(5)
        def texts(w):
            out=[]
            for child in w.winfo_children():
                try:out.append(child.cget('text'))
                except tk.TclError:pass
                out+=texts(child)
            return out
        self.assertIn('Studio 프로필 슬롯',texts(ui.body))
    def test_dialog_fits_content_and_aligns_to_owner_bottom_right(self):
        self.root.deiconify();self.root.geometry('1000x900+100+80');self.root.update()
        ui,e=self.macro();e.dialog.update();e.fit_dialog();e.dialog.update()
        width,height,x,y=e.last_geometry
        self.assertLessEqual(height,e.dialog.winfo_screenheight()-100)
        self.assertEqual(x,max(0,min(e.dialog.winfo_screenwidth()-width-8,self.root.winfo_rootx()+self.root.winfo_width()-width)))
        self.assertEqual(y,max(0,min(e.dialog.winfo_screenheight()-height-48,self.root.winfo_rooty()+self.root.winfo_height()-height)))
        e.kind.set('스틱 방향');e.dialog.update();self.assertGreaterEqual(e.last_geometry[1],420)
        self.assertAlmostEqual(e.canvas.canvasy(0),0,delta=1);e.close()

if __name__=='__main__':unittest.main()
