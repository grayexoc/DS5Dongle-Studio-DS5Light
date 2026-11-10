# exp.23 native neutral-report fix

Hardware evidence: user confirms exp.12 works, exp.13/17/20/21 fail and exp.22 broad inheritance bypass works for CrimsonPulse. This implicates cached motor-intent inheritance but does not establish every packet-level interaction.

Production policy: only in DualSense/Edge USB mode, auto_haptics_enable=0, and a report of at least four payload bytes with no motor command or other control flags, apply the incoming neutral selectors/zero motor values directly. The same payload in XInput/Mix/Replace retains the existing inheritance policy. Reports with actual trigger, volume/audio, mute/LED or other flags retain motor intent, as before. Unflagged nonzero motor values still do not infer rumble mode (exp.17 fix retained). Short reports do not select native through this exception. No PCM-silence heuristic, new persistent settings or profile migration.

Removed STUDIO_TEST_NATIVE_HOST_FLAGS option/branch; this build does not rely on the exp.22 blanket native bypass. Send-time refresh, packet layout and transport limits unchanged. This does not claim native output for every no-authority packet is defined by Sony; it is a scoped compatibility policy supported by the reproduced regression. A native-mode host that uses neutral reports as no-ops after rumble may stop that held rumble; physical compatibility remains to be checked.

Validation: seven regression scripts pass. Added neutral CrimsonPulse-like 47-byte report (unused trigger OFF bytes), repeated reports, short input, every non-motor control flag group and improved-rumble preservation; XInput/Mix behavior unchanged. Separate Release compile/link, UF2 headers/payload numbering, embedded version and packaging source hashes verified. Existing warnings remain. No flashing or exp.23 hardware confirmation.

Apply exp.23, reconnect, verify automatic haptics OFF, restart CrimsonPulse and repeat the exp.12/22 actions. Also test ordinary rumble during LED/volume changes and the earlier native special attack case.

SHA256: 312eed324e69c6eaadbfc6d7d9c9e893e146608c2c1960a3359ef18ed1c7470b
