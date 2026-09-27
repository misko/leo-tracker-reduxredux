# Legacy native-profile search result

## Decision

No tested proposal is ready for ARM promotion. Direct 512-bin seeding was fast
but retained only 1/6 blind-reference positives on development. Increasing the
timing grid retained 3/6 (`low`) and 4/6 (`high`); combining all three seeds did
not improve on 4/6. High-resolution seeding followed by blind search when the
seed did not gate retained every reference positive, but cost more than blind
search overall.

The validation configuration was frozen before validation as SHA-256
`22298a4d3f6c580bb163f310644e5a70e09f0587432ea9e5e9474a45d9f40df5`.
It contains the exact blind control and the only simple fallback candidate that
had complete development retention. Validation did not tune the configuration.

## Results

All retention figures use the strict current research gate
`fractional_complete && margin > 0.025`. A proposed positive must also match the
same selected 20-ms window, be within 8 kHz tracking CFO, and be within 2 us
circular fractional epoch. These are diagnostic associations against a blind
detector, not real-signal truth or calibrated classifier recall.

| Split / variant | Supported RX cases | Blind-positive retention | Median native CPU | Median wall |
| --- | ---: | ---: | ---: | ---: |
| Development blind | 32 | 6/6 | 1.236 ms | 1.308 ms |
| Development high seed + blind fallback | 32 | 6/6 | 2.099 ms | 2.251 ms |
| Validation blind | 32 | 12/12 | 1.135 ms | 1.208 ms |
| Validation high seed + blind fallback | 32 | 12/12 | 1.544 ms | 1.676 ms |

The validation candidate was about 36% slower by median native CPU and 39%
slower by median measured wall time. Its high-resolution seed gated on 12/32
receiver cases; the other 20 paid for a seed and then blind fallback. All 12
matched validation candidates had exactly equal persisted epoch, fractional
offset, tracking CFO, exact score, control score, and margin to the blind
control. This establishes within-build fallback fidelity on this small split,
but no compute benefit.

The existing binding processed only 2.5 and 5 MS/s. Every 7.5 and 10 MS/s case
is present in the receipt as unsupported: 16 real visits per evaluated split
and 12 synthetic-control visits, rather than being counted as negatives or
removed from the inventory.

The supported synthetic set has eight injected-pilot receiver cases and eight
each of constructed noise and tone. The blind profile recovered 3/8 injected
pilots with the required injected window/CFO/timing identity. The fallback also
recovered those same 3/8 and added no gates on supported noise or tone. The
controls were not retuned to raise recovery, and their expected detector
decision is deliberately unspecified. The unsupported high-rate controls do
not contribute to these denominators.

Development composite variants concatenate proposals from independent calls.
Their raw `additional_positive_candidates` field can count duplicate proposals
unless clustered. Selection here used reference retention, timing, and the
separate noise/tone gate counts. The frozen fallback never concatenates two
positive calls: it runs blind only when the seeded call has no positive gate.

## Profile and reproducibility

These results apply only to the legacy native-tone-CI16 research profile. They
must not be pooled with the decision-band worker's build, which enables several
additional numerical features and produces a different blind baseline.

- Dataset manifest: `ce3a22f10abefca4623affe006331b770dad5d3788d99aa44bdad93d2f75af48`
- Deployment source commit: `8803d6a7b2bab4b1945e447238a14b30a887695e`
- Native binary: `f9c346ad103c68e837f36d4db70e8250df4887496df90fc7eba725a3ff4f97ba`
- Native build receipt: `b48dda05e52614476bbc1c305d8084a5a61f235bbec54d6f019c35a278c30fff`
- Experiment script: `80dd3a94daf60f7362ba3e26bece8f7a0d21a471e3e6569191f8691ecbbb664b`
- Development config: `b1796bfb3d98d0687f3287134562fb96ea906a42078de68226aac002ab380ae9`
- Development results: `a84a45ba5842225821bc21ef4fce21c8a9449698bf0dd1bc4b3ed9c22c8d79f0`
- Control results: `e027830a30ec83c4e9fa93c656b6d962b6e4e95a2a439ddedaa3bbcfc878db18`
- Frozen validation config: `22298a4d3f6c580bb163f310644e5a70e09f0587432ea9e5e9474a45d9f40df5`
- Validation results: `cf9408e9072fed43771ae7c16974139713881bf640389bd1ae723532caeb3f55`

Each result contains raw per-case/repetition candidates, exact/control scores,
CPU/wall times, caller-IQ hashes, source hashes, compiler identity, build flags,
and explicit unsupported cases. One warmup preceded three timed repetitions;
candidate outputs had to be identical across the three runs. The component's
nine tests cover the strict gate, fractional circular identity, candidate-level
inventory, injected-pilot identity, split discipline, IQ hash/geometry, and
configuration freeze guard. The preliminary exposure to the superseded
format-only dataset manifest is recorded separately.

## Acquisition and causal tracking plan

The self-screened seed is useful for acquisition only when a blind fallback is
available; without fallback it loses references. A distinct tracking mode can
avoid repeating acquisition, but it needs a causal state contract that this
experiment did not implement or validate:

1. Acquire blind on the first visit for a `(session, channel, edge, receiver)`
   key. Cache only a gated candidate.
2. Convert its fractional epoch to absolute device-counter phase using the
   selected window offset, then propagate that phase to a later visit from its
   recorded start counter. Do not use a future visit or a retrospective oracle.
3. Confirm the predicted local epoch while retaining the full CFO search. A
   counter discontinuity, stale cache, geometry change, channel change, failed
   confirmation, or implausible CFO/timing motion triggers blind reacquisition.
4. Periodically force blind reacquisition because a wrong but gated seed would
   otherwise suppress fallback and poison subsequent state.

The eight-visit blocks contain some repeated channels, so a separately frozen
chronological experiment could test this state machine. It must start each
session and split with an empty cache and compare in common source-counter
coordinates. Same-dwell high-resolution seeding validated here is not evidence
that prior-visit tracking is accurate.

## Held-out command

The search worker did not open holdout IQ. Root can run the single authorized
legacy-profile holdout after serial timing conditions are available with the
unchanged script and configuration:

```sh
.venv/bin/python reports/2026_09_26_ds5_server_eval/search/run_experiment.py \
  --split holdout \
  --config reports/2026_09_26_ds5_server_eval/search/frozen_validation_config.json \
  --output reports/2026_09_26_ds5_server_eval/search/holdout_results.json \
  --authorize-holdout
```
