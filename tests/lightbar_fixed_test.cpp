#include "config.h"
#include "lightbar_fixed.h"
#include <cassert>
#include <cstddef>
#include <cstdio>
#include <cstring>
#include <cmath>
#include "lightbar_config_extract.h"

int main() {
    static_assert(sizeof(Config_body) <= SLOT_MAX_BODY_LEN);
    static_assert(sizeof(Config_body) == offsetof(Config_body, usb_gamepad_mode) + 1);
    Config_body defaults;memset(&defaults,0xff,sizeof(defaults));config_body_valid(defaults);
    assert(std::fabs(defaults.haptics_gain-1.2f)<0.0001f && defaults.haptics_aa==1);
    LightbarFixed p;
    uint8_t report[63]{}, original[63]{};
    // An unseen colour is not an explicit black/off command.
    assert(!p.pending(false,false,0,0,0));
    p.apply(report,false,false,0,0,0);
    assert(!(report[1]&12)&&!(report[38]&2));
    p.apply(report,false,true,12,34,56);
    assert((report[38]&2)&&report[41]==2);
    uint8_t startup[63];memcpy(startup,report,63);
    p.accepted(report,false,true,12,34,56);
    memset(report,0,63);p.apply(report,false,true,12,34,56);
    p.accepted(report,false,true,12,34,56);
    memset(report,0,63);p.apply(report,false,false,0,0,0);
    assert((report[1]&4)&&!(report[1]&8)&&report[44]==0&&report[45]==0&&report[46]==255);
    p.accepted(report,false,false,0,0,0,p.is_restore_report(report));
    assert(!p.pending(false,false,0,0,0));
    // A queued old override arriving after release must trigger another release.
    uint8_t late_override[63]{};late_override[1]=4;late_override[44]=12;
    p.accepted(late_override,false,false,0,0,0);
    assert(p.pending(false,false,0,0,0));
    memset(report,0,63);p.apply(report,false,false,0,0,0);
    assert((report[1]&4)&&!(report[1]&8)&&report[44]==0&&report[45]==0&&report[46]==255);
    p.accepted(report,false,false,0,0,0,p.is_restore_report(report));
    assert(!p.pending(false,false,0,0,0));
    // A real host colour requests Bluetooth setup before RGB restoration.
    uint8_t first[63]{};first[1]=4;first[44]=90;p.host_update(first,63);
    memcpy(report,first,63);p.apply(report,false,false,0,0,0);
    p.accepted(report,false,false,0,0,0);
    memcpy(report,first,63);p.apply(report,false,false,0,0,0);
    p.accepted(report,false,false,0,0,0,p.is_restore_report(report));
    memset(original,0x5a,63);memcpy(report,original,63);
    p.apply(report,false,true,12,34,56);
    assert((report[1]&12)==4&&!(report[38]&2));
    assert(report[44]==12&&report[45]==34&&report[46]==56);
    for(unsigned i=0;i<63;i++)
        if(i!=1&&i!=38&&i!=41&&(i<44||i>46))assert(report[i]==original[i]);
    uint8_t stale[63]{};stale[1]=4;
    p.accepted(stale,false,true,12,34,56);
    assert(p.pending(false,true,12,34,56));
    p.accepted(report,false,true,12,34,56);
    for(int i=0;i<1000;i++)assert(!p.pending(false,true,12,34,56));

    // Host colour changes during a fixed profile are restored, including black/off.
    uint8_t host[63]{};host[1]=4;host[44]=90;p.host_update(host,63);
    memcpy(report,host,63);p.apply(report,false,false,0,0,0);
    assert(report[44]==90&&(report[1]&4));
    p.accepted(stale,false,false,0,0,0,true);
    assert(p.pending(false,false,0,0,0));
    p.accepted(report,false,false,0,0,0); // old identical payload lacks restore tag
    assert(p.pending(false,false,0,0,0));
    p.accepted(report,false,false,0,0,0,p.is_restore_report(report));
    assert(!p.pending(false,false,0,0,0));
    memset(host,0,63);host[1]=4;p.host_update(host,63);
    memcpy(report,host,63);p.apply(report,false,false,0,0,0);
    assert(!(report[44]|report[45]|report[46]));
    p.accepted(report,false,false,0,0,0,p.is_restore_report(report));

    // Actual host release/setup are retried until sent, then never replayed by ticks.
    host[1]=0x18;host[43]=4;host[38]=2;host[41]=1;p.host_update(host,63);
    memcpy(report,host,63);p.apply(report,false,true,1,2,3);
    assert(!(report[1]&8)&&!(report[38]&2)); // fixed profile retains ownership
    p.accepted(report,false,true,1,2,3);
    memcpy(report,host,63);p.apply(report,false,false,0,0,0);
    assert((report[1]&8)&&!(report[1]&16)&&(report[38]&2)&&report[41]==1);
    assert(p.pending(false,false,0,0,0));
    p.accepted(stale,false,false,0,0,0);assert(p.pending(false,false,0,0,0));
    p.accepted(report,false,false,0,0,0);
    memcpy(report,host,63);p.apply(report,false,false,0,0,0);
    assert(!(report[1]&8)&&!(report[38]&2));
    p.accepted(report,false,false,0,0,0,p.is_restore_report(report));
    assert(!p.pending(false,false,0,0,0));

    // A late queued startup packet must be followed by the latest colour.
    p.accepted(startup,false,false,0,0,0);assert(p.pending(false,false,0,0,0));
    memset(report,0,63);p.apply(report,false,false,0,0,0);
    p.accepted(report,false,false,0,0,0,p.is_restore_report(report));
    assert(!p.pending(false,false,0,0,0));
    // Battery notifications must not become the cached game colour.
    report[44]=255;p.apply(report,false,false,0,0,0,true);
    assert(!p.is_restore_report(report));p.accepted(report,false,false,0,0,0);
    assert(p.pending(false,false,0,0,0));
    memset(report,0,63);p.apply(report,false,false,0,0,0);
    assert((report[1]&4)&&report[44]==0);
    p.accepted(report,false,false,0,0,0,p.is_restore_report(report));
    assert(!p.pending(false,false,0,0,0));
    // Repeated identical game colours must not create periodic control traffic.
    memset(host,0,63);host[1]=4;
    for(int i=0;i<1000;i++) { p.host_update(host,63);assert(!p.pending(false,false,0,0,0)); }
    p.reset();assert(!p.pending(false,false,0,0,0));

    Config_body legacy;
    memset(&legacy, 0xff, sizeof(legacy));
    config_body_valid(legacy); // Actual firmware validation, not a test reimplementation.
    assert(legacy.config_version == CONFIG_VERSION && legacy.lightbar_fixed == 0);
    assert(legacy.rumble_gain == 100 && legacy.rumble_release == 0);
    assert(legacy.lightbar_r == 255 && legacy.lightbar_g == 255 && legacy.lightbar_b == 255);
    Config_body configured = legacy;
    configured.lightbar_fixed = 1;
    configured.lightbar_r = 0; configured.lightbar_g = 73; configured.lightbar_b = 255;
    configured.rumble_gain = 100; configured.rumble_release = 0;
    config_body_valid(configured);
    assert(configured.lightbar_fixed == 1 && configured.lightbar_r == 0 && configured.lightbar_g == 73);
    memcpy(fixture_name, "Audio Haptic", 12);
    fixture_body = legacy;
    fixture_body.config_version = 19;
    fixture_body.usb_gamepad_mode = 0xff;
    fixture_body.rumble_gain = fixture_body.rumble_release = 0xff;
    memset(reinterpret_cast<uint8_t *>(&fixture_body) + offsetof(Config_body, lightbar_fixed), 0xff, 4);
    const uint32_t previous_id = crc32(fixture_name, SLOT_NAME_LEN) ^
        crc32(reinterpret_cast<const uint8_t *>(&fixture_body), offsetof(Config_body, lightbar_fixed));
    assert(active_profile_restore(1, previous_id)); // Old journal identity remains valid.
    assert(g_active_slot == 1 && g_active_snapshot_valid && g_active_snapshot.lightbar_fixed == 0);
    assert(!active_profile_restore(1, previous_id ^ 1));
    fixture_body = configured;
    fixture_body.config_version = 20;
    fixture_body.usb_gamepad_mode = 0xff;
    fixture_body.rumble_gain = fixture_body.rumble_release = 0xff;
    const uint32_t v20_id = crc32(fixture_name, SLOT_NAME_LEN) ^
        crc32(reinterpret_cast<const uint8_t *>(&fixture_body), offsetof(Config_body, rumble_gain));
    assert(active_profile_restore(1, v20_id));
    assert(g_active_snapshot.rumble_gain == 100 && g_active_snapshot.rumble_release == 0);
    fixture_body = configured;
    fixture_body.config_version = 21;
    fixture_body.usb_gamepad_mode = 0xff;
    const uint32_t v21_id = crc32(fixture_name, SLOT_NAME_LEN) ^
        crc32(reinterpret_cast<const uint8_t *>(&fixture_body), offsetof(Config_body, usb_gamepad_mode));
    assert(active_profile_restore(1, v21_id) && g_active_snapshot.usb_gamepad_mode == 0);
    fixture_body = configured;
    const uint32_t current_id = resume_slot_fingerprint(fixture_name, fixture_body);
    assert(active_profile_restore(1, current_id));
    assert(g_active_snapshot.lightbar_g == 73);
    assert(!active_profile_restore(1, previous_id)); // Never accept old identity for rewritten slot.
    puts("PASS: output isolation, host interference, queue retry, no periodic sends, OFF/release/reconnect, config compatibility");
    printf("Config_body=%zu bytes, slot limit=%u, prior body=%zu\n", sizeof(Config_body), SLOT_MAX_BODY_LEN,
           offsetof(Config_body, lightbar_fixed));
}
