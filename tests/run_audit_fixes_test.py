"""Compile extracted production paths with host hardware mocks; no firmware build."""
from pathlib import Path
import os, subprocess, re
root=Path(__file__).resolve().parents[1]
base=Path(os.environ.get('DS5_FIRMWARE_TOOLS',root.parent/'DS5Dongle-Studio-build'))
out=base/'reports/audit-fixes';out.mkdir(parents=True,exist_ok=True)
bin=base/'source/toolchain/mingw64/mingw64/bin'
env=dict(os.environ);env['PATH']=str(bin)+os.pathsep+env.get('PATH','')
def extract(s,signature):
 start=s.index(signature);return s[start:s.index('\n}',start)+2]
def run(name,code):
 cpp=out/(name+'.cpp');cpp.write_text(code,encoding='utf-8')
 subprocess.run([str(bin/'g++.exe'),'-std=c++17','-I'+str(root/'src'),str(cpp),'-o',str(out/(name+'.exe'))],env=env,check=True)
 p=subprocess.run([str(out/(name+'.exe'))],env=env,capture_output=True,text=True)
 (out/(name+'.txt')).write_text(p.stdout+p.stderr);print(name,p.stdout+p.stderr);p.check_returncode()

s=(root/'src/storage_redo.cpp').read_text(encoding='utf-8')
s=re.sub(r'^#include.*\n','',s,flags=re.M)
s=s.replace('    extern const uint8_t __flash_binary_end[];','')
s=s.replace('reinterpret_cast<uintptr_t>(__flash_binary_end)','XIP_BASE')
run('storage',r"""
#include <cstdint>
#include <cstring>
#include <cassert>
#include <cstdio>
constexpr unsigned FLASH_SECTOR_SIZE=4096,FLASH_PAGE_SIZE=256;
constexpr unsigned SLOT_COUNT=16,SLOTS_PER_SECTOR=8;
constexpr unsigned MACRO_FLASH_OFFSET=8192,STORAGE_REDO_DATA=12288,STORAGE_REDO_META=16384;
uint32_t slot_sector_offset_at(unsigned i){return i*4096;}
uint8_t flashmem[20480];
#define XIP_BASE reinterpret_cast<uintptr_t>(flashmem)
int operation=0,cut=0;
unsigned meta_erases=0;
uint32_t blocked_program=UINT32_MAX;
uint32_t crc32(const uint8_t*p,unsigned n){uint32_t c=~0u;while(n--){c^=*p++;for(int i=0;i<8;i++)c=(c>>1)^(0xedb88320u&-(c&1));}return ~c;}
void step(){if(++operation==cut)throw 1;}
void flash_range_erase(uint32_t off,uint32_t n){if(off==STORAGE_REDO_META)++meta_erases;for(unsigned i=0;i<n;i+=256){memset(flashmem+off+i,255,256);step();}}
void flash_range_program(uint32_t off,const uint8_t*p,uint32_t n){if(off==blocked_program)return;for(unsigned i=0;i<n;i+=4){for(unsigned j=0;j<4;j++)flashmem[off+i+j]&=p[i+j];step();}}
"""+s+r"""
int main(){
 uint8_t before[20480],old[4096],fresh[4096];
 memset(flashmem,255,sizeof flashmem);memset(old,0x12,sizeof old);memset(fresh,0x34,sizeof fresh);
 memcpy(flashmem,old,4096);memcpy(flashmem+4096,old,4096);memcpy(before,flashmem,sizeof before);
 assert(storage_redo_write(0,fresh,4096));int total=operation;assert(meta_erases==1);
 assert(storage_redo_write(0,fresh,4096)&&meta_erases==1&&operation==total);
 // An incomplete header may have programmed bits anywhere on the metadata page.
 memcpy(flashmem,before,sizeof before);flashmem[STORAGE_REDO_META+FLASH_PAGE_SIZE-1]=0;
 meta_erases=0;assert(storage_redo_write(0,fresh,4096)&&meta_erases==2);
 for(int at=1;at<=total;at++){
  memcpy(flashmem,before,sizeof before);operation=0;cut=at;
  try{storage_redo_write(0,fresh,4096);}catch(int){}
  cut=0;assert(storage_redo_recover());assert(storage_redo_recover());
  assert(!memcmp(flashmem,old,4096)||!memcmp(flashmem,fresh,4096));
  assert(!memcmp(flashmem+4096,old,4096));
 }
 // Power can fail again during boot recovery. Keep the committed redo until verified.
 memcpy(flashmem,before,sizeof before);operation=0;
 cut=FLASH_SECTOR_SIZE/FLASH_PAGE_SIZE+FLASH_SECTOR_SIZE/4+FLASH_PAGE_SIZE/4;
 try{storage_redo_write(0,fresh,4096);}catch(int){}
 uint8_t pending[20480];memcpy(pending,flashmem,sizeof pending);
 cut=0;operation=0;assert(storage_redo_recover());int recovery_steps=operation;
 for(int at=1;at<=recovery_steps;at++){
  memcpy(flashmem,pending,sizeof pending);operation=0;cut=at;
  try{storage_redo_recover();}catch(int){}
  cut=0;assert(storage_redo_recover());assert(!memcmp(flashmem,fresh,4096));
 }
 printf("PASS: %d interrupted boot recoveries\n",recovery_steps);
 puts("PASS: one metadata erase on a clean save; a reused dirty page is erased first; no-op does not erase");
 // A corrupt committed redo must never write its target or permit another slot/macro write.
 memcpy(flashmem,pending,sizeof pending);flashmem[STORAGE_REDO_DATA]^=1;
 uint8_t damaged[20480];memcpy(damaged,flashmem,sizeof damaged);
 operation=0;assert(!storage_redo_recover());assert(recovery_blocked);
 assert(!storage_redo_write(4096,fresh,4096)&&!storage_redo_write(MACRO_FLASH_OFFSET,fresh,256));
 assert(operation==0&&!memcmp(damaged,flashmem,sizeof damaged));
 // A verified-looking header must not target any non-slot or non-macro sector.
 recovery_blocked=false;memcpy(flashmem,pending,sizeof pending);
 Header invalid{magic,STORAGE_REDO_META,crc32(flashmem+STORAGE_REDO_DATA,4096),0};
 invalid.header_checksum=crc32(reinterpret_cast<const uint8_t*>(&invalid),12);
 memcpy(flashmem+STORAGE_REDO_META,&invalid,sizeof invalid);memcpy(damaged,flashmem,sizeof damaged);
 assert(!storage_redo_recover()&&recovery_blocked&&!memcmp(damaged,flashmem,sizeof damaged));
 // If writing the target fails verification, keep both redo sections for a later boot.
 recovery_blocked=false;memcpy(flashmem,pending,sizeof pending);blocked_program=0;
 assert(!storage_redo_recover()&&recovery_blocked);
 assert(!memcmp(flashmem+STORAGE_REDO_DATA,pending+STORAGE_REDO_DATA,8192));
 blocked_program=UINT32_MAX;assert(!storage_redo_write(0,fresh,4096));
 recovery_blocked=false;assert(storage_redo_recover());assert(!memcmp(flashmem,fresh,4096));
 puts("PASS: corrupt redo and invalid target preserve all bytes; failed replay keeps redo until reboot");
 cut=0;assert(!storage_redo_write(STORAGE_REDO_META,fresh,4096));
 assert(storage_redo_write(MACRO_FLASH_OFFSET,fresh,256));
 assert(!memcmp(flashmem+MACRO_FLASH_OFFSET,fresh,256));
 for(int i=256;i<4096;i++)assert(flashmem[MACRO_FLASH_OFFSET+i]==255);
 printf("PASS: %d power cuts, old/new atomic sector, untouched neighbour, idempotent recovery, macro padding\n",total);
}
""")

s=(root/'src/bt.cpp').read_text(encoding='utf-8')
run('queue',r"""
#include <deque>
#include <cstring>
#include <cstdint>
#include <cassert>
#include <cstdio>
#define __not_in_flash_func(x) x
using uint=unsigned;
struct send_element{uint8_t data[512]{};size_t len=0;uint32_t enqueued_ms=0;bool lightbar_restore=false;bool native_audio=false;};
std::deque<send_element> send_fifo;
unsigned queue_get_level(std::deque<send_element>*q){return q->size();}
bool queue_is_full(std::deque<send_element>*q){return q->size()==10;}
unsigned queue_removals=0;
bool queue_try_remove(std::deque<send_element>*q,send_element*p){if(q->empty())return false;++queue_removals;*p=q->front();q->pop_front();return true;}
bool queue_try_add(std::deque<send_element>*q,send_element*p){if(q->size()==10)return false;q->push_back(*p);return true;}
uint32_t get_absolute_time(){return 100;}uint32_t to_ms_since_boot(uint32_t t){return t;}
struct {int auto_haptics_enable=0;}cfg;auto&get_config(){return cfg;}
int hid_interrupt_cid=1;
send_element pending_send;bool pending_send_valid=false;
bool state_report_is_lightbar_restore(const uint8_t*){return false;}
void fill_output_report_checksum(uint8_t*,uint16_t){}
void l2cap_request_can_send_now_event(int){}
"""+s[s.index("struct AudioTransportStats"):s.index("struct ControlSend")]+extract(s,'static const uint8_t *output_report_state(')+'\n'+extract(s,'void __not_in_flash_func(bt_write)')+'\n'+extract(s,'void bt_discard_audio()')+r"""
int main(){
 uint8_t control[78]{};control[0]=0x31;control[3]=0x0c;
 for(int i=0;i<1000;i++){control[1]=i;bt_write(control,78);}assert(send_fifo.size()==1);
 uint8_t audio[398]{};audio[0]=0x36;audio[12]=64;
 for(int i=0;i<1000;i++)bt_write(audio,398);
 assert(send_fifo.size()==8&&send_fifo.front().data[1]==0x31);
 pending_send.data[1]=0x36;pending_send_valid=true;bt_discard_audio();
 assert(!pending_send_valid&&send_fifo.size()==1&&send_fifo.front().data[1]==0x31);
 for(int i=0;i<7;i++)bt_write(audio,398);
 control[5]=123;bt_write(control,78);assert(send_fifo.size()==9);
 control[5]=0;bt_write(control,78);assert(send_fifo.size()==10); // A -> B -> A preserves intent
 assert(send_fifo.back().data[6]==0);
 send_element item;
 while(pop_send_fifo(item)){}
 assert(queued_controls==0&&native_queued==0);
 control[5]=120;bt_write(control,78);control[5]=0;bt_write(control,78);control[5]=120;bt_write(control,78);
 assert(send_fifo.size()==3);bt_write(control,78);assert(send_fifo.size()==3);
 while(pop_send_fifo(item)){}
 for(int i=0;i<10;i++){control[5]=i;bt_write(control,78);}
 assert(send_fifo.size()==10);bt_write(audio,398);assert(send_fifo.size()==10);
 while(pop_send_fifo(item)){}
 control[5]=20;bt_write(control,78);
 for(int i=0;i<7;i++)bt_write(audio,398);
 const auto removals=queue_removals;
 control[1]++;control[35]++;
 bt_write(control,78);assert(send_fifo.size()==8&&queue_removals==removals);
 assert(pop_send_fifo(pending_send)&&queued_controls==0);pending_send_valid=true;
 bt_write(control,78);assert(send_fifo.size()==8&&queued_controls==1);
 uint8_t short_control[12]{0x31};
 bt_write(short_control,12);
 bt_write(control,78);assert(send_fifo.size()==10&&queued_controls==3);
 control[5]=42;bt_write(control,78); // Evicts audio while available.
 assert(send_fifo.size()==10&&queued_controls==4);
 bt_discard_audio();assert(send_fifo.size()==4&&queued_controls==4);
 bt_write(control,78);assert(send_fifo.size()==4);
 for(int i=0;i<6;i++){control[5]=80+i;bt_write(control,78);}
 assert(queued_controls==10);
 control[5]=100;bt_write(control,78);assert(queued_controls==10); // Rejected, cache unchanged.
 assert(pop_send_fifo(item));assert(queued_controls==9);
 control[5]=85;bt_write(control,78);assert(send_fifo.size()==9);
 control[5]=100;bt_write(control,78);assert(send_fifo.size()==10);
 while(pop_send_fifo(item)){}
 assert(queued_controls==0);
 puts("PASS: actual bt_write: duplicate lookup without rotation, A-B-A order, retry isolation, short reports, audio eviction and full-queue rejection");
}
""")

s=(root/'src/audio.cpp').read_text(encoding='utf-8')
start=s.index('        const unsigned state_size = auto_mode == 0 ? 0 : 65;')
end=s.index('\n        bt_write(pkt, sizeof(pkt));',start)
run('packet',r"""
#include <cassert>
#include <cstring>
#include <cstdint>
#include <cstdio>
#include <atomic>
#include <initializer_list>
#define DISABLE_SPEAKER_PROC 0
constexpr unsigned SAMPLE_SIZE=64, speaker_payload_size=200;
uint8_t haptic_buf[SAMPLE_SIZE], opus_silence_buf[2][speaker_payload_size];
std::atomic<unsigned> opus_silence_mask{3};
bool have_frame=true;
void state_set(uint8_t *p,unsigned n){memset(p,0x55,n);}
bool take_speaker_frame(uint8_t *p){if(have_frame)memset(p,0x77,speaker_payload_size);return have_frame;}
int main(){
 memset(haptic_buf,0x33,sizeof(haptic_buf));
 memset(opus_silence_buf[0],0x11,speaker_payload_size);
 memset(opus_silence_buf[1],0x22,speaker_payload_size);
 for(int auto_mode=0;auto_mode<3;++auto_mode)
 for(bool speaker_enabled:{false,true})
 for(bool plug_headset:{false,true})
 for(bool buffered:{false,true}){
 uint8_t pkt[398]{};have_frame=buffered;
"""+s[start:end]+r"""
 const unsigned tag=auto_mode==0?11:76;
 if(auto_mode){assert(pkt[11]==0x90&&pkt[12]==63);for(unsigned i=13;i<76;++i)assert(pkt[i]==0x55);}
 assert(pkt[tag]==0x92&&pkt[tag+1]==SAMPLE_SIZE);
 for(unsigned i=0;i<SAMPLE_SIZE;++i)assert(pkt[tag+2+i]==0x33);
 unsigned last=tag+2+SAMPLE_SIZE;
 if(speaker_enabled){
   assert(pkt[last]==(plug_headset?0x96:0x93)&&pkt[last+1]==speaker_payload_size);
   for(unsigned i=0;i<speaker_payload_size;++i)assert(pkt[last+2+i]==(buffered?0x77:plug_headset?0x22:0x11));
   last+=2+speaker_payload_size;
 }
 for(unsigned i=last;i<sizeof(pkt);++i)assert(pkt[i]==0);
 }
 puts("PASS: production packet layout for Native/Mix/Replace, speaker/headset and silent frames");
}
""")

# Actual UAC set/get handlers, with control transfers captured in RAM.
s=(root/'src/usb.cpp').read_text(encoding='utf-8')
run('usb-controls',r"""
#include <cstdint>
#include <cstring>
#include <cassert>
#include <cstdio>
#include <algorithm>
#define TU_U16_LOW(x) ((x)&255)
#define TU_U16_HIGH(x) ((x)>>8)
#define TU_VERIFY(x) if(!(x)) return false
#define TU_LOG2(...)
#define TU_BREAKPOINT()
#define UAC1_ENTITY_SPK_FEATURE_UNIT 2
#define UAC1_ENTITY_MIC_FEATURE_UNIT 5
#define AUDIO10_FU_CTRL_MUTE 1
#define AUDIO10_FU_CTRL_VOLUME 2
#define AUDIO10_CS_REQ_SET_CUR 1
#define AUDIO10_CS_REQ_GET_CUR 0x81
#define AUDIO10_CS_REQ_GET_MIN 0x82
#define AUDIO10_CS_REQ_GET_MAX 0x83
#define AUDIO10_CS_REQ_GET_RES 0x84
struct tusb_control_request_t{uint16_t wValue,wIndex,wLength;uint8_t bRequest;};
struct Config{uint8_t speaker_volume=60,headset_volume=70,sync_spk_headset_volume=0,lock_volume=0;}cfg;
Config&get_config(){return cfg;}
uint8_t speaker=0,headset=0,mute[2]{};
float volume[2]{};uint8_t reply[8]{};
void set_volume(uint8_t s,uint8_t h){speaker=s;headset=h;}
bool tud_audio_buffer_and_schedule_control_xfer(uint8_t,const tusb_control_request_t*,const void*p,unsigned n){memcpy(reply,p,n);return true;}
"""+s[s.index('static constexpr int speaker_volume_span'):s.index('/*int main()')]+extract(s,'static bool audio10_set_req_entity(')+'\n'+extract(s,'static bool audio10_get_req_entity(')+r"""
int main(){
 tusb_control_request_t q{2<<8,2<<8,2,1};int16_t input=-20*256;
 assert(audio10_set_req_entity(&q,reinterpret_cast<uint8_t*>(&input)));
 assert(speaker==102&&headset==70&&cfg.speaker_volume==102);
 q.bRequest=0x81;assert(audio10_get_req_entity(0,&q));int16_t got;memcpy(&got,reply,2);assert(got==speaker_level_to_usb(102));
 cfg.lock_volume=1;cfg.sync_spk_headset_volume=1;input=0;q.bRequest=1;
 assert(audio10_set_req_entity(&q,reinterpret_cast<uint8_t*>(&input)));
 assert(speaker==102&&headset==70&&cfg.speaker_volume==102&&cfg.headset_volume==70);
 q.bRequest=0x81;assert(audio10_get_req_entity(0,&q));memcpy(&got,reply,2);assert(got==speaker_level_to_usb(102));
 cfg.lock_volume=0;
 cfg.sync_spk_headset_volume=1;input=-100*256;q.bRequest=1;
 assert(audio10_set_req_entity(&q,reinterpret_cast<uint8_t*>(&input)));assert(speaker==0&&headset==0);
 input=0;assert(audio10_set_req_entity(&q,reinterpret_cast<uint8_t*>(&input)));assert(speaker==127&&headset==127);
 assert(speaker_level_from_usb(-32768)==0&&speaker_level_from_usb(32767)==127);
 assert(speaker_level_from_usb(-12800)==64);
 for(int level=0;level<=127;++level)
  assert(speaker_level_from_usb(speaker_level_to_usb(level))==level);
 q.wLength=1;assert(!audio10_set_req_entity(&q,reinterpret_cast<uint8_t*>(&input)));
 q={1<<8,5<<8,1,1};uint8_t on=1;assert(audio10_set_req_entity(&q,&on));assert(mute[1]==1);
 puts("PASS: actual USB volume round trip, sync on/off, bounds, malformed length, mic mute command");
}
""")

s=(root/'src/usb_descriptors.cpp').read_text(encoding='utf-8')
a=s.index('            const char *str = nullptr;');b=s.index('            size_t const max_count',a)
run('usb-string',r"""
#include <cstdint>
#include <cstring>
#include <cassert>
#include <cstdio>
bool active=false;bool usb_xinput_active(){return active;}bool ds_mode(){return true;}
const char* string_desc_arr[]={"en","maker","pad","serial","extra"};
const uint16_t *check(uint8_t index){size_t chr_count;
"""+s[a:b]+r"""
 static uint16_t result;result=chr_count;return &result;}
int main(){for(int mode=0;mode<2;mode++){active=mode;assert(check(2));assert(check(0xee)==nullptr);assert(check(255)==nullptr);assert((check(5)!=nullptr)==active);}puts("PASS: actual string resolver, invalid index, XInput audio name");}
""")

usb=(root/'src/usb.cpp').read_text(encoding='utf-8')
bt=(root/'src/bt.cpp').read_text(encoding='utf-8')
descriptor_types=s[s.index('enum {'):s.index('// Number of HID interfaces')]
string_indices=s[s.index('enum {\n    STRID_LANGID'):s.index('// Device Descriptors')]
descriptor_state=s[s.index('static volatile bool s_idle_pid'):
                   s.index('// Configuration Descriptor')].replace('#include "xinput_usb.h"', '')
configuration=s[s.index('uint8_t descriptor_configuration[]'):
                s.index('// HID Report Descriptor')]
xinput=(root/'src/xinput_usb.cpp').read_text(encoding='utf-8')
xinput_gamepad=xinput[xinput.index('constexpr uint8_t input_ep'):
                       xinput.index('static_assert(sizeof(gamepad)')]
run('usb-enumeration',r"""
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <string>
#define ENABLE_WAKE_HID
#define U16_TO_U8S_LE(x) uint8_t(x),uint8_t((x)>>8)
#define TUD_BOS_DESCRIPTOR(...) 0x11
#define TUD_BOS_MS_OS_20_DESCRIPTOR(...) 0x22
#define TUSB_DESC_STRING 3
#define CFG_TUD_AUDIO_FUNC_1_N_CHANNELS_RX 4
constexpr uint8_t TUSB_DESC_INTERFACE_ASSOCIATION=11,TUSB_DESC_INTERFACE=4;
struct Config_body {
 uint8_t controller_mode=2, usb_gamepad_mode=0, enable_wake=0, polling_rate_mode=0;
 bool keyboard=false, mouse=false;
} cfg;
Config_body &get_config(){return cfg;}
bool is_dse=false, hide_serial=false;
bool device_usb_serial_hidden(){return hide_serial;}
bool bt_edge_connected(){return is_dse;}
bool usb_mouse_iface_needed(const Config_body &c){return c.mouse;}
bool usb_kbd_iface_needed(const Config_body &c){return c.enable_wake || c.keyboard || c.mouse;}
uint8_t usb_mouse_instance(const Config_body &){return 2;}
struct DeviceDescriptor {uint16_t idVendor,idProduct,bcdUSB;uint8_t iSerialNumber;} desc_device{};
const uint8_t xinput_device[]{18,1};
const uint8_t *xinput_device_descriptor(){return xinput_device;}
const uint8_t *xinput_configuration_descriptor(const uint8_t *,uint16_t,uint8_t);
bool usb_edge_serial_hidden(const Config_body &);
void usb_schedule_reconnect();
void state_rumble_reset(){}
void wake_note_usb_reconnect(){}
bool macros_suspended=false;
void macro_suspend(bool on){macros_suspended=on;}
void xinput_disconnect(){}
unsigned audio_session_resets=0;
void audio_usb_session_reset(){++audio_session_resets;}
unsigned audio_playback_invalidations=0;
void audio_usb_playback_invalidate(){++audio_playback_invalidations;}
uint32_t now=0;
unsigned connects=0, disconnects=0;
uint32_t get_absolute_time(){return now;}
uint32_t to_ms_since_boot(uint32_t value){return value;}
void tud_connect(){++connects;}
void tud_disconnect(){++disconnects;}
uint8_t board_usb_get_serial(uint16_t *,uint8_t){return 0;}
const uint8_t desc_hid_report_ds[316]{},desc_hid_report_dse[432]{};
const uint8_t desc_hid_report_kbd[]{1},desc_hid_report_mouse[]{2},desc_bos[]{3};
"""+descriptor_types+string_indices+extract(s,'static bool desired_ds_mode(')+'\n'+descriptor_state+configuration+
    extract(s,'uint8_t const *tud_hid_descriptor_report_cb(')+'\n'+
    s[s.index('static char const *string_desc_arr'):s.index('#ifdef ENABLE_WAKE_HID\n//--------------------------------------------------------------------+',s.index('static char const *string_desc_arr'))]+
    extract(s,'uint8_t const *tud_descriptor_bos_cb(')+'\n'+xinput_gamepad+
    extract(xinput,'const uint8_t *xinput_configuration_descriptor(')+'\n'+
    usb[usb.index('namespace {'):usb.index('uint8_t mute[2]')]+
    extract(bt,'static void restore_full_usb_identity(')+r"""
std::u16string product() {
 auto text=tud_descriptor_string_cb(2,0);
 return std::u16string(text+1,text+(text[0]&255)/2);
}
uint16_t report_length(const uint8_t *descriptor) {
 for(unsigned off=0,total=descriptor[2]+256u*descriptor[3];off<total;off+=descriptor[off]) {
  assert(descriptor[off]>=2);
  if(descriptor[off+1]==0x21 && descriptor[off]==9)
   return descriptor[off+7]+256u*descriptor[off+8];
 }
 return 0;
}
int main() {
 macros_suspended=true;
 usb_detach();
 assert(!macros_suspended&&audio_session_resets==1);
 restore_full_usb_identity();
 assert(connects==1&&disconnects==1);
 macros_suspended=true;
 tud_umount_cb();
 assert(!macros_suspended);
 assert(audio_playback_invalidations==1);
 tud_descriptor_device_cb();
 assert(desc_device.idVendor==0x054c&&desc_device.idProduct==0x0ce6&&desc_device.iSerialNumber==3&&desc_device.bcdUSB==0x0200);
 const auto *descriptor=tud_descriptor_configuration_cb(0);
 assert(descriptor[4]==4&&descriptor[CONFIG_DESC_LEN_BASE-1]==4&&report_length(descriptor)==316);

 // These changes occur before the host finishes its first enumeration.
 is_dse=true;hide_serial=true;cfg.enable_wake=1;cfg.mouse=true;cfg.polling_rate_mode=1;
 restore_full_usb_identity();
 restore_full_usb_identity();
 assert(usb_reconnect_pending()&&disconnects==2&&connects==1);
 tud_descriptor_device_cb();
 assert(desc_device.idProduct==0x0ce6&&desc_device.iSerialNumber==3&&desc_device.bcdUSB==0x0200);
 assert(product()==u"DualSense Wireless Controller"&&!tud_descriptor_bos_cb());
 descriptor=tud_descriptor_configuration_cb(0);
 assert(report_length(descriptor)==316&&descriptor[4]==4&&descriptor[CONFIG_DESC_LEN_BASE-1]==4);
 assert(tud_hid_descriptor_report_cb(0)==desc_hid_report_ds);
 now=249;usb_reconnect_task();assert(connects==1);
 now=250;usb_reconnect_task();assert(connects==2&&!usb_reconnect_pending());
 tud_descriptor_device_cb();
 assert(desc_device.idProduct==0x0df2&&desc_device.iSerialNumber==0&&desc_device.bcdUSB==0x0210);
 assert(product()==u"DualSense Edge Wireless Controller"&&tud_descriptor_bos_cb());
 descriptor=tud_descriptor_configuration_cb(0);
 assert(report_length(descriptor)==432&&descriptor[4]==6&&descriptor[CONFIG_DESC_LEN_BASE-1]==2);
 assert(tud_hid_descriptor_report_cb(0)==desc_hid_report_dse);
 assert(tud_hid_descriptor_report_cb(1)==desc_hid_report_kbd&&tud_hid_descriptor_report_cb(2)==desc_hid_report_mouse);

 usb_set_idle_pid(true);usb_schedule_reconnect();
 now=500;usb_reconnect_task();tud_descriptor_device_cb();
 assert(usb_served_idle_pid()&&desc_device.idVendor==0x2e8a&&desc_device.idProduct==0x0de0);
 assert(product()==u"DS5Dongle (controller off)");
 is_dse=false;cfg.usb_gamepad_mode=1;
 restore_full_usb_identity();assert(usb_reconnect_pending());
 now=750;usb_reconnect_task();assert(tud_descriptor_device_cb()==xinput_device);
 assert(!usb_served_idle_pid()&&report_length(tud_descriptor_configuration_cb(0))==sizeof(xinput_settings_report));
 assert(tud_hid_descriptor_report_cb(0)==xinput_settings_report);
 is_dse=true;restore_full_usb_identity();
 assert(!usb_reconnect_pending()&&product()==u"DualSense Wireless Controller");
 puts("PASS: descriptors remain consistent before SET_CONFIG, late DS/Edge upgrade, idle wake and XInput");
}
""")

channel_close=bt.index('        case L2CAP_EVENT_CHANNEL_CLOSED: {')
run('required-hid-channel-loss',r"""
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <map>
constexpr int L2CAP_EVENT_CHANNEL_CLOSED=1;
uint16_t hid_control_cid, hid_interrupt_cid;
bool hid_control_open, hid_interrupt_open, hid_channels_failed;
unsigned neutral, wake_resets, rumble_resets, rear_disconnects, disconnects;
std::map<unsigned,unsigned> feature_data;
uint16_t l2cap_event_channel_closed_get_local_cid(const uint16_t *p){return *p;}
void controller_input_on_disconnect(){++neutral;}
void wake_on_bt_disconnect(){++wake_resets;}
void state_rumble_reset(){++rumble_resets;}
void audio_rear_link_disconnected(){++rear_disconnects;}
bool bt_disconnect(){++disconnects;return true;}
"""+extract(bt,'static void reset_disconnected_hid(')+r"""
void closed(uint16_t cid){const auto *packet=&cid;switch(1){
"""+bt[channel_close:bt.index('        case L2CAP_EVENT_CAN_SEND_NOW:',channel_close)]+r"""
}}
int main(){
 for(uint16_t lost:{10,11}){
  hid_control_cid=10;hid_interrupt_cid=11;hid_control_open=hid_interrupt_open=true;
  hid_channels_failed=false;feature_data[0x81]=42;
  unsigned before=neutral;
  closed(99);assert(neutral==before&&hid_control_open&&hid_interrupt_open&&!feature_data.empty());
  closed(lost);closed(lost);closed(lost==10?11:10);
  assert(neutral==before+1&&wake_resets==neutral&&rumble_resets==neutral&&rear_disconnects==neutral&&disconnects==neutral);
  assert(hid_channels_failed&&!hid_control_open&&!hid_interrupt_open);
  assert(!hid_control_cid&&!hid_interrupt_cid&&feature_data.empty());
 }
 puts("PASS: either required channel closes the session once; unrelated or duplicate close leaves it alone");
}
""")

xinput_state=xinput[xinput.index('alignas(4) uint8_t input'):xinput.index('void send_rumble(')]
run('xinput-out-rearm',r"""
#include <cassert>
#include <cstdint>
#include <cstdio>
constexpr uint8_t input_ep=0x89,output_ep=0x09;
using xfer_result_t=uint8_t;
constexpr uint8_t XFER_RESULT_SUCCESS=0;
uint32_t now=0;
unsigned submits=0, rumble=0;
bool accept=false,ready=true,busy=false;
uint32_t get_absolute_time(){return now;}
uint32_t to_ms_since_boot(uint32_t time){return time;}
bool tud_ready(){return ready;}
bool usbd_edpt_busy(uint8_t,uint8_t ep){return ep==output_ep&&busy;}
bool usbd_edpt_xfer(uint8_t,uint8_t ep,uint8_t*,uint16_t){assert(ep==output_ep);++submits;return accept;}
bool xinput_decode_rumble(uint8_t*,uint32_t,uint8_t &left,uint8_t &right){left=1;right=2;return true;}
void send_rumble(uint8_t,uint8_t){++rumble;}
void state_rumble_reset(){}
unsigned audio_session_resets=0;
void audio_usb_session_reset(){++audio_session_resets;}
"""+xinput_state+extract(xinput,'void reset(')+'\n'+extract(xinput,'void bus_reset(')+'\n'+extract(xinput,'bool transfer(')+'\n'+
extract(xinput,'bool xinput_report_ready(')+r"""
int main(){
 endpoints_open=true;
 transfer(0,output_ep,XFER_RESULT_SUCCESS,8);assert(submits==1&&rumble==1);
 now=7;assert(xinput_report_ready()&&submits==1);
 now=8;busy=true;assert(xinput_report_ready()&&submits==1);
 busy=false;assert(xinput_report_ready()&&submits==2);
 now=16;ready=false;assert(!xinput_report_ready()&&submits==2);
 ready=accept=true;assert(xinput_report_ready()&&submits==3&&rumble==1);
 now=24;assert(xinput_report_ready()&&submits==3);
 accept=false;transfer(0,output_ep,1,0);assert(submits==4);
 bus_reset(0);now=32;transfer(0,output_ep,XFER_RESULT_SUCCESS,8);
 assert(!xinput_report_ready()&&submits==4&&rumble==1&&!output_retry_pending&&audio_session_resets==1);
 puts("PASS: OUT retry obeys interval/backpressure and stops at reset without replaying rumble");
}
""")

s=(root/'src/audio.cpp').read_text(encoding='utf-8')
a=s.index('    static mic_decode_element mic_pb{};');b=s.index('    // 1.',a)
run('mic-mute',r"""
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <cassert>
#include <cstdio>
constexpr int MIC_FRAMES=480;
struct mic_decode_element{uint32_t generation;int16_t data[480];uint16_t len;};
uint32_t mic_stream_generation=0, mic_now_mock=0;
bool mic_active=true;
struct Config {bool disable_mic=false;} config;
Config &get_config(){return config;}
constexpr int MIC_OPUS_SIZE=71;
struct mic_element {uint32_t generation;uint8_t data[MIC_OPUS_SIZE];};
struct MicInputQueue {int count=0;} mic_fifo;
bool bt_is_ready(){return true;}
bool queue_is_full(MicInputQueue*){return false;}
bool queue_try_remove(MicInputQueue*,void*){return false;}
bool queue_try_add(MicInputQueue *q,const mic_element*){++q->count;return true;}
#define __not_in_flash_func(x) x
uint32_t get_absolute_time(){return mic_now_mock;} uint32_t to_ms_since_boot(uint32_t t){return t;}
float volume[2]{};
int stale_mic=0, playback_ticks=0;int mic_decode_fifo;uint8_t mute[2]{};int16_t captured[960]{};
bool queue_try_remove(int*,mic_decode_element*p){if(!p)return false;for(int i=0;i<480;i++)p->data[i]=i+1;p->len=960;p->generation=mic_stream_generation-stale_mic;return true;}
unsigned write_limit=1920,capture_bytes=0;
uint16_t tud_audio_write(const void*p,uint16_t n){n=std::min<unsigned>(n,write_limit);memcpy(captured,p,n);capture_bytes=n;return n;}
"""+extract(s,'bool audio_mic_active()')+extract(s,'void __not_in_flash_func(mic_add_queue)')+r"""
void process(){
"""+s[a:b]+r"""
 ++playback_ticks;
}
int main(){process();assert(captured[0]==1&&captured[1]==1&&captured[959]==480);mute[1]=1;process();for(auto x:captured)assert(x==0);mute[1]=0;process();assert(captured[0]==1);volume[1]=20;process();assert(captured[959]==4800);volume[1]=48;process();assert(captured[959]==32767);volume[1]=-20;process();assert(captured[959]==480);volume[1]=0;write_limit=400;process();assert(captured[199]==100);process();assert(captured[0]==101);
 mic_active=false;capture_bytes=0;process();assert(capture_bytes==0);mic_active=true;++mic_stream_generation;write_limit=1920;process();assert(captured[0]==1);
 write_limit=0;process();mic_now_mock+=20;write_limit=1920;process();assert(captured[0]==1);
 capture_bytes=0;stale_mic=1;int before=playback_ticks;process();assert(capture_bytes==0&&playback_ticks==before+1);stale_mic=0;process();assert(capture_bytes>0);
 write_limit=400;process();assert(capture_bytes==400);
 config.disable_mic=true;++mic_stream_generation;capture_bytes=0;process();assert(!capture_bytes);
 uint8_t incoming[MIC_OPUS_SIZE]{};
 mic_add_queue(incoming,sizeof(incoming));assert(!mic_fifo.count);
 config.disable_mic=false;++mic_stream_generation;write_limit=1920;process();assert(captured[0]==1);
 mic_add_queue(incoming,sizeof(incoming));assert(mic_fifo.count==1);
 puts("PASS: USB mic gain/mute, partial writes, policy toggles, close/reopen, bounded pending age");}
""")

s=(root/'src/audio.cpp').read_text(encoding='utf-8')
idle=s[s.index('    if (connected && link_changed && mic_active)'):s.index('    // Mic playback')]
run('audio-idle',r"""
#include <cassert>
#include <cstdint>
#include <cstdio>
bool connected=false,link_changed=false,discard_usb=false,headset_state_known=true,mic_active=true;
bool bt_is_ready(){return connected;}
unsigned mic_stream_generation=0,mic_fifo=0,mic_decode_fifo=0,usb_bytes=0,clears=0,mic_clears=0,status_updates=0;
uint8_t g_oled_ah_input_peak=1,g_oled_ah_output_peak=1;
bool queue_is_empty(unsigned *q){return *q==0;}
bool queue_try_remove(unsigned *q,void *){if(!*q)return false;--*q;return true;}
unsigned tud_audio_available(){return usb_bytes;}
void tud_audio_clear_ep_out_ff(){++clears;usb_bytes=0;}
void tud_audio_clear_ep_in_ff(){++mic_clears;}
void update_mic_status(){++status_updates;}
"""+extract(s,'static void reset_mic_stream()')+extract(s,'void audio_mic_policy_changed()')+r"""
void tick(){
"""+idle+r"""
}
int main(){
 tick();assert(!mic_stream_generation&&!clears);
 mic_fifo=2;mic_decode_fifo=2;link_changed=true;discard_usb=true;tick();
 assert(mic_stream_generation==1&&!headset_state_known&&!mic_fifo&&!mic_decode_fifo&&!clears);
 link_changed=false;discard_usb=false;mic_decode_fifo=1;usb_bytes=12;tick();tick();
 assert(!mic_decode_fifo&&!usb_bytes&&clears==1&&mic_stream_generation==1&&mic_clears==1);
 connected=true;mic_fifo=2;audio_mic_policy_changed();
 assert(mic_stream_generation==2&&mic_clears==2&&!mic_fifo&&status_updates==1);
 tick();assert(mic_clears==2&&status_updates==1);
 audio_mic_policy_changed();assert(mic_clears==3&&status_updates==2);
 assert(!g_oled_ah_input_peak&&!g_oled_ah_output_peak);
 puts("PASS: disconnect resets once; late mic frames and new USB bytes still discarded");
}
""")
a=s.index('    const bool connected = bt_is_ready();',s.index('void __not_in_flash_func(audio_loop)'))
b=s.index('    const bool speaker_enabled',a)
run('stream-reset',r"""
#include <cstdint>
#include <cstring>
#include <cassert>
#include <cstdio>
#include <atomic>
using uint=unsigned;
constexpr int SAMPLE_SIZE=64,CFG_TUD_AUDIO_FUNC_1_N_CHANNELS_RX=4;
struct Config{uint8_t auto_haptics_enable=1;}config;
Config&get_config(){return config;}
#include "profile_chime.h"
ProfileChime profile_chime;
std::atomic<bool> audio_link_active{false};
std::atomic<uint32_t> haptic_packet_peaks{0};
bool link=true,audio_input_seen=false,speaker_filters_reset=false;
bool mic_active=false;
uint32_t now=0,last_audio_input_ms=0,mic_generation=0;
int resets=0,clears=0,discards=0,usb_frames=0;
uint16_t g_diag_rear_left_peak=0,g_diag_rear_right_peak=0;
struct Resampler{void Reset(){resets++;}}resampler;
void __sev(){} bool bt_is_ready(){return link;}
uint32_t get_absolute_time(){return now;}uint32_t to_ms_since_boot(uint32_t x){return x;}
void tud_audio_clear_ep_out_ff(){clears++;usb_frames=0;}void bt_discard_audio(){discards++;}
void set_mic_active(bool active){if(mic_active!=active)++mic_generation;mic_active=active;}
bool spk_active=false;
void audio_usb_playback_invalidate(){}
"""+s[s.index('enum class StreamReset'):s.index('static bool rear_route_ready()')]+
extract(s,'void audio_usb_session_reset(')+r"""
struct Positions{uint speaker;int haptic;uint remainder;};
Positions tick(bool seed){
"""+s[a:b]+r"""
 if(seed){audio_buf_pos=300;haptic_buf_pos=20;usb_remainder_bytes=3;audio_input_seen=true;last_audio_input_ms=now;}
 return {audio_buf_pos,haptic_buf_pos,usb_remainder_bytes};
}
int main(){
 tick(true);now=10;auto p=tick(false);assert(p.speaker==300&&p.haptic==20);
 audio_reset_stream();p=tick(false);
 assert(!p.speaker&&!p.haptic&&!p.remainder&&speaker_filters_reset);
 int n=resets;tick(false);assert(resets==n);
 tick(true);now+=60;p=tick(false);assert(!p.speaker&&!p.haptic&&!audio_input_seen);
 tick(true);config.auto_haptics_enable=0;p=tick(false);assert(!p.haptic);
 tick(true);link=false;p=tick(false);assert(!p.haptic);link=true;tick(false);
 assert(resets==discards&&clears==4);
 for(int i=0;i<100;i++){
  tick(true);config.auto_haptics_enable^=1;p=tick(false);assert(!p.haptic&&!p.speaker&&!p.remainder);
  tick(true);audio_reset_stream();p=tick(false);assert(!p.haptic&&!p.speaker&&!p.remainder);
  tick(true);link=false;p=tick(false);assert(!p.haptic);link=true;p=tick(false);assert(!p.haptic);
 } // timeout and mode switch preserve queued fresh USB PCM
 tick(true);spk_active=mic_active=true;usb_frames=2;
 const auto before=discards;
 audio_usb_session_reset();assert(!spk_active&&!mic_active&&!audio_input_seen&&!usb_frames&&mic_generation==1&&discards==before+1);
 audio_usb_session_reset();assert(mic_generation==1&&discards==before+1);
 spk_active=true;set_mic_active(true);usb_frames=3;
 const int after_close=clears;
 p=tick(false);assert(!p.haptic&&!p.speaker&&!p.remainder&&usb_frames==3&&clears==after_close);
 assert(spk_active&&mic_active&&mic_generation==2);
 puts("PASS: actual partial buffers reset; USB session end drops old audio and preserves the new alt setting and PCM");
}
""")
a=s.index('    if (reset_haptic_filters) {');b=s.index('    } else if (split_on',a)
block=s[a:b]+'    }\n'
variables=sorted(set(re.findall(r'\b([a-z][a-z0-9_]*)\s*=',block))-{'speaker_filters_reset'})
prologue=s[s.index('    const bool dsp_rear ='):a]
run('dsp-reset','#include <cassert>\n#include <cstdio>\n#include <cstdint>\n'
    'struct { int ah_dsp_source=0; } cfg; int actual_ch=4,auto_mode=0; bool speaker_filters_reset=false;\n'
    +''.join('float '+x+'=0;\n' for x in variables)
    +'void tick(){\n'+prologue+block+'}\n'
    +'void seed(){'+''.join(x+'=1;' for x in variables)+'}\n'
    +'void cleared(){'+''.join('assert('+x+'==0);' for x in variables)+'assert(!speaker_filters_reset);}\n'
    +'int main(){seed();speaker_filters_reset=true;tick();cleared();'
    +'seed();tick();'+''.join('assert('+x+'==1);' for x in variables)
    +'auto_mode=1;tick();cleared();seed();auto_mode=2;tick();cleared();'
    +'seed();cfg.ah_dsp_source=1;tick();cleared();seed();actual_ch=2;tick();cleared();'
    +'puts("PASS: production mode/input transitions and stream reset clear LP, envelope and carrier memories; unchanged mode preserves them");}\n')

s=(root/'src/state_mgr.cpp').read_text(encoding='utf-8')
a=s.index('    // Cached trigger commands');b=s.index('    // XInput rumble',a)
run('synth-audio-authority',r"""
#include <cstdint>
#include <cassert>
#include <cstdio>
int main(){uint8_t copy[63]{};copy[0]=0xff;copy[1]=0xff;
"""+s[a:b]+r"""
assert(copy[0]==0x03&&copy[1]==0x7d);
assert(!(copy[0]&0xfc)&&!(copy[1]&0x82));
puts("PASS: synthetic replay drops cached game trigger/audio authority and retains motor selectors");}
""")



# Control retries execute the production pump, including its ordering rotation.
s=(root/'src/bt.cpp').read_text(encoding='utf-8')
run('control-retry',r"""
#include <deque>
#include <cstdint>
#include <cstring>
#include <cassert>
#include <cstdio>
using uint=unsigned; constexpr int MTU_CONTROL=672,BTSTACK_ACL_BUFFERS_FULL=1;
struct ControlSend{uint8_t data[672];uint16_t len;uint8_t retries;};
std::deque<ControlSend> control_fifo;
bool queue_try_remove(std::deque<ControlSend>*q,ControlSend*p){if(q->empty())return false;if(p)*p=q->front();q->pop_front();return true;}
bool queue_try_add(std::deque<ControlSend>*q,ControlSend*p){if(q->size()==8)return false;q->push_back(*p);return true;}
unsigned queue_get_level(std::deque<ControlSend>*q){return q->size();}
bool queue_is_empty(std::deque<ControlSend>*q){return q->empty();}
int hid_control_cid=1;bool hid_control_open=true;int status=1,writes=0,last=-1,events=0;
uint16_t l2cap_get_remote_mtu_for_local_cid(int){return 672;}
void l2cap_request_can_send_now_event(int){events++;}
int l2cap_send(int,uint8_t*p,uint16_t){last=p[1];return status;}
void dse_on_profile_write(uint8_t){writes++;}
uint32_t now_ms=0;
uint32_t get_absolute_time(){return now_ms;}
uint32_t to_ms_since_boot(uint32_t t){return t;}
"""+extract(s,'static bool control_error_log_due()')+'\n'+extract(s,'bool bt_control_send(')+'\n'+extract(s,'static void bt_control_send_ready()')+r"""
int main(){
 uint8_t a[]{0x53,0x60},b[]{0x43,0x70};
 assert(bt_control_send(a,2)&&bt_control_send(b,2));
 bt_control_send_ready();assert(writes==0&&control_fifo.front().data[1]==0x60);
 status=0;bt_control_send_ready();assert(last==0x60&&writes==1);bt_control_send_ready();assert(last==0x70&&writes==1);
 status=1;assert(bt_control_send(a,2));for(int i=0;i<3;i++)bt_control_send_ready();assert(control_fifo.empty()&&writes==1);
 for(int i=0;i<8;i++)assert(bt_control_send(b,2));assert(!bt_control_send(a,2));
 now_ms=999;assert(!control_error_log_due());now_ms=1000;assert(control_error_log_due());
 now_ms=0xfffffff0u;assert(control_error_log_due());now_ms=0x100;assert(!control_error_log_due());
 now_ms=0x400;assert(control_error_log_due());
 control_fifo.clear();hid_control_open=false;assert(!bt_control_send(a,2));
 puts("PASS: ordered retry, successful-send notification, retry limit, queue admission");
}
""")

macro=(root/'src/macro.cpp').read_text(encoding='utf-8')
cmd=(root/'src/cmd.cpp').read_text(encoding='utf-8')
legacy=cmd[cmd.index('        case 0x1a: {\n'):cmd.index('        case 0x1b: {\n')]
lease=cmd[cmd.index('        case 0x23: {\n'):cmd.index('        case 0x24: {\n')]
run('macro-pause-lease',r"""
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <vector>
static bool g_suspended=false;
static uint32_t g_pause_owner=0,g_pause_updated_ms=0,clock_ms=0;
static uint32_t now_ms(){return clock_ms;}
void macro_suspend(bool);
int resets=0,activity=0;
void macro_reset(){++resets;}
void manual_power_note_activity(uint32_t){++activity;}
std::vector<uint8_t> pico_settings_reply;
"""+extract(macro,'static void expire_macro_pause()')+'\n'+extract(macro,'void macro_suspend(bool on)')+'\n'+
extract(macro,'bool macro_suspend_legacy(bool on)')+'\n'+extract(macro,'bool macro_pause_lease(')+r"""
void command(int id,uint8_t const* buffer,uint16_t bufsize){switch(id){
"""+legacy+lease+r"""
}}
int main(){
 uint8_t req[10]{1,1,1,2,3,4,5,6,7,8};
 constexpr uint32_t owner=0x04030201, stranger=42;
 uint8_t on=1,off=0;
 command(0x1a,&on,1);assert(g_suspended&&pico_settings_reply[2]==0);
 command(0x23,req,10);assert(pico_settings_reply[2]==1&&!g_pause_owner);
 command(0x1a,&off,1);assert(!g_suspended&&pico_settings_reply[2]==0);
 command(0x23,req,9);assert(pico_settings_reply[2]==1&&!g_suspended);
 command(0x23,req,10);assert(pico_settings_reply[2]==0&&g_pause_owner==owner&&activity==1);
 assert(!memcmp(req,pico_settings_reply.data()+3,10));
 command(0x1a,&off,1);assert(pico_settings_reply[2]==1&&g_suspended);
 assert(!macro_pause_lease(1,stranger)&&!macro_pause_lease(2,stranger)&&!macro_pause_lease(3,stranger));
 clock_ms=29999;expire_macro_pause();assert(g_suspended);
 req[1]=2;req[9]=10;command(0x23,req,10);assert(pico_settings_reply[2]==0&&activity==2&&resets==2);
 clock_ms=59998;expire_macro_pause();assert(g_suspended);
 clock_ms=59999;expire_macro_pause();assert(!g_suspended&&!g_pause_owner);
 assert(!macro_pause_lease(2,owner)&&macro_pause_lease(3,owner));
 clock_ms=0xfffffff0u;assert(macro_pause_lease(1,stranger));
 clock_ms+=30000u;expire_macro_pause();assert(!g_suspended);
 assert(macro_pause_lease(1,stranger));macro_suspend(false); // USB session ended
 assert(!macro_pause_lease(2,stranger));
 assert(macro_pause_lease(1,owner)&&!macro_pause_lease(3,stranger));
 assert(g_suspended&&macro_pause_lease(3,owner)&&!g_suspended);
 puts("PASS: legacy compatibility, exact echo, exclusive session, timed renewal, expiration, timer wrap and disconnect");
}
""")
s=(root/'src/dse.cpp').read_text(encoding='utf-8')
s=re.sub(r'^#include.*\n','',s,flags=re.M)
run('edge-prefetch',r"""
#include <cstdint>
#include <vector>
#include <unordered_map>
#include <cstdio>
#include <cstring>
#include <cassert>
std::unordered_map<uint8_t,std::vector<uint8_t>> feature_data;
uint32_t now=1;uint16_t cid=1;int request_count=0;
uint32_t get_absolute_time(){return now;}uint32_t to_ms_since_boot(uint32_t t){return t;}
uint16_t bt_control_cid(){return cid;}
bool bt_control_send(const uint8_t*,uint16_t){return true;}
bool set_feature_data(uint8_t,uint8_t*,uint16_t){return true;}
std::vector<uint8_t> get_feature_data(uint8_t,uint16_t){request_count++;return {};}
"""+s+r"""
int main(){
 dse_on_connect();now=4001;dse_task();
 for(int i=0;i<12;i++){now+=80;dse_task();}
 assert(!dse_profiles_ready());
 for(uint8_t id=0x70;id<=0x7a;id++){uint8_t p[]{0xa3,id,1};dse_on_control_packet(p,3);}
 now+=80;dse_task();assert(!dse_profiles_ready());
 uint8_t last[]{0xa3,0x7b,1};dse_on_control_packet(last,3);now+=80;dse_task();assert(dse_profiles_ready());
 prefetch_start();for(int i=0;i<45;i++){now+=80;dse_task();}assert(!dse_profiles_ready()&&prefetch_next==0);
 dse_on_connect();assert(!dse_profiles_ready()&&prefetch_next==0&&profile_written_ms==0);
 puts("PASS: no early completion, delayed final response, bounded missing-response retry, reconnect reset");
}
""")


s=(root/'src/macro.cpp').read_text(encoding='utf-8')
run('mute-binding',r"""
#include <cstdint>
#include <cassert>
#include <cstdio>
constexpr int MACRO_COUNT=4,GESTURE_NONE=0;constexpr uint32_t BTN_MUTE=1u<<18;
struct Entry{int gesture=0;uint32_t chord=0;int out_btn=0;uint8_t keys[4]{};};
struct {struct {Entry entry;}rec[4];}g_table;
struct {uint32_t macro_disable=0;}cfg;
uint32_t mute_binding_mask=0;bool mute_binding_dirty=true;
auto&get_config(){return cfg;}bool g_loaded=true;void macro_load(){}
bool macro_is_enabled(uint32_t mask,int i){return !(mask&(1u<<i));}
bool macro_any_enabled(uint32_t mask){return (mask&15)!=15;}
"""+extract(s,'bool macro_uses_mute_button(')+r"""
int main(){
 assert(!macro_uses_mute_button());auto&e=g_table.rec[0].entry;e.chord=BTN_MUTE;e.out_btn=1;mute_binding_dirty=true;
 assert(macro_uses_mute_button());cfg.macro_disable=1;assert(!macro_uses_mute_button());
 cfg.macro_disable=0;e.out_btn=0;e.keys[0]=4;mute_binding_dirty=true;assert(macro_uses_mute_button());
 e.keys[0]=0;mute_binding_dirty=true;assert(!macro_uses_mute_button());puts("PASS: mute button mapping, keyboard macro, disabled and empty entries");
}
""")

# Send-ready pump: regular 32-frame native packets and a deliberate transport stall.
s=(root/'src/bt.cpp').read_text(encoding='utf-8')
a=s.index('            if (hid_interrupt_cid == 0 ||',s.index('case L2CAP_EVENT_CAN_SEND_NOW:'))
b=s.index('\n            break;',a)
pump=s[a:b]
q=(out/'queue.cpp').read_text(encoding='utf-8')
q=q[:q.index('int main(){')]
q=q.replace('uint32_t get_absolute_time(){return 100;}', 'uint32_t now=100;uint32_t get_absolute_time(){return now;}')
continuity_code=q+r"""
#include <vector>
#include "rumble_delivery.h"
bool queue_is_empty(std::deque<send_element>*q){return q->empty();}
std::vector<int> delivered;int status=0;
int l2cap_event_can_send_now_get_local_cid(uint8_t*){return 1;}
constexpr int BTSTACK_ACL_BUFFERS_FULL=1;
uint8_t pending_send_retries=0;uint32_t pending_send_failed_ms=0;
int recovery_requests=0;void audio_reset_stream(){++recovery_requests;}
void audio_rear_sync(){}
void state_refresh_rumble(uint8_t*p){p[0]&=~3u;p[38]&=~4u;p[2]=p[3]=0;}
void state_set(uint8_t*p,unsigned n){memset(p,0,n);}
void state_report_sent(const uint8_t*,bool){}
bool suspend_release_pending=false;
bool state_suspend_release_pending(){return suspend_release_pending;}
void state_suspend_release_sent(const uint8_t*){}
int l2cap_send(int,uint8_t*p,unsigned){if(!status)delivered.push_back(p[21]);return status;}
void pump(){uint8_t*packet=nullptr;do {
"""+pump+r"""
}while(false);}
int main(){
 uint8_t audio[398]{};audio[0]=0x36;audio[12]=64;
 for(int i=0;i<200;i++){now+=11;audio[20]=i;bt_write(audio,398);pump();}
 assert(delivered.size()==200);for(int i=0;i<200;i++)assert(delivered[i]==i);
 audio[20]=201;bt_write(audio,398);status=1;pump();assert(pending_send_valid);
 now++;status=0;pump();assert(delivered.back()==201&&!pending_send_valid);
 audio[20]=202;bt_write(audio,398);now+=48;pump();
 assert(delivered.back()==202); // native retained at 48 ms
 cfg.auto_haptics_enable=1;audio[20]=203;bt_write(audio,398);now+=48;
 audio[20]=205;bt_write(audio,398);pump();assert(delivered.back()==205); // same event skips stale head
 assert(g_audio_transport_stats.expired==1);
 cfg.auto_haptics_enable=0;audio[20]=204;bt_write(audio,398);status=1;pump();now+=20;
 audio[20]=206;bt_write(audio,398);status=0;pump();assert(delivered.back()==206);
 assert(g_audio_transport_stats.retry_expired==1);
 audio[20]=207;bt_write(audio,398);status=1;for(int i=0;i<6;i++)pump();assert(!pending_send_valid);
 assert(g_audio_transport_stats.retry_exhausted==1);
 status=2;audio[20]=208;bt_write(audio,398);pump();assert(g_audio_transport_stats.send_error==1);
 status=0;now=0xfffffff0;audio[20]=209;bt_write(audio,398);now=32;pump();assert(delivered.back()==209);
 // Enqueue policy remains attached to the frame, not the later live mode.
 now=100;cfg.auto_haptics_enable=1;bt_write(audio,398);cfg.auto_haptics_enable=0;now+=48;pump();
 assert(g_audio_transport_stats.expired==2);
 cfg.auto_haptics_enable=0;audio[20]=210;bt_write(audio,398);now+=119;pump();assert(delivered.back()==210);
 audio[20]=211;bt_write(audio,398);now+=120;pump();assert(delivered.back()==210);
 assert(recovery_requests==1&&g_audio_transport_stats.recoveries==1&&!pending_send_valid&&send_fifo.empty());
 audio[20]=212;bt_write(audio,398);pump();assert(delivered.back()==212);
 unsigned rec=g_audio_transport_stats.recoveries;
 for(int i=0;i<20;i++){now+=11;bt_write(audio,398);}pump();
 assert(g_audio_transport_stats.recoveries==rec+1&&send_fifo.empty());
 now+=1000;bt_write(audio,398);pump();assert(g_audio_transport_stats.recoveries==rec+1); // idle excluded
 for(int i=0;i<500;i++){
  now+=2;bt_write(audio,398);
  if(i%3==0)pump();
  if(i%29==0)bt_discard_audio();
  unsigned expected=0;for(const auto &item:send_fifo)expected+=item.native_audio;
  assert(native_queued==expected);
 }
 bt_discard_audio();assert(native_queued==0);
 puts("PASS: ordered delivery, transient recovery, native retention, bounded retries, stale-head scan, wrap and per-frame policy");
}
"""
run('native-continuity',continuity_code)


# Consume actual encoded frames once, in order; never wait for core1.
s=(root/'src/audio.cpp').read_text(encoding='utf-8')
run('speaker-payload-route-change',r"""
#include <cstdint>
#include <cstring>
#include <cassert>
"""+s[s.index('#define REPORT_SIZE'):s.index('// #define VOLUME_GAIN')]+extract(s,'bool audio_strip_speaker_payload(')+r"""
int main() {
 for (int native=0;native<2;++native) {
  uint8_t report[REPORT_SIZE];memset(report,0xa5,sizeof(report));
  report[0]=REPORT_ID;
  int tag=native?77:142;
  report[tag]=native?0x93:0x96;report[tag+1]=200;
  assert(!audio_strip_speaker_payload(report,sizeof(report)-1,native));
  assert(audio_strip_speaker_payload(report,sizeof(report),native));
  assert(!audio_strip_speaker_payload(report,sizeof(report),native));
  for(int i=1;i<REPORT_SIZE;++i)
   assert(report[i]==(i>=tag&&i<tag+202?0:0xa5));
 }
}
""")
run('speaker-result-queue',r"""
#include <cstdint>
#include <cstring>
#include <cassert>
#include <cstdio>
#include <atomic>
using critical_section_t=int;
int locked=0;void critical_section_enter_blocking(int*){assert(!locked);locked=1;}
void critical_section_exit(int*){assert(locked);locked=0;}
uint32_t now=0;uint32_t get_absolute_time(){return now;}uint32_t to_ms_since_boot(uint32_t x){return x;}
"""+s[s.index('struct SpeakerFrame'):s.index('static uint8_t opus_silence_buf')]+extract(s,'static void publish_speaker_frame(')+'\n'+extract(s,'static bool take_speaker_frame(')+r"""
bool speaker_enabled=true,speaker_was_enabled=true,reset_stream=false,speaker_filters_reset=false;
bool plug_headset=false,speaker_was_headset=false;
unsigned audio_buf_pos=0;
int discards=0;void discard_speaker_queue(){++discards;}
void transition(){
"""+s[s.index('    const bool speaker_route_changed'):s.index('\n#endif',s.index('    const bool speaker_route_changed'))]+r"""
}
"""+r"""
int main(){
 uint32_t seq=0;uint8_t data[200]{},out[200]{};
 assert(!take_speaker_frame(out));
 data[0]=1;publish_speaker_frame(data,1,++seq);data[0]=2;publish_speaker_frame(data,1,++seq);
 assert(take_speaker_frame(out)&&out[0]==1);assert(take_speaker_frame(out)&&out[0]==2);
 assert(!take_speaker_frame(out)); // no replay of last frame
 for(int i=3;i<=5;i++){data[0]=i;publish_speaker_frame(data,1,++seq);}
 assert(take_speaker_frame(out)&&out[0]==4);assert(take_speaker_frame(out)&&out[0]==5);
 data[0]=6;publish_speaker_frame(data,1,++seq);now=25;data[0]=7;publish_speaker_frame(data,1,++seq);
 assert(take_speaker_frame(out)&&out[0]==7);assert(!take_speaker_frame(out));
 ++speaker_generation;opus_head=opus_count=0;publish_speaker_frame(data,1,++seq);assert(!take_speaker_frame(out));
 now=0xfffffff0;publish_speaker_frame(data,2,++seq);now=5;assert(take_speaker_frame(out));
 now=0xfffffff0;publish_speaker_frame(data,2,++seq);now=9;assert(!take_speaker_frame(out));
 assert(g_speaker_stats.overflow==1&&g_speaker_stats.stale==2&&g_speaker_stats.rejected_generation==1);
 assert(g_speaker_stats.published==9&&g_speaker_stats.consumed==6&&g_speaker_stats.underrun>0);
 for(int i=0;i<100;i++){
  uint32_t old=speaker_generation;publish_speaker_frame(data,old,++seq);
  speaker_enabled=!speaker_enabled;reset_stream=(i%3==0);transition();
  assert(opus_count==0&&speaker_generation==old+1);
  publish_speaker_frame(data,old,++seq);assert(!take_speaker_frame(out));
  publish_speaker_frame(data,speaker_generation,++seq);assert(take_speaker_frame(out));
 }
 assert(discards==100&&g_speaker_stats.resets==100);
 const uint32_t old=speaker_generation;
 reset_stream=false;audio_buf_pos=10;plug_headset=true;transition();
 assert(audio_buf_pos==0&&speaker_generation==old+1&&speaker_was_headset);
 publish_speaker_frame(data,old,++seq);assert(!take_speaker_frame(out));
 transition();assert(speaker_generation==old+1);
 assert(!locked);puts("PASS: FIFO, one-shot consumption, capacity, stale skip, generation and timer wrap");
}
""")

s=(root/'src/main.cpp').read_text(encoding='utf-8')
a=s.index('        const uint32_t audio_started_us');b=s.index('        interrupt_loop();',a)
run('usb-catchup',r"""
#include <cstdint>
#include <cassert>
#include <cstdio>
unsigned bytes=0,now=0,cost=100,calls=0,polls=0,tasks=0;bool progress=true;
unsigned tud_audio_available(){return bytes;}uint32_t time_us_32(){return now;}
void audio_loop(){++calls;now+=cost;if(progress)bytes=bytes>384?bytes-384:0;}
void cyw43_arch_poll(){++polls;}void tud_task(){++tasks;}
void usb_profile_event_task(){}
void service(){
"""+s[a:b]+r"""
}
int main(){
 service();assert(calls==1&&polls==0); // still services resets/microphone without OUT PCM
 calls=0;bytes=1152;service();assert(calls==3&&bytes==0&&polls==2&&tasks==2);
 calls=polls=tasks=0;bytes=10000;service();assert(calls==3&&polls==2); // hard iteration bound
 calls=polls=tasks=0;cost=300;bytes=1152;service();assert(calls==2&&polls==1);
 calls=polls=tasks=0;cost=100;bytes=1152;progress=false;service();assert(calls==1&&polls==0);
 progress=true;calls=0;now=0xfffffff0;bytes=768;service();assert(calls==2);
 puts("PASS: bounded catch-up, BT service, time budget, no-progress exit, timer wrap");
}
""")

# Inactive native mode must not update generated-haptics coefficient caches.
# Speaker-accent/leak synthesis was retired; its removed caches are not exercised.
s=(root/'src/audio.cpp').read_text(encoding='utf-8')
conditions=['auto_mode > 0 && cached_intensity != intensity','auto_mode > 0 && lp_fc != lp_fc_cached','auto_mode > 0 && cached_ENV_REL != smooth_cfg']
blocks=[]
for condition in conditions:
 a=s.index('    if ('+condition+')');b=s.index('\n    }',a)+6;blocks.append(s[a:b])
run('inactive-dsp',r"""
#include <cmath>
#include <cassert>
#include <cstdio>
#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif
int auto_mode=0;
int cached_intensity=-1,intensity=80,lp_fc=100,lp_fc_cached=0,cached_ENV_REL=-1,smooth_cfg=50;
float intensity_curved=0,lp_a=0,ENV_REL=0;
void update(){
"""+'\n'.join(blocks)+r"""
}
int main(){
 update();assert(cached_intensity==-1&&lp_fc_cached==0&&cached_ENV_REL==-1);
 auto_mode=1;update();
 assert(cached_intensity==80&&lp_fc_cached==100&&cached_ENV_REL==50);
 assert(lp_a>0&&ENV_REL>0&&std::isfinite(intensity_curved));
 puts("PASS: native skips coefficient work; first enabled block refreshes caches");
}
""")

s=(root/'src/audio.cpp').read_text(encoding='utf-8')
run('speaker-pcm-identity',r"""
#include <cstdint>
#include <cstring>
#include <deque>
#include <cassert>
#include <cstdio>
#define __not_in_flash_func(x) x
struct Stats{uint32_t pcm_created=0,pcm_dropped=0;}g_speaker_stats;
"""+s[s.index('struct audio_raw_element'):s.index('// Three fixed blocks')]+r"""
audio_raw_element speaker_blocks[3];std::deque<uint8_t> free_speaker_blocks{0,1,2},audio_fifo;
bool queue_try_remove(std::deque<uint8_t>*q,uint8_t*p){if(q->empty())return false;*p=q->front();q->pop_front();return true;}
bool queue_try_add(std::deque<uint8_t>*q,uint8_t*p){unsigned cap=q==&audio_fifo?2:3;if(q->size()==cap)return false;q->push_back(*p);return true;}
bool queue_is_full(std::deque<uint8_t>*q){return q->size()==2;}
void release_speaker_block(uint8_t i){assert(queue_try_add(&free_speaker_blocks,&i));}
"""+extract(s,'static void __not_in_flash_func(publish_speaker_block)')+r"""
int main(){float pcm[1024]{};for(int i=0;i<5;i++)publish_speaker_block(pcm,1,1+i%2);
 assert(g_speaker_stats.pcm_created==5&&g_speaker_stats.pcm_dropped==3);
 uint8_t i;assert(queue_try_remove(&audio_fifo,&i));assert(speaker_blocks[i].sequence==4&&speaker_blocks[i].channels==2);
 release_speaker_block(i);assert(queue_try_remove(&audio_fifo,&i));assert(speaker_blocks[i].sequence==5&&speaker_blocks[i].channels==1);
 puts("PASS: source identities survive PCM overflow; drops counted before encoder");}
""")

# Pace calibration by successful mouse reports, not main-loop iterations.
s=(root/'src/main.cpp').read_text(encoding='utf-8')
a=s.index('    // Keep calibration separate');b=s.index('\n}\n',a)
run('gyro-calibration',r"""
#include <algorithm>
#include <cassert>
#include <cstdint>
#include <cstdio>
using int32_t = std::int32_t;
struct Config{} cfg;
struct GyroMouseReport{uint8_t buttons;int16_t x,y;int8_t wheel;};
int32_t g_cal_remaining=17,g_gm_pend_x=3,g_gm_pend_y=-2;
constexpr int32_t CAL_STEP=8;
uint8_t mbtn=0,s_mbtn_sent=0;
bool ready=false,accept=false;
int sum=0,packets=0;
int8_t macro_mouse_peek_scroll(){return 0;}
void macro_mouse_take_scroll(){}
uint8_t usb_mouse_instance(Config){return 0;}
bool tud_hid_n_ready(uint8_t){return ready;}
bool tud_hid_n_report(uint8_t,int,const GyroMouseReport *report,size_t){
 if(!accept)return false;
 sum+=report->x;packets++;return true;
}
void tick(){
"""+s[a:b]+r"""
}
int main(){
 for(int i=0;i<300;i++)tick();
 assert(g_cal_remaining==17 && g_gm_pend_x==3 && packets==0);
 ready=true;tick();
 assert(g_cal_remaining==17 && g_gm_pend_x==3 && packets==0);
 accept=true;tick();
 assert(g_cal_remaining==9 && g_gm_pend_x==0 && g_gm_pend_y==0 && sum==11);
 tick();tick();tick();
 assert(g_cal_remaining==0 && packets==3 && sum==20);
 puts("PASS: busy/failed HID preserves counts; successful reports send at most 8 calibration counts each");
}
""")

# Actual legacy save command publishes pending/completion with an echoed request tag.
s=(root/'src/cmd.cpp').read_text(encoding='utf-8')
dispatcher=s[s.index('void pico_cmd_set('):]
a=dispatcher.index('        case 0x67: {');b=dispatcher.index('        case 0x15:',a)
live=(root/'src/config.cpp').read_text(encoding='utf-8')
run('settings-read-revision',r"""
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <vector>
#include "config.h"
Config config{};
std::vector<uint8_t> pico_portal_reply;
constexpr int CYW43_WL_GPIO_LED_PIN=1;
void cyw43_arch_gpio_put(int,bool){}
void config_valid(){}
void audio_mic_policy_changed(){}
void set_volume(uint8_t,uint8_t){}
void set_gain(uint8_t){}
uint32_t calc_config_crc(const Config &c){return c.body.speaker_volume;}
Config_body& get_config(){return config.body;}
bool active_profile_get(uint8_t &slot,bool &edited,uint8_t *name){slot=3;edited=true;memset(name,0,SLOT_NAME_LEN);return true;}
bool macro_uses_mute_button(){return false;}
"""+live[live.index('static uint32_t live_config_revision'):live.index('// ============================ Profile slots')]+r"""
void query(const uint8_t *buffer,uint16_t bufsize){switch(0x67){
"""+dispatcher[a:b]+r"""
}}
uint32_t word(unsigned offset){uint32_t value;memcpy(&value,pico_portal_reply.data()+offset,4);return value;}
int main(){
 uint8_t request[]{'R','1',0x12,0x34,0x56,0x78};
 config.body.speaker_volume=55;
 query(nullptr,0);assert(!memcmp(pico_portal_reply.data()+29,"REV1",4)&&word(41)==0);
 query(request,sizeof(request));assert(word(33)==0&&word(37)==55);
 assert(!memcmp(pico_portal_reply.data()+41,request+2,4));
 assert(pico_portal_reply[3]==3&&pico_portal_reply[4]==1&&!memcmp(pico_portal_reply.data()+22,"SLP2",4));
 Config_body next=config.body;next.speaker_volume=70;
 set_config(reinterpret_cast<const uint8_t *>(&next),sizeof(next));
 next.speaker_volume=55;set_config(reinterpret_cast<const uint8_t *>(&next),sizeof(next));
 query(request,sizeof(request));assert(word(33)==2&&word(37)==55);
 config.body.speaker_volume=40;query(request,sizeof(request));assert(word(33)==2&&word(37)==40);
 puts("PASS: profile header preserved; settings A-B-A advances revision; direct volume updates alter checksum");
}
""")
a=dispatcher.index('        case 0x04: {');b=dispatcher.index('        case 0x05:',a)
run('scalar-unsupported-field',r"""
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <vector>
std::vector<uint8_t> pico_portal_reply;
bool get_config_field(uint8_t fid,uint8_t *data,uint16_t){
 if(fid!=0x12)return false;
 *data=0;return true;
}
void query(const uint8_t *buffer,uint16_t bufsize){switch(4){
"""+dispatcher[a:b]+r"""
}}
int main(){
 uint8_t fid=0x12;
 query(&fid,1);assert(pico_portal_reply[2]==fid&&pico_portal_reply[3]==0&&pico_portal_reply[4]==0);
 fid=0xab;query(&fid,1);assert(pico_portal_reply[2]==0xff&&pico_portal_reply[3]==fid&&pico_portal_reply[4]==1);
 query(nullptr,0);assert(pico_portal_reply[2]==0xff&&pico_portal_reply[3]==0&&pico_portal_reply[4]==0);
 puts("PASS: valid scalar zero, explicitly unsupported field, and missing field ID have distinct responses");
}
""")
a=dispatcher.index('        case 0x0b: {');b=dispatcher.index('        case 0x0c:',a)
run('bulk-write-transaction',r"""
#include <algorithm>
#include <cassert>
#include <cmath>
#include <cstring>
#include <cstdio>
#include <vector>
#include "config.h"
Config_body live{};
std::vector<uint8_t> pico_portal_reply;
unsigned applies=0, led_tests=0;
Config_body& get_config(){return live;}
void set_config(const uint8_t *data,const uint16_t size){++applies;memcpy(&live,data,size);}
void battery_notify_test(uint8_t){++led_tests;}
"""+s[s.index('template<typename T>'):s.index('static uint8_t g_last_field_len')]+
extract(s,'static bool set_field_in(')+r"""
void write(const uint8_t *buffer,uint16_t bufsize){switch(0x0b){
"""+dispatcher[a:b]+r"""
}}
int main(){
 live.speaker_volume=100;live.headset_volume=70;
 const uint8_t invalid[]{2,2,1,55,0xfd,1,1}, truncated[]{2,2,1,55,3,1}, led[]{2,2,1,55,0x9e,1,0};
 for(auto request: {std::pair{invalid,sizeof(invalid)},std::pair{truncated,sizeof(truncated)},std::pair{led,sizeof(led)}}){
    write(request.first,request.second);
    assert(pico_portal_reply[2]==1&&pico_portal_reply[3]==0);
    assert(!applies&&!led_tests&&live.speaker_volume==100&&live.headset_volume==70);
 }
 const uint8_t valid[]{2,2,1,55,3,1,35};
 write(valid,sizeof(valid));assert(applies==1&&live.speaker_volume==55&&live.headset_volume==35);
 assert(pico_portal_reply[2]==0&&pico_portal_reply[3]==2);
 const uint8_t empty[]{0};write(empty,sizeof(empty));assert(applies==1&&pico_portal_reply[2]==0&&pico_portal_reply[3]==0);
 for(uint8_t mode:{0,1,2}){
    const uint8_t highpass[]{1,0xc9,1,mode};
    write(highpass,sizeof(highpass));
    assert(pico_portal_reply[2]==0&&live.ah_highpass==mode);
 }
 const auto before=applies;
 const uint8_t invalid_highpass[]{2,2,1,60,0xc9,1,3};
 write(invalid_highpass,sizeof(invalid_highpass));
 assert(pico_portal_reply[2]==1&&applies==before&&live.ah_highpass==2&&live.speaker_volume==55);
 puts("PASS: a rejected chunk leaves RAM and LED state unchanged; a valid chunk applies once");
}
""")
a=s.index('        case 0x02: {',s.index('void pico_cmd_set('));b=s.index('        case 0x03:',a)
run('config-save-reply',r"""
#include <cstdint>
#include <cstring>
#include <cassert>
#include <cstdio>
#include <unordered_map>
#include <vector>
std::vector<uint8_t> pico_settings_reply;
bool save_ok=true;int saves=0;
bool config_save(){++saves;const auto &p=pico_settings_reply;assert(p.size()==63&&p[0]==0x66&&p[1]==2&&p[2]==0xfe&&p[3]==1);return save_ok;}
void command(const uint8_t *buffer,uint16_t bufsize){switch(2){
"""+s[a:b]+r"""
}}
int main(){uint8_t tag[]{0x12,0x34,0x56,0x78};
 for(bool ok:{true,false}){save_ok=ok;command(tag,4);const auto &r=pico_settings_reply;assert(r[2]==(ok?0:2)&&r[3]==1&&!memcmp(r.data()+4,tag,4));}
 command(nullptr,0);for(int i=4;i<8;i++)assert(pico_settings_reply[i]==0);assert(saves==3);
 puts("PASS: pending before flash, success/failure, request-tag echo and legacy empty payload");}
""")

cases=[]
for command in ('08','19','1c','1d','21','22'):
 start=dispatcher.index(f'        case 0x{command}: {{')
 cases.append(dispatcher[start:dispatcher.index('\n        }',start)+10])
run('settings-write-replies',r"""
#include <algorithm>
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <vector>
constexpr unsigned SLOT_NAME_LEN=16, SLOT_COUNT=32;
std::vector<uint8_t> pico_settings_reply;
bool ok=true, policy=false;
int writes=0;
bool slot_save(uint8_t idx,const uint8_t *name,uint8_t len){
    ++writes;assert(idx==4&&len==16&&!memcmp(name,"0123456789ABCDEF",16));
    assert(pico_settings_reply[2]==0xfe);return ok;
}
bool macro_commit(){++writes;return ok;}
bool set_policy(bool value){++writes;if(ok)policy=value;return ok;}
bool device_set_auto_dormant(bool v){return set_policy(v);}
bool device_set_disconnect_on_dock(bool v){return set_policy(v);}
bool device_set_usb_serial_hidden(bool v){return set_policy(v);}
bool device_auto_dormant(){return policy;}
bool device_disconnect_on_dock(){return policy;}
bool device_usb_serial_hidden(){return policy;}
void manual_power_note_activity(unsigned=0){}
"""+extract(s,'static void echo_settings_write_tag(')+r"""
void command(uint8_t cmd,const uint8_t *buffer,uint16_t bufsize){switch(cmd){
"""+'\n'.join(cases)+r"""
}}
int main(){
    uint8_t p[61]{}, tag[]{0x89,0x67,0x45,0x23};
    memcpy(p+57,tag,4);
    command(0x22,p,61);
    assert(pico_settings_reply[2]==0&&pico_settings_reply[3]==1&&writes==0);
    assert(!memcmp(pico_settings_reply.data()+59,tag,4));
    p[0]=4;memcpy(p+1,"0123456789ABCDEF",16);
    command(8,p,61);assert(pico_settings_reply[2]==0&&pico_settings_reply[3]==4);
    assert(!memcmp(pico_settings_reply.data()+59,tag,4));
    command(8,p,17);assert(pico_settings_reply[2]==0&&pico_settings_reply[59]==0);
    ok=false;command(0x19,p,61);assert(pico_settings_reply[2]==1);
    assert(!memcmp(pico_settings_reply.data()+59,tag,4));
    ok=true;command(0x19,nullptr,0);assert(pico_settings_reply[2]==0&&pico_settings_reply[59]==0);
    for(uint8_t id:{0x1c,0x1d,0x21}){
        policy=false;p[0]=1;p[1]=1;ok=true;command(id,p,61);
        assert(policy&&pico_settings_reply[2]==0&&pico_settings_reply[4]==1);
        assert(!memcmp(pico_settings_reply.data()+59,tag,4));
        p[1]=0;ok=false;command(id,p,61);
        assert(policy&&pico_settings_reply[2]==2&&pico_settings_reply[4]==1);
        assert(!memcmp(pico_settings_reply.data()+59,tag,4));
        p[0]=0;command(id,p,61);
        assert(pico_settings_reply[2]==0&&pico_settings_reply[4]==1&&pico_settings_reply[59]==0);
    }
    assert(writes==10);
    puts("PASS: actual dispatch cases, tagged outcomes, legacy slot/macro, policy reads and failure");
}
""")
