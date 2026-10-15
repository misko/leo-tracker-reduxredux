# DS22 station reference: historical metadata supports continuity, not surveyed truth

All **44 available development fast recordings** have indirect historical evidence supporting the same station as the configured evaluation reference. No contradictory radio or station identity was found. This strengthens the label to **metadata-supported configured reference**, while GPS/survey verification and a direct fast-recording pose binding remain absent. The evaluation reference and all scientific outputs are unchanged.

The authority's roof coordinates are **9.225 metres** from the existing reference. This small difference cannot explain the kilometre-scale localization failures, and no error-based reference replacement was made.

| Check | Result |
|---|---:|
| Frozen ready development members checked | 44/44 |
| Members with consistent adjacent station evidence | 44/44 |
| Members with pose-bound adaptive captures before and after | 43/44 |
| Members with only a following in-DS22 adaptive capture | 1: DS22-001 |
| Verified adjacent pose-binding usages | 87, representing 51 unique adaptive recordings |
| Radio or embedded-authority contradictions | 0 |
| Direct fast-session pose files in the inspected pose store | 0 |
| Location/GPS fields in inspected fast segment and root metadata | 0 |

## Historical identity chain

The original sealed DS22 manifest (`sha256:705380facbea54e6a1142eab07f1114f7ae99d3066e4f8bd9210cb55014768f3`) supplies recording IDs, session IDs, capture timestamps and raw identities. The previously frozen membership supplies the 44 ready development labels; no membership or performance-based filtering was added. Their 616 segment metadata snapshots were hash-checked against the original seal. As a wider metadata census, all 956 pinned segments across all 69 fast members identify the same radio serial, `1040005e0b100007100010000bf33a5d4d`. This broader check did not read locked-set inference or errors.

Each inspected fast capture identifies host `192.168.1.20`. For each development member, the audit selected the closest earlier and closest later adaptive member by **capture time**, without reading any adaptive performance result. Existing pose companion files bind those adaptive recordings to `station_gauss` and that same radio serial. The audit verified the companion content digest, embedded authority digest, exact inner acquisition-manifest digest, qualified capture-time bracket and authority validity interval. The inner acquisition digest differs from the outer JSON-file digest; matching the correct contract matters here.

All 87 companion usages carry the same authority content as `/etc/leo/station-authority/gauss-r20-lt3d-004b-20261001-v1.json`. Its declared validity begins on October 1, before the October 13–14 DS22 acquisitions. This is historical receipt evidence, not an assumption that a current setting applies retrospectively. The authority itself says its start boundary is prospective configuration, not a measured installation time, and that its coordinates were supplied by the operator; altitude and survey uncertainty remain unknown.

The five requested priority cases have both preceding and following matching receipts:

| Case | Fast capture UTC | Bound neighboring adaptive labels |
|---|---|---|
| DS22-019 | 2026-10-13 08:47:54.759 | 018 / 020 |
| DS22-059 | 2026-10-13 18:53:00.480 | 058 / 060 |
| DS22-075 | 2026-10-13 22:55:01.163 | 074 / 076 |
| DS22-109 | 2026-10-14 07:29:22.101 | 108 / 110 |
| DS22-131 | 2026-10-14 13:02:06.324 | 130 / 132 |

The neighboring captures begin approximately 15 minutes before and after each priority fast recording. Exact identities, timestamps, raw identities and all metadata paths/digests are in the companion JSON.

## What is still unknown

The inspected capture-pose publisher binds adaptive captures, not these fast sessions. No direct fast-session pose companion was found in either known revision directory. The pinned fast segment metadata and current root JSON receipts contain radio/configuration evidence but no latitude, longitude, GPS, station ID or pose-authority field. Root receipts were read and hashed, not modified. The audit did not search raw IQ for position or infer geography from satellite fit results.

Matching device identity and time-bracketing station receipts provide continuity evidence; they cannot prove the device never moved between captures. The authority's roof position is operator-configured, not contemporaneous GPS or surveyed antenna phase-center truth. The evaluation coordinates remain `37.84903264307456, -122.4856541910174`; the authority coordinates are `37.849056280893684, -122.48575489722863`. Neither was chosen by minimizing position errors. No model, prior, seed, bank, acceptance threshold or historical evaluation file changed.

## Reproduction

Source: `tools/ds22_station_provenance_audit.py`, commit `aef09575a`; five component tests passed, including rejection of wrong recording, timing, radio and content bindings. Ruff passed. Execution was bounded by an external 120-second timeout with five-second kill grace. This was exclusively metadata work: **zero localization objectives, fits, raw-IQ reads, new captures or QNAP writes**.

The first read-only attempt reached final report construction but incorrectly tried to parse the Python source file as JSON; it stopped before creating an output namespace. A raw-file binding helper and regression test corrected that bookkeeping error. The completed run uses separate namespace `/srv/bulk/leo-research-ds21-ds22/2026_10_14/ds22-station-provenance-v2`. Its 840 input bindings were rehashed before completion. Exact report JSON SHA256: `18e6a8e7456313e4ebebbd7e79ad41b719a8fc6d8604bda72dacf8e6d44c86d1`.
