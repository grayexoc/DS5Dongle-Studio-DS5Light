# exp.19 native age-expiry experiment

Purpose: test whether Studio's time-only 48 ms audio expiry contributes to weak/missing native texture. No authoritative source inspected specifies 48 ms as a DualSense requirement.

References:
- BTstack official protocols manual: https://bluekitchen-gmbh.com/btstack/protocols.html describes send-ready events and transient buffer-full failures, not a 48 ms audio deadline.
- Bridge v2.0.1 local reference: select_next_output_packet_locked sends queued audio without a matching age-only drop; its four-entry queue drops oldest on overflow. AUDIO_STREAM_QUEUE_LATE_US=12000 is diagnostic, not an expiry rule. Source: https://github.com/SundayMoments/DS5_Bridge/tree/v2.0.1

Trial-only build option STUDIO_TEST_NATIVE_NO_EXPIRY=ON bypasses 48 ms age expiry when auto_haptics_enable=0. Default option is OFF. Mix/Replace retains 48 ms. Queue depth/overflow eviction, 10 ms failed-audio retry budget, retry count, stream close/reset and disconnect cleanup remain unchanged. No fixed delay is inserted. During a stall, retained packets may play late; bounded memory does not imply a fixed latency bound.

The production enqueue and send-ready regression passes both configurations: normal ordered delivery, temporary ACL-full recovery, baseline expiry, native trial retention at 48 ms, continued Mix/Replace expiry, and retained failed-send retry expiry.

Build directory: build/xinput-exp19-age-test. Version: studio-xinput-exp.19-native-age-test. Includes post-exp.18 host lightbar restoration and new-setting defaults (texture off, gain 1.2). Existing valid profile values are not migrated. Compare the same saved profile, gain, speaker route, game action and physical conditions against exp.18; changing gain between tests invalidates the age-only comparison. New-setting default 1.2 can clip peaks.

Test footsteps/running first, then special attacks, speaker audio sync, stopping playback and reconnection. An improvement would support further transport investigation; it would not establish an optimal permanent deadline. No improvement does not rule out overflow or retries as other loss sources. No real Bluetooth trace or on-device timing measurement is implied by host regressions.
