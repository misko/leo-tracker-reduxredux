# Recorded holdout: compute passes, quality fails

Both predeclared 64-visit sessions completed with the unchanged frozen candidate.
The candidate is not qualified for the requested small-loss 10x replacement.
These sessions are now consumed holdout evidence. Do not retune on these results
and then describe another evaluation on these sessions as independent validation.

| Rate | Application mean CPU | Candidate mean CPU | CPU speedup | Receiver identities retained | Unmatched active receiver decisions, baseline → candidate | Associated visits retained |
|---|---:|---:|---:|---:|---:|---:|
| 2.5 MS/s | 1535.44 ms | 79.95 ms | 19.21x | 37/43 | 7 → 9 | 36/36 |
| 5 MS/s | 4009.18 ms | 210.42 ms | 19.05x | 5/6 | 41 → 41 | 5/6 |

Both rates fail every predeclared 1%, 3%, and 5% reference-loss band. At 2.5 MS/s,
rescue recovers one receiver identity and adds two reference-extra outputs; at
5 MS/s it recovers none. These extra/mismatched decisions are disagreements with
the application, not established physical false alarms. In particular, the
application and native detector score different symbol regions. The 5 MS/s
session has only six reference-positive receiver outcomes, too few for a precise
sensitivity estimate, but the observed result fails the fixed acceptance gate.

Candidate wall p95/max is 89.93/94.03 ms at 2.5 MS/s and 397.61/419.44 ms at
5 MS/s. Zero of 64 and 64 of 64 calls respectively exceed 120 ms. CPU savings do
not establish single-core real-time operation at 5 MS/s.

## Failure localization from saved receipts

`failure_audit.json` recounts the existing assessments, verifies source hashes,
recomputes CPU totals, checks primary-positive preservation, and lists every
remaining miss. It does not independently recompute scientific association.

All six 2.5 MS/s misses are inactive RX1 results for which all ten first-probe
Python proposals fail the unchanged margin gate. No native rescue confirmation
is reached. Reference-associated probe indices are:

| Visit | Reference probe indices |
|---|---|
| 1976 | 3, 7, 8 |
| 1987 | 3, 8 |
| 1999 | 3, 9, 10 |
| 2004 | 1, 5, 6 |
| 2006 | 6, 8 |
| 2007 | 5, 8, 9 |

This localizes a temporal-coverage weakness in always acquiring on probe zero.
It is not proof that another probe schedule will recover them or that probe-zero
IQ contains no signal. No threshold should be lowered solely to fit these rows.

The 5 MS/s miss at visit 579 RX1 is an active guided identity disagreement;
the reference inventory contains a probe 0/4 pair. An inactive-only rescue cannot
correct an already-active wrong identity. Of the 41 unmatched active outputs,
18 use guided tracking, 14 use blind fallback after guided failure, and nine
use cold blind discovery. Tracking accepts fresh measurements, but those
measurements do not guarantee reference identity. This implicates acceptance
and scoring compatibility as well as discovery breadth; it does not isolate
the physical cause of each disagreement.

## Consequences for the next experiment

Prioritize matching the application's final scoring profile in a cheap native
confirmation path, then test bounded discovery over separated time windows.
Existing-primary positives cannot be unconditionally preserved in a new
candidate if that rule also preserves wrong identities. Change this only in a
separate version with explicit reference/truth tests, not in the frozen candidate.

Evaluate canonical confirmation on original development/control data first,
including known pilots, early/late symbol support, pure tones, multiple signals,
and cached wrong-frequency hypotheses. Measure whether it suppresses unmatched
outputs without losing correct ones before adding broader acquisition.
Do not claim that it will solve the misses: a confirmation filter cannot recover
an absent proposal. Profile proposal generation separately and use a fixed
time-distributed schedule or measured signal evidence to allocate a bounded
search budget. A new final candidate needs fresh, disjoint recorded validation.

The measured 10x CPU ceilings here are 153.54 ms and 400.92 ms per visit on
average. Current candidate costs leave about 73.60 ms and 190.50 ms respectively
before crossing those aggregate ceilings. These are planning budgets, not a
measured allowance for any specific extra acquisition or a real-time guarantee.

## Execution

Runs completed in 104.65 and 273.52 seconds, within the separate 300-second
bounds, CPU0 and numerical-library threads=1. Complete-call timings include
conversion, controller, discovery and rescue; exclude IO, initialization,
hashing and serialization. Methods rotate within visits and hold independent
causal state. All input arrays remained unchanged, frozen source inventory
rehashes pass, and primary-positive decisions are preserved. Original JSON
results and candidate sources remain unchanged. No RF collection or production
change was performed. Receipt hashes are recorded in `failure_audit.json`.
