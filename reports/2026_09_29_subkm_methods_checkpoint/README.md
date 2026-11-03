# Prototype evaluation checkpoint

The tested methods improve agreement with the operator's reference coordinate, but do not yet establish reliable subkilometre absolute accuracy. The configured search center itself is 809 m from that reference. Its independent uncertainty was not supplied, and the candidate banks remain conditioned on the site region.

[Generated comparison table](table.md) · [Full-precision results and input hashes](results.json)

The table reports spherical horizontal reference distance, not calibrated accuracy. N8 medians summarize three fits; the other rows show one fit per dataset. The contiguous windows belong to the existing sparse 24-scan pool. Scan counts are not independent trial counts. Score-balanced selection uses all scouting scans to fit its selection criterion: retaining eight scans after inspecting 24 is compression, not an eight-scan acquisition result.

## What to retain

1. **Pooled N24 as the working geographic baseline.** Reference errors are approximately 388, 390 and 107 m for DS7, DS8 and DS9. This is encouraging agreement under the present site-conditioned setup. It is not blind validation.
2. **Training-only timing re-selection as an optimization safeguard.** One pass recovered the best known N24 mode from the best distant-start endpoint in each dataset. It changed none of the 72 timings in the nine already-selected contiguous N8 fits. Numerical agreement between optimizers is not positioning precision. See [timing re-selection](../2026_09_29_timing_reselection/) and [N8 audit](../2026_09_29_n8_timing_reselection/).
3. **Score-balanced selection for compression research.** Eight retained scans reproduce the 24-scan locations within about 5–21 m, but require the full 24-scan scouting fit. Reducing scouting to 12 scans yields reference errors of 1,038, 1,232 and 534 m. It does not yet solve acquisition efficiency. See [24-scan selection](../2026_09_29_score_balanced_selection/) and [prefix experiment](../2026_09_29_prefix_score_selection/).

## What did not transfer consistently

- **Sequence-informed shared phase drift:** the scaled optimizer audit gave 379 held-frame improvements and 421 regressions across 800 frames; mean normalized-error improvement was negative (−0.0000279). This parameter is an effective phase model, not a measured hardware clock. Do not promote it into Doppler correction. See [waveform experiment](../2026_09_29_shared_phase_drift/).
- **Shared curvature:** reference distance improves on DS7 and DS8, worsens on DS9. Summed outside-pool log-score changes versus N24 are −12.02, +16.91 and −2.35, respectively, with only 6/15 scan wins. Better source residuals are insufficient grounds for promotion. See [curvature evaluation](../2026_09_29_curvature_n24/).
- **Geometry-only selection:** more predicted information does not ensure less error; DS7 remains at 1.83 km. Measured scan disagreement explains why score balance matters. See [selection](../2026_09_29_information_selection/) and [disagreement audit](../2026_09_29_scan_disagreement/).
- **Recency weighting by window choice:** recent versus early data and cumulative versus recent data have mixed forward predictive results. There is no consistently winning recency rule in these panels. See [temporal evaluation](../2026_09_29_temporal_forecast/).

## Next priorities

1. Freeze the baseline, timing safeguard and evaluation rules before evaluating another untouched partition. Keep location distance, excluded-scan predictive likelihood, convergence and abstention coverage separate. Existing repeatedly inspected targets are exploratory evidence.
2. Test whether scan disagreement can support a selection or abstention rule using only scans available at decision time. Compare against timestamp-balanced selection at the same scouting budget. The 24-scan compression result cannot answer this question.
3. Obtain the provenance and horizontal uncertainty of the operator reference. A justified bound can establish a bound on absolute error for a fixed estimate; decimal precision cannot. Also compare against the configured center, which already falls below 1 km reference distance. See [reference audit](../2026_09_29_reference_accuracy_gate/).
4. Require held-frame transfer before introducing any sequence-derived frequency correction into the geographic fit. Preserve frequency ambiguities and receiver-specific evidence rather than forcing a shared clock correction that failed transfer.

No new RF collection or production component changes are part of this checkpoint. These artifacts are local; this checkpoint does not claim remote publication.

## Reproduction

From the repository root, run `python3 reports/2026_09_29_subkm_methods_checkpoint/build.py`. This reads saved JSON outputs, requires qualified source results, recomputes the N8 medians from estimated coordinates, and records SHA256 hashes for all inputs. It does not rerun RF extraction or claim a fresh independent trial.
