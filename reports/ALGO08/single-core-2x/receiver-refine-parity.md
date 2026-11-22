# Exact rejection of coarse seeds using one frame parity

The opt-in parity bound saved **1.15%** median native CPU on the prospective Gauss archive, **0.63%** on the weak-carrier archive, and **1.73%** on the four Austin field edge/windows. Native CPU on the four Austin phase nulls was flat. All **207 ordered factors**, including **81 signed residuals**, matched the exact fractional-batch receiver. The savings are too small to narrow the publication budget materially. [Matched timings, profiles and hashes](receiver-refine-parity-results.json)

## Certificate

The earlier power-only bound allowed a normalized refinement score of one. The new bound measures half the real full-rate correlations and lets an independently confirmed seed set the score that another seed would have to exceed. For each of a later seed's nine offsets, the receiver computes the original eight block correlations on the seven even frames. Let $z_{f,b}$ be those complex correlation values. Even after the unknown signed carrier correction, each cosine and sine component lies in $[-1,1]$. The triangle and Cauchy–Schwarz inequalities give

$$
\sum_{f\ \mathrm{even}}\left|\sum_{b=0}^7 z_{f,b}\,w_b\right|^2
\ \le\ 16\sum_{f\ \mathrm{even}}\sum_{b=0}^7 |z_{f,b}|^2 .
$$

The factor is eight blocks times the squared norm bound of two for each rotation. The implementation uses 17 to allow for binary64 rounding. The binary32 correlation components are read exactly into binary64 and their squares are exact within range. The nonnegative numerator uses 56 complex norms. The reference numerator uses at most eight complex products and sequential additions per frame and seven frame powers. Their accumulated roundoff is small relative to the 6.25% allowance, even if the coherent sum cancels. The denominator uses the same even-frame order and arithmetic as the reference. The refined score is the smaller of its two parity scores, so the even bound need only be strictly below the confirmed incumbent at all nine offsets. A nonfinite value cannot certify rejection. [Prior coarse bank and power-only bound](receiver-coarse-bank.md) · [Exact bound and kernel](../../../tools/pipeline_eval/variants/experimental/receiver_refine_parity.inc)

The first seed receives all 14 frames and the original independent confirmation gates. If it fails confirmation, the original bank finishes every later seed and gates them in the original descending score order. Once a seed is confirmed, any later candidate whose upper bound is high enough receives the remaining seven frames, exact score and unchanged tie rule. A higher confirmed score replaces the incumbent, so earlier equal scores win. Wrap cases and unsupported CPUs use the original computation. No seed uses prior visits or geographic information. The coarse winner continues through the original full two-scan cancellation and independent fractional verification.

## Matched native measurements

| Saved input | Lane calls per repeat | Factors / residuals | Median reference → variant CPU | CPU saved |
| --- | ---: | ---: | ---: | ---: |
| Gauss prospective physical | 160 | 141 / 55 | 0.578690 → 0.572058 s | 1.15% |
| Gauss weak-carrier physical | 36 | 58 / 22 | 0.184783 → 0.183622 s | 0.63% |
| Austin physical | 4 | 8 / 4 | 0.021869 → 0.021490 s | 1.73% |
| Austin phase nulls | 4 | 0 / 0 | 0.007409 → 0.007408 s | 0.02% |

Five Gauss repeats and nine Austin repeats alternate arm order per lane and repeat. Gauss has two independently received lanes. Austin has two disjoint 20 ms intervals, two tuning edges and one physical antenna, so the benchmark calls only lane zero. It verifies the archived waveform and null digests. The two Gauss archives have no selected continuation rows in these sparse slices. The measurement covers complete native receiver calls and excludes archive reading, setup and publication. [Austin field provenance](austin-receiver.md)

In two instrumented prospective repeats, both arms entered 492 scouts. Their total native CPU was 1.13853 → 1.13375 seconds. Coarse refinement went from 0.14191 to 0.13959 seconds, and the early incumbent ordering increased gate CPU from 0.04521 to 0.04657 seconds. The bound attempted 820 of 1,968 seed requests and rejected 252. This removed 6.4% of seed-frame correlations. The saved arithmetic corresponds to roughly 0.8% of native CPU at the reference refinement share of 12.5%. Even perfect pruning of every attempted bound would remove only 20.8% of the refinement frames, or about 2.6% of native CPU at that same share. If every first seed confirmed and every later seed pruned, half of three out of four seeds would still cap the estimate at 4.7% native savings before paying for the bound. The unconfirmed branch and surviving candidates retain most refinement work.

## Reproduce

The unflagged build reproduced `c5fca3e240f5415a061ce17057ef215070767d23cae4932b9a1d566217eae420`. The opt-in benchmark binary was `4376653c32a6161dbaa31f8dcb494ad8eff811b3fa2dcddf56d2fe3e36967fe8`. Fifteen component tests passed, covering safe rejection, incumbent score equality, signed CFO, wrapped offsets and byte-exact full fallback. [Component tests](../../../tests/pipeline_eval/test_experimental_receiver_refine_parity.py)

~~~sh
work=/tmp/leo-algo08v2-2x-bench
tree=/home/mouse9911/gits/leo-tracker-reduxredux
study="$tree/reports/2026_11_19_receiver_screening"
trial=reports/ALGO08/single-core-2x
python="$tree/.venv/bin/python"
algo08_lock() {
  flock -x "$work/gauss.lock" ionice -c2 -n7 nice -n15 taskset -c 2 \
    env OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONPATH="src:.:$trial" timeout 80s "$@"
}
algo08_lock "$python" -m tools.pipeline_eval.variants.experimental.receiver_build \
  "$work/receiver-refine-parity.so" --pack-stencil --batch-refine --fractional-batch --refine-parity
algo08_lock "$python" -m tools.pipeline_eval.variants.experimental.receiver_build \
  "$work/receiver-refine-parity-profile.so" --pack-stencil --batch-refine --fractional-batch --refine-parity --profile
algo08_lock "$python" "$trial/receiver_refine_parity_trial.py" \
  "$work/receiver-fractional-batch.so" "$work/receiver-refine-parity.so" \
  "$work/receiver-fractional-batch-profile.so" "$work/receiver-refine-parity-profile.so" \
  /opt/leo-algo08/current/assets /srv/bulk/leo-dev/ds26-two-carrier-20261120/prospective-iq.zip \
  "$tree/reports/2026_11_20_single_scan_glrt/satellite-reference.zip" \
  /home/mouse9911/.cache/austin-waveform-20261119/exemplar250-257.zip \
  "$study/physical/raw-source-audit.json" "$study/arrival-and-timing/austin-waveform/native-outputs.jsonl.gz"
algo08_lock "$python" -m pytest -q tests/pipeline_eval/test_experimental_receiver_refine_parity.py \
  tests/pipeline_eval/test_experimental_receiver_refine_bank.py
~~~
