# Expanded development exposes temporal misses

The unchanged local-confirmed primary completed 64 visits from two original
exposed development sessions, with membership fixed before IQ. These are the
first 32 consecutive visits in each original dev block; they are not independent
validation and were not selected by current detector outcomes. They reverse the
rate/edge combinations used by the recent development cohort.

| Rate / edge | Reference receiver identities retained | Unmatched active receiver outputs | Lost associated visits | Application / candidate mean CPU | CPU speedup |
|---|---:|---:|---:|---:|---:|
| 2.5 MS/s lower | 9/13 | 11 | 3 | 1550.66 / 14.43 ms | 107.49x |
| 5 MS/s upper | No reference positives | 2 | 0 | 4211.59 / 32.65 ms | 128.97x |

The 2.5 MS/s quality result fails the small-loss objective. The 5 MS/s sample
cannot establish sensitivity: zero reference positives is not 100% retention.
Unmatched active outputs are reference disagreements, not proven physical false
alarms. Recorded truth remains unknown. No rescue is included in this candidate.
Maximum candidate wall times are 30.11 and 45.79 ms.

## New temporal acquisition challenge

All four 2.5 MS/s misses are inactive RX1 cold-discovery results. Their reference
pair inventories have these supporting probe indices:

| Visit | Reference probes |
|---|---|
| 1679 | 0,3,4,6 |
| 1681 | 2,6 |
| 1688 | 1,9 |
| 1689 | 4,7 |

Three cases have no probe-zero member in the reference inventory. Unlike the
recent development cohort where every fixed seed recovered the same eleven
receivers, this provides a useful later-window challenge. Inventory membership
is an acquisition opportunity observation, not proof that unlisted windows
cannot support guided detection or a mathematical limit on another algorithm.

Next apply the already fixed early/middle/late proposal diagnostic to every
inactive receiver in these 64 visits, including reference-negative receivers.
Preserve all new unmatched outputs and account for time on negatives. Do not
select only the four misses or treat this mostly-negative 5 MS/s cohort as proof
of sensitivity. Use the original positive development and constructed controls
alongside this expanded cohort for any candidate selection. Final qualification
still requires disjoint recorded evidence and explicit quality gates.

## Execution and correction

The original attempt stopped before its first detector call because the new
descriptor stripped `sha256:` while the existing development loader requires
that prefix. The file bytes match their manifest hash; this was an adapter
format error, not corpus corruption. Preserve zero-row `results.json` and the
original source lock. The separately pinned `run_hash_adapter.py` restores the
manifest hash string without changing detector or membership and writes
`results.hash_adapter.json`. Three metadata/adapter/summary tests pass, including
distinguishing successful visits from lost receiver identities.

The corrected replay completed in 187.16 seconds within its 300-second bound,
CPU0 and numerical threads=1. Methods rotate within visits; candidate state
starts cold per session. Complete-call timings include conversion, tracking and
confirmation; exclude IO, initialization and serialization. Source inventories
rehash successfully and input arrays remain unchanged. Per-visit checkpoints
are saved before summary analysis. No held-out IQ, new RF collection, QNAP write,
or production change occurred. `summary.json` records receipt-derived totals.
