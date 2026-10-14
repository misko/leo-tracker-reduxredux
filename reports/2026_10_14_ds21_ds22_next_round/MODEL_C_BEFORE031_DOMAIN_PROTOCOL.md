# Separate before031 radial replication

The complete coverage/after cohort screen is sealed before this separate experiment. Metadata from newly A-sealed before031 identifies a winning original 25 km disk contact (24.999999999999766 km). No position error was read or used to select this case. This is a **before-branch** replication, separate from the frozen ten-case coverage cohort.

Use `model-a-pipeline-before-031-cached-v2`, requiring label 031 and its genuine `ds21-generic-fitted-model-composition-v2` scientific schema. Freeze added wrapper/trigger sources and original case source/input/call authority before training cache preparation. Validate original all/low/high unit selectors through their genuine cached readers; only the all winner enters the radial test. Preserve original observations, candidate bank, calibration/priors, native likelihood, epoch-shift physics, timing and fitted c.

Use the prespecified physical trigger from `MODEL_C_COHORT_DISK_SCREEN_PROTOCOL.md`: source independently stationary ≤0.001, matching saved KKT; local 25 km disk contact ≤1e−6 km and squared-radius constraint ≤1e−6 km²; outward physical gradient ≤−0.01 objective/km; centered 0.1 m finite difference negative and agreeing within max(0.005, 1% of absolute analytic derivative). Three original objective calls, zero fits, no held/reference evidence. Original and recentered domain KKT remain separate; saved endpoint and solver initializer semantics are unchanged. The 180 s internal whole-slice bound includes validation, preparation, replays and sealing; TERM at 195 s, KILL at 200 s. One diagnostic worker runs alongside at most five prerequisite workers.

```text
python tools/ds21_model_c_before031_domain.py freeze --parent reports/2026_10_14_ds21_ds22_next_round/local/model-a-pipeline-before-031-cached-v2 --output reports/2026_10_14_ds21_ds22_next_round/local/model-c-domain-before-031-v1
timeout --signal=TERM --kill-after=5s 195s python tools/ds21_model_c_before031_domain.py run --output reports/2026_10_14_ds21_ds22_next_round/local/model-c-domain-before-031-v1
```

Use release scientific Python and numerical thread counts one. If the sealed numerical trigger supports it, root reviews this separate replication before the proposed two-call original-disk versus recentered-disk continuation at the same original all-winner state/nuisance, both 20 s / 600 iterations, fitted c. Seal both outcomes before a reference join and retain original controls. No automatic fit or broader promotion follows metadata alone.
