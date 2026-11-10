# Pico mapping extensions — experiment v31

Companion: DS5Light v1.0.1 Experimental. Previous v30 artifacts are preserved.

The global table stays at 32 records of 35 bytes. No slot stride, record layout,
flash placement, CRC or web configuration change is required.

| Existing byte | New meaning |
| --- | --- |
| flags (5), bit 5 | Shift layer row |
| flags (5), bit 6 | Profile action confirmation chime, default off |
| out_btn (17), 23–30 | Activate slot index 0–7, displayed as profile 1–8 |
| out_btn (17), 31 | Single physical button in chord is the momentary Shift key |

Definitions remain device global; the existing per-profile inverted enable mask
controls each row. The Shift key uses one table row. Unspecified Shift bindings
inherit Base; an enabled Shift row replaces a Base row with the same chord and
gesture. Existing chord specificity/short-long/double semantics are retained.
The Shift key is suppressed from game input. PS shortcut handling yields when
PS itself is the Shift key. Edge onboard Fn+face combinations cannot be cancelled
inside Pico and may conflict with controller-local profile switching.

Transitions cancel pulses, pending taps, key sequences and held mouse/keyboard
state. Keyboard release is retried after USB backpressure. Profile actions queue
to the main loop; empty slots fail without confirmation, selecting the current
slot does nothing, and held sources must be released before another activation.
Normal slot activation handles deferred persistence and USB re-enumeration.

Command `0x20`, payload `[subcommand, nonce32-le]`, reply on `0x84`:
`66 20 status protocol-version subcommand nonce32-le capabilities ...`.
Protocol version is 1. Subcommand 0 reads capabilities (bits 0–2: Shift,
profile outputs, chime); subcommand 1 requests preview without switching or
saving. Status 0 succeeds, 1 rejects malformed/unknown input, 2 means preview
cannot run with the current connection/build/suspend state. Replies echo the
nonce to reject stale reads; writes are never retried by the companion.

The cue uses the existing speaker encoder/packet path, a 60 ms finite tapered
waveform and a bounded silent tail. It is mixed after speaker filtering and
never enters the haptic input/DSP. With no USB audio, zero input frames are
generated only for the cue duration. Profile speaker volume and headset routing
are respected. Speaker processing, stream reset and BT recovery remain otherwise
unchanged when the optional cue is off.

Validation: original macro engine suite plus Shift override/inheritance/release,
disabled alternate, suspension, profile one-shot guard, unchanged storage,
USB-busy key release and cue bounds/wrap passed. Haptic delivery, suspend release,
LED, upstream reliability, rumble shaping, BOOTSEL dormancy, device diagnostics
and audit regression runners passed. ARM build and companion frozen startup,
embedded module/asset checks passed. This is not physical controller validation.

Artifacts: `build/xinput-exp30/ds5-studio-light_v31.uf2` (Pico 2 W, XInput
experiment enabled) and the companion's versioned Experimental ZIP. Build
directory experiment indices and firmware release versions are independent.
Physical Shift/profile/chime checks and visual inspection remain pending; the
computer-use tool rejected capture of the Python test window. No device was
flashed. Clear/disable extended records before downgrading to older firmware.

## Post-v31 review fixes — source only

- Move command `0x20` from the config-field setter into `pico_cmd_set` so the
  companion can query capabilities and request a preview through the actual HID
  command path. Diagnostics field `0x20` remains read-only and unchanged.
- Preserve pending keyboard release across repeated resets while the USB
  endpoint is busy, including burst playback with no held-key history.
- Re-arm a profile action only after all source buttons remain released for
  50 ms. A half-pad action waits for the physical pad click to release, even if
  the finger moves to the other half. Timer wrap and layer resets retain the
  release guard correctly.
- Clear both virtual trigger-axis values during macro reset.

Validation: macro-layer (including the original engine suite), device command,
suspend-release and upstream reliability runners passed. New cases cover a
one-frame dropout, stable release across timer wrap, pad-half movement, repeated
USB-busy reset during burst playback, analog cleanup, and command capability/
preview replies. ARM syntax checks passed for cmd.cpp, macro.cpp, main.cpp and
bt.cpp. These are host/mock checks, not controller validation.

No firmware linked, UF2 regenerated or device flashed. The existing v31 UF2
listed above predates these source fixes.
