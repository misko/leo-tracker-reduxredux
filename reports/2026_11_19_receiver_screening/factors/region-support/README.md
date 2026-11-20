# Portable v5 with local region support

The offered tile competes against a locally unrestricted position and a training-selected exterior fit. The three fits use the same orbital identities and the same held native Doppler observations. At each of two new synthetic sites, the unrestricted estimate was within 0.095 or 0.213 km of truth under all three offers. Both omitted offers and the exact prior false-publication query withheld in 21–31 s. The fixed-scale covariance also withheld every containing offer, including both sites 1.5 km from the offered face. [Protocol](PROTOCOL.md) · [Sealed predictions](raw-positions.jsonl.gz) · [Scores](scores.json)

| Offer | Unrestricted diagnostic error (km) | Conditional lower bound for tile mass | Held inside / exterior RMS (Hz) | Outcome |
|---|---:|---:|---:|---|
| Fresh Site 1, containing | 0.095 | 0.906 | 25.65 / 39.65 | Withheld |
| Fresh Site 1, near edge | 0.095 | 0.716 | 25.65 / 29.68 | Withheld |
| Fresh Site 1, omitted | 0.095 | 0.000 | 1906.08 / 25.65 | Withheld |
| Fresh Site 2, containing | 0.213 | 0.911 | 25.58 / 45.12 | Withheld |
| Fresh Site 2, near edge | 0.213 | 0.767 | 25.58 / 31.52 | Withheld |
| Fresh Site 2, omitted | 0.213 | 0.000 | 2943.80 / 25.58 | Withheld |
| Prior halo containing | 0.313 | 0.948 | 27.18 / 50.05 | Withheld |
| Prior coverage omission | 0.170 | 0.000 | 1842.66 / 26.44 | Withheld |

For all containing offers, held Doppler favored the inside position even after excluding its strongest orbital contribution. The 150 Hz fixed measurement scale with one effective unit of weight per physical arc gave coordinate uncertainties of 2.3–2.9 km. Removing an orbit shifted the unrestricted solution by at most 0.14 km. The gate's conditional position mass was below 95% in every containing case. Those diagnostic fits did not publish a position or invoke the paired compact-v5 finish. Hence both calibration arms have zero position coverage, and the table's held RMS is common prefit evidence. The known omitted replay's prior coverage outputs were 72.664 km and 66.148 km from truth despite 23.51 and 23.55 Hz conditional fit RMS. The earlier halo had also withheld its containing replay. [Same-input prior results](replay-stock.jsonl.gz)

The [development-noise follow-up](development-noise/README.md) freezes a different covariance model for a new independent two-site draw. It keeps the same 95% mass requirement and held comparison. Both ordinary containing offers and one near-edge offer published, both new omitted offers withheld, and the exact known false omission remained withheld. The near-edge miss retained 82.3% interior mass. The conditional covariance and unrestricted estimate apply to the finite local square and one set of learned identities. [Fixed-noise held support plot](held-region-support.png)

## Reproduce

The source lock binds the experiment to the previous portable receiver's frozen scientific implementation and native LP64 backend. Each worker mounts the sealed authentic causal TLE objects and receives only the native capture and offered geometry. The source and prediction directories contain the original publications and withheld results. To draw new sites or reproduce the published seed, use a separate output directory.

```sh
mkdir -p /tmp/region-support-report
.venv/bin/python -m tools.pipeline_eval.qualification.tile_region_support_trials \
  --scratch /tmp/region-support --report /tmp/region-support-report --cpus 0 7
.venv/bin/python -m tools.pipeline_eval.qualification.tile_region_support_trials \
  --score --scratch /tmp/region-support --report /tmp/region-support-report
```

Pass `--seed-hex` from the corresponding `labels.json` to reproduce the fresh acquisition and tile geometry. The report does not reproduce elapsed times, which depend on host load.
