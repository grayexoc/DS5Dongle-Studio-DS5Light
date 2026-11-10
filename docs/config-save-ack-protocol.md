# DS5Light integration: verified configuration save

Firmware source support added after exp.23; not built yet. DS5Light files are unchanged.

Legacy command 0x02 still performs exactly one synchronous config_save(). Empty/zero-padded old payloads remain accepted; old clients may ignore the added reply. No new stream guard was added to this command, so its existing flash behavior is retained. Device policy 0x1C/0x1D audio-active protection is separate and unchanged.

Request, raw HID bytes (64 bytes including ID):
`80 66 02 <tag0 tag1 tag2 tag3> <zero padding>`
Tag is an optional four-byte request identifier; firmware echoes the bytes verbatim. An old empty/zero-padded request gets tag zero. Choose a fresh nonzero tag for each deliberate save; do not retry a save automatically after a missing reply.

Read feature report 0x84. Raw result including report ID:
`84 66 02 <status> 01 <tag0 tag1 tag2 tag3> ...`
Status: FE = processing, 00 = config_save returned verified success, 02 = config_save failed. Version marker is 01. Request tag occupies raw reply bytes 5..8 (or bytes 4..7 after stripping the 0x84 report ID).

Before starting flash work firmware replaces stale reply with FE; only after config_save returns does it publish success/failure. A returned status 00 means the journal write/no-op was verified by config_save, not just that USB accepted a packet. This does not verify all profiles/macros or substitute for power-cycle testing.

Future DS5Light flow:
1. Stop its own audio engine as before; ask user to stop external audio before settings maintenance. Do not kill other apps automatically.
2. Send one save with fresh request tag under the per-device serialization lock.
3. Poll GET 0x84 for matching command, version and tag. FE waits; 00 confirms; 02 reports failure. Allow at least 2 seconds for lockout/flash/USB scheduling; timeout is uncertain, not success.
4. Older firmware has no matching acknowledgment: show save-unconfirmed / verification unavailable, not unsupported controller, and never blindly repeat the flash write. A later RAM field read is not persistence verification.
5. Other 0x84 commands and external settings clients can overwrite replies. A wrong tag or command must not acknowledge the save; ask to close other settings clients if needed.

Example request tag 12 34 56 78 -> successful raw reply begins `84 66 02 00 01 12 34 56 78`.
