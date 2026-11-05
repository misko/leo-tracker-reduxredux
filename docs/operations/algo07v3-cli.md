# Standalone ALGO07v3 run and publication recovery

Current qualification: [all 17 mapped scientific audit sections](../../reports/2026_11_05_algo07v3_factor_reuse/README.md)
match on DS26-0002, including explicitly accounted original-worker context
construction counters. This does not qualify other scans, ordinary admission
or excluded operational metadata. The factorization prototypes remain external;
the owned CLI continues to use its previously integrated numerical kernel.

The owned command is `leo-algo07v3` after installing this checkout, or
`PYTHONPATH=src python -B -m leo.cli.algo07v3` from its root. It starts one owned
worker. It does not invoke earlier ALGO executables or consume their results.
Fresh runs now execute each initial branch's independent c=0 and fitted-c fits
in two owned child processes. The parent returns their results in the original
order; branch selection, phase rounds, budgets and zero-phase controls are
unchanged. Direct numerical calls remain serial unless supplied the execution
port. The request schema and published contracts are unchanged.
Ordinary predictive annotation also executes its at-most-three predeclared
randomized grouped folds in owned child processes and merges complete results
in the original seed order. Targets, inclusion trials and adoption remain
sequential. Numerical replays with mutable policy receipts and calls with a
proposal callback keep serial execution. Initial-arm and fold concurrency do
not overlap: at most three fit children are active, each with one BLAS thread
and the job's inherited CPU affinity. Failed or interrupted children abort the
stage and are reaped; incomplete folds cannot become scientific rejections.

The command is currently qualified for **validation-all-work** only. It is not a
deployed service or a claim of equivalence to production wall-clock admission.

## Run

```sh
PYTHONPATH=src python -B -m leo.cli.algo07v3 run \
  --request /absolute/path/request.json \
  --work-dir /absolute/path/fresh-attempt \
  --timeout 1200
```

Each attempt directory must be new. It contains the frozen request, launch
description, streamed stage log, worker outcome and supervisor receipt. The
separate `output_root` holds the owned scientific archive and public artifacts.
An existing committed scientific result with the same request is reused; the
command never overwrites it with a newly fitted result. A different request for
the same run fails. A committed receipt with a missing or corrupt archive fails
rather than silently starting another fit.

Requests contain these exact version-one fields:

| Field | Meaning |
| --- | --- |
| `schema_version` | `1` |
| `execution_policy` | `"validation-all-work"` |
| `identity` | `run_id`, `session_id`, tagged `input_sha256` |
| `native_input` | Absolute `path` and tagged `sha256` of native GLRT JSON |
| `track_config` | Absolute `path` and tagged `sha256` of JSON containing `config` |
| `tle_root` | Absolute causal archive root supplied to the public archive reader |
| `output_root` | Absolute local output root, outside QNAP |
| `search_center` | `[37.906, -122.545]`, the current published 25 × 25 km frame |
| `screen_center` | Explicit two-element latitude/longitude screening center |
| `scan_identities` | Unique identities including `identity.session_id` |
| `title` | Recording title used by the renderer |
| `evaluation_reference` | `null`, or presentation-only `latitude_deg`/`longitude_deg` |
| `runtime` | Exact installed versions of `python`, `numpy`, `scipy`, `sgp4`, `matplotlib`, `pillow` |

`leo.operations.localization_v3_job.runtime_versions()` reports the runtime
pins. Freeze these in the request before comparing runs; do not change them to
make a mismatched runtime pass. Input and configuration bytes are checked before
inference and again before committing evidence. The full configuration, request
digest, runtime versions and loaded owned source hashes are saved in provenance.
The archive reader and preparation retain the causal catalogue evidence.

The current figure contract fixes the regional frame; this command does not
introduce a new location-specific fitting prior. Evaluation coordinates are
passed only to rendering/publication and do not enter fitting or association.

## Recovery without refitting

```sh
PYTHONPATH=src python -B -m leo.cli.algo07v3 resume \
  --request /absolute/path/request.json \
  --work-dir /absolute/path/fresh-resume-attempt \
  --timeout 1200
```

`resume` requires an already committed scientific archive. It verifies the same
identity and request, then publishes its saved PNGs and sidecars through the
existing public port. It needs neither native GLRT bytes nor the TLE archive and
does not rerun rendering or inference. This supports interruption after the
scientific commit, including partial UI publication. It does not restart a
partially completed optimizer. Repeated publication preserves content digests.

## Limits and cancellation

This execution adapter uses Linux/POSIX process groups and signal timers. The
supervisor pins BLAS thread counts to one and enforces `--timeout` over the child
process, including its imports, numerical work and publication. Accepted limits
are positive and at most 7,200 seconds. The default is 1,200 seconds.

The pair adapter uses Linux `fork` from a single Python-thread owner. It shares
the scan copy-on-write and inherits the worker's CPU affinity; it does not expand
that CPU allowance. At most two numerical children run for an initial pair.
Successful fits wait for normal worker exit under the existing job/stage deadline,
without a new short completion cutoff. A child crash, serialization error or
incomplete result aborts the job and cannot become a scientific rejection.
Parent interruption terminates, kills if necessary and reaps both children.

On timeout the supervisor sends termination to the entire worker process group, waits up to
two seconds, then kills remaining descendants and reaps the direct child. A
timeout returns exit code 124. Parent cancellation cleans up the same group and
returns 130. SIGKILL of the supervisor itself is outside this adapter's cleanup
guarantee; a service manager should own the process group/cgroup in deployment.

Gap stages retain their supplied stage caps. Their Python-level timer raises a
dedicated `BaseException` so a cancellation cannot become an ordinary scientific
rejection/fallback. Native code can defer Python signal handling; the process
supervisor supplies the hard outer limit. An interrupted job is not reported as
complete. If cancellation races a finished commit, the attempt can report
interruption while durable evidence exists; use `resume` to verify and reconcile
that state.

The all-work policy admits the validation discovery work without the older
ALGO03 elapsed-time admission cutoff. It retains the numerical budgets, stopping
rules and existing inner limits. It does **not** establish ordinary production
admission equivalence, nor guarantee all work finishes within the requested
timeout. Changing those scientific admission semantics remains a release gate.

## Timing scopes

The worker records native-to-render, evidence projection/save, publication and
their combined time. Its combined clock starts after loading the result/public
adapters. The supervisor separately records child process elapsed time, including
startup/imports and final outcome writing. Neither clock includes capture,
detector/native GLRT extraction or queue waits. Matched full reference/current
runs are required before claiming an end-to-end speedup.

The external `tools/qualify_algo07v3_cli.sh` harness runs this same command in
private mount/network namespaces, masks older installations/bulk results/reports,
binds the frozen bundle read-only, and can hide it completely for `resume`.
It requires namespace/mount privileges; the CLI itself does not.
