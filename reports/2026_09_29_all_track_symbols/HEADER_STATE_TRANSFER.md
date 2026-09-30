# Can the known tail state predict the changing header?

A constrained learned mapping from the known repeating-pattern state predicts
held tail signs, including in another visit, but does not improve prediction of
the first six header symbols over a fixed per-coordinate majority. This helps
separate known-state redundancy from the early unknown structure. It does not
establish that the header is independent of the state, encrypted, or a particular
message format.

## Experiment

Use the original 24-data-carrier paired DS9-middle and DS9-last caches, with the
45 qualified, receiver-checked state labels per visit from the preceding
[constellation assay](RESIDUAL_CONSTELLATION.md). Verify the raw soft-cache hash
against that assay's receipt and verify its embedded inventory binding.

Train on RX0 in the first 22 eligible DS9-middle frames. Represent the known
state by its 60-element ±1 generator word, divided by sqrt(60). Predict each
coordinate's observed real sign using ridge regression with fixed penalty 1.0
and an unpenalized intercept. The coefficient fit centers features and targets
using training means only. No penalty, feature set, or polarity is selected on
evaluation outcomes.

Evaluate on RX1 in the remaining 23 middle frames, then all 45 last-visit frames.
Select coordinates whose positive-sign frequency is 20–80% on the training
receiver and frames only. There are 95 such header coordinates out of 144
(six symbols × 24 carriers). No evaluation confidence gate or agreement-based
coordinate selection is used. Predictors know the tail state, but never see the
evaluation header signs.

Repeat the same procedure as a positive control on six late symbols 272–277,
disjoint from the state-label selection window at 194–225. This independently
selects 103 variable tail coordinates. A majority baseline predicts each
coordinate's training-majority sign. Controls permute training state-feature
rows 199 times and refit the entire model while leaving outcomes and evaluation
states fixed. These are dependent descriptive controls, not a formal causal
test or a claim of untouched validation data.

## Results

| Region and evaluation | Decisions | Learned mapping | Majority baseline | Shuffled mapping 2.5–97.5% |
|---|---:|---:|---:|---:|
| Header 2–7, later middle frames | 2,185 | 54.55% | 56.16% | 51.99–55.97% |
| Header 2–7, last visit | 4,275 | 51.63% | 52.35% | 50.76–53.71% |
| Tail 272–277, later middle frames | 2,369 | 74.55% | 63.02% | 55.08–62.60% |
| Tail 272–277, last visit | 4,635 | 72.00% | 63.93% | 55.90–62.46% |

The header mapping is within the shuffled range and below its majority baseline
in both evaluations. The tail mapping exceeds every shuffled control in both
evaluations. Tail prediction also improves for states absent from training:
71.57% versus 64.70% majority in the middle visit; 69.75% versus 64.50% in the
last visit. Thus the positive-control result is not solely memorization of
repeated states. Detailed seen/unseen-state subdivisions are saved in the output.

These accuracies measure agreement with noisy RX1 signs, not transmitter bit
accuracy or successful payload decoding. The lower majority baseline of the
header's second-visit test also illustrates why simply counting agreement above
50% can be misleading.

## Interpretation

The limited-data mapping can recover known-state structure where it exists,
but it offers no validated header prediction here. A nonlinear dependence,
another hidden state, or a longer coded relationship remains possible. Twenty-two
training frames cannot rule out arbitrary functions of a 60-state label.
The findings support keeping symbols 2–7 as a separate unknown target rather
than labeling them with the tail's generator bits.

No new information bits, field semantics, satellite identity, timing, or orbit
data have been established. Both visits have been studied before, and no new
satellite association is inferred from these measurements.

## Reproduction

`header_state_transfer.py` saves frozen predictions, observed signs, selected
coordinates, frame/state labels, input/method hashes, and metrics under ignored
`local/header-state-transfer/`. It reads existing files only. Two synthetic
tests check transfer of a known linear relationship and preservation of a
training-only constant intercept. All 29 tests in the research folder and Ruff
checks pass. No recording, download, commit, or deployment was performed.
