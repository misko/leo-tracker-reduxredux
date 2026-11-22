# Pairing frame covariance entries without changing their sums

The paired kernel cut covariance and mode-construction CPU by **13.68%** and complete native receiver CPU by **1.67–2.93%** across the small public simulation prefixes and generated cases. All **13 ordered factors**, including **four residuals**, reproduced the balanced floating receiver's timing, CFO and scores. This adds a modest native gain without omitting any frame, covariance entry or mode. [Build and measurement receipts](measurements/receiver-mode-pair.json)

The compiled x86-64 reference uses four Float32 accumulation chains per covariance entry. It accumulates a scalar tail into the first chain and folds the four results in order. The new AVX2 kernel places two independent partners of one normalized frame in the two 128-bit halves of a vector. It broadcasts the common frame's samples once and keeps the original products, additions and reduction order in both halves. A final unpaired entry and systems without AVX2 use the reference dot product. Normalization, Hermitian placement, Jacobi sweeps and the two mode projections use their original arithmetic. The earlier covariance gate tested a statistical omission rule. This kernel computes its full matrix. [Prior covariance gate](receiver-covariance-confirmation.md) · [Paired dot product](../../../tools/pipeline_eval/variants/experimental/receiver_mode_pair.inc)

| Saved input | Lane calls per repeat | Factors / residuals | Median reference → candidate CPU | Median paired saving |
| --- | ---: | ---: | ---: | ---: |
| Northern simulation, first 16 visits | 32 | 3 / 0 | 66.68 → 64.72 ms | 2.93% |
| Southern simulation, first 16 visits | 32 | 0 / 0 | 52.73 → 51.41 ms | 2.49% |
| Generated I/Q, both pilot edges | 8 | 10 / 4 | 31.87 → 30.86 ms | 1.67% |

The generated protocol uses four 20 ms stereo windows, two per pilot edge. Lane zero receives strong and weaker pilots at opposing signed carriers. Lane one receives noise or a separate pilot. The evaluated centers are zero and ±87.5 kHz, and the planted carriers are distinct from the training carriers. The timing alternates arm order over lanes and repeats, with five repeats per simulated site and nine for the generated cases. The sample supplies little positive evidence at the public sites, and it yields no selected continuation. The logged native clock includes both scout passes and their independent gates on lanes that reach them.

The two separately instrumented builds processed the same 246 scouts across 216 complete native calls. Covariance through mode construction took **78.291 → 67.578 ms**. Complete native time went from **428.846 → 421.850 ms**. The baseline mode stage accounted for 18.3% of this profile, giving a 2.50% native arithmetic saving at the measured stage reduction. The full instrumentation measured 1.64% aggregate savings. No publication was evaluated.

## Independent physical recording from Austin

The same two frozen binaries processed two disjoint 20 ms periods from a single antenna in Austin, each at both pilot edges. Both receivers returned the same eight ordered factors and scores. In all four edge/window combinations the strongest factor matched the authors' relative frame timing. The largest absolute discrepancy was **0.645 sample** at 10 MS/s. Both receivers returned zero factors on all four matched phase-randomized controls. Nine alternating-order repeats gave a **1.21% median paired native CPU saving** on the physical windows and 2.47% on the controls. These are four configurations of one physical excerpt. This checks acquisition at another station. Its duration, timing information and channel coverage do not support a position benchmark. The AVX2 result was measured on Gauss. [Independent field receipt](measurements/receiver-mode-pair-austin.json) · [Source and timing reference](austin-receiver.md)

The replay uses the two binary hashes below and the release's pinned pilot templates. Pass the authenticated archive, source audit and wide-GLRT receipt listed in the Austin reproduction command to `austin_windows`. Use `austin` with the reference and candidate libraries. After the native calls, score each winning factor with `score` against the first complete author-marked frame of its window. [Checked input loader](receiver_refine_parity_trial.py) · [Paired timing and factor comparison](receiver_resident_cancel_trial.py) · [Phase scoring](austin_receiver_trial.py)

## Frozen pipeline for the next paired test

The next raw-to-web candidate uses this paired covariance receiver and the previously exercised predictive-grid solver. Its specification is `sha256:375895c3afda3abd3a916f90bbd63248b5e792f70c78a0e4f136c9bf1a79d423`. All solver source and library hashes match its immediate parent. Its end-to-end speed and position accuracy remain unmeasured. First compare one matched pair on the public **southern near-inside offer**, which stresses a different regional frame and pilot edge from the prior northern integration. Use its detections to check the near and distant omitted offers. This is a development test. Report the known near-omission failure if it persists. The twelve further DS30 pairs and fresh-site panel are outside this test. [Frozen specification](measurements/covariance-posterior-freeze.json) · [Parent's raw-to-web evidence](signed-repair-triage.md#full-two-scan-receiver-with-balanced-synthetic-training-at-the-northern-site)

## Frozen builds and tests

The candidate and its instrumented control use the same site-free training at zero and ±100 kHz as the balanced receiver. GCC required matching branch profiles for every translation unit. The candidate SHA-256 is `d44c60320320be8281ed6e71285f8cb50cc0e204df9fa1eef53d36c514e51128`. The uninstrumented reference is `678d8a24ae727cc65442436955c4e9718354ada4e103db24c362d3d9b727ff9d`. Seven direct byte-comparison tests covered the two native widths, partial vectors, unaligned input, identical partners, signed zeros and mixed magnitudes. [Balanced training](receiver-resident-cancel.md#balanced-mixer-training) · [Component tests](../../../tests/pipeline_eval/test_experimental_receiver_mode_pair.py)

~~~sh
p=/tmp/leo-algo08v2-2x-bench
work="$p/paired-mode-rebuild"
manifest="$p/paired-mode-rebuild.json"
t=reports/ALGO08/single-core-2x
py=/home/mouse9911/gits/leo-tracker-reduxredux/.venv/bin/python
assets=/opt/leo-algo08/current/assets
lock() {
  flock -x "$p/gauss.lock" ionice -c2 -n7 nice -n15 taskset -c 2 \
    env OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONPATH="src:.:$t" timeout 80s "$@"
}
lock "$py" -m pytest -q tests/pipeline_eval/test_experimental_receiver_mode_pair.py
lock "$py" "$t/receiver_mode_pair_trial.py" freeze "$work" "$assets" \
  "$p/site-free-balanced-mixer-pgo-v2/balanced-combined/use.so" > "$manifest"
lock "$py" "$t/receiver_mode_pair_trial.py" evaluate "$work" "$manifest" "$assets" \
  /tmp/leo-regional-qZJKBw4W/public/panel.json
~~~
