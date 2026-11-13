"""Host regression of production mix, motor ownership/cache, stream timeout and queue fields."""
from pathlib import Path
import os, subprocess
root=Path(__file__).resolve().parents[1]
base=root.parent/'DS5Dongle-Studio-build'
out=base/'reports/haptic-delivery-tests';out.mkdir(parents=True,exist_ok=True)
bin_dir=base/'source/toolchain/mingw64/mingw64/bin'
env=dict(os.environ);env['PATH']=str(bin_dir)+os.pathsep+env.get('PATH','')
source=(root/'src/state_mgr.cpp').read_text(encoding='utf-8')
audio=(root/'src/audio.cpp').read_text(encoding='utf-8')
def extract(s, signature):
    start=s.index(signature);return s[start:s.index('\n}',start)+2]
block=source[source.index('    state.EnableRumbleEmulation = update.'):source.index('    if (!get_config().lock_volume')]
code=r"""
#include <cassert>
#include <cstring>
#include <cstdio>
#include <cmath>
#include "haptic_mix.h"
#include "rumble_delivery.h"
#include "rumble_shape.h"
#include "output_diagnostics.h"
OutputDiagnostics output_diagnostics;
OutputTest output_test;
void state_host_led_update(const uint8_t *,uint8_t){}
struct SetStateData {uint8_t bytes[63];};
uint8_t g_host_cache[63]{},g_host_cache_size=0;bool g_host_motor_valid=false;
uint32_t g_last_host_ms=0,g_last_rumble_ms=0,now=0,last_audio_input_ms=0;
bool audio_input_seen=false,connected=true,xinput=true;
bool bt_is_ready(){return connected;}
bool usb_xinput_active(){return xinput;}
uint32_t get_absolute_time(){return now;}
uint32_t to_ms_since_boot(uint32_t t){return t;}
uint8_t captured[63];
bool state_update_apply(const uint8_t *p,uint8_t n){SetStateData update{};memcpy(&update,p,n);refresh_rumble_fields(reinterpret_cast<uint8_t*>(&update),p);memcpy(captured,&update,63);return true;}
struct Motor {
 bool EnableRumbleEmulation=false,UseRumbleNotHaptics=false,EnableImprovedRumbleEmulation=false;
 bool AllowRightTriggerFFB=false,AllowLeftTriggerFFB=false;
 uint8_t RumbleEmulationLeft=0,RumbleEmulationRight=0;
} state;
struct Config {int auto_haptics_enable=1,rumble_gain=100,rumble_release=0,rumble_mode=0;} config;
Config &get_config(){return config;}
volatile uint8_t g_rumble_l=0,g_rumble_r=0;
RumbleShape rumble_shape;bool rumble_output_pending=false;
"""
code+=extract(audio,'bool audio_haptics_stream_active()')+'\n'
code+=extract(source,'bool state_update(')+'\n'
code+='void apply(const Motor &update,uint8_t size=63) { const Motor old_state=state;\n'+block+'}\n'
bt=(root/'src/bt.cpp').read_text(encoding='utf-8')
refresh=bt[bt.index('                    if (auto *queued = pending_send.data[1]'):bt.index('                    const uint8_t status = l2cap_send')]
code+=r'''
struct {uint8_t data[100]{};unsigned len=79;} pending_send;
'''+extract(bt,'static const uint8_t *output_report_state(')+r'''
void state_refresh_rumble(uint8_t *p){p[0]&=~3u;p[38]&=~4u;p[2]=p[3]=0;}
unsigned checksum_updates=0;
void fill_output_report_checksum(uint8_t *,unsigned){++checksum_updates;}
void check_control_transition(){
 for(uint8_t id: {uint8_t(0x31),uint8_t(0x36)}) {
  pending_send.data[1]=id;pending_send.len=100;
  pending_send.data[13]=63;
  const unsigned motor = id==0x31?6:16;
  pending_send.data[motor]=120;
'''+refresh+r'''
  assert(pending_send.data[motor]==(id==0x31?120:0));
  assert(checksum_updates==(id==0x31?0:1));
 }
'''+refresh+r'''
 assert(checksum_updates==1); // The already-refreshed retry retains its checksum.
}
'''
code='#include <initializer_list>\n'+code
code+=r"""
int main(){
 check_control_transition(); // pending START survives a newer STOP; stale audio is refreshed
 // Mix stays linear below the knee, including opposite-polarity cancellation.
 for(int d=-90;d<=90;d++) {
   const float v=d/100.f;
   assert(std::fabs(haptic_mix(0,v)-v)<1e-6f);
 }
 assert(std::fabs(haptic_mix(0,.8f-.7f)-.1f)<1e-6f);
 assert(std::fabs(haptic_mix(0,.3f+.4f)-.7f)<1e-6f);
 const float at_one=haptic_mix(0,1);
 assert(std::fabs(at_one-.95f)<1e-6f);
 float previous=0;
 for(int i=0;i<=2000;i++) {
   const float x=i/1000.f,y=haptic_mix(0,x);
   assert(y>=previous&&y<=1&&y<=x+1e-6f);
   assert(std::fabs(y+haptic_mix(0,-x))<1e-6f);
   previous=y;
 }
 assert(std::fabs(haptic_mix(.5f,.3f)-.8f)<1e-6f);
 assert(std::fabs(haptic_mix(.7f,-.45f)-.25f)<1e-6f);
 assert(std::fabs(haptic_mix(-.7f,.45f)+.25f)<1e-6f);
 assert(std::fabs(haptic_mix(.7f,.3f)-.95f)<1e-6f);
 assert(std::fabs(haptic_mix(.98f,-.01f)-.97f)<1e-6f);
 assert(std::fabs(haptic_mix(1,-.3f)-.7f)<1e-6f);
 assert(haptic_mix(1,2)==1&&haptic_mix(-1,-2)==-1);
 for(int n=-100;n<=100;++n) {
   float native=n/100.f;
   assert(haptic_mix(native,0)==native);
   float last = -1;
   for(int d=-200;d<=200;++d) {
     const float added = d/100.f;
     const float out = haptic_mix(native,added);
     assert(std::fabs(out)<=1.000001f && out>=last-1e-6f);
     assert(std::fabs(out+haptic_mix(-native,-added))<1e-6f);
     if (std::fabs(native+added)<=.9f) assert(out==native+added);
     last = out;
   }
 }
 RumbleSent sent;uint8_t snapshot[63]{};snapshot[0]=3;snapshot[2]=100;
 assert(sent.pending(snapshot));sent.accepted(snapshot);assert(!sent.pending(snapshot));
 snapshot[0]=0;assert(sent.pending(snapshot));sent.accepted(snapshot);
 snapshot[0]=3;assert(sent.pending(snapshot)); // short stream hand-back still required
 sent.accepted(snapshot);snapshot[5]=80;assert(sent.pending(snapshot));
 sent.accepted(snapshot);snapshot[37]=7;assert(sent.pending(snapshot));
 sent.accepted(snapshot);snapshot[10]=5;assert(sent.pending(snapshot)); // trigger OFF retries
 sent.accepted(snapshot);snapshot[32]++;assert(!sent.pending(snapshot)); // timestamp is not control intent
 sent.reset();assert(sent.pending(snapshot));
 uint8_t queued[63],current[63]{};memset(queued,0xaa,63);
 current[0]=3;current[38]=4;current[2]=120;current[3]=90;
 refresh_rumble_fields(queued,current);
 assert(queued[2]==120&&queued[3]==90&&(queued[0]&3)==3);
 current[2]=current[3]=0;refresh_rumble_fields(queued,current);
 for(int i=0;i<63;++i) if(i!=0&&i!=2&&i!=3&&i!=38) assert(queued[i]==0xaa);
 assert(queued[2]==0&&queued[3]==0); // stale carrier now sends STOP
 uint8_t host[63]{};host[0]=3;host[2]=120;host[3]=90;
 state_update(host,63);now=100;uint8_t led[63]{};led[1]=4;
 state_update(led,63);assert(captured[2]==120&&captured[3]==90);
 now=1000;state_update(led,63);assert(captured[2]==120); // XInput held
 xinput=false;state_update(led,63);assert(captured[2]==0&&captured[3]==0);
 host[2]=host[3]=0;state_update(host,63);assert(captured[2]==0);
 host[0]=1;host[2]=99;host[3]=88;host[38]=0;
 state_update(host,63);assert(captured[2]==0&&captured[3]==0&&(captured[0]&3)==1);
 config.auto_haptics_enable=0;
 Motor unflagged;unflagged.RumbleEmulationLeft=255;unflagged.RumbleEmulationRight=255;
 apply(unflagged);assert(!state.UseRumbleNotHaptics&&!state.EnableImprovedRumbleEmulation);
 assert(g_rumble_l==255&&g_rumble_r==255); // preserve source values, no inferred mode
 // q1-style repeated reports, including trigger flags, must never infer mode.
 for(int level=255;level>=0;--level) {
   unflagged.RumbleEmulationLeft=level;unflagged.RumbleEmulationRight=255-level;
   unflagged.AllowLeftTriggerFFB=level&1;unflagged.AllowRightTriggerFFB=level&2;
   apply(unflagged);
   assert(!state.UseRumbleNotHaptics&&!state.EnableRumbleEmulation&&!state.EnableImprovedRumbleEmulation);
   assert(state.AllowLeftTriggerFFB==unflagged.AllowLeftTriggerFFB);
   assert(state.AllowRightTriggerFFB==unflagged.AllowRightTriggerFFB);
 }
 Motor improved;improved.EnableImprovedRumbleEmulation=true;improved.RumbleEmulationLeft=80;
 apply(improved);assert(state.EnableImprovedRumbleEmulation&&state.RumbleEmulationLeft==80);
 apply(unflagged);assert(!state.EnableImprovedRumbleEmulation&&!state.UseRumbleNotHaptics);
 config.auto_haptics_enable=1;
 Motor m;m.UseRumbleNotHaptics=true;m.EnableRumbleEmulation=true;
 m.RumbleEmulationLeft=100;m.RumbleEmulationRight=50;
 audio_input_seen=false;apply(m);assert(state.UseRumbleNotHaptics&&state.RumbleEmulationLeft==100);
 audio_input_seen=true;last_audio_input_ms=now;apply(m);assert(!state.UseRumbleNotHaptics&&!state.EnableRumbleEmulation);
 assert(g_rumble_l==100&&g_rumble_r==50);
 config.auto_haptics_enable=2;apply(m); // Replace uses the same PCM ownership rule
 assert(!state.UseRumbleNotHaptics&&!state.EnableRumbleEmulation);
 // Native restore must cancel an existing rumble release tail.
 config.auto_haptics_enable=0;config.rumble_release=40;config.rumble_gain=200;
 apply(m);assert(state.RumbleEmulationLeft>0);
 Motor native;native.EnableRumbleEmulation=true;
 now++;apply(native);assert(state.RumbleEmulationLeft==0&&state.RumbleEmulationRight==0);
 assert(!rumble_output_pending&&!state.UseRumbleNotHaptics);
 config.auto_haptics_enable=1;config.rumble_release=0;config.rumble_gain=100;
 now--;
 now+=59;assert(audio_haptics_stream_active());now++;assert(!audio_haptics_stream_active());
 apply(m);assert(state.UseRumbleNotHaptics&&state.RumbleEmulationRight==50);
 last_audio_input_ms=0xfffffff0;now=20;assert(audio_haptics_stream_active());
 connected=false;assert(!audio_haptics_stream_active());
 config.auto_haptics_enable=0;uint8_t empty[63]{};
 for(int xbox=0;xbox<2;xbox++){
   xinput=xbox;host[0]=3;host[2]=80;host[3]=90;host[38]=0;state_update(host,63);state_update(empty,63);
   assert((captured[0]&3)==(xbox?3:0));
   assert(captured[2]==(xbox?80:0));
 }
 config.auto_haptics_enable=1;xinput=false;state_update(host,63);state_update(empty,63);
 assert((captured[0]&3)==3&&captured[2]==80); // Mix keeps legacy inheritance
 config.auto_haptics_enable=0;
 // Every real non-motor control group retains held rumble, including improved mode.
 for(int group=0;group<4;group++)for(int bit=0;bit<8;bit++) {
   uint8_t control[63]{};bool relevant=true;
   if(group==0){control[0]=1u<<bit;relevant=bit>=2;}
   if(group==1)control[1]=1u<<bit;
   if(group==2){control[38]=1u<<bit;relevant=bit!=2;}
   if(group==3){control[0]=0x0c;control[10]=control[21]=5;}
   if(!relevant)continue;
   host[0]=3;host[38]=4;state_update(host,63);state_update(control,63);
   assert((captured[0]&3)==3&&(captured[38]&4)&&captured[2]==80);
 }
 // Actual CrimsonPulse neutral-start shape: unused trigger OFF bytes grant no authority.
 uint8_t start[47]{};start[10]=start[21]=5;
 state_update(host,63);state_update(start,47);assert(!(captured[0]&3)&&!(captured[38]&4)&&!captured[2]&&!captured[3]);
 uint32_t last_motor=g_last_rumble_ms;
 for(int i=0;i<20;i++){now++;state_update(start,47);assert(!(captured[0]&3)&&!(captured[38]&4));}
 assert(g_last_rumble_ms==last_motor);
 host[0]=3;state_update(host,63);state_update(start,1);assert((captured[0]&3)==3); // short report cannot select native
 host[0]=3;host[2]=80;host[3]=90;host[38]=4;
 for(int xbox=0;xbox<2;xbox++)for(int length=1;length<4;length++){
  xinput=xbox;state_update(host,63);uint8_t short_led[63]{};short_led[1]=4;
  state_update(short_led,length);assert((captured[0]&3)==3&&captured[2]==80&&(captured[38]&4));
  state_update(short_led,63);assert((captured[0]&3)==3&&captured[2]==80&&(captured[38]&4));
 }
 connected=true;xinput=false;config.auto_haptics_enable=0;config.rumble_gain=100;
 for(int improved_mode=0;improved_mode<2;improved_mode++)for(int release_mode=0;release_mode<3;release_mode++){
   config.rumble_release=release_mode;rumble_shape.reset();
   Motor start;start.EnableRumbleEmulation=!improved_mode;start.UseRumbleNotHaptics=true;
   start.EnableImprovedRumbleEmulation=improved_mode;start.RumbleEmulationLeft=100;start.RumbleEmulationRight=60;
   now+=100;apply(start);assert(state.UseRumbleNotHaptics&&state.RumbleEmulationLeft==100);
   Motor stop=start;stop.RumbleEmulationLeft=stop.RumbleEmulationRight=0;
   now++;apply(stop);
   unsigned duration=RumbleShape::duration(release_mode);
   if(duration){assert(state.UseRumbleNotHaptics);now+=duration-1;apply(stop);assert(state.UseRumbleNotHaptics);now++;apply(stop);}
   assert(state.EnableRumbleEmulation&&!state.UseRumbleNotHaptics&&!state.EnableImprovedRumbleEmulation);
   assert(!state.RumbleEmulationLeft&&!state.RumbleEmulationRight);
   rumble_output_pending=false;now++;apply(stop);assert(!rumble_output_pending); // no repeated mode commands
   now++;apply(start);assert(state.UseRumbleNotHaptics&&state.RumbleEmulationLeft==100); // immediate new attack
   xinput=true;now++;apply(stop);now+=50;apply(stop);assert(state.UseRumbleNotHaptics);xinput=false;
   // Selector left behind by the DS watchdog is released too.
   config.rumble_release=0;Motor timed=start;timed.EnableRumbleEmulation=false;
   timed.EnableImprovedRumbleEmulation=false;timed.RumbleEmulationLeft=timed.RumbleEmulationRight=0;
   apply(timed);assert(state.EnableRumbleEmulation&&!state.UseRumbleNotHaptics);
 }
 puts("PASS: native unity/headroom, stereo, queued STOP/non-motor preservation, held rumble, DS-only watchdog, stream fallback/wrap/disconnect");
}
"""
(out/'test.cpp').write_text(code,encoding='utf-8')
subprocess.run([str(bin_dir/'g++.exe'),'-std=c++17','-Wall','-Wextra','-I'+str(root/'src'),str(out/'test.cpp'),'-o',str(out/'test.exe')],env=env,check=True)
p=subprocess.run([str(out/'test.exe')],env=env,capture_output=True,text=True)
(out/'result.txt').write_text(p.stdout+p.stderr,encoding='utf-8');print(p.stdout+p.stderr);p.check_returncode()
subprocess.run([str(bin_dir/'g++.exe'),'-std=c++17','-Wall','-Wextra','-I'+str(root/'src'),
    str(root/'tests/output_diagnostics_test.cpp'),'-o',str(out/'diagnostics.exe')],env=env,check=True)
subprocess.run([str(out/'diagnostics.exe')],env=env,check=True)
print('PASS: diagnostic control bytes, idle identity, 2-second tests, wrap, OFF acknowledgement and untouched LED/audio fields')
