# Radio .20: native support loss and frozen-filter diagnosis

The saved 30/60-MS/s measurements point mainly to low normalized coherence,
not a large timing or carrier-prediction error. A model using the frozen FPGA
filters closely reproduces the measured reduction in matched energy between
the native and coarse paths. This is offline evidence from the preceding
[physical runs](2026_09_13_radio20_live_causal_feedback.md); no new RF was
collected and no runtime gate or controller behavior was changed.

## Timing and carrier refinement do not remove the support gap

All 360 rejected native measurements at 30 MS/s failed only the existing
coherence gate. Their reported local corrections, including supported heads,
range from −51.1 to +48.0 ns and −62.7 to +63.3 Hz. Substituting the reported
linearized coherence would increase the count above 0.05 from 149 to only 158
out of 509. This is a diagnostic comparison, not a proposed gate change.

At 60 MS/s, sixteen native heads failed only coherence; one also exceeded the
local timing bound. None of the seventeen heads reaches 0.05 even using its
reported linearized coherence.

The already-retained ±8-coarse-sample, four-phase timing search likewise makes
little difference to median coarse coherence: 0.07734 → 0.07752 on the 64
30-MS/s pairs and 0.06889 → 0.07019 on the seventeen 60-MS/s pairs. This
post-hoc coarse search cannot establish the optimum native timing, but it does
not support a large systematic source-coordinate error as the explanation for
these pairs.

## What the frozen filters predict

For each paired pilot, the diagnostic reconstructs the component represented
by the three native reference-space moments. It restores the recorded carrier,
applies the frozen two-stage DDC filters at their actual source rates and
absolute decimation phases, removes the declared group delay, and evaluates
the same coarse reference phase used by the paired review. No response gain is
fitted to the observed coarse measurements.

| Median matched-energy ratio, coarse/native | 30 MS/s, 64 pairs | 60 MS/s, 17 pairs |
| --- | ---: | ---: |
| Predicted from native projection and frozen filters | 0.7998 | 0.7805 |
| Observed on the paired measurements | 0.8149 | 0.7901 |
| Median observed/predicted ratio | 1.0180 | 1.0090 |

The preceding physical review measured median total-energy ratios of 0.5104
and 0.4851. Thus the coarse path removes proportionally more total energy than
matched energy, yielding the observed higher normalized coherence. The model's
agreement supports this filtering explanation; it does not show an arithmetic
failure in the native estimator.

Independent impulse tests verify the model's source-index and group-delay
alignment at both rates. A 400-kHz complex tone verifies the cascaded transfer
against direct evaluation of the frozen coefficients. Reference and input
hashes are retained with the results.

## Limits and consequences for the implementation

This is a floating linear-filter diagnostic. It excludes fixed-point rounding
and clipping, and native raw IQ is unavailable for these runs. In particular,
the native projection omits unknown signal/noise components orthogonal to its
three-column basis; filtering can change their contribution to the coarse
matched sum. Agreement within approximately one to two percent at the median
is therefore supporting evidence, not exact native-to-coarse reconstruction.
These are development recordings already inspected during implementation,
not held-out calibration data.

The result argues against trying to recover stable tracking merely by extending
the existing local timing/frequency refinement. It also provides no universal
coherence conversion factor or authority to lower the native gate. A different
native support policy would need separate signal and control validation.

Fresh coarse support is another possible input to a future tracking policy,
but the current interfaces do not support inserting it into a running native
controller. `glrt_tracking_trend_from_coarse` transfers startup history;
subsequent controller feedback is tied to retained native heads and their
chronology. Directly overwriting that history would discard the provenance and
horizon checks that the physical runs just verified.

The next implementation step to evaluate is a separately retained, passive
coarse observer during native operation, first on the existing corpus. It must
keep its own source association and history, remain bounded in CPU/storage,
and establish whether fresh supported coarse measurements actually persist
through native loss. Any later use of those observations for scheduling needs
an explicit causal fusion/retention policy and independent tests; the existing
native support decision must remain visible. Such a path would supplement
native tracking, not establish native precision or sustained native support by
itself. Autonomous LO revisits and refinement remain unfinished as well.

The [diagnostic results](figures/2026_09_13_radio20_native_filter_diagnosis/evidence.json)
include every paired comparison, correction summaries, input hashes and model
checks. The [diagnostic source](figures/2026_09_13_radio20_native_filter_diagnosis/diagnose_native_filter_transfer.py)
is retained alongside them. Original evidence remains beneath
`/srv/bulk/leo/glrt-deployment-20260909/radio20-iq-tracking-20260912/`.

