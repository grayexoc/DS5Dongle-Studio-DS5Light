# exp.17 native-haptics mode fix

Only controller behavior change from exp.16: remove the Ninja Gaiden compatibility inference that sets UseRumbleNotHaptics solely because unflagged motor bytes are nonzero. Explicit host rumble selectors, XInput rumble and auto-haptics Mix handling remain in place.

USB capture q1 contains 6,303 Pico HID output reports; 859 have nonzero motor bytes and none request rumble through byte 0 low bits or byte 38 bit 2. Audio payloads must be excluded from this count even when their first byte happens to be 0x02.

## Result and causal chain

The user reported that exp.17 resolves the missing effect on hardware. Together with the one-behavior-change build and q1, this identifies the removed inference as the cause of the reproduced failure, not a lack of PCM amplitude.

1. The game supplies native PCM and also HID reports containing motor values without rumble selectors.
2. The old Ninja Gaiden compatibility workaround treats those values as permission to set UseRumbleNotHaptics.
3. The resulting controller state requests emulated rumble instead of preserving the native PCM mode. Both modes use the same physical actuators, not separate rumble motors.
4. Repeated game reports can reassert this selection; raising PCM gain or changing filtering cannot repair mode ownership.
5. exp.17 preserves explicit host selectors and stops inferring mode from motor magnitude. The user confirms the missing effect returns.

Earlier PCM replay worked while the game was running in the background. This is consistent with a difference in concurrent foreground HID output, but there is no paired foreground/background HID capture proving that exact difference. q1 is PC-to-Pico evidence, not an over-the-air Bluetooth trace.

## Permanent policy and regression coverage

Keep the exp.17 behavior as the normal policy. XInput explicitly generates byte 0 = 3, so its normal rumble does not rely on the removed inference. Explicit improved rumble remains honored. Active Mix/Replace keeps PCM ownership and retains raw motor values for synthesis; stream timeout still hands back to explicit rumble. Native-mode transitions cancel rumble release tails.

The host regression covers repeated unflagged motor values and trigger flags, explicit/improved rumble, return from improved rumble, Mix/Replace, stream fallback, XInput hold, and the DualSense watchdog. It executes extracted production logic with host stubs; it is not a full Bluetooth/hardware integration test.

No further runtime behavior change is needed after the successful A/B result. Follow-up changes clarify comments and extend regression coverage. No new setting, profile format, DS5Light command, gain, filter, or transmission interval is introduced.

## Limits

Games that depended on the old inference may lose general rumble. Do not reintroduce a global inference or gate it only on PCM silence: valid native streams contain silence and gaps. Any compatibility exception needs a separately reproduced case and explicit scope. The original Ninja Gaiden case has not been retested.

The successful special-attack test does not establish bit-identical wired fidelity, latency parity, every game's compatibility, or that earlier transport/DSP changes were all necessary. No automatic flash or profile reset is performed.
