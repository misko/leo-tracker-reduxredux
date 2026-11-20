# Faster complete candidate selection on saved IQ

The row-wise peak selector reduced paired median CPU for the complete prepared capture detector by **17.9–19.8%** across four recordings. It preserved the full ordered public detector result and original native projection in **240 of 240** measured mode calls on 16 genuine dual windows. The fine FFT workspace experiment reached the same parity and delivered **−0.8% to +3.4%** paired median CPU savings by case. The complete replay candidate uses the row-wise selector and the original fine FFT. [Complete detector timing](stage.pdf) · [Per-call CPU and wall ranges](stage.csv) · [Candidate and gate audit](parity.json)

## The peak selector preserves the heap order

For each retained rank, `retained_peaks` finds the first eligible maximum in each CFO row. The first maximum resolves the original epoch tie within that row. Across the row maxima it uses the original score, absolute CFO, epoch, and discovery order. It removes the same circular epoch neighborhood and CFO neighbors before the next rank. The prepared grid still evaluates every original cell. No new native library or ABI is required. The implementation is 39 Python lines and 1,673 source bytes. [Selector source](../../../../tools/pipeline_eval/variants/prepared_hotpath_peaks.py) · [Selector protocol](SELECTOR.md)

| Saved capture | Prepared median CPU / wall (ms) | Row-wise median CPU / wall (ms) | Paired CPU savings | Paired time saved over existing vector selector |
|---|---:|---:|---:|---:|
| DS26-0237, legacy lower | 458 / 483 | 375 / 376 | 17.9% | 3.5 ms |
| DS29-0082, legacy upper | 584 / 593 | 476 / 478 | 18.1% | 3.7 ms |
| DS29-0174, screened upper | 361 / 361 | 288 / 289 | 18.9% | 6.4 ms |
| DS29-0519, screened lower | 363 / 366 | 291 / 292 | 19.8% | 7.0 ms |

Each case includes 20 measurements per mode across four genuine visits. The row-wise reduction saved 5.21 ms in the pooled paired median over the existing vectorized selector. It cleared the 5 ms preset by 0.21 ms. Individual paired differences ranged from −23.7 to +37.9 ms. The conservative performance conclusion is the gain from replacing the original heap. The smaller difference between vectorized selectors varies by case and repeat. The shared host was busy during both measurement series. The trial pinned each case to CPU 0 or 1, set one thread per numerical library, rotated mode order, and timed only resident saved CI16 through detector execution and probe projection. [Frozen selector inputs](selector-input-lock.json) · [CPU and wall medians and ranges](summary.json)

## Ordered candidate and gate evidence

The installed detector reproduced 32 authenticated probe rows. Across unique windows it returned 256 public candidates, including 49 integer gate positives. The projection contained 163 candidate records and 47 fractional gate positives. Each timed arm matched that complete public payload and projection. Single-lane positives exercised fallback searches. The four genuine negative visits stayed negative. The closest archived fractional margin to the 0.025 gate in the fixed panel was 0.00267 away. The smallest genuine gap between eligible coarse competitors was 3.70 × 10⁻⁶. The selector also matches the heap on a one-ULP separation, exact signed-CFO ties, and suppression across the circular epoch boundary in the component tests. [Parity and gap audit](parity.json) · [Component tests](../../../../tests/pipeline_eval/test_prepared_hotpath.py)

## Fine FFT workspace experiment

The separately instrumented producer runs confirmed that fine FFT scoring, the prepared folded grid, and heap selection consume most of the capture detector CPU. The installed heap took about 95 ms in the two warm profiles. The row-wise peak reduction took 8–11 ms. Conditioned CFO scoring used 45–47 ms, and integer and fractional GLRT together used 26–35 ms in the two row-wise profiles. The original received-energy prefix used 4–5 ms and probe projection took under 0.05 ms. Fine FFT preparation and transform costs varied across the instrumented passes. The chart shows the profile times separately from the uninstrumented five-repeat benchmark. [Profile chart](profile-stages.pdf) · [Stage counts and clocks](profiles.json)

The fine experiment assembled the same 44-sample pilot views with reusable binary64 FFT inputs and outputs. Its 11,184,000 bytes of explicit buffers and 93 Python lines delivered marginal complete detector savings. The fine-buffer-only CPU result regressed slightly on DS26-0237, and its gain elsewhere fell short of the planned threshold. The composition with the existing vector selector improved 14.0–18.4% in its own series. The isolated selector series establishes which change accounted for the material gain. [Fine workspace protocol](PROTOCOL.md) · [Frozen fine trial inputs](fine-input-lock.json)

## Run the selected detector

Run inside the installed capture producer and open one selector patch per dedicated replay worker. The existing prepared worker owns archive authentication, the full FFT grid, and both refiners.

```python
from unittest.mock import patch

from leo.analysis.starlink import acquisition
from tools.pipeline_eval.qualification import prepared_capture_waveform
from tools.pipeline_eval.variants.prepared_hotpath_peaks import retained_peaks

with patch.object(acquisition, "_retain_score_map_peaks", retained_peaks):
    prepared_capture_waveform.raw(work, cpu)
```

The measurements here cover host detector time and complete emitted support. The whole-recording replay and position comparison are separate. [Detector report seal](qualification-lock.json)
