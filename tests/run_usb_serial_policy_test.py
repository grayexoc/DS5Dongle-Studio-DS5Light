"""Production journal/policy paths with flash fault injection; no device access."""
from pathlib import Path
import os,subprocess
root=Path(__file__).resolve().parents[1]
s=(root/'src/config.cpp').read_text(encoding='utf-8')
u=(root/'src/usb_descriptors.cpp').read_text(encoding='utf-8')
def extract(text,signature):
    start=text.index(signature)
    return text[start:text.index('\n}',start)+2]+'\n'
out=root.parent/'DS5Dongle-Studio-build/reports/usb-serial-policy'
out.mkdir(parents=True,exist_ok=True)
code=r'''
#include <cassert>
#include <cstdint>
#include <cstddef>
#include <cstdio>
#include <cstring>
#include <stdexcept>
static uint8_t flashmem[16384];
#define XIP_BASE reinterpret_cast<uintptr_t>(flashmem)
constexpr unsigned FLASH_SECTOR_SIZE=4096,FLASH_PAGE_SIZE=256;
constexpr unsigned CONFIG_JOURNAL_A_OFFSET=0,CONFIG_JOURNAL_B_OFFSET=4096;
constexpr unsigned LEGACY_CONFIG_FLASH_OFFSET=12288,STORAGE_REDO_META=8192;
constexpr unsigned CONFIG_MAGIC=0x1234,CONFIG_VERSION=22,SLOT_COUNT=24;
constexpr int PICO_OK=0;
struct Config_body { uint8_t config_version,disable_usb_sn,usb_gamepad_mode,padding[29]; };
struct Config { uint32_t magic;uint16_t size;uint32_t crc32;Config_body body; };
static Config config{};
static bool activation_save_pending=false,activation_idle_tracking=false;
static unsigned activation_save_attempts=0,activation_retry_at_ms=0;
static bool audio=false,write_failure=false;
static int cut=-1,operations=0;
uint32_t crc32(const uint8_t*p,unsigned n){uint32_t c=~0u;while(n--){c^=*p++;for(int i=0;i<8;i++)c=(c>>1)^(0xedb88320u&-(c&1));}return ~c;}
uint32_t calc_config_crc(const Config&c){return crc32(reinterpret_cast<const uint8_t*>(&c.body),sizeof(c.body));}
bool audio_processing_active(){return audio;}
unsigned get_absolute_time(){return 0;}unsigned to_ms_since_boot(unsigned n){return n;}
unsigned save_and_disable_interrupts(){return 0;}void restore_interrupts(unsigned){}
void step(){if(++operations==cut)throw std::runtime_error("power cut");}
void flash_range_erase(unsigned off,unsigned n){for(unsigned i=0;i<n;i+=256){memset(flashmem+off+i,255,256);step();}}
void flash_range_program(unsigned off,const uint8_t*p,unsigned n){for(unsigned i=0;i<n;i+=4){for(int j=0;j<4;j++)flashmem[off+i+j]&=p[i+j];step();}}
int flash_safe_execute(void(*fn)(void*),void*p,unsigned){if(write_failure)return -1;fn(p);return PICO_OK;}
const Config*flash_config(){return reinterpret_cast<const Config*>(flashmem+8192);}
void config_valid(){config.body.config_version=CONFIG_VERSION;if(config.body.disable_usb_sn>1)config.body.disable_usb_sn=0;}
void migrate_legacy_storage(){}
void active_profile_restore(uint8_t,uint32_t){}
bool active_profile_resume_state(uint8_t&slot,uint32_t&fp){slot=3;fp=0xabcd;return true;}
void recover_storage(void*){}static bool recovery_ok=true;
void panic(const char*){throw std::runtime_error("panic");}
static void config_defer_activation_save();
'''
code+=s[s.index('constexpr uint32_t CONFIG_JOURNAL_MAGIC'):s.index('static bool recovery_ok')]
code+=extract(s,'void config_load(')
code+=s[s.index('constexpr uint32_t CONFIG_WRITE_LEN'):s.index('static bool config_journal_fits_firmware')]
code+='static bool config_journal_fits_firmware(){return true;}\n'
for signature in ('static void config_save_flash_op(', 'static bool config_journal_write(',
                  'static bool config_save_impl(', 'static bool save_device_policy(',
                  'bool device_set_auto_dormant(', 'bool device_set_disconnect_on_dock(',
                  'bool device_set_usb_serial_hidden(', 'static void config_defer_activation_save() {'):
    code+=extract(s,signature)
code+='bool device_usb_serial_hidden(){return usb_serial_hidden_policy;}\n'
code+=extract(u,'bool usb_edge_serial_hidden(')
code+=r'''
void seed(bool legacy){
 memset(flashmem,255,sizeof flashmem);config={};config.body.config_version=22;config.body.disable_usb_sn=legacy;
 ConfigProfileIdentity id{};id.tagged_slot=CONFIG_PROFILE_TAG|3|DORMANT_POLICY_BIT|DOCK_DISCONNECT_BIT;id.fingerprint=0xabcd;
 assert(config_journal_write(reinterpret_cast<uint8_t*>(&config.body),sizeof(config.body),id,10));
}
ConfigProfileIdentity stored(){uint32_t off;ConfigProfileIdentity id{};assert(config_journal_device_identity(id));return id;}
int main(){
 for(bool legacy:{false,true}){
  seed(legacy);config_load();assert(usb_serial_hidden_policy==legacy&&activation_save_pending);
  assert(config_save_impl(10));auto id=stored();assert(id.tagged_slot&USB_SERIAL_INITIALIZED_BIT);
  assert((id.tagged_slot&~DEVICE_POLICY_MASK)==(CONFIG_PROFILE_TAG|3));assert(id.fingerprint==0xabcd);
  assert(device_set_usb_serial_hidden(!legacy));
  // A loaded old profile and its subsequent save cannot overwrite common state.
  config.body.disable_usb_sn=legacy;assert(config_save_impl(10));config_load();assert(usb_serial_hidden_policy==!legacy);
  assert(!activation_save_pending);
  Config_body profile{};profile.disable_usb_sn=legacy;assert(usb_edge_serial_hidden(profile)==!legacy);
  profile.usb_gamepad_mode=1;assert(!usb_edge_serial_hidden(profile));
  assert(device_set_auto_dormant(false));assert(device_set_disconnect_on_dock(false));config_load();assert(usb_serial_hidden_policy==!legacy);
  audio=true;assert(!device_set_usb_serial_hidden(legacy));audio=false;assert(usb_serial_hidden_policy==!legacy);
  write_failure=true;assert(!device_set_usb_serial_hidden(legacy));write_failure=false;assert(usb_serial_hidden_policy==!legacy);
 }
 // Profile OFF arrives before the first migration journal save; even a torn
 // migration footer must retain the original ON value from the older record.
 seed(true);config_load();config.body.disable_usb_sn=0;
 uint8_t migration_before[sizeof flashmem];memcpy(migration_before,flashmem,sizeof flashmem);
 operations=0;assert(config_save_impl(10));int migration_count=operations;
 for(int failure=1;failure<=migration_count;failure++){
  memcpy(flashmem,migration_before,sizeof flashmem);cut=-1;config_load();
  config.body.disable_usb_sn=0;operations=0;cut=failure;
  try{config_save_impl(10);}catch(const std::runtime_error&){}
  cut=-1;config_load();assert(usb_serial_hidden_policy);
 }
 // Explicit OFF is authoritative even before the deferred migration save.
 seed(true);config_load();assert(device_set_usb_serial_hidden(false));config_load();assert(!usb_serial_hidden_policy);
 seed(true);config_load();assert(config_save_impl(10));
 uint8_t before[sizeof flashmem];memcpy(before,flashmem,sizeof flashmem);
 operations=0;assert(device_set_usb_serial_hidden(false));int count=operations;
 for(int failure=1;failure<=count;failure++){
  memcpy(flashmem,before,sizeof flashmem);cut=-1;config_load();operations=0;cut=failure;
  try{device_set_usb_serial_hidden(false);}catch(const std::runtime_error&){}
  cut=-1;config_load();auto id=stored();
  // A torn write yields the old or fully committed policy; legacy slot bytes cannot re-enable it.
  bool value=usb_serial_hidden_policy;config.body.disable_usb_sn=!value;assert(config_save_impl(10));config_load();assert(usb_serial_hidden_policy==value);
  assert(id.tagged_slot&USB_SERIAL_INITIALIZED_BIT);
 }
 // A second interrupted write must not erase the only complete policy footer.
 seed(true);config_load();assert(config_save_impl(10));
 uint8_t committed[sizeof flashmem];memcpy(committed,flashmem,sizeof flashmem);
 config.body.disable_usb_sn=0;operations=0;assert(config_save_impl(10));int first_count=operations;
 int repeated_cuts=0;
 for(int first=1;first<=first_count;first++){
  memcpy(flashmem,committed,sizeof flashmem);cut=-1;config_load();
  config.body.disable_usb_sn=0;operations=0;cut=first;
  try{config_save_impl(10);}catch(const std::runtime_error&){}
  cut=-1;uint32_t off;ConfigProfileIdentity id{};
  const auto* newest=config_journal_latest(off);
  const auto* complete=config_journal_device_identity(id);
  if(!newest||!complete||newest==complete)continue;
  config_load();assert(usb_serial_hidden_policy);
  uint8_t torn[sizeof flashmem];memcpy(torn,flashmem,sizeof flashmem);
  operations=0;assert(device_set_auto_dormant(false));int second_count=operations;
  for(int second=1;second<=second_count;second++){
   memcpy(flashmem,torn,sizeof flashmem);cut=-1;config_load();operations=0;cut=second;
   try{device_set_auto_dormant(false);}catch(const std::runtime_error&){}
   cut=-1;config_load();assert(usb_serial_hidden_policy);++repeated_cuts;
  }
 }
 assert(repeated_cuts>0);
 printf("PASS: migration, explicit policy persistence, profile immunity, audio/save rejection, %d single and %d repeated power-cut points\n",count+migration_count,repeated_cuts);
}
'''
(out/'test.cpp').write_text(code,encoding='utf-8')
bin=root.parent/'DS5Dongle-Studio-build/source/toolchain/mingw64/mingw64/bin'
env=dict(os.environ);env['PATH']=str(bin)+os.pathsep+env.get('PATH','')
subprocess.run([str(bin/'g++.exe'),'-std=c++17',str(out/'test.cpp'),'-o',str(out/'test.exe')],env=env,check=True)
result=subprocess.run([str(out/'test.exe')],env=env,capture_output=True,text=True)
(out/'result.txt').write_text(result.stdout+result.stderr)
print('\n'.join(result.stdout.splitlines()[-2:])+result.stderr)
result.check_returncode()
