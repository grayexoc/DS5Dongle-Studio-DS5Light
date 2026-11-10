"""Regressions for target lifetime, asynchronous stopping and visible UI assets."""
import ctypes
import os
from pathlib import Path
import tempfile
import threading
import time
import tkinter as tk
from types import SimpleNamespace
import unittest
from dataclasses import asdict
from unittest.mock import patch

import app as ui
from process_audio import ProcessSampler


class TargetLifetimeTests(unittest.TestCase):
    def test_access_denied_is_unknown_not_exit(self):
        sampler=ProcessSampler.__new__(ProcessSampler)
        sampler.kernel=SimpleNamespace(OpenProcess=lambda *_:None)
        with patch('process_audio.ctypes.get_last_error',return_value=5):
            self.assertIsNone(sampler.is_running(123))
        with patch('process_audio.ctypes.get_last_error',return_value=87):
            self.assertIs(sampler.is_running(123),False)

    def test_real_process_identity_and_pid_reuse(self):
        sampler=ProcessSampler()
        started=sampler._read_times(os.getpid())[0]
        self.assertIs(sampler.is_running(os.getpid(),started),True)
        self.assertIs(sampler.is_running(os.getpid(),started-10),False)


class ModifiedUITests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=tk.Tk(); self.root.withdraw()
        args=['app.py','--preferences-test-path',str(Path(self.temp.name)/'prefs.json'),
              '--preset-test-path',str(Path(self.temp.name)/'presets.json'),
              '--ui-test-path',str(Path(self.temp.name)/'ui.json'),'--smoke-test','unused']
        with patch('app.devices',return_value=[]),patch('sys.argv',args):
            self.ui=ui.App(self.root)
        self.root.update_idletasks()
        for job in self.root.tk.call('after','info'): self.root.after_cancel(job)
        self.ui._preferences_ready=False

    def tearDown(self):
        self.ui._closing=True;self.ui.battery.close();self.ui.controller_presence.close();self.ui.studio_settings.close()
        self.ui.studio.close();self.ui.mute_shortcut.close()
        for job in self.root.tk.call('after','info'): self.root.after_cancel(job)
        self.root.update_idletasks()
        self.root.destroy(); self.temp.cleanup()

    def engine(self,alive=True,delay=0):
        result=SimpleNamespace(status='오류: simulated initialization failure',capture_channels=None,
                               phase='running' if alive else 'error',reconnecting=False,errors=0,last_block_time=time.monotonic(),
                               stop_event=threading.Event(),thread=SimpleNamespace(is_alive=lambda:alive))
        def stop():
            time.sleep(delay); result.thread=SimpleNamespace(is_alive=lambda:False); return True
        result.stop=stop
        return result

    def test_tree_images_are_in_visible_column_and_borders_are_fixed(self):
        self.ui._process_snapshot=[dict(name='Game.exe',pid=123,started=1.,cpu=3.),
                                   dict(name='Music.exe',pid=124,started=2.,cpu=1.)]
        self.ui.render_games()
        self.assertIn('tree',str(self.ui.process_table['show']))
        self.assertTrue(self.ui.process_table.item('123','image'))
        self.assertIn('Game.exe',self.ui.process_table.item('123','text'))
        self.assertEqual(self.ui.pages.cget('highlightcolor'),ui.BORDER)
        self.assertFalse(hasattr(self.ui,'normal_button'))
        self.assertTrue((Path(ui.__file__).parent/'assets/dslight.ico').is_file())
        self.assertFalse(hasattr(self.ui,'caption_icon'))
        before=dict(self.ui.process_dot_colors); self.ui.render_games()
        self.assertEqual(before,self.ui.process_dot_colors)

    def test_failed_engine_restores_controls(self):
        self.ui.engine=self.engine(alive=False)
        self.ui.render(); self.ui.tick()
        self.assertIsNone(self.ui.engine)
        self.assertIn('simulated initialization failure',self.ui.status.get())
        self.assertNotIn('disabled',self.ui.start_button.state())

    def test_stop_is_asynchronous_and_callbacks_run_once(self):
        self.ui.engine=self.engine(delay=.3)
        callbacks=[]
        start=time.perf_counter()
        self.ui.stop(on_complete=lambda:callbacks.append('closed'))
        self.assertLess(time.perf_counter()-start,.2)
        self.assertTrue(self.ui._stopping)
        self.ui.stop()
        until=time.monotonic()+3
        while self.ui.engine and time.monotonic()<until:
            self.root.update(); time.sleep(.01)
        self.assertIsNone(self.ui.engine)
        self.assertEqual(callbacks,['closed'])

    def test_unknown_target_does_not_stop_and_checks_are_throttled(self):
        self.ui.engine=self.engine()
        self.ui.active_process_pid=123; self.ui.active_process_name='Game'
        self.ui.next_process_check=0
        with patch.object(self.ui._process_sampler,'is_running',return_value=None) as check:
            self.ui.tick(); self.ui.tick()
        self.assertEqual(check.call_count,1)
        self.assertIsNotNone(self.ui.engine)
        self.assertFalse(self.ui._stopping)

    def test_confirmed_target_exit_requests_stop(self):
        self.ui.engine=self.engine()
        self.ui.active_process_pid=123; self.ui.active_process_name='Game'
        self.ui.next_process_check=0
        with patch.object(self.ui._process_sampler,'is_running',return_value=False): self.ui.tick()
        until=time.monotonic()+2
        while self.ui.engine and time.monotonic()<until:
            self.root.update(); time.sleep(.01)
        self.assertIsNone(self.ui.engine)
        self.assertIn('Game',self.ui.status.get())

    def test_failed_saves_leave_persistent_notice(self):
        self.ui._saved_preferences=None
        with patch.object(self.ui.preference_store,'save',side_effect=PermissionError('read only')):
            self.ui._save_preferences()
        self.assertIn('read only',self.ui.notice.get())

    def test_footer_height_is_reserved_for_all_statuses(self):
        self.root.update_idletasks()
        height=self.ui.footer.winfo_height()
        self.assertEqual(height,88)
        for status in ('',ui.tr('정지'),'Game · Running','Long backend status '*30):
            self.ui.status.set(status); self.root.update_idletasks()
            self.assertEqual(self.ui.footer.winfo_height(),height)
            self.assertEqual(self.ui.status_label.winfo_manager(),'grid')

    def test_diagnostics_skip_hidden_tabs_and_minimized_window(self):
        self.ui.engine=SimpleNamespace(stats=lambda: self.fail('Hidden diagnostics computed statistics'))
        self.ui.selected_tab=0; self.ui._update_diagnostics()
        self.ui.selected_tab=1
        with patch.object(self.root,'state',return_value='iconic'): self.ui._update_diagnostics()
        with patch.object(self.root,'state',return_value='normal'),patch.object(self.ui.device_page,'winfo_viewable',return_value=1):
            self.ui.engine=SimpleNamespace(stats=lambda:dict(status='Game ready',blocks=50))
            self.ui._update_diagnostics()
        self.assertIn('Game ready',self.ui.diagnostics_body._text)
        self.assertFalse(hasattr(self.ui,'open_diagnostics'))

    def test_scope_and_launch_circles_have_no_focus_rectangle(self):
        for control in self.ui.scope_buttons+self.ui.launch_checks:
            self.assertEqual(int(control.cget('highlightthickness')),0)
        self.ui.remember_last.set(False); self.ui.auto_start.set(False)
        self.ui.launch_checks[1].invoke()
        self.assertTrue(self.ui.auto_start.get()); self.assertTrue(self.ui.remember_last.get())

    def test_filter_selection_has_gold_border_without_dotted_focus(self):
        style=ui.ttk.Style(self.root)
        self.assertNotIn('Button.focus',str(style.layout('Filter.TButton')))
        for index,(_,strength) in enumerate(self.ui.style_buttons):
            self.ui.set_strength(strength)
            for other,(button,_) in enumerate(self.ui.style_buttons):
                self.assertEqual(button.cget('style'),'Selected.Filter.TButton' if other==index else 'Filter.TButton')
        self.assertEqual(style.lookup('Selected.Filter.TButton','bordercolor',('focus',)),ui.ACCENT)

    def test_section_headings_use_bold_compact_tracking(self):
        def headings(widget):
            found=[widget] if isinstance(widget,ui.SectionTitle) else []
            for child in widget.winfo_children(): found.extend(headings(child))
            return found
        titles=headings(self.ui.game_page)
        self.assertEqual(len(titles),3)
        self.assertIn(ui.tr('PC 억제 필터'),[title.title for title in titles])
        for title in titles:
            self.assertEqual(title.font.actual('weight'),'bold'); self.assertLess(title.tracking,0)

    def test_gain_slider_and_filter_are_independent(self):
        self.assertEqual(self.ui.gain.get(),100)
        self.assertEqual(self.ui.gain_slider.maximum,150)
        self.assertEqual(self.ui.gain_slider.reference,100)
        self.ui.gain.set(125); self.ui.filter_on.set(False); self.ui.update_controls()
        self.assertEqual(self.ui.controls.gain,1.25)
        self.assertTrue(self.ui.controls.bypass); self.assertTrue(self.ui.gain_slider.enabled)

    def test_unchanged_channel_does_not_keep_scheduling_saves(self):
        self.ui.engine=self.engine(); self.ui.engine.capture_channels=6
        self.ui.scope.set('device'); self.ui.channel.set(next(key for key,value in ui.CHANNELS.items() if value==6))
        changes=[]
        self.ui.channel.trace_add('write',lambda *_:changes.append(True))
        self.ui.render(); self.ui.render()
        self.assertEqual(changes,[])

    def test_selected_game_auto_loads_linked_preset_without_changing_output(self):
        item=dict(name='Game tuned',game_exe='Game.exe',scope='process',channels=2,input='old input',output='old output',
                  controls=asdict(ui.Controls(gain=1.25,strength=.8)))
        self.ui.store.save(0,item,bind_game='Game.exe',auto_apply=True)
        self.ui.scope.set('process'); self.ui.desired_game='Game.exe'
        destination=self.ui.destination.get()
        self.ui._process_snapshot=[dict(name='Game.exe',pid=123,started=1.,cpu=1.)]
        self.ui.render_games()
        self.assertEqual(self.ui.gain.get(),125); self.assertEqual(self.ui.strength.get(),80)
        self.assertEqual(self.ui.destination.get(),destination)
        self.assertTrue(self.ui.auto_apply_game.get())
        self.ui.gain.set(110); self.ui.update_controls(); self.ui.render_games()
        self.assertEqual(self.ui.gain.get(),110)  # List refresh must preserve unsaved edits.

    def test_game_link_is_committed_only_when_saved(self):
        self.ui.scope.set('process'); self.ui.desired_game='Game.exe'
        self.ui._process_snapshot=[dict(name='Game.exe',pid=123,started=1.,cpu=1.)]
        self.ui.render_games(); self.ui.auto_apply_game.set(True)
        self.assertIsNone(self.ui.store.bound_slot('Game.exe'))
        self.ui.slot_name.set('Game'); self.ui.gain.set(150); self.ui.save_slot()
        self.assertEqual(self.ui.store.bound_slot('Game.exe'),0)
        self.assertEqual(self.ui.store.slots[0]['controls']['gain'],1.5)
        self.ui.auto_apply_game.set(False); self.ui.save_slot()
        self.assertIsNone(self.ui.store.bound_slot('Game.exe'))


if __name__=='__main__': unittest.main(verbosity=2)
