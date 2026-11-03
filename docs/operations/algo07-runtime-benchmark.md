# ALGO07 runtime benchmark

The target is a tenfold reduction in active processing time from recorded fast
scan data to the standard published ALGO07 position, preserving scientific
behavior. Acquisition duration and queue delay are reported separately. A
tenfold speedup of one function does not establish this end-to-end target.

## Frozen reference

Freeze the complete available DS26/DS27/DS28 reference inventory before changing
runtime code. The existing guarded-policy audit contains 148 DS26, 13 DS27,
and 14 DS28 paired outcomes. The parent fast memberships contain 159, 15, and
16 recordings respectively; retain the 15 unavailable upstream cases in the
accounting. These are existing development results, not independent validation
or fresh full-pipeline executions.

The initial freeze binds the reference audit, its numerical receipts and guard
evidence, the recorded input manifests, causal catalogues, and ALGO06 endpoints.
Hash checks ensure the evidence does not silently change. They do not prove
that every transitive raw-IQ file has been copied or rerun. Before numerical
replay, export each case through its public port, freeze that complete export,
and validate the production read audit.

Each numerical optimization must reproduce both calibration arms, observation
ownership, satellite identities, qualification decisions, and fallback reasons.
Prefer exact equality. If a mathematically equivalent operation changes floating
point order, declare tight tolerances before the trial and inspect decision
margins; do not approve solely on an unchanged average position error. Frequency
objective parity and geographic error parity are separate checks.

## CLI

The initial CLI supports immutable file inventories and bounded per-stage Python
profiles. A specification is JSON with a nonempty `files` list, whose rows have
`path`, optional `sha256`, and optional descriptive `role`/`case` fields. Paths
are resolved relative to the specification. Existing expected hashes are checked
before the baseline is written.

```bash
python -m leo.cli.algo07_profile freeze --spec spec.json --output frozen.json
python -m leo.cli.algo07_profile verify --manifest frozen.json
python -m leo.cli.algo07_profile run --manifest frozen.json \
  --stage association --output /srv/bulk/leo/research/runtime/trial-001 \
  --timeout 1200 --script /absolute/path/to/replay_worker.py -- --input private-input
python -m leo.cli.algo07_profile show --profile /srv/bulk/leo/research/runtime/trial-001/profile.pstats
```

`run` creates a new output directory, verifies the baseline before and after the
command, records wall/child CPU time and peak RSS, bounds the process group, and
profiles the named Python script. Its log and profile may include sensitive
operational paths; review them before publication. It does not publish any
scientific result or grant a script permission to modify production. Run workers
using their existing guarded, private-input launch workflow. Child scripts need
their own profiles; the CLI explicitly labels this limit.

## Iteration measurements

To inspect a live numerical child rather than its waiting supervisor:

```bash
python -m leo.cli.algo07_profile sample --pid CHILD_PID \
  --research-root /srv/bulk/leo/research/runtime/case \
  --output /srv/bulk/leo/research/runtime/case/sample-001 \
  --duration 20 --sampler /absolute/path/to/py-spy
```

This requires access to the process through the operating system. It uses
nonblocking external sampling, accepts only a command naming the specified
private research root, and records PID start identity, raw stacks and sampler
errors. It does not cover descendants. Duration is bounded to 60 seconds;
sampler timeout does not terminate the target worker. Sampling may perturb
timing and fail to unwind frames: report both limitations, preserve raw bytes,
and do not treat unparseable rows as valid samples.

`tools/profile_algo07_full_glrt.py` extends small native fixtures to every window
of a recording. Use its `snapshot` and `run` subcommands with the installed native
Python. Published candidate equality covers all receivers and processed/invalid
windows. Use a 30-minute total bound and eight or fewer workers for this benchmark
(the CLI supports up to sixteen);
this stage still does not rerun downstream localization. A comparison with saved
published results alone does not measure baseline speed.

For ALGO03 private replays, `tools/compare_algo03_runtime_replays.py` compares
both arms and every scientific JSON value exactly, including intermediate
nominations, ownership and optimizer histories. Supply explicit baseline and
candidate runtime-manifest pins. The tool validates source-receipt hashes and
requires complete read audits; timing, process IDs and validated relocated
provenance are accounted for separately. An unchanged endpoint alone cannot
pass this comparison.

`tools/profile_hierarchical_bound.py capture` records actual likelihood arrays
at predeclared positions in both arms. `measure` alternates baseline/candidate
execution order and requires exact equality with recorded outputs. It measures
the likelihood kernel, not localization accuracy or worker speed. Retain the
capture hashes, implementation hashes, all timings and failed comparisons.

Prepared numerical replays use `tools/profile_algo07_numerics.py`:

```bash
python tools/profile_algo07_numerics.py snapshot --bulk-root /srv/bulk/leo \
  --job COMPLETED_ALGO07_JOB --output /srv/bulk/leo/research/runtime/case
python tools/profile_algo07_numerics.py run \
  --snapshot /srv/bulk/leo/research/runtime/case \
  --output /srv/bulk/leo/research/runtime/case/reference \
  --mode replay --reference --timeout 1200
```

Omit `--reference` for the candidate kernel. The frozen reference kernel must
be captured before editing it. `--mode capture` performs only incumbent
reconstruction and records real tensor inputs; it does not repeat nomination
and refitting. The guarded launches verify input hashes afterward and retain
process-tree-specific read audits. Compare complete intermediate results using
`tools/compare_algo07_runtime_replays.py`; unchanged fallback endpoints alone
are insufficient. Research-only inputs use the separate snapshot adapter and
are intentionally restricted to reconstruction.

`--reference` replaces only the phase-pair kernel. For changes elsewhere in the
numerical implementation, run the profiler from a separate checkout of the full
baseline revision. A kernel switch is not a baseline for changed geometry or
calibration code.

Native GLRT has a separate bounded adapter. Pass the actual installed native
worker source, which can differ from this checkout's older fast-scan adapter:

```bash
python tools/profile_algo07_glrt.py snapshot --bulk-root /srv/bulk/leo \
  --run-id COMPLETED_FAST_RUN --source-root /absolute/installed/native-worker \
  --output /srv/bulk/leo/research/runtime/native-fixture --per-channel 2 --seed 20261103
python tools/profile_algo07_glrt.py run \
  --snapshot /srv/bulk/leo/research/runtime/native-fixture \
  --source-root /absolute/installed/native-worker \
  --output /srv/bulk/leo/research/runtime/native-fixture/baseline --timeout 300
```

Use the native worker's installed Python/dependencies. The snapshot selects
whole paired-receiver windows within each of the eight channels, verifies their
IQ through the public source reader, and freezes exported arrays and installed
Python/native-library bytes. The replay requires exact agreement with every
published fractional candidate field. This measures detector work without
rerunning a whole scan, writing production results, or modifying its queue.

1. Measure current discovery/validation, IQ/GLRT, graph construction, initial
   association/localization, each recovery stage, and final publication.
2. Pick one hotspot and implement a bounded change with component-owned tests.
3. Compare baseline and candidate on the same frozen cases, under the same CPU,
   thread limits, storage/cache conditions and solver budgets. Alternate ordering
   when repeated runs are appropriate. Record system load.
4. Check scientific parity and reference hashes. Preserve failures and timeouts;
   faster fallback cannot count as faster successful inference.
5. Publish the successful iteration and its limitations, then measure production
   before selecting the next hotspot.

The November 3 queue audit found repeated historical terminal validation using
several CPU cores. A prior ALGO07 canary profile also found two-family phase
integration inside finite-difference optimization. These are hypotheses for the
first measurements, not proven tenfold opportunities.
