# Protected local repair on six public search regions

The protected repair still published both false fixes when the northern and southern receivers were **100 m outside** their offered squares. The repair added **48 northern and 42 southern observations per calibration arm** on those offers and reduced the RF RMS in all four fits. Both **52.5 km omissions** withheld before signed fitting, with both calibrated coordinates null. The two valid containing replays reproduced the donor’s repaired terminals, ordered owners and all sixteen figure bytes. [Frozen cases](local-future-omissions-protocol.md) · [Scored receipt](measurements/local-future-omissions.json.gz)

Each site reused its genuine, authenticated short-receiver detector packet over all three offers. The 12 saved runs held the graph, full causal catalogue, native geographic and regional scorers, signed fitting, numerical grid and publication fixed. The matched control applied the same forward selection without the repair callback. The independent scorer used the original scoring key only after validating all twelve terminals and figure packets. Earlier northern omission decisions used the same forward factors. The closest earlier southern omissions used the reviewed regional-track scorer on unfiltered short factors. All four historical omission decisions agreed with these replays. [Northern controls](north-causal-transfer.md) · [Southern controls](regional-track-scores.md) · [Replay and scorer](local_future_omissions.py)

| Offer and reference clearance | Forward → protected decision | Owned observations per arm | Horizontal error, forward → protected (km) | RF RMS, forward → protected (Hz) |
|---|---|---:|---|---|
| North, +0.100 km | Fix → fix | 304 → 352 | 0.128 / 0.113 → 0.102 / 0.143 | 6.881 / 6.764 → 6.814 / 6.731 |
| North, −0.100 km | False fix → false fix | 304 → 352 | 0.153 / 0.102 → 0.103 / 0.115 | 6.886 / 6.765 → 6.815 / 6.731 |
| North, −52.500 km | Withheld → withheld | 0 → 0 | — | — |
| South, +0.100 km | Fix → fix | 266 → 308 | 0.577 / 0.787 → 0.441 / 0.491 | 7.983 / 7.930 → 7.833 / 7.735 |
| South, −0.100 km | False fix → false fix | 266 → 308 | 0.577 / 0.787 → 0.441 / 0.491 | 7.983 / 7.930 → 7.833 / 7.735 |
| South, −52.500 km | Withheld → withheld | 0 → 0 | — | — |

Paired entries report fixed-zero and fitted `c` in that order. The repair preserves every original satellite owner and role. On the northern near omission fitting `c` reduced final RF RMS by 0.084 Hz while increasing horizontal error by 12 m. On the southern near omission it reduced RF RMS by 0.098 Hz while increasing error by 49 m. Both low-error terminal locations remain invalid for the omitted-region task. The early regional proof agreed exactly across arms on all six offers. On both far offers, each receiver’s winning exterior point had 50 km face clearance, with zero separation between the two winners. They completed all 96 probes and withheld under `both_receivers_support_far_exterior`. [Both calibration arms, proof, and owner checks](measurements/local-future-omissions.json.gz)

The north near repair ended both fits on the offer face. Its post-repair check spent 25 probes and stopped at `inside_score`, the same stop as the original early proof. The south near repair ended 0.341 and 0.277 km inside its east face, so the boundary-triggered post-repair check used no exterior probes. The early south proof likewise stopped at `inside_score` after 25 probes. The existing evidence allowed both invalid near-region terminals. [Existing signed route](blind_joint_route.py) · [Regional decision](early_region.py)

## Saved execution and figures

| Offer | Solve CPU, forward → protected (s) | Process elapsed, forward → protected (s) | Repair nomination / refit / extra exterior CPU (ms) | Grid points / PNGs per publication |
|---|---:|---:|---:|---:|
| North, containing | 3.565 → 3.715 | 6.854 → 6.918 | 20 / 30 / 215 | 137 / 8 |
| North, 100 m omitted | 3.587 → 3.830 | 6.920 → 7.143 | 21 / 29 / 236 | 137 / 8 |
| North, 52.5 km omitted | 2.359 → 2.206 | 3.553 → 3.350 | — | 0 / 0 |
| South, containing | 3.325 → 3.309 | 6.414 → 6.486 | 18 / 32 / <1 | 144 / 8 |
| South, 100 m omitted | 3.326 → 3.343 | 6.438 → 6.411 | 17 / 31 / <1 | 137 / 8 |
| South, 52.5 km omitted | 2.316 → 2.234 | 3.522 → 3.381 | — | 0 / 0 |

These are single order-alternated saved pairs on one low-priority Gauss core. Both far cases exit before the repair callback. Their process differences reflect variation in a shared execution path. The largest measured repair cost was the northern boundary reprobe. All eight fixes completed the grid and optimizer path with zero endpoint objective-replay error in both arms. The score independently decoded all **64 required PNGs** and matched their bytes and pixels to the recorded evidence. Each of the four matched fix pairs changed its figure bytes and pixels after support changed. All 64 sealed PNGs are available in `/var/tmp/leo-local-future-omissions-figures.zip` with SHA-256 `1942ac1a1be2358fb8ef308a6d99ca035ef6594678ab56e009c5e7c108604afe`. The original publication stores, paths and numerical grids are under `/var/tmp/leo-local-future-omissions.kwn5FsYr/paired`. [Receipt with per-file digests](measurements/local-future-omissions.json.gz)

## Reproduction

Use the [frozen donor scorer and repair](local_future_repair_trial.py) and the [offer driver](local_future_omissions.py) with subcommands `run NEW_ROOT GEOGRAPHIC_LIBRARY REGIONAL_LIBRARY` and then `score NEW_ROOT NEW_JSON`. The run uses the installed v3 payload and release interpreter. The score uses the repository Python environment and the original reference files `reports/ALGO08/regional-release/scoring-key.json` and `reports/2026_11_21_ds30_full/reference-audit.json` required by the shared scorer. The first scoring invocation lacked the latter in the sparse checkout. Restoring it allowed scoring the same sealed outputs. No inference was repeated. The Gauss CPU, lock and thread settings are those in the protocol. Twenty-eight focused and adjacent tests passed. [Added checks](../../../tests/pipeline_eval/test_local_future_omissions.py) · [Donor repair tests](../../../tests/pipeline_eval/test_local_future_repair.py)
