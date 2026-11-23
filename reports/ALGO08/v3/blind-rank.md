# Share catalogue preparation across blind rank seeds

On saved DS30-0008 detections, the replacement reduced full-catalogue rank time from **6.923 to 5.090 CPU seconds**, a **26.5%** reduction. The full cold stage including all three exact refinements fell from **13.996 to 12.303 CPU seconds**. The physical case and the independent southern containing and omitted offers reproduced the complete ordered assignments, integer aliases, refined scores, phase histories, and sites. [Matched receipts](measurements/blind-rank.json)

The installed rank takes four receiver-state seeds through the centre, and it explores the four corners with the best centre seed. Each of the eight centre explorations recomputes the same nominal geometry before applying its current receiver and satellite phase estimates. At one point, discovery also gathers the same Doppler rows and subtracts the same adjusted observations twice to form its frequency and phase-derivative statistics. The previous sparse-rank change already avoided dense phase-overlay copies in association. Duplicate identical associations also already shared their result. An earlier shared-search variant reused the centre projection. Streamed nomination cut little on the measured controls, and the temporal-moment method changed 12 of 111 dense assignments. [Sparse rank](../single-core-2x/sparse-rank-projection.md) · [Earlier centre sharing](../../../tools/pipeline_eval/variants/v5_shared_search.py) · [Nomination and moment comparisons](../single-core-2x/solver-streamed-nomination.md)

## Same centre and distinct corners

The replacement keeps one centre projection and the existing causal catalogue. Every corner still projects the complete catalogue at its own receiver coordinates. At the centre each track reuses its exact RF-scaled Doppler rows, full-time visibility, and the centered phase derivative with its three fixed reductions. Each seed recalculates the observed curve after its current receiver-smooth correction, the Doppler subtraction, and the phase cross term. For positive zero channel corrections the stock frequency and phase passes center the same residual, so one pass produces both statistics with the same row order and floating operations. A different correction uses the original separate passes. Corners use the fused arithmetic with their own distinct geometry. [Source-pinned overlay](../../../tools/pipeline_eval/variants/algo08_blind_rank.py)

The allocation limit for the cached per-track terms is 128 MiB. When another track would exceed the limit, its terms are calculated on demand. The dense case retained 110.9 MB of per-track terms and reused 53.4 million track-time-catalogue cells across the centre seeds. The existing centre planes held 144.5 MB. The cache drops both at the first corner. Exact seed improvement, full-catalogue white likelihood, alias rounding, full-time horizons, signature deduplication, stable rank ordering and the original top-three refinement all ran in both variants. The overlay has no reference location or prior branch result as input. [Work counters](measurements/blind-rank.json)

## Saved comparisons

Each pair ran in fresh low-priority processes using the installed ALGO08v3 numerical bindings, one thread, CPU 2 and the shared Gauss lock. Inputs were the sealed detector packets, the original supplied offers and the matched causal TLE archives. The dense and southern-omitted pairs ran the candidate first. The containing pair ran the control first. The cold clock covers fresh scan-context construction, ranking and all six phase refinements across the three finalists. The evidence comparison hashes the entire ordered ranked row records including the original assignments and aliases, and checks both exact phase updates and fitted site for each finalist. The comparison ends before the downstream paired RF finish because its input node, point and reference matched exactly. [Trial runner](blind_rank_trial.py)

| Saved offer | Catalogue / ranked assignments | Rank CPU s, installed → shared | Cold CPU s, installed → shared | Winning cold east, north km in both |
|---|---:|---:|---:|---:|
| DS30-0008 | 1,476 / 7 | 6.923 → 5.090 | 13.996 → 12.303 | 4.939, −5.813 |
| Southern containing | 1,618 / 3 | 0.400 → 0.318 | 0.506 → 0.421 | 12.234, 0.601 |
| Southern omitted | 1,612 / 8 | 0.512 → 0.454 | 0.629 → 0.570 | −12.500, 12.500 |

The dense stock rank called the nominal projector 13 times for 1.394 CPU seconds. The candidate called it five times for 0.547 seconds, including every corner. The stock frequency and derivative statistics used 1.616 seconds together. The candidate accumulated them in 0.682 seconds. Association used 1.872 seconds in the control and 1.859 in the candidate, and both made the same 16 calls. The three exact two-round refinements used about 7 CPU seconds. The omitted offer retained its original corner minimum, which requires the exterior check in the complete solver. This local saving leaves most of the dense cold and downstream repair and evidence time in place. [Original blind finish](blind-joint.md)

Six owned tests and three adjacent sparse-projection tests passed. The owned tests verify binary64 statistics on C- and F-order inputs, repeated observation times, changing receiver-corrected observations, distinct corners, the memory limit, and the original channel-correction path. The benchmark requires no raw I/Q access. [Tests](../../../tests/pipeline_eval/test_algo08_blind_rank.py)

```sh
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
payload=/opt/leo-algo08/algo08v3/payload
rank_code="$PWD/reports/ALGO08/v3"
flock -x /tmp/leo-algo08v2-2x-bench/gauss.lock ionice -c2 -n7 nice -n15 taskset -c 2 \
  env PYTHONPATH="$rank_code:$payload:$release/src:$release" \
  OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 \
  "$release/venv/bin/python" -BPs "$rank_code/blind_rank_trial.py" "$case" "$new_receipt" \
  --profile --candidate
```

Use `DS30-0008`, `south-containing` or `south-far` for the saved case. Omit `--candidate` for the installed control.
