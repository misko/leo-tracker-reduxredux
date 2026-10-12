# Full position comparison of retained clock seeds

This experiment moves the [seed-retention repair](../incumbent-clock/README.md)
from fixed-point frequency checks into the full B7 position pipeline. Numerical
execution has started; no new geographic improvement is established yet.

The [frozen protocol](protocol.json) retains the same eight development
recordings, original whole-recording roles, observation inventories, initial
catalogues and priors. It excludes the earlier data-selected points and runs
the original 400-point search and recovery policy. Four modes cross original
versus guarded joined bootstrap proposals with unconditioned versus conditioned
clock initialization. Every mode retains original and completed intermediate
seeds, with the existing five-second bootstrap allowance per search point.

DS20 runs both raw and fixed development-donor band corrections; DS16 runs raw
observations because these recordings have no high-band rows. The donor and
same-radio/time-invariance assumptions are inherited from the earlier experiment.
Raw persisted measurements and RF tags remain untouched. Candidate banks may
change across modes as a consequence of initialization and discovery.

Within each condition, c=0 and fitted-c final arms share observations, the final
candidate bank, priors and fitting budgets. Upstream discovery uses fitted c,
so this is a conditional final-stage ablation. Different accepted fallback stages
must be identified and compared at a common stage where available; an operational
fallback is not a controlled model comparison by itself. Frequency scores and
geographic errors will be reported separately after the numerical terminals are
sealed. Reference coordinates do not enter protocol creation or execution.

Workers run in bounded resumable slices of 30–600 seconds. Immutable, checksummed
checkpoints preserve completed work between slices; a yielded slice is not a
completed position search. Compact per-point bootstrap audits retain all events,
interruption status, selected catalogue order and seed vectors. Failed numerical
conditions stay explicit. The first condition is DS20
`fast-014c72ff95ab599c51ba3b3ec9b92cb8`, raw original-control.

Four tool checks verify original observation/RF identity, audit preservation,
whole-recording roles, exclusion of earlier selected points and refusal to replace
a frozen protocol. They pass in the scientific and publication checkouts, alongside
69 previously verified affected analysis/application checks. The frozen numerical
components, production defaults, golden fixtures and hardware remain unchanged.

Reproduce with the built native orbit extension, scientific release Python,
one BLAS thread and `PYTHONPATH=src:tools`:

```bash
python tools/full_incumbent_merge_study.py freeze
python tools/full_incumbent_merge_study.py execute \
  --dataset DS20 --session-id fast-014c72ff95ab599c51ba3b3ec9b92cb8 \
  --calibration raw --mode original-control --maximum-seconds 300
```

The protocol already exists in the executed scientific tree; resume with
`execute`, and do not repeat `freeze` there. The current panel is exposed
development evidence, not a fresh validation set or whole-corpus qualification.
Full DS20/DS16 geographic comparisons and the authoritative DS15 membership
remain outstanding. No new RF collection or QNAP write is required.
