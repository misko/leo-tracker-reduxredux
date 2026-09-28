# DS7: complete recordings after DS6

Minted from the explicitly approved 88-recording proposal, with membership frozen at **2026-09-27 16:21:53.052560 UTC**. Later recordings do not extend DS7. The authoritative configuration is [manifest.json](manifest.json); exact approved input is [approved-proposal.json](approved-proposal.json).

The corpus contains **194,934 visits**, **144,839,100,000 simultaneous dual-receiver sample instants**, and **860,110,430,482 compressed IQ bytes** declared by sealed source manifests. Both software receivers remain together. Captures span September 27 **05:46:47.936854–16:06:47.298702 UTC**, strictly after DS6. Valid IQ sums to 6.498 hours per receiver. Sample rates are 19 recordings at 2.5, 27 at 5, 23 at 7.5 and 19 at 10 MS/s.

Admission requires published, validated sealed manifests, completed zero-error terminals, attested source spans, qualified UTC, complete retained-visit coverage, no reported dropped events or missing/unclassified samples, nonempty IQ and restored radio state. Retune-invalid intervals are accounted metadata. A missed duty target does not imply missing IQ. All approved capture records, their source digests and original readiness observations are preserved exactly.

[evaluation-units.json](evaluation-units.json) freezes 88 individual recordings, rate strata, eleven chronological groups of eight and the full corpus. These are evaluation views, not an independent train/test split. Prior research exposure has not been audited. Analysis readiness is separate from recording completeness: the proposal snapshot recorded 79 complete tracking products, three running and six pending; complete products may have deferred groups. GLRT status is specific to the requested configuration. Run results must name their own analyzer configuration and product digests.

All 88 source manifest seals were revalidated at mint through the installed read-only adaptive-hop store, and pose companion bytes matched the approved digests. [mint-verification.json](mint-verification.json) records that check and its timestamps. [pose-authority.json](pose-authority.json) and `pose/*.json` preserve the reference evidence. The reference coordinate is operator supplied, not surveyed truth; altitude and directed RF baseline remain unknown and receiver mapping is provisional. Keep reference coordinates hidden from position inference.

This mint freezes metadata and references IQ under `/srv/bulk/leo`; it does not copy or decompress/re-hash 860 GB of IQ or independently stat each payload. The source manifests bind chunk and stream hashes. No new RF capture or analysis was launched. Intended retention is preservation of all DS7 sources for research, but **no enforced retention hold was added**: the inspected catalog retention service supports recording, scanner and persistent-hop stores, not this adaptive-hop store. This artifact is not a backup or an indefinite retention guarantee.

`SHA256SUMS` seals every artifact in this directory. Verify offline with:

```sh
python3 reports/2026_09_27_ds7_post_ds6/verify.py
```

The mint script is provenance for this one-time operation and refuses to overwrite the directory. The archived table retains its original proposal wording. Any membership change requires a new dataset version, not editing these sealed files. The mint exists in this workspace; GitHub publication is separate.

See the [dataset configuration index](../../docs/research/datasets.md) for DS1–DS7.
