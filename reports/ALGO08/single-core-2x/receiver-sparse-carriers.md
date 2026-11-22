# FFT support limits and an exact sparse carrier sweep

The sparse sweep saved **0.63%** median paired full receiver CPU on the DS26 weak-carrier archive, or **20.3 µs per lane**, against the frozen spectral receiver. The measured Austin configurations saved **0.80%** at zero center and **0.01%** at shifted centers. All **74 factor records and 52 continuation decisions** matched exactly. The three historic dense CFO regression lanes reproduced all five archived factor records. The sweep leaves the FFTs in place and the measured whole-call gain is small. [Paired receiver and stage clocks](measurements/receiver-sparse-carriers.json.gz) · [Dense regression](measurements/receiver-sparse-carriers-regression.json)

## Timing padding and the signed carrier grid

The normal scout at stride four evaluates 3,333 timing offsets against an unlagged template length of 1,408 samples. For lag $d$, the kernel spans $1,408-d$ samples and the signal spans $4,740-d$. The circular FFT correlation returns the retained linear lag products because an epoch $e$ reads indices $e$ through $e+1,408-d-1$. The maximum is $4,739-d$. A circular transform with length $N \ge 4,740-d$ can cover all retained outputs without aliasing. Folding below that whole-support length can place a sample from the latest retained epoch into an earlier one. The older crop from 8,192 to 4,800 already exploits the distinction between the retained epoch set and the complete linear convolution. [Existing crop](receiver.md) · [Timing and carrier FFTW plans](receiver-fftw.md)

| Quantity | Values at stride four |
|---|---|
| Actual timing lags | 2, 4, 6, 11, 18, 28, 44, 74 |
| Sufficient whole-support lengths | 4738, 4736, 4734, 4729, 4722, 4712, 4696, 4666 |
| Current timing FFT length | 4800 |
| Padding above whole support | 62–134 samples, 83.4 mean |
| Carrier FFT length and grid spacing | 4096 and 610.3515625 Hz |

In the optimistic $N\log_2 N$ model, using all eight minimum timing lengths saves **1.94% of FFT arithmetic** before alternate factorization or planning. Even crediting that fraction to the entire latest timing-search stage gives about **6.6 µs per two-scout lane**. A 4,096-point overlap-save plan can keep only $4,096-(1,408-d)+1$ consecutive epochs per block and therefore needs two blocks for all 3,333. A different length also changes Float32 butterfly order, so agreement in the mathematical correlation leaves equal rounded scores unproven. [Latest timing clocks](measurements/receiver-spectral-vectors.json.gz)

The carrier transform reads 704 potentially nonzero input samples, with the rest padded to make the fixed 4,096-bin grid. Using a plain 2,048-point FFT preserves every other frequency in exact arithmetic. Recovering the interleaved points needs another 2,048-point transform of suitably phase-rotated samples. It would change the stock arithmetic and still require both independent mode spectra. The previous tracking test lost 30 of 152 verified factors when it reduced the timing proposal support. The raw-shortlist residual experiment found seven of 36 measured residual phases outside its retained raw timing indices. This experiment covers both full scouts and their original timing proposals. [Tracking comparison](receiver-tracking.md) · [Residual coverage](receiver-shortlist.md)

## Sparse eligible bins and exact ranking

The existing eligibility builder already caches the ordered bin list for the actual signed bounds, mixer and scout rate. The new code extracts contiguous runs from that list with no change to the eligibility predicate. At the normal symmetric bounds, the actual grid has 2,621 eligible bins in two spans. The first mode writes only those powers and the second adds its powers in the original order. As the second mode is added, AVX2 finds one maximum per 32-bin tile. An increasing-index equality search picks the earliest equal maximum. The maximum for each tile can be reused by the second search unless its winner is inside the original circular exclusion. Only such tiles receive an additional exact search over their remaining bins. The AVX2 branch preserves the original behavior when the first eligible entry is NaN. Unsupported CPUs and irregular lists with more than two runs use the original sweep. [Eligibility cache](receiver-resident-cancel.md) · [Sparse arithmetic](../../../tools/pipeline_eval/variants/experimental/receiver_sparse_carriers.inc)

| Saved sample | Lane calls per repeat | Frozen spectral median CPU | Sparse sweep median CPU | Median paired saving |
|---|---:|---:|---:|---:|
| DS26 weak-carrier stereo | 36 | 116.04 ms | 114.66 ms | 0.63% |
| Austin measured, zero center | 4 | 13.18 ms | 13.21 ms | 0.80% |
| Austin measured, shifted center | 4 | 17.68 ms | 17.55 ms | 0.01% |
| Austin phase nulls, zero center | 4 | 5.41 ms | 5.31 ms | 2.04% |
| Austin phase nulls, shifted center | 4 | 6.42 ms | 6.31 ms | 1.22% |

Twelve paired repeats alternate arm order. Full native calls include both scout passes, all gates, cancellation and numerical verification whenever the signal reaches them. All 58 DS26 and 16 Austin factors retained their complete ordered bytes, including all 30 residuals. The sparse archives returned no continued selections. Both Austin null configurations remained empty. The dense checks reuse the original sealed lane and I/Q digests for visits 2661, 3298, and 3869. All three primary CFOs and both residual factors matched full restoration. [Exact comparisons](measurements/receiver-sparse-carriers.json.gz) · [Wrapped lane authority](receiver-cfo-lineage.md)

In the matched instrumented arms, 432 carrier searches took **61.10 → 56.93 ms**, roughly **9.64 µs saved per scout**. Timing search took **72.96 → 72.77 ms**. At the latest measured `b63cf5…` stage budget, the entire carrier search accounts for about **0.283 ms per two-scout lane**, including the FFTs. The measured sweep reduces only part of that time. Recovering milliseconds per lane would require work outside these padding and eligibility changes. [Matched stage measurements](measurements/receiver-sparse-carriers.json.gz)

Nine component tests verify every eligible power byte and both picks across ties, wrap, quiet NaNs and infinities, exact gap boundaries, empty input, and one, two, or irregular runs. The candidate SHA-256 is `5a8f85a4a4d0b3ba9bad5c3f9e5a09de6a8a6e579003fb16c33960b95f918b37`. The builder first reproduces the frozen spectral receiver byte for byte, then recompiles only the timing object with the same generated site-free feedback. The results cover the saved native tests. [Component tests](../../../tests/pipeline_eval/test_experimental_receiver_sparse_carriers.py) · [Build and replay driver](receiver_sparse_carriers_trial.py)

## Reproduce

~~~sh
p=/tmp/leo-algo08v2-2x-bench
tree=/home/mouse9911/gits/leo-tracker-reduxredux
t=reports/ALGO08/single-core-2x
r=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
hist="$tree/reports/2026_11_19_receiver_screening"
saved=/tmp/ds30-v2-stage-covariance-375895/DS30-0008
lock() {
  flock -x "$p/gauss.lock" ionice -c2 -n7 nice -n15 taskset -c 2 \
    env OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
    PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="src:.:$t" timeout 80s "$@"
}
lock "$tree/.venv/bin/python" -m pytest -q tests/pipeline_eval/test_experimental_receiver_sparse_carriers.py
lock "$tree/.venv/bin/python" -m reports.ALGO08.single-core-2x.receiver_sparse_carriers_trial \
  trial "$p/sparse-carriers-rebuild" "$p" "$r/assets" \
  "$tree/reports/2026_11_20_single_scan_glrt/satellite-reference.zip" \
  /home/mouse9911/.cache/austin-waveform-20261119/exemplar250-257.zip \
  "$hist/physical/raw-source-audit.json" "$hist/arrival-and-timing/austin-waveform/native-outputs.jsonl.gz" \
  > "$p/sparse-carriers-rebuild.json"
lock sudo -n -u leo -- env OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="src:.:$t" "$r/venv/bin/python" -BPs \
  -m reports.ALGO08.single-core-2x.receiver_sparse_carriers_trial regression \
  "$p/sparse-carriers-rebuild" "$p/sparse-carriers-rebuild.json" "$p" "$r/assets" "$saved/pair.json" \
  "$saved/candidate/fast-scan-automatic-work/algo08-v2-3dce9426edd1831eade2003d69a00297/detections.json" \
  /srv/bulk/leo-dev/ds30-full-20261121/bindings/DS30-0008.json /srv/bulk
~~~
