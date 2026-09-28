# Larger DS7 evaluation: exact GLRT hits and recovery

The current reduced ARM search recovered **499 of 7,007 baseline-positive
20-ms receiver/windows (7.12%)**, and **499 of 19,581 individual positive
candidate hits (2.55%)**. It does not meet the requested 80%/90% preservation
target. The earlier native-baseline parity and runtime figures must not be
interpreted as preservation of the full GLRT search.

## Coverage and successful execution

This run uses **704 new unique 120-ms dual-receiver dwells**, eight evenly
spaced across each of all **88 DS7 recordings**. It is 25.14 times the previous
28-dwell sample and has no overlap with that sample. Both channel edges and
all eight scan targets are represented. It remains a subset: 84.48 seconds of
recorded dwell time, or 0.361% of DS7's 194,934 published dwells.

All 704 original-baseline calls and all 704 ARM calls completed successfully.
The original full search ran in eight independent server processes. The
unchanged optimized native `goal40mag` method ran on CPU0 of physical PLUTO+
192.168.1.15 using the same saved inputs. No RF collection occurred. This is a
quality/recovery experiment with no simultaneous capture and no admission
drops, not a new cross-platform speed comparison.

## Unique 20-ms windows

One window means one receiver and one 20-ms interval. The original method
evaluates eleven overlapping intervals per receiver, starting at 0, 10, ...,
100 ms. ARM ranks six non-overlapping intervals per receiver, then executes
GLRT for one selected interval. Cheap ranking is not counted as an executed
GLRT window. Warmups and repeated processing do not increase unique counts.

| Rate | Dwells | Original windows run | Original positive windows | ARM windows run | ARM positive windows | Original positive windows recovered | Recovery |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2.5 MS/s | 152 | 3,344 | 1,682 | 304 | 191 | 126 | 7.49% |
| 5 MS/s | 216 | 4,752 | 1,874 | 432 | 188 | 144 | 7.68% |
| 7.5 MS/s | 184 | 4,048 | 1,933 | 368 | 162 | 126 | 6.52% |
| 10 MS/s | 152 | 3,344 | 1,518 | 304 | 120 | 103 | 6.79% |
| **Total** | **704** | **15,488** | **7,007** | **1,408** | **661** | **499** | **7.12%** |

Recovered means the same visit, receiver, and interval contains at least one
positive hypothesis matching a baseline positive within 2 microseconds in
timing and 8 kHz in tracking CFO. There are 522 baseline-positive windows with
any ARM positive in the same interval; 23 of those do not contain an eligible
identity match and are not credited in the recovered column.

The ARM binary also executes one warmup per input/receiver before recording
the scored result: 2,816 physical native confirmation calls including warmup,
versus 1,408 unique scored receiver/windows. No warmup result is credited as
an additional hit.

## Individual GLRT candidate hits

The original evaluates eight candidate entries per window: 123,904 entries
overall. A hit here is a returned margin-positive candidate entry, not a
distinct physical transmitter. Separate original candidate entries remain in
the denominator even when their timing/frequency values coincide. One-to-one
matching prevents one ARM hypothesis from recovering several such entries.

| Rate | Original positive candidate hits | ARM positive candidate hits | Original hits recovered | Original hits missed | Recovery |
|---|---:|---:|---:|---:|---:|
| 2.5 MS/s | 4,573 | 191 | 126 | 4,447 | 2.76% |
| 5 MS/s | 5,466 | 188 | 144 | 5,322 | 2.63% |
| 7.5 MS/s | 5,186 | 162 | 126 | 5,060 | 2.43% |
| 10 MS/s | 4,356 | 120 | 103 | 4,253 | 2.36% |
| **Total** | **19,581** | **661** | **499** | **19,082** | **2.55%** |

The identical recovered counts in the two tables are not interchangeable
metrics: ARM emitted one candidate per selected window in this run, so every
matched candidate recovers one window. Their reference denominators differ.
The 162 unmatched ARM positives are additional relative to this matching
criterion; they are not automatically false alarms or additional true signals.

## Where recovery is lost

Of the original 7,007 positive windows:

- **6,372 were never selected for ARM GLRT.**
- **635 were selected**; 113 produced no ARM positive.
- Of the 522 selected windows positive in both methods, 23 failed the identity
  matching tolerances and **499 recovered a baseline detection**.

Thus the dominant loss is omitted windows. Even inside the selected windows,
ARM recovers 499 of 1,790 original positive candidate entries. Expanding the
window count alone does not establish preservation of the original candidate
inventory. Speed comparisons intended to preserve 80%/90% of the original
hits need the full baseline denominator and this matching rule retained.

Baseline positivity is `passed_margin_gate`, equivalent to margin >= 0.025.
Native positivity additionally requires completed fractional refinement and
uses margin > 0.025. No baseline or ARM candidate lies exactly on the
threshold, so equality at the gate does not explain these results.

## Receipts and verification

`plan.json` and `inputs.json` bind the complete selected cohort and payloads.
`baseline-01/run.json` reports zero failures and unchanged scientific sources;
`baseline-summary.json` independently inventories its windows and candidates.
`arm03/run.json` seals the complete combined ARM results, including an explicit
64-dwell completed prefix from `arm02`; see `TRANSPORT.md`. Each target-side
raw input and template was SHA-256 checked before execution. Post-run binary
hashes agree with the qualified binary for both target directories.

`score.json` contains the complete and per-rate comparisons. `AUDIT.md`
describes the independent scorer and validation rules; `INDEPENDENT_AUDIT.json`
records a separate recomputation. The comparison rejects missing cases,
duplicated cases, shortened original window inventories, and mismatched source
contexts. Tests include one-to-one matching, window and receiver boundaries,
fractional timing, threshold equality, and exact cohort membership.

Selection and workload details are in `PROTOCOL.md`; exact baseline commands
are in `EXECUTION.md`. The findings are reference-relative detection recovery,
not independent labels of physical signal truth or a full-DS7 evaluation.
