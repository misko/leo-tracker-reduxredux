# Before031 matched disk control

The separately source-frozen before031 zero-fit radial replication passed the unchanged prespecified trigger: original domain KKT 0.000355950715, recentered KKT 8.072205293, radius 24.999999999999762 km, physical radial derivative −11.010872146 objective/km and centered 0.1 m derivative −11.010870949. Initializer delta was zero. Three original evaluations, zero fits, no held/reference evidence. Root reviewed these actual numbers before authorizing this two-call control.

Use the exact saved original before031 all-band training winner vector and nuisance in both calls. Keep its original winning 25 km disk for `original-disk`; center the new 25 km disk on that same winner XY for `recentered-disk`. All observations, candidate bank, full priors, native singleton likelihood, original epoch-shift orbit model, calibration and timing layout remain unchanged. Fitted c only. The high/low fits are not seeds, and the reference is not a center or selection criterion.

Both calls use the original `fit_group_calibration` with 20 s and 600 iterations. Reuse the independently qualified same-winner initialization/domain and endpoint-replay ports from the C003/C023 control. Require identical effective initial vectors; only the original tiny timing-face margin ≤1e−8 is allowed, with first seven coordinates unchanged. Source endpoint feasibility is distinct from solver initialization. Audit each returned physical endpoint under its own disk and full nuisance constraints; objective/NLL/reported KKT must replay within 1e−7. Select only its own stationary returned endpoint; no added incumbent, restart, continuation or retry beyond these two declared calls.

Freeze original audit/input/source authority and added control source before preparation. Internal whole-pair cap 120 s, including source validation, original cached preparation, two calls, independent replays and sealing; TERM135/KILL140. One diagnostic/control worker alongside at most five prerequisite workers. Each timeout/nonstationary endpoint is retained; unexpected exceptions terminate without a scientific terminal. This is an additional warm control with original discovery/initialization/54-call case costs already incurred, not an equal end-to-end search-budget comparison.

Seal both before031 outcomes before any configured-reference join. Report training objective/NLL/RMS separately from position error; this experiment prepares no held data. Report the before branch separately from the ten-case after cohort, and preserve all baseline histograms and original controls. An objective improvement alone is not an accuracy improvement.

```text
python tools/ds21_model_c_before031_disk_control.py freeze --diagnostic reports/2026_10_14_ds21_ds22_next_round/local/model-c-domain-before-031-v1 --output reports/2026_10_14_ds21_ds22_next_round/local/model-c-domain-before-031-control-v1
timeout --signal=TERM --kill-after=5s 135s python tools/ds21_model_c_before031_disk_control.py run --output reports/2026_10_14_ds21_ds22_next_round/local/model-c-domain-before-031-control-v1
python tools/ds21_model_c_before031_disk_control.py evaluate --output reports/2026_10_14_ds21_ds22_next_round/local/model-c-domain-before-031-control-v1
```

Use release scientific Python, `PYTHONDONTWRITEBYTECODE=1`, `PYTHONPATH=src:tools` and numerical thread counts one. Owned tests cover exact two-start/cap matching, independent endpoint audit, timeout retention, unexpected exception termination, source guards, no retry and the two-outcome reference gate. No existing scientific source is modified.
