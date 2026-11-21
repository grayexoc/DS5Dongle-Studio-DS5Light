---- MODULE RearRouteHandover ----
(* Proposed Phase 5 protocol, informed by the activation gate in
   docs/codex-v3/STUDIO_FIRMWARE_SPEC.md:71-75 (worktree).
   Source read at 0b828f88ce6c65c66077348d6dc34f933a573c33.
   src/config.cpp:687-701 increments config_revision in set_config.
   src/audio.cpp:365-394 observes link/mode and resets USB, remainder and
   Bluetooth buffers; :477-503 reads/reassembles USB; :788-909 selects
   native/rear DSP, and :1093-1155 stages and queues haptic output. These motivate the
   boundaries; this module describes a proposed lease and drain protocol.

   A single PC producer owns the playback session. Revision or link epoch
   identifies the session together with the selected encoding. Both counters
   increase without reuse within the model. The firmware updates revocation
   atomically with an observed revision/link change. Ack/request delivery is
   asynchronous; a mismatched message is consumed without opening a route.
   Samples carry ghost provenance for the check. Firmware HAS NO such per-
   sample metadata and relies on the barrier. Transport includes all PC/USB
   submissions that could still arrive after host closure. A device-observed
   boundary certifies that it is exhausted after producer closure; this
   assumption still needs an implementation and device evidence. Device
   queues represent USB, partial frame / in-progress conversion, and queued
   Bluetooth audio. Already submitted Bluetooth packets, hardware timing,
   multiple producers, real capacities, failures and eventual progress are
   outside this finite safety model. *)
EXTENDS Naturals, Sequences

CONSTANTS Capacity, MaxRevision, MaxLink, InitialMode
VARIABLES wanted, active, boundary, producer, request, ack,
          transport, usb, partial, bluetooth, contaminated, staleAckAccepted

device == <<wanted, active, boundary>>
host == <<producer, request, ack>>
queues == <<transport, usb, partial, bluetooth>>
checks == <<contaminated, staleAckAccepted>>
vars == <<device, host, queues, checks>>
Modes == {"native", "control"}
None == [rev |-> 0, link |-> 0, mode |-> "none"]
LinkUp == wanted.link % 2 = 0
Empty(q) == Len(q) = 0
LocalDrained == Empty(usb) /\ Empty(partial) /\ Empty(bluetooth)

Init == /\ wanted = [rev |-> 1, link |-> 0, mode |-> InitialMode]
        /\ active = wanted
        /\ producer = wanted
        /\ boundary = FALSE
        /\ request = None
        /\ ack = None
        /\ transport = <<>>
        /\ usb = <<>>
        /\ partial = <<>>
        /\ bluetooth = <<>>
        /\ contaminated = FALSE
        /\ staleAckAccepted = FALSE

Revoke(next) == /\ wanted' = next
                /\ active' = None
                /\ boundary' = FALSE
                /\ UNCHANGED <<host, queues, checks>>

ChangeRevision == /\ wanted.rev < MaxRevision
                  /\ \E mode \in Modes:
                       Revoke([wanted EXCEPT !.rev = @ + 1, !.mode = mode])

ChangeLink == /\ wanted.link < MaxLink
              /\ Revoke([wanted EXCEPT !.link = @ + 1])

Submit == /\ producer # None
          /\ Len(transport) < Capacity
          /\ transport' = Append(transport, producer)
          /\ UNCHANGED <<device, host, usb, partial, bluetooth, checks>>

Arrive == /\ ~Empty(transport)
          /\ Len(usb) < Capacity
          /\ usb' = Append(usb, Head(transport))
          /\ transport' = Tail(transport)
          /\ UNCHANGED <<device, host, partial, bluetooth, checks>>

Assemble == /\ ~Empty(usb)
            /\ Empty(partial)
            /\ partial' = <<Head(usb)>>
            /\ usb' = Tail(usb)
            /\ UNCHANGED <<device, host, transport, bluetooth, checks>>

Interpret == /\ active # None
             /\ ~Empty(partial)
             /\ Len(bluetooth) < Capacity
             /\ bluetooth' = Append(bluetooth, Head(partial))
             /\ contaminated' = (contaminated \/ Head(partial) # active)
             /\ partial' = <<>>
             /\ UNCHANGED <<device, host, transport, usb, staleAckAccepted>>

Send == /\ active # None
        /\ ~Empty(bluetooth)
        /\ contaminated' = (contaminated \/ Head(bluetooth) # active)
        /\ bluetooth' = Tail(bluetooth)
        /\ UNCHANGED <<device, host, transport, usb, partial, staleAckAccepted>>

CloseProducer == /\ active = None
                 /\ producer # None
                 /\ producer' = None
                 /\ UNCHANGED <<device, request, ack, queues, checks>>

ObserveBoundary == /\ active = None
                   /\ producer = None
                   /\ Empty(transport)
                   /\ boundary' = TRUE
                   /\ UNCHANGED <<wanted, active, host, queues, checks>>

FlushDevice == /\ active = None
               /\ usb' = <<>>
               /\ partial' = <<>>
               /\ bluetooth' = <<>>
               /\ UNCHANGED <<device, host, transport, checks>>

RequestLease == /\ active = None
                /\ request = None
                /\ LinkUp
                /\ request' = wanted
                /\ UNCHANGED <<device, producer, ack, queues, checks>>

RejectStaleRequest == /\ request # None
                      /\ request # wanted
                      /\ request' = None
                      /\ UNCHANGED <<device, producer, ack, queues, checks>>

GrantLease == /\ active = None
              /\ LinkUp
              /\ request = wanted
              /\ ack = None
              /\ producer = None
              /\ boundary /\ LocalDrained
              /\ active' = wanted
              /\ ack' = wanted
              /\ request' = None
              /\ UNCHANGED <<wanted, boundary, producer, queues, checks>>

DeliverAck == LET nextProducer == IF ack = active /\ active = wanted
                                  THEN ack ELSE producer
              IN /\ ack # None
                 /\ producer' = nextProducer
                 /\ staleAckAccepted' = (staleAckAccepted \/
                      (nextProducer # producer /\ nextProducer # active))
                 /\ ack' = None
                 /\ UNCHANGED <<device, request, queues, contaminated>>

\* A suppressed/idle session may wait indefinitely; check only safety.
Idle == UNCHANGED vars

Next == ChangeRevision \/ ChangeLink \/ Submit \/ Arrive \/ Assemble \/
        Interpret \/ Send \/ CloseProducer \/ ObserveBoundary \/ FlushDevice \/
        RequestLease \/ RejectStaleRequest \/ GrantLease \/ DeliverAck \/ Idle

Spec == Init /\ [][Next]_vars

NoRearContamination == ~contaminated
NoStaleAcknowledgement == ~staleAckAccepted
LateInFlight == active = None /\ producer = None /\ ~Empty(transport)
SameModeRevision == producer # None /\ wanted.rev > producer.rev /\
                    wanted.mode = producer.mode /\ active = None
StaleRequest == request # None /\ request # wanted /\ active = None
StaleAck == ack # None /\ ack # wanted /\ active = None
LinkRevoked == ~LinkUp /\ active = None
Rearmed == wanted.rev > 1 /\ producer = wanted /\ active = wanted
====
