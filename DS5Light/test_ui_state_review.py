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
