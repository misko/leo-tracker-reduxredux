# Exact receiver identity mapping from public trajectory contracts

The sampled training scan `scan-fw-0634fced66c0f843` has **840 cached observation
IDs and 840 exact reconstructed matches**, with no conflicting stream/path
assignments. All 840 selected observations belong to **RX1** in this example.
This does not establish receiver coverage in other scans or imply that raw RX0
samples are absent. It means this cached eligible-track set is RX1-only.

The compact cache omits receiver identity, but the public trajectory graph retains
`stream_id` and `receiver_path_id`. Re-running the same public projection and
trajectory configuration regenerates the hashed observation IDs exactly. Hashes
therefore do not prevent the join; they provide its equality check. The initial
schema-only claim that mapping was unavailable was incorrect and is withdrawn.

The reconstruction projects 2,192 candidates into seven hypotheses. Repeated
observation IDs across hypotheses must agree on both stream and receiver path;
any conflict or missing cached ID fails the join. The derived mapping contains
the 840 ID-to-stream/path associations and hashes of source manifests, trajectory
configuration, cached evidence and worker. It adds no fields to published contracts.

Only this training recording was inspected. The next per-RX model must first
validate mapping coverage for its own scans; this one example is not a guarantee
that every cached track can be reconstructed after code or source changes.
Channel names are not inferred from the opaque receiver-path identifier here.

Reproduce with the read-only service identity and normal-user stdout redirection:

```bash
sudo -n -u leo .venv/bin/python \
  reports/2026_09_23_receiver_identity_mapping/reconstruct.py \
  --session scan-fw-0634fced66c0f843 \
  --evidence reports/2026_09_23_day_position_validation/replication/block_01/cache/evidence/scan-fw-0634fced66c0f843.json \
  > /tmp/receiver-mapping.json
```

Two synthetic tests reject conflicting receiver assignments and missing cached
support, while permitting consistent repeated hypotheses. No IQ or geographic
position outcome is used. Terra established the live reconstruction; the main
task implemented, tested and saved the reproducible export.
