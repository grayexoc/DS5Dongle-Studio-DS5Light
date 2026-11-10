# Fixed lightbar: DS5Light integration contract

Firmware built as studio-oled-v1.4.6; no flash, web settings or DS5Light changes performed. Changed translation units passed ARM syntax-only checks; native tests passed output isolation, host interference, queue admission retry, unchanged-policy suppression, OFF/release/reconnect, legacy defaults and previous profile identity restoration. Physical controller behaviour remains unverified until a future authorized flash/test.

## Fields

| ID | Suggested key | Wire type | Meaning |
|---|---|---|---|
| 0xC1 | lightbar_fixed | u8 | 0 passthrough, 1 fixed; reject other writes |
| 0xC2 | lightbar_rgb | u32 LE | 0x00RRGGBB; valid 0..0xFFFFFF; RGB changes together |

Example #3366CC: integer 0x003366CC, wire CC 66 33 00. Black is valid. Existing field 0x19 lightbar_off overrides fixed colour. Enabling fixed colour should explicitly resolve that conflict in the UI or clear 0x19 as part of the user's enable action. Do not change unrelated settings.

Use existing commands: live write 0x01, live read 0x04, bulk write 0x0B, bulk read 0x0C, save slot 0x08, activate 0x09, slot-field read/export 0x0D. The two fields participate in these existing paths. All payloads below omit the existing report framing and zero padding.

Capability probe: bulk read payload `02 C1 C2`. Require status 0, count 2, both echoed IDs, lengths 1 and 4, and in-range values. A single 0x04 read is insufficient: old firmware echoes unknown IDs with zero data. Probe only at attach/reconnect or explicit refresh; no periodic capability polling. Unsupported firmware must not receive writes. The first release containing this feature is studio-oled-v1.4.6.

Example enable #3366CC, explicitly turning lightbar_off off: bulk-write payload `03 C2 04 CC 66 33 00 19 01 00 C1 01 01`. Validate all values before sending, confirm response and read back. The existing bulk writer can partially apply malformed requests; it is not a rollback transaction. Do not automatically replay writes after uncertain acknowledgement.

UI: one fixed toggle and colour picker, using existing Apply/Save profile flow. Send only on explicit apply/colour commit; no drag streaming, timers, repeated RGB enforcement or background flash writes. Save profile only on the existing user save action. Add both fields to profile export/import and scope/allowlist definitions; older backups missing these fields default fixed OFF. Ignore/hide advanced lightbar effects.

## Firmware behaviour

Priority is OFF > fixed > host/battery notification. State composition overwrites RGB and blocks game reset/fade commands in existing outgoing reports. It does not mutate the underlying host colour cache, haptics/audio payload or separate player/mute LEDs. Existing report RGB writes are retained for robustness; there is no separate repeating colour command. On policy change, idle control reports are requested until successful L2CAP submission (not controller acknowledgement). FIFO admission alone does not acknowledge RGB; rejection, expiry and send errors retain the pending request. Reconnect resets the policy and first submits LIGHT_OUT setup, then submits RGB separately. Delayed setup and stale colours keep the current colour pending. Fixed/OFF suppress colour notification-only report scheduling. Disabling ownership restores the underlying host colour through a report.

Config_body grew 295 -> 299 bytes, within the 486-byte slot limit. Configuration version is 20. Old records default fixed OFF, and old raw-slot fingerprints are accepted only after their old-span checksum and absent extension tail are verified. Previous UF2 artifacts are preserved; the device is unchanged until a future authorized flash.
