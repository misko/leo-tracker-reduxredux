# Cross-visit waveform frequency prediction

**Superseded cross-visit convention:** this run fitted wrapped cached CFO across
visits. The localization inputs already unwrap visit-dependent frequency aliases.
See [the corrected replay](../2026_09_29_waveform_alias_audit/README.md). The original
results and post-hoc offset ablation below are retained for provenance and must
not be used as conclusions about dealiased trajectory quality.

Long-pilot refinement improved held-visit prediction on **12 of 18 tracks**.
Mean error decreased in DS7, DS8 and DS9. A post-hoc constant-offset control
also favors the changed slope on 13/18 tracks. This is evidence that some
refinements affect useful frequency evolution, rather than only a constant
offset that localization would remove. It is not a geographic accuracy result.

All **54 selected excerpts** were recovered: three visits for each of the same
18 receiver tracks in the preceding experiment. We demodulated eight frames
per excerpt, 432 total, and scored 144 held-visit frames. There were no failed
tracks, replacements, quality exclusions or frequency-search boundary fits.

| Dataset | Tracks | Cached trajectory NMSE | Refined trajectory NMSE | Improved tracks |
|---|---:|---:|---:|---:|
| DS7 | 6 | 0.945485 | 0.937928 | 4/6 |
| DS8 | 6 | 0.981972 | 0.975770 | 5/6 |
| DS9 | 6 | 1.013413 | 0.914913 | 3/6 |
| All | 18 | 0.980290 | 0.942870 | 12/18 |

Lower normalized mean squared pilot-prediction error is better. Excerpts have
equal weight. The pooled relative reduction is approximately 3.82%, but the
median paired reduction is only 0.002849 NMSE. **DS9 middle RX1 contributes
74.5% of the pooled sum of improvements.** Removing it descriptively leaves
a mean reduction of 0.010112; it remains in every primary aggregate.

![Per-track held-visit comparison](comparison.png)

## Frozen test

For each previously selected track, A is its earliest training observation.
B is the earliest training observation at least two seconds later. H is the
first original held observation after B. All 18 tracks support these choices.
Training spans are 2.065–3.269 seconds and forecast horizons 0.120–4.711 seconds.
Neither waveform quality nor prior frequency outcomes selected these visits.

One trajectory extrapolates the two cached carrier frequencies linearly.
The other uses the same frequencies plus long-pilot residuals independently
estimated at A/B. Actual tuned RF is included so tuning changes do not masquerade
as frequency changes. Both arms use the same times, memberships, cached epochs,
fixed ±1500 Hz search, eight-frame fits and corrected upconversion convention.
The known pilot fit uses symbols22–221 with independent frame/carrier gains.

At H, both trajectories predict the same raw pilot observations. Its cached CFO
only defines the demodulator reference: subtracting it converts each independently
predicted absolute frequency into that reference. It does not train either
trajectory. Every arm calibrates gains on H symbols22–221 and predicts222–301.
Thus H supplies nuisance amplitude/phase calibration, but no frequency fit to
either trajectory. There is no interframe or intervisit phase-coherence assumption.

The cached H frequency and a local long-pilot H fit are descriptive controls.
Their pooled NMSEs are 0.904594 and 0.896260 respectively, better than either
extrapolated trajectory on average. The refined trajectory beats cached H in
only 3/18 cases. **Do not replace available per-visit measurements with this
two-point extrapolator.** Its purpose is to test whether earlier corrections
contain predictive information.

## Post-hoc mechanism ablation

After inspecting the primary results, we added an explicitly descriptive
constant-offset arm: add the mean of A/B residual corrections to the cached
trajectory without changing its slope. Compare this with the full refined
trajectory on the identical H samples. No new selection, tuning or extraction
was performed. This was not a preregistered endpoint.

| Dataset | Full refinement beats constant-only | Mean NMSE gain beyond constant-only |
|---|---:|---:|
| DS7 | 5/6 | 0.005678 |
| DS8 | 5/6 | 0.012040 |
| DS9 | 3/6 | 0.042630 |
| All | 13/18 | 0.020116 |

`offset_ablation.py` verifies the algebraic decomposition of the refined
prediction into the constant correction and slope contribution before scoring.
These results support investigating the slope changes, but do not identify
their physical cause as Doppler, oscillator drift or correct satellite tracking.

## Decision and limits

Retain long-pilot refinement as a candidate for a bounded geographic ablation.
The next needed artifact is a sufficiently sampled per-visit trajectory with
frequency uncertainty: two training points are too fragile for deployment.
Keep track membership, candidate hypotheses and geographic training/held splits
fixed when testing revised observations. Include the cached baseline and a
constant-offset control so improvement cannot be attributed only to a frequency
shift. Weak measurements must remain visible in coverage and failure counts.

The current assay uses previously exposed panels, and track construction used
full recordings. Eighteen tracks from nine recordings are not 144 independent
trials. Near-unit pilot NMSE in several cases limits information. There is no
verified satellite identity, independently calibrated Doppler truth, or position
estimate in this report. Consistent sub-kilometer accuracy remains unproven.

## Execution and evidence

The frozen plan contains 54 selections with no unsupported cases. A excerpts
were reused only after raw-file hashes, candidates and analysis manifests were
verified through the public source. B/H data were read through the read-only IQ
port. Extraction invocation 1 exited124 at its 120-second cap with 30 checkpointed
entries; invocation 2 resumed the remaining24 and exited0. The primary numerical
run and post-hoc diagnostic each finished within their 120-second caps.
No new RF was collected and no production code was changed.

Three trajectory tests pass (signed slope/offset invariance, deterministic
selection, unsupported coverage). The inherited estimator's four tests cover
held-symbol isolation and signed raw-waveform frequency recovery at both edges.
Plan, inventory, result and ablation hashes bind the evidence and dependencies.

- [PROTOCOL.md](PROTOCOL.md): frozen primary test.
- [plan.json](plan.json), [inventory.json](inventory.json): exact selection and extraction bindings.
- [results.json](results.json): all primary frame errors and frequency estimates.
- [TABLE.md](TABLE.md): every track and held-visit control.
- [offset_ablation.json](offset_ablation.json): descriptive slope-versus-offset evidence.
- `prepare.py`, `extract.py`, `study.py`, `test_study.py`, `summarize.py`,
  `offset_ablation.py`: reproduction scripts and tests.

Reproduction uses NumPy/SciPy, Matplotlib for plotting, and the installed public
read-only storage ports for extraction. Set `OPENBLAS_NUM_THREADS=1`. Local IQ
files are required. Artifacts are local; no remote publication occurred here.
