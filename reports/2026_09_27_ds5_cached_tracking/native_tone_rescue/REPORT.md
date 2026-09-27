# Native tone-removal rescue: development result

The bounded candidate exceeds 10x aggregate CPU improvement on the fixed
64-visit recorded development replay while retaining 78/79 application-positive
receiver identities (98.73%). The unchanged native tracked baseline retains
67/79. All 11 inactive receiver misses are recovered; the remaining mismatch is
the already-active frequency alias at 2.5 MS/s visit 1101 RX1. Existing native
positives are preserved, and rescue adds no new reference-extra or mismatched
receiver decisions. Recorded reference agreement is not independent physical
truth. This is development evidence, not held-out qualification or deployment.

| Rate | Application mean CPU | Rescue mean CPU | Aggregate CPU speedup | Retained receiver identities | Rescue wall p95 / max | Calls above 120 ms |
|---|---:|---:|---:|---:|---:|---:|
| 2.5 MS/s | 1259.19 ms | 53.46 ms | 23.55x | 36/37 (baseline 33/37) | 121.14 / 123.95 ms | 2/32 |
| 5 MS/s | 3351.18 ms | 158.69 ms | 21.12x | 42/42 (baseline 34/42) | 349.59 / 369.77 ms | 28/32 |

Both methods retain associated detections in all 56 application-positive visits.
The native baseline's five additional-or-mismatched active receiver outcomes
remain unchanged (three at 2.5 MS/s and two at 5 MS/s). The 2.5 MS/s miss rate
is 2.70%; across both rates it is 1.27%. These pass the exploratory 3%/5%
reference-miss bands overall, but not the 1% band. None is a field error-rate
estimate. The 5 MS/s latency exceeds a 120 ms recording's duration on most
visits, so a real-time single-core replacement is not established.

## What was measured

The primary NativeTradeoffDetector and guarded engine are unchanged. Rescue
selects one inactive receiver, acquires ten hypotheses on its first 20 ms probe,
and confirms eligible hypotheses on probes zero and two. The separate rescue
engine loads the full probe, applies the exact blind stationary-tone fit, and
runs one final GLRT without acquisition or re-ingestion. Acquired and physical
frequency inputs remain separate. The original score, support, status and
identity gates remain fixed. Rescue positives do not enter the track cache.

Fifty of 64 visits run a rescue acquisition (22/32 and 28/32 by rate). There
are 427 Python candidate scores, 12 native seed calls and 12 native confirmation
calls, yielding 11 rescues. None of the 24 recorded native rescue points applies
tone subtraction; the tone fit still runs and is included in cost. Its role is
to reject interference when present, as demonstrated by controls. All primary
decisions match the separately stateful baseline exactly. The existing primary
cache contributes 31 guided accepts, 31 blind fallbacks and 66 cold receiver
calls. This experiment does not isolate the additional speedup from caching.

Complete-call CPU and wall timing includes conversion, primary processing,
Python rescue acquisition/scoring, native confirmation, controller work and
receipt-object capture. It excludes file reading, hashing, serialization and
one-time initialization. Measurements use CPU0 and one numerical-library thread;
methods rotate within each visit, and only one DSP campaign runs at a time.
The recorded campaign completed in 156.39 seconds. Ratios compare aggregate
paired CPU costs; they do not multiply independent speedups.

The earlier fixed-probe-zero/two 76/79 "proposal ceiling" was too strong a
description of a post-hoc inventory opportunity count. It counted independently
acquired application probe pairs; guided scoring can confirm a seed on probe
two even when blind acquisition there selected another alias. This actual
algorithm recovered visits 1083 and 1104 RX1 as well. Treat inventory counts
as opportunities, not mathematical bounds on a different search algorithm.

## Scientific gates and limits

The 42 original controls pass all 84 required receiver policies for both primary
and new rescue, with 52 positives retained. The 12-parent, 24-execution original/
swapped negative audit has zero active decisions among 48 receiver checks.
The frozen raw-rescue comparator reproduces its two original and three audit
failures, representing three distinct physical tone receiver waveforms.

The 26 diagnostic cases yield 38 truth-associated positives, ten true negatives
and four inactive weak pilots in both primary and new rescue, with no required
truth failures. Rescue performs eight acquisitions but no native point calls:
all 80 Python seed scores fail the margin gate. Application-relative aggregate
CPU gains are 36.93x/45.77x. Two reference-identity disagreements reflect existing
native/application symbol-region differences, not newly introduced rescue
errors. No improvement in weak-signal sensitivity is demonstrated here.

The original diagnostic attempt lost its receipt to a summary-only None-value
bug after all calls. A separately pinned adapter fixes summary construction;
the repeat and real replay use that adapter, with unchanged frozen scientific
code. See QUALIFICATION.md and diagnostic_reporting_failure.json. Do not count
the failed attempt as an independent repetition or omit this reporting deviation.

Reserved validation remains unopened. Small constructed-negative counts do not
establish rare false-alarm performance; multisignal coverage, new channel
conditions, rescued-track caching, and the active alias remain open. The next
steps are independent receipt review, a fixed held-out evaluation, and a bounded
latency optimization targeting rescue acquisition rather than the already-cheap
native points. Do not promote solely from this development result.

## Evidence

- Original source lock (118 files): `a05ab9405f8433b21e576e3c3a13c47fadb87e403fcd31db79df343527007f88`
- Reporting adapter lock (123 files): `7a1ee8c362370447a5e39ad90ae797dcdd08d06897061c6204ed0a340046401a`
- Controls: `fbc63c6ce95ca7c2ebb86ce9519570e6bb5191b99194a8c194b6dbecc4eeb929`
- Diagnostic repeat: `2adc922bb46b0e17dc7a3465684c0489722da3bce9da679810f6c8c700a9f2d0`
- Recorded replay: `696107cffed8f7de8d2f11d44d11e99f4c2663558a12489aa5e01e9c59139f81`

All receipts are complete and source-stable; root independently rehashed both
source inventories after the recorded replay. Input arrays remained immutable.
The full research suite passes 543 tests and 11 subtests across two normal-mode
collection shards, avoiding the older frozen duplicate test-module basename.

Subsequent receipt-only audit independently recomputed the association and
timing totals and verified all 11 recoveries; see `receipt_audit.json` and
`CACHE_FEASIBILITY.md`. Its two additional audit-helper tests pass. A post-hoc
cache inventory found six recent same-channel rescue opportunities, but simple
zero-drift reuse misses the current selected timing on all six, and three also
change physical-frequency identity substantially. No cache speedup is inferred
from that inventory, and no new IQ was opened for the audit.
