# Expanded quad development set

Latest complexity ablation: [all 112 first-start replay audits are complete](FIRST_START_RESULTS.md). One start accepts 61/64 singles, 32/32 pairs and 16/16 quads, with median errors 2,023 / 1,501 / 775 m. The original three-start arm accepts 61/64, 31/32 and 15/16, with medians 2,023 / 1,494 / 1,136 m. Acceptance populations differ; matched median error changes are zero. [Fresh cold comparisons](COLD_SEED_RESULTS.md) show observed time savings on the first DS9 block only.

The [denser-evidence pilot](DENSER_PILOT_RESULTS.md) is complete after passing [numerical prerequisites](DENSER_PREREQUISITES.md). All six warm fits pass, but sixteen points improve DS9/DS10 errors from 659/1,538 m to 486/940 m while worsening DS11 from 1,628 m to 2,464 m. No promotion or automatic window expansion follows. A within-model diagnostic separates changed endpoint identities from continuous evidence/prior tension; conditional added-observation prediction is the next proposed check.

The [complete baseline](FULL_PANEL_BASELINE.md) evaluates all sixteen blocks: 61/64 singles, 31/32 pairs and 15/16 quads pass numerical audits, with median accepted errors of 2,023 / 1,494 / 1,136 m. [Bounded continuation](POST_BASELINE_RESULTS.md) recovers all five unresolved windows; the resulting medians are 1,972 / 1,410 / 1,044 m. Continuation reuses fitted states with original work charged, rather than constituting a new cold benchmark. Numerical acceptance does not guarantee accuracy or calibrated uncertainty. All results are development evidence.

Subsequent experiments have completed: [constituent starts for all pairs](FULL_PAIR_RESULTS.md), [recursive starts for all quads](FULL_RECURSIVE_QUAD_RESULTS.md), [marginal association window pilots](MARGINAL_WINDOW_PILOT_RESULTS.md), and [weighted-curvature single pilots](WEIGHTED_MARGINAL_PILOT_RESULTS.md). These remain separate experimental arms; none replaces the full-panel baseline.

Frozen 64-scan membership: 16 non-overlapping blocks of four consecutive recordings, selected using metadata only. This adds 52 scans beyond the original 64-scan benchmark and reuses 12; together the two panels contain 116 unique scans. The original benchmark is preserved. DS12 remains outside this development selection.

| Source | Quads | Scans | Adjacent pairs |
|---|---:|---:|---:|
| DS9 | 6 | 24 | 12 |
| DS10 | 5 | 20 | 10 |
| DS11 | 5 | 20 | 10 |
| Total | 16 | 64 | 32 |

Each block A/B/C/D yields four singles, AB and CD, and ABCD. There are 112 evaluation units per model, with 16 matched A → AB → ABCD comparisons. These share observations and are not independent trials. All tuning and resampling must keep complete quads together.

All selected blocks span 26.20–26.27 minutes. Four approximately five-minute captures are separated by normal approximately two-minute capture gaps. Continuity checks use the full frozen candidate inventory, including inadmitted recordings that break runs. The selector rejects cross-hardware links, overlaps and inter-scan gaps above 180 seconds. It does not select using GPS, fit outcomes or convergence.

| Block | Chronological admitted scan ranks |
|---|---|
| DS9-B01 | 1–4 |
| DS9-B02 | 17–20 |
| DS9-B03 | 37–40 |
| DS9-B04 | 57–60 |
| DS9-B05 | 77–80 |
| DS9-B06 | 97–100 |
| DS10-B01 | 1–4 |
| DS10-B02 | 41–44 |
| DS10-B03 | 87–90 |
| DS10-B04 | 135–138 |
| DS10-B05 | 179–182 |
| DS11-B01 | 1–4 |
| DS11-B02 | 17–20 |
| DS11-B03 | 33–36 |
| DS11-B04 | 50–53 |
| DS11-B05 | 78–81 |

Eight selector tests pass, covering missing captures, long gaps, overlapping captures, hardware changes, deterministic selection, duplicate rejection, nested units and real-data counts. Membership and input/source bindings are hash sealed in [selection.json](selection.json) and [selection.sha256](selection.sha256).

All sixteen blocks are evaluated, with correlated nested windows. See [PILOT_REPORT.md](PILOT_REPORT.md) for the original model and [FULL_PANEL_BASELINE.md](FULL_PANEL_BASELINE.md) for the complete baseline. All 64 scans have admitted observation/orbit inputs. Capture-bound operator pose companions were verified for all 64 scans, reporting constant location within each quad; this is not physical movement sensing or a survey.

[PROTOCOL.md](PROTOCOL.md) is the original frozen execution plan; its final “Current stage” paragraph records the state at selection time. All baseline windows restart from the original uniform Sacramento prior and fixed 100 ft MSL height. Input or numerical failures remain in the selected population without replacement. The common-clock pilot retains independent clocks; [three cold equivalence checks](POST_BASELINE_RESULTS.md) validate the faster acquisition on the selected single, pair and quad, with timing limitations stated separately.

![Selected blocks](selection.png)
