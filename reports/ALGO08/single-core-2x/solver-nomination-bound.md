# A subset cost bound for white curve nomination

The four-observation witness preserved all **27 nominee and alias pairs** and removed over 99% of full curve evaluations at each saved anchor. It was slower than applying the original visibility mask before profiling. Compact evaluation changed the emitted diagnostics on eight tracks. The witness stays in the offline trial. [Matched receipts](measurements/solver-nomination-bound.json)

The scope is the fixed-state, ungated curve nominee consumed by shared-phase and receiver-smooth discovery. The existing streamlined path computes every full-time cost and keeps diagnostic residuals for the winner. The fine salvage bound excludes supports using acceptance gates. The new witness compares optimistic costs within the original white alias and bias model. [Streamlined nomination](solver-streamed-nomination.md) · [Fine salvage bound](solver-salvage-bound.md)

## Frozen witness

For any track longer than four observations, use the original samples at the first index, both index thirds and the last index. The same rule applies to every candidate at the anchor. Read input predictions from the current exact phase geometry. Compute full-time visibility using the existing elevation test. Use the lowest visible witness cost to choose a full-time incumbent, then profile every visible row whose lower bound can reach its guarded score. Inconclusive comparisons, alias boundaries and near ties follow the original dense calculation and catalogue ordering.

With independent white weights \(w=1/150\), the complete profile contains the squared normalized innovations, a constant-bias Gaussian prior with scale \(B=1000\) Hz, and a candidate-independent log normalization. The stock alias comes from the mean of the complete raw curve. The bound minimizes over every integer alias, retaining the same possible alias lattice. This avoids choosing one alias for the full profile from the subset.

For \(m=4\) witness rows, the normalized squared innovations decompose into \(\sum_{i<j}(e_i-e_j)^2/m + m\bar e^2\). Pair differences cancel the alias and bias. For the mean part, Cauchy–Schwarz gives

\[
 m\bar e^2+(b/B)^2
 \ \ge\ \frac{(\bar e+wB(b/B))^2}{1/m+(wB)^2}.
\]

The numerator equals \(w^2(\bar r+kP)^2\) in real arithmetic, for unaliased residuals \(r\), period \(P\) and integer alias \(k\). Its minimum over \(k\) is the squared distance from the mean to the alias lattice, scaled by \(w^2\). The subset keeps the **complete track's** log normalization. It drops only nonnegative squared-innovation contributions. The proof applies to the original independent white likelihood. Correlated whitening, split tracks, binary acceptance gates, fitted phase transfers and other objectives retain their original paths.

The arithmetic guard allows at most 4,096 observations and magnitudes up to \(2^{24}\) Hz. Pointwise residual subtraction is common to the original and witness. An original or compact full profile has raw residual magnitude at most \(2^{25}\) Hz, integer-alias correction below \(2^{26}\) Hz, and a weighted ridge bias below \(2^{27}\) Hz. Ordinary binary64 rounding of the multiplications, subtraction and complete dot products at that scale leaves less than \(2^{-18}\) normalized units per innovation. The witness reduces each pair distance by twice that allowance and the mean distance by one allowance before squaring. It widens summed costs and finalist intervals, and replays the dense calculation if the mean folded frequency lies within \(2^{-11}\) Hz of a half-alias or if finalist intervals overlap. The final compact profile uses the original floating operations. Bitwise diagnostic agreement is tested separately because changing the outer matrix shape can alter summation. [Prototype](../../../tools/pipeline_eval/variants/algo08_nomination_bound.py)

The witness, input support and guards were committed at `7c3597208` before either saved anchor ran. The calibration and phase offsets are zero at those anchors. The original phase proposal stage already uses all-time Doppler, visibility and derivative arrays. These timing boundaries retain that shared projection and measure its cost separately from per-curve nomination.

## One anchor per saved input

The three profiling repeats reverse execution order in the middle repeat. The control uses the previously verified white profile. The visibility-only arm restricts the original profile to satellites visible over the entire track. Timed witness work includes its domain check, all coarse scores, incumbent, complete finalist scoring and diagnostics. Full curve counts include the separately profiled incumbent. Repeated dummy rows used to keep the column-major orientation are covered by the timer.

| Saved anchor | Tracks | Dense / visible / witness full evaluations | Dense CPU | Visibility-only CPU | Witness CPU | Shared projection and extraction CPU |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| DS30-0008 disputed components | 12 | 17,712 / 5,197 / 85 | 3.954 ms | 1.733 ms | 2.566 ms | 117.264 ms |
| Northern near-edge simulation | 15 | 23,535 / 6,979 / 30 | 2.007 ms | 0.957 ms | 2.113 ms | 6.819 ms |

The witness uses 70,848 and 94,140 sampled cells respectively. Its full-profile work falls to 3,542 of 879,696 cells on DS30-0008 and 570 of 447,165 cells on the simulation. With the shared projection and extraction charged, the physical anchor changes from **121.22 to 119.83 ms** and the simulated anchor from **8.83 to 8.93 ms**. The visibility-only medians are **119.00 ms** and **7.78 ms** at the same boundaries. Causal sky construction and full solver time are outside this comparison.

The witness retains the full winner and alias in all 27 tests. It reproduces the complete nominee tuple byte for byte on 9 physical and 10 simulated tracks. The maximum numerical changes on the other tracks are \(4.55\times10^{-13}\) in cost, \(1.46\times10^{-11}\) Hz in bias, \(9.09\times10^{-13}\) Hz in RMS and \(1.71\times10^{-11}\) Hz in an innovation. Changing the candidate matrix shape can change the floating reduction. A planted test shows the diagnostic difference immediately in both row- and column-major layouts, even when the winner is well separated. Ties, near alias boundaries and non-white likelihoods take the original path. The complete visibility-only tuples matched on both saved anchors.

Visibility-first evaluation is the measured lower-cost direction. Its next exactness check is to preserve the original winner's floating reduction and gate diagnostics when moving rows out of the dense layout. The tested witness leaves the expensive common phase projection untouched. Avoiding that projection would require preserving the full-time inputs of the exploratory phase statistics and the later exact visibility check.

## Reproduce

The physical anchor is the centre of the original DS30-0008 offer. Its 12 components come from the previously recorded disagreement, selected by exact component key. The native input matches the original `34d0381e` roster digest. The public northern anchor is the centre of the existing near-edge offer and uses every eligible curved component. Both inputs are existing detector outputs. Each case builds a causal sky and stops inside the initialization boundary before any position fit. Fifteen targeted component tests passed. [Previous disagreement](location-triage.md) · [Anchor runner](solver_nomination_bound_trial.py)

~~~bash
algo08_work=/tmp/leo-algo08v2-2x-bench
algo08_release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
algo08_ds30=/srv/bulk/leo-dev/ds30-full-20261121
algo08_public=/tmp/leo-regional-qZJKBw4W/public
algo08_runner=reports/ALGO08/single-core-2x/solver_nomination_bound_trial.py

algo08_lock() {
  flock -x "$algo08_work/gauss.lock" ionice -c2 -n7 nice -n15 taskset -c 2 \
    env OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 timeout 80s "$@"
}
algo08_lock env PYTHONPATH=".:$algo08_release/src:$algo08_release" \
  "$algo08_release/venv/bin/python" "$algo08_runner" \
  "$algo08_ds30/runs/DS30-0008/compact_two_scan/raw-gg4o9mm7/native.json" \
  "$algo08_ds30/snapshot/inputs/DS30-0008/tle" "$algo08_release/assets" \
  "$algo08_work/integration02/ds30-station-offer.json" \
  34d0381ec59c6dc1d264292ee402adbe020ef8c6521d866dde2a83221db395c7 \
  --stock "$algo08_work/solver-control-moments-DS30-0008.json" \
  --moments "$algo08_work/solver-moments-DS30-0008.json"
algo08_north_root="$algo08_work/integration-batch-orbit/pairs/north-edge/baseline"
algo08_lock env PYTHONPATH=".:$algo08_release/src:$algo08_release" \
  "$algo08_release/venv/bin/python" "$algo08_runner" \
  "$algo08_north_root"/fast-scan-automatic-work/*/detections.json \
  "$algo08_public/tle" "$algo08_release/assets" \
  "$algo08_work/near-edge/0abe7b4514be674d9f5388e3.json" \
  54ffd828f5cb9b09baa1d38e0f3fdff5b9e41954f74e60226e239fa5c6e4f1d8
algo08_lock env PYTHONPATH=src:. \
  /home/mouse9911/gits/leo-tracker-reduxredux/.venv/bin/python -m pytest -q \
  tests/pipeline_eval/test_algo08_nomination_bound.py \
  tests/pipeline_eval/test_algo08_streamed_nomination.py
~~~
