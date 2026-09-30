# Does repeated-state averaging reveal additional information?

This follow-up to `WITHIN_VISIT.md` tests whether state-conditioned templates
predict held-out observations beyond the known analytical T-code waveform.
It uses existing paired DS10 caches and collects no new RF data.

## Fixed test

For each of the six cached visits, split jointly qualified frames chronologically
in half. Use early-half RX0 to estimate templates and late-half RX1 to evaluate
them. Identify states from symbols 194–225; require at least two training frames
per eligible state, two eligible states, and four training and test frames.
Keep only test frames whose state is eligible. No early test signs enter template
selection. State classification itself uses the existing two-receiver tail assay.

Only DS10-F010-v1085 meets these requirements: 16 classified training frames,
13 eligible test frames, and eligible states 28, 44, 52. The other five visits
abstain; a quality failure or insufficient repeated states is not negative
evidence about their message content.

For each frame and receiver independently, fit the analytical waveform's complex
gain on symbols 226–257. Subtract it and predict residual regions disjoint from
both state selection and gain fitting. Repeat with a single gain per frame and
with a gain per carrier. Do not divide by weak fitted gains.

The state template is the mean training residual for the target state. The global
baseline is the mean of all training residuals, including singleton states. The
reported reduction is `1 - state_template_MSE / global_template_MSE`; positive
values favor state conditioning. Zero prediction is a separate residual baseline.
199 deterministic training-label permutations preserve state counts and the
target set. They are descriptive controls, not independent-trial significance
tests. Different averaging sample sizes and time-varying channel errors limit
the interpretation of a negative result.

## Results

| OFDM symbols | Raw waveform: state over global MSE reduction | Residual: scalar gain | Residual: per-carrier gain |
|---|---:|---:|---:|
| 2–7 | −15.08% | −0.90% | −1.56% |
| 8–33 | +4.47% | −6.17% | −6.75% |
| 34–129 | +5.61% | −13.01% | −12.94% |
| 130–193 | +4.47% | −15.19% | −14.72% |
| 258–289 | +5.72% | −14.17% | −13.92% |

All residual regions favor the simpler global template over state-specific
templates in both gain models. Later residual state templates also lose to
predicting zero. Early residual templates improve over zero by 18–19%, but the
global template does better: this reflects common structure, not demonstrated
additional state-dependent data.

Some negative improvements exceed every shuffled-label result. That is **not**
successful additional decoding: beating random labels while losing to a simpler
baseline does not justify claiming new bits. Shared template subtraction and
state-dependent model errors also prevent interpreting a residual pattern as
message information without further validation.

This result supports the known T-code as the explanation for the observed later
state-conditioned repetition. It does not prove the absence of additional bits;
it rejects this unregularized averaging method as a demonstrated recovery method
on this held-out example. No satellite ID, position, time field, FEC, or CRC was
decoded in this experiment.

## Consequence for the investigation

The changing early signs still have the strongest direct evidence for information
beyond the known repeated pattern: matched receivers agree much more than
mismatched frames. The next useful test is per-frame receiver combining and
validation of early-sign structure using disjoint carriers or symbol subsets,
with fixed-template and sign-bias controls. Repeated-state averaging should not
be counted as additional information recovery on the evidence above.

## Reproduction and validation

Run `state_transfer.py` in an environment with NumPy and SciPy. Generated
`local/within-visit/state-transfer.json` records source cache and script hashes,
all frame/state selections, both gain models and all control summaries. Outputs
remain Git-ignored. Existing frozen manifests and prior analysis seals are
unchanged.

`test_state_transfer.py` verifies recovery of a synthetic state-dependent pattern
on new noisy samples and rejects a constant pattern as state information. Together
with `test_within_visit.py`, four tests pass. This is validation of the comparison
implementation, not proof of the interpretation of real RF signs.
