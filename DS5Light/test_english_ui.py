import sys,re,unittest
import localization
from unittest import skipUnless
import test_studio_settings as fixture
from studio_help import help_text
from studio_scope import EDITABLE
from studio_english_strings import EN
from studio_i18n import text
from studio_macro_editor import MacroEditor
kr=re.compile('[가-힣]')
@skipUnless(localization.LANGUAGE=='en', 'Run English checks through run_ui_checks.py')
class EnglishUI(unittest.TestCase):
 setUp=fixture.NativeUITests.setUp
 tearDown=fixture.NativeUITests.tearDown
 editor=fixture.NativeUITests.editor
 def check(self,parent):
  bad=[]
  def walk(w):
   for option in ('text','values'):
    try:v=str(w.cget(option))
    except Exception:continue
    if kr.search(v.replace('한국어','')):bad.append((str(w),option,v))
   for child in w.winfo_children():walk(child)
  walk(parent);self.assertFalse(bad,bad[:8])
 def test_categories_search_and_macro(self):
  ui=self.editor();self.root.geometry("860x1000+0+0");self.root.deiconify();self.root.update()
  for category in range(6):
   ui.select_category(category);self.root.update_idletasks();self.check(ui.parent)
   self.assertLessEqual(ui.body.winfo_reqwidth(),ui.canvas.winfo_width()+1,(category,ui.body.winfo_reqwidth(),ui.canvas.winfo_width()))
  ui.search.set('rumble');ui.render_fields();self.check(ui.parent)
  ui.search.set('');ui.select_category(4)
  ui.doc.macros={str(i):[0]*35 for i in range(32)};ui.doc.macro_baseline={k:list(v) for k,v in ui.doc.macros.items()}
  ui.new_macro();self.check(ui.parent)
  ui.macro_editor.go_step(1);self.check(ui.parent)
  ui.macro_editor.close()
 def test_help_and_catalog(self):
  for key in EDITABLE:self.assertFalse(kr.search(help_text(key)),key)
  for source in EN:self.assertFalse(kr.search(text(source)),source)
 def test_studio_actions_and_audio_mode_fit_at_minimum_width(self):
  from tkinter import font,ttk
  ui=self.editor()
  self.root.geometry('860x860+0+0');self.root.deiconify();self.root.update_idletasks()
  style=ttk.Style(self.root)
  for button in (ui.apply_button,ui.save_button):
   name=button.cget('style') or button.winfo_class()
   measure=font.Font(root=self.root,font=style.lookup(name,'font') or 'TkDefaultFont').measure
   self.assertGreaterEqual(button.winfo_width(),measure(button.cget('text'))+8)
  selector=ui.field_views['auto_haptics_enable'][1][0]
  measure=font.nametofont('TkTextFont').measure
  for option in selector.cget('values'):
   self.assertGreaterEqual(selector.winfo_width(),measure(option)+24,option)

class TemplateTests(unittest.TestCase):
 def test_arguments_preserved(self):
  import string
  parser=string.Formatter()
  for source,target in EN.items():
   if '{' not in source:continue
   self.assertEqual(sorted(f for _,f,_,_ in parser.parse(source) if f is not None),sorted(f for _,f,_,_ in parser.parse(target) if f is not None),source)

if __name__=='__main__': unittest.main(verbosity=2)


class TerminologyTests(unittest.TestCase):
 def test_reviewed_fields_have_short_labels_and_help(self):
  from studio_english_strings import FIELD_LABELS,FIELD_HELP,OPTION_TEXT
  for key in EDITABLE:
   self.assertIn(key,FIELD_LABELS,key)
   self.assertIn(key,FIELD_HELP,key)
   self.assertLessEqual(len(FIELD_LABELS[key]),40,key)
   self.assertLessEqual(len(FIELD_HELP[key]),220,key)
  self.assertEqual(OPTION_TEXT['Mouse (finer aim; needs the pad hidden in most games)'],'Mouse')
 def test_bundled_terms_and_placeholders(self):
  from translations import EN as catalog
  self.assertEqual(catalog['세기'],'Strength')
  self.assertEqual(catalog['체크 해제'],'Unchecked')
  for source,target in catalog.items():
   self.assertNotIn('audiohaptic',target.lower(),source)


@skipUnless(localization.LANGUAGE=='en', 'English presentation checks')
class EnglishRevisionTests(unittest.TestCase):
 def test_new_layer_and_profile_terms(self):
  from studio_help import label
  self.assertEqual(text('프로필 {0}번').format(8),'Profile 8')
  self.assertEqual(text('시프트 레이어에서 사용'),'Use in shift layer')
  self.assertEqual(label('speaker_gain'),'DualSense speaker gain')
  self.assertEqual(label('disable_inactive_disconnect'),'Disable idle disconnect')
  self.assertEqual(localization.tr('오디오햅틱 세기'),'Audio haptics strength')
 def test_gyro_conditions_keep_button_icons(self):
  from studio_help import options
  from studio_fields import FIELDS
  from controller_glyphs import icon_key,glyph
  import tkinter as tk
  root=tk.Tk();root.withdraw()
  try:
   for key in ('gyro_mode','at_mode','at_l2_mode'):
    for _,value in options(FIELDS[key]):
     if value.startswith('Hold '):
      self.assertEqual(icon_key(value),value[5:])
      self.assertIsNotNone(glyph(root,value),value)
   from studio_button_names import NAMES
   for name in NAMES:self.assertIsNotNone(glyph(root,name),name)
   self.assertEqual(text('듀얼센스 전원'),'DualSense power')
   self.assertIsNotNone(glyph(root,text('듀얼센스 전원')))
  finally:root.destroy()
 def test_shift_flags_and_profile_outputs_are_translated(self):
  # The complete editor is exercised by EnglishUI; check the previously hidden captions too.
  for key in ('시프트 레이어에서 사용','전환 신호음','프로필 {0}번'):
   self.assertFalse(kr.search(text(key)),key)


@skipUnless(localization.LANGUAGE=='en', 'English presentation checks')
class EnglishMinimumDpiTests(unittest.TestCase):
 tearDown=fixture.NativeUITests.tearDown
 editor=fixture.NativeUITests.editor
 def setUp(self):
  from unittest.mock import patch
  dpi=patch('ui_dpi._window_dpi',return_value=120)
  dpi.start()
  self.addCleanup(dpi.stop)
  fixture.NativeUITests.setUp(self)
 def test_reported_controls_fit_at_125_percent(self):
  from tkinter import font
  from ui_dpi import ui_scale
  width,height=self.root.minsize()
  self.root.geometry(f'{width}x{height}+0+0')
  self.root.deiconify();self.root.update()
  self.assertEqual(ui_scale(self.root),1.25)
  for check in self.ui.advanced_checks:
   self.assertTrue(check.winfo_viewable(),check.text)
   left,top,right,bottom=check.bbox('all')
   self.assertGreaterEqual(min(left,top),0,check.text)
   self.assertLessEqual(right,check.winfo_width(),check.text)
   self.assertLessEqual(bottom,check.winfo_height(),check.text)
  ui=self.editor()
  def labels(parent):
   for child in parent.winfo_children():
    if child.winfo_class()=='Label':yield child
    yield from labels(child)
  for category,prefix in ((3,'Hold DualSense level'),(4,'Shared mappings.')):
   ui.select_category(category);self.root.update_idletasks()
   label=next(w for w in labels(ui.body) if w.cget('text').startswith(prefix))
   assigned_font=font.Font(root=self.root,font=label.cget('font'))
   lines=label.cget('text').splitlines()
   self.assertLessEqual(max(map(assigned_font.measure,lines)),label.winfo_width())
   self.assertLess(label.winfo_height(),(len(lines)+1)*assigned_font.metrics('linespace'))
  ui.doc.macros={str(i):[0]*35 for i in range(32)}
  ui.doc.macro_baseline={k:list(v) for k,v in ui.doc.macros.items()}
  ui.new_macro();editor=ui.macro_editor
  editor.buttons[0].set(True);editor.go_step(1);self.root.update_idletasks()
  for title,button in editor.output_kind_buttons:
   self.assertTrue(button.winfo_viewable(),title)
   self.assertGreaterEqual(button.winfo_width(),button.winfo_reqwidth(),title)
