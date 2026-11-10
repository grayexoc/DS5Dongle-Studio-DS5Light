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
