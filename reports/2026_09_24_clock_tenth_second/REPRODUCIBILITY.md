# Reproducibility note

`results.json` binds the executed refinement source, protocol, unchanged parent
Engine source, and sealed parent inference. The parent inference in turn records
all twelve session cache and receipt hashes. The refinement instantiated that
same Engine and its run-time cohort checks, so cache provenance is transitive
through those two bound artifacts; no cache or receipt was regenerated.

Postexecution publication review independently hashed all twelve current cache
and receipt pairs and verified exact agreement with the sealed parent bindings.
It also verified the refinement result seal. This check is a postexecution
provenance audit, not a preexecution gate. Both refinement tests passed.

Run with one BLAS thread:

```text
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 .venv/bin/python reports/2026_09_24_clock_tenth_second/run.py
.venv/bin/python reports/2026_09_24_clock_tenth_second/plot.py
```

The exact result digest is recorded in `results.sha256`.
