# Exact blocked maxima for the timing scout

The blocked selector preserved all **66 ordered factors**, including **26 residuals**, and their exact scores. The timing-search profile saved **1.44 ms** across 216 scouts, or **0.31%** of total native CPU. Complete uninstrumented native CPU was flat on the saved Gauss and Austin comparisons. The measured result closes this optimization. [Frozen builds and timing receipt](measurements/receiver-epoch-blocks.json)

## Why rebuilding the signed residual still makes sense

The cancellation kernel fits a distinct complex gain per pilot block, applies that block's rotated waveform, then rounds and clips against the original CI16 sample. Its correction occupies almost the complete window and inherits the pilot bandwidth and block gain transitions. The prior raw-versus-residual support audit found only **200–228 reusable stencils out of 50,000** quarter-rate FIR outputs on each of 92 actual residual passes. Every covariance row intersected changed samples. Even a generous audit bound credited less than **0.3% of native CPU** to reuse of unchanged input and FIR work. [Support audit](receiver-cancel-support.md) · [Signed cancellation](../../../native/algo08v2/tools/pipeline_eval/variants/pilot_cancel.c)

Filtering a complete correction can recover an ideal real-valued residual by linearity. Float32 changes that identity for the emitted samples. For example, rounding `1 + 2⁻²⁴` to binary32 gives 1, then subtracting the small term gives `1 − 2⁻²⁴`. Recomputing the original sum after removing the small term gives 1. The scout's normalized frame eigensystem depends on the changed rows. Its lag products have signal-correction cross terms, and the carrier FFT consumes the recomputed principal modes. Static pilot lag filters and FFT plans are already shared. A previous separate linear bank reused actual signed correction spectra and missed 34 of 36 residual seeds even with exact first cancellation. [Linear proposal experiment](receiver-projection.md)

## Reuse maxima within one score array

The current paired-covariance build spends about **14.8%** of native CPU in timing search on the saved profile. After the lag transforms and their energy-normalized additions, the receiver scans all 3,333 quarter-rate scores 12 times. Each selected phase clears its radius-two circular neighborhood. The new selector builds maxima for consecutive blocks of 64 scores, chooses among the cached maxima, and rescans only affected blocks after applying the original exclusion writes. The blocks, all comparisons and the lag scores are independent of site or carrier history. [Current stage profile](measurements/receiver-mode-pair.json)

Both levels use a strict comparison in increasing index order, so every tie chooses the same original index. The cutoff uses the same wrap and writes, including when all entries reach −1. A NaN at the first position in any block uses the reference global scan to preserve its ordering behavior. With the production geometry, the old scan has **39,984 comparisons** and the new selector has at most **5,416**, including initialization and two full invalidated blocks per selection. The cutoff leaves all score arithmetic, FFTs and native verification in use. [Selector](../../../tools/pipeline_eval/variants/experimental/receiver_epoch_blocks.inc)

## Matched receiver measurements

| Saved input | Lanes per repeat | Factors / residuals | Median native CPU, reference → candidate | Median paired savings |
| --- | ---: | ---: | ---: | ---: |
| Gauss weak-carrier slots | 36 | 58 / 22 | 152.93 → 153.15 ms | −0.12% |
| Austin physical field excerpt | 4 | 8 / 4 | 17.75 → 17.87 ms | −0.18% |
| Austin phase nulls | 4 | 0 / 0 | 6.92 → 6.78 ms | +0.02% |

Five paired repeats cover the 18 sealed Gauss archive entries and nine cover the saved off-site cases. Both pilot edges are represented. Austin uses one measured antenna and the two disjoint 20 ms windows at its two archived tuning edges. Each arm sees the authenticated original input digests. All saved ranks, epochs, fractional timing, signed CFOs, exact and control scores, and recorded continuation decisions match. These sparse comparisons produce no selected continuation. [Austin input provenance](austin-receiver.md)

Three separate Gauss profiled repeats took **57.98 → 56.54 ms** in timing search and **464.60 → 464.34 ms** in complete native calls. The selector removes a small part of the timing stage's total cost. The lag products, FFTs and normalization still run for both scans. No receiver or publication configuration adopts this experiment.

## Reproduce

The same balanced synthetic compiler recipe trains both variants. The reference is paired covariance SHA-256 `d44c60320320be8281ed6e71285f8cb50cc0e204df9fa1eef53d36c514e51128`. The experimental build is `ed1ab9223a74126973f2e6b7e8230f7dd756c443f01721443f8916e42f33938f`. Nine tests passed, comparing all returned indices and post-exclusion score bytes across both native widths, ties, wrap, partial blocks and nonfinite cases. [Tests](../../../tests/pipeline_eval/test_experimental_receiver_epoch_blocks.py)

~~~sh
p=/tmp/leo-algo08v2-2x-bench
tree=/home/mouse9911/gits/leo-tracker-reduxredux
study="$tree/reports/2026_11_19_receiver_screening"
t=reports/ALGO08/single-core-2x
py="$tree/.venv/bin/python"
assets=/opt/leo-algo08/current/assets
work="$p/blocked-epochs-rebuild"
manifest="$p/blocked-epochs-rebuild.json"
lock() {
  flock -x "$p/gauss.lock" ionice -c2 -n7 nice -n15 taskset -c 2 \
    env OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONPATH="src:.:$t" timeout 80s "$@"
}
lock "$py" -m pytest -q tests/pipeline_eval/test_experimental_receiver_epoch_blocks.py
lock "$py" "$t/receiver_epoch_blocks_trial.py" freeze "$work" "$assets" \
  "$p/site-free-mode-pair-pgo/candidate/use.so" > "$manifest"
lock "$py" "$t/receiver_epoch_blocks_trial.py" evaluate "$work" "$manifest" "$assets" \
  "$tree/reports/2026_11_20_single_scan_glrt/satellite-reference.zip" \
  /home/mouse9911/.cache/austin-waveform-20261119/exemplar250-257.zip \
  "$study/physical/raw-source-audit.json" "$study/arrival-and-timing/austin-waveform/native-outputs.jsonl.gz"
~~~
