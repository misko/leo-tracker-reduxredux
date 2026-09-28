# DS7 proposal: complete recordings after DS6

**Status: proposed, not minted.** This is a fixed metadata inventory for review, not a new RF collection, processing run, or scientific train/test split.

Propose all **88** published adaptive recordings whose earliest capture start is after DS6's final capture end and which were finalized by **2026-09-27 16:21:53.052560 UTC**. Membership is fixed at that cutoff; later publication or collection does not silently extend it. All 88 pass the proposed recording-completeness gates; no indexed candidate was rejected.

| Property | Proposed corpus |
|---|---|
| First capture start (host-bracket midpoint) | 2026-09-27 05:46:47.936854 UTC |
| Final capture end (terminal host timestamp) | 2026-09-27 16:06:47.298702 UTC |
| Radio | `radio_pluto_5d4d` |
| Software receivers | Both RX0 and RX1, kept together |
| Retained visits | 194,934 |
| Simultaneous dual-receiver sample instants | 144,839,100,000 |
| Valid IQ duration, summed across visits | 23,392.08 seconds / 6.498 hours per receiver |
| Compressed IQ bytes declared by sealed manifests | 860,110,430,482 bytes / 860.11 GB |
| Pose bindings | All 88 verified against their source manifest and authority |
| Sample rates | 19 at 2.5, 27 at 5, 23 at 7.5, 19 at 10 MS/s |

Elapsed wall time, recorded source-span duration, and retained valid IQ duration are different quantities. Retune/transition-invalid intervals are explicitly accounted for and are not usable IQ samples. No channel, receiver, visit or sample window is selected using signal quality, satellite association, or position error.

## Proposed membership rule

1. Start strictly after the latest terminal capture time in the immutable DS6 manifest; exclude every DS6 session ID explicitly. Nanosecond boundaries are preserved in the manifest.
2. Published sealed recording manifest validates through the installed read-only `AdaptiveHopIqStore`; finalization is no later than the fixed inventory cutoff.
3. Terminal state is completed with zero terminal error; source span is attested and UTC binding is qualified.
4. Every started event has a retained complete visit. Recorded transport loss, unreceived tail, unclassified samples and dropped device events must all be zero.
5. Recording is nonempty and radio restoration completed. Chunk, sample and byte accounting must satisfy the existing manifest contract.

All published adaptive radios were considered by the store's metadata index; every post-DS6 candidate was on the DS6 radio. This proposal does not claim an inventory of unrelated capture systems or unpublished acquisition/spool sessions. A recording absent from the published index cannot qualify at this snapshot.

**Completeness does not require a duty-cycle target or a successful analysis.** All 88 report `duty_target_met=false`; the API's combined `capture_qualified` flag includes that target and must not be mistaken for missing IQ. Explicit zero-loss accounting and full retained-visit coverage define this proposal's recording completeness.

## Analysis readiness is separate

The initial readiness observation found 79 tracking products complete, three running and six pending. Per-recording refreshed states, observation timestamps, input digests, product/configuration digests and any deferred-group counts are in the manifest. Analysis states can change after observation; they do not change raw membership.

The current default GLRT status endpoint reports `not_started` for its requested configuration even on recordings with complete published tracking products. That endpoint is configuration-specific, not an inventory of every historical analysis. Its configuration and bindings are retained explicitly. It must not be interpreted as evidence that the complete tracking products have no upstream GLRT evidence. Likewise, a tracking product marked complete can retain a configured group cap and deferred groups; it is not proof that every possible track was processed.

If “fully complete” is intended to mean every requested analysis is also finished, first specify exact analyzer/configuration versions and required stages. The raw 88-recording corpus remains the proposed parent; an analysis-ready view should be explicitly derived rather than silently dropping harder or pending recordings.

## Reference and evaluation handling

The verified companion authority is `gauss-r20-roof-20260926-v1`, with operator-supplied WGS84-interpreted coordinate **37.849056280893684, -122.48575489722863**. Physical RX1 is west-facing and physical RX2 east-facing; software mapping is provisional. Altitude, uncertainty and directed RF phase-centre baseline remain unknown. Pose metadata is not surveyed truth and must not enter position-hidden inference accidentally.

Keep each complete recording, both receivers and all visits in one evaluation unit. `evaluation-units.json` defines single recordings, rate strata, eleven groups of eight and the full corpus. These chronological groups are convenience units, not independent trials or a randomized train/test split. Before model comparison, select a reproducible split of whole correlated groups with an explicit prior-exposure audit. Being later than DS6 does not establish that another research task has never inspected these observations.

## Integrity and scope

This proposal revalidates sealed source manifests, receipt accounting and existing pose digests. It does **not** decompress/re-hash approximately 860 GB of raw IQ or independently stat every payload file. The original manifests bind their chunk and full-stream hashes; proposal-level validation must not be described as a new end-to-end payload verification. No retention hold or storage mutation was applied. Minting should preserve exact membership and references, establish the intended retention authority, and state payload verification scope explicitly.

Files:

- `proposed-manifest.json`: exact proposed members, source digests, capture times and readiness metadata.
- `inventory.json`: all considered candidates, completeness decisions and initial/refreshed readiness observations.
- `recordings.csv` and `TABLE.md`: human-reviewable inventory.
- `ds6-parent-manifest.json`: exact published DS6 manifest bytes; its digest binds the exclusion boundary.
- `evaluation-units.json`: complete recording units and rate/group views, without train/test assignments.
- `build_proposal.py`: read-only metadata collector; `verify.py`: offline membership/accounting/seal checks.
- `SHA256SUMS`: seals the local proposal artifacts; these are proposal seals, not a minted dataset registration.

Validation: run `python3 reports/2026_09_27_ds7_proposal/verify.py`. The collector uses the installed API release's storage contract and never reads raw IQ, launches analysis or modifies acquisition.
