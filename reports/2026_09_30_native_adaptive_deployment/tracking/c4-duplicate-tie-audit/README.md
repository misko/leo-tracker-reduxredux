# C4 duplicate-rank identity audit

This is a read-only numerical audit of the six candidate and tracklet identity
differences already recorded in `../comparison.json` and `../e2-pipeline.json`.
It changes neither production tracking nor a scientific fixture. It does not
close exact-v1 identity parity.

## Cause

The server and native implementations use the same per-source selection key:
largest evidence weight, then smallest absolute fitted residual, then candidate
ID. The relevant server code is `_one_per_time` in maintained
`leo/analysis/cfo_lines.py`; the native equivalent is `one_per_source` in
`native/adaptive/tracking/tracking.cpp`.

All six differing source groups contain two alternatives with exactly equal
weights at that comparison. Two pairs have identical score inputs, and four
pairs reach the common weight cap of 16. Their raw CFOs differ by only one or
two binary64 ULPs, `5.820766091346741e-11` or
`1.1641532182693481e-10 Hz`. Three frozen server choices are source candidate
rank 0 and three are rank 1, so neither rank nor candidate-ID order reproduces
the existing choices.

The arithmetic difference enters the four repeated line-fit iterations. The
reviewed server oracle builds a centered, square-root-weighted two-column design and calls
`numpy.linalg.lstsq`; this environment dispatches to OpenBLAS DGELSD. The
native implementation solves weighted normal equations in a fixed scalar
order. The final-model diagnostic shows each competing absolute residual equal
or separated by one ULP. The initial and refined per-source selections can
therefore choose opposite candidate IDs even though source membership, time,
CFO, alias and physical track membership remain the same.

| Native track | Source suffix | Native rank | Server rank | Raw CFO delta, native-server (Hz) |
|---:|---|---:|---:|---:|
| 7 | `f2c1c196` | 0 | 1 | `+1.1641532182693481e-10` |
| 9 | `e2288b7d` | 1 | 0 | `-5.820766091346741e-11` |
| 12 | `ad5c37f2` | 1 | 0 | `+5.820766091346741e-11` |
| 23 | `3be01a4e` | 0 | 1 | `+5.820766091346741e-11` |
| 28 | `ff42e2ff` | 0 | 1 | `-5.820766091346741e-11` |
| 49 | `67b99489` | 1 | 0 | `+1.1641532182693481e-10` |

`mismatches.json` retains the complete IDs, score inputs, weights, sibling
candidates and CFO values. `residual-diagnostics.txt` retains the fitted-model
residual comparison.

## Bounded solver substitution

Each solver experiment reconstructs the complete 11,747-candidate fixture and
compares all selected candidate IDs with the frozen 64-track server oracle.
Every variant retained 64 tracks and had zero source-membership mismatches.

| Fit used inside the Python server pipeline | Candidate-ID mismatches |
|---|---:|
| NumPy DGELSD (`numpy.linalg.lstsq`) | 0 |
| SciPy DGELSD | 0 |
| SciPy GELSS | 3 |
| SciPy GELSY | 4 |
| Python ordered normal equations | 10 |
| Python normal equations with `math.fsum` | 5 |
| Python centered covariance with `math.fsum` | 6 |
| Python modified Gram-Schmidt with `math.fsum` | 8 |

The Python normal-equation result of 10 is deliberately **not** called the
native result. Those substitutions replace only `_fit_alias_line` while
retaining the server's NumPy weighted-mean, modulo, vector residual and
aggregate operations. The actual portable native executable differs in six
rows and is bound by `native-tracks.tsv` plus `mismatches.json`. The substitution
experiment isolates sensitivity to a solver choice; it is not a C++ emulator.

Changing even the LAPACK driver moves the selected duplicate sources. A custom
two-column solver can be mathematically sound without reproducing historical
one-ULP OpenBLAS choices. Exact frozen-v1 compatibility would require the
pinned DGELSD numerical path and matching surrounding NumPy arithmetic, or a
bit-level emulation qualified on every architecture. That is not a lean
portable dependency.

The bounded portability addendum binds that conclusion to the actual numerical
geometry and binary rather than treating DGELSD as an abstract two-column SVD.
The six final fits have 42, 60, 66, 75, 83 and 86 rows, two columns and one
right-hand side, and the server performs four refits. The pinned one-thread
NumPy OpenBLAS DSO is an x86-64 Haswell build with SHA-256
`05c9f9eb89ee68a4b9d673184fa91c99587e736392c0c2d49180a8aa5303d080`.
Its `scipy_dgelsd_64_` binary calls the LAPACK path components `ILAENV`,
`DGEQRF`, `DORMQR`, `DGEBRD`, `DORMBR` and `DLALSD`; the ARM Buildroot sysroot
contains no LAPACK or OpenBLAS library. A small analytic 2-by-2 SVD would omit
the row-wise QR and orthogonal-transform arithmetic whose rounding participates
in these one-ULP choices. The audit therefore records a lean exact-equivalent
solver as unsupported by the evidence, not mathematically impossible. No new
solver experiment was run: the retained DGELSD/GELSS/GELSY and portable-solver
matrix already distinguishes the relevant behaviors, while another call to the
same pinned DSO would merely repeat the oracle. See
`dgelsd-portability-addendum.json` for the inspected call inventory and exact
qualification boundary.

The smallest scientifically general portable option is a new, versioned tie
policy shared by server and native implementations: treat residuals within an
explicit scale-aware binary64 tolerance, far below the measurement uncertainty,
as equivalent and then select by canonical candidate ID. It would eliminate
solver-dependent hashes, but it would intentionally change some frozen v1
tracklet identities, partition seeds and masks. It therefore needs a new
algorithm/config digest and explicit golden review. It cannot be presented as
exact-v1 closure.

## Reproduction

Run from the repository root. Each complete solver command took under one
minute on the recorded host.

```sh
python3 reports/2026_09_30_native_adaptive_deployment/tracking/c4-duplicate-tie-audit/mismatch_inventory.py \
  > reports/2026_09_30_native_adaptive_deployment/tracking/c4-duplicate-tie-audit/mismatches.json

python3 reports/2026_09_30_native_adaptive_deployment/tracking/c4-duplicate-tie-audit/residual_diagnostics.py \
  > reports/2026_09_30_native_adaptive_deployment/tracking/c4-duplicate-tie-audit/residual-diagnostics.txt

LEO_C4_ORACLE_SOURCE=/var/tmp/leo-arm-realtime-publication/src \
OPENBLAS_NUM_THREADS=1 /var/tmp/leo-arm-realtime-publication/.venv/bin/python \
  reports/2026_09_30_native_adaptive_deployment/tracking/c4-duplicate-tie-audit/solver_experiment.py \
  > reports/2026_09_30_native_adaptive_deployment/tracking/c4-duplicate-tie-audit/solver-experiment.jsonl

LEO_C4_ORACLE_SOURCE=/var/tmp/leo-arm-realtime-publication/src \
OPENBLAS_NUM_THREADS=1 /var/tmp/leo-arm-realtime-publication/.venv/bin/python \
  reports/2026_09_30_native_adaptive_deployment/tracking/c4-duplicate-tie-audit/lapack_driver_experiment.py \
  > reports/2026_09_30_native_adaptive_deployment/tracking/c4-duplicate-tie-audit/lapack-driver-experiment.jsonl
```

The experiment actually imported
`/var/tmp/leo-arm-realtime-publication/src/leo/analysis/cfo_lines.py`, SHA-256
`e7fe080db15ce17e183d12582bad8e638f5fca973f9cefb26e88c0bfc938c7ea`.
That reviewed source includes source-group deduplication used by the frozen
oracle. The similarly named workspace reference file has SHA-256
`ea2861d5ec9ead85a64f0a01959c0e1a9c31008e413fa1b922751e8a44175f3e`
and is **not** the imported oracle: it groups only by rounded time and lacks the
source-group field.

`executed-solver-experiment.py` and
`executed-lapack-driver-experiment.py` preserve the exact scripts that produced
the retained raw JSONL. They hardcode that same reviewed source location. The
unprefixed reproduction scripts require `LEO_C4_ORACLE_SOURCE`, verify the
`cfo_lines.py` hash above and verify the imported module path before running;
their numerical body is otherwise unchanged. This prevents a silent rerun
against the different workspace source or a later server checkout.

The maintained server source is used only as a numerical oracle. It is not a
native runtime dependency.
