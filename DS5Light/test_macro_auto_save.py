"""All shared-table edit entry points auto-save; failed saves remain exportable."""
import copy,json,tempfile,unittest,tkinter as tk
from pathlib import Path
from unittest.mock import patch
import test_studio_settings as fixture
from test_studio_macro_flow import record


class AutoSaveTests(unittest.TestCase):
    setUp=fixture.NativeUITests.setUp
    tearDown=fixture.NativeUITests.tearDown

    def editor(self):
        ui=fixture.NativeUITests.editor(self)
        ui.path=b'test';ui.profile_stamp=dict(index=0,name='Native',edited=False)
        ui.doc.macros={str(i):[0]*35 for i in range(32)}
        ui.doc.macros['0']=record(chord=1,keys=[4])
        ui.doc.macro_baseline=copy.deepcopy(ui.doc.macros)
        ui.doc.values['macro_disable']=0xfffffffe
        return ui

    def test_delete_saves_once_and_defers_profile_mask(self):
        ui=self.editor();mask=ui.doc.values['macro_disable']
        with patch('studio_dialogs.confirm_delete',return_value=True),patch.object(ui,'save_macro_edits') as save:
            ui.delete_macro(0)
        save.assert_called_once_with(ui.profile_stamp,mask=mask|1,record=(0,[0]*35))
        self.assertEqual(ui.doc.values['macro_disable'],mask)

    def test_profile_switch_while_delete_dialog_open_cannot_delete(self):
        ui=self.editor();before=copy.deepcopy(ui.doc.macros)
        def change(*args):ui.profile_stamp=dict(index=1,name='Other',edited=False);return True
        with patch('studio_dialogs.confirm_delete',side_effect=change),patch.object(ui,'save_macro_edits') as save:
            ui.delete_macro(0);save.assert_not_called()
        self.assertEqual(ui.doc.macros,before)

    def test_busy_uncertain_and_readonly_cannot_modify_table(self):
        ui=self.editor();before=copy.deepcopy(ui.doc.macros)
        for field,value in (('busy',True),('uncertain',True),('write_ready',False)):
            old=getattr(ui,field);setattr(ui,field,value)
            with patch('studio_dialogs.confirm_delete') as confirm,patch.object(ui,'save_macro_edits') as save:
                ui.delete_macro(0);confirm.assert_not_called();save.assert_not_called()
            setattr(ui,field,old)
        self.assertEqual(ui.doc.macros,before)

    def test_import_saves_once_keeps_profile_mask_and_motion(self):
        ui=self.editor();mask=ui.doc.values['macro_disable']
        motion=[0]*35;motion[4]=16;ui.doc.macros['2']=motion[:];ui.doc.macro_baseline['2']=motion[:]
        with tempfile.TemporaryDirectory() as tmp:
            name=Path(tmp)/'mapping.json'
            name.write_text(json.dumps({'macros':[dict(index=0,chord=2,keys=[5])]}),encoding='utf-8')
            with patch('studio_macro_tools.filedialog.askopenfilename',return_value=str(name)),patch('studio_macro_tools.messagebox.askyesno',return_value=True),patch.object(ui,'save_macro_edits') as save:
                ui.import_macros();save.assert_called_once_with(ui.profile_stamp)
        self.assertEqual(ui.doc.values['macro_disable'],mask)
        self.assertEqual(ui.doc.macros['2'],motion)
        self.assertEqual(ui.doc.macros['0'][0],2)

    def test_import_cancel_keeps_all_edits_and_does_not_save(self):
        ui=self.editor();before=copy.deepcopy(ui.doc.macros)
        with patch('studio_macro_tools.filedialog.askopenfilename',return_value=''),patch.object(ui,'save_macro_edits') as save:
            ui.import_macros();save.assert_not_called()
        self.assertEqual(ui.doc.macros,before)

    def test_unrelated_json_cannot_clear_mappings(self):
        ui=self.editor();before=copy.deepcopy(ui.doc.macros)
        with tempfile.TemporaryDirectory() as tmp:
            name=Path(tmp)/'settings.json';name.write_text('{"fields":{}}',encoding='utf-8')
            with patch('studio_macro_tools.filedialog.askopenfilename',return_value=str(name)),patch('studio_macro_tools.messagebox.showerror') as error,patch.object(ui,'save_macro_edits') as save:
                ui.import_macros();error.assert_called_once();save.assert_not_called()
        self.assertEqual(ui.doc.macros,before)

    def test_manual_save_removed_and_unsaved_export_survives_error(self):
        ui=self.editor();ui.doc.macros['0'][0]=2;ui.loaded=False;ui.write_ready=False;ui.uncertain=True
        ui.select_category(4)
        def buttons(widget):
            for child in widget.winfo_children():
                try:yield child.cget('text')
                except tk.TclError:pass
                yield from buttons(child)
        captions=list(buttons(ui.body))
        self.assertNotIn('Pico 매핑·매크로 저장',captions)
        self.assertIn('미저장 매핑 내보내기',captions)

    def test_export_failure_reports_error_without_discarding_edits(self):
        ui=self.editor();before=copy.deepcopy(ui.doc.macros)
        with patch('studio_macro_tools.filedialog.asksaveasfilename',return_value='blocked.json'),patch('studio_macro_tools.Path.write_text',side_effect=OSError('access denied')):
            ui.export_macros()
        self.assertIn('내보내기 실패',ui.progress.cget('text'));self.assertEqual(ui.doc.macros,before)

    def test_auto_save_note_is_single_line_and_profile_heading_removed(self):
        ui=self.editor();ui.select_category(4)
        def labels(widget):
            for child in widget.winfo_children():
                if isinstance(child,tk.Label):yield child
                yield from labels(child)
        widgets=list(labels(ui.body));captions=[w.cget('text') for w in widgets]
        first=next(w for w in widgets if w.cget('text')=='등록·편집·삭제·가져오기·시프트키 변경 시 자동 저장합니다.')
        self.assertEqual(int(str(first.cget('wraplength'))),0)
        self.assertNotIn('\n',first.cget('text'))
        self.assertNotIn('현재 프로필에서 사용',captions)


if __name__=='__main__':unittest.main()
