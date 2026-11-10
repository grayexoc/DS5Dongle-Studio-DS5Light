"""Recent local editing changes. Native Tk widgets, no actual HID writes."""
import unittest,tkinter as tk
from tkinter import ttk
from unittest.mock import patch,Mock
import test_studio_settings as fixture
from studio_lightbar import rgb_palette
from studio_help import help_text

def walk(parent):
    for child in parent.winfo_children():
        yield child;yield from walk(child)

def palette_entries(dialog):
    entries=[w for w in walk(dialog) if isinstance(w,ttk.Entry)]
    return next(w for w in entries if str(w.cget('width'))=='10'),[w for w in entries if str(w.cget('width'))=='4']

def set_entry(widget,value):widget.setvar(str(widget.cget('textvariable')),str(value))

class RecentUITests(unittest.TestCase):
    setUp=fixture.NativeUITests.setUp
    tearDown=fixture.NativeUITests.tearDown
    editor=fixture.NativeUITests.editor
    def palette(self,callback,initial=0x123456):
        errors=[];self.root.report_callback_exception=lambda *args:errors.append(args)
        with patch('studio_lightbar._show',side_effect=callback):result=rgb_palette(self.root,initial)
        self.assertFalse(errors,errors)
        return result
    def test_hex_forms_synchronise_rgb_and_preview(self):
        for text,expected in (('#3366cc',0x3366cc),('3366CC',0x3366cc),('0x3366CC',0x3366cc),('#000000',0),('FFFFFF',0xffffff)):
            with self.subTest(text=text):
                def edit(dialog,owner,accept):
                    field,channels=palette_entries(dialog);set_entry(field,text)
                    self.assertEqual([int(w.get()) for w in channels],[(expected>>s)&255 for s in (16,8,0)])
                    self.assertEqual(field.get(),f'#{expected:06X}')
                    self.assertTrue(any(isinstance(w,tk.Label) and str(w.cget('bg')).upper()==f'#{expected:06X}' for w in walk(dialog)))
                    accept.invoke()
                self.assertEqual(self.palette(edit),expected)
    def test_invalid_hex_blocks_confirm_then_recovers(self):
        for text in ('','#12','#GGGGGG','1234567','0x12345'):
            with self.subTest(text=text):
                def edit(dialog,owner,accept):
                    field,channels=palette_entries(dialog);set_entry(field,text);accept.invoke()
                    self.assertTrue(dialog.winfo_exists())
                    self.assertEqual([int(w.get()) for w in channels],[18,52,86])
                    set_entry(field,'#010203');accept.invoke()
                self.assertEqual(self.palette(edit),0x010203)
    def test_rgb_entry_updates_hex_after_incomplete_hex(self):
        def edit(dialog,owner,accept):
            field,channels=palette_entries(dialog);set_entry(field,'#1')
            for w,value in zip(channels,(51,102,204)):set_entry(w,value)
            self.assertEqual(field.get(),'#3366CC');accept.invoke()
        self.assertEqual(self.palette(edit),0x3366cc)
    def test_invalid_rgb_is_blocked_and_valid_hex_repairs_it(self):
        def edit(dialog,owner,accept):
            field,channels=palette_entries(dialog);set_entry(channels[0],256);accept.invoke()
            self.assertTrue(dialog.winfo_exists())
            set_entry(field,'000000');accept.invoke()
        self.assertEqual(self.palette(edit),0)
    def test_hex_cancel_does_not_edit_document_or_send(self):
        ui=self.editor();before=dict(ui.doc.values)
        def cancel(dialog,owner,accept):
            field,_=palette_entries(dialog);set_entry(field,'#abcdef');dialog.destroy()
        with patch.object(ui,'with_client') as wire,patch('studio_lightbar._show',side_effect=cancel):
            ui.choose_lightbar_colour();wire.assert_not_called()
        self.assertEqual(ui.doc.values,before)
    def test_speaker_children_grouped_once_and_disabled_when_parent_on(self):
        ui=self.editor();ui.select_value('auto_haptics_enable',2)
        parent=ui.field_views['disable_speaker'][0]
        mix=ui.field_views['auto_mute_mix'];replace=ui.field_views['auto_mute_replace']
        # The detail group uses one row frame per field, below the speaker group.
        groups=[group for group in ui._option_groups
                if {'auto_mute_mix','auto_mute_replace'} <= {key for key,_ in group[1]}]
        self.assertEqual(len(groups),1)
        self.assertIs(mix[0].master.master,groups[0][4])
        self.assertIs(replace[0].master.master,groups[0][4])
        self.assertIs(groups[0][4].master,parent.master.master.master)
        for key,title in (('auto_mute_mix','Mix 모드 스피커 음소거'),('auto_mute_replace','Replace 모드 스피커 음소거')):
            self.assertFalse(ui.field_views[key][1][0].enabled)
            self.assertEqual(sum(isinstance(w,tk.Label) and w.cget('text')==title for w in walk(ui.body)),1)
        self.assertIn('단자',help_text('disable_speaker'))
        self.assertIn('헤드셋',help_text('disable_speaker'))
    def test_mode_transitions_manual_override_and_child_values_preserved(self):
        ui=self.editor();saved={k:ui.doc.values[k] for k in ('auto_mute_mix','auto_mute_replace')}
        with patch.object(ui,'with_client') as wire:
            ui.select_value('auto_haptics_enable',2);self.assertEqual(ui.doc.values['disable_speaker'],1)
            ui.vars['disable_speaker'].set(False)
            self.assertFalse(ui.field_views['auto_mute_mix'][1][0].enabled)
            self.assertTrue(ui.field_views['auto_mute_replace'][1][0].enabled)
            ui.select_value('auto_haptics_enable',2);self.assertEqual(ui.doc.values['disable_speaker'],0)
            ui.select_value('auto_haptics_enable',1);self.assertEqual(ui.doc.values['disable_speaker'],0) # Preserve explicit override on mode roundtrip.
            ui.select_value('auto_haptics_enable',0);self.assertEqual(ui.doc.values['disable_speaker'],0)
            ui.vars['disable_speaker'].set(True);ui.refresh_read_values()
            self.assertEqual(ui.doc.values['disable_speaker'],1);wire.assert_not_called()
        self.assertEqual({k:ui.doc.values[k] for k in saved},saved)
    def test_mode_off_stages_pair_only_and_read_sync_preserves_manual_state(self):
        ui=self.editor();values=dict(ui.doc.values,auto_haptics_enable=2,disable_speaker=1)
        ui.doc.load(values);ui.render_fields();ui.select_value('auto_haptics_enable',0)
        self.assertEqual(ui.doc.changes,{'auto_haptics_enable':0,'disable_speaker':0})
        ui.doc.load(dict(values,auto_haptics_enable=0));ui.refresh_read_values()
        self.assertEqual(ui.doc.values['disable_speaker'],1);self.assertFalse(ui.doc.changes)

if __name__=='__main__':unittest.main()
