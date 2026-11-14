import copy,unittest
from unittest.mock import patch
from studio_shift import POWER_OFF,set_shift_key,shift_key,validate_extension
from studio_macro_design import MacroDraft,OUTPUTS,conflicts
from studio_records import macro_records
from studio_settings_protocol import SettingsClient


class ShiftModelTests(unittest.TestCase):
    def test_shift_key_stages_in_free_record_and_keeps_others(self):
        records={str(i):[0]*35 for i in range(32)}
        records['0'][19]=65;before=copy.deepcopy(records)
        after,mask=set_shift_key(records,0xffffffff,19)
        self.assertEqual(records,before);self.assertEqual(after['0'],before['0'])
        self.assertEqual(shift_key(after)[0],1);self.assertEqual(mask,0xfffffffd)
        restored=macro_records(after);self.assertEqual(restored,after)
        changed,newmask=set_shift_key(after,mask,None)
        self.assertIsNone(shift_key(changed));self.assertEqual(newmask,0xffffffff)

    def test_no_free_record_and_invalid_key_do_not_mutate(self):
        rows={str(i):[1]*35 for i in range(32)};before=copy.deepcopy(rows)
        for key in (18,23,-1):
            with self.assertRaises(ValueError):set_shift_key(rows,0,key)
        self.assertEqual(rows,before)

    def test_numbered_profile_and_chime_preserve_existing_layout(self):
        row=[0]*35;row[0]=1;row[11]=27;row[12:17]=[7,6,5,4,3]
        draft=MacroDraft(row);state=dict(draft.initial,output_kind='profile',output=30,layer=True,chime=True)
        result=draft.build(state,strict=True)
        self.assertEqual(len(result),35);self.assertEqual(result[17],30)
        self.assertEqual(result[5]&96,96);self.assertEqual(result[12:17],row[12:17])
        self.assertEqual(MacroDraft(result).build(MacroDraft(result).initial),result)
        for output in (0,22,31):
            with self.assertRaises(ValueError):draft.build(dict(state,output=output),strict=True)

    def test_layers_do_not_report_conflicts_with_each_other(self):
        a=[0]*35;a[0]=1;a[17]=1;b=list(a);b[5]=32
        self.assertFalse(conflicts({'0':a,'1':b},0))
        b[5]=0;self.assertTrue(conflicts({'0':a,'1':b},0))

    def test_old_firmware_cannot_receive_extended_write(self):
        row=[0]*35;row[0]=1;row[17]=23
        client=SettingsClient(object())
        with patch.object(client,'command',side_effect=TimeoutError) as command:
            with self.assertRaisesRegex(RuntimeError,'v31'):client.write_macro(0,row)
            self.assertEqual(command.call_count,1);self.assertEqual(command.call_args.args[0],0x20)

    def test_legacy_write_needs_no_capability_read(self):
        row=[0]*35;row[0]=1;row[17]=1
        client=SettingsClient(object())
        with patch.object(client,'command',return_value=bytes([0x66,24,0,0])) as command:
            client.write_macro(0,row);self.assertEqual(command.call_count,1)
            self.assertEqual(command.call_args.args[0],24)

    def test_power_off_mapping_round_trip_and_capability_gate(self):
        row=[0]*35;row[0]=1
        draft=MacroDraft(row)
        record=draft.build(dict(draft.initial,output_kind='controller',output=POWER_OFF),strict=True)
        self.assertEqual(MacroDraft(macro_records({'0':record})['0']).initial['output_kind'],'controller')
        for bits in (0x0f,0x1f):
            client=SettingsClient(object())
            capability=bytes([0x66,0x20,0,1,0,0,0,0,0,bits])
            with patch.object(client,'command',side_effect=[capability,bytes([0x66,24,0])]) as command:
                if bits==0x0f:
                    with self.assertRaises(RuntimeError):client.write_macro(0,record)
                    self.assertEqual([c.args[0] for c in command.call_args_list],[0x20])
                else:
                    client.write_macro(0,record)
                    self.assertEqual([c.args[0] for c in command.call_args_list],[0x20,24])


import test_studio_settings as fixture
class ShiftUITests(unittest.TestCase):
    setUp=fixture.NativeUITests.setUp
    tearDown=fixture.NativeUITests.tearDown
    editor=fixture.NativeUITests.editor

    def prepare(self):
        ui=self.editor();ui.doc.macros={str(i):[0]*35 for i in range(32)}
        ui.doc.macro_baseline=copy.deepcopy(ui.doc.macros);ui.select_category(4);return ui

    def test_refresh_reloads_layer_records_without_opening_picker(self):
        from studio_button_names import NAMES
        from test_studio_reconnect import fresh
        ui=self.prepare();ui.entry_attempts={'fields','macros'}
        ui.entry_queries_enabled=True
        with patch.object(ui,'schedule_entry'),patch.object(self.ui,'refresh_devices'):
            ui.results.put(('read',fresh(),None));ui.poll()
        self.assertNotIn('macros',ui.entry_attempts)
        with patch.object(ui,'task') as task:
            ui.entry_step(ui.entry_generation)
            self.assertEqual(task.call_args.args[0],'macros')
        records={str(i):[0]*35 for i in range(32)}
        records,mask=set_shift_key(records,0xffffffff,19)
        row=[0]*35;row[0]=1;row[5]=32;row[17]=1;row[19:24]=b'Layer'
        records['1']=row;ui.macro_layer=True
        with patch.object(ui,'schedule_entry'):
            ui.results.put(('macros',records,None));ui.poll()
        self.assertEqual(ui.shift_key_label.cget('text'),NAMES[19])
        self.assertFalse(ui.shift_editor.winfo_manager())
        def labels(widget):
            for child in widget.winfo_children():
                if child.winfo_class()=='Label':yield child.cget('text')
                yield from labels(child)
        self.assertIn('Layer',list(labels(ui.body)))

    def test_inline_choice_cancel_stages_nothing_and_commit_requests_auto_save(self):
        from studio_button_names import NAMES
        ui=self.prepare();before=copy.deepcopy(ui.doc.macros)
        self.root.deiconify();self.root.update()
        with patch.object(ui,'with_client') as hid,patch.object(ui,'task') as task,patch.object(ui,'save_macro_edits') as save:
            ui.open_shift_picker()
            self.root.update()
            self.assertTrue(ui.shift_choice.expanded)
            ui.shift_choice.choose(ui.shift_choice.values.index(NAMES[19]))
            self.assertTrue(ui.shift_enabled.get())
            ui.cancel_shift_key();self.assertEqual(ui.doc.macros,before)
            ui.open_shift_picker();self.root.update();self.assertEqual(ui.shift_selection.get(),'없음')
            ui.shift_choice.choose(ui.shift_choice.values.index(NAMES[20]))
            ui.commit_shift_key()
            save.assert_called_once()
            self.assertEqual(int.from_bytes(bytes(shift_key(ui.doc.macros)[1][:4]),'little'),1<<20)
            ui.open_shift_picker();self.assertEqual(ui.shift_selection.get(),NAMES[20])
            hid.assert_not_called();task.assert_not_called()

    def test_profile_editor_preview_and_stage(self):
        from studio_macro_editor import MacroEditor
        ui=self.prepare();row=[0]*35;row[0]=1
        ui.path=b'test';ui.profile_stamp=dict(index=0,name='Test',edited=False)
        editor=MacroEditor(ui,0,initial=row)
        editor.output_kind.set(OUTPUTS['profile']);editor.output.set('프로필 8번')
        editor.chime.set(True);editor.layer.set(True);editor.refresh()
        self.assertEqual(editor.draft.build(editor.state())[17],30)
        with patch.object(ui,'task') as task,patch.object(ui,'with_client') as hid,patch.object(ui,'save_registered_macro') as save:
            editor.preview_chime();self.assertEqual(task.call_args.args[0],'chime_preview');hid.assert_not_called()
            editor.commit();hid.assert_not_called();save.assert_called_once()
        self.assertEqual(ui.doc.macros['0'][5]&96,96)

    def test_power_off_editor_stages_and_reopens_under_controller_outputs(self):
        from studio_macro_editor import MacroEditor
        ui=self.prepare();row=[0]*35;row[0]=1
        ui.path=b'test';ui.profile_stamp=dict(index=0,name='Test',edited=False)
        editor=MacroEditor(ui,0,initial=row)
        editor.output_kind.set(OUTPUTS['controller'])
        self.assertEqual(len(editor.output_kind_buttons),4)
        editor.output_control.toggle()
        for name in ('Create','Options','듀얼센스 전원'):
            index=editor.output_control.values.index(name)
            self.assertIsNotNone(editor.output_control.tiles[index].image)
        editor.output_control.choose(editor.output_control.values.index('듀얼센스 전원'))
        self.assertFalse(editor.output_record.winfo_manager())
        with patch.object(ui,'with_client') as hid,patch.object(ui,'save_registered_macro') as save:
            editor.commit()
            hid.assert_not_called();save.assert_called_once()
        self.assertEqual(ui.doc.macros['0'][17],POWER_OFF)
        editor=MacroEditor(ui,0)
        self.assertEqual(editor.output_kind.get(),OUTPUTS['controller'])
        self.assertEqual(editor.output.get(),'듀얼센스 전원')
        editor.close()

    def test_inline_choice_has_icons_and_creates_no_window(self):
        from controller_glyphs import ControllerChoice
        from studio_button_names import NAMES
        ui=self.prepare();self.root.deiconify();self.root.update()
        def windows(widget):
            import tkinter as tk
            return [child for child in widget.winfo_children() if isinstance(child,tk.Toplevel)]
        before=windows(self.root);ui.open_shift_picker();self.root.update()
        self.assertEqual(windows(self.root),before)
        self.assertIsInstance(ui.shift_choice,ControllerChoice)
        self.assertEqual(list(ui.shift_choice.values),['없음']+NAMES[:23])
        for name in ['L1','R1','L3','R3',NAMES[18],*NAMES[19:23]]:
            tile=ui.shift_choice.tiles[ui.shift_choice.values.index(name)]
            self.assertIsNotNone(tile.image)
        ui.open_shift_picker();self.assertFalse(ui.shift_editor.winfo_manager())

    def test_inline_choice_keeps_profile_disabled_and_can_clear_key(self):
        from studio_button_names import NAMES
        ui=self.prepare()
        ui.doc.macros,mask=set_shift_key(ui.doc.macros,0xffffffff,19)
        row=shift_key(ui.doc.macros);ui.doc.values['macro_disable']=mask|(1<<row[0])
        ui.open_shift_picker();self.assertFalse(ui.shift_enabled.get())
        with patch.object(ui,'save_macro_edits') as save:
            ui.commit_shift_key();self.assertTrue(ui.doc.values['macro_disable']&(1<<row[0]));save.assert_called_once()
            ui.open_shift_picker();ui.shift_selection.set('없음');ui.commit_shift_key()
            self.assertEqual(save.call_count,2)
        self.assertIsNone(shift_key(ui.doc.macros))

if __name__=='__main__':unittest.main()
