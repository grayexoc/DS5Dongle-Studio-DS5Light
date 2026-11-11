"""Compile extracted production paths with host hardware mocks; no firmware build."""
from pathlib import Path
import os, subprocess, re
root=Path(__file__).resolve().parents[1]
base=root.parent/'DS5Dongle-Studio-build'
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
uint32_t crc32(const uint8_t*p,unsigned n){uint32_t c=~0u;while(n--){c^=*p++;for(int i=0;i<8;i++)c=(c>>1)^(0xedb88320u&-(c&1));}return ~c;}
void step(){if(++operation==cut)throw 1;}
void flash_range_erase(uint32_t off,uint32_t n){for(unsigned i=0;i<n;i+=256){memset(flashmem+off+i,255,256);step();}}
void flash_range_program(uint32_t off,const uint8_t*p,uint32_t n){for(unsigned i=0;i<n;i+=4){for(unsigned j=0;j<4;j++)flashmem[off+i+j]&=p[i+j];step();}}
"""+s+r"""
int main(){
 uint8_t before[20480],old[4096],fresh[4096];
 memset(flashmem,255,sizeof flashmem);memset(old,0x12,sizeof old);memset(fresh,0x34,sizeof fresh);
 memcpy(flashmem,old,4096);memcpy(flashmem+4096,old,4096);memcpy(before,flashmem,sizeof before);
 assert(storage_redo_write(0,fresh,4096));int total=operation;
 for(int at=1;at<=total;at++){
  memcpy(flashmem,before,sizeof before);operation=0;cut=at;
  try{storage_redo_write(0,fresh,4096);}catch(int){}
  cut=0;assert(storage_redo_recover());assert(storage_redo_recover());
  assert(!memcmp(flashmem,old,4096)||!memcmp(flashmem,fresh,4096));
  assert(!memcmp(flashmem+4096,old,4096));
 }
 // Power can fail again during boot recovery. Keep the committed redo until verified.
 memcpy(flashmem,before,sizeof before);operation=0;cut=16+16+1024+64;
 try{storage_redo_write(0,fresh,4096);}catch(int){}
 uint8_t pending[20480];memcpy(pending,flashmem,sizeof pending);
 cut=0;operation=0;assert(storage_redo_recover());int recovery_steps=operation;
 for(int at=1;at<=recovery_steps;at++){
  memcpy(flashmem,pending,sizeof pending);operation=0;cut=at;
  try{storage_redo_recover();}catch(int){}
  cut=0;assert(storage_redo_recover());assert(!memcmp(flashmem,fresh,4096));
 }
 printf("PASS: %d interrupted boot recoveries\n",recovery_steps);
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
bool queue_try_remove(std::deque<send_element>*q,send_element*p){if(q->empty())return false;*p=q->front();q->pop_front();return true;}
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
 send_fifo.clear();native_queued=0;control[5]=120;bt_write(control,78);control[5]=0;bt_write(control,78);control[5]=120;bt_write(control,78);
 assert(send_fifo.size()==3);bt_write(control,78);assert(send_fifo.size()==3);
 send_fifo.clear();native_queued=0;for(int i=0;i<10;i++){control[5]=i;bt_write(control,78);}
 assert(send_fifo.size()==10);bt_write(audio,398);assert(send_fifo.size()==10);
 puts("PASS: actual bt_write: repeated control bounded, audio eviction, distinct control preserved, full control queue");
}
""")

s=(root/'src/audio.cpp').read_text(encoding='utf-8')
start=s.index('            memmove(pkt + 11');end=s.index('\n        }',start)
run('packet',r"""
#include <cassert>
#include <cstring>
#include <cstdint>
#include <cstdio>
int main(){
 uint8_t pkt[398]{};pkt[0]=0x36;pkt[12]=63;pkt[76]=0x92;pkt[77]=64;
 for(int i=0;i<64;i++)pkt[78+i]=i;
 pkt[142]=0x93;pkt[143]=200;
 for(int i=0;i<200;i++)pkt[144+i]=i;
"""+s[start:end]+r"""
 assert(pkt[11]==0x92&&pkt[12]==64);
 for(int i=0;i<64;i++)assert(pkt[13+i]==i);
 assert(pkt[77]==0x93&&pkt[78]==200);
 for(int i=0;i<200;i++)assert(pkt[79+i]==i);
 for(int i=329;i<394;i++)assert(pkt[i]==0);
 puts("PASS: actual native packet rearrangement, both payloads and tail");
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
struct Config{uint8_t speaker_volume=60,headset_volume=70,sync_spk_headset_volume=0;}cfg;
Config&get_config(){return cfg;}
uint8_t speaker=0,headset=0,mute[2]{};
float volume[2]{};uint8_t reply[8]{};
void set_volume(uint8_t s,uint8_t h){speaker=s;headset=h;}
bool tud_audio_buffer_and_schedule_control_xfer(uint8_t,const tusb_control_request_t*,const void*p,unsigned n){memcpy(reply,p,n);return true;}
"""+extract(s,'static bool audio10_set_req_entity(')+'\n'+extract(s,'static bool audio10_get_req_entity(')+r"""
int main(){
 tusb_control_request_t q{2<<8,2<<8,2,1};int16_t input=-20*256;
 assert(audio10_set_req_entity(&q,reinterpret_cast<uint8_t*>(&input)));
 assert(speaker==80&&headset==70&&cfg.speaker_volume==80);
 q.bRequest=0x81;assert(audio10_get_req_entity(0,&q));int16_t got;memcpy(&got,reply,2);assert(got==input);
 cfg.sync_spk_headset_volume=1;input=-100*256;q.bRequest=1;
 assert(audio10_set_req_entity(&q,reinterpret_cast<uint8_t*>(&input)));assert(speaker==0&&headset==0);
 input=0;assert(audio10_set_req_entity(&q,reinterpret_cast<uint8_t*>(&input)));assert(speaker==100&&headset==100);
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
#define STUDIO_XINPUT_EXPERIMENT
bool active=false;bool usb_xinput_active(){return active;}bool ds_mode(){return true;}
const char* string_desc_arr[]={"en","maker","pad","serial","extra"};
const uint16_t *check(uint8_t index){size_t chr_count;
"""+s[a:b]+r"""
 static uint16_t result;result=chr_count;return &result;}
int main(){for(int mode=0;mode<2;mode++){active=mode;assert(check(2));assert(check(0xee)==nullptr);assert(check(255)==nullptr);assert((check(5)!=nullptr)==active);}puts("PASS: actual string resolver, invalid index, XInput audio name");}
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
uint32_t get_absolute_time(){return mic_now_mock;} uint32_t to_ms_since_boot(uint32_t t){return t;}
float volume[2]{};
int stale_mic=0;int mic_decode_fifo;uint8_t mute[2]{};int16_t captured[960]{};
bool queue_try_remove(int*,mic_decode_element*p){if(!p)return false;for(int i=0;i<480;i++)p->data[i]=i+1;p->len=960;p->generation=mic_stream_generation-stale_mic;return true;}
unsigned write_limit=1920,capture_bytes=0;
uint16_t tud_audio_write(const void*p,uint16_t n){n=std::min<unsigned>(n,write_limit);memcpy(captured,p,n);capture_bytes=n;return n;}
void process(){
"""+s[a:b]+r"""
}
int main(){process();assert(captured[0]==1&&captured[1]==1&&captured[959]==480);mute[1]=1;process();for(auto x:captured)assert(x==0);mute[1]=0;process();assert(captured[0]==1);volume[1]=20;process();assert(captured[959]==4800);volume[1]=48;process();assert(captured[959]==32767);volume[1]=-20;process();assert(captured[959]==480);volume[1]=0;write_limit=400;process();assert(captured[199]==100);process();assert(captured[0]==101);
 mic_active=false;capture_bytes=0;process();assert(capture_bytes==0);mic_active=true;++mic_stream_generation;write_limit=1920;process();assert(captured[0]==1);
 write_limit=0;process();mic_now_mock+=20;write_limit=1920;process();assert(captured[0]==1);
 capture_bytes=0;stale_mic=1;process();assert(capture_bytes==0);stale_mic=0;process();assert(capture_bytes>0);
 puts("PASS: USB mic gain/mute, partial writes, close/reopen, bounded pending age");}
""")

s=(root/'src/audio.cpp').read_text(encoding='utf-8')
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
bool link=true,audio_input_seen=false,stream_reset_requested=false,speaker_filters_reset=false;
uint32_t now=0,last_audio_input_ms=0;int resets=0,clears=0,discards=0;
struct Resampler{void Reset(){resets++;}}resampler;
void __sev(){} bool bt_is_ready(){return link;}
uint32_t get_absolute_time(){return now;}uint32_t to_ms_since_boot(uint32_t x){return x;}
void tud_audio_clear_ep_out_ff(){clears++;}void bt_discard_audio(){discards++;}
struct Positions{uint speaker;int haptic;uint remainder;};
Positions tick(bool seed){
"""+s[a:b]+r"""
 if(seed){audio_buf_pos=300;haptic_buf_pos=20;usb_remainder_bytes=3;audio_input_seen=true;last_audio_input_ms=now;}
 return {audio_buf_pos,haptic_buf_pos,usb_remainder_bytes};
}
int main(){
 tick(true);now=10;auto p=tick(false);assert(p.speaker==300&&p.haptic==20);
 stream_reset_requested=true;audio_input_seen=false;p=tick(false);
 assert(!p.speaker&&!p.haptic&&!p.remainder&&speaker_filters_reset);
 int n=resets;tick(false);assert(resets==n);
 tick(true);now+=60;p=tick(false);assert(!p.speaker&&!p.haptic&&!audio_input_seen);
 tick(true);config.auto_haptics_enable=0;p=tick(false);assert(!p.haptic);
 tick(true);link=false;p=tick(false);assert(!p.haptic);link=true;tick(false);
 assert(resets==discards&&clears==4);
 for(int i=0;i<100;i++){
  tick(true);config.auto_haptics_enable^=1;p=tick(false);assert(!p.haptic&&!p.speaker&&!p.remainder);
  tick(true);stream_reset_requested=true;p=tick(false);assert(!p.haptic&&!p.speaker&&!p.remainder);
  tick(true);link=false;p=tick(false);assert(!p.haptic);link=true;p=tick(false);assert(!p.haptic);
 } // timeout and mode switch preserve queued fresh USB PCM
 puts("PASS: actual partial buffers reset on close, timeout, mode and link change; steady stream preserved");
}
""")
a=s.index('    if (speaker_filters_reset) {');b=s.index('    const bool dsp_rear',a)
block=s[a:b]
variables=sorted(set(re.findall(r'\b([a-z][a-z0-9_]*)\s*=',block))-{'speaker_filters_reset'})
run('dsp-reset','#include <cassert>\n#include <cstdio>\nint main(){\nbool speaker_filters_reset=true;\n'+''.join('float '+x+'=1;\n' for x in variables)+block+''.join('assert('+x+'==0);\n' for x in variables)+'assert(!speaker_filters_reset);puts("PASS: actual DSP reset clears all envelope, carrier and native filter memories");}\n')

s=(root/'src/state_mgr.cpp').read_text(encoding='utf-8')
a=s.index('    // Synthetic ticks');b=s.index('    // XInput rumble',a)
run('synth-audio-authority',r"""
#include <cstdint>
#include <cassert>
#include <cstdio>
int main(){uint8_t copy[63]{};copy[0]=0xff;copy[1]=0xff;
"""+s[a:b]+r"""
assert(copy[0]==0x0f&&copy[1]==0x7d);
assert(!(copy[0]&0xf0)&&!(copy[1]&0x82));
puts("PASS: synthetic replay removes audio/volume authority and preserves trigger/motor selectors");}
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
"""+extract(s,'bool bt_control_send(')+'\n'+extract(s,'static void bt_control_send_ready()')+r"""
int main(){
 uint8_t a[]{0x53,0x60},b[]{0x43,0x70};
 assert(bt_control_send(a,2)&&bt_control_send(b,2));
 bt_control_send_ready();assert(writes==0&&control_fifo.front().data[1]==0x60);
 status=0;bt_control_send_ready();assert(last==0x60&&writes==1);bt_control_send_ready();assert(last==0x70&&writes==1);
 status=1;assert(bt_control_send(a,2));for(int i=0;i<3;i++)bt_control_send_ready();assert(control_fifo.empty()&&writes==1);
 for(int i=0;i<8;i++)assert(bt_control_send(b,2));assert(!bt_control_send(a,2));
 control_fifo.clear();hid_control_open=false;assert(!bt_control_send(a,2));
 puts("PASS: ordered retry, successful-send notification, retry limit, queue admission");
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
run('speaker-result-queue',r"""
#include <cstdint>
#include <cstring>
#include <cassert>
#include <cstdio>
using critical_section_t=int;
int locked=0;void critical_section_enter_blocking(int*){assert(!locked);locked=1;}
void critical_section_exit(int*){assert(locked);locked=0;}
uint32_t now=0;uint32_t get_absolute_time(){return now;}uint32_t to_ms_since_boot(uint32_t x){return x;}
"""+s[s.index('struct SpeakerFrame'):s.index('static uint8_t opus_silence_buf')]+extract(s,'static void publish_speaker_frame(')+'\n'+extract(s,'static bool take_speaker_frame(')+r"""
bool speaker_enabled=true,speaker_was_enabled=true,reset_stream=false,speaker_filters_reset=false;
int discards=0;void discard_speaker_queue(){++discards;}
void transition(){
"""+s[s.index('    if (speaker_enabled != speaker_was_enabled || reset_stream)'):s.index('\n#endif',s.index('    if (speaker_enabled != speaker_was_enabled || reset_stream)'))]+r"""
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

# Inactive native mode must not update auto-haptic/leak coefficient caches.
s=(root/'src/audio.cpp').read_text(encoding='utf-8')
conditions=['auto_mode > 0 && cached_intensity != intensity','auto_mode > 0 && lp_fc != lp_fc_cached','auto_mode > 0 && cached_ENV_REL != smooth_cfg','leak_active && ohp_fc != ohp_fc_cached','leak_active && olp_fc != olp_fc_cached','leak_active && mk_now != mk_key','leak_active && hp_fc != hp_fc_cached','leak_active && cached_TRANS_RATIO != sens_cfg','leak_active && cached_GATE_OPEN != atk_cfg','leak_active && cached_GATE_CLOSE != decay_cfg']
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
int auto_mode=0;bool leak_active=false;
int cached_intensity=-1,intensity=80,lp_fc=100,lp_fc_cached=0,cached_ENV_REL=-1,smooth_cfg=50;
float intensity_curved=0,lp_a=0,ENV_REL=0;
float ohp_fc=400,ohp_fc_cached=-1,ohp_a=0,olp_fc=3500,olp_fc_cached=-1,olp_a=0;
unsigned mk_now=1,mk_key=0;float leak_makeup=1;
float hp_fc=300,hp_fc_cached=-1,hp_a=0;
int cached_TRANS_RATIO=-1,sens_cfg=50,cached_GATE_OPEN=-1,atk_cfg=50,cached_GATE_CLOSE=-1,decay_cfg=50;
float TRANS_RATIO=0,GATE_OPEN=0,GATE_CLOSE=0;
void update(){
"""+'\n'.join(blocks)+r"""
}
int main(){
 update();assert(cached_intensity==-1&&lp_fc_cached==0&&cached_ENV_REL==-1);
 assert(ohp_fc_cached==-1&&olp_fc_cached==-1&&mk_key==0&&hp_fc_cached==-1);
 assert(cached_TRANS_RATIO==-1&&cached_GATE_OPEN==-1&&cached_GATE_CLOSE==-1);
 auto_mode=1;leak_active=true;update();
 assert(cached_intensity==80&&lp_fc_cached==100&&cached_ENV_REL==50);
 assert(ohp_fc_cached==400&&olp_fc_cached==3500&&mk_key==1&&hp_fc_cached==300);
 assert(cached_TRANS_RATIO==50&&cached_GATE_OPEN==50&&cached_GATE_CLOSE==50);
 assert(lp_a>0&&ohp_a>0&&olp_a>0&&hp_a>0&&std::isfinite(leak_makeup));
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
int main(){float pcm[1024]{};for(int i=0;i<5;i++)publish_speaker_block(pcm,1);
 assert(g_speaker_stats.pcm_created==5&&g_speaker_stats.pcm_dropped==3);
 uint8_t i;assert(queue_try_remove(&audio_fifo,&i));assert(speaker_blocks[i].sequence==4);
 release_speaker_block(i);assert(queue_try_remove(&audio_fifo,&i));assert(speaker_blocks[i].sequence==5);
 puts("PASS: source identities survive PCM overflow; drops counted before encoder");}
""")

# Actual legacy save command publishes pending/completion with an echoed request tag.
s=(root/'src/cmd.cpp').read_text(encoding='utf-8')
a=s.index('        case 0x02: {',s.index('void pico_cmd_set('));b=s.index('        case 0x03:',a)
run('config-save-reply',r"""
#include <cstdint>
#include <cstring>
#include <cassert>
#include <cstdio>
#include <unordered_map>
#include <vector>
std::unordered_map<uint8_t,std::vector<uint8_t>> feature_data;
bool save_ok=true;int saves=0;
bool config_save(){++saves;const auto &p=feature_data[0x84];assert(p.size()==63&&p[0]==0x66&&p[1]==2&&p[2]==0xfe&&p[3]==1);return save_ok;}
void command(const uint8_t *buffer,uint16_t bufsize){switch(2){
"""+s[a:b]+r"""
}}
int main(){uint8_t tag[]{0x12,0x34,0x56,0x78};
 for(bool ok:{true,false}){save_ok=ok;command(tag,4);const auto &r=feature_data[0x84];assert(r[2]==(ok?0:2)&&r[3]==1&&!memcmp(r.data()+4,tag,4));}
 command(nullptr,0);for(int i=4;i<8;i++)assert(feature_data[0x84][i]==0);assert(saves==3);
 puts("PASS: pending before flash, success/failure, request-tag echo and legacy empty payload");}
""")
