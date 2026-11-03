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
