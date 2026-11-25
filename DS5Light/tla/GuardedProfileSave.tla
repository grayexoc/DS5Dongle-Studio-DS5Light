--------------------------- MODULE GuardedProfileSave ---------------------------
EXTENDS Naturals

\* Source read at 53d5e8bac6bdf3c34bdd5a09e82f268758b2783c, plus working-tree fix.
\* DS5Light/studio_settings_ui.py:888-1046, StudioSettings.apply:
\* immutable intended configuration token, separate slot and boot-save outcomes.
\* DS5Light/studio_settings_protocol.py:126-152,476-501, command/save_flash/save_slot:
\* each write is sent once, and positive ACK is correlated to that request.
\* src/cmd.cpp:666-673,712-721,798-827, profile_save_guard_matches/pico_cmd_set;
\* src/config.cpp:599-614,935-961, config_save_impl/slot_save:
\* token and active slot validation and flash dispatch run together on core 0.
\* DS5Light/studio_reconnect.py:19-end, wait_for_macros: same-device read only.
\* Scope starts once the expected live snapshot has been validated. Zero is its
\* token. Edits can change the token, and selecting a different destination can
\* change slot identity without changing the token. The model has one app save.
\* Flash is represented by the durable state at command completion. Each command
\* can fail, or commit and lose its response. No hardware timing, flash bit errors,
\* token wrap/collision, destination edits with unchanged token and active index,
\* weak USB identity evidence, or legacy protocol is modeled. 'unavailable'
\* also abstracts an early return from a save failure with no automatic readback.
\* Weak fairness models a running host's bounded ACK waits and recovery deadline.

CONSTANTS Slots, Edits

VARIABLES phase, slotStatus, bootStatus, slotSends, bootSends, recovery,
          token, active, slotVersion, bootVersion, reply, usb

host == <<phase, slotStatus, bootStatus, slotSends, bootSends, recovery>>
firmware == <<token, active, slotVersion, bootVersion, reply>>
vars == <<host, firmware, usb>>

Outcomes == {"none", "done", "rejected", "conflict", "unknown"}
Phases == {"start", "slotDispatch", "slotReply", "bootStart", "bootDispatch",
           "bootReply", "recover", "finished"}
UsbStates == {"initial", "missing", "foreign", "returned"}
Source == 1
Destination == Slots
OriginalDevice == usb \in {"initial", "returned"}
TokenMatches == token = 0

Init ==
    /\ phase = "start"
    /\ slotStatus = "none"
    /\ bootStatus = "none"
    /\ slotSends = 0
    /\ bootSends = 0
    /\ recovery = "none"
    /\ token = 0
    /\ active = Source
    /\ slotVersion = Edits + 1
    /\ bootVersion = Edits + 1
    /\ reply = "none"
    /\ usb = "initial"

Edit ==
    /\ token < Edits
    /\ token' = token + 1
    /\ UNCHANGED <<host, active, slotVersion, bootVersion, reply, usb>>

ChangeActive ==
    /\ \E i \in 1..Slots: /\ i # active /\ active' = i
    /\ UNCHANGED <<host, token, slotVersion, bootVersion, reply, usb>>

UsbChange ==
    /\ \/ /\ usb = "initial" /\ usb' = "missing"
       \/ /\ usb = "missing" /\ usb' \in {"foreign", "returned"}
       \/ /\ usb = "foreign" /\ usb' = "returned"
    /\ UNCHANGED <<host, firmware>>

SendSlot ==
    /\ phase = "start"
    /\ slotSends < 2
    /\ phase' = "slotDispatch"
    /\ slotSends' = slotSends + 1
    /\ reply' = "none"
    /\ UNCHANGED <<slotStatus, bootStatus, bootSends, recovery, token, active,
                   slotVersion, bootVersion, usb>>

SlotGuard == TokenMatches /\ active = Source

DispatchSlot ==
    /\ phase = "slotDispatch"
    /\ OriginalDevice
    /\ phase' = "slotReply"
    /\ IF SlotGuard
       THEN \/ /\ reply' = "done"
               /\ slotVersion' = token
               /\ active' = Destination
            \/ /\ reply' = "rejected"
               /\ UNCHANGED <<slotVersion, active>>
       ELSE /\ reply' = "conflict"
            /\ UNCHANGED <<slotVersion, active>>
    /\ UNCHANGED <<slotStatus, bootStatus, slotSends, bootSends, recovery,
                   token, bootVersion, usb>>

ReceiveSlot ==
    /\ phase = "slotReply"
    /\ OriginalDevice
    /\ slotStatus' = reply
    /\ phase' = IF reply = "done" THEN "bootStart" ELSE "recover"
    /\ UNCHANGED <<bootStatus, slotSends, bootSends, recovery, firmware, usb>>

TimeoutSlot ==
    /\ phase \in {"slotDispatch", "slotReply"}
    /\ phase' = "recover"
    /\ slotStatus' = "unknown"
    /\ UNCHANGED <<bootStatus, slotSends, bootSends, recovery, firmware, usb>>

CancelBeforeBoot ==
    /\ phase = "bootStart"
    /\ phase' = "recover"
    /\ UNCHANGED <<slotStatus, bootStatus, slotSends, bootSends, recovery, firmware, usb>>

SendBoot ==
    /\ phase = "bootStart"
    /\ bootSends < 2
    /\ phase' = "bootDispatch"
    /\ bootSends' = bootSends + 1
    /\ reply' = "none"
    /\ UNCHANGED <<slotStatus, bootStatus, slotSends, recovery, token, active,
                   slotVersion, bootVersion, usb>>

BootGuard == TokenMatches /\ active = Destination

DispatchBoot ==
    /\ phase = "bootDispatch"
    /\ OriginalDevice
    /\ phase' = "bootReply"
    /\ IF BootGuard
       THEN \/ /\ reply' = "done"
               /\ bootVersion' = token
            \/ /\ reply' = "rejected"
               /\ UNCHANGED bootVersion
       ELSE /\ reply' = "conflict"
            /\ UNCHANGED bootVersion
    /\ UNCHANGED <<slotStatus, bootStatus, slotSends, bootSends, recovery,
                   token, active, slotVersion, usb>>

ReceiveBoot ==
    /\ phase = "bootReply"
    /\ OriginalDevice
    /\ bootStatus' = reply
    /\ phase' = "recover"
    /\ UNCHANGED <<slotStatus, slotSends, bootSends, recovery, firmware, usb>>

TimeoutBoot ==
    /\ phase \in {"bootDispatch", "bootReply"}
    /\ phase' = "recover"
    /\ bootStatus' = "unknown"
    /\ UNCHANGED <<slotStatus, slotSends, bootSends, recovery, firmware, usb>>

Recover ==
    /\ phase = "recover"
    /\ phase' = "finished"
    /\ recovery' \in IF OriginalDevice THEN {"original", "unavailable"}
                     ELSE {"unavailable"}
    /\ UNCHANGED <<slotStatus, bootStatus, slotSends, bootSends, firmware, usb>>

HostProgress == SendSlot \/ ReceiveSlot \/ TimeoutSlot \/ SendBoot \/ CancelBeforeBoot \/
                ReceiveBoot \/ TimeoutBoot \/ Recover
Next == HostProgress \/ DispatchSlot \/ DispatchBoot \/ Edit \/ ChangeActive \/
        UsbChange \/ (phase = "finished" /\ UNCHANGED vars)
Spec == Init /\ [][Next]_vars /\ WF_vars(HostProgress)

TypeOK ==
    /\ phase \in Phases
    /\ slotStatus \in Outcomes /\ bootStatus \in Outcomes
    /\ slotSends \in 0..2 /\ bootSends \in 0..2
    /\ recovery \in {"none", "original", "unavailable"}
    /\ token \in 0..Edits /\ active \in 1..Slots
    /\ slotVersion \in 0..(Edits + 1) /\ bootVersion \in 0..(Edits + 1)
    /\ reply \in Outcomes /\ usb \in UsbStates

IntendedSnapshot == slotVersion \in {0, Edits + 1} /\ bootVersion \in {0, Edits + 1}
NoSilentSuccess == /\ (slotStatus = "done" => slotVersion = 0)
                   /\ (bootStatus = "done" => bootVersion = 0)
SlotFirst == bootSends > 0 => slotStatus = "done"
AtMostOnce == slotSends <= 1 /\ bootSends <= 1
ConfirmedSlotStays == [] [slotStatus = "done" => slotStatus' = "done"]_vars
ReadOnlyRecovery == [] [Recover => UNCHANGED firmware]_vars
NoForeignRecovery == [] [Recover /\ ~OriginalDevice => recovery' # "original"]_vars
NoWrongActiveWrite ==
    [] [(DispatchSlot /\ slotVersion' # slotVersion => active = Source) /\
        (DispatchBoot /\ bootVersion' # bootVersion => active = Destination)]_vars
EventuallyFinished == <> (phase = "finished")

BothSaved == phase = "finished" /\ slotStatus = "done" /\ bootStatus = "done"
SlotCommittedReplyLost == slotVersion = 0 /\ slotStatus = "unknown"
BootCommittedReplyLost == bootVersion = 0 /\ bootStatus = "unknown"
GuardRejectsSlotEdit == phase = "slotReply" /\ slotVersion = Edits + 1 /\ reply = "conflict" /\ token # 0
GuardRejectsBootEdit == phase = "bootReply" /\ bootVersion = Edits + 1 /\ reply = "conflict" /\ token # 0
ForeignDuringRecovery == phase = "recover" /\ usb = "foreign"

=============================================================================
