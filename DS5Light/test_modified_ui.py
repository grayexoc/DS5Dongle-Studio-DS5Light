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
from unittest.mock import Mock,patch

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
    def test_tab_strip_keyboard_selection_uses_existing_page_guard(self):
        tabs=self.ui.tabs
        self.assertEqual(int(tabs.cget('takefocus')),1)
        for key in ('Left','Right','Home','End'):self.assertTrue(tabs.bind(f'<{key}>'))
        self.assertEqual(tabs._select_from_keyboard(1),'break')
        self.assertEqual((self.ui.selected_tab,tabs.selected),(1,1))
        with patch.object(type(self.ui.studio_settings),'transfer_locked',True):
            tabs._select_from_keyboard(2)
        self.assertEqual((self.ui.selected_tab,tabs.selected),(1,1))

    def test_main_buttons_and_tab_keep_focus_without_inner_dots(self):
        app=self.ui
        style=ui.ttk.Style(self.root)
        for button in (app.refresh_button,app.game_save_button,app.load_button,
                       app.studio.apply,app.start_button,app.stop_button):
            self.assertNotIn('Button.focus',str(style.layout(button.cget('style'))))
        with patch.object(app.tabs,'focus_get',return_value=app.tabs):
            app.tabs.draw()
        bounds=app.tabs.find_withtag('tab-0')[0]
        self.assertEqual(app.tabs.itemcget(bounds,'dash'),'')
        self.assertGreater(float(app.tabs.itemcget(bounds,'width')),1)

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

    def wait_for_file_save(self):
        deadline=time.monotonic()+2
        while self.ui.file_save_busy and time.monotonic()<deadline:
            self.root.update();time.sleep(.01)
        self.assertFalse(self.ui.file_save_busy)

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

    def test_refresh_keeps_current_process_but_rejects_reused_pid(self):
        app=self.ui
        app.scope.set('process')
        app.desired_game='Game.exe'
        rows=[dict(name='Game.exe',pid=123,started=1.,cpu=3.),
              dict(name='Other.exe',pid=124,started=2.,cpu=4.)]
        app.render_games(rows)
        self.assertEqual(app._run_route()[1:3],(123,1.))
        app.game.set(next(key for key,pid in app.game_map.items() if pid==124))
        app._finish_game_refresh(rows,None,False)
        self.assertEqual(app._run_route()[1:3],(124,2.))
        app.render_games([rows[0],dict(rows[1],started=3.)])
        self.assertIsNone(app._run_route()[1])

    def test_settings_opens_device_diagnostics_without_duplicate_preview(self):
        with patch('app.open_diagnostics') as open_dialog:
            self.ui.device_diagnostics_button.invoke()
            open_dialog.assert_called_once_with(self.ui)
        self.assertFalse(hasattr(self.ui,'optimizer_preview_button'))

    def test_failed_automatic_studio_output_reports_status(self):
        app=self.ui
        app.scope.set('device')
        app.studio.observed_profile={'auto_haptics_enable':2,'ah_dsp_source':1}
        candidate=self.engine()
        candidate.start=Mock(side_effect=RuntimeError('exclusive denied'))
        with (
            patch('app.Engine',return_value=candidate),
            patch('output_debug.record'),
            patch.object(app.studio,'check_before_start',side_effect=lambda ready:ready()),
            patch.object(app.studio.binding,'output',return_value={'name':'Studio'}),
            patch('app.messagebox.showerror') as error,
        ):
            app.start()
        self.assertTrue(candidate.studio_live)
        self.assertIn('exclusive denied',app.status.get())
        error.assert_not_called()
        self.assertFalse(app.run_intent.requested)

    def test_start_confirmation_cancels_if_route_changed(self):
        app=self.ui
        app.run_intent.request(app._run_route())
        app.scope.set('process')
        with patch.object(app.studio,'native_mix_conflict') as next_check:
            app._start_after_profile_check()
        next_check.assert_not_called()
        self.assertFalse(app.run_intent.requested)

    def test_saving_settings_does_not_apply_or_render_controls(self):
        app=self.ui
        app.remember_last.set(True)
        original=app.controls
        app.gain.set(150)
        with patch.object(app,'render') as render:
            snapshot=app._preference_snapshot()
        render.assert_not_called()
        self.assertIs(app.controls,original)
        self.assertEqual(snapshot['controls']['gain'],1.5)
        app.update_controls()
        applied=app.controls
        app.update_controls()
        self.assertIs(app.controls,applied)

    def test_diagnostics_layout_runs_only_for_change_or_tab_entry(self):
        app=self.ui
        app._diagnostics_text=None
        with (patch.object(app,'_diagnostics_visible',return_value=True),
              patch.object(app.diagnostics_body,'fit_text') as fit,
              patch.object(app,'_schedule_diagnostic_spacing') as schedule):
            app._update_diagnostics()
            app._update_diagnostics()
            fit.assert_called_once()
            schedule.assert_not_called()
            app._update_diagnostics(True)
            schedule.assert_called_once()

    def test_failed_engine_restores_controls(self):
        self.ui.engine=self.engine(alive=False)
        self.ui.render(); self.ui.tick()
        self.assertIsNone(self.ui.engine)
        self.assertIn('simulated initialization failure',self.ui.status.get())
        self.assertNotIn('disabled',self.ui.start_button.state())

    def test_empty_startup_retries_keep_start_and_load_enabled(self):
        studio=self.ui.studio
        studio.initial_deadline=time.monotonic()+10
        with (patch('studio_panel.start_thread',side_effect=lambda thread:thread.run()),
              patch('studio_panel.devices',return_value=[]),
              patch.object(studio._cancel,'wait',return_value=False)):
            for _ in range(3):
                studio.task('startup',lambda:None)
                self.assertTrue(studio.busy)
                self.assertFalse(self.ui.start_button.instate(['disabled']))
                self.assertFalse(self.ui.load_button.instate(['disabled']))
                studio.poll()
                self.assertFalse(self.ui.start_button.instate(['disabled']))
            studio.task('startup',lambda:None)
            self.ui.start_button.invoke()
            self.assertTrue(self.ui.run_intent.requested)
            studio.poll()
            self.assertEqual(studio.operation,'check_start')
            self.assertTrue(self.ui.start_button.instate(['disabled']))
            self.assertFalse(self.ui.load_button.instate(['disabled']))
            studio.poll()
            self.assertFalse(self.ui.run_intent.requested)
            self.assertIsNone(self.ui.engine)
            self.assertFalse(self.ui.start_button.instate(['disabled']))

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
            end=time.monotonic()+2
            while self.ui._preferences_busy and time.monotonic()<end:self.root.update();time.sleep(.01)
        self.assertIn('read only',self.ui.notice.get())

    def test_preferences_write_coalesces_newer_edits_and_finishes_final_flush(self):
        app=self.ui;started=threading.Event();release=threading.Event();snapshots=[]
        app.remember_last.set(True);app.gain.set(100)
        def save(data,*,update_cache):
            self.assertFalse(update_cache)
            snapshots.append(data['controls']['gain'])
            if len(snapshots)==1:
                started.set();release.wait(2)
        finished=Mock()
        with patch.object(app.preference_store,'save',side_effect=save):
            try:
                app._save_preferences()
                self.assertTrue(started.wait(1))
                app.gain.set(110);app._save_preferences()
                app.gain.set(125);app.flush_preferences(on_complete=finished)
                self.root.update();finished.assert_not_called()
            finally:release.set()
            end=time.monotonic()+2
            while not finished.called and time.monotonic()<end:self.root.update();time.sleep(.01)
        finished.assert_called_once_with()
        self.assertEqual(snapshots,[1.,1.25]);self.assertEqual(app._saved_preferences['controls']['gain'],1.25)

    def test_status_details_open_full_clipped_message_by_key_or_click(self):
        app=self.ui;original='Device error: '+('settings read failed '*5)+'field 0x12 '+('wait for Pico '*6)
        with patch.object(app.status_label,'winfo_width',return_value=186),patch.object(ui.messagebox,'showinfo') as details:
            app.status.set(original)
            self.assertNotEqual(app._status_display.get(),original)
            self.assertEqual(str(app.status_label.cget('takefocus')),'1')
            self.assertTrue(app.status_label.bind('<Return>'));self.assertTrue(app.status_label.bind('<Button-1>'))
            self.assertEqual(app._show_status_details(),'break')
            self.assertEqual(details.call_args.args[1],original)
            app.status.set('Ready');self.assertIsNone(app._show_status_details())
            self.assertEqual(details.call_count,1)

    def test_old_slot_gain_is_explicitly_clamped_and_other_bounds_are_preserved(self):
        app=self.ui
        for requested,actual in ((0,.5),(.49,.5),(.50,.50),(2.,2.),(4.,3.)):
            with self.subTest(gain=requested):
                app.store.slots[0]=dict(name='Saved',game_exe='',scope='device',channels=0,input='',output='',
                                        controls=dict(asdict(app.controls),gain=requested))
                app._apply_slot(0)
                self.assertEqual(app.gain.get(),actual*100)
                self.assertEqual(app.controls.gain,actual)
                self.assertEqual(app.store.slots[0]['controls']['gain'],requested)
                self.assertEqual('지원 최솟값' in app.notice.get(),requested<.5)

    def test_footer_height_is_reserved_for_all_statuses(self):
        self.root.update_idletasks()
        height=self.ui.footer.winfo_height()
        self.assertGreaterEqual(height,self.ui.footer.content.winfo_reqheight())
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

    def test_manual_surround_includes_all_subchannels_and_hard_clips(self):
        app=self.ui
        app.scope.set('process')
        app.center.set(False);app.rear.set(False);app.lfe.set(False)
        app.limiter.set(next(label for label,value in ui.LIMITERS.items() if value=='soft'))
        for channels in (6,8,0):
            with self.subTest(channels=channels):
                app.channel.set(next(label for label,value in ui.CHANNELS.items() if value==channels))
                app.update_controls()
                self.assertEqual((app.controls.center,app.controls.rear,app.controls.lfe,
                                  app.controls.limiter),
                                 (True,True,True,'hard') if channels else (False,False,False,'soft'))

    def test_saved_profile_preserves_configuration_behind_forced_dsp_controls(self):
        from preferences import PreferenceStore
        from presets import PresetStore

        app = self.ui
        app.scope.set('process')
        app.channel.set(next(label for label, value in ui.CHANNELS.items() if value == 6))
        app.limiter.set(next(label for label, value in ui.LIMITERS.items() if value == 'soft'))
        app.rear.set(True)
        app.center.set(False)
        app.lfe.set(False)
        app.bg.set(False)
        app.transient.set(False)
        app.filter_on.set(True)
        app.update_controls()
        self.assertEqual(app.controls.limiter, 'hard')
        self.assertTrue(app.controls.center and app.controls.lfe)
        self.assertTrue(app.controls.background and app.controls.transient)

        app.slot_name.set('Surround profile')
        app.save_slot()
        self.wait_for_file_save()
        stored = PresetStore(app.store.path).slots[0]['controls']
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'preferences.json'
            PreferenceStore(path).save(app._preference_snapshot())
            self.assertEqual(PreferenceStore(path).load()['controls'], stored)
        self.assertTrue(stored['rear'])
        for flag in ('center', 'lfe', 'background', 'transient'):
            self.assertFalse(stored[flag])
        self.assertEqual(stored['limiter'], 'soft')

        app.load_slot()
        self.assertEqual(app.controls.limiter, 'hard')
        app.channel.set(next(label for label, value in ui.CHANNELS.items() if value == 0))
        app.update_controls()
        self.assertEqual(app.controls.limiter, 'soft')
        self.assertTrue(app.controls.rear)
        self.assertFalse(app.controls.center or app.controls.lfe)

    def test_section_headings_use_bold_compact_tracking(self):
        def headings(widget):
            found=[widget] if isinstance(widget,ui.SectionTitle) else []
            for child in widget.winfo_children(): found.extend(headings(child))
            return found
        titles=headings(self.ui.game_page)+headings(self.ui.device_page)
        self.assertEqual(len(titles),6)
        self.assertIn(ui.tr('오디오햅틱 필터'),[title.title for title in titles])
        for title in titles:
            self.assertEqual(title.font.actual('weight'),'bold'); self.assertLess(title.tracking,0)

    def test_filter_has_no_processing_mode_selector(self):
        self.assertFalse(hasattr(self.ui, 'processing_mode'))
        self.assertFalse(hasattr(self.ui, 'ai_switch'))

    def test_gain_slider_and_filter_are_independent(self):
        self.assertEqual(self.ui.gain.get(),100)
        slider=self.ui.gain_slider
        self.assertFalse(slider.enabled)
        profile = dict(index=0, name='Mix', edited=True, auto_haptics_enable=1, auto_mute_mix=True)
        self.ui._external_profile(dict(path=b'pico', profile=profile))
        self.assertTrue(slider.enabled)
        self.assertEqual((slider.minimum,slider.maximum,slider.reference),(100,300,100))
        labels=[slider.itemcget(item,'text') for item in slider.find_all() if slider.type(item)=='text']
        self.assertEqual(labels,['1x','2x','3x'])
        for key,value in (('Home',100),('Right',200),('End',300),('Right',300)):
            slider._key(SimpleNamespace(keysym=key))
            self.assertEqual(self.ui.gain.get(),value)
            self.assertEqual(self.ui.controls.gain,value/100)
            self.assertEqual(self.ui.gain_value.cget('text'),f'{value/100:g}x')
        self.root.update_idletasks()
        slider._set_from_x(slider.pad + .42 * max(1,slider.winfo_width() - 2 * slider.pad))
        self.assertEqual(self.ui.controls.gain,2.)
        self.ui.gain.set(125); self.ui.filter_on.set(False); self.ui.update_controls()
        self.assertEqual(self.ui.controls.gain,1.25)
        self.assertTrue(self.ui.controls.bypass); self.assertTrue(self.ui.gain_slider.enabled)
        self.ui._external_profile(dict(path=b'pico', profile=dict(profile, auto_mute_mix=False)))
        self.assertFalse(slider.enabled)
        self.assertEqual(self.ui.gain_value.cget('text'), '1x')
        self.assertEqual(self.ui.controls.gain, 1.25)

    def test_unchanged_channel_does_not_keep_scheduling_saves(self):
        self.ui.engine=self.engine(); self.ui.engine.capture_channels=6
        self.ui.scope.set('device'); self.ui.channel.set(next(key for key,value in ui.CHANNELS.items() if value==2))
        changes=[]
        self.ui.channel.trace_add('write',lambda *_:changes.append(True))
        self.ui.render(); self.ui.render()
        self.assertEqual(changes,[])

    def test_main_controls_fit_at_minimum_size(self):
        self.root.tk.call('tk', 'scaling', 120/72)
        width,height=self.root.minsize()
        self.root.geometry(f'{width}x{height}')
        self.root.deiconify()
        self.root.update()
        app=self.ui
        self.assertEqual(len(app.tabs.labels),3)
        gain_card=app.gain_frame.master
        filter_card=app.impact_slider.master.master.master.master
        self.assertEqual(app.scale.master.winfo_height(),app.impact_slider.master.winfo_height())
        self.assertEqual(tuple(point for point,_ in app.scale.ticks),(40,50))
        for slider in (app.scale,app.impact_slider):
            slider.draw()
            captions=[slider.bbox(item) for item in slider.find_all() if slider.type(item)=='text']
            self.assertEqual(len(captions),2)
            first,second=captions
            self.assertLessEqual(first[2],second[0])
            for left,top,right,bottom in captions:
                self.assertGreaterEqual(left,0)
                self.assertLessEqual(right,slider.winfo_width())
                self.assertLessEqual(bottom,slider.winfo_height())
        self.assertEqual(gain_card.winfo_rooty()+gain_card.winfo_height(),
                         filter_card.winfo_rooty()+filter_card.winfo_height())
        for scope in ('device','process'):
            app.scope.set(scope);app.render()
            self.root.update_idletasks()
            self.assertTrue(app.process_table.winfo_viewable())
            for widget in (app.start_button,app.stop_button,
                           app.channel_choice,app.gain_slider,app.impact_slider):
                self.assertTrue(widget.winfo_viewable(), (scope,str(widget),self.root.geometry()))
                self.assertGreater(widget.winfo_width(),1)
                self.assertLessEqual(widget.winfo_rooty()+widget.winfo_height(),
                                     self.root.winfo_rooty()+self.root.winfo_height())

    def test_device_selectors_are_on_settings_and_diagnostics_tab(self):
        app=self.ui
        app.open_connection()
        self.assertEqual(app.selected_tab,1)
        for key in ('source','output'):
            widget=app.conn_widgets[key]
            self.assertTrue(str(widget).startswith(str(app.device_page)+'.'))
        app.scope.set('process');app.render_connection()
        self.assertTrue(app.conn_widgets['source'].instate(['disabled']))
        self.assertTrue(app.conn_widgets['output'].instate(['readonly']))

    def test_basic_transport_starts_and_stops_both_capture_scopes(self):
        app=self.ui
        app.select_tab(0)
        app.source.set(ui.AUTO)
        app.destination.set(ui.AUTO)
        app.game.set('Game.exe')
        app.game_map['Game.exe']=123
        app.game_names['Game.exe']='Game.exe'
        for scope,pid in (('device',None),('process',123)):
            with self.subTest(scope=scope):
                app.scope.set(scope)
                app.studio.observed_profile={'auto_haptics_enable':2,'ah_dsp_source':int(pid is not None)}
                app.render()
                candidate=self.engine()
                candidate.start=Mock()
                with (
                    patch('app.Engine', return_value=candidate) as create,
                    patch('output_debug.record'),
                    patch.object(app.studio,'check_before_start',side_effect=lambda ready:ready()),
                    patch.object(app.studio.binding,'output',return_value={'name':'Studio'}),
                    patch.object(app.studio,'discover'),
                    patch.object(app._process_sampler,'is_running',return_value=True),
                ):
                    app.start_button.invoke()
                    candidate.start.assert_called_once()
                    self.assertEqual(create.call_args.kwargs['process_pid'],pid)
                    self.assertEqual(candidate.studio_live,pid is not None)
                    app.stop_button.invoke()
                    until=time.monotonic()+3
                    while app.engine and time.monotonic()<until:
                        self.root.update(); time.sleep(.01)
                self.assertIsNone(app.engine)
                self.assertEqual(app.selected_tab,0)

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
        self.ui.slot_name.set('Game'); self.ui.gain.set(200)
        started=threading.Event();release=threading.Event()
        from presets import replace_text
        def write(path,payload):
            started.set()
            if not release.wait(2):raise TimeoutError('test did not release writer')
            replace_text(path,payload)
        with patch('presets.replace_text',side_effect=write):
            try:
                self.ui.save_slot()
                self.assertTrue(started.wait(1))
                self.ui.slot.current(1);self.ui.slot_selected();self.root.update()
                self.assertIsNone(self.ui.store.bound_slot('Game.exe'))
                self.assertIn('disabled',self.ui.game_save_button.state())
            finally:release.set()
            self.wait_for_file_save()
        self.assertEqual(self.ui.slot.current(),1)
        self.assertEqual(self.ui.store.bound_slot('Game.exe'),0)
        self.assertEqual(self.ui.store.slots[0]['controls']['gain'],2.)
        self.ui.slot.current(0);self.ui.slot_selected()
        self.ui.auto_apply_game.set(False); self.ui.save_slot();self.wait_for_file_save()
        self.assertIsNone(self.ui.store.bound_slot('Game.exe'))


if __name__=='__main__': unittest.main(verbosity=2)
