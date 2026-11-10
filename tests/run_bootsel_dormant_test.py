"""Host register model of actual firmware code; no device access."""
from pathlib import Path
import os,re,subprocess

root=Path(__file__).resolve().parents[1]
base=root.parent/'DS5Dongle-Studio-build'
out=base/'reports/bootsel-dormant-tests';out.mkdir(parents=True,exist_ok=True)
source=(root/'src/manual_power.cpp').read_text(encoding='utf-8')
start=source.index('static void __no_inline_not_in_flash_func(dormant_wait_with_bootsel)() {')
end=source.index('\n}',start)+2
(out/'bootsel_dormant_extract.h').write_text(source[start:end],encoding='utf-8')
sdk=base/'source/toolchain/pico-sdk/src/rp2350/hardware_regs/include/hardware/regs'
text='\n'.join((sdk/(name+'.h')).read_text() for name in ('io_qspi','pads_qspi','sio','xosc'))
names=set(re.findall(r'\b(?:IO_QSPI_|PADS_QSPI_|SIO_GPIO_HI_IN_QSPI_CSN_|XOSC_DORMANT_|XOSC_STATUS_)[A-Z0-9_]+',source[start:end]))
definitions=[]
for name in sorted(names):
    value=re.search(r'^#define '+name+r'\s+_u\((0x[0-9a-fA-F]+|[0-9]+)\)',text,re.M)
    assert value,name
    definitions.append('#define '+name+' '+value[1]+'u')
(out/'bootsel_register_extract.h').write_text('\n'.join(definitions)+'\n',encoding='utf-8')
bin_dir=base/'source/toolchain/mingw64/mingw64/bin'
env=dict(os.environ);env['PATH']=str(bin_dir)+os.pathsep+env.get('PATH','')
exe=out/'bootsel_dormant_test.exe'
subprocess.run([str(bin_dir/'g++.exe'),'-std=c++17','-Wall','-Wextra','-Werror','-I'+str(out),str(root/'tests/bootsel_dormant_test.cpp'),'-o',str(exe)],env=env,check=True)
p=subprocess.run([str(exe)],env=env,capture_output=True,text=True,check=True)
(out/'result.txt').write_text(p.stdout,encoding='utf-8');print(p.stdout)
