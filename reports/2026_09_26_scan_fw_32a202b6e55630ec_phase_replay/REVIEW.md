# Independent replay review

This is the coordinator's implementation review log. Findings below are gates
on interpretation, not conclusions about the radio signal. Final conclusions
belong in `REPORT.md` after the replacement runs and checks finish.

| Check | Finding | Required disposition |
| --- | --- | --- |
| Capture identity | The manifest envelope file hash differs from its canonical document digest. | Bind scientific inputs to canonical document digest `b381f62da5b5490e43790b69e2947919ad9fee6441b642ac04e7af1be487993a`; retain file hashes with explicit labels. |
| Time strata | Target-specific time bins would not represent the same session intervals. | Freeze shared session-counter bins, require complete dwell containment, and retain 32 development / 96 evaluation visits. |
| Direct IQ mixing | Averaging before removing the large receiver frequency difference can cancel the waveform. | Restore the absolute relative CFO sample by sample before integration; preserve the original zero-CFO baseline but reject its fitted efficacy scores. |
| Physical windows | The historical direct estimator used 32,768 native samples, not an arbitrary 1 ms window. | Compare at the actual 3.2768 ms native-rate support; label other windows separately. |
| Forward validation | A random-interior frequency/rate fit cannot become causal merely by refitting the intercept on the prefix. | Fit alias, frequency, rate, response, weights and intercept exclusively on each declared training support. |
| Qualification duration | A 20 ms probe cannot satisfy a historical 75 ms or minimum-20-frame qualification. | Treat dense 20 ms probes as acquisition seeds; evaluate duration gates on actual contiguous 50–120 ms support inside the dwell. |
| FFT interpretation | Full-bin FFT and direct products represent the same samples. | Verify Parseval parity; do not count equivalent formulations as independent corroboration. |
| Bandwidth comparison | Decimating independently centered raw receivers can preserve different physical RF bands. | Recenter before filtering, compare common physical support, and exclude FIR transients and any training/held support overlap. |
| Acquisition denominators | A complete below-threshold basin is different from a qualified acquisition. | Keep exploratory all-basin spectra separate from the frozen passing-candidate primary cohort; include failed visits in end-to-end denominators. |
| Phase meaning | Concentration is invariant to a fitted phase intercept; zero-centered error is not. | Distinguish raw phase, trained-intercept prediction, response-normalized phase, modulo-pi phase and timing phase. |

The scan audit found no matches to the tested embedded-counter signature. This
does not certify every possible RF defect or establish phase continuity through
retuning. Corrected acquisition, local tracking and cross-visit continuity each
require their own evidence.
