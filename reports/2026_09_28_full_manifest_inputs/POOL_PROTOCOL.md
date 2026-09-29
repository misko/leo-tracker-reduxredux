# Execution-only amendment: four bounded input workers

Applies only to future stages launched by launch_batch_pool.py. Original
protocols, launchers, scientific settings, plan membership and existing seals
remain unchanged. Checkpoint 06 measured 799.88 summed job seconds for ten
recordings, with peak RSS below 0.9 GiB per worker. Eighty recordings remained
unprepared then; preparation is the measured bottleneck. Available memory was
approximately 94 GiB when this amendment was prepared.

Permit at most four concurrent scientific input workers, each executing one
existing fixed chronological five-record batch. Different batches from the
same dataset may coexist. Each launcher takes a shared global lock, shared
locks for BOTH DS8 and DS9, an exclusive dataset/batch lock, and one of four
exclusive worker-slot locks. Thus serial and older two-worker launchers cannot
overlap this mode, duplicate batches cannot start, and a fifth worker fails
before science. Locks are held for the full invocation and released on exit.
No modeling worker may overlap this input mode; verify that before launch.

Before each stage require MemAvailable >= 4 GiB for validation, 4.5 GiB for
observations and 5 GiB for bank export. These are three GiB above original
serial thresholds and are not reservations against production workloads.
Preserve unstarted stages on insufficient headroom or time. Do not alter
production services or force capacity.

Use stage caps of 120/240/30 seconds. Only the observation cap increases from
60 seconds: DS9-F028 produced its complete observation file but timed out at
60.17 seconds before successful process exit. Its separate recovery is recorded
in RECOVERY_PROTOCOL.md; the original failure remains evidence. The cause of
its late exit is not established. Do not enable this pool until that bounded
recovery and its numerical-content equivalence check succeed.

Preserve the 4 GiB address-space cap, BLAS1/nice19, 1800-second invocation
deadline, eligibility gates, partition,
candidate banks and no-retry policy. No automatic queue, scientific retry,
new RF collection, waveform read, provider fetch or QNAP write is introduced.
Select only frozen disjoint missing-input batches. The unchanged scientific
runner determines numerical outputs. Audit and publish only after all input
workers are terminal. Bind this amendment, launcher, lock helper and tests in
every new stage receipt. This is execution capacity, not model retuning.
