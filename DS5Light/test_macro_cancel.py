"""Cancel must restore the embedded list and discard only the edited draft."""
import copy,unittest,tkinter as tk
from tkinter import ttk
from unittest.mock import patch
import test_studio_settings as fixture
from test_studio_macro_flow import record

class MacroCancelTests(unittest.TestCase):
    setUp=fixture.NativeUITests.setUp
    tearDown=fixture.NativeUITests.tearDown
    def editor(self):
        e=fixture.NativeUITests.editor(self);e.doc.macros={str(i):[0]*35 for i in range(32)};e.doc.macro_baseline=copy.deepcopy(e.doc.macros)
        e.select_category(4);self.root.deiconify();self.root.update();return e
    def cancel(self,e):
        def walk(w):
            yield w
            for child in w.winfo_children():yield from walk(child)
        button=next(w for w in walk(e.macro_editor.footer) if isinstance(w,ttk.Button) and w.cget('text')=='취소')
        button.invoke();self.root.update_idletasks()
    def test_new_cancel_returns_list_and_restores_record_and_mask(self):
        e=self.editor();before=copy.deepcopy(e.doc.macros);mask=e.doc.values['macro_disable']
        with patch.object(e,'with_client') as send:
            e.new_macro();self.root.update_idletasks();self.assertTrue(e.editor_holder.winfo_ismapped());self.assertFalse(e.canvas.winfo_ismapped())
            self.cancel(e)
            self.assertTrue(e.canvas.winfo_ismapped());self.assertFalse(e.editor_holder.winfo_ismapped())
            self.assertEqual(e.doc.macros,before);self.assertEqual(e.doc.values['macro_disable'],mask);send.assert_not_called()
    def test_existing_cancel_keeps_record_and_returns_list(self):
        e=self.editor();e.doc.macros['0']=record(chord=1,keys=[4]);e.doc.macro_baseline=copy.deepcopy(e.doc.macros);e.render_fields()
        before=copy.deepcopy(e.doc.macros);e.edit_macro(0);e.macro_editor.name.set('Changed');self.cancel(e)
        self.assertTrue(e.canvas.winfo_ismapped());self.assertEqual(e.doc.macros,before)
        self.assertGreater(e.body.winfo_height(),20)
    def test_new_cancel_does_not_discard_other_settings(self):
        e=self.editor();e.changed('auto_haptics_gain',101);e.new_macro();self.cancel(e)
        self.assertEqual(e.doc.values['auto_haptics_gain'],101);self.assertEqual(e.doc.changes,{'auto_haptics_gain':101})

    def test_new_draft_stages_nothing_until_commit(self):
        e=self.editor();before=copy.deepcopy(e.doc.macros);mask=e.doc.values['macro_disable']
        e.path=b'test';e.profile_stamp=dict(index=0,name='Test',edited=False)
        with patch.object(e,'with_client') as send,patch.object(e,'save_registered_macro') as save:
            e.new_macro();editor=e.macro_editor;self.assertEqual(e.doc.macros,before);self.assertEqual(e.doc.values['macro_disable'],mask)
            editor.buttons[0].set(True);editor.keys[0].set('A');editor.go_step(1);editor.commit();self.root.update_idletasks()
            self.assertTrue(any(e.doc.macros['0']));self.assertEqual(e.doc.values['macro_disable'],mask);save.assert_called_once()
            self.assertTrue(e.canvas.winfo_ismapped());self.assertIsNone(e.macro_editor);send.assert_not_called()
    def test_repeated_add_cancel_leaves_no_staged_rows(self):
        e=self.editor();before=copy.deepcopy(e.doc.macros)
        for _ in range(4):
            e.new_macro();self.cancel(e);self.assertTrue(e.canvas.winfo_ismapped());self.assertFalse(e.editor_holder.winfo_ismapped())
        self.assertEqual(e.doc.macros,before);self.assertFalse(e.doc.dirty)
    def test_cancel_inline_keyboard_capture_restores_list(self):
        e=self.editor();e.new_macro();editor=e.macro_editor
        with patch.object(e,'with_client') as send:
            editor.start_capture('keys');self.cancel(e);self.assertIsNone(editor.capture);self.assertIsNone(editor.capture_job)
            self.assertTrue(e.canvas.winfo_ismapped());send.assert_not_called()

if __name__=='__main__':unittest.main()
