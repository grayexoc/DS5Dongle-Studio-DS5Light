"""Run the real macro engine's original regressions and new layer/action cases."""
from pathlib import Path
import os,shutil,subprocess
root=Path(__file__).resolve().parents[1]
out=root/'build'/'macro-layer-tests';out.mkdir(exist_ok=True)
stubs=out/'stubs';shutil.copytree(root/'tools/macro-tests/stubs',stubs,dirs_exist_ok=True)
shutil.copyfile(root/'src/macro.cpp',stubs/'macro.cpp')
assert (stubs/'macro.cpp').read_bytes()==(root/'src/macro.cpp').read_bytes()
source=r'''
#define main original_main
#include "ORIGINAL"
#undef main
#include <cassert>
#include "profile_chime.h"
bool storage_redo_write(uint32_t target,const uint8_t*image,uint32_t bytes){
 flash_range_erase(target,FLASH_SECTOR_SIZE);flash_range_program(target,image,bytes);return true;
}
static MacroRecord output(uint32_t source,uint8_t destination,uint8_t flags){
 MacroRecord r{};r.entry.chord=source;r.entry.out_btn=destination;r.entry.flags=flags;return r;
}
int main(){
 int old=original_main();assert(old==0);
 fresh_device();
 g_cfg.enable_wake=0;g_cfg.ps_shortcut_enabled=0;
 g_cfg.gyro_output=g_cfg.stick_mouse=g_cfg.touch_mouse=0;
 enable_only(1);
 assert(!usb_kbd_iface_needed(g_cfg));
 assert(macro_set_entry(0,output(BTN_R3,T2BTN_CROSS,6))&&macro_commit());
 assert(!usb_kbd_iface_needed(g_cfg));
 auto keyboard=output(BTN_R3,0,6);keyboard.entry.keys[0]=4;
 assert(macro_set_entry(0,keyboard)&&!usb_kbd_iface_needed(g_cfg));
 assert(macro_commit()&&usb_kbd_iface_needed(g_cfg));
 enable_only(0);assert(!usb_kbd_iface_needed(g_cfg));
 enable_only(1);macro_load();assert(usb_kbd_iface_needed(g_cfg));
 assert(macro_set_entry(0,output(BTN_R3,MACRO_PROFILE_FIRST,6))&&macro_commit());
 assert(!usb_kbd_iface_needed(g_cfg));
 assert(macro_set_entry(0,output(BTN_R3,MOUT_LEFT,6))&&macro_commit());
 assert(usb_kbd_iface_needed(g_cfg)&&usb_mouse_iface_needed(g_cfg));
 fresh_device();
 macro_set_entry(0,output(BTN_MUTE,MACRO_SHIFT_KEY,6));
 macro_set_entry(1,output(BTN_R3,T2BTN_CROSS,6));
 macro_set_entry(2,output(BTN_R3,T2BTN_CIRCLE,6|MACRO_FLAG_SHIFT));
 macro_set_entry(3,output(BTN_L1,T2BTN_TRIANGLE,6));enable_only(15);
 btn_r3(true);step(10);assert(macro_inject_mask()==(1u<<(T2BTN_CROSS-1)));
 rpt[RPT_BTN2]|=4;step(10);
 assert(macro_inject_mask()==(1u<<(T2BTN_CIRCLE-1)));assert(macro_suppress_mask()&BTN_MUTE);
 rpt[RPT_BTN1]|=1;step(10);
 assert(macro_inject_mask()&(1u<<(T2BTN_TRIANGLE-1))); // unassigned Shift inherits Base
 rpt[RPT_BTN2]&=~4;tick(80);
 assert(macro_inject_mask()&(1u<<(T2BTN_CROSS-1)));
 assert(!(macro_inject_mask()&(1u<<(T2BTN_CIRCLE-1))));
 // Disabled alternate mappings never shadow enabled Base mappings.
 g_cfg.macro_disable|=1u<<2;rpt[RPT_BTN2]|=4;step(10);
 assert(macro_inject_mask()&(1u<<(T2BTN_CROSS-1)));
 macro_suspend(true);step(10);assert(!macro_inject_mask());macro_suspend(false);
 fresh_device();macro_set_entry(0,output(BTN_R3,MACRO_PROFILE_FIRST+7,MACRO_FLAG_CHIME));enable_only(1);
 btn_r3(true);step(10);uint8_t slot=0;bool chime=false;uint32_t source=0;
 assert(macro_take_profile(slot,chime,source)&&slot==7&&chime&&source==BTN_R3);
 assert(!macro_inject_mask());tick(500);assert(!macro_take_profile(slot,chime,source));
 macro_reset();macro_block_until_release(BTN_R3);step(10);assert(!macro_take_profile(slot,chime,source));
 // A one-frame dropout cannot re-arm a key still held across a slot switch.
 btn_r3(false);step(5);btn_r3(true);step(5);tick(60);
 assert(!macro_take_profile(slot,chime,source));
 btn_r3(false);tick(80);btn_r3(true);step(10);assert(macro_take_profile(slot,chime,source));
 // Stable release also works across the 32-bit millisecond timer wrap.
 macro_reset();macro_block_until_release(BTN_R3);g_now_ms=0xfffffff0u;
 btn_r3(false);tick(30);btn_r3(true);step(5);assert(!macro_take_profile(slot,chime,source));
 btn_r3(false);tick(80);btn_r3(true);step(10);assert(macro_take_profile(slot,chime,source));
 // A half-pad action remains blocked while the same physical click is held.
 fresh_device();macro_set_entry(0,output(BTN_TOUCHPAD,MACRO_PROFILE_FIRST,0));enable_only(1);
 touch(true,200,300);rpt[RPT_BTN2]|=2;step(10);assert(macro_take_profile(slot,chime,source));
 macro_reset();macro_block_until_release(BTN_PAD_CLICK_LEFT);
 touch(true,1500,300);tick(80);assert(!macro_take_profile(slot,chime,source));
 rpt[RPT_BTN2]&=~2;tick(80);rpt[RPT_BTN2]|=2;step(10);assert(macro_take_profile(slot,chime,source));
 // Power-off is queued once and never leaks into controller or keyboard output.
 fresh_device();auto power=output(BTN_R3,MACRO_POWER_OFF,MACRO_FLAG_HOLD);
 assert(macro_set_entry(0,power));enable_only(1);
 btn_r3(true);step(10);assert(macro_take_power_off());assert(!macro_inject_mask());
 tick(500);assert(!macro_take_power_off());
 btn_r3(false);tick(80);btn_r3(true);step(10);assert(macro_take_power_off());
 macro_reset();assert(!macro_take_power_off());
 power.entry.gesture=GEST_STICK;assert(!macro_set_entry(0,power));
 fresh_device();assert(macro_set_entry(0,output(BTN_R3,MACRO_POWER_OFF,0)));enable_only(1);
 btn_r3(true);step(10);assert(macro_take_power_off());assert(!macro_inject_mask());
 // Shift storage survives commit/reload without altering the record format.
 fresh_device();auto shift=output(BTN_LEFT_FN,MACRO_SHIFT_KEY,6);
 assert(macro_set_entry(0,shift)&&macro_commit());macro_load();MacroRecord loaded{};macro_get(0,loaded);
 assert(!memcmp(&shift,&loaded,sizeof(shift)));assert(sizeof(MacroRecord)==35);
 shift.entry.chord=BTN_LEFT_FN|BTN_R3;assert(!macro_set_entry(0,shift));
 // USB backpressure during layer/reset releases must not lose the key-up.
 fresh_device();auto held=chord_macro(BTN_R3,K_J,0,0,false);held.entry.flags=2;
 macro_set_entry(0,held);enable_only(1);btn_r3(true);step(10);assert(key_down_now(K_J));
 g_ep_ready=false;macro_reset();g_ep_ready=true;macro_task();assert(last_report_blank());
 // Burst playback has no hold-set history: retries must survive repeated resets.
 fresh_device();macro_set_entry(0,chord_macro(BTN_R3,K_J,0,0,false));enable_only(1);
 btn_r3(true);step(10);assert(key_down_now(K_J));
 g_ep_ready=false;macro_reset();for(int i=0;i<4;++i)macro_task();macro_reset();
 assert(key_down_now(K_J));g_ep_ready=true;macro_task();assert(last_report_blank());
 // Reset must also discard analog trigger outputs without another input report.
 fresh_device();auto analog=hold_macro(BTN_L2,0,true);analog.entry.out_btn=T2BTN_R2;
 macro_set_entry(0,analog);enable_only(1);rpt[RPT_L2_AXIS]=90;btn_l2(true);step(10);
 assert(macro_analog_out(true)==90);macro_reset();
 assert(!macro_analog_out(false)&&!macro_analog_out(true)&&!macro_report_active());
 // Shortcut key-down/key-up cannot be overwritten by queued or held macros.
 fresh_device();macro_set_entry(0,chord_macro(BTN_R3,K_J,0,0,false));enable_only(1);
 g_ps_owns_stub=true;btn_r3(true);step(10);assert(g_sent_n==0&&macro_busy());
 g_ps_owns_stub=false;macro_task();assert(key_down_now(K_J));settle();
 fresh_device();macro_set_entry(0,held);enable_only(1);g_ps_owns_stub=true;
 btn_r3(true);step(10);assert(g_sent_n==0&&macro_busy());
 g_ps_owns_stub=false;macro_task();assert(key_down_now(K_J));
 // Swipe suppression does not wait for a swipe, and obeys profile/layer/suspend.
 fresh_device();auto swipe=output(0,T2BTN_CROSS,MACRO_FLAG_REPLACE);
 swipe.entry.gesture=0x80;macro_set_entry(0,swipe);enable_only(1);step(10);
 assert(macro_suppress_mask()&BTN_TOUCHPAD);
 g_cfg.macro_disable=0xffffffffu;step(10);assert(!(macro_suppress_mask()&BTN_TOUCHPAD));
 g_cfg.macro_disable=~1u;macro_suspend(true);step(10);assert(!macro_suppress_mask());macro_suspend(false);
 fresh_device();macro_set_entry(0,output(BTN_MUTE,MACRO_SHIFT_KEY,MACRO_FLAG_HOLD));
 swipe.entry.flags|=MACRO_FLAG_SHIFT;macro_set_entry(1,swipe);enable_only(3);step(10);
 assert(!(macro_suppress_mask()&BTN_TOUCHPAD));rpt[RPT_BTN2]|=4;step(80);
 assert(macro_suppress_mask()&BTN_TOUCHPAD);rpt[RPT_BTN2]&=~4;tick(80);
 assert(!(macro_suppress_mask()&BTN_TOUCHPAD));
 // Swipes suppress the game report while physical clicks still run Pico mappings.
 for (const uint32_t click : {BTN_TOUCHPAD, BTN_PAD_CLICK_LEFT, BTN_PAD_CLICK_RIGHT}) {
     fresh_device();
     swipe.entry.flags = MACRO_FLAG_REPLACE;
     assert(macro_set_entry(0,swipe));
     assert(macro_set_entry(1,output(click,T2BTN_CIRCLE,MACRO_FLAG_HOLD)));
     enable_only(3);
     touch(true,click == BTN_PAD_CLICK_RIGHT ? 1500 : 200,300);step(10);
     rpt[RPT_BTN2]|=2;step(10);
     assert(macro_suppress_mask()&BTN_TOUCHPAD);
     assert(macro_inject_mask()&(1u<<(T2BTN_CIRCLE-1)));
 }
 // Cue finishes, starts/stops at zero, does not overrun, and handles timer wrap.
 ProfileChime cue;cue.start(0xfffffff0,1000);assert(cue.active(20));assert(cue.next()==0);
 for(int i=0;i<4000;++i){float x=cue.next();assert(x>=-.061f&&x<=.061f);}
 assert(cue.next()==0);assert(!cue.active(100));
 puts("PASS: shift inheritance/suspend, profile debounce/timer-wrap/pad guard, repeated key-up retry, analog reset, storage and cue bounds");
}
'''.replace('ORIGINAL',(root/'tools/macro-tests/macro-tests.cpp').as_posix())
(out/'test.cpp').write_text(source,encoding='utf-8')
bin_dir=root.parent/'DS5Dongle-Studio-build/source/toolchain/mingw64/mingw64/bin'
env=dict(os.environ);env['PATH']=str(bin_dir)+os.pathsep+env.get('PATH','')
subprocess.run([str(bin_dir/'g++.exe'),'-std=c++17','-DENABLE_WAKE_HID','-I'+str(root/'src'),'-I'+str(stubs),str(out/'test.cpp'),str(stubs/'macro.cpp'),'-o',str(out/'test.exe')],env=env,check=True)
result=subprocess.run([str(out/'test.exe')],env=env,capture_output=True,text=True)
(out/'result.txt').write_text(result.stdout+result.stderr,encoding='utf-8')
print('\n'.join((result.stdout+result.stderr).splitlines()[-12:]));result.check_returncode()
