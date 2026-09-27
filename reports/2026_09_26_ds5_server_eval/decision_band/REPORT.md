# Decision-band development and validation report

The direct causal Q15 FIR followed by the 2.5 MS/s native GLRT is not an ARM
promotion candidate in this form. It passed synthetic fidelity controls, but
the frozen validation run retained only 1 of 8 native-5 MS/s reference-positive
receivers under the required same-observation-window identity rule. It was also
about 4.0 times slower than the native-5 MS/s comparator on this x86 server.

## Frozen method

- Source rate is reduced to 2.5 MS/s with a direct symmetric Kaiser 8.6 Q15
  FIR. Tap counts are 81, 121, and 161 at 5, 7.5, and 10 MS/s.
- Each filter has 40 decision samples of incomplete causal support, 20 decision
  samples of group delay, and another two samples excluded for fractional
  search. Timing is delay-corrected into source coordinates.
- One blind 512-bin whole-dwell confirmation uses the existing native GLRT.
  The primary positive rule is `candidate_count > 0`, fractional completion,
  valid support, and strict exact-minus-control margin greater than 0.025.
- A retained comparator positive also requires the same raw 20 ms observation
  window, tracking CFO within 8 kHz, and circular timing within 2 microseconds.
  Delay-corrected source windows are preserved as a diagnostic. A candidate in
  a different raw window remains a conservative loss even when periodic timing
  and CFO agree.
- CPU and wall timings include receiver materialization, filtering, support
  masking, screening, and one confirmation. Both receiver costs are summed per
  visit. Workspaces and buffers are warmed before three timed repetitions.

The native library was built from the adaptive-deploy
`runtime/scanner-glrt/algorithm.json` profile. Its scientific flags include
hybrid projection, symbol diversity, amplitude weighting, tone nuisance,
conditioned block rotation, and energy support. These results and timings must
not be compared as though they used the search worker's native profile.

## Evidence

| Split/rate | Reference positives | Retained | Candidate / baseline wall ms, both RX | Result |
|---|---:|---:|---:|---|
| development, 2.5M | 7 | 7 | 3.032 / 3.000 | identity control |
| development, 5M | 0 | 0 | 24.412 / 5.962 | no recall denominator |
| validation, 2.5M | 6 | 6 | 3.025 / 2.997 | identity control |
| validation, 5M | 8 | 1 | 24.244 / 6.115 | fails retention and compute |

Seven of the eight validation reference-positive 5 MS/s receivers selected a
different 20 ms window after reduction; one of those also had a large CFO
difference. This is a real failure under the preregistered identity rule, not a
pass-count substitution. The candidate produced seven positives, but positive
count alone does not establish retention.

All 16 synthetic known-pilot receivers were detected after reduction across
2.5, 5, 7.5, and 10 MS/s. Their maximum tracking-CFO error was 49.3 Hz and
maximum circular timing error was 0.130 microseconds; all used the injected
window. No synthetic noise or tone receiver was positive, and matched-rate
controls added no positives relative to their native comparator.

Validation throughput at rates without a matched native-rate oracle was 35.81
ms at 7.5 MS/s and 39.84 ms at 10 MS/s per dual-receiver visit. These are
filter-plus-detector timing/fidelity observations only. They support no recall
claim. No boundary-unsupported candidate occurred; incomplete fractional
confirmations remain explicitly counted rather than being hidden as positives.

The next bounded experiment should keep the same coefficients, support bounds,
and mapping while replacing the direct FIR with the existing FFT decimator or
an equivalent staged/polyphase implementation. The direct FIR result gives no
reason to expand a parameter sweep.

## Frozen receipts and final command

- Dataset: `ce3a22f10abefca4623affe006331b770dad5d3788d99aa44bdad93d2f75af48`
- Experiment source: `0bc89b294ea3b3389beec4a788fb0bc656c6d3e671e13cd0c81fd44159b204e6`
- Native library: `21b510afe862f09956a0e93ea7ba8b80066b90a14ffa26c5db12ebb79d7ca129`
- Frozen config: `ea074f61164bd9c6e5468671172b1a90dd58c0cf67f86044a48fd9729368ce66`
- Development receipt: `4f3a556ac8ec8eb232ba41ad2efa6abe5bf0f019ab4ea025e950dfa1c908a797`
- Control receipt: `843f82f44d2977813ded8c0036028260acde45335c5c4e2bfdf1144ef8cbf9ed`
- Validation receipt: `ca1dbfb9542a5344838d6dcbce3d995b59e9d20dbb12dd7f94cf8f783427e31e`

The authorized final evaluator can run the unchanged holdout path once:

```bash
.venv/bin/python reports/2026_09_26_ds5_server_eval/decision_band/decision_band.py evaluate \
  --dataset reports/2026_09_26_ds5_server_eval/dataset/cases.json \
  --split holdout \
  --config reports/2026_09_26_ds5_server_eval/decision_band/config.frozen.json \
  --reference-root /home/mouse9911/gits/leo-adaptive-position-deploy \
  --output reports/2026_09_26_ds5_server_eval/decision_band/holdout.json
```
