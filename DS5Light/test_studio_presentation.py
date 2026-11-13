import tkinter as tk
from tkinter import ttk
import unittest
from unittest.mock import Mock, patch
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
        self.assertEqual(LABELS['haptics_gain'],'네이티브 햅틱 세기')
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
        self.assertIn('L2 · 끔',texts);self.assertIn('R2 · 끔',texts)
        self.assertNotIn('고급 트리거 효과는 웹 설정을 이용하세요.',texts)
        self.assertNotIn('추가 설정',texts)
        self.assertNotIn('게임 적응형 트리거 효과 대체',texts)
        self.assertEqual(texts.count('게임 효과보다 내 설정 우선'),1)
        self.assertFalse(e.vars['synth_force'].get())
        self.assertFalse(any('공사 중' in str(text) for text in texts))

    def test_trigger_side_switch_keeps_drafts_and_shows_shared_fields_once(self):
        e=self.editor()
        e.doc.values.update(at_l2_mode=2,at_l2_shape=3,at_mode=2,at_shape=0)
        e.select_category(2)
        self.assertIn('벽 통과 위치',self.texts(e))
        self.assertNotIn('at_strength',e.vars)
        e.number_changed('at_l2_start_pos','4')
        next(w for w in walk(e.body) if isinstance(w,ttk.Button) and w.cget('text').startswith('R2 ·')).invoke()
        self.assertEqual(e.doc.values['at_l2_start_pos'],4)
        self.assertIn('at_strength',e.vars)
        self.assertNotIn('at_l2_strength',e.vars)
        common=next(w for w in walk(e.body) if isinstance(w,ttk.Button) and 'L2/R2 공통 설정' in w.cget('text'))
        self.assertTrue(common.cget('text').startswith('▾'))
        self.assertEqual(self.texts(e).count('트리거 반동 소스'),1)
        self.assertIn('synth_force',e.vars)
        common.invoke()
        self.assertNotIn('synth_force',e.vars)

    def test_trigger_status_only_reads_and_rejects_incomplete_reply(self):
        e=self.editor()
        with patch.object(e,'task') as task, patch.object(e,'with_client') as use_client:
            e.check_trigger_status('R2')
            self.assertEqual(task.call_args.args[0],'trigger_status')
            operation=task.call_args.args[1]
            client=Mock()
            use_client.side_effect=lambda read:read(client)
            client.command.return_value=bytes((0x66,0x0c,0,2,0x36,1,2,0x3c,1,90))
            self.assertEqual(operation(),('R2',2,90))
            client.command.assert_called_once_with(0x0c,bytes((2,0x36,0x3c)),echo=b'\x02')
            client.command.return_value=bytes((0x66,0x0c,1,0))
            with self.assertRaises(ValueError):operation()

    def test_quick_input_stages_self_mapping_and_copies_to_correct_side(self):
        from studio_settings_protocol import validate_changes
        e=self.editor();e.select_category(2)
        def choose(value):
            effect=next(w for w in walk(e.body) if isinstance(w,ttk.Combobox) and '단축 트리거' in w.cget('values'))
            effect.set(value);effect.event_generate('<<ComboboxSelected>>')
        choose('단축 트리거')
        self.assertTrue(e.vars['synth_force'].get())
        self.assertEqual({k:e.doc.values[k] for k in ('t2_l2_mode','t2_l2_pos','t2_l2_button','at_l2_strength','at_l2_start_pos')},
                         dict(t2_l2_mode=1,t2_l2_pos=14,t2_l2_button=9,at_l2_strength=100,at_l2_start_pos=2))
        self.assertEqual(e.doc.values['t2_mode'],0)
        self.assertIn('100%로 인식되는 깊이',self.texts(e))
        self.assertIn('저항 시작 위치',self.texts(e))
        self.assertEqual(e.range_controls['t2_l2_pos'][1].marker,14)
        self.assertEqual(e.range_controls['at_l2_strength'][1].marker,100)
        self.root.deiconify()
        self.root.update_idletasks()
        self.assertFalse(any(w.find_withtag('full_input_depth') for w in walk(e.body) if isinstance(w,tk.Canvas)))
        e.vars['t2_l2_pos'].set('18')
        e.copy_trigger('at_l2_','at_')
        self.assertEqual((e.doc.values['t2_mode'],e.doc.values['t2_pos'],e.doc.values['t2_button']),(1,18,10))
        self.assertEqual(e.doc.values['at_start_pos'],2)
        validate_changes(e.doc.baseline,e.doc.changes)
        choose('끔')
        self.assertEqual(e.doc.values['t2_l2_mode'],0)
        self.assertEqual(e.doc.values['t2_mode'],1)
        self.assertTrue(e.vars['synth_force'].get())
        next(w for w in walk(e.body) if isinstance(w,ttk.Button) and w.cget('text').startswith('R2 ·')).invoke()
        choose('끔')
        self.assertFalse(e.vars['synth_force'].get())
        e.revert()
        self.assertFalse(e.doc.changes)

    def test_switching_active_trigger_effect_resets_sliders_and_markers(self):
        e=self.editor()
        e.doc.values.update(at_l2_mode=2,at_l2_shape=0,at_l2_strength=82,at_l2_start_pos=7)
        e.select_category(2)
        for name,start in (('점점 무거워짐',0),('2단계 저항',40)):
            effect=next(w for w in walk(e.body) if isinstance(w,ttk.Combobox) and '단축 트리거' in w.cget('values'))
            self.assertEqual(tuple(effect.cget('values')[:2]),('끔','단축 트리거'))
            effect.set(name);effect.event_generate('<<ComboboxSelected>>')
            for suffix,value in (('strength',start),('start_pos',0),('strength_b',100)):
                slider=e.range_controls['at_l2_'+suffix][1]
                self.assertEqual((slider.variable.get(),slider.marker),(str(value),value))

    def test_trigger_dropdown_reveals_new_field(self):
        e=self.editor()
        e.doc.values.update(at_l2_mode=2,at_l2_shape=2)
        e._open_option_groups.update({('L2','recoil'),('triggers','common')})
        self.root.geometry('900x690')
        self.root.deiconify()
        e.select_category(2)
        self.root.update_idletasks()
        e.canvas.yview_moveto(.25)
        offset=e.canvas.canvasy(0)
        self.assertGreater(offset,0)
        condition=e.field_views['at_l2_mode'][1][0]
        condition.current(1)
        condition.event_generate('<<ComboboxSelected>>')
        self.root.update_idletasks()
        self.assertEqual(e.doc.values['at_l2_mode'],1)
        title=e.field_views['at_l2_threshold'][0]
        self.assertGreater(e.canvas.canvasy(0),offset)
        self.assertGreaterEqual(title.winfo_rooty(),e.canvas.winfo_rooty())
        self.assertLess(title.winfo_rooty(),e.canvas.winfo_rooty()+e.canvas.winfo_height())

    def test_effect_selection_reveals_custom_trigger_title_and_effect(self):
        e=self.editor()
        self.root.geometry('900x690')
        self.root.deiconify()
        e.select_category(2)
        self.root.update_idletasks()
        for name in ('단축 트리거','2단계 저항','끔'):
            e.canvas.yview_moveto(1)
            effect=next(w for w in walk(e.body) if isinstance(w,ttk.Combobox) and '단축 트리거' in w.cget('values'))
            effect.set(name)
            effect.event_generate('<<ComboboxSelected>>')
            self.root.update_idletasks()
            title=next(w for w in walk(e.body) if isinstance(w,tk.Label) and w.cget('text')=='커스텀 트리거')
            effect=next(w for w in walk(e.body) if isinstance(w,ttk.Combobox) and '단축 트리거' in w.cget('values'))
            top=e.canvas.winfo_rooty()
            self.assertGreaterEqual(title.winfo_rooty(),top)
            self.assertLessEqual(effect.winfo_rooty()+effect.winfo_height(),top+e.canvas.winfo_height())
            self.assertEqual(effect.get(),name)

    def test_new_trigger_starts_at_defaults_and_marker_resets_live_value(self):
        e=self.editor()
        e.doc.values['at_l2_strength']=24
        e.select_category(2)
        self.root.deiconify()
        effect=next(w for w in walk(e.body) if isinstance(w,ttk.Combobox) and '단축 트리거' in w.cget('values'))
        effect.set('일정한 저항')
        effect.event_generate('<<ComboboxSelected>>')
        slider=e.range_controls['at_l2_strength'][1]
        self.assertEqual(e.doc.values['at_l2_strength'],70)
        slider.variable.set('25')
        self.root.update_idletasks()
        marker=slider.find_withtag('default_marker')[0]
        x1,y1,x2,y2=slider.bbox(marker)
        x,y=(x1+x2)//2,(y1+y2)//2
        slider.event_generate('<Motion>',x=x,y=y)
        slider.event_generate('<Button-1>',x=x,y=y)
        self.assertEqual(e.doc.values['at_l2_strength'],70)

    def test_quick_input_requires_firmware_fields_and_preserves_declined_mapping(self):
        e=self.editor();e.doc.values.update(t2_l2_mode=2,t2_l2_pos=80,t2_l2_button=10);e.select_category(2)
        effect=next(w for w in walk(e.body) if isinstance(w,ttk.Combobox) and '단축 트리거' in w.cget('values'))
        with patch('studio_settings_ui.messagebox.askyesno',return_value=False) as confirm:
            effect.set('단축 트리거');effect.event_generate('<<ComboboxSelected>>')
            confirm.assert_called_once()
        self.assertEqual((e.doc.values['t2_l2_mode'],e.doc.values['t2_l2_pos'],e.doc.values['t2_l2_button']),(2,80,10))
        del e.doc.values['t2_l2_button'];e.render_fields()
        self.assertFalse(any('단축 트리거' in w.cget('values') for w in walk(e.body) if isinstance(w,ttk.Combobox)))
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
