# Residual-predicate two-worker benchmark handoff

This report freezes an exact pre-predicate control and production tracking
source `b8f2dff...`, then builds each against the same execution-enabled CLI and
runtime executor. It adds no optimization and changes no production, live or
application source.

The host gate ran every binary at one and two workers over the complete
11,747-candidate DS9 fixture. All four serialized outputs are byte-identical,
with SHA-256
`6819cb39151bb2cbe894e5d427244aa95d1eae73e17469e5033659d2b0a30084`
and 64 tracks. Host timings are diagnostic because the machine was shared; the
gate establishes numerical and execution-path coherence only.

The ARM executables are:

- `build-arm-control/leo-tracking-execution`, SHA-256
  `858b7114e3d51b7168842e8323e43b58ba73ba828380ea3a44dea0c2baa89295`
- `build-arm-optimized/leo-tracking-execution`, SHA-256
  `9b1e02321ce06dbc2fa0df5ac03c933803ae45de2b6d3295d1332160e285e1f6`

After root stages them as `control` and `optimized`, the bounded CPU-only ABBA
measurement is:

```sh
stage=/mnt/glrtbench/native-adaptive/tests/residual-predicate-two-worker-v1
fixture=/mnt/glrtbench/native-adaptive/tests/tracking-prefix-v1/candidates.tsv
measure=/mnt/glrtbench/native-adaptive/current/measure-run

"$measure" 90 "$stage/control" "$fixture" --workers 2 \
  > "$stage/control-first.tsv" 2> "$stage/control-first.time.json"
"$measure" 90 "$stage/optimized" "$fixture" --workers 2 \
  > "$stage/optimized-first.tsv" 2> "$stage/optimized-first.time.json"
"$measure" 90 "$stage/optimized" "$fixture" --workers 2 \
  > "$stage/optimized-second.tsv" 2> "$stage/optimized-second.time.json"
"$measure" 90 "$stage/control" "$fixture" --workers 2 \
  > "$stage/control-second.tsv" 2> "$stage/control-second.time.json"
sha256sum "$stage"/*.tsv
```

This invokes no radio source or detector. The resulting timing is the standalone
two-worker lane reconstruction path. It is not an application publication,
capture-concurrent, regional-search or five-second cadence qualification.

The production predicate boundary regression was already run physically and is
bound separately by `../residual-predicate-research/production-arm-focused.json`;
it need not be repeated for this timing handoff.

Root executed the frozen ABBA pair with two workers. Control wall times were
14.9262 and 14.8536 seconds; optimized wall times were 14.0729 and 14.0792
seconds. The mean reduction is 5.47%, with pairwise reductions of 5.72% and
5.21%. All four outputs are byte-identical at the expected SHA-256. The result
remains well above five seconds and does not qualify continuous pipeline
cadence. The immutable evidence is under `physical-arm/`.
