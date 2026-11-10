"""UI lifecycle regressions: repeated rebuilds must release Tcl callbacks."""
import gc
import tkinter as tk
import unittest
from unittest.mock import patch
import test_studio_settings as fixture
from test_studio_macro_flow import record
from studio_macro_editor import MacroEditor
from ui_controls import widget_trace

class LifecycleTests(unittest.TestCase):
    setUp=fixture.NativeUITests.setUp
    tearDown=fixture.NativeUITests.tearDown
    editor=fixture.NativeUITests.editor

    def counts(self):
        self.root.update_idletasks();gc.collect()
        return (len(self.root.tk.call('info','commands')),
                len(self.root.tk.call('info','vars','PY_VAR*')))

    def test_category_rebuilds_do_not_accumulate_callbacks_or_variables(self):
        ui=self.editor();counts=[]
        for _ in range(4):
            for category in range(6):ui.category=category;ui.render_fields()
            counts.append(self.counts())
        self.assertEqual(counts,[counts[0]]*4)

    def test_closed_macro_editors_release_traces_and_help_icons(self):
        ui=self.editor();ui.doc.macros['0']=record(chord=1,keys=[4]);counts=[];tips=len(ui.tips)
        for _ in range(4):
            ui.macro_editor=MacroEditor(ui,0,embedded=True)
            ui.macro_editor.close()
            self.assertEqual(len(ui.tips),tips)
            counts.append(self.counts())
        self.assertEqual(counts,[counts[0]]*4)

    def test_widget_cleanup_keeps_unrelated_variable_trace(self):
        var=tk.StringVar(master=self.root);frame=tk.Frame(self.root);received=[];other=[]
        token=var.trace_add('write',lambda *_:other.append(var.get()))
        widget_trace(frame,var,lambda *_:received.append(var.get()))
        var.set('one');frame.destroy();var.set('two')
        self.assertEqual(received,['one']);self.assertEqual(other,['one','two'])
        var.trace_remove('write',token)

    def test_refresh_and_cancel_stay_separate_without_registering_more_callbacks(self):
        ui=self.editor();before=self.counts()
        with patch.object(ui,'read') as read,patch.object(ui.cancel,'set') as cancel:
            for busy in (False,True)*5:
                ui.busy=busy;ui.update_state();ui.read_button.invoke()
                if busy:
                    self.assertIn('disabled',ui.read_button.state())
                    self.assertEqual(ui.cancel_button.winfo_manager(),'grid')
                    ui.cancel_button.invoke()
                else:self.assertEqual(ui.cancel_button.winfo_manager(),'')
            self.assertEqual(read.call_count,5);self.assertEqual(cancel.call_count,5)
        ui.busy=False;ui.update_state();self.assertEqual(before,self.counts())

if __name__=='__main__':unittest.main()
