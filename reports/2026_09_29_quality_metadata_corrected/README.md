# Detector quality is recoverable; source-group overlap needs attention

The corrected metadata sidecar binds **8,111 observations in 184 tracks** from three deterministic scans, one per dataset, to the archived public projection. Every observation matches its original track, time, canonical dealiased frequency, receiver, channel, RF and visit. This opens a source-supported quality audit without changing the baseline export contract.

The strongest new finding is shared acquisition provenance: **distinct candidates from the same probe group occur in different exported tracks for 17.7–19.9% of the observations** in this pilot. Exact time/frequency duplicate counting missed most of this relationship because the candidate hypotheses have different fitted supports or frequencies.

| Pilot dataset | Tracks | Observations | Distinct-candidate groups shared across tracks | Observations in those groups |
|---|---:|---:|---:|---:|
| DS7 | 56 | 2,391 | 211 | 423 (17.7%) |
| DS8 | 64 | 3,093 | 302 | 615 (19.9%) |
| DS9 | 64 | 2,627 | 235 | 471 (17.9%) |

[Quality-field summary](summary.json) · [Source-group overlap inventory](group-overlap.json) · [Protocol](PROTOCOL.md)

A source group is derived from capture, visit, receiver and probe identity in the pinned projection. The legacy trajectory code describes hypotheses as source-disjoint interpretations of competing per-probe candidates. This makes exported-track independence a concrete issue to investigate. It does not yet prove that every shared-group candidate pair is mutually exclusive physically, that both came from identical support samples, or that the overlap causes geographic error. No observation was removed or downweighted in this pilot.

## Available quality fields

The original baseline export contains times, frequency, partition, receiver/channel/RF and visits, but omits exact detector score, control score, margin, source-group identity, candidate rank, support duration and uncertainty fields. These are available from cached analysis through the public read-only tracking input adapter.

Detector margin varies substantially: pilot medians are 0.4764, 0.4787 and 0.5363, with ranges 0.0285–0.8017, 0.1343–0.8116 and 0.1267–0.8180. All observations have already passed detector/trajectory selection; these distributions do not describe rejected detections or provide a calibration of frequency error.

The raw `standard_uncertainty_hz` is **constant within each scan**, at 2,772.43, 2,764.68 and 2,755.44 Hz. Source inspection and exact numerical replay show it equals:

`hypot(400 Hz, 15000 Hz/s × timing-bracket-width / 2)`.

The timing bracket is scan-wide (about 364–366 ms). Canonical uncertainty differs across RF channels only by the declared 11.2 GHz / actual-RF scale. It should not be treated as measured independent per-observation CFO variance or substituted directly for the likelihood's 100 Hz scale. Detector margin likewise needs calibration before becoming a weight.

## Binding correction and audit

The [first attempt](../2026_09_29_quality_metadata/README.md) failed because it compared raw receiver CFO with the exported canonical dealiased frequency. Those three failures remain preserved. The corrected run binds the baseline to each reconstructed point's `normalized_dealiased_cfo_hz`, exactly as the archived numerical-input implementation does. It records raw CFO, canonical dealiased CFO and relative alias index separately, along with raw and canonical uncertainty.

All three corrected processes succeeded in 14–17 seconds under 60-second caps. Capture and analysis manifest digests match the baseline exports, and hashes of the three public runtime modules match the previously archived pinned environment. No orbit propagation, IQ read or RF collection was required.

## Next priority

Before a quality-weighted likelihood, audit which competing source groups coexist within the exported all-track set and how the original graph hypotheses resolve them. Then compare a source-consistent track set or an explicit alternative-hypothesis likelihood against ordinary pooling on matched data. Preserve both coverage and excluded alternatives. Choosing the highest detector margin alone is not yet justified as a calibrated association rule.

This is a three-scan availability/provenance pilot, not evidence for the full DS7–DS9 corpus or a measured accuracy gain. The sidecar includes all tracks in each chosen baseline export; downstream eligibility remains a separate rule. Shared-group labels remain in a single training/held partition, but that does not establish independence within either partition.

## Artifacts

[export.py](export.py), [launch.py](launch.py), [input hashes](manifest.json), per-dataset sidecars and receipts, [summarize.py](summarize.py), and [audit_groups.py](audit_groups.py) are retained. Existing contracts, baseline exports and production components are unchanged. These local artifacts have not been remotely published.
