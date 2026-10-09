# Explicit entrypoints; not yet executed or frozen

[entrypoint.py](entrypoint.py) supplies two commands. Neither prepares a protocol,
chooses recordings, retries an incomplete claim, or launches a worker implicitly.
The pilot remains the single consumed DS18-022 recording. The numerical queue
remains under parent control; no reconstruction, preflight, run or freeze was
performed while preparing these commands.

## Preflight

After independent review, prepare a metadata-only specification with
`freeze.prepare_plan(document_path, imports_path, None, preflight_only=True)`.
This includes every iteration116 Python source (therefore the entrypoint and
its tests), the inherited dependency closure, sanitized document and exact
original-coarse bundle. Publish that specification explicitly before any
reconstruction. It contains no fabricated observation/bank array hashes.

When capacity and authorization permit:

```bash
PYTHONPATH=src:. OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  /path/to/production/python reports/2026_10_09_position_error_iter116/entrypoint.py \
  preflight --protocol reports/2026_10_09_position_error_iter116/preflight-plan.json \
  --output reports/2026_10_09_position_error_iter116/preflight
```

Preflight verifies all declared source/input hashes and the loader/document
bindings, then creates an exclusive immutable claim **before** importing the
corpus loader. It uses `BoundCorpusLoader` with immutable105's verified
`load_case` over the sanitized107 document. The output records full-array
identities, input/evidence identities, counts, Python/NumPy versions and elapsed
time including loader import, public input preparation, orbit-bank reconstruction
and hashing. It does not call a likelihood or fitter. This reconstruction has
the existing bank builder's bound; it is not claimed to have a hard overall
preflight wall-clock deadline.

A successful or failed terminal receipt is reused exactly. A claim without a
terminal receipt blocks another invocation; there is no automatic crash retry.
Source changes, wrong session or loader, and stale bindings fail before loading.

## One resumable search slice

After the successful preflight, `freeze.plan_from_preflight` verifies that the
current preflight specification digest still matches the receipt, builds the
search plan and binds that receipt as an immutable input. It also records the
preflight runtime versions. Review and explicitly publish the final protocol
before running:

```bash
PYTHONPATH=src:. OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  /path/to/production/python reports/2026_10_09_position_error_iter116/entrypoint.py \
  run --protocol reports/2026_10_09_position_error_iter116/protocol.json \
  --output reports/2026_10_09_position_error_iter116/results/DS18-022
```

Each invocation validates the protocol/runtime and delegates **one** slice to
the existing durable driver. Loader import and reconstruction occur inside that
slice's claim/accounting. A pending result allows a deliberate later invocation
with the same protocol and directory. The twelve total claimed-slice cap and
persisted cumulative elapsed accounting never reset between invocations.
There is no shell retry loop or automatic follow-up worker. Failed, incomplete
or budget-exhausted terminal outcomes return a nonzero exit status and retain
their receipts; claimed crashes require explicit investigation.

## Preparation checks

The synthetic tests verify exclusive preflight claims, immutable identity/cost
receipts, source mismatches before work, no crash/failure retry, and CLI delegation
to one slice without eager loading. An isolated production-Python smoke check
imported immutable105's loader successfully **without invoking it**. No actual
preflight specification, reconstruction result or search protocol was written.
Recordings and positions remain untouched by this entrypoint preparation.
