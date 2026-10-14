# DS21-053 C: matched expanded-domain channel views

All three fitted-c fits passed independent stationarity and feasibility checks.
The shared 50 km domain substantially improves every view; the combined result
still trails the lower band and does not reach the sub-kilometre target.

| Likelihood view | Previous 25 km error (km) | Matched 50 km error (km) | 50 km stationarity | Distance from unchanged centre (km) |
|---|---:|---:|---:|---:|
| CH1–8 | 10.055802 | 1.749188 | 0.000168314 | 36.214780 |
| CH1–4 | 10.213730 | 1.405833 | 0.000106053 | 35.917770 |
| CH5–8 | 9.600813 | 1.759683 | 0.000043963 | 32.809240 |

The full-band error exceeds lower-band error by 0.343355 km and improves on
upper-band error by 0.010495 km. Every endpoint is interior to the expanded disk.
Further radius expansion is therefore not justified by an active boundary here.

These are conditional likelihood ablations. All views retain the same full-band
candidate bank, coordinate frame, priors, original clock-winner seed, nuisance
state, unchanged search centre, and 20-second/600-iteration budget. The earlier
training-only outward-gradient test triggered expansion; no reference position
selected the centre, initial state, or radius. The 25 km comparison comes from
the sealed prior view experiment, which used the same near-basin source state.
The current three-call run takes that state directly and fits each view once.
No cross-view objective ranking is meaningful. No cohort baseline is replaced.

All three calls were sealed before reference evaluation; total runtime was
42.880 seconds. The full-band result exactly reproduces the preceding 50 km
disk-control result. Five evaluator rejection tests and Ruff passed.

Sources: driver `6759f2c9e`; evaluator/tests `b4fe9ec94`.
Experiment: `/srv/bulk/leo-research-ds21-ds22/2026_10_14/model-c-clock-expanded-views-053-v1`.
Terminal SHA256: `37895ff5a7ce9ecf561f26ca6ee72a3af058eeac25160f4f67ef01e1be18ddd0`.
Seal SHA256: `940620e1c38d6b5af88ebc3d17ad67d641040fb1bdfacf34af77ee50b02f605e`.
Numerical outcomes and independent audits are in `development-errors.json`.

Next: compare each endpoint's per-band likelihood and nuisance state under
both likelihood views, before choosing a calibration or association intervention.
The remaining difference cannot be attributed to the former 25 km boundary.
