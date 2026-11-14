import copy,tkinter as tk,unittest
from unittest.mock import patch
import test_studio_settings as fixture
from studio_records import macro_records
from studio_macro_design import MacroDraft,conflicts,category

def record(**kw):return macro_records([dict(index=0,**kw)])['0']

class MacroFlowModelTests(unittest.TestCase):
    def test_original_bytes_survive_unchanged_view(self):
        for r in [record(chord=1,keys=[224,4],flags=0x80,rel_order=0,label='Old'),record(gesture=160,keys=[26,7,22,4],flags=0x84,stick_thresh=48),record(gesture=128,keys=[9],flags=1)]:
            draft=MacroDraft(r);self.assertEqual(draft.build(draft.initial),r)
    def test_name_change_preserves_unused_bytes(self):
        r=record(chord=1,keys=[4],flags=0x80,rel_order=0);r[12:17]=[11,22,0,33,44]
        d=MacroDraft(r);view=dict(d.initial,name='Changed');out=d.build(view,strict=True)
        self.assertEqual(out[:19],r[:19]);self.assertNotEqual(out[19:],r[19:])
    def test_example_combo_to_r3_with_hold_and_hide(self):
        r=record(chord=1,keys=[4]);d=MacroDraft(r)
        s=dict(d.initial,chord=(1<<14)|(1<<7),condition='hold',hide=True,output_kind='controller',output=8)
        out=d.build(s,strict=True);self.assertEqual(out[5],6);self.assertEqual(out[17],8);self.assertEqual(int.from_bytes(bytes(out[:4]),'little'),(1<<14)|(1<<7))
    def test_double_and_long_modes_use_firmware_flags(self):
        d=MacroDraft(record(chord=1,keys=[4],flags=6))
        self.assertEqual(d.build(dict(d.initial,condition='double'))[5],16)
        self.assertEqual(d.build(dict(d.initial,condition='long',hold=90))[5],1)
    def test_disabled_overlaps_do_not_warn(self):
        rows={'0':record(chord=1,keys=[4]),'1':record(chord=3,keys=[5])}
        self.assertEqual(conflicts(rows),[]);self.assertIn('단독 입력',conflicts(rows,0xfffffffc)[0])
    def test_double_tap_notice_only_when_same_input_active(self):
        rows={'0':record(chord=1,keys=[4]),'1':record(chord=1,keys=[5],flags=16)}
        self.assertIn('250ms',conflicts(rows,0xfffffffc)[0]);rows['1'][:4]=bytes([2,0,0,0]);self.assertEqual(conflicts(rows,0xfffffffc),[])
    def test_tap_and_long_are_distinct_conditions(self):
        self.assertFalse(conflicts({'0':record(chord=1,keys=[4]),'1':record(chord=1,keys=[5],flags=1)},0xfffffffc))
    def test_categories_and_motion_exclusion(self):
        self.assertEqual(category(record(chord=1,out_btn=8,flags=2)),'버튼 매핑')
        self.assertEqual(category(record(chord=3,out_btn=8,flags=2)),'조건 매크로')
        r=[0]*35;r[4]=144
        self.assertFalse(conflicts({'0':r},0))
        with self.assertRaises(ValueError):MacroDraft(r)

class MacroFlowUITests(unittest.TestCase):
    setUp=fixture.NativeUITests.setUp
    tearDown=fixture.NativeUITests.tearDown
    editor=fixture.NativeUITests.editor
    def macro(self,data):
        ui=self.editor();ui.doc.macros={str(i):[0]*35 for i in range(32)};ui.doc.macros['0']=list(data);ui.doc.macro_baseline=copy.deepcopy(ui.doc.macros)
        ui.path=b'test';ui.profile_stamp=dict(index=0,name='Test',edited=False)
        from studio_macro_editor import MacroEditor
        ui.macro_editor=MacroEditor(ui,0);return ui,ui.macro_editor
    def test_three_steps_and_no_hid_while_editing(self):
        ui,e=self.macro(record(chord=1,keys=[4]))
        with patch.object(ui,'with_client') as hid,patch.object(ui,'task') as task:
            e.mode.set('빠르게 두 번 누르기');e.name.set('Test');e.refresh();hid.assert_not_called();task.assert_not_called()
        self.assertEqual(e.draft.build(e.state())[5],16)
        titles=[]
        def walk(w):
            for c in w.winfo_children():
                if isinstance(c,tk.Label):titles.append(c.cget('text'))
                walk(c)
        walk(e.body)
        for title in ('⌘ 실행 조건','▶ 실행 동작','동작 규칙'):self.assertIn(title,titles)
        e.close()
    def test_commit_saves_combo_but_defers_activation_until_verified(self):
        ui,e=self.macro(record(chord=1,keys=[4]))
        for v in e.buttons:v.set(False)
        e.buttons[14].set(True);e.buttons[7].set(True);e.mode.set('누르는 동안 유지');e.hide.set(True);e.output_kind.set('듀얼센스 버튼');e.output.set('R3')
        before=ui.doc.values['macro_disable']
        with patch.object(ui,'with_client') as hid,patch.object(ui,'save_registered_macro') as save:
            e.commit();e.commit();hid.assert_not_called();save.assert_called_once()
        raw=ui.doc.macros['0'];self.assertEqual(raw[5],6);self.assertEqual(raw[17],8);self.assertEqual(ui.doc.values['macro_disable'],before)
    def test_stick_and_swipe_constrain_available_behaviour(self):
        ui,e=self.macro(record(chord=1,keys=[4]))
        e.kind.set('스틱 방향');self.assertEqual(e.mode.get(),'누르는 동안 유지');self.assertEqual(e.output_kind.get(),'키보드');self.assertIn('disabled',e.mode_control.state())
        e.kind.set('터치패드 스와이프');self.assertEqual(e.mode.get(),'짧게 누르기');self.assertEqual(e.draft.build(e.state())[4],128);e.close()
    def test_ps_shortcut_only_appears_for_ps_and_stages_profile_change(self):
        ui,e=self.macro(record(chord=1,keys=[4]))
        ui.doc.values['ps_shortcut_enabled']=ui.doc.baseline['ps_shortcut_enabled']=0
        ui.select_category(0)
        self.assertNotIn('ps_shortcut_enabled',ui.field_views)
        self.assertEqual(e.ps_shortcut_row.winfo_manager(),'')
        e.buttons[16].set(True)
        self.assertEqual(e.ps_shortcut_row.winfo_manager(),'pack')
        with patch.object(ui,'with_client') as wire:
            e.ps_shortcut_control.invoke()
            wire.assert_not_called()
        self.assertEqual(ui.doc.changes['ps_shortcut_enabled'],1)
        ui.write_ready=False
        e.ps_shortcut.set(False);e.change_ps_shortcut()
        self.assertTrue(e.ps_shortcut.get())
        self.assertEqual(ui.doc.values['ps_shortcut_enabled'],1)
        e.buttons[16].set(False)
        self.assertEqual(e.ps_shortcut_row.winfo_manager(),'')
        e.close()
    def test_unchanged_save_preserves_existing_record(self):
        raw=record(chord=1,keys=[224,4],flags=0x80,rel_order=0);raw[12:17]=[9,8,0,6,5]
        ui,e=self.macro(raw)
        with patch.object(ui,'save_registered_macro'):e.commit()
        self.assertEqual(ui.doc.macros['0'],raw)

    def test_profile_changed_during_edit_cannot_save(self):
        ui,e=self.macro(record(chord=1,keys=[4]));ui.profile_stamp=dict(index=1,name='Other',edited=False)
        with patch.object(ui,'save_registered_macro') as save:e.commit();save.assert_not_called()
        self.assertFalse(e.closed);self.assertIn('프로필이 바뀌',e.feedback.get());e.close()

    def test_save_start_failure_keeps_record_and_shows_error(self):
        ui,e=self.macro(record(chord=1,keys=[4]));e.name.set('Changed')
        before=ui.doc.values['macro_disable']
        with patch.object(ui,'save_registered_macro',side_effect=RuntimeError('thread start failed')):e.commit()
        self.assertIn('저장 시작 실패',ui.progress.cget('text'))
        self.assertTrue(ui.doc.macro_changes);self.assertEqual(ui.doc.values['macro_disable'],before)
    def test_filter_and_warning_follow_activation(self):
        ui=self.editor();ui.doc.macros={'0':record(chord=1,out_btn=8,flags=2),'1':record(chord=3,keys=[4])};ui.doc.macro_baseline=copy.deepcopy(ui.doc.macros);ui.select_category(4)
        ui.toggle_macro(0,True);ui.toggle_macro(1,True);self.assertIn('단독 입력',ui.macro_warning.get())
        ui.toggle_macro(1,False);self.assertEqual(ui.macro_warning_label.winfo_manager(),'')
        ui.filter_macros('버튼 매핑');self.assertFalse(hasattr(ui,'macro_filter'))
    def test_editor_stays_inside_viewport_for_each_input_and_output(self):
        ui,e=self.macro(record(chord=1,keys=[4]));self.root.deiconify();self.root.update();e.dialog.deiconify();e.dialog.update()
        self.assertGreater(e.canvas.winfo_width(),200)
        for kind in ('버튼 입력','스틱 방향','터치패드 스와이프'):
            e.kind.set(kind);e.refresh();e.dialog.update_idletasks()
            self.assertLessEqual(e.body.winfo_reqwidth(),e.canvas.winfo_width()+1)
            self.assertLessEqual(e.dialog.winfo_height(),self.root.winfo_screenheight()-100)
        e.kind.set('버튼 입력')
        for output in ('컨트롤러 버튼','키보드','마우스'):
            e.output_kind.set(output);e.dialog.update_idletasks();self.assertLessEqual(e.body.winfo_reqwidth(),e.canvas.winfo_width()+1)
        e.close()

if __name__=='__main__':unittest.main()
