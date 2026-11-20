# Composed compact secant with causal orbit and cavity guards

`v5_causal_orbit_fit.run(case, work_dir)` uses the normal complete frozen native v5 request, including the original 25 km roof tile and its causal TLE history. The worker wraps a single compact secant position run in the existing three serial guard contexts. It loads the same native factors once, uses the same graph, and leaves the initial ranking, five phase rounds, paired objective and final adoption code in the frozen numerical source.

- Corner support extends the original integer-second orbit lattice only when the compact discovery projection needs it. The original screened causal SGP4 rows, ordered bank and unchanged seam states remain the authority.
- The older-orbit guard handles an explicit code 6 on the previous-element alignment only after verifying the same NORAD’s current grid. Affected old rows use the existing missing-history prior. Other old and current states retain their original paths and checks.
- The corrected cavity guard isolates the recognized leave-family-out convergence failure. Surviving nominations still run the original proposals and selection. Publication of an incumbent after an optional family fails requires both arms to pass the original compatible-track, phase convergence, phase bounds and tile checks and have finite coordinate and RF receipts. The curved-only adapter supplies the exact last phase change from the original history record.

The composition binds each standalone source to its measured digest. The paired standalone series chooses the corresponding isolated repair for each diagnosed case. The two controls use the separately measured previous-orbit worker, which performed no old-state fallback on them. The archived cavity rows use matched native, catalogue, frozen request, tile and track configuration digests. Their original receipts lack a local case-cache digest. The comparison also includes unmodified compact secant and all four original capture-era outcomes.

## Numerical results

All ten workers returned. The composed receiver published seven paired positions and withheld three. Unmodified compact published two, and capture-era no-repair v5 published one. All eight diagnosed recordings failed in the unmodified compact archive and all four capture-era roles. The composition exactly matched the corresponding standalone status and reason on all ten cases and the coordinates and RF RMS on every published arm. Both controls also matched unmodified compact secant exactly. [Sealed scores](scores.csv) · [`c = 0` position distribution](position-errors-c0.png) · [Fitted `c` position distribution](position-errors-fitted_c.png)

| Recording | Composed result | `c = 0` error (km) | Fitted `c` error (km) | `c = 0` conditional RF RMS (Hz) | Fitted `c` conditional RF RMS (Hz) |
| --- | --- | ---: | ---: | ---: | ---: |
| DS26-0132 | Corner support | 0.559 | 0.651 | 76.544 | 76.510 |
| DS26-0156 | Corner support | 1.405 | 1.508 | 54.539 | 54.506 |
| DS26-0181 | Withheld after corner support, during family history | — | — | — | — |
| DS26-0191 | Withheld after 19 optional family rejections | — | — | — | — |
| DS26-0199 | Withheld after 4 optional family rejections | — | — | — | — |
| DS26-0281 | Corner support | 0.742 | 0.743 | 69.270 | 69.271 |
| DS26-0285 | Missing older orbit | 2.615 | 2.608 | 63.047 | 63.029 |
| DS26-0289 | Missing older orbit | 0.335 | 0.326 | 45.336 | 45.328 |

Both optional-cavity cases failed the original paired incumbent gate after finding no positive-gain replacement. Neither published a coordinate or RF residual. On the five recovered recordings, fitted `c` reduced conditional RF RMS on four, while geographic error decreased on two. Median error was 0.742 km with `c = 0` and 0.743 km with fitted `c` on this retrospective failure panel.

The four-lane replay took 211.4 seconds wall. Individual complete attempts used 47–128 seconds wall, 42–75 seconds CPU, and 0.97–1.21 GiB peak child RSS. Verified corner support took 13–49 ms for each of its four cases. The earlier-element retry took 2.01–2.39 seconds, including the original alignment work. The stage receipts include the cavity proposal cost and paired gate result. Historical standalone times came from separate runs and host loads.

## Reproduce the matched run

Use the existing authenticated compact-complement case cache. The earlier `compact_roof_selection prepare` regenerates that cache at its original path. These commands use a fresh output directory and already locked solver sources.

```bash
nice -n 10 taskset -c 0-3 .venv/bin/python -B -m \
  tools.pipeline_eval.qualification.causal_orbit_fit_trial replay \
  --work /tmp/leo-causal-orbit-fit-repeat
.venv/bin/python -m tools.pipeline_eval.qualification.causal_orbit_fit_results publish \
  --work /tmp/leo-causal-orbit-fit-repeat
.venv/bin/python -m tools.pipeline_eval.qualification.causal_orbit_fit_results score
```
