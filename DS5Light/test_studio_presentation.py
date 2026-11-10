import tkinter as tk
from tkinter import ttk
import unittest
from unittest.mock import patch
import test_studio_settings as base
from studio_scope import EDITABLE
from studio_help import help_text,reference_point,LABELS,TITLES,DESCRIPTIONS
from studio_reference import WEB_HELP
from studio_tooltip_ko import TRANSLATED_HELP
from studio_range import RangeSlider

def walk(widget):
    for child in widget.winfo_children():
        yield child
        yield from walk(child)

class PresentationTests(unittest.TestCase):
    setUp=base.NativeUITests.setUp
    tearDown=base.NativeUITests.tearDown
    editor=base.NativeUITests.editor
    def texts(self,e):
        out=[]
        for w in walk(e.body):
            try:out.append(w.cget('text'))
            except tk.TclError:pass
        return out
    def test_clean_translated_help(self):
        for key in EDITABLE:
            text=help_text(key)
            self.assertNotIn('('+key+')',text)
            for removed in ('근거:','Suggested setup','출처:','Studio 원문','편집만으로'):self.assertNotIn(removed,text)
            if WEB_HELP.get(key):
                description=DESCRIPTIONS.get(key,'')
                self.assertTrue(any('가'<=char<='힣' for char in description),key)
        self.assertEqual(reference_point('audio_buffer_length'),(48,'추천'))
        self.assertIn('끊기면 64',help_text('audio_buffer_length'))
        self.assertEqual(LABELS['gyro_output'],'자이로 작동 기준')
        self.assertEqual(LABELS['haptics_gain'],'햅틱 파형 증폭')
        self.assertEqual(TITLES['Device & Connection'],'장치')
    def test_only_question_icons_have_option_tips(self):
        e=self.editor()
        for category in range(4):
            e.select_category(category)
            self.assertTrue(e.tips)
            for tip in e.tips:self.assertTrue(getattr(tip.widget,'_studio_help_icon',False))
            for w in walk(e.body):
                if isinstance(w,(tk.Label,RangeSlider)):self.assertFalse(w.bind('<Enter>'))
    def test_compact_values_units_and_right_alignment(self):
        e=self.editor();e.select_category(0)
        self.assertIn('분',self.texts(e))
        for w in walk(e.body):
            if isinstance(w,ttk.Entry) and not isinstance(w,ttk.Combobox):self.assertEqual(int(w.cget('width')),4)
            if isinstance(w,ttk.Combobox):self.assertEqual(w.cget('justify'),'right')
    def test_slider_end_numbers_and_marker(self):
        e=self.editor();self.root.deiconify();self.root.update_idletasks()
        sliders=[w for w in walk(e.body) if isinstance(w,RangeSlider)]
        self.assertTrue(sliders)
        for slider in sliders:
            slider.draw();texts=[slider.itemcget(i,'text') for i in slider.find_all() if slider.type(i)=='text']
            low,high=slider.limits()
            self.assertIn(f'{low:g}',texts);self.assertIn(f'{high:g}',texts)
    def test_search_hint_is_not_query_text(self):
        e=self.editor();self.assertEqual(e.search.get(),'');self.assertEqual(e.search_hint.cget('text'),'설정 검색')
        e.search.set('gyro');self.assertEqual(e.search_hint.winfo_manager(),'')
    def test_trigger_editor_replaces_old_web_only_notice(self):
        e=self.editor();e.select_category(2);texts=self.texts(e)
        self.assertIn('L2',texts);self.assertIn('R2',texts)
        self.assertNotIn('고급 트리거 효과는 웹 설정을 이용하세요.',texts)
        self.assertFalse(any('공사 중' in str(text) for text in texts))
    def test_macro_add_matches_upstream_empty_slot_and_enabled_mask(self):
        e=self.editor();e.doc.macros={str(i):[0]*35 for i in range(32)};e.doc.macro_baseline={k:v[:] for k,v in e.doc.macros.items()};e.select_category(4)
        self.assertIn('+ 매핑·매크로 추가',self.texts(e))
        with patch.object(e,'edit_macro') as opened,patch.object(e,'with_client') as hid:
            e.new_macro();self.assertEqual(opened.call_args.args,(0,));self.assertTrue(any(opened.call_args.kwargs['initial']));hid.assert_not_called()
        self.assertFalse(any(e.doc.macros['0']));self.assertEqual(e.doc.values['macro_disable']&1,1);self.assertFalse(e.doc.dirty)
    def test_macro_add_reads_definitions_first(self):
        e=self.editor()
        with patch.object(e,'task') as task:
            e.new_macro();self.assertEqual(task.call_args.args[0],'macros');self.assertEqual(e.after_macro_read,e.new_macro)
    def test_slot_import_and_separate_bootloader_card(self):
        e=self.editor();e.select_category(5)
        self.assertIn('전체 슬롯 가져오기',self.texts(e));self.assertIn('Pico 펌웨어 설치',self.texts(e))
        self.assertNotIn('슬롯 파일 복원',self.texts(e))

if __name__=='__main__':unittest.main()
