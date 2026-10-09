# Explicit user pause

User requested pausing research to discuss a clean ablation from deployed hard60.
The supported goal lifecycle now reports PAUSED. Production was not stopped.

The two iteration84 research Python processes were suspended using SIGSTOP:
PID4121459 / exec43900 shard0; PID4121460 / exec81101 shard1.
Both were authoritatively verified in process state T after suspension.
At suspension129/148 member results were complete (DS16 63, DS17 51, DS18 15).
The unfinished members in progress were DS18-017 and DS18-016 respectively.
Iteration83 remains checkpointed with no live worker.

Do not resume automatically. On explicit user resume, inspect process state and
receipts first. Suspension can inflate wall-clock measurements/timeouts for an
in-flight fit: do not treat those affected fits as ordinary matched-budget runs.
Preserve all receipts and use a separately frozen retry if needed, rather than
silently accepting contaminated timing or overwriting an immutable attempt.
Completed pre-pause receipts are retained. No model or operational selection
policy changed as part of pausing.
