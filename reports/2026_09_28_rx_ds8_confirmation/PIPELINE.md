# DS8 receiver-confirmation pipeline reuse audit

## Reusable stages

The prior four-record geometry confirmation already established the required public-contract path:

```text
metadata-selected sessions
  -> public TrackingInput cache package
  -> paired opportunities
  -> grouped 60/20/20 partitions
  -> training-prefix candidate bank
  -> training-only alias/RX calibration
  -> exact-lane geometry dataset
  -> frozen full-calibration causal-reference scoring
```

For DS8, use only the four session IDs frozen in the new metadata readiness artifact. Do not open
candidate lists while selecting or packaging the panel. The DS8 manifest and pose companions are
already sealed in `reports/2026_09_28_ds8_post_ds7`: all 65 admitted captures have qualified UTC,
complete accounting and verified pose files. The new
[`rx_ds8_confirmation_cache.py`](../../tools/rx_ds8_confirmation_cache.py) adapter is the correct
first stage. It checks the selected row against the sealed DS8 capture metadata, verifies pose
digests and validity intervals, checks the installed public `TrackingInput` contract and paired
probe metadata, and writes four hash-bound cache files plus pipeline `inventory.json` and
`manifest.json`. Its validation reads probe/RF/timestamp structure but does not inspect candidate or
outcome fields.

Run every stage from the repository root in the installed API interpreter, with a fresh output
path and receipt-bound hashes. The reusable module invocations are:

```bash
sudo -n /opt/leo-tracker/current-api/.venv/bin/python \
  -m tools.rx_ds8_snapshot_authority \
  --readiness reports/2026_09_28_rx_causal_refit/ds8-readiness.json \
  --pose-dir reports/2026_09_28_ds8_post_ds7/pose \
  --bulk-root /srv/bulk/leo \
  --tle-root /var/lib/leo/tle \
  --output reports/2026_09_28_rx_ds8_confirmation/snapshot-authority.json \
  --receipt reports/2026_09_28_rx_ds8_confirmation/snapshot-authority-receipt.json

sudo -n /opt/leo-tracker/current-api/.venv/bin/python \
  -m tools.rx_ds8_confirmation_cache \
  --readiness reports/2026_09_28_rx_causal_refit/ds8-readiness.json \
  --ds8-manifest reports/2026_09_28_ds8_post_ds7/manifest.json \
  --pose-dir reports/2026_09_28_ds8_post_ds7/pose \
  --bulk-root /srv/bulk/leo \
  --output-dir reports/2026_09_28_rx_ds8_confirmation/prepared

sudo -n /opt/leo-tracker/current-api/.venv/bin/python \
  -m tools.rx_paired_opportunities \
  --inventory reports/2026_09_28_rx_ds8_confirmation/prepared/inventory.json \
  --output-dir reports/2026_09_28_rx_ds8_confirmation/opportunities

sudo -n /opt/leo-tracker/current-api/.venv/bin/python \
  -m tools.rx_grouped_partitions \
  --opportunities reports/2026_09_28_rx_ds8_confirmation/opportunities/opportunities.jsonl \
  --output reports/2026_09_28_rx_ds8_confirmation/partitions.json \
  --evaluation-only

sudo -n /opt/leo-tracker/current-api/.venv/bin/python \
  -m tools.rx_training_candidate_bank \
  --inventory reports/2026_09_28_rx_ds8_confirmation/prepared/inventory.json \
  --manifest reports/2026_09_28_rx_ds8_confirmation/prepared/manifest.json \
  --partitions reports/2026_09_28_rx_ds8_confirmation/partitions.json \
  --snapshot-authority reports/2026_09_28_rx_ds8_confirmation/snapshot-authority.json \
  --output reports/2026_09_28_rx_ds8_confirmation/candidate-bank.json

sudo -n /opt/leo-tracker/current-api/.venv/bin/python \
  -m tools.rx_training_alias_mapping \
  --inventory reports/2026_09_28_rx_ds8_confirmation/prepared/inventory.json \
  --partitions reports/2026_09_28_rx_ds8_confirmation/partitions.json \
  --candidate-bank reports/2026_09_28_rx_ds8_confirmation/candidate-bank.json \
  --protocol reports/2026_09_28_rx_ds8_confirmation/PROTOCOL.md \
  --protocol-sha256 sha256:<frozen-protocol-digest> \
  --output reports/2026_09_28_rx_ds8_confirmation/alias-mapping.json

sudo -n /opt/leo-tracker/current-api/.venv/bin/python \
  -m tools.rx_geometry_dataset \
  --bank reports/2026_09_28_rx_ds8_confirmation/candidate-bank.json \
  --mapping reports/2026_09_28_rx_ds8_confirmation/alias-mapping.json \
  --partitions reports/2026_09_28_rx_ds8_confirmation/partitions.json \
  --opportunities reports/2026_09_28_rx_ds8_confirmation/opportunities/opportunities.jsonl \
  --output reports/2026_09_28_rx_ds8_confirmation/dataset.json
```

The completed run used this directory's `launch.py` to wrap the stages with
`timeout`, `prlimit`, `nice`, one-thread settings and exclusive receipts. Its
`models` stage freezes both calibration families; its `score` stage evaluates them.
Use the recorded commands and hashes to reproduce the run in a fresh output
directory; existing outputs intentionally fail on overwrite.

## Resolved authority before the candidate bank

The sealed DS8 corpus initially supplied no sanitized `snapshot-authority.json`. This prerequisite
is now resolved by [`rx_ds8_snapshot_authority.py`](../../tools/rx_ds8_snapshot_authority.py),
[`snapshot-authority.json`](snapshot-authority.json), and its
[`snapshot-authority-receipt.json`](snapshot-authority-receipt.json). The builder reads only public
tracking timing/manifests, sealed pose metadata, and the read-only TLE archive; it does not read
candidate or outcome fields.

The installed preparation source selects the latest snapshot strictly before
`first_sample_estimate_utc_ns - 505 seconds`; it does not use `select_nearest`. The builder uses
that same public `select_latest_before` API, rereads each selected snapshot to verify its digest,
and records the tracking anchor, cutoff, collection time, provider, and installed source hashes.
All four selections are strictly causal. They resolve to the same content digest,
`sha256:1f257fbf0981dd20ea80f304953f7a9d2a17f9f4f3a4957b01ec126ad8bda6ac`, although the first
selection uses an earlier collection of those identical bytes. The sanitized authority has one
entry per selected session:

```json
{
  "sessions": {
    "<session>": {
      "input_manifest_sha256": "sha256:...",
      "analysis_manifest_sha256": "sha256:...",
      "snapshot_digest": "sha256:...",
      "site": {"latitude_deg": 0.0, "longitude_deg": 0.0}
    }
  }
}
```

The authority SHA-256 is
`sha256:01274efbf2f905f79b89499e9d82fd2705604ef25c255985c0b24d3ad9b72a82`.
Candidate-bank preparation remains responsible for reproducing this digest after training-prefix
filtering, and fails closed on any mismatch.

The readiness file's prose says the cache-export stage will emit "pose/snapshot authority", but
the current cache packer emits pose and cache bindings only. That wording is not itself a snapshot
receipt and does not satisfy the candidate-bank input.

The packaged manifest already carries the verified pose object and capture/cache bindings expected
by the candidate-bank loader. Confirm its four session IDs and site coordinates exactly match the
snapshot authority; do not substitute a generic roof coordinate without the per-session pose
binding.

## Required stage gates

At each boundary, require exact four-session membership and preserve source hashes. Opportunities
must contain nonempty rows for every selected cache. Partitions must keep overlap-connected groups
within one role and prove candidate removal cannot change assignment. The bank must use only each
recording's first 60% training prefix for reconstruction, candidate ranking and CFO fit. Mapping
must filter raw caches to that same prefix before reconstruction and receiver-bias estimation.
Dataset assembly must preserve exact source IDs, lane identity, common canonical coordinates and
all passed candidates without a forecast-residual gate.

Do not reuse the old `rx_geometry_frozen_score` command for the final model comparison. The DS8
question requires the newly frozen full-six-calibration D/E/S/T fits under both uniform and causal
references, with the same candidate set, causal history and controls. The scorer must be purpose
built or explicitly extended and tested for those contracts.
