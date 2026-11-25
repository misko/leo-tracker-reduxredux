# DS30-0218 saved replay coordinator

The coordinator uses the [registered field stage](masked-cfo-0218-readiness.md),
the [optional residual observer](masked-cfo-0218-owner-residuals.md) from
`116a98cc26915e095d11d79de6cc0facc0c13171`, and the existing scientific
scorer. Its ordinary and corrected workers use one verified original
detector packet, original live offer and original causal inventory. The
ordinary scientific parity gate compares the actual saved terminal and
publication to the completed field successor before corrected admission.

Once both original field rows are verified and the matched supplement is
approved, run from this checkout as `leo` with the installed release Python.
Use a fresh direct path below `/dev/shm` as `STAGE`. Keep both plan hashes
reported by `prepare-field`. The observer source SHA-256 is
`f6e912af1ed5e3fa4f82427569a195ca4b69110c839456cd0ca398363ea4b1c3`.

```bash
python -IB reports/ALGO08/v3/masked_cfo_0218.py status
python -IB reports/ALGO08/v3/masked_cfo_0218.py prepare-field "$STAGE"
python -IB reports/ALGO08/v3/masked_cfo_0218_capsule.py preflight "$STAGE" --cell ordinary --pin "$ORDINARY_PLAN" --observer-pin "$OBSERVER_SHA"
python -IB reports/ALGO08/v3/masked_cfo_0218_capsule.py preflight "$STAGE" --cell corrected --pin "$CORRECTED_PLAN" --observer-pin "$OBSERVER_SHA"
```

`preflight` imports the real installed saved worker inside the capsule
on CPU3. It opens only the exact staged scientific inputs. It binds the
declared source tree and runtime, tests descriptor inheritance via stdin
and namespace, then stops before Graph and solver execution. Retain both
returned `capsule-ready.json` digests. A development `probe` uses the
existing signed DS30-0019 fixture to exercise the same path before
DS30-0218 arrives.

```bash
python -IB reports/ALGO08/v3/masked_cfo_0218_capsule.py probe /dev/shm/NEW-0218-PROBE --observer-pin "$OBSERVER_SHA"
```

After separate consent for each CPU2 slot, use the live official campaign
PID. The controller and external readback run on CPU3. Only the numerical
child executes on CPU2. The following environment and priorities apply
to both watch invocations.

```bash
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 OMP_THREAD_LIMIT=1 MKL_NUM_THREADS=1 BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
taskset -c 3 nice -n 15 ionice -c 3 python -IB reports/ALGO08/v3/masked_cfo_0218_capsule.py watch "$STAGE" --cell ordinary --pin "$ORDINARY_READY" --driver-pid "$PID"
taskset -c 3 nice -n 15 ionice -c 3 python -IB reports/ALGO08/v3/masked_cfo_0218_capsule.py watch "$STAGE" --cell corrected --pin "$CORRECTED_READY" --ordinary-gate-pin "$ORDINARY_GATE" --driver-pid "$PID"
```

Each 120-second passive watch reads only official export updates. Admission
requires a signed fresh storage deferral, verified live retry driver at
idle, quiet read-only source filesystem, already resident operands, and
the nonblocking shared Gauss lease. The bounded numerical worker must
start with at least 26 seconds remaining and exits or is killed within
24 seconds. The controller passes the leased file descriptor as stdin and
the worker verifies its inode. The mounted original request metadata,
signed factors, TLE view and sources are read-only. Only that cell's
private tmpfs output and scratch are writable. The namespace and seccomp
filter deny backing archive aliases and network sockets. The official
raw driver's own storage guards still operate normally.

For each role, `clock.json` measures namespace launch through exit and
includes the optional residual export. The unchanged inner observation
witness reports the through-verified-publication clock. The residual
export also seals its own post-closure clock. The coordinator verifies
those artifact digests, the isolation proof and the binding to the
standard receipt before continuing. The ordinary watch returns the
digest of `ordinary-gate.json` after physical publication parity.
Use that digest as `ORDINARY_GATE`. The corrected watch seals
`verification-pins.json` for both cells and only then invokes the
held survey join through the existing scorer. Withholds and zero edits
are valid sealed outcomes. Failed admission or worker exit remains
visible and the coordinator gives no scientific score for it. A
launched cell cannot launch a second numerical child.

The final 0019 CPU3 proof is
`/dev/shm/leo-0218-capsule-probe03/probe/capsule-ready.json`, SHA-256
`d47747f16a8da1bd62d7a47a5bd3c6745e75aafb82606e414885832c5907e96d`.
It validated 66 explicitly mounted inputs, 47 exact staged TLE bodies,
the original worker and observer import, independent mount and network
namespaces, inherited stdin, read-only inputs, and five denied path
variants. IPv4, IPv6 and Unix sockets all returned `EPERM`. The no-fit
worker reported zero acquisition calls, waveform reads and solver runs.
The first no-fit attempt reached isolation and stopped on the installed
same-device check for `/dev/shm`; the final capsule binds a private
directory on the host tmpfs. Both official DS30-0218 rows were still
pending when this check was sealed.
