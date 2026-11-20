# Using the missing-history prior for an isolated older-orbit decay

The two compact secant assertions on DS26-0285 and DS26-0289 came from SGP4 code 6 for one older record, NORAD 63012 (`STARLINK-11449`). Both recordings used the same earlier TLE epoch `1793158060207104000`, collected at `1793297047368813889`, from snapshot `91362ddd01a725beeb7c70d3ee72eb8f34d3c58698d97a8637e1d351f928862f`. The old model predicts decay at every alignment sample. Both current causal records propagate successfully at every knot of their original padded grids.

| Case | Stage | Alignment UTC in ns | Older codes | Current snapshot SHA-256 | Current codes |
| --- | --- | --- | --- | --- | --- |
| DS26-0285 | Family-history weighting | `1793317964307524544`, `1793318114307524544`, `1793318264307524544` | 6, 6, 6 | `77c5128479abaf874fab7032806458c6777c4ddf5e0d406e375f948e2f388009` | 0, 0, 0 |
| DS26-0289 | Initial discovery likelihood | `1793323997824974461`, `1793324147824974461`, `1793324297824974461` | 6, 6, 6 | `18d05009335ad8443af55a31b10f231a6af7763662a0c3cfa9aa7f415b57285a` | 0, 0, 0 |

The worker rechecks the specific failed alignment and validates the corresponding current orbit across its full original padded grid. It retries the frozen previous-bank routine with only the unusable old row hidden from its parsed history view. The original historical text and digest are still verified. The current orbit stays eligible for candidate selection and uses the existing one-second missing-history phase width and default physical orbital uncertainty. All valid older records pass through the frozen evaluator in their original order. The repair covers the three existing alignment instants and leaves the padding checks in force. A synthetic fixture with an actual SGP4 code 6 on a checksum-valid current record failed closed, and a valid neighbouring prior matched its independently evaluated history exactly.

## Matched numerical results

Both affected recordings obtained paired endpoints after the guard. Unmodified compact secant failed on both, and all four matched capture-era v5 options failed on both. The two controls published unchanged compact positions and conditional RF RMS in all four paired arms. Only DS26-0126 published in the archived capture-era no-repair role, at 1.860 km with `c = 0` and 1.813 km with fitted `c`. This variant was run independently of the prior orbit-domain interpolation extension.

| Recording | `c = 0` error (km) | Fitted `c` error (km) | `c = 0` conditional RF RMS (Hz) | Fitted `c` conditional RF RMS (Hz) |
| --- | ---: | ---: | ---: | ---: |
| DS26-0285 | 2.615 | 2.608 | 63.047 | 63.029 |
| DS26-0289 | 0.335 | 0.326 | 45.336 | 45.328 |

The calibration change reduced geographic error by about 8 and 9 metres and conditional RF RMS by 0.017 and 0.008 Hz respectively. These are two retrospective recovered recordings. [Scores and original outcomes](scores.csv) · [`c = 0` distribution](position-errors-c0.png) · [Fitted `c` distribution](position-errors-fitted_c.png)

The four fresh attempts took 56–63 seconds wall, 45–57 seconds CPU and 1.02–1.22 GiB peak child RSS per case. On affected recordings, explicit status and current-grid verification took 2.2–2.9 ms and the frozen retry took 2.04–2.08 seconds, including the legitimate alignment work that the failed first call could not complete. DS26-0285 retained all 1,371 other histories in its retry. DS26-0289 retained 21 in its first affected alignment and 1,470 in the later full alignment. The two controls performed no retries. The diagnostic and candidate waves took about 98 seconds of active wall and 4 minutes 16 seconds from initial diagnostic launch through the final numerical receipt.

## Reproduce the matched benchmark

Use the authenticated compact-complement case cache and the frozen runtime. The earlier `compact_roof_selection prepare` regenerates the cache at its original path. These report builders load original diagnostic receipts, while the existing sealed archive can be used to reproduce the scores and charts directly.

```bash
nice -n 10 taskset -c 0-3 .venv/bin/python -B -m \
  tools.pipeline_eval.qualification.previous_orbit_trial replay \
  --work /tmp/leo-previous-orbit-repeat
.venv/bin/python -m tools.pipeline_eval.qualification.previous_orbit_results publish \
  --work /tmp/leo-previous-orbit-repeat
.venv/bin/python -m tools.pipeline_eval.qualification.previous_orbit_results score
```
