# Region support with development-calibrated noise

The follow-up calibrates displacement curvature using the median training RMS across independent orbits, with a 40 Hz minimum. It preserves each phase prior's precision, the orbit-deletion scatter, the held in/out score and the 95% tile-mass criterion. This addresses the fixed-noise experiment's uncertainty without changing its publication thresholds. The new blind seeds were drawn after binding the implementation. [Protocol](PROTOCOL.md) · [Source lock](source-lock.json)

Both new ordinary containing offers and one of two containing edge offers returned positions in both calibration arms. Both new omitted offers withheld in 25–27 s. The known coverage false publication withheld in 22 s, and the prior halo's containing miss returned both fixes. Every worker finished before the deadline. [Scores](scores.json) · [Sealed positions](raw-positions.jsonl.gz) · [Held support plot](held-region-support.png)

| Offer | Status (s) | Conditional tile mass lower bound | Published position error in km, zero / fitted | Conditional compact-v5 RF RMS in Hz, zero / fitted |
|---|---|---:|---:|---:|
| Fresh Site 1, containing | Returned (112.7) | 0.9991 | 0.457 / 0.319 | 23.314 / 23.312 |
| Fresh Site 1, near edge | Returned (78.6) | 0.9574 | 0.457 / 0.319 | 23.314 / 23.312 |
| Fresh Site 1, omitted | Withheld (24.6) | 0.0000 | — | — |
| Fresh Site 2, containing | Returned (110.7) | 0.9985 | 0.221 / 0.307 | 23.959 / 23.960 |
| Fresh Site 2, near edge | Withheld (35.1) | 0.8228 | — | — |
| Fresh Site 2, omitted | Withheld (26.8) | 0.0000 | — | — |
| Prior halo containing | Returned (71.5) | 1.0000 | 0.338 / 0.153 | 24.103 / 24.101 |
| Prior coverage omission | Withheld (22.1) | 0.0000 | — | — |

The shared prefit statistics distinguish ambiguity from an exterior win. On the ambiguous Site 2 edge offer, the physical estimate was 0.087 km from truth and 1.53 km inside the face. Conditional north uncertainty was 1.65 km. Held RMS was 25.77 Hz for the interior and 26.76 Hz for its nearest exterior competitor. The 82.3% mass lower bound withheld publication. The other edge offer passed with 95.7% mass and a held-forecast improvement from 32.23 to 28.24 Hz. On both new omitted offers the exterior model predicted 25.77–28.24 Hz, compared with 1.62–2.17 kHz from the same identities constrained to the offered tile. They have no compact-v5 fit or geographic error in either arm. The independent unrestricted diagnostics stayed within 0.187 km and 0.087 km of truth across all three offers at the two sites.

The ordinary offers are the two independent fresh locations. Their median published error is 0.339 km at zero calibration and 0.313 km with fitted calibration. Fitted calibration improved Site 1 by 138 m and worsened Site 2 by 86 m. Its conditional RF RMS changed by −0.0015 Hz and +0.0006 Hz, respectively. The near-edge offers reuse those captures. This trial covers two synthetic sites, one exact historical positive replay and one exact historical omission replay. The tile mass is conditional on the screened orbit inventory, the selected identities and the local search extent. [Fresh scores and held diagnostics](scores.json) · [Exact prior replay comparison](replay-stock.jsonl.gz)

## Reproduce

The local input prerequisites are the same as for the [fixed-noise experiment](../README.md). Use `--seed-hex` from this report's `labels.json` to reproduce the fresh candidate streams and offered geometry. Use a new directory for new predictions.

```sh
mkdir -p /tmp/region-support-development-report
.venv/bin/python -m tools.pipeline_eval.qualification.tile_region_empirical_trials \
  --scratch /tmp/region-support-development --report /tmp/region-support-development-report \
  --cpus 0 7
.venv/bin/python -m tools.pipeline_eval.qualification.tile_region_empirical_trials \
  --score --scratch /tmp/region-support-development \
  --report /tmp/region-support-development-report
```
