"""Exercise the actual command handlers and counter encoder without hardware."""
from pathlib import Path
import os
import subprocess

root = Path(__file__).resolve().parents[1]
base = root.parent / 'DS5Dongle-Studio-build'
out = base / 'reports/device-diagnostics-tests'
out.mkdir(parents=True, exist_ok=True)
source = (root / 'src/cmd.cpp').read_text(encoding='utf-8')
dispatch = source.index('void pico_cmd_set(')
commands = source[source.index('        case 0x1e: {\n',dispatch):source.index('        case 0x1d: {\n',dispatch)]
assert 'case 0x20:' in commands
setter = source.index('static bool set_field_in(')
assert 'case 0x20:' not in source[setter:source.index('\n}',setter)]
bt = (root / 'src/bt.cpp').read_text(encoding='utf-8')
start = bt.index('void bt_diagnostic_snapshot(')
counter = bt[start:bt.index('\n}', start) + 2]
stats = bt[bt.index('struct AudioTransportStats {'):bt.index('constexpr uint32_t kMixedAudioAgeMs')]
stats = stats[:stats.index('void bt_diagnostic_snapshot(')]
state_source = (root / 'src/state_mgr.cpp').read_text(encoding='utf-8')
state_start = state_source.index('bool state_output_test(')
start_test = state_source[state_start:state_source.index('\n}', state_start) + 2]
code = r'''
#include <cassert>
#include <cstdint>
#include <cstring>
#include <map>
#include <vector>
#include <cstdio>
#include "state_mgr.h"
#include "output_diagnostics.h"
std::map<uint8_t,std::vector<uint8_t>> feature_data;
bool ready=true, processing=false;
uint8_t auto_mode=0;
OutputTest output_test;
uint8_t state[47]{}, g_host_cache[47]{}, g_host_cache_size=47;
bool game_ever_r2=false, game_ever_l2=false;
unsigned starts=0, activity=0;
bool chime_ok=true;unsigned chimes=0;
bool audio_profile_chime(){++chimes;return chime_ok;}
struct Config {uint8_t auto_haptics_enable=0;} config;
Config &get_config(){config.auto_haptics_enable=auto_mode;return config;}
enum class ManualPowerState {Idle, Stopping};
ManualPowerState power=ManualPowerState::Idle;
ManualPowerState manual_power_state(){return power;}
void manual_power_note_activity(unsigned){++activity;}
void state_rumble_reset(){++starts;}
bool bt_is_connected(){return true;}
bool bt_is_ready(){return ready;}
bool audio_processing_active(){return processing;}
bool audio_haptics_stream_active(){return false;}
uint8_t audio_diagnostic_route(){return 2;}
void audio_diagnostic_snapshot(uint8_t *p){
 const uint32_t counters[]={0xffffffff,2,3,4};memcpy(p,counters,sizeof(counters));
}
bool bt_signal_valid(){return true;}
bool usb_xinput_active(){return true;}
void bt_get_signal_strength(int8_t *p){*p=-42;}
volatile uint16_t g_diag_ch01_peak=100,g_diag_ch23_peak=200;
uint16_t g_diag_rear_left_peak=100,g_diag_rear_right_peak=200;
uint32_t g_diag_usb_audio_blocks=0x12345678;
volatile uint8_t g_diag_actual_ch=4;
uint32_t get_absolute_time(){return 1234;}
uint32_t to_ms_since_boot(uint32_t n){return n;}
void state_diagnostic_snapshot(uint8_t *p){p[0]=3;p[1]=3;p[9]=1;p[17]=1;}
unsigned send_fifo=4;bool pending_send_valid=true;
unsigned queue_get_level(unsigned *p){return *p;}
'''+start_test+stats+counter+r'''
void command(uint8_t id,const uint8_t *buffer,uint16_t bufsize){switch(id){
'''+commands+r'''
}}
int main(){
 uint8_t payload[5]={0,0x12,0x34,0x56,0x78};
 command(0x1e,payload,5);auto r=feature_data[0x84];
 assert(r.size()==63&&r[2]==0&&r[3]==1&&r[4]==0&&!memcmp(r.data()+5,payload+1,4));
 assert(r[9]==19&&r[10]==1&&r[12]==4&&r[13]==100&&r[15]==200&&r[17]==uint8_t(-42));
 assert(r[18]==3&&r[19]==3&&r[27]==1&&r[35]==1&&r[43]==uint8_t(1234));
 assert(r[47]==1&&r[48]==100&&r[50]==200&&r[52]==0x78&&r[55]==0x12&&r[56]==1&&r[57]==1&&r[58]==2);
 assert(starts==0&&activity==0);
 g_audio_transport_stats.sent=0xffffffff;g_audio_transport_stats.retries=9;
 payload[0]=1;command(0x1e,payload,5);r=feature_data[0x84];
 assert(r[9]==255&&r[12]==255&&r[41]==9&&r[45]==5);
 for(unsigned n=0;n<5;++n){command(0x1e,payload,n);assert(feature_data[0x84][2]==1);}
 payload[0]=2;command(0x1e,payload,5);r=feature_data[0x84];
 assert(r[2]==0&&r[4]==2&&!memcmp(r.data()+5,payload+1,4));
 assert(r[9]==255&&r[12]==255&&r[13]==2&&r[17]==3&&r[21]==4);
 payload[0]=3;command(0x1e,payload,5);assert(feature_data[0x84][2]==1);
 for(unsigned kind=1;kind<=15;++kind){
  payload[0]=kind;command(0x1f,payload,5);
  assert(feature_data[0x84][2]==0&&output_test.kind==kind);
 }
 unsigned before=starts;payload[0]=16;command(0x1f,payload,5);
 assert(feature_data[0x84][2]==1&&starts==before&&output_test.kind==15);
 payload[0]=1;processing=true;command(0x1f,payload,5);assert(starts==before);
 processing=false;auto_mode=1;command(0x1f,payload,5);assert(starts==before);
 auto_mode=0;ready=false;command(0x1f,payload,5);assert(starts==before);
 ready=true;power=ManualPowerState::Stopping;command(0x1f,payload,5);assert(starts==before);
 payload[0]=0;processing=true;command(0x1f,payload,5);
 assert(feature_data[0x84][2]==0&&output_test.kind==0&&output_test.release&&starts==before);
 // Capability and preview requests must reach the real command dispatch.
 payload[0]=0;before=activity;command(0x20,payload,5);r=feature_data[0x84];
 assert(r.size()==63&&r[0]==0x66&&r[1]==0x20&&r[2]==0&&r[3]==1&&r[4]==0&&r[9]==0x1f);
 assert(!memcmp(r.data()+5,payload+1,4)&&chimes==0&&activity==before);
 for(unsigned n=0;n<5;++n){command(0x20,payload,n);assert(feature_data[0x84][2]==1);}
 payload[0]=2;command(0x20,payload,5);assert(feature_data[0x84][2]==1&&chimes==0);
 payload[0]=1;command(0x20,payload,5);r=feature_data[0x84];
 assert(r[2]==0&&r[4]==1&&!memcmp(r.data()+5,payload+1,4)&&chimes==1&&activity==before+1);
 chime_ok=false;command(0x20,payload,5);assert(feature_data[0x84][2]==2&&chimes==2);
 puts("PASS: real diagnostic/test/extension commands: tags, capabilities, preview gates, malformed payload and no read side effects");
}
'''
(out / 'commands.cpp').write_text(code, encoding='utf-8')
bin_dir = base / 'source/toolchain/mingw64/mingw64/bin'
env = dict(os.environ)
env['PATH'] = str(bin_dir) + os.pathsep + env.get('PATH', '')
subprocess.run([str(bin_dir / 'g++.exe'), '-std=c++17', '-Wall', '-Wextra', '-I'+str(root / 'src'),
                str(out / 'commands.cpp'), '-o', str(out / 'commands.exe')], env=env, check=True)
result = subprocess.run([str(out / 'commands.exe')], env=env, check=True, capture_output=True, text=True)
(out / 'result.txt').write_text(result.stdout + result.stderr, encoding='utf-8')
print(result.stdout)
