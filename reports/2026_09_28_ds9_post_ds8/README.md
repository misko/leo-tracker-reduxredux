# DS9: analysis-complete recordings after DS8

DS9 freezes **105 recordings** admitted from 116 published post-DS8 candidates
at the capture/product cutoff **2026-09-28 14:20:25.287224 UTC**. Exact nanosecond
cutoff and parent digest are in [manifest.json](manifest.json). Membership is
immutable; recordings finishing analysis later do not extend DS9.

| Property | Frozen value |
|---|---:|
| Recordings | 105 |
| Visits | 232,562 |
| Valid IQ per receiver | 27,907.44 seconds / 7.7521 hours |
| Compressed IQ referenced in place | 1,258,610,247,484 bytes / 1.2586 TB |
| 2.5 / 5 / 7.5 / 10 MS/s recordings | 20 / 12 / 20 / 53 |
| Verified pose companions | 105 |
| Excluded candidates | 11 |

Admitted capture starts span **2026-09-28 00:16:44.321211–12:53:12.065709 UTC**;
the final admitted recording ends at **12:58:13.169402 UTC**. Both software
receivers remain together. DS9 is disjoint from DS8 by session ID and source
manifest digest. The lower boundary is DS8's last capture end, not its later
inventory cutoff. Calendar span is not uninterrupted IQ exposure.

## Admission and meaning of analysis complete

Recordings must be published and finalized by the cutoff, have qualified UTC
strictly after DS8, a completed zero-error capture terminal, complete retained
visits, attested source spans, nonempty IQ, restored radio state, and no reported
dropped events or missing/unclassified samples. Retune-invalid samples are
accounted separately; a missed duty target is not missing data.

Analysis admission requires:

- Production GLRT at **120 ms probe stride**, with every visit checkpointed and
  a sealed metrics manifest (`metrics_ready` or `figures_ready`).
- A **complete tracking product**, with complete trajectory and TLE stages,
  whose creation timestamp is no later than the cutoff.
- Exact session and raw-manifest bindings and an exact match between the
  tracking input analysis digest and the GLRT metrics manifest digest.

Every admitted recording actually reported `figures_ready` and tracking
`complete`. The 10 ms API default is a different analysis configuration and is
not the admission query. Full GET responses, configurations, digests, timestamps
and candidate accounting are preserved in `analysis/` for **all 116 candidates**.
The capture candidate list was frozen first; readiness was observed during the
subsequent inventory interval, not in an atomic database snapshot. Tracking
creation time enforces the fixed product cutoff.

Completion means completion of the configured pipeline. The tracking products
use a four-group limit and can retain deferred candidate groups; this does not
claim exhaustive satellite-candidate evaluation or independently verified
satellite identities. No new analysis or RF acquisition was launched.

The 11 excluded records remain in the manifest with their reasons and receipts:
**three** had ready GLRT figures but pending tracking; **eight** had partial
GLRT and pending tracking. Thus chronological groups can contain capture gaps.

## Evaluation and provenance

[evaluation-units.json](evaluation-units.json) binds 105 individual units,
thirteen chronological groups of eight, a one-recording remainder, four rate
strata and the full dataset. These are evaluation views, not train/test splits.

Pose companions bind the same operator-supplied roof authority as DS6–DS8.
Coordinates are unsurveyed, receiver mapping is provisional, and altitude and
directed RF baseline remain unknown. Reference metadata must be withheld from
position inference unless its use is explicitly declared.

IQ remains in its source store. Minting used the public read-only adaptive-hop
reader to validate sealed manifests and chunk accounting; it did not copy,
decompress or rehash the raw IQ. DS9 is not a backup or enforced retention hold.
`SHA256SUMS` seals membership, candidate inventory, evaluation units, pose and
analysis evidence, plus the mint/verifier source and admission tests.

Offline verification needs only Python's standard library:

```sh
python3 reports/2026_09_28_ds9_post_ds8/mint.py verify
```

Validation at mint: **16 admission tests passed**, Ruff checks passed, the DS8
parent verifier passed, and DS9 offline verification passed. Tests cover missing
analysis, partial coverage, stale/mismatched products, wrong GLRT configuration,
the completion cutoff, deferred-group handling and refusal to overwrite DS9.

`mint.py collect` was run in checkpointed metadata-only batches through the
installed API reader runtime; `mint.py seal` finalized the inspected inventory.
Both refuse to overwrite an existing DS9. `local/` contains ignored working
checkpoints; every artifact needed for offline verification is outside it.
