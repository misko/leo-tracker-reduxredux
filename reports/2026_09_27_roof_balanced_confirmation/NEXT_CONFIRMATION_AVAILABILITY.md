# Outcome-blind availability inventory for a possible next confirmation cohort

Inventory cutoff: **2026-09-27 08:36:52.913856508 UTC**
(`1790498212913856508` ns). This is availability preparation only. No location,
reception, satellite-association, or search result was read, and no cache,
tracking input, candidate bank, RF recording, or experiment was created.

## Deterministic selection

The policy is the earliest four existing recordings, ordered by
`(capture_start_utc_ns, session_id)`, that:

1. start strictly after the last SECOND-cohort recording start
   (`1790483338777911208` ns, `scan-fw-c9db23377d1194dd`);
2. are absent from the original ten-session development cohort, the first
   four-session confirmation cohort, and the four-session SECOND cohort;
3. have a valid pose binding whose capture-manifest digest matches the public
   read-only capture store; and
4. have a complete published public tracking-analysis manifest at the inventory
   cutoff.

The prior manifests contain 18 distinct excluded sessions. Applying the policy
selects the following four without replacement or signal/outcome inspection:

| Order | Recording/session ID | Capture interval UTC | Duration | Rate | Complete visits | Stored compressed | Manifest SHA-256 |
|---:|---|---|---:|---:|---:|---:|---|
| 1 | `scan-fw-0960ee5a52eff93e` | 04:36:02.704405–04:41:04.636925 | 301.933 s | 7.5 MHz | 2,215 | 11.95 GB | `5fc88f8b8af4b748e871f5d1eff4f7c796022432d5a6b456e8f68aeab5b63104` |
| 2 | `scan-fw-127d8fc36e804ae2` | 04:43:07.755388–04:48:09.299180 | 301.544 s | 2.5 MHz | 2,215 | 3.76 GB | `3951aac367e9cdc3f8f95d4e323b447eb17297aec61753b31d1c01a904eeffb1` |
| 3 | `scan-fw-a077447f07d9f81f` | 04:50:12.457108–04:55:13.943655 | 301.487 s | 2.5 MHz | 2,219 | 3.78 GB | `5bb649c58a7d7617d8aa72edb94673ca86b7873ca8e870a3e3589ab585f06273` |
| 4 | `scan-fw-4b6f98a08c65d0cd` | 04:57:16.495150–05:02:18.323308 | 301.828 s | 10 MHz | 2,214 | 16.10 GB | `8406a4be01ed90c82e2290086fdd71c8c5679447cfacd1f3fc3281eefa9d970f` |

All four report receiver IDs 0 and 1, complete visit counts equal to their
receipt event counts, matching pose/capture manifest digests, and a published
tracking-analysis manifest. The common pose-authority digest is
`sha256:03e00d1aaaabf0c27244b9733335fd695c649fb2eb2479e7936e2516946ac1d3`.

## Pose authority and limitations

These recordings do **not** carry surveyed GPS truth. Their position is the
operator-supplied roof coordinate interpreted as WGS84. Altitude and survey
uncertainty are unspecified. RX1/RX2 orientation is operator-described as west
and east, while the physical-to-software receiver mapping remains provisional.
Elevation, RF phase centers, directed phase-center baseline, and world tilt are
unmeasured. The pose authority covers each capture and identifies the same
`radio_pluto_5d4d` fixture used by the earlier roof cohorts.

## Candidate identifiers

The safe candidate identifiers available at this inventory stage are the four
recording/session IDs above. Satellite candidate IDs were deliberately not
loaded: they live in tracking inputs or position-dependent catalogue products,
and availability selection does not need them. Any future confirmation must
rebuild the full causal catalogue independently at every evaluated position and
must not borrow candidate lists, shortlists, or fitted identities from prior
cohorts.

Readiness is a snapshot at the cutoff, not an experiment authorization. A later
confirmation freeze should persist a machine-readable manifest and revalidate
the same capture, pose, and analysis digests before preparing inputs.
