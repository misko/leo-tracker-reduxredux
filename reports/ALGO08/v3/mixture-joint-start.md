# A mixture start for the repaired joint solver

On saved DS30-0008 detections, the mixture handoff reduced solver-plus-evidence CPU from **43.708 to 30.274 seconds**. Both calibration arms returned full numerical evidence after one bounded repair. Their horizontal errors increased from **1.112 / 1.070 km to 2.133 / 1.980 km**, and each arm lost a net 495 observation owners. The dense comparison exceeded the 24-second target and the 0.25 km per-arm error allowance. The two small southern controls preserved their decisions. Fallback count was zero. [Prespecified comparison](mixture-joint-start-protocol.md) · [Scored receipts](measurements/mixture-joint-start.json)

## RF-only handoff

The candidate ran the previous sampled mixture in the fixed-zero arm, with the same all-catalogue five-by-five mesh, local search, eight-orbit slate and three signed alias alternatives. Its selected point and eight shared receiver terms started the installed full-data curved exploration. That exploration nominated satellite phases and owners from every curved track and causal orbit. The original anchored alias operation used the full curves at the offered site. A single exact cold position fit consumed those rebuilt assignments. Genuine-previous salvage, predictive selection, both-arm fitting, the capped common-support repair and the exterior check then followed the current repaired route. Both final arms used identical curved and predictive membership and fitting budgets. The timed saved replays exercised the original complete evidence packet. [Cold handoff](mixture_joint_start.py) · [Repaired solver](blind-joint-repair.md)

The mixture selected the east face of the dense offer, 7.446 km from the reference. The one full-curve cold fit reached the south face, with 7.008 km error and 6,104.510 Hz full-curve RMS. The first genuine-history gate retained 3,043 of the 4,522 curved points, versus 3,235 in the repaired control. Salvage added 961 points. The recheck kept 3,219 curved and nominated 825 predictive observations. One curved track with 79 points and one predictive track with 20 points failed the paired fit. The existing repair removed them and returned 3,140 curved and 805 predictive observations. [Cold and repair stage numbers](measurements/mixture-joint-start.json)

## Position, frequency fit and ownership

| Saved offer | Returned decision | Error km `c = 0` / fitted, repaired → mixture | RF RMS Hz `c = 0` / fitted, repaired → mixture |
|---|---|---:|---:|
| DS30-0008 | Both arms returned after one repair | 1.112 / 1.070 → 2.133 / 1.980 | 128.836 / 128.761 → 128.701 / 128.687 |
| South containing | Both arms returned | 0.296 / 0.607 → 0.296 / 0.607 | 6.470 / 6.373 → 6.470 / 6.373 |
| South omitted | Both withheld on the original exterior check | — | — |

Each dense arm shared 3,944 observation IDs with the repaired control. Of those, 248 changed satellite and 3,696 kept the same owner. The mixture route dropped 496 old IDs and added one, moving each arm from 4,440 to 3,945 observations. The lower RF RMS accompanies worse geographic errors on this smaller support. Within the mixture route's common dense support, fitting `c` lowered RMS by 0.014 Hz and error by 0.153 km. [Physical scoring reference](../../2026_11_21_ds30_full/reference-audit.json)

The containing southern pair matched all 266 owners in both arms. Its errors increased by 0.034 m and 0.009 m. Fitting `c` lowered RMS by 0.096 Hz and increased error by 0.311 km within the mixture route. The omitted route provisionally reached 53.948 km error in both arms with 6.598 and 6.620 Hz RMS. The same two-receiver exterior decision withheld both estimates. The postfit scorer supplied the geographic references only after inference. [Simulated references](../regional-release/scoring-key.json) · [Scorer](mixture_joint_start_score.py)

## Complete saved-solver cost

| Saved offer | Cold CPU s, repaired → mixture | Numerical evidence CPU s, repaired → mixture | Total CPU s, repaired → mixture | Elapsed s, repaired → mixture |
|---|---:|---:|---:|---:|
| DS30-0008 | 15.451 → 8.757 | 6.713 → 5.748 | 43.708 → 30.274 | 43.959 → 30.277 |
| South containing | 0.499 → 0.686 | 0.442 → 0.436 | 3.857 → 4.884 | 3.858 → 4.885 |
| South omitted | 0.641 → 0.640 | — | 6.605 → 6.734 | 6.605 → 6.735 |

Dense mixture evaluation took 6.355 seconds, full-curved reassignment took 0.591, and the exact cold fit took 1.811. The candidate still spent 5.090 CPU seconds in salvage, 2.243 in the predictive stage, and 1.496 preparing and fitting the bounded repair. Charging the saved-packet preparation and granting free numerical evidence would leave 24.526 CPU seconds. Both dense routes produced complete 179-point grids with zero selected-objective replay error in each calibration arm. Both containing southern routes produced complete 137-point grids with zero replay error. The omitted check cost 2.874 and 2.975 CPU seconds in the two runs. [Per-stage receipts](measurements/mixture-joint-start.json)

The three fresh repaired controls reproduced the published saved repaired terminal records. The timings cover one pair per offer under the shared Gauss lock with CPU 2, nice 15, best-effort I/O priority 7, and one numerical thread. Each process read its sealed detector packet and original causal archive and offer. The dense failure triggered the prespecified stop before the northern offers. Thirteen targeted tests passed. [Saved trial driver](mixture_joint_start_trial.py) · [Tests](../../../tests/pipeline_eval/test_algo08v3_mixture_joint_start.py)

```sh
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
payload=/opt/leo-algo08/algo08v3/payload
trial_code="$PWD/reports/ALGO08/v3"
flock -x /tmp/leo-algo08v2-2x-bench/gauss.lock ionice -c2 -n7 nice -n15 taskset -c 2 \
  env PYTHONPATH="$trial_code:$payload:$release/src:$release" \
  OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 \
  "$release/venv/bin/python" -BPs "$trial_code/mixture_joint_start_trial.py" \
  "$case" "$new_receipt" --candidate
```

Use `DS30-0008`, `south-containing` or `south-far` for the three measured offers. Omit `--candidate` for the repaired control.
