"""Compare production lookup math and the current AA/Mix/WDL output stages."""
from pathlib import Path
import os
import re
import subprocess
import tempfile
import json
from test_support import firmware_build

root=Path(__file__).resolve().parents[1]
bin_dir=root.parent/'DS5Dongle-Studio-build/source/toolchain/mingw64/mingw64/bin'
env=dict(os.environ,PATH=str(bin_dir)+os.pathsep+os.environ.get('PATH',''))
with tempfile.TemporaryDirectory(prefix='haptic-math-') as temporary:
    out=Path(temporary)
    executable=out/'test.exe'
    subprocess.run([str(bin_dir/'g++.exe'),'-O3','-std=c++17','-DWDL_RESAMPLE_TYPE=float',
                    '-DWDL_RESAMPLE_NO_SSE','-I'+str(root/'src'),'-I'+str(root/'lib/WDL/WDL'),
                    str(root/'tests/haptic_math_test.cpp'),str(root/'lib/WDL/WDL/resample.cpp'),
                    '-o',str(executable)],env=env,check=True)
    subprocess.run([str(executable)],env=env,check=True)
    build=firmware_build(root)
    entries=json.loads((build/'compile_commands.json').read_text())
    entry=next(row for row in entries if Path(row['file']).name=='audio.cpp')
    command,count=re.subn(r' -o \S+ -c ',' -fsyntax-only ',entry['command'])
    assert count==1
    subprocess.run(command,cwd=entry['directory'],check=True)
    print('PASS: audio.cpp ARM syntax; no firmware build or device write')
