# DS9 receiver-0 wideband detector diagnostic

This is an isolated research build. It does not change or qualify the ordinary
12-bin production detector. The build expands only the deployed-server
reference modes to 22 coarse-frequency slots and validates the complete grid
size before writing it. The initial experiment used zero receiver centers and
residual CFO from -800 kHz through +800 kHz, which produces 21 regular 80 kHz
bins.

**Authority correction:** zero receiver centers are retained here only as the
rejected diagnostic geometry.  The schedule construction wrote zero directly;
it did not preserve a `compile_pilot_search_geometry` call deriving the center
from the recording's tuned RF/IF, channel, and edge.  The source-bound lower-edge
geometry is -312,500 Hz on all eight visits.  The corrected bounded replay in
[`retention-audit-v1/`](retention-audit-v1/) recovers exact rank/gate structure,
23/23 passing candidates, and all 43 persisted rows within the frozen numeric
tolerances without changing thresholds or goldens.  The findings below describe
the rejected zero-center experiment and are not the authorized parity result.

The fixed visit selection is frozen in
[`missing-rx0-selection.json`](../missing-rx0-selection.json). It is the first
two lower-edge, receiver-0 visits per channel whose reference source group was
used by a reference track and absent from the native complete-scan projection:
126, 191, 193, 283, 301, 307, 346, and 418. Selection preceded this replay.

## Result

All eight missing source groups produced at least one tolerant match after the
authoritative wideband reference replay. Across the eight visits, the reference
has 23 passing candidates and the research build has 23. One-to-one matching at
the predeclared bounds of two continuous-epoch samples and 10 kHz finds 21
matches, two unmatched reference candidates, and two additional research
candidates. Six of the eight particular reference candidates used by tracks
receive a one-to-one tolerance match. These are detection matches, not exact
numeric or candidate-ID parity.

The four discrepant visits locate the remaining differences:

- Visit 191 loses reference rank 1, an exact scientific duplicate of recovered
  reference rank 0: epoch, fractional offset, CFO, and all three scores are the
  same. The distinct reference rank 3 signal is recovered as research rank 2.
- Visit 193's reference ranks 0 and 1 are adjacent integer/fractional
  representations of nearly the same continuous support. The research rank 0
  matches reference rank 1 exactly within binary arithmetic; it is also within
  0.0002 continuous samples and 5.09 Hz of reference rank 0. One-to-one
  accounting therefore records reference rank 0 as missing, but this is a
  multiplicity/canonical-retention difference rather than an entirely missing
  physical signal.
- Visit 346 adds research rank 3, an exact scientific duplicate of recovered
  research rank 2. The reference retains only one of those two coarse-bin
  paths.
- Visit 126 adds a distinct research rank 3. Reference rank 3 matches research
  rank 4 by epoch/CFO tolerance, but its exact score and margin differ
  materially (reference 0.6490/0.6091 versus research 0.3994/0.3556). This is
  recovery under the detector comparator, not numerical parity.

The retained reference fixture begins after candidate refinement and does not
contain its coarse acquisition inventory. The research outputs show eight
retained coarse candidates per receiver and preserve coarse bin, coarse/fine
CFO, acquired CFO, fractional status, and gate outcome in
[`comparison.json`](comparison.json). Duplicate candidates arriving from
adjacent coarse bins and the insertion/canonical-retention rules are therefore
the narrow remaining hypothesis. Proving the exact insertion difference would
require diagnostic counters before and after reference canonical retention; it
is not inferred here.

The certified interval and scalar reference modes have byte-identical candidate
payloads on all receiver rows of the four discrepant visits (126, 191, 193, and
346). Only timing and interval-screen telemetry differ. The interval extension
is therefore ruled out for these discrepancies.

## Qualification scope

The host and ASAN/UBSAN builds pass the endpoint and fail-before-write grid
tests. A real 7.5 MS/s, 120 ms DS9 visit (visit 301, both receiver rows) also ran
through the sanitizer build in 6.82 seconds with exit 0 and no sanitizer
diagnostic; this is separate from the small grid unit. The ordinary legacy
geometry panel remains unchanged after timing/profile fields are removed. A
span above 1.6 MHz is rejected by the isolated setter. The eight interval runs
finish in 1.00--1.90 seconds each; the four scalar controls finish in
1.50--1.71 seconds each.

This proves bounded missing-source recovery on eight preselected visits. It is
not a full 2,215-visit replay, a production promotion, detector/server numeric
parity, or location qualification.

## Production safety finding

The current production research setter accepts spans through 900 kHz, while
the underlying coarse arrays hold 12 values. The legacy `grid()` writes the
13th value for some accepted spans before the caller checks `count > 12`.
The smallest independent safety correction is to reject any production
research-setter span above 880 kHz, before storing the geometry. At 80 kHz
spacing, every span at or below 880 kHz needs at most 12 slots under the frozen
endpoint rule. A component regression should cover aligned 880 kHz, a value
clearly above it, 900 kHz, non-finite bounds, and verify that rejected geometry
does not replace the prior setting. This safety fix does not enable or claim
wideband scientific support; the checked `bounded_grid()` and 22-slot storage
remain confined to this research source copy.

## Reproduction

Run the retained comparator from the repository root:

```sh
python3 reports/2026_09_30_native_adaptive_deployment/ds9/receiver-authority-ablation-v1/wideband-research/compare_fixed8.py
```

The copied host and sanitizer binaries, source closure, raw JSONL outputs,
timing logs, qualification outputs, and hashes are all below this directory.
The raw CI16 inputs are not duplicated here; their authoritative hashes and
read-only corpus paths are bound by the selection manifest and the parent
`missing-rx0-replay/raw-authority.json` receipt.
