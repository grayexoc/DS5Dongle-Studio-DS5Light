"""Exercise extracted production paths with mocked hardware; syntax only on ARM."""
from pathlib import Path
import json, os, re, subprocess
root=Path(__file__).resolve().parents[1]
base=root.parent/'DS5Dongle-Studio-build'
out=base/'reports/upstream-reliability-tests';out.mkdir(parents=True,exist_ok=True)
main=(root/'src/main.cpp').read_text(encoding='utf-8')
bt=(root/'src/bt.cpp').read_text(encoding='utf-8')
callback=main[main.index('void tud_hid_set_report_cb('):main.index('\nint main()')]
auth=bt[bt.index('        case HCI_EVENT_AUTHENTICATION_COMPLETE:'):bt.index('        case HCI_EVENT_ENCRYPTION_CHANGE:')]
start=main.index('    if (cyw43_arch_init()) {')
failure=main[start:main.index('\n    cyw43_arch_gpio_put',start)]
usb_wait=bt[bt.index('bool bt_usb_features_pending() {'):bt.index('\n#else\nbool bt_usb_features_pending()')]
code=r'''
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <map>
#include <vector>
#define STUDIO_XINPUT_EXPERIMENT
using hid_report_type_t=int;
constexpr int HID_REPORT_TYPE_OUTPUT=2;
struct SetStateData { uint8_t data[63]; };
int reportSeqCounter=0, sends=0, updates=0, commands=0, features=0, state_sets=0;
bool spk_active=false, changed=true;
uint32_t now=0;
uint32_t get_absolute_time(){return now;}
uint32_t to_ms_since_boot(uint32_t x){return x;}
bool state_rumble_wants_report(const uint8_t*){return false;}
struct Config { int auto_haptics_enable=1; int usb_gamepad_mode=0; } config;
Config &get_config() {return config;}
uint8_t captured[63]{}, sent[78]{};
bool state_update(const uint8_t *p,uint8_t n) { ++updates; memset(captured,0,63);memcpy(captured,p,n);return changed; }
void state_set(uint8_t *p,uint8_t n) {++state_sets;memcpy(p,captured,n);}
void bt_write(uint8_t *p,uint16_t n) {assert(n==78);++sends;memcpy(sent,p,n);}
void pico_cmd_set(uint8_t,const uint8_t*,uint16_t) {++commands;}
void set_feature_data(uint8_t,uint8_t*,uint16_t) {++features;}
using hci_con_handle_t=uint16_t;
constexpr int HCI_EVENT_AUTHENTICATION_COMPLETE=6, ERROR_CODE_SUCCESS=0;
constexpr int ERROR_CODE_AUTHENTICATION_FAILURE=5, ERROR_CODE_PIN_OR_KEY_MISSING=6;
uint16_t acl_handle=7;bool link_encrypted=true;
uint8_t current_device_addr[6]{};
int drops=0,disconnects=0,searches=0,graces=0,encrypts=0;
int hci_set_connection_encryption;
uint8_t hci_event_authentication_complete_get_status(uint8_t *p) {return p[0];}
uint16_t hci_event_authentication_complete_get_connection_handle(uint8_t *p) {return p[1];}
const char *bd_addr_to_str(uint8_t*) {return "mock";}
void gap_drop_link_key_for_bd_addr(uint8_t*) {++drops;}
void bt_disconnect() {++disconnects;}
void manual_power_note_activity() {++graces;}
void gap_inquiry_start(int n) {assert(n==30);++searches;}
void hci_send_cmd(int*,uint16_t,int) {++encrypts;}
int init_error=0,slept=0,reboots=0;
int cyw43_arch_init() {return init_error;}
void sleep_ms(int n) {slept+=n;}
void watchdog_reboot(int a,int b,int c) {assert(!a&&!b&&!c);++reboots;throw 1;}
void tight_loop_contents() {assert(false);}
static constexpr uint32_t usb_feature_wait_ms = 120;
uint32_t usb_feature_started_ms=0;
bool usb_identity_pending=false, link_connected=true, suspended=false, host_suspended=false;
int restored=0;
std::map<uint8_t, std::vector<uint8_t>> feature_data;
bool bt_is_connected(){return link_connected;}
bool tud_suspended(){return suspended;}
bool wake_host_is_suspended(){return host_suspended;}
void restore_full_usb_identity(){++restored;}
'''
code+=usb_wait+'\n'
code+=callback+'\nvoid auth(uint8_t *packet) {switch(6) {\n'+auth+'}}\n'
code+='void boot() {\n'+failure+'\n}\n'
code+=r'''
int main() {
 usb_identity_pending=true;
 usb_feature_started_ms=0xfffffff0u;now=3;
 feature_data[0x05].resize(41);feature_data[0x09].resize(20);feature_data[0x20].resize(63);
 bt_usb_identity_task();assert(usb_identity_pending&&!restored);
 feature_data[0x20].resize(64);host_suspended=true;
 bt_usb_identity_task();assert(!restored);
 host_suspended=false;bt_usb_identity_task();bt_usb_identity_task();
 assert(restored==1&&!usb_identity_pending);
 feature_data.clear();usb_identity_pending=true;usb_feature_started_ms=0;now=119;
 bt_usb_identity_task();assert(restored==1&&usb_identity_pending);
 now=120;link_connected=false;bt_usb_identity_task();assert(restored==1);
 link_connected=true;bt_usb_identity_task();assert(restored==2&&!usb_identity_pending);
 config.usb_gamepad_mode=1;usb_identity_pending=true;now=0;
 bt_usb_identity_task();assert(restored==3&&!usb_identity_pending);
 config.usb_gamepad_mode=0;now=0;
 uint8_t p[65]{};p[0]=2;for(int i=1;i<64;++i)p[i]=i;
 tud_hid_set_report_cb(0,0,0,p,64);assert(sends==1&&updates==1);
 uint8_t first[63];memcpy(first,sent+3,63);
 tud_hid_set_report_cb(0,2,2,p+1,63);assert(sends==2&&!memcmp(first,sent+3,63));
 tud_hid_set_report_cb(0,2,2,p+1,1);assert(sends==3&&captured[0]==1&&captured[1]==0);
 tud_hid_set_report_cb(0,2,2,nullptr,1);
 tud_hid_set_report_cb(0,2,2,p,0);
 tud_hid_set_report_cb(0,0,0,p,1);
 tud_hid_set_report_cb(0,0,0,p,65);
 tud_hid_set_report_cb(0,2,2,p,64);
 tud_hid_set_report_cb(0,2,3,p,63);assert(sends==3);
 spk_active=true;changed=false;state_sets=0;
 tud_hid_set_report_cb(0,2,2,p,63);assert(sends==3&&state_sets==1);
 changed=true;state_sets=0;
 tud_hid_set_report_cb(0,2,2,p,63);assert(sends==4&&state_sets==1);
 config.auto_haptics_enable=0;changed=false;
 tud_hid_set_report_cb(0,2,2,p,63);assert(sends==4); // unchanged ordinary state suppressed
 p[0]=0x0c;now=8;
 tud_hid_set_report_cb(0,2,2,p,63);assert(sends==5);
 now=9;tud_hid_set_report_cb(0,2,2,p,63);assert(sends==5);
 now=16;tud_hid_set_report_cb(0,2,2,p,63);assert(sends==6);
 uint8_t cmd[]={0x66,1};tud_hid_set_report_cb(0,0x80,3,cmd,2);assert(commands==1);
 tud_hid_set_report_cb(0,0x60,3,p,2);assert(features==1);
 uint8_t event[]={8,7};auth(event);assert(!drops&&disconnects==1&&searches==1&&graces==1&&!link_encrypted);
 event[0]=5;auth(event);event[0]=6;auth(event);assert(drops==2&&searches==3);
 event[0]=0;auth(event);assert(encrypts==1&&disconnects==3);
 event[1]=8;event[0]=5;auth(event);assert(drops==2&&disconnects==3);
 boot();assert(!slept&&!reboots);init_error=1;try {boot();assert(false);}catch(int) {}
 assert(slept==500&&reboots==1);
 puts("PASS: USB paths, bounded initial feature wait, suspend and XInput gates, feature routing, auth and boot recovery");
}
'''
(out/'test.cpp').write_text(code,encoding='utf-8')
bin_dir=base/'source/toolchain/mingw64/mingw64/bin'
env=dict(os.environ);env['PATH']=str(bin_dir)+os.pathsep+env.get('PATH','')
subprocess.run([str(bin_dir/'g++.exe'),'-std=c++17',str(out/'test.cpp'),'-o',str(out/'test.exe')],env=env,check=True)
p=subprocess.run([str(out/'test.exe')],env=env,check=True,capture_output=True,text=True)
(out/'result.txt').write_text(p.stdout,encoding='utf-8');print(p.stdout)
from test_support import firmware_build
build=firmware_build(root)
entries=json.loads((build/'compile_commands.json').read_text())
with (out/'syntax.txt').open('w',encoding='utf-8') as log:
 for name in ('main.cpp','bt.cpp','wake.cpp','macro.cpp','audio.cpp','cmd.cpp'):
  entry=next(e for e in entries if Path(e['file']).name==name)
  command,n=re.subn(r' -o \S+ -c ',' -fsyntax-only ',entry['command']);assert n==1
  command=command.replace(entry['file'],str(root/'src'/name))
  subprocess.run(command,cwd=entry['directory'],stdout=log,stderr=log,check=True)
print('PASS: ARM syntax checks for changed firmware sources; no firmware build')
