# Optimized full-catalogue saved publication on DS30-0374

The new `joint_publication.py --optimized-full-catalogue` option published the complete saved DS30-0374 packet in **14.239 s elapsed**. The authenticated original full-catalogue run took **14.728 s**, and installed stock took **24.134 s**. The new option reproduced both full-catalogue arm results, 2,822 observation owners and roles per arm, the numerical path, both sampled grid minima, and all eight PNGs byte for byte. Grid scores differed by at most **7.276 × 10⁻¹²** in either arm against a `1e-5` allowance. [Comparison protocol](optimized-full-catalogue-protocol.md) · [Verified receipt](measurements/optimized-full-catalogue-DS30-0374.json.gz)

| Same saved detections and offer | Installed stock | Original full catalogue | Optimized full catalogue |
|---|---:|---:|---:|
| Solve including grid, CPU s | 21.383 | 12.160 | **11.680** |
| Publication, CPU s | 24.035 | 14.681 | **14.213** |
| Publication, elapsed s | 24.134 | 14.728 | **14.239** |
| Horizontal error, zero / fitted `c`, km | 1.855 / 1.935 | 1.860 / 1.929 | 1.860 / 1.929 |
| Frequency RMS, zero / fitted `c`, Hz | 101.536 / 101.520 | 101.577 / 101.594 | 101.577 / 101.594 |
| Owners per arm / complete grid nodes / figures | 2,905 / 179 / 8 | 2,822 / 179 / 8 | 2,822 / 179 / 8 |

The prior controls come from separate saved launches. The measured **1.034×** against the original full-catalogue route and **1.695×** against stock compare the same authenticated inputs and timing boundaries across those launches. The fresh CLI process through exit took **15.703 s elapsed / 15.676 CPU s**, including startup and artifact rereads in `--verify-images`. The table uses the publication function's clock, which excludes startup and that verification. Acquisition, including the raw receiver, is outside both clocks. [Previous complete saved publication](full-family-web.md) · [Installed stock verification](signed-0374-transfer.md)

The authorized 25 km search region, capture-era archive, input authority, and observation packet matched all three publications. The optimized route reproduced the original full-catalogue support, phase-history qualification and exterior decision. Relative to installed stock it kept the same satellite and role for all 2,822 shared observations in each arm and omitted 83 conditional observations per arm. Horizontal error changed by **+4.2 m** for `c = 0` and **−6.7 m** for fitted `c`. All eight PNG dimensions agree across the three runs. All eight encoded and RGBA hashes match the original full-catalogue run. None match stock, which used different fits and observation support.

## What ran on the second physical recording

The frozen finalist race completed all three branches because the closest partial score gap was **329.155**, below its required **495.375**. All three completed scores and the winning coordinates matched the original full-catalogue run exactly. The signed-history guard declined the phase update as before, so the ordinary full-catalogue finish supplied both published positions. The prepared causal catalogue was captured once. Both endpoints stayed inside the original boundary trigger and made zero exterior probe requests. This run measures neither finalist pruning savings nor savings from reusing an exterior catalogue. [Finalist race calibration and ceiling](cold-finalist-race.md) · [Portable catalogue handoff](prepared_exterior.py)

The checked posterior handoff used the reduced predictive factor on all **356** fresh evaluations, with zero fallbacks. The reduced kernel produced the same marginal Gaussian objective by dropping exactly zero triangular-solve columns and integrating the predictive-curve biases analytically. It supplied the matching squared-residual decomposition required by the attached grid evaluator. The separately timed kernel used **0.333 CPU s** in this run. The preserved full comparator spent **0.523 CPU s** in the incumbent predictive kernel. Standard evidence cost **3.001 CPU s** in the candidate and **3.312 s** in the earlier run. The candidate retained all 179 nodes, exactly the same coordinates and metadata after omitting elapsed and binding fields, and zero endpoint objective-replay error. [Grid derivation](grid-predictive-reduction.md) · [Scoped kernel binding](optimized_grid.py)

## Reproduce

Run the script as the account with read access to the archived signed detector packets. The outer audit uses the checkout's read-only storage API. The subprocess uses the installed v3 publication stack and a new publication directory. The `score` command verifies both historical publication roots against the pinned receipt and evidence digests. `--full-catalogue` remains available as the independent original route. The accepted evidence is one saved physical transfer outside the finalist race's calibration. Forty-one component and publication tests passed. [Trial and scorer](optimized_full_catalogue_trial.py)

```bash
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
trial="$PWD/reports/ALGO08/v3/optimized_full_catalogue_trial.py"
full=/var/tmp/leo-full-catalogue-web.iGqSXPBd/publication
stock=/var/tmp/leo-signed-0374.KBD4SnU5/pair/stock
out=/var/tmp/leo-optimized-full-0374-repeat
gauss() {
  sudo -n -u leo flock -x /tmp/leo-algo08v2-2x-bench/gauss.lock \
    ionice -c2 -n7 nice -n15 taskset -c 2 env \
    PYTHONPATH="$PWD/reports/ALGO08/v3:$PWD:$PWD/src:$release/src:$release" \
    OMP_NUM_THREADS=1 OMP_THREAD_LIMIT=1 OPENBLAS_NUM_THREADS=1 \
    MKL_NUM_THREADS=1 BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 "$@"
}
gauss "$release/venv/bin/python" -BPs "$trial" run "$out"
gauss "$release/venv/bin/python" -BPs "$trial" score "$out" "$full" "$stock" "$out/score.json"
```
