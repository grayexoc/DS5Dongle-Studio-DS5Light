# Native control follow-up after exp.15

Source changes only; not yet built or tested on the controller.

- Clear only HapticPowerSave in startup mute/power byte (0x0F -> 0x0B). Explicit game mute/power commands still pass through. This is a candidate mitigation, not proof of the missing effect's cause.
- Native restore selector (byte 0 low bits 01, improved rumble off) bypasses rumble gain/release shaping, cancelling any remaining release tail immediately.
- In native mode, forward repeated USB output commands even while the speaker is active. Identical trigger commands can be intentional re-arms. Mix/Replace retain existing suppression.
- Do not compose controller state inside native audio packets when that state block will be removed anyway. Separate state reports retain the existing policy.

Checks: extracted production motor-path test covers restore during a 40 ms release; USB callback test covers repeated native commands and unchanged Mix gating; LED and ARM syntax regressions are run separately.

Remaining risk: forwarding repeated native commands can increase Bluetooth traffic. Queue delivery, special-attack restoration, actual power behavior and wired texture parity require hardware confirmation. No DSP retuning, profile migration, web settings changes, or new configuration fields.
