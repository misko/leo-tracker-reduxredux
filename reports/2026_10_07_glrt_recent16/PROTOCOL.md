# Recent sixteen completed scans: frozen detector comparison

Design recorded October 7, 2026, before examining prototype results on this
cohort. This follows the DS5 and simulated comparison in
`../2026_10_07_glrt_segment_followup/`; those results and sources remain fixed.

## Membership and scope

Freeze the sixteen newest captures with complete production GLRT at the
inventory observation. Require a sealed metrics digest, exact source binding,
and completed visit coverage; do not require completed tracking, a strong signal,
or successful satellite identification. Preserve public read-only status receipts
and newer incomplete exclusions. `selection.json` is the authoritative snapshot;
membership does not move as newer jobs finish.

Use existing archived IQ and every available production candidate, without
additional score filtering. The preflight established that production discards
integer seeds for candidates whose fractional refinement is incomplete. Its
public archive exposes those ranks and failure reasons, but not their timing
and CFO. Retain their counts explicitly: this is a comparison conditioned on
the archive's available candidate bank, not an evaluation of all acquired seeds.
No RF acquisition, production job submission, publication, or fixture change.
Reading occurs through the installed public storage ports in read-only mode.
All derived files stay in this research directory. No localization experiment or
position-accuracy claim is part of this task.

Aim to evaluate every existing GLRT probe in all sixteen scans. Before starting,
measure source I/O and correlation extraction on a few deterministically chosen
visits. Freeze coverage and execution limits from this cost preflight, without
selecting on prototype outcomes. If full replay is not a lean bounded operation,
use a declared outcome-independent visit sample across all sixteen scans and
report the sampled fraction explicitly. Never describe sampled probes as an
exhaustive scan replay. Preserve failures and their denominators.

## Matched observations and models

The primary aperture is symbols 2 through 65, with the original complete
64-symbol frame support. Every method uses the same raw complex correlations,
actual exact/control template energies, candidate inventory, and 512-bin CFO
grid. Do not derive this aperture by first requiring 256-symbol frame support.

Reuse archived integer timing epochs and acquired CFO seeds. Compare the
recomputed baseline with persisted integer GLRT scores, separately from any
fractional-epoch production refinement. Do not silently substitute tracking CFO
for the acquired seed. Record baseline numerical agreement and any backend or
support differences before interpreting method changes.

The four-visit, 10 MS/s cost preflight supported full coverage. Freeze the run
to all 35,352 archived visits across sixteen scans, all recorded receivers and
scheduled probes, with four single-thread workers and a 25-minute outer bound.
Use the public digest-verified visit stream and read raw IQ once per visit.
Persist compact compressed case results plus first/middle/last-visit correlation
samples for independent audit. Persisted integer scores agreed to 2.22e-16 in
preflight; no prototype outcome was used to change methods or membership.

Primary methods are current coherent margin, Gaussian coherent, segment8,
segment16, segment32, and the previously development-selected phase_kernel32.
Run the remaining frozen fixed scorer variants as secondary diagnostics where
cheap. No new method selection, tuning, synthetic threshold transfer, or
multiscale maximization is introduced on this cohort.

For every method, select its candidate and frequency using the first 0--20 ms
window only. Confirm at 40--60 ms of the same visit with timing and total CFO
fixed. Both exact and control use that same frequency. Forty milliseconds is
thirty nominal pilot frames. Do not reacquire or optimize the later window.

## Outcomes

For the hypothesis chosen by each method and the hypothesis chosen by the
current baseline, compute two common later-window confirmation statistics:
Gaussian64 exact-minus-control and phase_kernel32 exact-minus-control. The
paired difference under each common formula is the primary continuous outcome.
Also retain exact and control values separately. This avoids comparing score
magnitudes from different normalizations.

Report each scan's means and denominators, candidate agreement, candidate plus
CFO agreement within one FFT bin, absolute physical CFO shifts within 1/5 kHz,
and median/p90 shifts. CFO shifts are not wrapped to turn an alias into agreement.
Include the unchanged-hypothesis subset and changed choices where practical.

All six primary methods and both common statistics share a complete-pair mask.
Preserve each of the sixteen scans even when a failure leaves no valid pairs;
use null values and explicit valid-scan counts, never zero imputation. Retain
method-specific available-pair counts as secondary coverage information.

Primary aggregates weight scans equally. Secondary aggregates weight cases
equally. Report positive/negative/tied scan differences. Use 5,000 bootstrap
resamples of scans with seed 2026100703 for conditional paired intervals. Scans
come from adjacent captures at one installation; those intervals do not measure
generalization to independent sites or days.

Unmodified recordings have unknown signal-presence truth. Higher scores,
positive margins, frequency agreement, or more retained candidates are not
calibrated detection recall or RF false-alarm rates. Later windows may contain
intermittent or different signals. Report these limitations with the results.

## Verification

Include component-owned tests for inventory, source geometry, evaluator, and
summary. Pin source and input digests, record runtime and all coverage, validate
persisted-baseline compatibility, and independently audit a deterministic
sample of direct quadratic/GLRT calculations. No outcome-driven exclusions or
silent skips. Final summaries must account for the complete frozen cohort.
