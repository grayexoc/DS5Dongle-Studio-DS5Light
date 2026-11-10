"""Compile the real PS shortcut engine; mock USB submission, clock and ownership."""
from pathlib import Path
import os
import subprocess

root=Path(__file__).resolve().parents[1]
out=root/'build/ps-shortcut-tests';out.mkdir(parents=True,exist_ok=True)
stubs=out/'stubs';(stubs/'class/hid').mkdir(parents=True,exist_ok=True)
(stubs/'class/hid/hid.h').write_text('#pragma once\n',encoding='utf-8')
(stubs/'tusb.h').write_text('''#pragma once
#include <cstdint>
constexpr uint8_t HID_KEY_G=0x0a,HID_KEY_TAB=0x2b,KEYBOARD_MODIFIER_LEFTGUI=8;
bool tud_hid_n_ready(uint8_t);
bool tud_hid_n_keyboard_report(uint8_t,uint8_t,uint8_t,const uint8_t*);
''',encoding='utf-8')
code=r'''
#include <cassert>
#include <cstdio>
#include <cstring>
#include "ps_shortcut.h"
#include "config.h"
#include "input_buttons.h"
#include "tusb.h"
uint32_t g_now_ms=1000,shift=0;
bool ready=true,accepted=true,suspended=false,waking=false,macro_active=false;
unsigned reports=0;uint8_t last_mod=0,last_key=0;Config_body cfg{};
Config_body &get_config(){return cfg;}
uint32_t macro_shift_key(){return shift;}
bool macro_busy(){return macro_active;}
bool wake_host_is_suspended(){return suspended;}
bool wake_owns_keyboard(){return waking;}
bool tud_hid_n_ready(uint8_t){return ready;}
bool tud_hid_n_keyboard_report(uint8_t,uint8_t,uint8_t mods,const uint8_t *keys){
 if(!accepted)return false;
 ++reports;last_mod=mods;last_key=keys?keys[0]:0;return true;
}
uint8_t report[63]{};
void clean(){
 ready=accepted=true;suspended=waking=macro_active=false;shift=0;
 ps_shortcut_reset();assert(!ps_shortcut_owns_keyboard());
 cfg.ps_shortcut_enabled=1;g_now_ms=1000;reports=0;last_mod=last_key=0;
 memset(report,0,sizeof(report));
}
void pulse(uint32_t end=1060){
 clean();g_now_ms=end-60;report[9]=1;ps_shortcut_tick(report,63);
 g_now_ms=end;report[9]=0;ps_shortcut_tick(report,63);
 assert(reports==1&&last_mod==8&&last_key==HID_KEY_G&&ps_shortcut_owns_keyboard());
}
void blank(){assert(last_mod==0&&last_key==0&&!ps_shortcut_owns_keyboard());}
int main(){
 // Key-up is driven without a new BT input report, exactly once at 30 ms.
 pulse();g_now_ms=1089;ps_shortcut_task();assert(reports==1);
 g_now_ms=1090;ps_shortcut_task();blank();assert(reports==2);
 for(int i=0;i<10;++i)ps_shortcut_task();assert(reports==2);
 // A reset must retain the release through repeated USB-busy attempts.
 pulse();ready=false;ps_shortcut_reset();ps_shortcut_reset();ps_shortcut_task();
 assert(ps_shortcut_owns_keyboard()&&reports==1);
 ready=true;ps_shortcut_task();blank();assert(reports==2);
 // Readiness is not submission success: retry rejected reports too.
 pulse();accepted=false;g_now_ms=1100;ps_shortcut_task();
 assert(ps_shortcut_owns_keyboard()&&reports==1);
 accepted=true;ps_shortcut_task();blank();
 // Turning the option off must still send a pending key-up, with no BT input.
 pulse();cfg.ps_shortcut_enabled=0;ps_shortcut_task();blank();
 // PS used as Shift must release an older shortcut before yielding ownership.
 pulse();shift=BTN_PS;ready=false;ps_shortcut_task();ps_shortcut_task();
 assert(ps_shortcut_owns_keyboard());ready=true;ps_shortcut_task();blank();
 report[9]=1;ps_shortcut_tick(report,63);assert(reports==2);
 // Wake's F15 sequence and a suspended USB bus must not be overwritten.
 pulse();suspended=true;g_now_ms=1200;ps_shortcut_task();assert(reports==1);
 suspended=false;waking=true;ps_shortcut_task();assert(reports==1);
 waking=false;ps_shortcut_task();blank();
 clean();waking=true;report[9]=1;ps_shortcut_tick(report,63);
 g_now_ms+=1000;ps_shortcut_tick(report,63);assert(reports==0);
 // A held/playing macro wins over a newly requested PS shortcut.
 clean();macro_active=true;report[9]=1;ps_shortcut_tick(report,63);
 g_now_ms+=60;report[9]=0;ps_shortcut_tick(report,63);
 assert(reports==0&&!ps_shortcut_owns_keyboard());
 // A rejected key-down never reserves the keyboard or schedules a phantom key-up.
 clean();accepted=false;report[9]=1;ps_shortcut_tick(report,63);
 g_now_ms+=60;report[9]=0;ps_shortcut_tick(report,63);
 assert(reports==0&&!ps_shortcut_owns_keyboard());
 // Long press remains Win+Tab and does not also send Win+G on release.
 clean();report[9]=1;ps_shortcut_tick(report,63);
 g_now_ms+=760;ps_shortcut_tick(report,63);assert(last_key==HID_KEY_TAB&&reports==1);
 g_now_ms+=30;ps_shortcut_task();blank();
 report[9]=0;g_now_ms+=60;ps_shortcut_tick(report,63);assert(reports==2);
 // The 30 ms deadline must not fire early across uint32 timer wrap.
 pulse(0xfffffff0u);g_now_ms=0xfffffff1u;ps_shortcut_task();assert(reports==1);
 g_now_ms=0x0e;ps_shortcut_task();blank();assert(reports==2);
 puts("PASS: PS shortcut key-up retry/reset/OFF/Shift, no-input task, submit failure, wake/macro ownership, long press and timer wrap");
}
'''
(out/'test.cpp').write_text(code,encoding='utf-8')
bin_dir=root.parent/'DS5Dongle-Studio-build/source/toolchain/mingw64/mingw64/bin'
env=dict(os.environ);env['PATH']=str(bin_dir)+os.pathsep+env.get('PATH','')
subprocess.run([str(bin_dir/'g++.exe'),'-std=c++17','-DENABLE_WAKE_HID',
 '-I'+str(root/'src'),'-I'+str(stubs),'-I'+str(root/'tools/macro-tests/stubs'),
 str(out/'test.cpp'),str(root/'src/ps_shortcut.cpp'),'-o',str(out/'test.exe')],env=env,check=True)
p=subprocess.run([str(out/'test.exe')],env=env,capture_output=True,text=True)
(out/'result.txt').write_text(p.stdout+p.stderr,encoding='utf-8')
print(p.stdout+p.stderr);p.check_returncode()
