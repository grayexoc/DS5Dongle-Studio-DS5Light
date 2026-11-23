# Studio Firmware Integration Specification

## Principle
Studio firmware is not merely a passive output device. Existing firmware already contains audio/haptics DSP and output logic. V3 must reuse and clarify ownership rather than duplicate or rewrite it.

## Existing source to audit
- `src/audio.cpp`
- `src/audio.h`
- `src/usb_descriptors.cpp`
- `src/tusb_config.h`
- `src/cmd.cpp`
- `src/config.cpp`
- `src/output_diagnostics.h`
- `src/haptic_math.h`
- existing protocol docs under `docs/`

## Responsibility split
PC:
- game/process audio semantic analysis;
- background/music estimation and suppression;
- transient/event classification;
- event priority and left/right haptic-control generation.

Studio:
- hardware-facing filter/conditioning intentionally retained;
- carrier generation;
- output amplitude and safety limits;
- left/right actuator routing;
- Native Haptics coexistence;
- anti-aliasing/output handling;
- firmware telemetry and actual applied settings.

Do not run duplicate background gate, envelope, LP, or smoothing stages unintentionally. For each parameter, declare the owning stage and whether another stage is fixed, bypassed, or intentionally complementary.

## Candidate settings to optimize
Only if actually exposed and supported by firmware:
- low-pass cutoff;
- crossover;
- low/high gain;
- filter slope;
- smoothing/envelope;
- gate;
- carrier;
- global haptic gain;
- Native Haptics mix/level;
- other exposed audio-haptics values discovered in Phase 0.

Exact config keys, units, ranges, persistence and side effects must be read from current firmware source and protocol. Do not infer names/ranges from UI labels.

## Capability and apply model
Query capabilities and active settings before optimization. Report supported fields and min/max/step where feasible. PC optimizer proposes candidate values; Apply Manager validates against firmware limits. Read back actual values after apply. Keep desired state separate from applied state. Partial apply must be reported and recovered. Never raise hardware safety limits automatically.

## Four-channel routing
Current source inspection indicates a four-channel descriptor with channel mask 0x0033 and an Auto Haptics source selector. The PC output path has a stereo-to-second-pair duplication behavior in at least one implementation path. Proposed target: CH0/1 preserve speaker L/R, CH2/3 carry dedicated L/R haptic-control signals. This is not approved as physically proven until end-to-end verification of descriptor, host channel order, buffer construction, firmware source, mixing, and physical actuator response.

## Native Haptics and other controller features
Preserve Native Haptics, Effect Leak, rumble, triggers, gyro, macro, USB/Bluetooth operation and unrelated controller settings. The PC Unified Profile must not take ownership of unrelated Studio settings.

### Proposed Phase 6 intensity-only apply contract

The offline Studio candidate may propose a decrease to `auto_haptics_gain` from a stable Replace/Rear profile. It uses the chosen WAV windows and either the current PC gain or a separately verified PC candidate. A candidate computed with the PC candidate may be offered for device application only after those PC controls are already selected and a fresh Studio read confirms the same identity and baseline. The digital headroom criterion is a rehearsal estimate.

If approved, add a version-advertised conditional intensity operation with the same tagged acknowledgement pattern as route command `0x25`. Keep this contract separate from the route transaction and legacy setter. The firmware compares the full revision and checksum, expected current intensity and current Replace/Rear/auto-mute route in the same dispatch as the write. It requires Bluetooth ready, DualSense mode, idle playback/DSP/stream and no active rear authorization. It accepts only a strict reduction in the existing 0–200 range. The operation changes one RAM field, returns the new profile token, and does not issue save or slot commands.

Restore uses the exact applied token and firmware-owned one-use record. Restore is allowed only to the original recorded intensity and only while the same route remains idle. Competing writes and device reset invalidate restore eligibility. The host verifies the received token and reads the intensity and route between matching profile reads. An uncertain result disables further writes until a fresh read. Keep PC gain changes and firmware writes separate because they have different ownership and failure boundaries.

Host regressions must exercise stale tokens, changed route, busy playback, same-value and upward candidates, invalid restore targets, a competing edit, and lost acknowledgements. Review the implementation against concurrent lease and configuration changes before firmware installation or a live settings trial.

## Firmware change policy
Prefer extending existing settings/diagnostic protocol. Add a new capability command only if current metadata is insufficient. Do not rewrite the firmware or flash devices during documentation/audit. User approval is mandatory before USB channel semantic changes, output behavior changes or firmware flashing.

## Phase 5 integration increment

Use the existing Replace plus rear-DSP setting pair for the opt-in four-channel rehearsal. The host preserves stereo front PCM and encodes the centered V3 control envelope in the rear pair for Studio's existing conditioning and carrier. This path requires verified 48 kHz PCM16 four-channel playback and correct Studio profile readback before it can be sent. Existing modes keep the published USB descriptor and filtering. The new optional output-packet peak diagnostics measure quantized left/right haptic bytes before Bluetooth submission. They do not establish Bluetooth receipt or physical motion. Firmware flashing remains separately gated.

Rehearsal file generation from `DS5Light/`: `python offline.py stereo.wav rehearsal.wav --studio-pcm16`. At 48 kHz PCM16 input, CH0/1 preserve the original bytes. Other supported input rates are resampled to 48 kHz. The rear channels contain normalized control converted to PCM16. Use a verified four-channel output stream for testing; ordinary media players may downmix or remap channels. This option does not itself open a device or change settings.

The manual host check is `python studio_replay.py rehearsal.wav`. It sends only short PCM16 files (up to 1.5 seconds and 15% peak), requires a positively matched four-channel WASAPI device, an idle ready Studio, and a stable active profile with Replace, rear DSP and Replace speaker auto-mute. It reads the profile revision between 250 ms chunks and stops on detected changes. The synchronous readbacks can interrupt playback continuity; the tool is for route verification. It does not write settings or reconnect to an alternate endpoint. The approved test profile must already be configured before invocation.

### Remaining runtime activation gate

While the PC owns the rear pair, CH2/3 carry control values. A profile switch to Off or Native Mix changes the same bytes to Native PCM. A host-side profile poll can miss samples submitted between polls. The current firmware reset also observes mode changes without always draining the USB FIFO, and a profile can change while the mode value stays the same.

Before offering continuous rehearsal routing in the app, the firmware must bind host ownership to an identified playback session and config revision. On any relevant revision or link change it must revoke control ownership and suppress rear samples from the previous session before applying the new interpretation. Keep the rear pair suppressed until the old producer is closed, the playback boundary is observed by the device, and USB, partial frame and queued Bluetooth audio are drained. Start a fresh session only after verifying the new mode and revision. Stale writes and acknowledgements must leave the route suppressed. Outside a host-owned session, retain the existing Native contract.

The PC must invalidate its local session token before acknowledging closure. It may accept a grant only for the outstanding, still-current request token. The firmware must separately enforce its authoritative revision since a USB HID response and a later host write cannot be checked atomically across devices.

Required transition tests include Replace to Off while a write is in flight, same-mode profile revision change, delayed acknowledgement, disconnect and reconnect, and another sender holding the USB playback interface open. If the device cannot observe a reliable stream boundary, remain in manual rehearsal mode.

The read-only USB observation page reports accepted playback SET_INTERFACE changes and explicit invalidations. Run `python studio_replay.py rehearsal.wav --observe-boundary` on firmware advertising page 3 to capture before, during and after values. A successful observation requires a new open, an explicit alt-0 close, matching configuration revision and no observed invalidation. The observation does not grant control ownership or establish that WASAPI close drains every queued sample. In the Windows WASAPI probe, an explicit alt-0 occurred after the sole or last shared stream closed. The first of two streams closing did not advance the USB generation. The optional local discard flag records completion of the existing firmware cleanup for the current closed generation. Reopening or invalidating the endpoint clears the flag, so a close and reopen in one task pass cannot certify the prior generation. Already submitted L2CAP packets and controller queues are outside the flag. WASAPI mixing also provides no proof of which process supplied individual PCM samples.

### Rear-control authorization prototype

The host test prototype accepts an arm request only for the current known, inactive USB generation with local discard complete, a matching configuration revision and Bluetooth link epoch, and a ready route. It expects the next USB generation exactly once. An extra SET_INTERFACE, invalidation, link change, revision change, or loss of readiness revokes permission. Unsigned generation rollover is covered in the host test.

In two Windows hardware runs, exclusive Initialize opened USB before the first buffer was primed or Start was called. The prototype therefore separates arm from commit. Arm reserves the next generation while the endpoint is closed and drained and keeps rear output suppressed. Commit requires the exact newly opened generation and must follow successful exclusive acquisition by the same host. The host sends only silence until it reads a correlated successful commit. A USB open alone never grants permission. Duplicate, stale, and mismatched commits fail. HID lifetime and correlation, timeouts and app-crash recovery, and actual firmware sample and Bluetooth enqueue guards still require integration. The prototype does not participate in production firmware or app behavior.

The host-only prototype uses a 2 s pending timeout and a 1 s active timeout for fault tests. These are provisional values. Each successful arm issues a new attempt ID even when rearming the same closed USB generation. Commit and renewal must echo that attempt ID. Renewal also requires the exact next sequence, so duplicates cannot refresh the timeout. On timeout permission is denied even while USB is still active. The host should serialize renewals with at most one outstanding request. A valid request already in flight when the app dies can extend the last deadline by one active timeout. In firmware, expiry must keep the rear pair suppressed until a new verified boundary and must be checked at both sample processing and Bluetooth queue delivery.

The prototype returns Legacy, Suppress, or Control. Pending and revoked attempts suppress the rear pair, including after expiry while USB remains open. Legacy resumes only after a known closed generation reports local discard complete. When a pending attempt expires without any USB event, the same verified closed and drained generation remains eligible. An invalidation alone cannot restore Legacy.

Production integration must apply Suppress before CH2/CH3 are interpreted as either control or PCM in audio_loop, and drop queued packets from the revoked attempt at the final L2CAP send check, including a pending retry. Preserve control-only Bluetooth packets. A HID response cannot substitute for either check. Packets already accepted by L2CAP remain outside this guarantee.

The opt-in firmware integration evaluates authorization at the beginning of audio_loop and before Bluetooth interrupt-queue dequeue or retry. During suppression it zeros CH2 and CH3 before either input interpretation. Every policy transition invalidates queued and pending 0x36 audio and requests the existing DSP/USB reset. Normal Bluetooth control reports remain queued. A hardware Bluetooth disconnect advances the link epoch. The default is Legacy until an arm succeeds. The ordinary application does not yet issue this command.

The development bundle exposes the same bounded renderer without starting the GUI. Run `DS5Light.exe --studio-exclusive-replay <fixture.wav> --report <new.json>` and wait for the process. Use a new report path. A successfully submitted fixture returns exit 0 and `submitted: true`; an unavailable lease or renderer writes an error and returns 1. The bundled native adapter runs through PowerShell 7 and uses only the verified Studio endpoint. The Windows endpoint must allow exclusive use and the Studio profile must already be in Replace with rear DSP and speaker auto-mute.

At app startup, a fresh Studio Replace/Rear profile selects the managed exclusive WASAPI worker. The host verifies the same-device output, confirms the profile still requests Replace/Rear, and acquires the firmware lease. A conditional write enables speaker auto-mute for the session when required, with guarded restoration on close. The capture path submits to a bounded queue. Separate renderer and lease-renewal workers handle HID I/O. Lease expiry, queue overflow, renderer failure, device identity change, or loss of input stops playback. The app displays the reason when exclusive startup fails. Live PCM is capped to the rehearsal amplitude. Actual game output, session-length reliability and physical latency remain final-integration items.
