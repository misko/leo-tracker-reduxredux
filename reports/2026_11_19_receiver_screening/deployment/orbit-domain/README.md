# Causal orbit support at the initial search corners

The unchanged compact secant v5 worker failed during initial corner discovery on four complete DS26 recordings. The fresh-discovery interior call uses phases limited to ±15 seconds. At the corners, `discovery.explore` overwrites phases for its selected proposals and retains the previous Gaussian posterior for other active satellite rows. Those retained phases can extend beyond the ±17 seconds of nominal bank padding once the original 50 ms derivative stencil is included. Observation timestamps were inside their original scans.

## Original failure witnesses

All four failures follow `v5_core.ranked_initial_nodes → discovery.explore → ScanLikelihood.shifted → orbit_projector.prepare`. Each row gives the largest excursion of the first rejected projection. Range uses the bank endpoint state and its recorded regional screen centre. The light times show the physical scale of signal transit, and the failed queries are along-orbit phase hypotheses. The trace archive retains each offending stencil timestamp, NORAD, and complete causal TLE provenance, including element epoch, collection time and snapshot digest.

| Recording | NORAD | Bank support (s) | Observation (s) | Phase (s) | Queried state (s) | Excess (s) | UTC query (ns) | Approx. range (km) | Light time (ms) |
| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| DS26-0132 | 67049 | −17 to 317 | 0.010000 | −16.978008 | −17.018008 | 0.018008 | 1793061451573781077 | 2,219 | 7.402 |
| DS26-0156 | 67447 | −17 to 317 | 299.802336 | +19.116031 | 318.968367 | 1.968367 | 1793101571542136673 | 2,117 | 7.062 |
| DS26-0181 | 63324 | −17 to 318 | 300.036537 | +18.094089 | 318.180626 | 0.180626 | 1793148819792171571 | 656 | 2.187 |
| DS26-0281 | 63272 | −17 to 318 | 0.010000 | −18.639612 | −18.679612 | 1.679612 | 1793310710965431048 | 1,628 | 5.430 |

DS26-0285 and DS26-0289 separately hit the frozen `orbit_modes.previous_bank` line 44 `assert good.all()` while propagating previous TLEs at 0, 150 and 300 seconds. DS26-0285 reaches it during history family weighting. DS26-0289 reaches it during initial model construction. Their diagnostic returns identify the array validity assertion. They did not identify individual bad SGP4 status codes.

## Repair and evaluation

The variant supplies only missing integer-second interpolation knots for the initial `receiver_smooth` corner projection. It reuses the screened causal catalogue’s exact SGP4 objects in the bound row order and the scan’s nanosecond origin. The three-instant propagator input requirement is satisfied with up to two existing seam knots. The worker checks their state vectors for exact equality and discards those copies. Original observations, existing knots, derivative step, likelihood, optimizer and candidate budgets, and final selection remain the inputs to the same compact pipeline. The extension admits only finite phase shifts through ±30 seconds and times inside the original acquisition support. Other queries retain their original guards.

The first locked attempt exposed the frozen sampling-grid minimum before generating extra states. Its source and eight attempted results are retained under `sampling-grid-attempt/`, and the revised bridge was locked before position scoring. The unmodified compact archive remains the matched numerical control. `original-roles.json` checks the four capture-era role results against the original execution records. The staged and historical timings cover different versions and were collected under different host loads. The candidate’s support-only wall time excludes the failed attempt to construct the original interpolation stencil, while worker and case wall times include it.

## Both-arm results

All four recorded interpolation exceptions cleared. The unchanged family-history fit returned a failure on DS26-0181 and the worker withheld both endpoints. Three recordings that had failed on all four capture-era roles and compact secant now produced both endpoints. The remaining four controls used zero extra knots and matched compact secant exactly in all eight endpoints and conditional RF RMS values. The capture-era no-repair role published two of these four controls.

| Recording | `c = 0` error (km) | Fitted-`c` error (km) | `c = 0` conditional RF RMS (Hz) | Fitted-`c` conditional RF RMS (Hz) | Added knot times (s) |
| --- | ---: | ---: | ---: | ---: | --- |
| DS26-0132 | 0.559 | 0.651 | 76.544 | 76.510 | −18 |
| DS26-0156 | 1.405 | 1.508 | 54.539 | 54.506 | +318, +319 |
| DS26-0181 | Withheld | Withheld | — | — | +319 |
| DS26-0281 | 0.742 | 0.743 | 69.270 | 69.271 | −19, −18 |

Fitting `c` reduced conditional RF RMS by roughly 0.03 Hz on two recovering recordings and increased geographic error on all three. The sample is a retrospective recovery panel. The original compact solver provided no endpoint on these three recordings for a matched change in distance. The independent unchanged controls establish regression parity here. [Position errors with `c = 0`](position-errors-c0.png) · [Position errors with fitted `c`](position-errors-fitted_c.png) · [All paired outcomes](scores.csv)

For the four affected recordings, support work took 21–49 ms per recording. It evaluated 90–357 causal states including seam verification, retained 30–238 new states across calls and used up to 0.48 MiB for a single augmented bank. The complete eight attempts used 72–121 s wall, 56–78 s CPU, and 0.97–1.23 GiB peak child RSS per case. The repaired runs were 100–121 s wall. The original support failures ended at 30–54 s. These compare a finished or withheld fit with an early failure. Four controls took 58–81 s in the archived batch and 72–95 s wall in the fresh batch, with zero measured support work. Active test waves took roughly 7 min 18 s including the diagnostic and first bridge replays. End-to-end calendar time between the first diagnostic launch and last numerical receipt was 13 min 6 s including the source revision gaps.

## Reproduction

Run from the repository with the frozen v5 runtime and the authenticated compact-complement case cache. The earlier `compact_roof_selection prepare` regenerates that cache at the same recorded path if necessary. Use an unused local working directory.

```bash
nice -n 10 taskset -c 0-3 .venv/bin/python -B -m \
  tools.pipeline_eval.qualification.orbit_domain_trial replay \
  --cpus 0 1 2 3 --work /tmp/leo-orbit-domain-repeat
.venv/bin/python -m tools.pipeline_eval.qualification.orbit_domain_results publish \
  --work /tmp/leo-orbit-domain-repeat
.venv/bin/python -m tools.pipeline_eval.qualification.orbit_domain_results score
```
