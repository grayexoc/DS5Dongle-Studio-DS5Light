from pathlib import Path
import json,re,subprocess,os
r=Path(__file__).resolve().parents[1];out=r/'build/profile-event-tests';out.mkdir(parents=True,exist_ok=True)
desc=(r/'src/usb_descriptors.cpp').read_text(encoding='utf-8')
macro=re.search(r'#define PROFILE_EVENT_DESCRIPTOR ([^\n]+)',desc).group(1)
for name,expected in (('desc_hid_report_ds',316),('desc_hid_report_dse',432),('xinput_settings_report',None)):
 text=desc.split(name+'[] = {',1)[1].split('};',1)[0].replace('PROFILE_EVENT_DESCRIPTOR',macro)
 text=re.sub(r'//[^\n]*','',text)
 raw=bytes(int(v.strip(),0) for v in text.split(',') if v.strip())
 if expected:assert len(raw)==expected,(name,len(raw))
 pos=0;rid=0;size=0;count=0;found=[]
 while pos<len(raw):
  prefix=raw[pos];pos+=1;n=(0,1,2,4)[prefix&3];value=int.from_bytes(raw[pos:pos+n],'little');pos+=n
  if prefix==0x85:rid=value
  elif prefix==0x75:size=value
  elif prefix==0x95:count=value
  elif prefix in (0x81,0xb1) and rid==0x8f:found.append((prefix,size*count))
 assert found==[(0x81,120),(0xb1,120)],(name,found)
print('PASS all three HID descriptors: event-only 15-byte input/feature, exact lengths',flush=True)
s=(r/'src/usb.cpp').read_text(encoding='utf-8');code=s[s.index('namespace {\nbool profile_event_subscribed'):]
stub='''
#include <cstdint>
#include <cstring>
#include <cassert>
#define SLOT_NAME_LEN 16
#define ENABLE_WAKE_HID
uint32_t clock_ms=0;bool ready=true,reconnect=false,accept=true;unsigned sent=0;uint8_t slot=1;bool edited=false,mute=false;
struct Config{uint8_t auto_haptics_enable=1,mix_native_level=0,ah_dsp_source=0;} cfg;
Config&get_config(){return cfg;}
bool active_profile_get(uint8_t&s,bool&e,uint8_t*){s=slot;e=edited;return true;}
bool macro_uses_mute_button(){return mute;}
bool usb_served_idle_pid(){return false;} bool usb_reconnect_pending(){return reconnect;}
uint32_t get_absolute_time(){return clock_ms;} uint32_t to_ms_since_boot(uint32_t t){return t;}
bool tud_hid_ready(){return ready;}
bool tud_hid_report(uint8_t id,const void*p,uint16_t n){assert(id==0x8f&&n==15);if(accept)++sent;return accept;}
'''
checks='''
int main(){uint8_t b[15];usb_profile_event_task();assert(sent==0);
assert(usb_profile_event_get(b,14)==0);assert(usb_profile_event_get(b,15)==15);
usb_profile_event_task();assert(sent==1);usb_profile_event_task();assert(sent==1);
clock_ms=100;slot=2;ready=false;usb_profile_event_task();assert(sent==1);
ready=true;usb_profile_event_task();assert(sent==2);
clock_ms=200;mute=true;cfg.auto_haptics_enable=0;usb_profile_event_task();assert(sent==3);
clock_ms=300;accept=false;slot=3;usb_profile_event_task();assert(sent==3);
accept=true;usb_profile_event_task();assert(sent==4);
assert(profile_event_data[9]==3&&profile_event_data[11]==0&&profile_event_data[12]==1);
clock_ms=400;cfg.mix_native_level=80;usb_profile_event_task();assert(sent==5);
clock_ms=500;cfg.ah_dsp_source=1;usb_profile_event_task();assert(sent==6);
assert(profile_event_data[4]==1&&profile_event_data[13]==0&&profile_event_data[14]==0);
clock_ms=600;usb_profile_event_slot_saved();usb_profile_event_task();assert(sent==7);
clock_ms=65000;slot=4;usb_profile_event_task();assert(sent==7);
usb_profile_event_get(b,15);usb_profile_event_task();assert(sent==8);
}
'''
p=out/'event.cpp';p.write_text(stub+code+checks,encoding='utf-8')
bin=r.parent/'DS5Dongle-Studio-build/source/toolchain/mingw64/mingw64/bin';env=dict(os.environ);env['PATH']=str(bin)+os.pathsep+env.get('PATH','')
subprocess.run([str(bin/'g++.exe'),'-std=c++17',str(p),'-o',str(out/'event.exe')],env=env,check=True)
subprocess.run([str((out/'event.exe').resolve())],env=env,check=True)
print('PASS firmware event state, idle, dedupe, backpressure and mode/mute changes',flush=True)
from test_support import firmware_build
rows=json.loads((firmware_build(r)/'compile_commands.json').read_text())
with (out/'arm-syntax.log').open('w',encoding='utf-8') as log:
 for name in ('main.cpp','usb.cpp','usb_descriptors.cpp','config.cpp','cmd.cpp','bt.cpp'):
  row=next(e for e in rows if Path(e['file']).name==name)
  cmd,n=re.subn(r' -o \S+ -c ',' -fsyntax-only ',row['command']);assert n==1
  subprocess.run(cmd,cwd=row['directory'],stdout=log,stderr=log,check=True,shell=False)
print('PASS ARM syntax for USB, profile metadata and Bluetooth transport; no firmware build')


