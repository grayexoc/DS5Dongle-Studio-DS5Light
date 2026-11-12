"""Host test of actual state composition and pending-report code; no device access."""
from pathlib import Path
import os,subprocess,json,re
root=Path(__file__).resolve().parents[1]
base=root.parent/'DS5Dongle-Studio-build'
out=base/'reports/led-optimization-tests';out.mkdir(parents=True,exist_ok=True)
source=(root/'src/state_mgr.cpp').read_text(encoding='utf-8')
def extract(signature):
    start=source.index(signature);return source[start:source.index('\n}',start)+2]
code=r'''
#include <cassert>
#include <cstring>
#include <cstdio>
#include <initializer_list>
#include "config.h"
#include "lightbar_fixed.h"
#include "player_led_sent.h"
#include "rumble_delivery.h"
#include "output_diagnostics.h"
OutputDiagnostics output_diagnostics;
OutputTest output_test;
#define __not_in_flash_func(name) name
struct SetStateData { uint8_t bytes[63]; } state{};
uint8_t g_host_cache[63]{};uint8_t g_host_cache_size=0;
bool game_ever_r2=false,game_ever_l2=false;
void state_rumble_reset(){state.bytes[2]=state.bytes[3]=0;}
static Config_body config{};
bool mute_mapping=false;
bool macro_uses_mute_button(){return mute_mapping;}
static Config_body &get_config_mock() { return config; }
#define get_config get_config_mock
static uint64_t now_us=0;
static uint32_t get_absolute_time() { return now_us/1000; }
static uint32_t to_ms_since_boot(uint32_t t) { return t; }
static bool player_led_restore_pending=false;
static uint8_t player_led_previous_mode=0;
static uint64_t time_us_64() { return now_us; }
static LightbarFixed lightbar_fixed_policy;
static PlayerLedSent player_led_sent;
static RumbleSent rumble_sent;
static bool rumble_output_pending=false;
static bool stream_active=false;
static bool audio_haptics_stream_active() { return stream_active; }
volatile uint8_t g_diag_pled_mode=0, g_batt_raw=0, g_diag_pled_raw=0;
volatile uint8_t g_diag_pled_bits=0, g_diag_pled_state=0;
volatile uint16_t g_diag_pled_runs=0;
static unsigned battery_calls=0;
static bool battery_notify_override(uint8_t &r,uint8_t &g,uint8_t &b) {
    ++battery_calls;r=255;g=0;b=0;return config.batt_notify_enable;
}
'''
code+=source[source.index('static constexpr uint8_t state_init_data'):source.index('};',source.index('static constexpr uint8_t state_init_data'))+2]+'\n'
code+=extract('void state_refresh_rumble(')+'\n'
code+=extract('static void state_host_led_update(')+'\n'
code+=extract('void __not_in_flash_func(state_set)')+'\n'
code+=extract('static void player_led_update_mode(')+'\n'
code+=extract('bool player_led_wants_report(void)')+'\n'
code+=extract('bool state_report_is_lightbar_restore(')+'\n'
code+=extract('void state_report_sent(')+'\n'
code+=extract('bool lightbar_fixed_wants_report(')+'\n'
code+=extract('bool state_prepare_report(')+'\n'
code+=extract('bool state_rumble_wants_report(')+'\n'
code+=extract('bool state_output_test(')+'\n'
code+=r'''
static bool legacy_prepare(uint8_t *data,bool force) {
    if(force || player_led_wants_report() || lightbar_fixed_wants_report() || state_rumble_wants_report()) {
        state_set(data,63);return true;
    }
    return false;
}
static void send() { uint8_t data[63];state_set(data,63);state_report_sent(data,state_report_is_lightbar_restore(data)); }
int main() {
    uint8_t data[63];
    for(bool stop_early:{false,true}) {
        memset(state.bytes,0,63);state.bytes[0]=4;state.bytes[10]=0x21;state.bytes[11]=0xfc;
        memcpy(g_host_cache,state.bytes,63);g_host_cache_size=63;
        game_ever_r2=game_ever_l2=true;now_us=0;
        state_output_test(4);
        assert(!game_ever_r2&&!game_ever_l2);
        assert(state.bytes[10]==5&&g_host_cache[10]==5&&g_host_cache[21]==5);
        state_prepare_report(data,true);state_report_sent(data,false);
        if(stop_early)state_output_test(0);else now_us=2000000;
        state_prepare_report(data,false);assert(data[10]==5&&data[21]==5);
        state_report_sent(data,false);assert(!output_test.pending());
        state_prepare_report(data,false);assert(data[10]==5&&data[21]==5); // no stale game resurrection
        state.bytes[0]|=4;state.bytes[10]=0x26;state_set(data,63);
        assert(data[10]==0x26); // fresh game/profile effects are not suppressed after cleanup
    }
    g_host_cache_size=0;now_us=0;memset(state.bytes,0,63);rumble_sent.reset();
    state.bytes[1]=1;state.bytes[8]=2;mute_mapping=true;
    state_set(data,63);assert((data[1]&1)&&data[8]==0);
    assert(state.bytes[8]==2); // keep the host value for restoration
    mute_mapping=false;state_set(data,63);assert(data[8]==2);
    memset(state.bytes,0,63);
    rumble_output_pending=true;memset(data,0,sizeof(data));data[2]=50;
    state_report_sent(data,false);assert(rumble_output_pending); // stale nonzero must not acknowledge zero
    data[2]=0;state_report_sent(data,false);assert(!rumble_output_pending);
    memcpy(state.bytes,state_init_data,63);
    lightbar_fixed_policy.reset();player_led_sent.reset();
    state_set(data,63);
    assert(!(data[1]&0x0c) && !(data[38]&2)); // no host colour: no setup or black write
    uint8_t explicit_black[63]{};explicit_black[1]=4;
    state_host_led_update(explicit_black,63);
    send();send(); // actual host black: setup then explicit off
    state_set(data,63);assert(!(data[38]&2));
    assert(!player_led_wants_report());
    state.bytes[1]=0x14;state.bytes[43]=4;
    state_set(data,63);assert(data[44]==0 && data[43]==4); // game chooses only white LED
    assert(player_led_wants_report()); // report dropped before successful send
    state_report_sent(data,false);
    assert(!player_led_wants_report());
    state.bytes[43]=0;state.bytes[38]=2;state.bytes[41]=2;
    state_set(data,63);
    assert((data[1]&0x14)==0x14 && !(data[38]&2) && data[43]==0 && data[44]==0);
    state.bytes[43]=4;
    config.player_led_bright=3;
    state_set(data,63);
    assert((data[1]&0x10) && !(data[43]&0x1f) && !(data[38]&1));
    config.player_led_bright=0;
    state.bytes[43]=0;
    state.bytes[44]=25;
    state_set(data,63);assert(data[44]==25 && data[43]==0); // game regains colour
    state.bytes[44]=0;config.lightbar_off=1;
    state_set(data,63);assert(data[44]==0 && (data[43]&0x1f)==0);
    config.lightbar_off=0;
    config.player_led_mode=1;
    assert(player_led_wants_report());
    state_set(data,63);
    assert(player_led_wants_report()); // composed or queued is not sent
    send();
    for(int i=0;i<1000;++i) {now_us+=50000;assert(!player_led_wants_report());}
    config.player_led_bright=2;assert(player_led_wants_report());send();assert(!player_led_wants_report());
    player_led_sent.reset();assert(player_led_wants_report());send(); // reconnect
    config.player_led_mode=2;g_batt_raw=0x14;now_us=60000000; // charging 40%
    assert(player_led_wants_report());send();assert(!player_led_wants_report());
    now_us+=750000;assert(player_led_wants_report());send(); // charging pulse boundary
    g_batt_raw=4;assert(!player_led_wants_report()); // same displayed pattern
    g_batt_raw=0;now_us+=100000;player_led_wants_report(); // start debounce
    now_us+=5000000;assert(player_led_wants_report());send();
    now_us=66500000;assert(player_led_wants_report());send(); // low-battery blink
    config.player_led_mode=0;config.player_led_bright=0;state.bytes[43]=3;
    assert(player_led_wants_report());send();
    if(player_led_wants_report())send(); // restore the host fade flag after instant hand-back
    assert(!player_led_wants_report()); // hand-back
    config.lightbar_fixed=1;config.lightbar_r=10;config.lightbar_g=20;config.lightbar_b=30;
    unsigned before=battery_calls;state_set(data,63);
    assert(battery_calls==before && data[44]==10 && data[45]==20 && data[46]==30);
    config.lightbar_off=1;state_set(data,63);assert(battery_calls==before && data[44]==0);
    config.lightbar_off=config.lightbar_fixed=0;config.batt_notify_enable=1;state_set(data,63);assert(battery_calls==before+1 && data[44]==255);
    // A composed candidate is reused byte-for-byte; motor refresh leaves all other fields alone.
    config.lightbar_fixed=config.lightbar_off=config.batt_notify_enable=0;
    config.player_led_mode=config.player_led_bright=0;
    for(int mode=0;mode<3;mode++)for(int active=0;active<2;active++) {
        config.auto_haptics_enable=mode;stream_active=active;
        memset(state.bytes,0xa5,63);state.bytes[2]=120;state.bytes[3]=90;
        uint8_t full[63],narrow[63];state_set(full,63);memset(narrow,0x5a,63);state_refresh_rumble(narrow);
        assert((narrow[0]&3)==(full[0]&3)&&(narrow[38]&4)==(full[38]&4));
        assert(narrow[2]==full[2]&&narrow[3]==full[3]);
        for(int i=0;i<63;i++)if(i!=0&&i!=2&&i!=3&&i!=38)assert(narrow[i]==0x5a);
        assert((narrow[0]&~3)==(0x5a&~3)&&(narrow[38]&~4)==(0x5a&~4));
    }
    config.auto_haptics_enable=0;stream_active=false;
    unsigned calls=battery_calls;
    config.batt_notify_enable=1;
    assert(state_prepare_report(data,true));assert(battery_calls==calls+1);
    calls=battery_calls;
    state_prepare_report(data,false);assert(battery_calls==calls+1); // one composition for decision + payload
    // Frozen-time differential check of the old short-circuit decision and new candidate path.
    for(int step=0;step<1200;step++) {
        now_us+=8000;
        config.player_led_mode=(step/50)%3;config.player_led_bright=(step/75)%4;
        config.lightbar_fixed=(step/30)%2;config.lightbar_off=(step/45)%2;
        config.lightbar_r=step;config.lightbar_g=step/2;config.lightbar_b=step/3;
        config.auto_haptics_enable=step%3;stream_active=step%2;
        config.batt_notify_enable=(step/20)%2;g_batt_raw=(step/100)%11;
        state.bytes[0]=step;state.bytes[2]=step/2;state.bytes[3]=step/3;state.bytes[38]=step/4;
        bool force=step%7==0;uint8_t old_data[63]{},new_data[63]{};
        player_led_update_mode();
        bool old_needed=legacy_prepare(old_data,force);
        bool new_needed=state_prepare_report(new_data,force);
        assert(old_needed==new_needed);
        if(old_needed)assert(memcmp(old_data,new_data,63)==0);
        if(step%5!=0 && new_needed)state_report_sent(new_data,state_report_is_lightbar_restore(new_data));
    }
    // No host LED authority: return the latched gauge to player 1, including forced ticks.
    memset(state.bytes,0,63);config.player_led_bright=0;config.player_led_mode=2;
    config.lightbar_fixed=config.lightbar_off=config.batt_notify_enable=0;
    config.auto_haptics_enable=0;stream_active=false;g_batt_raw=5;
    assert(state_prepare_report(data,true));state_report_sent(data,false);
    config.player_led_mode=0;now_us+=1000;
    assert(state_prepare_report(data,true));assert((data[1]&16)&&(data[43]&31)==4);
    now_us+=2000000;assert(state_prepare_report(data,false));assert(data[1]&16); // not acked: still retries
    uint8_t stale[63]{};stale[1]=16;stale[43]=7;state_report_sent(stale,false);
    assert(player_led_restore_pending);
    state_report_sent(data,false);assert(!player_led_restore_pending);
    state_prepare_report(data,false);assert(!(data[1]&16));
    // Returning brightness to passthrough restores the host value, or USB default zero.
    memset(state.bytes,0,63);player_led_sent.reset();
    config.player_led_mode=0;config.player_led_bright=2;
    send();config.player_led_bright=0;
    assert(state_prepare_report(data,false));assert((data[38]&1)&&data[42]==0);
    state_report_sent(data,false);assert(!player_led_wants_report());
    state.bytes[38]=1;state.bytes[42]=1;
    config.player_led_bright=2;send();config.player_led_bright=0;
    state_set(data,63);assert((data[38]&1)&&data[42]==1);send();
    // A lightbar release may reset the player pattern; reapply the host pattern.
    memset(state.bytes,0,63);state.bytes[1]=16;state.bytes[43]=4;
    send();assert(!player_led_wants_report());
    uint8_t release_only[63]{};release_only[1]=8;
    state_report_sent(release_only,false);
    assert(player_led_wants_report());send();assert(!player_led_wants_report());
    // Reset commands carry no RGB. Restore the last explicit RGB afterwards.
    memset(state.bytes,0,63);state.bytes[1]=0x14;state.bytes[43]=4;state.bytes[44]=90;
    uint8_t command[63]{};command[1]=8;
    state_host_led_update(command,1);assert(state.bytes[44]==90);
    state_host_led_update(command,2);
    assert(!(state.bytes[1]&0x10)&&(state.bytes[1]&4)&&state.bytes[43]==0&&state.bytes[44]==90);
    state_set(data,63);assert(data[1]&8);
    state_report_sent(data,false);state_set(data,63);assert(!(data[1]&8));
    command[1]=0;command[38]=2;command[41]=2;state.bytes[1]=4;state.bytes[44]=90;
    state_host_led_update(command,41);assert(state.bytes[44]==90);
    state_host_led_update(command,42);assert(state.bytes[44]==90&&(state.bytes[1]&4));
    state_set(data,63);assert((data[38]&2)&&data[41]==2&&!(data[1]&0x14));
    state_report_sent(data,false);state_set(data,63);
    assert(!(data[38]&2)&&(data[1]&0x14)==0x14&&data[44]==90);
    send();

    // LIGHT_OUT and a switch from player-off to default share one restore.
    memset(state.bytes,0,63);lightbar_fixed_policy.reset();player_led_sent.reset();
    player_led_previous_mode=0;player_led_restore_pending=false;
    config.player_led_mode=1;
    assert(state_prepare_report(data,false));send();
    config.player_led_mode=0;state_host_led_update(command,42);
    assert(state_prepare_report(data,false));
    assert((data[38]&2)&&data[41]==2&&!(data[1]&0x14));
    state_report_sent(data,false);
    assert(player_led_restore_pending&&state_prepare_report(data,false));
    assert(!(data[38]&2)&&(data[1]&0x14)==0x14&&data[46]==255&&(data[43]&31)==4);
    uint8_t stale_setup[63];memcpy(stale_setup,data,63);
    stale_setup[38]|=2;stale_setup[41]=2;
    state_report_sent(stale_setup,false);assert(player_led_restore_pending);
    send();assert(!player_led_restore_pending&&!state_prepare_report(data,false));

    // A host RGB of zero survives setup and is distinct from an absent colour.
    uint8_t black[63]{};black[1]=4;
    state_host_led_update(black,63);memset(state.bytes+44,0,3);send();
    state_host_led_update(command,42);send();
    state_set(data,63);
    assert((data[1]&4)&&data[44]==0&&data[45]==0&&data[46]==0);
    send();
    // No game running: native startup -> brown/off audio profile -> native startup.
    memset(state.bytes,0,63);lightbar_fixed_policy.reset();player_led_sent.reset();
    player_led_previous_mode=0;player_led_restore_pending=false;
    config.batt_notify_enable=0;config.lightbar_fixed=config.lightbar_off=0;
    config.player_led_mode=config.player_led_bright=0;
    for(int cycle=0;cycle<100;cycle++) {
        config.auto_haptics_enable=1;config.lightbar_fixed=1;
        config.lightbar_r=120;config.lightbar_g=80;config.lightbar_b=40;
        config.player_led_mode=1;state_prepare_report(data,false);send();send();
        state_set(data,63);assert(data[44]==120&&data[45]==80&&data[46]==40);
        assert((data[43]&31)==0);
        config.auto_haptics_enable=0;config.lightbar_fixed=0;config.player_led_mode=0;
        assert(state_prepare_report(data,false));
        assert((data[1]&0x14)==0x14&&data[44]==0&&data[45]==0&&data[46]==255);
        assert((data[43]&31)==4);send();
        assert(!state_prepare_report(data,false));
    }
    // An explicit game-off pattern must win over the startup fallback.
    state.bytes[1]=0x14;state.bytes[43]=0;
    config.player_led_mode=1;state_prepare_report(data,false);send();config.player_led_mode=0;
    state_prepare_report(data,false);assert((data[43]&31)==0);send();
    puts("PASS: LED policies, no-game native/audio roundtrip x100, explicit game off, mapped mute isolation");
}
'''
(out/'test.cpp').write_text(code,encoding='utf-8')
bin_dir=base/'source/toolchain/mingw64/mingw64/bin'
env=dict(os.environ);env['PATH']=str(bin_dir)+os.pathsep+env.get('PATH','')
subprocess.run([str(bin_dir/'g++.exe'),'-std=c++17','-I'+str(root/'src'),str(out/'test.cpp'),'-o',str(out/'test.exe')],env=env,check=True)
p=subprocess.run([str(out/'test.exe')],env=env,capture_output=True,text=True)
(out/'result.txt').write_text(p.stdout+p.stderr,encoding='utf-8');print(p.stdout+p.stderr);p.check_returncode()
from test_support import firmware_build
build=firmware_build(root)
rows=json.loads((build/'compile_commands.json').read_text())
logs=[]
for name in ('state_mgr.cpp','bt.cpp'):
    row=next(r for r in rows if r['file'].endswith(name))
    command,n=re.subn(r' -o \S+ -c ',' -fsyntax-only ',row['command']);assert n==1
    command=command.replace(row['file'],str(root/'src'/name))
    p=subprocess.run(command,cwd=build,capture_output=True,text=True)
    logs.append(name+': '+str(p.returncode)+'\n'+p.stdout+p.stderr)
    (out/'syntax.txt').write_text('\n'.join(logs),encoding='utf-8');p.check_returncode()
print('PASS: ARM syntax checks (2 files); no firmware build')
