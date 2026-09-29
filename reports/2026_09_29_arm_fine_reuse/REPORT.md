# Exact fine-FFT reuse on one PLUTO+ core

The lazy spectrum cache reduces restricted-search CPU time from **6,388.459
to 5,460.863 ms per 120 ms dual-RX dwell** at 2.5 MS/s: 14.52% less CPU, or
1.170x faster. All 123,904 candidate objects on the 704-dwell DS7 cohort are
identical to the previous restricted search. Against the **standard analysis
pipeline**, recovery remains **19,400/19,581 (99.08%)**, including
**4,551/4,573 at 2.5 MS/s**. No new detection-quality gain is claimed.

This remains a research method far from real time. The inherited restricted
search also returns 18,328 unmatched positive entries; preserving its output
does not resolve their interpretation or restore its 181 missing baseline
hits. The near-baseline-quality boundary-fallback reference still recovers
19,576/19,581.

## What changes

Candidates with the same integer refined timing epoch use the same fine-FFT
input, even when they request different frequency ranges. Cache each frame's
complex spectrum and normalization denominator within one receiver-window.
Then read only each candidate's requested bins, preserving the original
per-bin magnitude, addition and division order. All windows, retained
candidates, frequency bins, refinement and GLRT stages remain present.

The first prototype instead calculated normalized magnitudes for every FFT
bin. It preserved outputs but was slower on ARM; it is rejected. The selected
lazy version saves transforms without calculating magnitudes of unused bins.

| Variant | Search CPU ms/dwell | Fine-FFT CPU ms/dwell | Standard hits recovered on ARM |
|---|---:|---:|---:|
| Previous restricted search | 6,388.459 | 3,817.394 | 119/119 |
| Full-bin score cache, rejected | 6,536.563 | 3,968.036 | 119/119, candidate objects unchanged |
| Lazy spectrum cache, selected | **5,460.863** | **2,841.015** | **119/119**, candidate objects unchanged |

The selected timing averages two runs of the same four unique DS7 dwells on
PLUTO+ 192.168.1.15 CPU0: 5,453.035 and 5,468.692 ms/dwell. Inputs are saved
CI16 in RAM; no RF capture or concurrent producer runs. The inherited baseline
is a separate measurement of the same four dwells, not an interleaved A/B.
Input/template/binary hashes are checked before each new hardware run.

The ARM cohort has 88 windows and 704 candidate entries, but only 425 unique
window/epoch pairs. The cache avoids 279 repeated fine-evaluation groups.
These counters count epoch/frame groups, not individual FFT calls. At most
16 frames contribute to one group. Final GLRT still executes 834 kernel calls
including 130 boundary fallbacks, with 258 positive outputs and 139 unmatched
positives relative to the 119 standard hits.

The cache is scoped to one search call, with at most eight epochs. Worst-case
spectrum storage is 9.77/19.53/29.30/39.06 MiB at 2.5/5/7.5/10 MS/s respectively.
This trades RAM for CPU and requires capture-memory contention testing before
deployment. Allocation failure returns an error after freeing completed
allocations; the caller's cleanup is safe after the cache has been zeroed.

## Qualification

- Host component tests require bit-identical scores for shared epochs with
  distinct frequency ranges, fresh-window invalidation and partial/full
  inputs at all four rates. The same component test passes on ARM.
- Host ASAN/UBSAN tests pass with leak detection and empty stderr.
- The initial 32-dwell all-rate host run preserves all 5,632 candidate objects.
- The full 704-dwell host run preserves all 123,904 candidate objects, all
  15,488 window outputs except timers/cache counters, and the ordering.
- The frozen standard-pipeline matcher independently re-scores the completed
  results: `host704-standard-audit.json` and `arm4-standard-audit.json`.

`builds/host-v3` and `arm-v2` contain rejected full-bin snapshots. The selected
snapshots are `host-v4` and `arm-v3`; each has `fine-reuse-build.json` with
source/binary hashes and compiler receipts. `host-asan-v1` contains sanitizer
receipts. `arm-unit.json` records the physical-ARM component check.

For publication, identical selected host/ARM sources are included once in
`selected-source-snapshot.tar.gz`, rather than duplicating every generated
build tree. Its members match every source hash in both selected build
receipts. Extract into a fresh directory and adapt the receipt's absolute
include/source/output paths to that directory when rebuilding. Compiled
binaries and large raw candidate inventories remain in the development
workspace; publication retains their hashes, summaries and scientific audits.

`host704-lazy-v1`, `arm4-lazy-v1` and `arm4-lazy-v2` retain actual outputs and
qualification summaries. `arm-aggregate.json` records timing averages. The
top-level source comment was clarified after compilation; immutable build
snapshots remain authoritative for the measured binaries.

Adding the separately measured existing FP64 proposal stage gives **6,449.296
ms/dwell**, versus the previous 7,376.891 ms. This is a stage-cost sum, not a
fused-pipeline or simultaneous-capture measurement. The new direct-CI16 final
scorer is not integrated and its isolated speedup is not multiplied into this
result.

## Reproduction

Run `evaluate.py` against an explicitly named binary and frozen reference:

```sh
.venv/bin/python reports/2026_09_29_arm_fine_reuse/evaluate.py \
  --binary reports/2026_09_29_arm_fine_reuse/builds/host-v4/cohort_fine_reuse \
  --reference regional704-v1 --output NEW_OUTPUT
```

For hardware use the ARM binary, `--arm`, and `--reference regional-arm-v1`.
Use fresh output directories. `--allow-proposal-changes` belongs to subsequent
proposal experiments and must be followed by a standard-pipeline hit audit;
it is not an equivalence gate for this cache experiment.
