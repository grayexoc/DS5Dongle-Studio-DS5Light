"""Host behavior tests and ARM syntax checks; no firmware build or device access."""
from pathlib import Path
import json, os, re, subprocess
root=Path(__file__).resolve().parents[1]
base=root.parent/'DS5Dongle-Studio-build'
out=base/'reports/rumble-shape-tests';out.mkdir(parents=True,exist_ok=True)
bin_dir=base/'source/toolchain/mingw64/mingw64/bin'
env=dict(os.environ);env['PATH']=str(bin_dir)+os.pathsep+env.get('PATH','')
subprocess.run([str(bin_dir/'g++.exe'),'-std=c++17','-Wall','-Wextra','-I'+str(root/'src'),
    str(root/'tests/rumble_shape_test.cpp'),'-o',str(out/'test.exe')],env=env,check=True)
p=subprocess.run([str(out/'test.exe')],env=env,capture_output=True,text=True)
(out/'result.txt').write_text(p.stdout+p.stderr,encoding='utf-8');print(p.stdout+p.stderr);p.check_returncode()
# Exercise the actual integration block without the unrelated trigger DSP.
source=(root/'src/state_mgr.cpp').read_text(encoding='utf-8')
first=source.index('    // Shape only controller-emulated rumble.')
block=source[first:source.index('\n    if (!get_config().lock_volume',first)]
code=r'''
#include "rumble_shape.h"
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstring>
struct State { bool EnableRumbleEmulation=false, UseRumbleNotHaptics=false, EnableImprovedRumbleEmulation=false;
 uint8_t RumbleEmulationLeft=0,RumbleEmulationRight=0;uint8_t triggers[22]{}; } state;
bool usb_xinput_active(){return false;}
struct Config {uint8_t auto_haptics_enable=0,rumble_gain=200,rumble_release=1;} config;
const Config &get_config() {return config;}
uint32_t now=0;
uint32_t get_absolute_time() {return now;}
uint32_t to_ms_since_boot(uint32_t n) {return n;}
RumbleShape rumble_shape;
bool rumble_output_pending=false;
void apply(const State &update,uint8_t size,bool auto_haptics_on) {
 const State old_state=state;
'''+block+r'''
}
int main() {
 State input;input.RumbleEmulationLeft=100;input.RumbleEmulationRight=25;
 state.UseRumbleNotHaptics=true;memset(state.triggers,0x55,22);
 apply(input,63,false);assert(state.RumbleEmulationLeft==200&&state.RumbleEmulationRight==50);
 assert(input.RumbleEmulationLeft==100);for(auto b:state.triggers)assert(b==0x55);
 State zero;now=1;apply(zero,63,false);assert(state.RumbleEmulationLeft==200&&rumble_shape.active());
 now=11;apply(zero,63,false);assert(state.RumbleEmulationLeft==100&&state.RumbleEmulationRight==25);
 state.RumbleEmulationLeft=7;state.RumbleEmulationRight=8;
 apply(input,63,true);assert(state.RumbleEmulationLeft==7&&state.RumbleEmulationRight==8&&!rumble_shape.active());
 state.UseRumbleNotHaptics=false;apply(input,63,false);
 assert(state.RumbleEmulationLeft==7&&state.RumbleEmulationRight==8&&!rumble_shape.active());
 state.UseRumbleNotHaptics=true;apply(input,3,false);
 assert(state.RumbleEmulationLeft==7&&!rumble_shape.active());
 puts("PASS: real integration gate: auto-haptics/native/short report bypass; raw source and triggers unchanged");
}
'''
(out/'integration.cpp').write_text(code,encoding='utf-8')
subprocess.run([str(bin_dir/'g++.exe'),'-std=c++17','-I'+str(root/'src'),str(out/'integration.cpp'),
    '-o',str(out/'integration.exe')],env=env,check=True)
p=subprocess.run([str(out/'integration.exe')],env=env,capture_output=True,text=True)
with (out/'result.txt').open('a',encoding='utf-8') as log:log.write(p.stdout+p.stderr)
print(p.stdout+p.stderr);p.check_returncode()
from test_support import firmware_build
build=firmware_build(root)
rows=json.loads((build/'compile_commands.json').read_text())
logs=[]
for name in ('state_mgr.cpp','bt.cpp','config.cpp','cmd.cpp'):
    row=next(r for r in rows if r['file'].endswith(name))
    command,n=re.subn(r' -o \S+ -c ',' -fsyntax-only ',row['command']);assert n==1
    command=command.replace(row['file'],str(root/'src'/name))
    p=subprocess.run(command,cwd=build,capture_output=True,text=True)
    logs.append(name+': '+str(p.returncode)+'\n'+p.stdout+p.stderr)
    (out/'syntax.txt').write_text('\n'.join(logs),encoding='utf-8');p.check_returncode()
print('PASS: ARM syntax checks (4 files); no firmware build')
