"""High-risk UI state regressions; device and audio writes are not performed."""
import tkinter as tk
import unittest
from types import SimpleNamespace
from unittest.mock import patch
import test_studio_settings as fixture
from localization import tr


class StateReviewTests(unittest.TestCase):
    setUp=fixture.NativeUITests.setUp
    tearDown=fixture.NativeUITests.tearDown
    editor=fixture.NativeUITests.editor

    def test_cancel_device_switch_restores_picker_and_preserves_draft(self):
        editor=self.editor();editor.path=b'A'
        editor.device_rows=[{'path':b'A'},{'path':b'B'}]
        editor.device_choice.configure(values=('Pico A','Pico B'))
        value=editor.doc.baseline['auto_haptics_gain']+1
        editor.doc.values['auto_haptics_gain']=value
        editor.device_choice.current(1)
        with patch('studio_settings_ui.messagebox.askyesno',return_value=False),patch.object(editor,'read') as read:
            editor.choose_device()
            self.assertEqual(editor.device_choice.current(),0)
            editor.choose_device()
            read.assert_not_called()
        self.assertEqual(editor.path,b'A')
        self.assertEqual(editor.doc.changes['auto_haptics_gain'],value)

    def test_start_without_process_skips_studio_check(self):
        app=self.ui
        app.scope.set('process');app.scope_changed();app.game.set('');app.game_map.clear()
        app.select_tab(1)
        with patch.object(app.studio,'check_before_start') as check:
            app.start()
            check.assert_not_called()
        self.assertEqual(app.selected_tab,0)
        self.assertIn('게임을 실행하고',app.status.get())

    def test_native_profile_skips_scan_and_restores_previous_overlay_layout(self):
        app=self.ui;overlay=app.global_capture_overlay
        app.scope.set('device');app.render()
        self.assertEqual(overlay.master.winfo_manager(),'grid')
        self.assertEqual(overlay.winfo_manager(),'place')
        self.assertEqual(overlay.label.cget('text'),'전역 캡쳐')
        app.scope.set('process');app.render()
        self.assertEqual(overlay.winfo_manager(),'')
        with patch('app.start_thread') as launch:
            app.studio.operation='discover'
            app._initial_process_refresh()
            launch.assert_not_called()
            app.studio.operation=None
            app.studio.auto_haptics_mode=0;app.render()
            app._initial_process_refresh();app.refresh_games()
            launch.assert_not_called()
            self.assertEqual(overlay.label.cget('text'),'네이티브 햅틱')
            self.assertIn('disabled',app.refresh_button.state())
            app.studio.auto_haptics_mode=1;app.render()
            self.assertIn('disabled',app.refresh_button.state())
            launch.assert_called_once()
            app.render();app.refresh_games()
            launch.assert_called_once()

    def test_audio_profile_or_process_scope_refreshes_once(self):
        app=self.ui
        app._initial_process_refresh_done=True
        app.studio.auto_haptics_mode=0;app.scope.set('process')
        with patch.object(app,'refresh_games') as refresh:
            app._refresh_processes_on_capture_change()
            refresh.assert_not_called()
            app.studio.auto_haptics_mode=1
            app._refresh_processes_on_capture_change()
            app._refresh_processes_on_capture_change()
            refresh.assert_called_once()
            app.scope.set('device');app._refresh_processes_on_capture_change()
            app.scope.set('process');app.scope_changed()
            self.assertEqual(refresh.call_count,2)
            app.studio.observed_profile=dict(index=2)
            app._refresh_processes_on_capture_change()
            app._refresh_processes_on_capture_change()
            self.assertEqual(refresh.call_count,3)
            app.studio.auto_haptics_mode=0
            app._refresh_processes_on_capture_change()
            self.assertEqual(refresh.call_count,3)

    def test_profile_switch_reports_separate_save_scopes(self):
        editor=self.editor()
        editor.doc.unsaved=True;editor.doc.macros_pending_flash=True
        with patch('studio_save_flow.profile_switch',return_value=None) as dialog:
            editor.request_profile_switch(lambda:self.fail('Cancelled switch continued'))
        self.assertEqual(dialog.call_args.kwargs,dict(profile=True,shared=True,profile_applied=True,shared_applied=True))

    def test_duplicate_process_hint_is_empty_and_owned_message_is_removed(self):
        app=self.ui;app.scope.set('process');app.desired_game='Game.exe'
        app.game.set('');app.game_map={};app.game_names={'one':'Game.exe','two':'game.exe'}
        app._process_hint_base=tr('듀얼센스 연결됨')
        app._process_hint_message='old selection hint';app.status.set('old selection hint')
        app._update_process_selection_status()
        self.assertEqual(app._process_selection_hint(),'')
        self.assertEqual(app.status.get(),tr('듀얼센스 연결됨'))
        self.assertIsNone(app._process_hint_message)

    def test_connection_state_is_independent_of_status_text(self):
        panel=self.ui.studio;panel.controller_connected=True
        self.ui.status.set(tr('연결된 듀얼센스가 없습니다.'))
        self.assertFalse(panel.connection_missing())
        panel.controller_connected=False;self.ui.status.set(tr('정지'))
        self.assertTrue(panel.connection_missing())
        panel._observe_profile(b'ours',dict(index=0,name='Audio',edited=False,auto_haptics_enable=1))
        self.assertFalse(panel.connection_missing())

    def test_battery_marker_only_with_ready_percentage(self):
        logo=self.ui.brand_wordmark
        for state,value,visible in [('ready',dict(percent=0,state=0),True),
                                    ('ready',dict(percent=40,state=0),True),
                                    ('ready',dict(percent=100,state=2),True),
                                    ('disconnected',None,False),('waiting',None,False),
                                    ('unavailable',None,False),('ready',None,False)]:
            logo.show_status(state,value)
            self.assertEqual(bool(logo.find_withtag('battery-full-marker')),visible)

    def test_option_redraw_keeps_scroll_and_category_change_resets(self):
        ui=self.editor();self.root.deiconify();self.root.update_idletasks()
        ui.select_category(3);self.root.update_idletasks();ui.canvas.yview_moveto(.35)
        position=ui.canvas.yview()[0];self.assertGreater(position,0)
        ui.render_fields();self.assertAlmostEqual(ui.canvas.yview()[0],position,delta=.02)
        ui.select_category(1);self.assertEqual(ui.canvas.yview()[0],0)

    def test_search_displays_source_category(self):
        ui=self.editor();ui.search.set('폴링율');ui.render_fields()
        def labels(widget):
            for child in widget.winfo_children():
                if isinstance(child,tk.Label):yield str(child.cget('text'))
                yield from labels(child)
        self.assertTrue(any(text.startswith('장치 › ') for text in labels(ui.body)))

    def test_battery_recovery_queries_once_and_defers_dirty_editor(self):
        ui=self.editor();panel=self.ui.studio
        panel.controller_connected=False
        monitor=SimpleNamespace(state='ready',value=dict(percent=40,state=0),
                                device=dict(path=b'ours',serial_number='ours'),generation=1,busy=False)
        ui.changed('auto_haptics_gain',101)
        with patch.object(panel,'discover') as discover:
            panel.recover_battery_connection(monitor);discover.assert_not_called()
            ui.doc.revert();panel.recover_battery_connection(monitor)
            discover.assert_called_once_with(refresh=True,target_device=monitor.device)
            panel.recover_battery_connection(monitor);self.assertEqual(discover.call_count,1)

    def test_cancel_while_waiting_for_audio_stop_never_starts_write(self):
        ui=self.editor();ui.changed('auto_haptics_gain',101)
        self.ui.engine=SimpleNamespace(capture_channels=2,mix_supported=True)
        callbacks=[]
        with patch.object(self.ui,'stop',side_effect=lambda on_complete:callbacks.append(on_complete)),patch.object(ui,'task') as task:
            ui.stopped_task('apply',lambda:None)
            self.assertTrue(ui.busy);ui.cancel_task()
            self.ui.engine=None;callbacks[0]()
            task.assert_not_called();self.assertFalse(ui.busy);self.assertFalse(ui.resume)
            self.assertEqual(ui.doc.changes,{'auto_haptics_gain':101})


if __name__=='__main__':unittest.main()
