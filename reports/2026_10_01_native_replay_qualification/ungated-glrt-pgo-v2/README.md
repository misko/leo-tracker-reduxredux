# Ungated GLRT PGO experiment

The qualified ungated ordinary build recipe is replayed by
`tools/build_ungated_glrt_pgo.py`. Detection-policy flags, including coarse-gate
bypass, remain unchanged. Source hashes are checked between training and use;
every profiled translation unit must have a nonempty profile, and coverage
mismatches fail compilation. The optional CZT member is not linked by this
refinement-mode-2 executable (verified by ARM `nm`), so the recipe builds that
member without PGO instead of silently tolerating missing training data.

The scan contains one template context. Training used its first 16 visits;
evaluation used its last 32, with disjoint visit IDs recorded in `protocol.json`.
The earlier `../ungated-glrt-pgo-v1/` attempt incorrectly assumed a second
context and is preserved with its failure. This corrected run used a new,
clean device profile directory; no profiles from that attempt were reused.

Build and train:

```sh
python3 tools/build_ungated_glrt_pgo.py generate /var/tmp/leo-ungated-pgo-v1
# On ARM, after staging the instrumented benchmark and training manifest:
GCOV_PREFIX=/mnt/glrtbench/ungated-glrt-pgo-v1/profiles-v2 GCOV_PREFIX_STRIP=3 \
  /mnt/glrtbench/native-adaptive/current/measure-run 90 \
  /mnt/glrtbench/ungated-glrt-pgo-v1/training \
  --manifest /mnt/glrtbench/ungated-glrt-pgo-v1/training-0.tsv --no-profile
# Copy profiles/objects/*.gcda to the same local build's objects directory.
python3 tools/build_ungated_glrt_pgo.py use /var/tmp/leo-ungated-pgo-v1
```

Use a fresh output directory and profile directory for another experiment.
`generate-build.json` and `use-build.json` retain exact compiler commands;
`source-manifest.json`, `profiles/`, `evaluation-payloads.json` and
`artifact-sha256.json` preserve provenance. Qualified experimental artifacts are
under `artifacts/`; they are not yet full-scan deployment defaults.

Four heldout trials ran control/PGO/PGO/control with the benchmark's
`--manifest heldout-0.tsv --no-profile` options. All scientific candidate
records matched the existing ungated archive exactly, as did training output.
Mean call CPU was 101.363183 ms ordinary versus 100.373313 ms PGO (0.9766%
lower). The first control's file loading incurred extra wall time, so whole
process wall time must not be used to claim a detector speedup. Per-call CPU
is measured after input preload. See `comparison.json` for every trial.

This small, single-context evaluation does not establish a full-scan saving,
concurrent losslessness or sustained throughput. The observed speedup alone
does not resolve the 44 rejected dwells and 313.77-second search in the
priority-overlap experiment.
