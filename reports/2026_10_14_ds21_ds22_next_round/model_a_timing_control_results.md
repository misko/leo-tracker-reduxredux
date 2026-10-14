# Model A: completed matched timing control on coverage 009/013

Locking high-stage satellite timings to the own low fit improves DS21-009 from
**3.155489 to 0.546915 km**, but slightly worsens DS21-013 from **1.509542 to
1.523394 km**. Neither treatment result reaches 0.5 km. This identifies a useful
stage dependence on 009, while rejecting the timing lock as a demonstrated
general solution or a release promotion. The full DS21+DS22 target remains open.

The source-qualified v2 matrices contain **24 sealed unit outcomes and 48
stationary scientific calls** across the two cases: 40 new calls and eight exact
saved-call recoveries. Both complete twelve-unit case matrices and their
training-objective selectors were sealed before the configured-reference join.
No reference, held observation or position error selected a proposal.

| Case | Original high repeat, final error km | Low-timing lock, final error km | Change km | Training-selected lock proposal |
|---|---:|---:|---:|---|
| DS21-009 | 3.155489 | 0.546915 | -2.608574 | shape-low, start 3 |
| DS21-013 | 1.509542 | 1.523394 | +0.013852 | cold-0, start 0 |

The two-case median changes from 2.332515 to 1.035154 km. This is a summary of
these two exposed development cases under one matched version, not a whole
dataset estimate, an independent-location validation, or a best-of-versions
selection. The historical shared-six 001/023/005/039 results and original fitted
009/013 comparisons remain separate. In particular, the original unmodified
discovery-policy 009 result of 0.658299 km is not mixed into this coverage table.

## Frequency fit and stage evidence

| Case / condition | Final training objective | Likelihood NLL | Conditional frequency RMS Hz | Fitted c Hz/GHz |
|---|---:|---:|---:|---:|
| 009 original high repeat | 34453.630816 | 34271.499506 | 91.621414 | -436.657687 |
| 009 low-timing lock | 33597.437736 | 33354.085883 | 91.872626 | -538.704363 |
| 013 original high repeat | 32661.799257 | 32253.204720 | 97.835399 | -730.616690 |
| 013 low-timing lock | 33259.603256 | 32841.980552 | 90.727146 | -537.452456 |

009 lowers objective by 856.193080 and NLL by 917.413623 while its conditional
RMS increases slightly. 013's RMS improves by 7.108253 Hz while its objective
increases by 597.803999, NLL increases by 588.775832, and position error worsens
by 13.852 m. Posterior assignment mass and conditional RMS need not track
mixture likelihood or position accuracy. These frequency measures are not
position confidence intervals and do not independently justify localization.

The selected 009 lock learns high offsets RX0 **-24121.509457 Hz**, RX1
**37418.149511 Hz**. Its low-to-final geographic displacement is 2.638195 km.
The selected 013 lock learns RX0 **-24048.529457 Hz**, RX1 **65937.329587 Hz**,
and moves 5.718846 km from its own low anchor. These are conditional learned
corrections, not independently measured hardware shifts or satellite identities.
Both selected final fits have false physical-boundary flags; their minimum
slacks are respectively 3.166157 and 0.047943. Those flags concern the original
timing/geography constraints and do not certify all coefficient bounds or a
globally correct geographic mode.

The high treatment changes one specified mechanism: it fixes the own low
common/relative timing vector when learning receiver offsets. The final model
still frees geography, common correction including fitted c, clock and timings
with those learned offsets fixed. Observations, randomized whole-group training
partition, candidate bank, original six proposals, physical donor functions,
priors and 25 km proposal domains are matched within each case. All scientific
calls retain fitted c and the original 20 s / 600-iteration allowance.
The experiment does not free final contrasts or introduce a calibration prior.

All **twelve repeated baseline final fits reproduce their original coverage
parent objective, full geographic/calibration/timing vector and nuisance vector
exactly**: maximum absolute difference is zero on both cases. This verifies
that the amended runtime did not change the tested baseline mathematics or seeds.
The fitted-c 0.546915 km result therefore comes from the declared timing-stage
intervention under matched coverage inputs, not a changed reference or baseline.

## Retained outer failures and corrected runtime

Four v1 outer attempts remain failed and unchanged: two NumPy receiver-tuple
serialization failures and two 90 s post-audit deadline failures. Their eight
high/final scientific calls had already completed stationarily. The separate
v2 recovery validates every original call triple and writes explicit
`recovered-metadata-only` outcomes with **zero** recovery predictor, objective
or optimizer calls. No saved fit was rerun or changed. The lost in-memory
projection/offset diagnostic fields remain explicitly unavailable.

The remaining twenty units completed without any new outer failure. Internal
unit times were **18.157–27.668 s** on 009 (mean **21.586750 s**) and
**18.374–28.766 s** on 013 (mean **22.016229 s**), including training preparation
and before/after authority checks. Summed saved fit times, including the reused
first-unit calls, are 24.929762 and 34.211631 s respectively; these have a
different scope from total orchestration wall time and are not added as new
work for the metadata recoveries.

The original zero-fit audit measured 21–29 s recursive parent reads plus
17–18 s training preparation. The qualified flat manifest preserves **419 live
source bindings, 5,054 authority files and ten case-specific semantic directory
inventories** per case. It rejects edited/missing bytes and added unpaired
authority files. Its real zero-fit before/after checks average **0.148322 s**.
Preparation measured 17.229883 / 17.395574 s and passed the declared 30 s bound;
the complete units retain 90 / 105 / 110 s internal / TERM / KILL bounds.
At most four explicitly named units ran concurrently, with single-threaded BLAS.

The [runtime amendment](model_a_runtime_amendment.md) records the failures,
profiles and source-qualified correction. Scientific implementation is
`116d71bfc`; the new runtime/manifest amendment is `3bfb9f646`. Fourteen new
runtime tests and the earlier thirty tests pass, including real synthetic
end-to-end scientific terminal writing, immutable authority/inventory checks,
wrong-low tampering, and recovery without numerical calls. No original runner,
scientific core, public contract, golden fixture, QNAP path or RF collection
changed.

## Evidence and next priority

The [compact machine-readable results](model_a_timing_control_results.json)
bind protocols, qualifications, every unit outcome, retained original failures,
aggregate seals and post-seal error joins, and retain all 24 unit training rows.
Raw immutable receipts remain under `local/model-a-timing-v2-009` and
`local/model-a-timing-v2-013`; failed v1 receipts remain in their original
`local/model-a-timing-009` / `013` namespaces.

| Case | Aggregate terminal SHA-256 | Post-seal evaluation SHA-256 |
|---|---|---|
| 009 | `1b3c7c437b6b4cdf6a74ece465ea0e8787f4795c00cb82ff6e2d6954e70976c0` | `fe5159db520a3c58e2b5dfec7ff781368384eef013bcbabb4172884bc9c7e070` |
| 013 | `1a9c9c8fa053ad07a6be45f2861b0dc3f6ea0229208926414ee76fd3f1411b1a` | `64fc27872c84871eba00b6ab8780b6cfcb8e9180cf26dd15445b0b1e7f8d1cb4` |

Do not tune this lock against these reference errors or choose it only for 009.
The current sequential experiment provides dependent shared-initialization
stages, not independent CH1–4 and CH5–8 end-to-end results. The next priority is
using the verified runtime correction to complete the uniform DS21 development
comparison and DS22 preparation, then rank failures within that completed
version. Any further scientific intervention must retain controlled candidates,
observations, priors and budgets and report position separately from frequency.
