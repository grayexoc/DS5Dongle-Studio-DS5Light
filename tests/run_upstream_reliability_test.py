"""Exercise extracted production paths with mocked hardware; syntax only on ARM."""
from pathlib import Path
import json, os, re, subprocess, sys
root=Path(__file__).resolve().parents[1]
base=Path(os.environ.get('DS5_FIRMWARE_TOOLS',root.parent/'DS5Dongle-Studio-build'))
out=base/'reports/upstream-reliability-tests';out.mkdir(parents=True,exist_ok=True)
main=(root/'src/main.cpp').read_text(encoding='utf-8')
bt=(root/'src/bt.cpp').read_text(encoding='utf-8')
callback=main[main.index('void tud_hid_set_report_cb('):main.index('// Scratch 0 is shared')]
auth=bt[bt.index('        case HCI_EVENT_AUTHENTICATION_COMPLETE:'):bt.index('        case HCI_EVENT_ENCRYPTION_CHANGE:')]
link_key=bt[bt.index('        case HCI_EVENT_LINK_KEY_REQUEST:'):bt.index('        case HCI_EVENT_USER_CONFIRMATION_REQUEST:')]
start=main.index('static constexpr uint32_t kCyw43RetryTag')
failure=main[start:main.index('\nint main()',start)]
usb_wait=bt[bt.index('bool bt_usb_features_pending() {'):bt.index('\n#else\nbool bt_usb_features_pending()')]
cmd=(root/'src/cmd.cpp').read_text(encoding='utf-8')
disconnect=bt[bt.index('bool bt_disconnect()'):bt.index('bool bt_is_connected()')]
control_start=bt.index('            if (packet[0] == 0xA3 && size < 2)')
control=bt[control_start:bt.index('            dse_on_control_packet',control_start)]
wake=(root/'src/wake.cpp').read_text(encoding='utf-8')
wake_reset=wake[wake.index('void wake_on_bt_disconnect('):wake.index('void wake_task(')]
neutral_start=main.index('uint8_t interrupt_in_data[63]')
neutral=main[neutral_start:main.index('critical_section_t report_cs',neutral_start)]
reset_start=main.index('void controller_input_on_disconnect(')
input_reset=main[reset_start:main.index('// Invoked when received GET_REPORT',reset_start)]
get_start=main.index('uint16_t tud_hid_get_report_cb(')
get_report=main[get_start:main.index('bool tud_audio_set_itf_cb(',get_start)]
reply_start=cmd.index('static void pico_cmd_reply_read(')
reply=cmd[reply_start:cmd.index('void pico_cmd_set(',reply_start)]
code=r'''
#include <algorithm>
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <map>
#include <vector>
using hid_report_type_t=int;
constexpr int HID_REPORT_TYPE_OUTPUT=2, HID_REPORT_TYPE_FEATURE=3;
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
constexpr int HCI_CON_HANDLE_INVALID=0xffff, GAP_CONNECTION_ACL=1, ERROR_CODE_COMMAND_DISALLOWED=12;
int connection_type=GAP_CONNECTION_ACL, disconnect_status=ERROR_CODE_SUCCESS;
int gap_get_connection_type(uint16_t){return connection_type;}
int gap_disconnect(uint16_t handle){assert(handle==acl_handle);++disconnects;return disconnect_status;}
void manual_power_note_activity() {++graces;}
void gap_inquiry_start(int n) {assert(n==30);++searches;}
void hci_send_cmd(int*,uint16_t,int) {++encrypts;}
using bd_addr_t=uint8_t[6];
using link_key_t=uint8_t[16];
using link_key_type_t=uint8_t;
constexpr int HCI_EVENT_LINK_KEY_REQUEST=5;
int hci_link_key_request_reply, hci_link_key_request_negative_reply;
bool key_available=true;
int positive_key_replies=0, negative_key_replies=0, key_logs=0;
void hci_event_link_key_request_get_bd_addr(uint8_t *packet,uint8_t *addr) {
 memcpy(addr,packet,sizeof(bd_addr_t));
}
bool gap_get_link_key_for_bd_addr(uint8_t*,uint8_t *key,link_key_type_t *type) {
 if (!key_available) return false;
 memset(key,0xa5,sizeof(link_key_t));
 *type=4;
 return true;
}
void hci_send_cmd(int *cmd,uint8_t*,uint8_t *key) {
 assert(cmd==&hci_link_key_request_reply);
 for (unsigned i=0;i<sizeof(link_key_t);++i) assert(key[i]==0xa5);
 ++positive_key_replies;
}
void hci_send_cmd(int *cmd,uint8_t*) {
 assert(cmd==&hci_link_key_request_negative_reply);
 ++negative_key_replies;
}
void link_key_log(const char *format,...) {
 const char *expected=key_available ? "[HCI] Link key request from %s, reply stored key type=%u\n"
                                    : "[HCI] Link key request from %s, no key, force re-pair\n";
 assert(strcmp(format,expected)==0);
 ++key_logs;
}
int init_error=0,slept=0,reboots=0;
bool halt_probe=false;
int cyw43_arch_init() {return init_error;}
void sleep_ms(int n) {slept+=n;if(halt_probe)throw 2;}
bool watchdog_reset=false;
struct Watchdog { uint32_t scratch[8]{}; } watchdog;
auto* watchdog_hw=&watchdog;
bool watchdog_caused_reboot(){return watchdog_reset;}
void watchdog_reboot(int a,int b,int c) {assert(!a&&!b&&!c);++reboots;watchdog_reset=true;throw 1;}
void tight_loop_contents() {assert(false);}
static constexpr uint32_t usb_feature_wait_ms = 120;
uint32_t usb_feature_started_ms=0;
bool usb_identity_pending=false, link_connected=true, suspended=false, host_suspended=false;
int restored=0;
std::map<uint8_t, std::vector<uint8_t>> feature_data;
bool bt_is_connected(){return link_connected;}
bool channels_open=true,check_dse=false,is_dse=false;
bool bt_is_ready(){return link_connected&&channels_open;}
bool macro_power_off_pending=false,control_full=false;
constexpr uint32_t kControlRetryMs=40;
int control_fifo=0, power_offs=0, usb_queries=0;
bool queue_is_full(int*){return control_full;}
void bt_power_off_controller(){++power_offs;}
std::vector<uint8_t> get_feature_data(uint8_t id,uint16_t){
 ++usb_queries;
 const auto report=feature_data.find(id);
 return report==feature_data.end()?std::vector<uint8_t>{}:report->second;
}
int edge_unlocks=0,sleep_acks=0;
void dse_on_connect(){++edge_unlocks;}
bool dse_is_profile_report(uint8_t id){return id>=0x70&&id<=0x7b;}
bool dse_profiles_ready(){return true;}
int usb_profile_event_get(uint8_t*,uint16_t){return 0;}
std::vector<uint8_t> pico_portal_reply,pico_settings_reply;
void manual_power_sleep_reply_read(){++sleep_acks;}
int report_cs=0,wake_cs=0, ps_resets=0, macro_resets=0, mouse_resets=0, flick_resets=0;
void critical_section_enter_blocking(int *cs){assert(*cs==0);++*cs;}
void critical_section_exit(int *cs){assert(*cs==1);--*cs;}
void ps_shortcut_reset(){++ps_resets;}
void macro_reset(){++macro_resets;}
void gyro_mouse_reset(){++mouse_resets;}
void flick_stick_reset(){++flick_resets;}
bool report_dirty=false,g_tm_down=true,bt_link_up=true;
uint8_t prev_b7=1,prev_b8=2,prev_b9=3;
uint8_t g_sm_stick_x=0,g_sm_stick_y=255;
volatile uint8_t g_l2_pos=255,g_r2_pos=255,g_l1_btn=1,g_r1_btn=1;
struct T2State { bool latched=false; } l2_st{true},r2_st{true};
enum {WAKE_IDLE,WAKE_PENDING_PRESS,WAKE_REQUESTED,WAKE_KEY_DOWN,WAKE_KEY_UP_SENT} state=WAKE_KEY_DOWN;
bool wake_owns_keyboard();
#define ENABLE_SERIAL 0
bool tud_suspended(){return suspended;}
bool wake_host_is_suspended(){return host_suspended;}
void restore_full_usb_identity(){++restored;}
'''
code+=usb_wait+'\n'+disconnect+'\n'+reply+'\n'+get_report+'\n'+neutral+input_reset+wake_reset
code+='void receive_control(uint8_t *packet,uint16_t size) {\n'+control+'}\n'
start=bt.index('void bt_macro_power_off_task(bool requested)')
end=bt.index('\n}',bt.index('void init_feature()',start))+2
code+=bt[start:end]+'\n'
code+=callback+'\nvoid auth(uint8_t *packet) {switch(6) {\n'+auth+'}}\n'
code+='\n#define printf link_key_log\nvoid request_link_key(uint8_t *packet) {switch(HCI_EVENT_LINK_KEY_REQUEST) {\n'+link_key+'}}\n#undef printf\n'
code+=failure+'\n'
code+=r'''
int main() {
 uint8_t address[6]{};
 request_link_key(address);
 assert(positive_key_replies==1&&negative_key_replies==0&&key_logs==1);
 key_available=false;
 request_link_key(address);
 assert(positive_key_replies==1&&negative_key_replies==1&&key_logs==2);
 puts("PASS: link key reply and rejection preserve HCI behavior without dumping keys");
 usb_identity_pending=true;
 usb_feature_started_ms=0xfffffff0u;now=3;
 feature_data[0x05].resize(41);feature_data[0x09].resize(20);feature_data[0x20].resize(63);
 bt_usb_identity_task();assert(usb_identity_pending&&!restored);
 feature_data[0x20].resize(64);host_suspended=true;
 bt_usb_identity_task();assert(!restored);
 host_suspended=false;bt_usb_identity_task();bt_usb_identity_task();
 assert(restored==1&&!usb_identity_pending);
 now=0;
 is_dse=true;
 init_feature();assert(usb_identity_pending&&check_dse&&!is_dse&&usb_queries==5);
 feature_data[0x05].resize(41);feature_data[0x09].resize(20);feature_data[0x20].resize(64);
 now=119;
 bt_usb_identity_task();assert(restored==1&&usb_identity_pending);
 now=120;channels_open=false;bt_usb_identity_task();assert(restored==1);
 channels_open=true;bt_usb_identity_task();assert(restored==2&&!usb_identity_pending);
 config.usb_gamepad_mode=1;usb_identity_pending=true;now=0;
 bt_usb_identity_task();assert(restored==3&&!usb_identity_pending);
 config.usb_gamepad_mode=0;
 now=0;control_full=true;bt_macro_power_off_task(true);
 assert(macro_power_off_pending&&power_offs==0);
 now=20;control_full=false;bt_macro_power_off_task(false);bt_macro_power_off_task(false);
 assert(!macro_power_off_pending&&power_offs==1);
 now=0xfffffff0u;control_full=true;bt_macro_power_off_task(true);
 now+=40;control_full=false;bt_macro_power_off_task(false);
 assert(!macro_power_off_pending&&power_offs==1);
 control_full=true;bt_macro_power_off_task(true);link_connected=false;
 bt_macro_power_off_task(false);link_connected=true;control_full=false;bt_macro_power_off_task(false);
 assert(!macro_power_off_pending&&power_offs==1);
 bt_macro_power_off_task(true);assert(power_offs==2);
 now=0;
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
 const int prior_disconnects=disconnects;
 connection_type=0;
 assert(!bt_disconnect()&&disconnects==prior_disconnects);
 connection_type=GAP_CONNECTION_ACL;
 assert(bt_disconnect()&&disconnects==prior_disconnects+1);
 disconnect_status=ERROR_CODE_COMMAND_DISALLOWED; // already queued in BTstack
 assert(bt_disconnect());
 disconnect_status=1;assert(!bt_disconnect());

 init_feature();
 uint8_t handshake[]={0x02}, short_edge[]={0xa3,0x70}, edge[]={0xa3,0x70,0x52};
 receive_control(handshake,sizeof(handshake));
 receive_control(short_edge,sizeof(short_edge));
 assert(check_dse&&!is_dse&&edge_unlocks==0);
 now+=120;bt_usb_identity_task();assert(!usb_identity_pending);
 receive_control(edge,sizeof(edge));receive_control(edge,sizeof(edge));
 assert(!check_dse&&is_dse&&edge_unlocks==1&&usb_identity_pending);

 uint8_t native[]={0xa3,0x81,0xaa}, usb_reply[63]{};
 pico_portal_reply={0x66,0x04,0x01};
 receive_control(native,sizeof(native));
 const int prior_queries=usb_queries;
 assert(get_feature_data(0x81,63)[1]==0xaa); // Edge's internal poll
 assert(tud_hid_get_report_cb(0,0x81,3,usb_reply,63)==3&&usb_reply[0]==0x66);
 assert(usb_queries==prior_queries+1); // the local read doesn't poll Bluetooth
 assert(tud_hid_get_report_cb(0,0x81,3,usb_reply,63)==1&&usb_reply[0]==0xaa);
 pico_settings_reply={0x66,0x1b,0,1,1,0,0,0};
 uint8_t native_settings[]={0xa3,0x84,0xbb};
 receive_control(native_settings,sizeof(native_settings));
 assert(tud_hid_get_report_cb(0,0x84,3,usb_reply,2)==2&&!sleep_acks);
 assert(tud_hid_get_report_cb(0,0x84,3,usb_reply,63)==8&&sleep_acks==1);

 memset(interrupt_in_data,255,sizeof(interrupt_in_data));
 controller_input_on_disconnect();
 assert(report_dirty&&!report_cs&&!l2_st.latched&&!r2_st.latched);
 assert(interrupt_in_data[0]==128&&interrupt_in_data[7]==8&&interrupt_in_data[8]==0);
 assert(interrupt_in_data[32]==0x80&&interrupt_in_data[36]==0x80);
 assert(!g_l2_pos&&!g_r2_pos&&!g_l1_btn&&!g_r1_btn&&!g_tm_down);
 assert(g_sm_stick_x==128&&g_sm_stick_y==128&&mouse_resets==1&&flick_resets==1);
 wake_on_bt_disconnect();
 assert(!bt_link_up&&state==WAKE_KEY_DOWN&&wake_owns_keyboard());
 assert(prev_b7==8&&!prev_b8&&!prev_b9&&ps_resets==1&&macro_resets==1);
 state=WAKE_PENDING_PRESS;
 wake_on_bt_disconnect();assert(state==WAKE_IDLE&&!wake_owns_keyboard());

 watchdog.scratch[0]=kCyw43RetryTag|3;assert(cyw43_boot_retries()==0);
 watchdog_reset=true;watchdog.scratch[0]=0x4d505752;assert(cyw43_boot_retries()==0);
 initialize_cyw43(0);assert(!slept&&!reboots);
 init_error=-1;
 for (uint32_t i=0;i<kCyw43RetryLimit;++i) {
   uint32_t retries=cyw43_boot_retries();watchdog.scratch[0]=0;
   assert(retries==i);slept=0;
   try {initialize_cyw43(retries);assert(false);}catch(int e) {assert(e==1);}
   assert(slept==int(500u<<i)&&reboots==int(i+1));
 }
 assert(cyw43_boot_retries()==kCyw43RetryLimit);
 watchdog.scratch[0]=0;halt_probe=true;slept=0;
 try {initialize_cyw43(kCyw43RetryLimit);assert(false);}catch(int e) {assert(e==2);}
 assert(slept==1000&&reboots==int(kCyw43RetryLimit)&&!watchdog.scratch[0]);
 halt_probe=false;init_error=0;slept=0;
 initialize_cyw43(kCyw43RetryLimit);assert(!slept&&!cyw43_boot_retries());
 puts("PASS: USB paths, USB restore on missing detection response, bounded macro power-off retry, suspend and XInput gates, Edge detection, Pico reply isolation, GAP disconnect, neutral input, wake key release, auth and boot recovery");
}
'''
(out/'test.cpp').write_text(code,encoding='utf-8')
bin_dir=base/'source/toolchain/mingw64/mingw64/bin'
env=dict(os.environ);env['PATH']=str(bin_dir)+os.pathsep+env.get('PATH','')
subprocess.run([str(bin_dir/'g++.exe'),'-std=c++17',str(out/'test.cpp'),'-o',str(out/'test.exe')],env=env,check=True)
p=subprocess.run([str(out/'test.exe')],env=env,check=True,capture_output=True,text=True)
(out/'result.txt').write_text(p.stdout,encoding='utf-8');print(p.stdout)
if '--host-only' in sys.argv:sys.exit(0)
from test_support import firmware_build
build=firmware_build(root)
entries=json.loads((build/'compile_commands.json').read_text())
with (out/'syntax.txt').open('w',encoding='utf-8') as log:
 for name in ('main.cpp','bt.cpp','wake.cpp','macro.cpp','audio.cpp','cmd.cpp','config.cpp','manual_power.cpp','dse.cpp'):
  entry=next(e for e in entries if Path(e['file']).name==name)
  command,n=re.subn(r' -o \S+ -c ',' -fsyntax-only ',entry['command']);assert n==1
  command=command.replace(entry['file'],str(root/'src'/name))
  subprocess.run(command,cwd=entry['directory'],stdout=log,stderr=log,check=True)
print('PASS: ARM syntax checks for changed firmware sources; no firmware build')
