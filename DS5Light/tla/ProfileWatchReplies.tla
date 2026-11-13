---- MODULE ProfileWatchReplies ----
(* Source read at non-Git app snapshot, 2026-11-13.
   studio_profile_watch.py SHA256 CD5C985631E6F892D7B52BFBB3FFECAA8890438CC1B8EC2C8396623353F9CCF3.
   Follows whole studio_profile_watch.py, especially ProfileWatch.tick lines
   59-101 and close line 102; app.py _profile_tick/_watch_external_profile
   and application close retain their generation/closing guards.
   UI owns key/generation/paused/busy and applies results; each job has a worker
   pc (reading/queued/done), captured identity and generation. Queue handover
   is atomic SimpleQueue.put/get. No condition variables or racing UI writers.
   One tick is linearized against worker enqueue: enqueue after get cannot
   enable another launch because busy remains true. Timers/events abstract to
   the nondeterministic launch choice, which cannot bypass the eligibility gate.
   Identity includes token/serial/path; None represents disabled. Identity and
   pause changes are bounded by Changes, launches by Requests; no generation
   wraparound. Paths of launchable identities exist. Reads terminate under weak
   fairness and may return data, error, or no data. Failed thread starts now
   queue the captured generation with an error in tick; Reply(error) conservatively
   represents this too. Failed-start UI recovery is also checked in production tests.
   The real caller stops ticks on close; therefore close leaves busy/queued
   state intact and open-polling liveness permits close as an alternative.
   Profile bytes, physical HID validity/rebinding, timing/backoff, ProfileEvents,
   allocations/OOM, and other device-lock holders are abstracted. Device-lock
   contention is the empty reply. No lock ownership property is claimed here.
   No post-close tick is invented; close is possible before launch or after
   any success/error. No item delivery order contract exists beyond FIFO queue.
*)
EXTENDS Naturals, Sequences, FiniteSets, TLC
CONSTANTS Keys, Requests, Changes
None == "none"
Ids == 1..Requests
VARIABLES key, paused, generation, changes, busy, closed, issued,
          pc, capturedGen, capturedKey, outcome, replies,
          staleApplied, inactiveApplied, sawError, drained, changedIdentity
ui == <<key, paused, generation, changes, busy, closed, issued,
        staleApplied, inactiveApplied, sawError, drained, changedIdentity>>
worker == <<pc, capturedGen, capturedKey, outcome, replies>>
vars == <<ui, worker>>
Init == /\ key = None /\ paused = FALSE /\ generation = 0 /\ changes = 0
        /\ busy = FALSE /\ closed = FALSE /\ issued = 0
        /\ pc = [i \in Ids |-> "idle"]
        /\ capturedGen = [i \in Ids |-> 0]
        /\ capturedKey = [i \in Ids |-> None]
        /\ outcome = [i \in Ids |-> "empty"] /\ replies = <<>>
        /\ staleApplied = FALSE /\ inactiveApplied = FALSE
        /\ sawError = FALSE /\ drained = FALSE /\ changedIdentity = FALSE

Tick(k, p, launch) ==
  LET changed == k # key \/ p # paused
      g == generation + IF changed THEN 1 ELSE 0
      hasReply == Len(replies) > 0
      id == IF hasReply THEN Head(replies) ELSE 1
      b == IF hasReply THEN FALSE ELSE busy
      applies == hasReply /\ capturedGen[id] = g /\ k # None /\ ~p
      starts == launch /\ ~b /\ k # None /\ ~p /\ issued < Requests
      n == issued + 1
  IN /\ ~closed /\ (~changed \/ changes < Changes)
     /\ key' = k /\ paused' = p /\ generation' = g
     /\ changes' = changes + IF changed THEN 1 ELSE 0
     /\ busy' = IF starts THEN TRUE ELSE b
     /\ issued' = IF starts THEN n ELSE issued
     /\ pc' = [i \in Ids |-> IF starts /\ i = n THEN "reading"
                                ELSE IF hasReply /\ i = id THEN "done" ELSE pc[i]]
     /\ capturedGen' = IF starts THEN [capturedGen EXCEPT ![n] = g] ELSE capturedGen
     /\ capturedKey' = IF starts THEN [capturedKey EXCEPT ![n] = k] ELSE capturedKey
     /\ replies' = IF hasReply THEN Tail(replies) ELSE replies
     /\ staleApplied' = (staleApplied \/
          (applies /\ outcome[id] = "data" /\ (capturedGen[id] # g \/ capturedKey[id] # k)))
     /\ inactiveApplied' = (inactiveApplied \/ (applies /\ outcome[id] = "data" /\ (p \/ k = None)))
     /\ sawError' = (sawError \/ (hasReply /\ outcome[id] = "error"))
     /\ drained' = hasReply
     /\ changedIdentity' = (changedIdentity \/
          (issued > 0 /\ k # None /\ k # capturedKey[issued]))
     /\ UNCHANGED <<closed, outcome>>
Poll == \E k \in Keys \cup {None}, p \in BOOLEAN, launch \in BOOLEAN: Tick(k,p,launch)

Reply(i) == /\ pc[i] = "reading"
            /\ pc' = [pc EXCEPT ![i] = "queued"]
            /\ \E result \in {"data", "error", "empty"}: outcome' = [outcome EXCEPT ![i] = result]
            /\ replies' = Append(replies, i)
            /\ UNCHANGED <<ui, capturedGen, capturedKey>>
Close == /\ ~closed /\ closed' = TRUE /\ generation' = generation + 1
         /\ UNCHANGED <<key, paused, changes, busy, issued, staleApplied,
                        inactiveApplied, sawError, drained, changedIdentity, worker>>
Done == closed /\ UNCHANGED vars
Next == Poll \/ (\E i \in Ids: Reply(i)) \/ Close \/ Done
Spec == Init /\ [][Next]_vars /\ WF_vars(Poll) /\ (\A i \in Ids: WF_vars(Reply(i)))

TypeOK == /\ key \in Keys \cup {None} /\ paused \in BOOLEAN /\ closed \in BOOLEAN
          /\ busy \in BOOLEAN /\ generation \in 0..(Changes+1) /\ changes \in 0..Changes
          /\ issued \in 0..Requests /\ pc \in [Ids -> {"idle","reading","queued","done"}]
          /\ capturedGen \in [Ids -> 0..Changes] /\ capturedKey \in [Ids -> Keys \cup {None}]
          /\ outcome \in [Ids -> {"data","error","empty"}]
          /\ replies \in Seq(Ids) /\ Len(replies) <= Requests
          /\ staleApplied \in BOOLEAN /\ inactiveApplied \in BOOLEAN
          /\ sawError \in BOOLEAN /\ drained \in BOOLEAN /\ changedIdentity \in BOOLEAN
NoStaleApply == ~staleApplied
NoInactiveApply == ~inactiveApplied
SingleWorker == Cardinality({i \in Ids: pc[i] \in {"reading","queued"}}) <= 1
BusyClears == [](busy /\ ~closed => <>(~busy \/ closed))
PausedQueued == paused /\ Len(replies) > 0
StaleQueued == \E i \in Ids: pc[i] = "queued" /\ capturedGen[i] # generation
ClosedQueued == closed /\ Len(replies) > 0
ErrorDrained == sawError
DisabledQueued == key = None /\ Len(replies) > 0
IdentityABA == /\ changedIdentity /\ ~paused /\ key # None
               /\ \E i \in Ids: pc[i] = "queued" /\ capturedKey[i] = key
                                /\ capturedGen[i] # generation
====
