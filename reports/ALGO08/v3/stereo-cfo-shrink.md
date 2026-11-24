# Can the simultaneous radio measurements refine the short carrier estimates?

Use the original candidate receiver packet alone to shrink the difference between two measured short CFOs on the same visit. Keep their mean, both identities and both epochs. DS30-0049 is the development example. Test the rule unchanged on DS30-0019, 0274 and 0086, the three physical recordings used for the independent temporal interpolation comparison. No survey, orbit, solver or waveform enters this experiment.

Preserve the signed 20/8 cadence, full anchors and all empty lanes. Require both radios on the original edge, RF, channel and counter, with measured pilot epochs within the existing two-sample circular tolerance. Estimate RX1 minus RX0 offset with the existing causal stereo rule over the preceding twelve opportunities in that stream. Use zero when its three-witness rule abstains. Apply one quarter of the residual difference to RX0 and its negative to RX1 only if the residual magnitude is at most 250 Hz. Append the original witness after deciding. All visits use raw observations in history. The predicted changes are independent of Graph membership and installed outcomes. [Earlier stereo confirmation rule](short-stereo-evidence-protocol.md)

Seal candidate-only predictions before loading installed measurements. Score short factors against the same signed 20 ms receiver winner on the same radio, first with the original two-sample unwrapped epoch and 250 Hz raw-carrier cuts, then with the epoch cut alone. Include the unchanged observations and show separately how many proposed rows lack an installed match. For visits where both installed rows satisfy the same comparison, decompose the two residuals into their simultaneous mean and half-difference. Report how much squared disagreement even a perfect differential correction could remove while preserving the mean. Require at least 100 changed strict rows per held recording, improved RMS on every held recording and at least 5% lower pooled strict changed-row MAE to warrant a position experiment. A correction on these existing positives cannot recover an empty lane or materially reduce runtime by itself.

## Measured CFO agreement

The rule changed 629 of the 8,722 strictly matched short measurements on the three held recordings. Across all 8,722 the mean absolute difference from the 20 ms receiver fell from 83.86 to 83.69 Hz. Among changed rows the improvement was 2.9%, below the predeclared 5% requirement. DS30-0086 also missed the coverage and RMS requirements. This branch stops at the saved receiver comparison. [Sealed candidate predictions](measurements/stereo-cfo-shrink-plan.json.gz) · [Per-recording scores, enrollment and receiver identities](measurements/stereo-cfo-shrink-score.json)

| Recording | Strict rows changed | Mean absolute difference in Hz, before → after | RMS difference in Hz, before → after |
|---|---:|---:|---:|
| DS30-0049, development | 15 | 74.76 → 67.46 | 95.61 → 84.75 |
| DS30-0019, held | 119 | 84.48 → 81.46 | 107.83 → 102.00 |
| DS30-0274, held | 469 | 77.93 → 74.90 | 97.98 → 94.10 |
| DS30-0086, held | 41 | 99.89 → 107.43 | 116.06 → 127.35 |
| Held, pooled | 629 | 80.60 → 78.26 | 101.17 → 98.12 |

Every actual adjustment used a prior offset estimated from the original radio measurements. Of 678 proposed held rows, 49 lacked a strict installed match, including three with no installed winner. Dropping the raw 250 Hz selection cut while retaining the epoch cut admitted 658 proposed rows. Their MAE fell from 91.04 to 87.77 Hz, and the count above 250 Hz fell from 29 to 22. Under the strict cut, two previously in-range rows crossed above 250 Hz.

On the 292 changed held visits where both radios strictly matched the 20 ms receiver, **59.9% of the original squared discrepancy was in the pair mean**. Opposite signed adjustments keep that component exactly. Even knowing the two installed CFOs could remove at most the other 40.1% on those visits through this operation. The actual rule removed 7.9% of the total squared discrepancy on that subset. The epoch-only cut gave a similar 40.0% ceiling on 320 visits. Shared carrier drift, measurement noise and selection errors can all enter the common component. These comparisons use overlapping 8 and 20 ms samples at one site and do not establish absolute CFO or position accuracy. [Temporal interpolation comparison](track-cfo-denoise.md)

The protocol was fixed at `c4a0f1c02`; predictions were sealed at `ac08ef640`. Run `python -m reports.ALGO08.v3.stereo_cfo_shrink SNAPSHOT` on the pinned first-30 export to reproduce the candidate-only JSON. Score the uncompressed prediction with `--score-plan FILE --sha256 5e3db48aee20b8216603cf4e6be33de0697a3b98e89d49b02480def60ff2b76b`. The independent scoring step checked both published native identities, ordered stereo opportunities and common original recording authority. The development and held results used saved detector packets alone.
