---- MODULE SpeakerOwnership ----
(* Derived from the BoundedQueue template (GPL-3.0-only).
Source read at 383552c1efc131a6e0cb24992f8b00f34d990673 plus current working tree.
Read whole src/audio.cpp (1-1311). Correspondence:
  freeQ/pending/data: speaker_blocks/free_speaker_blocks/audio_fifo, 182-219.
  Start/Acquire/Steal/Write/CheckFull/Evict/ReturnOld/Enqueue: 202-219;
  Reset/Drain/ReturnReset: audio_loop 366-383 and discard_speaker_queue 197-200;
  Take/CheckGeneration/Encode/Publish/ReturnWorker: 1140-1188;
  Init: audio_init 1108-1130. Generation/publication lock: 298-312,375-381.
Callers: main.cpp 1603-1612 invokes audio_loop serially on core0; USB callback
1335 and bt.cpp 1053 request reset (do not themselves mutate pool ownership).
Assumptions: Pico queue_try_add/remove/is_full are individually linearizable;
queue locking supplies inter-core visibility; initialization completes before
core1 runs; exactly one producer/resetter and one worker, no reentrant core0
pool calls. Core0 never resets mid-publish. One transition per queue operation;
a detached evicted/reset index is explicitly held until returned. Failed queue
removal and subsequent fallback are distinct steps. Failed enqueue is modeled.
Write abstracts the entire PCM memcpy: only producer-held storage is writable.
Worker captures the item at removal and NoOverwrite checks it remains stable.
Each opus_cs critical section is atomic (no nested acquisition, no allocation,
exit, exception or longjmp under these sections). No explicit mutex owner is
needed because the source acquires it once per modeled section. Encode is an
unlocked phase and may fail for any item; it does not publish on failure.
Reset increments generation before draining; worker may take during the drain.
Bounded Resets abstracts finitely many route/link/config resets; no uint32 wrap.
Items is a finite input prefix. Dropped PCM is allowed; publication is FIFO as a
subsequence. Only successful publication events checked, not output consumption,
Opus bytes, route values, 25ms expiry, mic, WFE/SEV, sleep or link starvation.
Liveness assumes worker initialized successfully, link remains runnable, no
committed sleep, terminating codec calls and weakly fair core0/core1 scheduling.
No consumer close/end/error API, CV waits, mutex unwind or multiple workers
exists in this protocol, so those template requirements are inapplicable.
AllReturned proves finite-prefix reclamation, not realtime playback or hardware.
*)
EXTENDS Naturals, Sequences, FiniteSets, TLC
CONSTANTS Pool, Depth, Items, Resets
VARIABLES freeQ, pending, data, epochs, ppc, held, old, made,
          wpc, work, captured, generation, resetCount, lastPublished,
          publicationOK, orderOK
producer == <<ppc, held, old, made>>
worker == <<wpc, work, captured>>
shared == <<freeQ, pending, data, epochs, generation, resetCount,
            lastPublished, publicationOK, orderOK>>
vars == <<producer, worker, shared>>
Slots == 1..Pool
Held(i) == IF i = 0 THEN {} ELSE {i}
Elements(q) == {q[i] : i \in 1..Len(q)}
Init == /\ freeQ = [i \in 1..Pool |-> i] /\ pending = <<>>
        /\ data = [i \in Slots |-> 0] /\ epochs = [i \in Slots |-> 0]
        /\ ppc = "idle" /\ held = 0 /\ old = 0 /\ made = 0
        /\ wpc = "idle" /\ work = 0 /\ captured = 0
        /\ generation = 1 /\ resetCount = 0 /\ lastPublished = 0
        /\ publicationOK = TRUE /\ orderOK = TRUE
Start == /\ ppc = "idle" /\ made < Items
         /\ made' = made + 1 /\ ppc' = "acquire"
         /\ UNCHANGED <<held, old, worker, shared>>
Acquire == /\ ppc = "acquire"
           /\ IF Len(freeQ) > 0
                 THEN /\ held' = Head(freeQ) /\ freeQ' = Tail(freeQ)
                      /\ ppc' = "write"
                 ELSE /\ held' = held /\ freeQ' = freeQ /\ ppc' = "steal"
           /\ UNCHANGED <<old, made, worker, pending, data, epochs, generation,
                          resetCount, lastPublished, publicationOK, orderOK>>
Steal == /\ ppc = "steal"
         /\ IF Len(pending) > 0
               THEN /\ held' = Head(pending) /\ pending' = Tail(pending)
                    /\ ppc' = "write"
               ELSE /\ held' = held /\ pending' = pending /\ ppc' = "idle"
         /\ UNCHANGED <<old, made, worker, freeQ, data, epochs, generation,
                        resetCount, lastPublished, publicationOK, orderOK>>
Write == /\ ppc = "write"
         /\ data' = [data EXCEPT ![held] = made]
         /\ epochs' = [epochs EXCEPT ![held] = generation]
         /\ ppc' = "checkFull"
         /\ UNCHANGED <<held, old, made, worker, freeQ, pending, generation,
                        resetCount, lastPublished, publicationOK, orderOK>>
CheckFull == /\ ppc = "checkFull"
             /\ ppc' = IF Len(pending) = Depth THEN "evict" ELSE "enqueue"
             /\ UNCHANGED <<held, old, made, worker, shared>>
Evict == /\ ppc = "evict"
         /\ IF Len(pending) > 0
               THEN /\ old' = Head(pending) /\ pending' = Tail(pending)
                    /\ ppc' = "returnOld"
               ELSE /\ old' = old /\ pending' = pending /\ ppc' = "enqueue"
         /\ UNCHANGED <<held, made, worker, freeQ, data, epochs, generation,
                        resetCount, lastPublished, publicationOK, orderOK>>
ReturnOld == /\ ppc = "returnOld"
             /\ freeQ' = Append(freeQ, old) /\ old' = 0 /\ ppc' = "enqueue"
             /\ UNCHANGED <<held, made, worker, pending, data, epochs, generation,
                            resetCount, lastPublished, publicationOK, orderOK>>
Enqueue == /\ ppc = "enqueue"
           /\ IF Len(pending) < Depth
                 THEN /\ pending' = Append(pending, held) /\ held' = 0
                      /\ ppc' = "idle"
                 ELSE /\ pending' = pending /\ held' = held /\ ppc' = "returnFailed"
           /\ UNCHANGED <<old, made, worker, freeQ, data, epochs, generation,
                          resetCount, lastPublished, publicationOK, orderOK>>
ReturnFailed == /\ ppc = "returnFailed"
                /\ freeQ' = Append(freeQ, held) /\ held' = 0 /\ ppc' = "idle"
                /\ UNCHANGED <<old, made, worker, pending, data, epochs, generation,
                               resetCount, lastPublished, publicationOK, orderOK>>
Reset == /\ ppc = "idle" /\ resetCount < Resets
         /\ generation' = generation + 1 /\ resetCount' = resetCount + 1
         /\ ppc' = "drain"
         /\ UNCHANGED <<held, old, made, worker, freeQ, pending, data, epochs,
                        lastPublished, publicationOK, orderOK>>
Drain == /\ ppc = "drain"
         /\ IF Len(pending) > 0
               THEN /\ old' = Head(pending) /\ pending' = Tail(pending)
                    /\ ppc' = "returnReset"
               ELSE /\ old' = old /\ pending' = pending /\ ppc' = "idle"
         /\ UNCHANGED <<held, made, worker, freeQ, data, epochs, generation,
                        resetCount, lastPublished, publicationOK, orderOK>>
ReturnReset == /\ ppc = "returnReset"
               /\ freeQ' = Append(freeQ, old) /\ old' = 0 /\ ppc' = "drain"
               /\ UNCHANGED <<held, made, worker, pending, data, epochs, generation,
                              resetCount, lastPublished, publicationOK, orderOK>>
Take == /\ wpc = "idle" /\ Len(pending) > 0
        /\ work' = Head(pending) /\ captured' = data[Head(pending)]
        /\ pending' = Tail(pending) /\ wpc' = "checkGeneration"
        /\ UNCHANGED <<producer, freeQ, data, epochs, generation, resetCount,
                       lastPublished, publicationOK, orderOK>>
CheckGeneration == /\ wpc = "checkGeneration"
                   /\ wpc' = IF epochs[work] = generation THEN "encode" ELSE "return"
                   /\ UNCHANGED <<work, captured, producer, shared>>
Encode == /\ wpc = "encode" /\ wpc' \in {"publish", "return"}
          /\ UNCHANGED <<work, captured, producer, shared>>
Publish == /\ wpc = "publish" /\ wpc' = "return"
           /\ IF epochs[work] = generation
                 THEN /\ lastPublished' = data[work]
                      /\ publicationOK' = (publicationOK /\ (epochs[work] = generation))
                      /\ orderOK' = (orderOK /\ (data[work] > lastPublished))
                 ELSE UNCHANGED <<lastPublished, publicationOK, orderOK>>
           /\ UNCHANGED <<work, captured, producer, freeQ, pending, data, epochs,
                          generation, resetCount>>
ReturnWorker == /\ wpc = "return"
                /\ freeQ' = Append(freeQ, work) /\ work' = 0 /\ wpc' = "idle"
                /\ UNCHANGED <<captured, producer, pending, data, epochs, generation,
                               resetCount, lastPublished, publicationOK, orderOK>>
Core0 == Start \/ Acquire \/ Steal \/ Write \/ CheckFull \/ Evict \/ ReturnOld
         \/ Enqueue \/ ReturnFailed \/ Reset \/ Drain \/ ReturnReset
Core1 == Take \/ CheckGeneration \/ Encode \/ Publish \/ ReturnWorker
Finished == made = Items /\ ppc = "idle" /\ pending = <<>> /\ work = 0
Done == Finished /\ UNCHANGED vars
Next == Core0 \/ Core1 \/ Done
Spec == Init /\ [][Next]_vars /\ WF_vars(Core0) /\ WF_vars(Core1)
TypeOK == /\ freeQ \in Seq(Slots) /\ pending \in Seq(Slots)
          /\ Len(freeQ) <= Pool /\ Len(pending) <= Depth
          /\ held \in 0..Pool /\ old \in 0..Pool /\ work \in 0..Pool
          /\ made \in 0..Items /\ captured \in 0..Items
          /\ data \in [Slots -> 0..Items] /\ epochs \in [Slots -> 0..(Resets+1)]
          /\ generation \in 1..(Resets+1) /\ resetCount \in 0..Resets
          /\ lastPublished \in 0..Items /\ publicationOK \in BOOLEAN /\ orderOK \in BOOLEAN
          /\ ppc \in {"idle", "acquire", "steal", "write", "checkFull", "evict",
                      "returnOld", "enqueue", "returnFailed", "drain", "returnReset"}
          /\ wpc \in {"idle", "checkGeneration", "encode", "publish", "return"}
Ownership == /\ Elements(freeQ) \cup Elements(pending) \cup Held(held) \cup Held(old) \cup Held(work) = Slots
             /\ Len(freeQ) + Len(pending) + Cardinality(Held(held)) +
                 Cardinality(Held(old)) + Cardinality(Held(work)) = Pool
NoOverwrite == work # 0 => data[work] = captured
CurrentPublication == publicationOK
OrderedPublication == orderOK
AllReturned == <>(Finished /\ Len(freeQ) = Pool)
QueueFull == Len(pending) = Depth
WorkerDuringReset == ppc = "drain" /\ work # 0
StaleBeforePublish == wpc = "publish" /\ epochs[work] # generation
StealNeeded == ppc = "steal" /\ Len(pending) > 0
DetachedEviction == ppc = "returnOld" /\ old # 0
====
