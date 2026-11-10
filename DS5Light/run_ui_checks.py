"""Run Korean and English UI checks in isolated processes."""
import os
from pathlib import Path
import subprocess
import sys
ROOT=Path(__file__).resolve().parent
CASES={'ko':['test_localization','test_studio_dependencies','test_studio_macro_flow','test_studio_presentation','test_studio_entry_revision','test_ui_lifecycle'],'en':['test_localization','test_english_ui']}
def main():
 for language,modules in CASES.items():
  print('UI checks: '+language,flush=True)
  code="import sys,unittest;sys.argv=['ui-check','--language',"+repr(language)+"];suite=unittest.defaultTestLoader.loadTestsFromNames("+repr(modules)+");r=unittest.TextTestRunner(verbosity=2).run(suite);sys.exit(not r.wasSuccessful())"
  result=subprocess.run([sys.executable,'-c',code],cwd=ROOT,env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',PYTHONIOENCODING='utf-8'))
  if result.returncode:return result.returncode
 return 0
if __name__=='__main__':raise SystemExit(main())
