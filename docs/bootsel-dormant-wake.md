# BOOTSEL wake from dormant (RP2350)

Added in studio-oled-v1.4.7 for the current Pico 2 W / RP2350 ARM build.

- Maximum dormant sleep can be exited with either OLED button 2 (GPIO17) or BOOTSEL (QSPI CSn).
- BOOTSEL wakes XOSC through the RP2350 IO_QSPI dormant interrupt hardware. No periodic BOOTSEL or CPU polling runs while dormant.
- Existing shutdown, profile identity retention and normal reboot/search paths are reused. The normal stack-ready event starts inquiry; no duplicate search command is added.
- On wake, the RAM-only helper waits until BOTH buttons remain released for at least 30 ms, then restores the QSPI CS output, pad configuration and dormant IRQ enable state before returning to flash code. The wake press is consumed, including a long hold, rather than entering the normal click/hold gesture handler.
- Core1 is reset and interrupts are masked before the helper. USB/radio shutdown and clock preparation precede the call. No SDK call, logger, timer service or flash data access is permitted between releasing CSn and restoring it.
- Normal active-mode BOOTSEL single/double/triple click and long hold are unchanged. The existing BOOTSEL_POLL_DURING_AUDIO=OFF setting remains unchanged.
- OLED button 2 continues to request controller power-off/disconnect and dormant sleep during active operation. BOOTSEL does not acquire that active-mode sleep function.
- RP2040 builds retain the previous OLED-only dormant wake path. USB insertion while BOOTSEL is held retains the boot ROM update-mode behaviour.

Verification: ARM compilation/link and post-link RAM placement/call/literal checks are required for this helper. Host register-model tests execute the actual extracted helper with SDK-derived constants and cover BOOTSEL/OLED/simultaneous wake, release bounce, and register restoration. These are code checks, not proof of physical QSPI wake or measured standby current. Device flashing and physical wake/reconnect/profile checks require a separate hardware run.
