# Pinned legacy pilot oracle

The legacy oracle is an offline qualification lane, never a production runtime
dependency. The current package launches one exact reviewed worker in one exact
historical environment. It never imports `leo_tracker` itself.

## Frozen identities and preflight

The launcher has no worker, checkout, interpreter, or environment override. It
requires all of these reviewed identities before and after every run:

- checkout `/home/mouse9911/gits/leo-tracker-oracle-0bb80d1` at commit
  `0bb80d14759fd8496b74e7d3219a690be18565a6` and tree
  `631bc74222f1d03dad99f418ee21e75d94dbb27d`;
- content digest of every tracked file beneath `src/leo_tracker`, plus
  `pyproject.toml` and `uv.lock`, not Git's possibly cached clean bit;
- absolute, root-owned `/usr/bin/git` and its reviewed binary digest;
- exact `tools/legacy_oracle_worker.py` path and content digest;
- every regular file and symlink in the checkout's `.venv`, plus every mapped
  external interpreter/shared-library file, against
  `config/qualification/legacy-oracle-environment-v1.json`; and
- the exact historical single-RX `pilot_symbolwise_v3` gates and arguments.

The dedicated checkout's source and `.venv` directory trees, and the reviewed
worker and environment manifest, are sealed without owner/group/other write
bits. The launcher verifies that seal as content provenance and as protection
against accidental concurrent environment mutation. It does not claim
resistance to a malicious account owner. If the environment must be rebuilt,
make only this exact dedicated checkout writable (`chmod -R u+w`), run the
frozen sync and manifest-review procedure, reseal it with `chmod -R a-w`, and
review/update every changed frozen digest together. Never loosen modes on the
reference checkout or on a live receipt merely to bypass a failing preflight.

The environment manifest is generated only during an explicit environment
review with `tools/build_legacy_environment_manifest.py`. Updating it, its two
frozen digests, the source-tree digest, or the worker digest is an evidence
revision—not a response to a failing test.

## IQ snapshot and evidence publication

The input must be an absolute, non-symlink, local 600,000,000-byte CI16-LE
single-receiver dwell with a reviewed digest. The launcher copies and hashes it
through a no-follow descriptor into an exclusive file beneath the evidence
directory. It then opens that snapshot read-only and unlinks its name before
the worker starts. The worker receives only the stable descriptor, hashes it
before and after evaluation, and emits exactly 600 decisions on stdout.

The receipt name is one relative filename. Publication uses the already-open
evidence directory descriptor with `O_NOFOLLOW | O_EXCL`, mode `0440`, a file
`fsync`, and a directory `fsync`. Loading likewise requires the evidence root,
opens relative to its no-follow directory descriptor, and rejects paths,
permissions, link counts, worker/source/environment identities, or semantic
digests that are not frozen.

An exclusive `.legacy-oracle.lock` in the evidence root is acquired before any
preflight and held through the final directory `fsync`. A second qualification
fails immediately; it cannot race the source/environment checks or publication.
The persistent lock file is coordination state, not a receipt, and remains mode
`0600` after the process releases its advisory lock.

## Command

```text
leo-legacy-oracle \
  --iq-path /absolute/local/one-receiver-60s.ci16 \
  --iq-sha256 sha256:<reviewed-digest> \
  --receiver-center-hz <reviewed-calibration-search-center> \
  --evidence-root /absolute/local/qualification/legacy-oracle \
  --receipt-name <immutable-receipt-name>.json
```

`receiver_center_hz` is the center of the historical acquisition search. The
decision's `cfo_hz` is the old acquisition result's absolute digital carrier
offset: `local_frequency_offset_hz` plus any selected digital-subband center.
It is not the small residual-CFO refinement from the QAM demodulator. The worker
checks this identity for every candidate.

The single-RX gates (`exact-control >= 0.025`, symbolwise margin `>= 0.03`) and
the `pilot_symbolwise_v3` arguments are the recorded J1 oracle parameters in
`leo-tracker-redux/reports/recording_rec_01M09J1R6E59GCC8ANJVYVRN1B_signal_investigation.md`
and the constants at the pinned revision.

A sealed receipt remains candidate-recovery evidence only. It does not claim
specificity, Starlink attribution, payload decode, or phase coherence. Pass its
validated decisions to `SealedLegacyReferenceDecisionPort`; never install or
import the historical package in production.
