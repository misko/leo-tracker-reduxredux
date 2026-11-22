# Sparse phase updates in full-catalogue ranking

Deferring the full-sky phase copies reduced the frozen `ad417aaa…` DS30-0008 ranking from **8.050 to 6.719 CPU seconds**, a **16.5% reduction**. The existing India waveform control measured **0.514 to 0.506 seconds**. On both inputs every audited candidate score, alias, bias, RMS, gate bit, full-time horizon decision, binary64 squared residual and ranked node record agreed exactly. [Matched ranking receipt](measurements/sparse-rank-projection.json)

The dense profiled solve spent 8.130 seconds in ranking, 9.268 in the screened phase fits, and 14.706 in conservative recovery. Within ranking, 16 association calls took 2.948 CPU seconds. The three full-array copies at the start of their projection routine accounted for 0.957 profiled seconds. The 13 pairs of discovery statistics and derivative augmentation took 1.620 seconds together. Previous experiments covered single-pass statistic fusion, reuse of a repeated identical association, reuse of the centre projection, and exact streamed nomination. The sparse overlay targets the separate copies of the full nominal Doppler, elevation and derivative planes before applying the already computed per-satellite phase shifts. [Dense profile](restored-scout-0008-solver-profile.md) · [Previous association reuse](solver-discovery.md) · [Earlier centre sharing](../../../tools/pipeline_eval/variants/v5_shared_search.py) · [Earlier statistic fusion](../../../tools/pipeline_eval/variants/fit_basis.py) · [Streamed nomination](solver-streamed-nomination.md)

The normal initial-search projection marks phase magnitudes above `1e-9` seconds, propagates those satellite rows and overlays them on three copies of the original planes. The experimental binding retains the original base planes and computes the same active rows with the same code, coordinates, phase references and observation timestamps. Association still gathers every catalogue row at every observation column of each track. The binding applies the replacements to that gather in the original array layout. Other access patterns can materialize the original dense result. Additional orbital corrections and unsupported base layouts use the original path. The code is scoped to one prepared ranking scan. [Binding](../../../tools/pipeline_eval/variants/algo08_sparse_rank_projection.py)

| Saved ranking | Candidate curve profiles | Active rows across 16 projections | Avoided full-plane copy traffic | Ranking CPU, original → sparse |
|---|---:|---:|---:|---:|
| DS30-0008 | 2,621,376 | 588 of 23,616 | 2.312 GB | 8.050 → 6.719 s |
| India waveform | 450,800 | 183 of 19,600 | 124.2 MB | 0.514 → 0.506 s |

Neither sparse rank materialized a full plane or fell back. The India run reversed the arm order and preserved its exact tie and ordered proposals. The timing covers one all-catalogue rank per arm with the measured audit CPU deducted. The original and sparse arms each constructed a fresh scan context from the same verified native preparation. The full fit and recovery clocks are outside this experiment. Seven tests passed, including exact lookup of duplicate observation columns, all three projected fields, fallbacks, and the existing dense-discovery checks. [Trial runner](sparse_rank_projection_trial.py) · [Projection tests](../../../tests/pipeline_eval/test_algo08_sparse_rank_projection.py)

The 1.331-second measured ranking reduction accounts for about 5% of the dense pair’s 27.507-second detection-to-decision half-time deficit if it transfers directly. The profiled dense recovery ran two paired gates and reused neither, and its 8.192-second gate boundary and 6.241-second salvage boundary remain separate costs. This result supports one local ranking optimization on identical evidence. A reduction that closes the measured dense gap requires substantial work in the fit and recovery stages. [Dense cost accounting](restored-scout-0008-solver-profile.md)

## Distant omitted southern offer

The southern portable input reused the released detections and capture-time archive with the offer that puts the reference 57.026 km beyond its closest face. Both ranks screened 1,669 sky objects and 25 curved tracks, evaluating 667,600 candidate curve profiles in total per arm. They produced identical full-time sightline decisions, costs, biases, aliases, RMS and gate bits. All twelve recorded squared residuals and all eight ordered node records matched exactly. Ranking CPU fell from **6.185 to 5.512 seconds**, with 1.762 GB of avoided full-plane copies and zero fallbacks. This control ends at the ranking boundary. The terminal decision on this offer was measured separately. [Omitted rank receipt](measurements/sparse-rank-projection-omitted.json) · [Earlier terminal comparison](screened-stock-recovery.md#omitted-offers)

## Reproduction

Use the already staged DS30-0008 profile inputs and the published India containing packet. The runner verifies the frozen specification, both saved documents and both causal archives before starting the rankings. Use a fresh local output directory.

```sh
bench=/tmp/leo-algo08v2-2x-bench
flock "$bench/gauss.lock" nice -n 15 ionice -c2 -n7 taskset -c 2 \
  env PYTHONPATH=src:. OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  .venv/bin/python -BPs -m reports.ALGO08.single-core-2x.sparse_rank_projection_trial \
  "$bench" "$bench/sparse-rank-projection-new"
```

Add `--southern-omitted` and use a fresh output directory to run just the omitted southern ranking.
