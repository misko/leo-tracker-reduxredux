# Radio .20: CPU acquisition and retained-IQ catch-up

The ARM coarse scanner now connects to full timing/frequency resolution and
the existing retained-IQ bootstrap through an explicit software-candidate
port. It does not fabricate a GLA1 acquisition event or supported history.
This advances the 30/60-MS/s FPGA integration; live acquisition, native
handoff/feedback, scanning and refinement remain unfinished.

The implementation is firmware-worktree commit
`3a6d9321252de5094efb75c1ea47b2826ce9d48a`, following the native
[30/60-MS/s commissioning](2026_09_12_radio20_native_30_60_commissioning.md).
It adds `glrt_cpu_seed`, an entry point in the existing bounded worker, and
a standalone saved-IQ benchmark. The original worker's cancellation,
retention, deadline and quality checks remain in use.

## Actual ARM measurements

Radio `192.168.1.20`, serial `1040005e0b100007100010000bf33a5d4d`, ran the new
executable on its previously recorded captures. Each capture supplies four
14000-sample blind search windows and 447851 retained samples per window.
All processing uses the FPGA-exported 2.5-MS/s IQ representation.

| Saved capture's native rate | ARM scan per window | Resolution and past-pilot checks | Supported handoffs |
| --- | --- | --- | --- |
| 30 MS/s | 645.57–652.68 ms | 549.80–552.49 ms | 0/4 |
| 60 MS/s | 645.97–652.38 ms | 548.49–552.08 ms | 0/4 |

The benchmark resolves each window's highest-scoring proposal, then checks
eight actual past pilots. All eight proposals failed the unchanged support
gate. This does not establish that either entire capture lacks a PSS; the
remaining candidates and broader acquisition coverage were not assessed.

Receiver time is **frozen at a saved snapshot** in this benchmark. Its epoch
is an offline replay identity. These measurements establish numerical
throughput and rejection behavior, not loaded DMA performance, live seed
freshness or native job admission. No FPGA tracking jobs were submitted.

Both runs used the resident `glrt-iq-tracking-r30000000-v1` image. The second
row refers to previously saved 60-MS/s IQ, not a new 60-MS/s deployment.
The operator held the normal production lease and serial lock, checked the
pinned SSH identity and payload hashes, and removed its temporary files.
The before/after firmware, boot identity, TX state and idle-buffer receipts
were identical. No new RF samples were collected.

## Numerical and failure validation

Independent replay checked 293304 coarse scores, 136 timing/frequency
hypotheses and 64 complete sets of integer moments against the original
saved IQ. Every integer matched; maximum absolute floating difference was
below `9e-19`. These checks validate the computation, not physical lock.

The complete blind executable produced supported handoffs at all four
synthetic-pilot window positions. Its zero-signal control produced no
candidate. Separate seed/worker tests cover fractional and large sample
coordinates, overwritten IQ, source identity, cancellation, deadlines,
retention failures and stale handoffs. The relevant test groups passed:
188 seed/worker/session tests, nine existing IIO/FFTW probe tests, and two
complete CPU-chain executable tests.

Compact evidence is retained in
[the accompanying JSON](figures/2026_09_12_radio20_cpu_acquisition_catchup/evidence.json).
The full IQ, score grids, numerical journals, deployment and operator
receipts remain under
`/srv/bulk/leo/glrt-deployment-20260909/radio20-iq-tracking-20260912/`, in
`hardware30-v1/`, `hardware60-v3/`, `cpu-tracking-arm-v1/` and
`cpu-tracking-arm-saved60-v1/`.

The next hardware step remains continuous GLI1 ingestion alongside ARM
acquisition, followed by catch-up with advancing source time, supported
native handoff and feedback. Both 30 and 60 MS/s need that evidence before
the full tracker can be declared working.
