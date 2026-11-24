# The regional horizon screen has a small CPU budget

The nominal regional bank selects an orbit when its original coarse propagation is usable and its maximum elevation reaches −12°. Only this decision uses the coarse states. The installed code also rotates their velocities to Earth-fixed coordinates and computes azimuth, range and range rate. A position-only implementation could retain the same source order, sampling times, observer, propagation status and original floating-point elevation test while omitting those calculations. The fine bank would still contain positions and velocities for all selected satellites. This change would be independent of repeated archive reads and parser work. [Installed orbit bank](/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c/src/leo/analysis/localization_v3/orbits.py:31) · [Installed angle calculation](/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c/src/leo/sky/frames.py:158)

## Measured reach

In the saved DS30-0316 named profile, the preparation's one `look_angles` call came from `regional_bank` and took **36.601 ms inclusive CPU**. Both preparation `teme_to_ecef` calls took **43.581 ms inclusive CPU**. Making all three calls free gives an **80.182 ms profiled CPU ceiling** on that request. This includes fine conversion and the original elevation calculation, both of which a practical implementation would still perform. Other `look_angles` callers use the range rate in their scientific model. Their costs do not belong to this ceiling. The earlier instrumented DS30-0016 20/12 ms preparation measured **163.880 ms CPU** for the coarse `ecef_states` call over 682,041 satellite-time cells. That encompasses required SGP4 propagation and excludes the subsequent angle call. The earlier study counted duplicate propagation cells. Neither number measures an implemented horizon speedup or transfers as a wall-time estimate. [0316 profile](measurements/named-shared-cpu-0316.json.gz) · [0016 saved attribution](measurements/live-orbit-setup-audit.json)

The stock angular expression is `rad2deg(arctan2(up, hypot(east, north)))`. Over exact real numbers, a negative `up` satisfies the threshold when `up² ≤ tan(12°)² × (east² + north²)`. A squared binary64 implementation would still need to reproduce the original result near −12°, at signed zero and for nonfinite inputs. The original reduction propagates NaNs through a candidate row. A candidate-wide early accept on the first passing sample would need to preserve that property and the original all-times propagation status. The measured budget does not warrant implementing or certifying the inequality.

## Through-exit ceiling on the qualified raw pairs

Both arms started with every signed payload and index page resident and exited successfully on each recording. DS30-0016 used all 713 admitted visits of 808 issued and both builds emitted both fits and eight figures. DS30-0107 used 27 admitted visits of 29 issued. Both builds withheld for `no_active_curvature` with zero figures. The candidate bypassed orbit preparation on that case. [Pinned clocks and residency](measurements/horizon-risk-budget.json)

| Actual raw process | Candidate wall s | Named v3 wall s | Candidate / v3 |
|---|---:|---:|---:|
| DS30-0016 | 8.829 | 10.745 | 0.822 |
| DS30-0107 | 0.615 | 1.497 | 0.411 |
| Total | 9.443 | 12.242 | 0.771 |

DS30-0016's candidate spent 3.218 s wall in authenticated acquisition and 5.045 s in decision and publication. The latter contains **1.515 s wall** of numerical preparation and **0.704 s wall** of inference. The preparation is the only new raw scope that could contain this screen. It also includes the 99 verified archive reads and other orbit work. Any separate gain from those reads is already included when the full preparation scope is credited. [Pinned stage clocks](measurements/horizon-risk-budget.json)

| Optimistic subtraction from the observed candidate | Two-case wall s | Median paired ratio | Ratio of totals | Seconds above half total |
|---|---:|---:|---:|---:|
| Observed | 9.443 | 0.616 | 0.771 | 3.323 |
| Entire measured preparation free | 7.929 | 0.546 | 0.648 | 1.808 |
| Entire measured preparation and inference free | 7.224 | 0.513 | 0.590 | 1.104 |

Both subtractions hold the rest of each original elapsed process fixed. The horizon change could reach only a fraction of the first subtotal. These are modeled floors for the measured path, with no new observed speedup. An exact optimization would preserve each arm's detector packet, roster, inference and charts. The raw candidate and named v3 used different detector recipes on DS30-0016. The two-case comparison therefore measures those full builds, while the subtraction models one local change within the candidate.

## Historical budget and next test

Acquisition was **67.11%** of the summed wall time across the 52 historical fixes with complete phase clocks. Erasing *every* measured detections-to-decision phase on those 52 would still leave **3,993.612 of 5,638.246 s** across the original 55 recordings, a **0.713 median paired ratio** and **0.708 ratio of totals**. The three unsplit rows retain their original elapsed costs. This is a separate historical model. It does not assume the two warm raw processes describe the historical storage mix. [Historical stage ledger](measurements/acquisition-throughput.json) · [Reproduced counterfactual](measurements/horizon-risk-budget.json)

Leave nominal horizon admission as-is for the doubling work. Price any parallel catalogue-read improvement against the same inclusive preparation clock and keep overlap explicit. Use complete authenticated acquisition as the next measurement boundary for an original-format receiver idea. It must reduce the combined path enough to matter under both the qualified warm clocks and the historical acquisition-heavy mix. A measured change to the receiver alone should be billed alongside downstream solver and figure work when its detection packet changes. No waveform, archive-body, or numerical job was needed for this ceiling.

From the repository root, the [reducer](horizon_risk_budget.py) reproduces the receipt from the two compact `/dev/shm` scores and digest-pinned checked-in traces. It only reads those receipts and two installed source files. Five [component tests](../../../tests/pipeline_eval/test_horizon_risk_budget.py) cover the wall-clock subtraction, median, unsplit ledger rows, profile caller and byte pins.

```sh
sudo -n -u leo python3 -BPs reports/ALGO08/v3/horizon_risk_budget.py
python3 -BPs -m unittest discover -s tests/pipeline_eval -p test_horizon_risk_budget.py
```
