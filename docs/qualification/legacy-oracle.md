# Pinned legacy pilot oracle

The legacy oracle is an offline, qualification-only lane. It is not part of
acquisition, processing workers, the API, or the browser. The current package
does not import historical `leo_tracker` code. Instead, `leo-legacy-oracle`
launches `tools/legacy_oracle_worker.py` in a separate Python interpreter with
an explicitly named historical checkout.

The launcher refuses to run unless all of these are true:

- the checkout is completely clean at
  `0bb80d14759fd8496b74e7d3219a690be18565a6`;
- its `uv.lock` has the frozen SHA-256 digest in the launcher;
- the IQ input is an absolute, non-symlink, 600,000,000-byte single-receiver
  CI16-LE dwell whose caller-supplied digest is verified before launch;
- the interpreter is the clean checkout's own `.venv` interpreter, its binary
  digest is sealed, and its full installed-distribution fingerprint equals a
  separately reviewed caller-supplied digest;
- the output does not already exist; and
- the worker returns all 600 scheduled decisions, each bound to the normalized
  complex64 IQ-window digest and the frozen configuration digest.

The old checkout's environment must be prepared separately with its own lock,
reviewed, and supplied explicitly. A conventional virtual-environment
`bin/python` symlink is accepted only when its parent path and target are local,
non-symlink paths. For example, after creating a clean detached worktree and
synchronizing its environment with the frozen lock:

```text
leo-legacy-oracle \
  --legacy-root /absolute/clean/leo-tracker-0bb80d1 \
  --legacy-python /absolute/legacy-venv/bin/python \
  --iq-path /absolute/local/one-receiver-60s.ci16 \
  --iq-sha256 sha256:<reviewed-digest> \
  --environment-sha256 sha256:<reviewed-environment-fingerprint> \
  --receiver-center-hz <reviewed-calibration-center> \
  --output /absolute/evidence/oracle-receipt.json
```

The checked-out source is used as a numerical oracle only. It must never be
installed into or imported by production. A receipt is a candidate-recovery
reference, not evidence of specificity, attribution, payload decode, or phase
coherence. `load_sealed_legacy_decisions()` validates the immutable envelope and
returns decisions suitable for `SealedLegacyReferenceDecisionPort`.

The runner intentionally does not create the clean worktree or mutate an old
checkout. It also does not choose a calibration center. Those are separately
reviewed campaign inputs, and omission is a hard stop rather than a synthesized
zero-calibration fallback.

`receiver_center_hz` is the center of the historical acquisition search. The
decision's `cfo_hz` is the old acquisition result's absolute digital carrier
offset: its `local_frequency_offset_hz` plus any selected digital-subband
center. It is not the small residual-CFO refinement reported later by the QAM
demodulator. The v1 worker checks this identity before emitting each candidate.
The single-RX gates (`exact-control >= 0.025`, symbolwise margin `>= 0.03`) and
the `pilot_symbolwise_v3` arguments are the recorded J1 oracle parameters in
`leo-tracker-redux/reports/recording_rec_01M09J1R6E59GCC8ANJVYVRN1B_signal_investigation.md`;
they are also the constants at the pinned source revision.
