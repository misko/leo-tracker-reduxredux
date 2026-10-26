Completed development stage, no raw IQ or validation outcomes. Only r02/prediction/
is edited. Round1 is immutable. Read PROTOCOL.md for midpoint-effective timing
measurement convention and distinct legacy-adapter control; this assumption
requires independent review because actual pilot weighting can differ.

All 576 forecasts sealed before archived evaluation: 289 quadratic, 164 linear
fallback, 123 no donor. Six tests and all-cell fresh reproduction/redaction,
unchanged primary/CFO/native ownership and exact legacy-adapter parity pass.
Archived fixed CFO-only cohort 144: median|timing error| 5.608→0.229 samples;
within 2 samples 10→117; large identity tail persists and RMS slightly worsens.
See REPORT.md for interpretation and limited applicability to new admissions.

protocol SHA256: 77ba1b8f357ddbb900da0d965822aefbc484b1b936e31c00b24ea9329c326758
predictions SHA256: 2382b0ae3ac7c55400fdd3032dae628e042eba0edf437ad2da77800df5244f11
source SHA256: b1b49492a84c9d2e61c59c5416061540964f318c788d0f67871d9fe09c982c3d

Input is round1/prediction/prediction_packets.json, frozen source/primary/native
provenance. Output predictions.json.rows[*] has header,target_support,donors,
primary_hypothesis_id,status(quadratic/linear_fallback/no_donor),model and
methods={linear,quadratic_or_fallback,legacy_adapter_linear}. Each point has
epoch_samples relative to target origin, nominal-midpoint timing reference,
unchanged cfo_hz/cfo_rate_hz_s/reference, uncertainty, and origin/end model
epochs. model is evaluable at any counter with predictor.evaluate.

linear.epoch_samples exactly preserves round1 primary.full.epoch_samples.
legacy_adapter_linear exactly adds rate*0.010 like round1 timing adapter.
Their signed difference is explicit. The optional legacy descriptive control
must not silently enlarge an acceptance trial budget. Quadratic uses one fixed
primary branch and CFO, no timing search or target-selected alternative.
