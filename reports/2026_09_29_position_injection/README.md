# Conditional position perturbations are recovered to 9–67 m

**The full ambiguous geographic estimator responds correctly to these local 1 km position perturbations.** On the three balanced-N8 panels, recovered displacement differs from the injected displacement by 9–67 m, despite retaining free per-scan timing and all candidate/background alternatives. This supports local estimator sensitivity; it does not establish 9–67 m real-world location accuracy.

| Dataset | Injected displacement | Recovered east displacement | Recovered north displacement | Displacement recovery error | Largest timing adjustment |
|---|---|---:|---:|---:|---:|
| DS7 | +1 km east | 1,029 m | +9 m | 30 m | 12.9 ms |
| DS7 | +1 km north | −12 m | 1,046 m | 47 m | 8.4 ms |
| DS8 | +1 km east | 1,003 m | −8 m | 9 m | 5.0 ms |
| DS8 | +1 km north | −3 m | 1,012 m | 12 m | 2.5 ms |
| DS9 | +1 km east | 1,067 m | −3 m | 67 m | 12.2 ms |
| DS9 | +1 km north | +28 m | 1,032 m | 42 m | 7.4 ms |

The error column is the Euclidean E/N difference between recovered and injected displacement, relative to the original fitted endpoint. It is not distance to the operator reference. No operator reference coordinate is used anywhere in this experiment.

## What was injected

The [protocol](PROTOCOL.md) preceded execution. At the original qualified zero-height N8 endpoint, choose each track's highest training-posterior satellite component conditional on signal. For each observation, compute that candidate's predicted frequency difference after shifting the position by +1 km east or +1 km north, keeping original timing fixed. Add this difference to the original observed CFO.

This preserves the selected candidate's original residual exactly, including its track offset, while changing its geometric position contribution. The maximum observed residual-preservation discrepancy is 2.33e-10 Hz. Original arrays, masks, timestamps and candidate states remain unchanged; new documents carry the injected observations.

The refit does **not** receive the selected candidate as a fixed association. It uses the original mixture over all candidates and the linear-background component, with horizontal location and all eight scan timings free. Two fixed starts are used: the original endpoint and the injected endpoint. Select the highest qualified training score. No observation is filtered based on the outcome.

## Numerical and association checks

All 12 optimizer starts qualify, covering two directions on three datasets. Maximum finite-difference gradient discrepancy is 4.45e-6. Each dataset finishes in 17–21 seconds. Zero-injection identity is checked for every track; the original training score replays within 1e-7 before injection. Input artifacts and source hashes verify.

Conditional top-candidate changes after fitting are 3/476 and 4/476 tracks on DS7, 3/478 and 4/478 on DS8, and 8/489 and 9/489 on DS9 for east/north respectively. These counts include weak signal-responsibility tracks and do not establish true satellite identity. Candidate visibility is unchanged between original and injected endpoints during perturbation generation.

Two component-owned tests pass: zero-shift identity, exact selected-candidate residual preservation and original-input preservation; invalid displacement shape rejection. Every fit, generation candidate, signal responsibility and conditional probability is retained in the dataset JSON files.

## What this changes for the subkm effort

These conditional 1 km perturbations are not largely absorbed into timing, ignored by the geographic fit, or converted into kilometre-scale recovery errors. That makes an elementary local position-response failure less likely as the explanation for the existing kilometre-scale differences between scan panels. The result does not rule out other optimization basins, nonlinear behavior farther away, or misspecified real observations.

The generation is deliberately conditional on the fitted model. Every eligible track is perturbed using its training-selected candidate, even when its signal responsibility is low. Real background tracks do not necessarily transform this way, and an incorrectly associated satellite can still yield a self-consistent injection. The banks are site-conditioned; observations and panels have already been examined. This is a local response stress test, not an independent synthetic population with verified identities, a raw-IQ injection, or an absolute accuracy certificate.

Prioritize independently constrained physical inputs and evidence that discriminates wrong candidate associations. The measured height sensitivity remains relevant, and the antenna-elevation question remains open. This successful response test does not justify claiming the real data are localized to the recovery-error numbers above.

## Evidence and reproduction

[DS7.json](DS7.json), [DS8.json](DS8.json), and [DS9.json](DS9.json) store full starts, selected fits, displacement/timing response, candidate changes, per-track injection ledger and dependency hashes.

```sh
OPENBLAS_NUM_THREADS=1 uv run --no-project --with numpy --with scipy python -m unittest discover -s reports/2026_09_29_position_injection -p 'test_*.py'
OPENBLAS_NUM_THREADS=1 timeout 180 uv run --no-project --with numpy --with scipy python reports/2026_09_29_position_injection/run.py DS7
```

Repeat for DS8/DS9 in a fresh output context; writers use exclusive creation. `evidence.sha256` seals the local protocol, implementation, tests, report and numerical outputs. No RF collection, archive export, production edit or remote publication occurred. Reliable absolute subkm accuracy remains unverified.
