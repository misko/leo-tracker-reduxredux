# Wave 6 Cortex-A9 PGO workflow

This experiment uses the sealed Wave 5 final v2 sources and existing strict
floating-point flags.  It adds GCC profile instrumentation or profile use; it
does not enable blanket fast-math or alter final FP64 GLRT source.

`build_pgo_v2.py generate` builds at the stable path `work-v2/arm`, then freezes the
instrumented executable, ARM component binaries, exact commands, source hashes,
and expected `.gcda` strings under `builds/generate-v2`.  The later `use` mode
requires the unchanged `work-v2/arm` source paths and recompiles at those same
object/output paths with `-fprofile-use`, `-fprofile-correction`, and fatal
coverage diagnostics.  Before compilation, the script explicitly requires all
four nonempty profile files because GCC 7 lacks `-Wmissing-profile`.  It freezes use artifacts separately and
refuses to overwrite either receipt.

## Training handoff

1. Run `python3 build_checks.py`, then build once on the host with
   `python3 build_pgo_v2.py generate`.  The checks compile and execute the frozen
   source's host and sanitizer component suites.
2. Copy `builds/generate-v2/fused_rate_coarse_gate_arm`, the four exact/control
   templates, and four selected training CI16 dwells to the ARM host.  Record
   the four metadata context identifiers.  These contexts are training-only.
3. On ARM, clear and create `/var/tmp/leo-wave6-pgo-profile-v2`, then invoke the
   instrumented binary once for each training context using
   `RATE EXACT CONTROL INPUT_CI16`.  Normal process exit flushes counters.
   Reusing the same instrumented binary accumulates the four runs.
4. Copy the complete `/var/tmp/leo-wave6-pgo-profile-v2` directory back to the
   identical absolute path on this build host.  Compare its filenames with
   `generate-manifest-v2.json.expected_gcda_strings`; every compilation unit named
   there must be present and nonempty.
5. Run `python3 build_pgo_v2.py use`.  Any missing profile or control-flow mismatch
   is fatal.  Do not rename sources, the stable work directory, objects, or the
   executable between the two compilations.
6. Execute ARM component tests from `builds/use-v2`, then evaluate scientific
   parity and timing on a broad held-out cohort that excludes all four training
   metadata contexts.  Compare candidate objects exactly before accepting any
   timing result.

The training runs are optimization input and cannot serve as timing evidence.
Host-generated profiles are invalid because they describe another compiler
target and architecture.

The v1 generator and receipt remain immutable provenance, but are superseded
before hardware use because the separately compiled proposal object embedded
an absolute path below its profile directory.  V2 compiles that object from a
recorded stable working directory using relative source/object names.  Its four
profile files are flat beneath the target profile directory.  The v2 generate
directory also contains evaluator-compatible `sources`, `binaries`, threshold
metadata, and source snapshots.  `provenance.json` binds both generate receipts.
The generated `v1-source-bindings.json` maps every unmodified v1
`source_tree_sha256` entry to its hash-verified preserved file without changing
the historical receipt.

`heldout32-reference` is a deterministic evaluation subset of the frozen
Wave 5 ARM152 rows.  It removes the exact four `arm4-v2` training metadata
contexts, then selects 32 evenly spaced positions from the remaining 148.  It
contains 704 windows and 1,201 candidate entries, with a reference mean actual
fused CPU time of 917.6329126875 ms per dwell (41.71058694034091 ms per window
times 22).  `test_holdout.py` verifies
zero training overlap, verbatim row selection, hashes, and counts.

## Completed target result

The v2 use binary completed the disjoint held-out panel at 874.445316 ms mean
outer CPU per dwell, versus 917.632913 ms for the frozen reference: a 4.71%
reduction.  All 1,201 emitted candidate objects were identical, and the
standard audit recovered 904/921 positive reference hits.  The four training
contexts were excluded.  All six ARM component suites passed.

`profile-data-v2.tar.gz` preserves the four target-generated `.gcda` files
(archive SHA-256
`0d7addaa13d8fb88ce09bd9513ff9908c327d3f3f1ced351a654c3ba7d8ac389`).
`profile-retrieval-v2.json` records each file hash, the training manifest hash,
and retrieval ownership note.  `training4-v2` is training evidence;
`arm-heldout32-v2` is the independent timing and parity evidence.
