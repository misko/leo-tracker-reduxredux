# DS3 iteration 32: session-nominal basin closure

This isolated experiment continues the sealed DS3 iteration-21 edge using the
same DS3-local frozen identities, timing, RF group weights, nominal Doppler
selector, profiled per-track CFO, and 800 Hz capped equal-session loss. It does
not modify or register with the historical backfill or aggregate report.

The prospective search permits at most 32 translated 48.828125 m lattices,
then eight 24.4140625 m lattices and eight 12.20703125 m lattices. Every stage
must select an interior 3 by 3 cell. A final non-selecting widened causal-rate
audit must converge away from its bounds and pass direct SGP4 replay within
0.2 Hz. The surveyed coordinate enters only through `evaluate_postseal.py`
after plan, inference, deterministic replay, and qualification are sealed.

`plan.json` is the preserved, superseded pre-execution seal. Review found that
the cached engine only invokes its widened audit for historical iteration IDs
20 and 21. No inference used that plan. `plan-v2.json` binds the isolated
wrapper that explicitly applies the same reviewed audit after a successful
interior closure; it is the authoritative prospective plan.

The completed blind run qualified numerically and replayed deterministically.
Its post-seal estimate is `(37.85654519329384, -122.47396176823618)`, with
`1.3235124655955364 km` surveyed-reference error. See `REPORT.md` for gates,
runtimes, exact artifact hashes, audit details, and comparison with the
`0.6925484539098848 km` full-DS3 surface and `0.11186936921843071 km`
42-scan RF-trim prior.

```bash
.venv/bin/pytest -q reports/2026_09_25_ds3_iteration32_session_nominal_closure/test_run.py
bash reports/2026_09_25_ds3_iteration32_session_nominal_closure/run_pipeline.sh

# Or run each stage manually:
.venv/bin/python reports/2026_09_25_ds3_iteration32_session_nominal_closure/run.py plan
.venv/bin/python reports/2026_09_25_ds3_iteration32_session_nominal_closure/run.py infer --workers 2
.venv/bin/python reports/2026_09_25_ds3_iteration32_session_nominal_closure/run.py replay --workers 2
.venv/bin/python reports/2026_09_25_ds3_iteration32_session_nominal_closure/run.py qualify
.venv/bin/python reports/2026_09_25_ds3_iteration32_session_nominal_closure/evaluate_postseal.py \
  --reference-latitude 37.84903264307456 \
  --reference-longitude -122.4856541910174
```
