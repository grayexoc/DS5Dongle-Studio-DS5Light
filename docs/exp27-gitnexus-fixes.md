# exp.27 — GitNexus review follow-up

Scope: three reported issues; no web configuration/profile schema changes.

1. DS5Light inherited StudioClient requests now call a no-op base cancellation hook.
   SettingsClient's existing override enforces cancellation/deadlines before a new send and
   around polling waits. Slot activation is not sent after cancelled metadata/info reads.
   Existing plain StudioClient consumers keep their default behavior. Already delivered writes
   cannot be rolled back by a subsequent cancel.
2. Firmware retains a suspend-release intent until a successfully accepted zero-motor/both-trigger
   OFF report drains the output FIFO. It retries only that OFF every 40 ms during suspension;
   normal synthesis remains disabled. Reconnect/reset and resume clear the pending intent.
   The FIFO drain condition prevents an old matching OFF ahead of a queued START from falsely
   acknowledging the new suspend release. No periodic OFF remains after acknowledgement.
3. Diagnostic audio opens an identity-checked four-channel stream paused, then arms native mode
   immediately before starting it. PCM is 1.5 seconds at 48 kHz, reserving time within the device's
   two-second lease. A monotonic deadline aborts delayed stream start/write; STOP and cleanup are
   still attempted. These changes do not add latency/buffering to normal audio haptics.

Regression scenarios:
- Cancel/deadline before activation and during metadata/info wait; no command 0x09 afterward.
- Three ACL-full failures, retry-budget expiry, full control queue, stale OFF ahead of START,
  acknowledgement quiescence, timestamp wrap and resume cancellation.
- 2.1-second device preparation before START, paused-open ordering, 1.5-second bounded PCM,
  stream-start overrun before any PCM, and final STOP/PortAudio cleanup.

Host checks/mock fault injection do not establish physical USB suspend, radio reliability or feel.
No device flash is performed by the build process. Existing firmware compiler warnings are unchanged.
