# Calibration work completed; bounded pilots preserved

Owned scope is this `calibration/` directory only. No sealed iteration-2 file,
production state, QNAP path or scientific golden fixture changed; no RF was
collected and no commit or push was made.

The executable components are `donors.py`, `causal_calibration.py`,
`run_calibration.py` and `wide/portfolio.py` / `wide/run_portfolio.py`.
`donor_manifest.json` preserves the causal public-adapter lookup: four proven
same-radio/rate/mode/actual-RF, same-stream-family prior donors, and S01 with no
proven donor. Both exact generation tokens, capture end, completion upper bound,
age and immutable input/terminal/calibration-stage digests remain bound.
Donor information is a band-difference initializer only; original priors and
all current physical calibration columns remain free during training.

All four neutral pilots and all four nine-point pilots are retained in their
respective `results/` directories. `README.md`, `comparison.csv` and
`summary.json` report every result. Neutral fitted-c donor/no-donor held counts
are both 237/1994; neutral c=0 counts are both 248/1994. Wide fitted-c counts are
242 donor / 226 no-donor; wide c=0 counts are 225 donor / 236 no-donor. All wide
endpoints are nonstationary. There is no demonstrated predictive recovery and
no basis for an all-five cold campaign. Configured reference distances are
evaluation products, separate from frequency fit and coverage.

Seven component tests passed: four in `test_calibration.py`, three in
`wide/test_portfolio.py`. They cover end-to-end held-CFO invariance, ignored
donor-position fields, shared-delta fallback physics, exact transport, c=0,
score caps including partial profiles, causal donor checks, and a grid that
scales only with prior radius. No default geometry node comes from an evaluated
location. Each wide run uses exactly nine proposal orbit projections and
1000 charged scores (820 full objective calls and 180 partial RX scores).

`production_replay_audit.md/.json` is a read-only audit, not a launched
experiment. A future faithful original-production cold test must derive a new
complete temporal-half raw-probe input, then rebuild discovery/calibration.
Historical 63/66-target-group holdouts leave 4734/4731 full-time observations;
their 75/129 coherence result is not a whole-half baseline. The public production
entry point has a hard 240+130-second admission reserve, with historical
480-second-cap executions taking 324–406 seconds. Its A/B/shared exact counter
excludes substantial discovery work. A train-half ephemeris bank spans only
that half plus 21 seconds; held evaluation needs explicit full-metadata-time
propagation of train-selected IDs and a stated clock-extrapolation policy.
Upstream production discovery is fitted-c; any downstream c=0 continuation
must retain that conditional qualification.

`manifest.json` seals the completed directory. Further scientific changes
belong in a new versioned experiment; none should overwrite these pilot
receipts or relabel them as successful recovery.
