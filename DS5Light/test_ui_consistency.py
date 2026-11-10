"""Actual Tk widgets and modal loops; all device operations are mocked."""
import copy,time,threading,unittest,tkinter as tk
from tkinter import ttk
from types import SimpleNamespace
from unittest.mock import patch
import test_studio_settings as fixtures
defaults=fixtures.defaults
import test_modified_ui as base_ui
from studio_slots import Slot
from device_binding import DeviceBinding
from controller_presence import IdleControllerPresence
import studio_dialogs as dialogs


def walk(widget):
    yield widget
    for child in widget.winfo_children():yield from walk(child)

class ConsistencyUITests(unittest.TestCase):
    setUp=fixtures.NativeUITests.setUp
    tearDown=fixtures.NativeUITests.tearDown
    editor=fixtures.NativeUITests.editor
    def test_initial_save_disabled_then_edit_and_saved_state(self):
        e=self.editor();self.assertIn('disabled',e.save_button.state())
        e.changed('auto_haptics_gain',101);self.assertNotIn('disabled',e.save_button.state())
        e.doc.load(e.doc.values);e.doc.unsaved=True;e.update_state();self.assertNotIn('disabled',e.save_button.state())
        e.doc.unsaved=False;e.doc.save_requested=True;e.update_state();self.assertIn('disabled',e.save_button.state())
        e.changed('auto_haptics_gain',102);self.assertNotIn('disabled',e.save_button.state())
    def test_band_controls_follow_split_without_widget_rebuild(self):
        e=self.editor();entry,slider,title=e.range_controls['ah_low_gain']
        self.assertEqual(str(entry.cget('state')),'disabled');self.assertFalse(slider.enabled)
        old_gain=e.doc.values['ah_low_gain'];identity=str(slider)
        with patch.object(e,'with_client') as send:
            e.vars['ah_xover_hz'].set('60');self.assertTrue(slider.enabled);self.assertEqual(str(entry.cget('state')),'normal')
            e.vars['ah_xover_hz'].set('0');self.assertFalse(slider.enabled);self.assertEqual(str(slider),identity)
            self.assertEqual(e.doc.values['ah_low_gain'],old_gain);send.assert_not_called()
    def test_off_to_audio_checks_speaker_and_manual_uncheck_warns(self):
        e=self.editor()
        with patch.object(e,'with_client') as send:
            for mode in (1,2):
                e.doc.load(dict(e.doc.baseline,auto_haptics_enable=0,disable_speaker=0))
                e.render_fields()
                e.select_value('auto_haptics_enable',mode);self.assertTrue(e.vars['disable_speaker'].get())
                e.vars['disable_speaker'].set(False);self.assertEqual(e.speaker_recommendations[0].winfo_manager(),'pack')
            send.assert_not_called()
    def test_footer_single_line_and_top_has_no_progress_widget(self):
        e=self.editor();self.root.deiconify();self.root.update()
        e.progress.configure(text='긴 작업 안내 '*40,kind='action');self.root.update_idletasks()
        self.assertEqual(int(e.notice_label.cget('height')),1);self.assertEqual(int(str(e.notice_label.cget('wraplength'))),0)
        self.assertLessEqual(e.notice_label.winfo_rootx()+e.notice_label.winfo_width(),e.revert_button.winfo_rootx())
        self.assertIn('…',e.notice_display.get());self.assertGreater(len(e.notice.get()),len(e.notice_display.get()))
        self.assertFalse(hasattr(e.progress,'grid_info'));self.assertEqual(int(e.read_button.grid_info()['column']),2)
    def test_message_kind_not_text_prefix_and_revert_clears_old_error(self):
        e=self.editor();e.progress.configure(text='설정 도움 안내',kind='action');self.assertEqual(e.notice.get(),'설정 도움 안내')
        e.progress.configure(text='이전 작업 오류',kind='error');e.revert();self.assertNotIn('이전 작업 오류',e.notice.get())
    def test_no_duplicate_settings_refresh_and_scoped_list_labels(self):
        e=self.editor();e.select_category(5)
        texts=[w.cget('text') for w in walk(e.body) if isinstance(w,ttk.Button)]
        self.assertNotIn('새로 고침',texts);self.assertIn('슬롯 목록 새로 고침',texts)
        e.select_category(4);texts=[w.cget('text') for w in walk(e.body) if isinstance(w,ttk.Button)]
        self.assertIn('매핑 목록 새로 고침',texts)
    def test_other_settings_edit_does_not_prompt_for_macro_refresh(self):
        e=self.editor();e.changed('auto_haptics_gain',101)
        with patch.object(e,'task') as task,patch.object(dialogs.messagebox,'askyesno') as confirm:
            e.read_macro_table();confirm.assert_not_called();self.assertEqual(task.call_args.args[0],'macros')
        self.assertEqual(e.doc.values['auto_haptics_gain'],101)
    def test_macro_refresh_reverts_only_confirmed_macro_mask(self):
        e=self.editor();e.changed('auto_haptics_gain',101);e.changed('macro_disable',0)
        with patch.object(e,'task'),patch.object(dialogs.messagebox,'askyesno',return_value=True):e.read_macro_table()
        e.results.put(('macros',{'0':[0]*35},None));e.poll()
        self.assertEqual(e.doc.values['auto_haptics_gain'],101);self.assertEqual(e.doc.values['macro_disable'],e.doc.baseline['macro_disable'])
    def test_missing_main_profile_load_performs_discovery_only(self):
        self.editor();s=self.ui.studio;s.slots=[Slot(0,'saved','Audio')];s.slot_paths=[b'A'];s.choice.configure(values=['Audio']);s.choice.current(0)
        self.ui.status.set('연결된 듀얼센스가 없습니다.')
        s.controller_connected=False
        with patch.object(s,'discover') as discover,patch('studio_panel.run_device') as send:
            s.render();self.assertEqual(s.apply.cget('style'),'Accent.TButton');s.activate()
            discover.assert_called_once_with(allow_running=True,refresh=True);send.assert_not_called()
    def test_verified_activation_schedules_current_settings_not_slot_catalog(self):
        e=self.editor();s=self.ui.studio;s.slots=[Slot(0,'saved','Audio')];s.slot_paths=[b'A'];s.paths=[b'A'];s.choice.configure(values=['Audio']);s.choice.current(0)
        profile=dict(index=0,name='Audio',edited=False,auto_haptics_enable=1)
        result=dict(path=b'A',old_path=b'A',profile=profile,verified=True,slot=s.slots[0],reconnect=False,deferred=False)
        with patch.object(e,'begin_entry') as begin:
            s.results.put(('activate',result,None));s.poll();begin.assert_called_once()
        self.assertIn('slots',e.entry_attempts);self.assertTrue(e.external_stale);self.assertFalse(e.write_ready)
    def test_reconnection_wait_stops_at_eight_seconds_and_resets_after_recovery(self):
        self.editor();engine=base_ui.ModifiedUITests.engine(self);engine.phase='waiting';engine.reconnecting=True;engine.blocks=1;self.ui.engine=engine
        with patch.object(self.ui.controller_presence,'tick'),patch.object(self.ui.battery,'tick'),patch.object(self.ui,'stop') as stop,patch('app.time.monotonic',return_value=100):
            self.ui.tick();self.assertEqual(self.ui._reconnect_wait_since,100)
            with patch('app.time.monotonic',return_value=107.9):self.ui.tick();stop.assert_not_called()
            with patch('app.time.monotonic',return_value=108):self.ui.tick();self.assertEqual(stop.call_args.kwargs['reason'],'reconnect_timeout')
            engine.phase='running';engine.reconnecting=False
            self.ui.tick();self.assertIsNone(self.ui._reconnect_wait_since)
        self.ui.engine=None
    def test_themed_confirm_alert_and_name_dialog_actual_modal_loops(self):
        self.editor();self.root.deiconify();self.root.update();observed=[]
        def inspect_and_close(expect_cancel=True,name=None):
            windows=[w for w in self.root.winfo_children() if isinstance(w,tk.Toplevel)]
            dialog=windows[-1]
            try:
                buttons=[w for w in walk(dialog) if isinstance(w,ttk.Button)]
                entries=[w for w in walk(dialog) if isinstance(w,ttk.Entry)]
                observed.append((dialog.cget('bg'),[b.cget('style') for b in buttons],entries[0].get() if entries else None))
                button=next(b for b in buttons if b.cget('text')==('저장' if name is not None else '취소' if expect_cancel else '확인'))
                button.invoke()
            finally:
                if dialog.winfo_exists():dialog.destroy()
        self.root.after(80,inspect_and_close);self.assertFalse(dialogs.confirm_bootloader(self.root))
        self.root.after(80,lambda:inspect_and_close(False));self.assertEqual(dialogs.messagebox.showerror('오류 확인','표시 시험',parent=self.root),'ok')
        self.root.after(80,lambda:inspect_and_close(name='Audio'));self.assertEqual(dialogs.profile_name(self.root,initial='Audio'),'Audio')
        self.root.after(80,lambda:inspect_and_close(name='Game'));self.assertEqual(dialogs.simpledialog.askstring('프리셋 저장','이름',initialvalue='Game',parent=self.root),'Game')
        self.assertEqual(len(observed),4)
        for bg,styles,value in observed:self.assertEqual(bg,'#151515');self.assertIn('Accent.Dialog.TButton',styles)
        self.assertNotIn('Button.focus',str(ttk.Style(self.root).layout('Dialog.TButton')))

class IdleScanTests(unittest.TestCase):
    def test_connected_idle_scan_is_throttled_and_stops_after_absence(self):
        class Immediate:
            def __init__(self,target,**kwargs):self.target=target
            def start(self):self.target()
        binding=DeviceBinding();binding.bind_hid(dict(path=b'A',serial_number='A'))
        monitor=IdleControllerPresence();clock=[100.]
        with patch('controller_presence.time.monotonic',side_effect=lambda:clock[0]),patch('controller_presence.threading.Thread',Immediate),patch('controller_presence.devices',return_value=[dict(path=b'A',serial_number='A')]) as scan:
            monitor.arm();monitor.tick(binding,enabled=True);scan.assert_not_called()
            clock[0]=108.;monitor.tick(binding,enabled=True);self.assertEqual(scan.call_count,1);self.assertTrue(monitor.tick(binding,enabled=True))
            clock[0]=115.9;monitor.tick(binding,enabled=True);self.assertEqual(scan.call_count,1)
            scan.return_value=[];clock[0]=116.;monitor.tick(binding,enabled=True);self.assertFalse(monitor.tick(binding,enabled=True));self.assertTrue(monitor.absent)
            clock[0]=200.;monitor.tick(binding,enabled=True);self.assertEqual(scan.call_count,2)
    def test_enumeration_error_is_not_disconnection(self):
        monitor=IdleControllerPresence();monitor.armed=True;monitor.generation=1
        monitor.results.put((1,None,None));monitor.tick(DeviceBinding(),enabled=True)
        self.assertTrue(monitor.armed);self.assertFalse(monitor.absent)

if __name__=='__main__':unittest.main()
