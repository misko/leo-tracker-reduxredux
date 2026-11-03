# All-ARM adaptive location: design and bounded DS9 prototype

The proposed implementation is a persistent native application with a fast IQ
path and a separately budgeted rolling location path. It accepts the user's
assumptions that ARM system UTC is correct and a recent TLE is locally available.
No database, HTTP server, Python runtime, catalogue-download service, rendering,
or immutable filesystem product graph is needed on the device.

The experiment demonstrates native ARM TLE propagation and compact all-track
scoring on existing DS9 results. **It does not yet demonstrate a real-time
IQ-to-location pipeline.** The measured location scorer is still too slow for
a fresh wide-area search at a short update interval. This is an important
measured design constraint, not hidden behind GLRT's per-dwell timing.

## Proposed execution structure

One application owns four numerical modules, connected by small bounded
in-memory records rather than server services:

1. **IQ to fractional GLRT observations.** A persistent context receives CI16
   buffers and actual tuning metadata. Use the standard first-20-ms-per-RX
   schedule at explicit 120 ms stride. Complete fractional epoch/CFO scoring
   and the peer-RX acquisition fallback before declaring equivalence. Existing
   private C code already contains fractional interpolation/scoring machinery;
   the maintained fast result path currently omits it. Reuse and qualify those
   kernels instead of porting the Python product stack. Preserve all passing
   candidates, not just the strongest one. Actual frequency calibration and
   the server/native search-range difference also need qualification.
2. **Observations to track snapshots.** Keep a bounded ring of observations
   with receiver/channel/edge, actual RF, sample counters, fractional support,
   CFO and score. Port the alias-aware track algorithm with the all-track
   policy of six observations and three seconds of support. Normalize to
   11.2 GHz. Start with the existing bounded batch algorithm on snapshots;
   incremental track maintenance is a subsequent change requiring parity tests.
3. **TLE to shared orbit cache.** Parse local TLEs once. Store position and
   velocity knots once per satellite, shared by every track, time shift and
   map point. Cubic Hermite interpolation avoids a satellite × time-shift ×
   observation state tensor. Refresh the cache incrementally. Each computation
   binds one TLE generation; changing the snapshot creates a new cache epoch.
4. **Tracks plus orbits to location hypotheses.** Keep a resumable search
   frontier and several competing regions/identities. Separate initial broad
   acquisition, warm local updates and periodic broad reacquisition. Evaluate
   every eligible track in the final score; do not define all-track inference
   by retaining only convenient strong tracks. Publish best-so-far coordinates,
   data age, score and remaining search budget. A budget-limited diagnostic is
   not a confirmed position fix.

The GLRT worker alone owns its process-global FFT caches. A second worker can
own orbit/position state on the other Cortex-A9 core, with bounded snapshots
between them. Alternatively use resumable low-priority work chunks. Actual
CPU/IRQ assignment and shared-memory contention need capture-concurrent
qualification; the current benchmarks run without capture. Background work
must not stall IQ ingestion. Avoid process-per-dwell execution and unbounded
job queues. Detect overflow explicitly rather than silently losing evidence.

## Requirements to retain, simplify, and remove

Correct system time replaces the server's timing-authority acquisition
workflow, but not the sample-to-time mapping: latch a UTC/counter origin and
derive support timestamps from counters and sample rate. USB arrival time or
analysis-completion time is not the RF observation time. Retunes, invalid spans
and stream restarts still delimit continuity. Do not fabricate fractional
offsets or substitute an excerpt midpoint for the GLRT support center.

Recent TLE availability removes fetching and archive-selection infrastructure.
For this historical test, the published snapshot is deliberately held fixed;
using today's newest elements would confound numerical implementation with
different orbital inputs. Local parsing and propagation error handling remain.
Correct UTC does not by itself remove the current model's per-track fitted
frequency offset or its +/-5 s orbit-shift search. Removing those terms is a
scientific model change, distinct from eliminating server dependencies.

Remove phase-report prerequisites, QAM diagnostics, waterfalls, PNGs, web/API,
PostgreSQL leases, report publication, catalogue network access, historical
position-method reports and Python/Pydantic objects from the device runtime.
Dual-RX relative phase is not consumed by this location method. Reference
coordinates are optional evaluation metadata used after inference.

Keep small C/C++ structs and explicit bounds/status codes. Record a run/config/
TLE identity once rather than rehashing large products in the numerical loop.
Preserve stable observation identities and frozen partitions for equivalence
testing. Add a new native result version instead of silently changing existing
published contracts. A replay adapter can reconstruct the server comparison
objects outside the real-time path.

## Tested compact scorer

The prototype reads all 64 tracks and 3,372 observations from the published
DS9 result for `scan-fw-3cfdaa6d75762cad`. Membership was selected by that
pre-existing report, not by prototype residual quality. It retains the full
11,129-member valid Starlink catalogue, eleven integer time shifts, original
training masks, frequency-offset fitting, evaluation-selected identity,
represented-second weights and 800 Hz capped residual objective.

It rejects an impossible satellite/track block only when all four Bezier
control points of every relevant Hermite segment lie below the local horizon.
The convex-hull property makes this conservative for the **interpolated**
orbit. It is not a proven error envelope for the exact SGP4 orbit. Remaining
blocks evaluate each candidate/tau/observation directly and reduce to one
winner per track; no large prediction tensor is allocated.

Relative to the server, the prototype replaces exact receive-epoch propagation
with interpolation and omits the redundant coarse one-second visibility
prefilter, applying direct visibility to the interpolated states instead.
Those are explicit differences to audit, not claims of bitwise equivalence.
The legacy whole-window validity selection is frozen from the host; its
1,316-node validity sweep is not included in the ARM orbit-generation timing.

### Physical Cortex-A9 results

These score **both existing selected locations**, each using every track and
the complete valid catalogue. They do not time a full regional ARM search.

| Knot spacing | ARM wall seconds, two points | Peak process RSS | Satellite choices matching server | Time-shift choices matching server | Largest point-score error |
|---|---:|---:|---:|---:|---:|
| 10 s | 27.898 | 23,196 KiB | 128/128 | 128/128 | 0.003669 Hz |
| 30 s | 27.448 | 8,664 KiB | 128/128 | 128/128 | 0.005702 Hz |
| 60 s | 28.518 | 4,980 KiB | 128/128 | 128/128 | 0.048211 Hz |

All three physical ARM point-result documents exactly match their corresponding
host C documents. Maximum individual-track RMS error is 0.113 / 0.149 / 0.500 Hz
for 10 / 30 / 60 s knots. This supports compact ephemerides on this case;
larger steps do not materially speed scoring because the repeated geometry
and residual search dominates. No global interpolation-error guarantee or
new position-accuracy claim follows from one DS9 scan.

The separate native C++ SGP4 run parses the same 11,129 TLE records and produces
43 ten-second knots per satellite **on ARM**. Setup uses about 0.75 CPU s;
propagation uses **4.016 CPU s / 4.017 wall s**, with zero propagation errors
and peak RSS **34,868 KiB**. Maximum coordinate discrepancy from the server
table is **7.19e-8 m**; velocity-component discrepancy is **1.04e-10 m/s**.
Those are implementation comparisons, not orbit-accuracy bounds. The pinned
SGP4 source is version 2.27 with the repository lockfile's SHA-256. Runtime
does not use Python. Output-file writes and transfer are outside propagation
timing. Scoring the ARM-generated table again retains all 128 satellite and
time-shift choices and the same sub-0.004-Hz point-score differences.

### Full regional replay and retained-candidate timing

The full regional replay completed **on the host**, using the ARM-generated
10-second orbit table and the unchanged server best-first search scheduler.
Both searches exhausted their original 400-point budgets. Each visited exactly
the same points in the same order and selected exactly the same coordinates
as its published server reference. Maximum score differences across all points
were **0.143840 Hz for Sacramento** and **0.092545 Hz for Reno**. Combined host
wall time was 321.42 s; this is not an ARM search timing. `search-audit.json`
records the independent comparison against the published results.

A separate physical ARM timing experiment restricts the catalogue to the
union of the 49 winning satellite identities in the two saved results. The
same two locations, all 64 tracks and all time shifts take **2.331 s**, with
peak RSS **1,380 KiB**. The 128 identity/time-shift selections still match.
This is deliberately **oracle-seeded timing evidence**: supplying the saved
winners does not test discovery, independent recovery, or a practical online
candidate-selection algorithm. It suggests value in retaining hypotheses, but
even this restricted implementation does not fit a 120 ms location deadline.
`oracle-seeded-warm-timing.json` contains the inputs and explicit scope warning.

## Consequences for the search algorithm

The orbit representation solves the memory problem; it does not solve global
search throughput. The measured two-point rate is about 14 s per point on
one core. Multiplying that rate by 800 points gives an order-of-hours cold
search estimate, **not an executed ARM campaign or a measured whole-search
runtime**. No such campaign was started. Dense rescanning must not be the
fast update path.

The next measured optimization should compare three increasingly aggressive
options, keeping the present full scorer as the audit/finalist evaluator:

- Exact work reduction: compute training residuals for every tau, then compute
  evaluation residuals only for its selected tau; share state interpolation
  and geometry across queries; preserve independent visibility accounting.
- A cheap Doppler-curve representation or fixed observation sketch to propose
  satellite/tau and geographic finalists, followed by full all-track rescoring.
  Retaining a fixed top-K set is an approximation and can lose the winner;
  test it on untouched whole scans and include fallback/reacquisition.
- Retain multiple location hypotheses between updates, updating their residual
  accumulators from new/expired observations. Run a separately budgeted broad
  search to recover from ambiguity or a wrong initial region. This changes
  the batch search schedule and must be validated as a streaming algorithm.

Do not prune an entire geographic cell merely because its center scores
poorly: the center score is not a lower bound on the cell. Likewise a poor
training score is not a safe satellite rejection bound when identity is
selected using evaluation RMS. Certified pruning requires valid bounds;
otherwise label the search approximation and measure its lost hypotheses.

The final target is two explicit deadlines: per-dwell candidate production,
and bounded-age location updates after enough track support. Current DS9 GLRT
measurements are about 50 ms mean and 100--102 ms worst case **before** adding
the missing production fractional path. Neither frequent location updates nor
complete fractional GLRT has a qualified concurrent-capture budget yet.

## Evidence and scope

`export.py` reads the published result and archived TLE through read-only
component ports. `inputs.json` binds the source, tracks, snapshot and server
reference scores. `score.c` is the small C evaluator; `check.py` builds host
and ARM binaries and tests knot spacings; `arm.py` performs bounded CPU0 runs.
`orbit.cpp` and `run_orbit.py` generate and compare actual ARM orbit states.
`search.py` replays the unchanged server best-first frontier on the host using
the compact C evaluator and ARM-generated orbit table. `host-search.json`
records its completed full-budget outcomes. Host search timing is not ARM
timing. No ground-truth position enters the inference inputs.

`test_score.py` independently checks the C results against NumPy plus the
server scalar scoring function on supplied predictions, checks deterministic
identity/tau ties and the unmatched penalty, and rejects truncated input.
**Three tests pass**, each exercising both the ordinary host binary and an
AddressSanitizer/UndefinedBehaviorSanitizer build. These do not certify all
malformed inputs of a production binary protocol; the fixture format is
research-private and not a proposed public persisted contract.

Remaining work includes the calibrated fractional GLRT path, an ARM track
builder, the compact native search scheduler, broader held-out datasets,
online catalogue-validity handling, and capture-concurrent latency tests.
Existing tracks were supplied to this experiment: it is not an end-to-end
native IQ-to-location demonstration. Nothing was deployed and no RF collected.
