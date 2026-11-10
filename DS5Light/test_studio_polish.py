import unittest,tkinter as tk,copy
from tkinter import ttk
from unittest.mock import patch
import test_studio_settings as base
import test_studio_macro_flow as flow
from studio_button_names import NAMES
from pathlib import Path
from studio_dialogs import confirm_delete

def walk(w):
    for c in w.winfo_children():
        yield c;yield from walk(c)
def text(w):
    try:return str(w.cget('text'))
    except tk.TclError:return ''

class PolishTests(unittest.TestCase):
    setUp=base.NativeUITests.setUp
    tearDown=base.NativeUITests.tearDown
    editor=base.NativeUITests.editor
    def test_search_under_navigation_and_connection_warning(self):
        ui=self.editor();self.root.deiconify();self.root.update()
        self.assertIs(ui.search_entry.master,ui.nav[0].master)
        self.assertGreater(ui.search_entry.winfo_rooty(),ui.nav[-1].winfo_rooty())
        self.assertIn('브라우저에서 Studio 웹 설정',text(ui.web_warning));self.assertNotIn('꺼 주세요',text(ui.web_warning))
        self.assertEqual(text(ui.read_button),'새로 고침');self.assertEqual(text(ui.save_button),'현재 프로필에 저장')
    def test_list_has_no_filters_and_gold_add_button(self):
        ui=self.editor();ui.doc.macros={'0':flow.record(chord=1,out_btn=8,flags=2),'1':flow.record(chord=3,keys=[4])};ui.doc.macro_baseline=copy.deepcopy(ui.doc.macros);ui.select_category(4)
        buttons=[w for w in walk(ui.body) if isinstance(w,ttk.Button)]
        self.assertFalse(any(text(w) in ('전체','버튼 매핑','조건 매크로') for w in buttons))
        add=next(w for w in buttons if text(w)=='+ 매핑·매크로 추가');self.assertEqual(str(add.cget('style')),'Accent.TButton')
        self.assertEqual(sum(text(w)=='편집' for w in buttons),2)
        self.assertTrue(any('모든 프로필' in text(w) for w in walk(ui.body)))
    def test_calibration_text_is_left_anchored(self):
        ui=self.editor();ui.select_category(3)
        for w in walk(ui.body):
            if isinstance(w,tk.Label) and str(w.cget('justify'))=='left' and float(str(w.cget('wraplength')))>0:self.assertEqual(str(w.cget('anchor')),'w')
    def test_controller_vector_module_is_removed(self):
        self.assertFalse(Path('studio_button_icons.py').exists())
        self.assertEqual(len(NAMES),25)
    def test_inline_input_dropdown_and_right_aligned_notice(self):
        ui,m=flow.MacroFlowUITests.macro(self,flow.record(chord=1,keys=[4]))
        m.clear_buttons();m.button_choice.set('L3');m.choose_button();m.button_choice.set('잘못된 항목');m.choose_button()
        # Only localized dropdown choices modify bits; capture uses the same model.
        m.button_choice.set('트라이앵글');m.choose_button();self.assertTrue(m.buttons[14].get() and m.buttons[7].get())
        labels=[w for w in walk(m.footer) if isinstance(w,tk.Label)]
        self.assertTrue(any(str(w.cget('anchor'))=='e' and str(w.cget('justify'))=='right' for w in labels));m.close()
    def test_delete_confirmation_theme_and_cancel(self):
        ui=self.editor();self.root.deiconify();self.root.update();observed=[]
        def cancel_dialog():
            dialogs=[w for w in self.root.winfo_children() if isinstance(w,tk.Toplevel)]
            if not dialogs:self.root.after(20,cancel_dialog);return
            d=dialogs[0];observed.append(d.cget('bg'))
            next(w for w in walk(d) if isinstance(w,ttk.Button) and text(w)=='취소').invoke()
        self.root.after(20,cancel_dialog);self.assertFalse(confirm_delete(ui.parent));self.assertEqual(observed,['#151515'])
    def test_delete_only_stages_after_confirmation(self):
        ui=self.editor();r=flow.record(chord=1,keys=[4]);ui.doc.macros={'0':r[:]};ui.doc.macro_baseline={'0':r[:]}
        with patch('studio_dialogs.confirm_delete',return_value=False):ui.delete_macro(0)
        self.assertEqual(ui.doc.macros['0'],r)
        with patch('studio_dialogs.confirm_delete',return_value=True),patch.object(ui,'with_client') as hid:ui.delete_macro(0);hid.assert_not_called()
        self.assertEqual(ui.doc.macros['0'],[0]*35);self.assertTrue(ui.doc.dirty)

if __name__=='__main__':unittest.main()
