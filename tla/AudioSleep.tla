---- MODULE AudioSleep ----
(* Source read at 383552c1efc131a6e0cb24992f8b00f34d990673 plus working tree.
   Entire src/audio.cpp and src/manual_power.cpp read. Correspondence:
   audio.cpp:129-131 audio_stop_state/worker_failed; 149-170 prepare_sleep;
   1227-1278 startup failure; 1280-1298 core1 CAS/processing/WFE loop;
   manual_power.cpp:132-139 aborts shutdown on false, 153-157 teardown/reset.
   One core0 caller, one core1 worker; bounded Attempts sequential calls.
   State 0 running, 1 request, 2 prepared, 3 committed. Strong CAS is one
   atomic step, including returning the observed value on failure. Loads and
   following CAS are separate, so acknowledgement may win the timeout race.
   Failed is published only after startup cleanup; no subsequent DSP work.
   WorkerMode 0=started, 1=delayed successful startup, 2=already failed,
   3=startup may fail before or after caller's first failed-flag read.
   Disabled abstracts DISABLE_SPEAKER_PROC: no launched worker, immediate true.
   A worker work phase abstracts the link check and optional speaker_proc/
   mic_proc calls and finite queue/codec operations. It may finish after cancellation but never after
   successful prepare. No codec termination or lock-freedom proof is implied.
   WFE uses a saturating event latch: SEV remains pending until consumed;
   entering WFE and consuming a pending event are distinct from state loads.
   No spurious events are required; their omission is conservative for waits.
   WF on each enabled core0/core1 phase and the elapsed-deadline step assumes
   scheduler progress, finite startup/work, and advancing time. No 2s real-time
   latency bound, C++ weak-memory/compiler mapping, SDK reset wrapper behavior,
   flash safety or dormant hardware behavior is checked. Atomic operations are
   coherent; acquire/release publication is abstracted by interleaving.
   Requests only resume after a false return; a true return ends this model
   because enter_dormant resets core1. There are no queue resources, mutex,
   unwind, delivery ordering or free operations in this handshake scope.
   A terminal stutter avoids reporting normal end/park as a deadlock; liveness
   catches a lost event. Delayed worker and failure-after-read are witnesses.
*)
EXTENDS Naturals
CONSTANTS Attempts, WorkerMode, Disabled
VARIABLES state, failed, event, cpc, result, attempt, expired, wpc, ack
core0 == <<cpc, result, attempt, expired>>
core1 == <<wpc, failed, ack>>
vars == <<state, event, core0, core1>>

Init == /\ state = 0 /\ event = FALSE
        /\ cpc = "start" /\ result = "none" /\ attempt = 1 /\ expired = FALSE
        /\ failed = (WorkerMode = 2)
        /\ wpc \in IF Disabled \/ WorkerMode = 2 THEN {"dead"}
                   ELSE IF WorkerMode = 0 THEN {"loop", "work", "idleWfe", "idleWait"}
                   ELSE {"startup"}
        /\ ack = FALSE

Start == /\ cpc = "start"
         /\ cpc' = IF Disabled \/ failed THEN "returned" ELSE "request"
         /\ result' = IF Disabled \/ failed THEN "true" ELSE "none"
         /\ UNCHANGED <<state, event, attempt, expired, core1>>
Request == /\ cpc = "request"
           /\ state' = 1 /\ cpc' = "requestSEV"
           /\ UNCHANGED <<event, result, attempt, expired, core1>>
RequestSEV == /\ cpc = "requestSEV"
              /\ event' = TRUE /\ cpc' = "poll"
              /\ UNCHANGED <<state, result, attempt, expired, core1>>
Poll == /\ cpc = "poll" /\ (state = 2 \/ expired)
        /\ cpc' = IF state = 2 THEN "commit" ELSE "timeoutCAS"
        /\ UNCHANGED <<state, event, result, attempt, expired, core1>>
Deadline == /\ cpc \in {"poll", "timeoutCAS"} /\ ~expired
            /\ expired' = TRUE
            /\ UNCHANGED <<state, event, cpc, result, attempt, core1>>
TimeoutCAS == /\ cpc = "timeoutCAS"
              /\ state' = IF state = 1 THEN 0 ELSE state
              /\ cpc' = IF state = 1 THEN "cancelSEV"
                        ELSE IF state = 2 THEN "commit" ELSE "poll"
              /\ UNCHANGED <<event, result, attempt, expired, core1>>
CancelSEV == /\ cpc = "cancelSEV"
             /\ event' = TRUE /\ cpc' = "returned" /\ result' = "false"
             /\ UNCHANGED <<state, attempt, expired, core1>>
Commit == /\ cpc = "commit"
          /\ state' = 3 /\ cpc' = "commitSEV"
          /\ UNCHANGED <<event, result, attempt, expired, core1>>
CommitSEV == /\ cpc = "commitSEV"
             /\ event' = TRUE /\ cpc' = "returned" /\ result' = "true"
             /\ UNCHANGED <<state, attempt, expired, core1>>
Retry == /\ cpc = "returned" /\ result = "false" /\ attempt < Attempts
         /\ cpc' = "start" /\ result' = "none"
         /\ attempt' = attempt + 1 /\ expired' = FALSE
         /\ UNCHANGED <<state, event, core1>>

Startup == /\ wpc = "startup"
           /\ wpc' = IF WorkerMode = 3 THEN "dead" ELSE "loop"
           /\ failed' = (WorkerMode = 3)
           /\ UNCHANGED <<state, event, core0, ack>>
WorkerCAS == /\ wpc = "loop"
             /\ state' = IF state = 1 THEN 2 ELSE state
             /\ wpc' = IF state = 1 THEN "preparedCheck" ELSE "work"
             /\ ack' = IF state = 1 THEN TRUE ELSE ack
             /\ UNCHANGED <<event, core0, failed>>
Work == /\ wpc = "work" /\ wpc' = "idleWfe"
        /\ UNCHANGED <<state, event, core0, failed, ack>>
IdleWfe == /\ wpc = "idleWfe"
           /\ wpc' = IF event THEN "loop" ELSE "idleWait"
           /\ event' = FALSE
           /\ UNCHANGED <<state, core0, failed, ack>>
IdleWake == /\ wpc = "idleWait" /\ event
            /\ wpc' = "loop" /\ event' = FALSE
            /\ UNCHANGED <<state, core0, failed, ack>>
PreparedCheck == /\ wpc = "preparedCheck"
                 /\ wpc' = IF state = 2 THEN "preparedWfe" ELSE "afterPrepared"
                 /\ UNCHANGED <<state, event, core0, failed, ack>>
PreparedWfe == /\ wpc = "preparedWfe"
               /\ wpc' = IF event THEN "preparedCheck" ELSE "preparedWait"
               /\ event' = FALSE
               /\ UNCHANGED <<state, core0, failed, ack>>
PreparedWake == /\ wpc = "preparedWait" /\ event
                /\ wpc' = "preparedCheck" /\ event' = FALSE
                /\ UNCHANGED <<state, core0, failed, ack>>
AfterPrepared == /\ wpc = "afterPrepared"
                 /\ wpc' = IF state = 3 THEN "parked" ELSE "work"
                 /\ UNCHANGED <<state, event, core0, failed, ack>>

Caller == Start \/ Request \/ RequestSEV \/ Poll \/ TimeoutCAS \/ CancelSEV
          \/ Commit \/ CommitSEV \/ Retry
Worker == Startup \/ WorkerCAS \/ Work \/ IdleWfe \/ IdleWake
          \/ PreparedCheck \/ PreparedWfe \/ PreparedWake \/ AfterPrepared
Next == Caller \/ Worker \/ Deadline \/ (cpc = "returned" /\ UNCHANGED vars)
Spec == Init /\ [][Next]_vars /\ WF_vars(Caller) /\ WF_vars(Worker)
        /\ WF_vars(Deadline)

TypeOK == /\ state \in 0..3 /\ failed \in BOOLEAN /\ event \in BOOLEAN
          /\ ack \in BOOLEAN /\ attempt \in 1..Attempts /\ expired \in BOOLEAN
          /\ result \in {"none", "false", "true"}
          /\ cpc \in {"start", "request", "requestSEV", "poll", "timeoutCAS",
                       "cancelSEV", "commit", "commitSEV", "returned"}
          /\ wpc \in {"startup", "dead", "loop", "work", "idleWfe", "idleWait",
                       "preparedCheck", "preparedWfe", "preparedWait", "afterPrepared", "parked"}
Quiescent == wpc \in {"preparedCheck", "preparedWfe", "preparedWait", "afterPrepared", "parked"}
NoUnsafeCommit == /\ (state = 3 => ack /\ Quiescent)
                  /\ (result = "true" => Disabled \/ failed \/ state = 3)
TimeoutSafe == result = "false" => state = 0
Final == cpc = "returned" /\ (result = "true" \/ attempt = Attempts)
EventualReturn == <>Final
\* Cancellation permits the ordinary loop/idle or a failed worker, not a park.
TimeoutRecovery == (Final /\ result = "false") ~>
                   (wpc \in {"loop", "work", "idleWfe", "idleWait", "dead"})
CommitParks == (state = 3) ~> (wpc = "parked")

Acknowledged == state = 2 /\ Quiescent
TimedOut == cpc = "returned" /\ result = "false"
Committed == state = 3 /\ wpc = "parked"
DelayedWorker == TimedOut /\ wpc = "startup"
FailureAfterRead == failed /\ cpc = "poll" /\ state = 1
KnownFailure == result = "true" /\ failed /\ state = 0
TimeoutAckRace == cpc = "timeoutCAS" /\ state = 2
====
