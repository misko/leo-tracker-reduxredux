# Historical continuous dual-RX inventory

**Date:** 2026-09-23. **Scope:** metadata-only search of the read-only
`RecordingStore`; no IQ was read and no RF was collected.

## Result

The post-continuity-fix corpus contains many gap-free dual-RX recordings long
enough for a multi-second phase test. The best new first target is
`cap-20260825T031521-ec8adc0e9426`: it has an independently reported 11.0 s
common-source interval and is less reused than the strongest 065355 capture.
The already-extracted 105915 capture remains the lowest-cost source-quality
check because it has a 7.05 s two-source overlap on one shared-clock radio and
650/704 accepted 20 ms windows. Its satellite association and historical pilot
edge caveats must remain explicit.

The public store reconciled 2,734 committed bundles with zero inspection
issues. From 2026-08-24 onward it contains 1,852 dual-RX streams at least five
seconds long:

| Applied sample rate | All >=5 s | Zero recorded gaps/missing/overflow |
| ---: | ---: | ---: |
| 2.5 MS/s | 1,639 | 1,380 |
| 3 MS/s | 22 | 18 |
| 5 MS/s | 191 | 142 |
| 10 MS/s | 0 | 0 |
| 15 MS/s | 0 | 0 |

Thus the long-recording inventory cannot answer whether 10 or 15 MS/s improves
phase quality. Existing high-rate products are short retuned visits. Comparing
those captures with long 2.5 MS/s recordings would confound sample rate,
source, tuning, time, and receiver state. A useful bandwidth test would process
the same high-rate IQ both at full bandwidth and through a frozen 2.5 MHz
filter; it is a separate short-visit test, not a substitute for continuity.

## Shortlist

All listed recording streams are 60.000 s, 2.5 MS/s, 2.5 MHz applied
bandwidth, 150,000,000 samples, and contain RX0 and RX1. For every stream,
`iter_timeline_metadata()` returned 573 refills with adjacent source sequence
and device-sample counters, zero missing samples, zero observed overflow, and
no timeline discontinuity.

| Priority | Session | Existing phase-blind/common-source support | Why retained |
| ---: | --- | --- | --- |
| 1 | `cap-20260825T065355-ba3e4fb8857b` | 14.864 s, 1,806 observations, 51/64 pilots | Longest and strongest retrospective overlap; use one radio's RX0/RX1 because the two radios have a recorded start skew. |
| 2 | `cap-20260825T031521-ec8adc0e9426` | 11.000 s, 1,365 observations, 45/64 pilots | Freshest strong continuous candidate and preferred new extraction. |
| 3 | `cap-20260825T105915-2770b84587cc` | 7.05 s continuous two-source overlap; 650/704 accepted 20 ms estimates | Existing same-radio, common-sample phase extraction makes this the cheapest source-quality diagnostic; identity/edge caveats prevent a geometric claim. |

`cap-20260825T115401-774be9e8b225` is an alternate with 11.825 s overlap,
1,920 observations, and 47/64 pilots. It was not selected because its
cross-band pairing adds a frequency-dependent receiver-chain phase nuisance.

The 43--45 s spans reported for scan-hop sessions are not continuous dwells:
they combine roughly 120 ms visits separated by 1.7--5.1 s retunes. They are
excluded from the shortlist even when their first-to-last timestamps are long.

## Bounded next extraction

Use 031521 first. Before reading IQ, freeze one same-radio stream, two source
tracks, the exact common-time window centers, templates, carrier models, and a
seeded random split of whole non-overlapping windows. Extract at most sixteen
20 ms windows distributed across the existing 11 s overlap (320 ms total IQ).
Require both sources in both receivers at every center and preserve all pilot
control failures as abstentions.

For each accepted center form the receiver/source phases independently, restore
their frozen model-coordinate phase at the common physical time, and form the
circular double difference

$$Z(t)=\operatorname{wrap}[(\delta_{1A}-\delta_{0A})-(\delta_{1B}-\delta_{0B})].$$

Fit an unknown baseline vector only on training windows, with its norm bounded
by the operator-provided 0.10--0.30 m range. Score held windows without phase
unwrapping against frozen candidate motion and wrong-time, candidate-swap, and
template-roll controls. Report design-matrix rank/condition, circular held
loss, control losses, and abstention. This is a conditional candidate-motion
consistency test. It cannot determine receiver pose, position, or satellite
identity without additional authority.

If 031521 does not furnish four simultaneous pilot-qualified branches, stop and
use 105915 to verify the scoring path; do not tune extraction on 031521 and then
describe 105915 as fresh validation. Confirmatory replication, if warranted,
is 065355 with the same frozen analysis.

## Reproduction and provenance

Run:

```bash
sudo -n env PYTHONPATH=src:tools:. PYTHONDONTWRITEBYTECODE=1 \
  OPENBLAS_NUM_THREADS=1 \
  /opt/leo-tracker/current-api/.venv/bin/python \
  tools/research/inventory_historical_continuous_dual_rx.py
```

The machine-readable output is
`reports/figures/2026_09_23_historical_continuous_dual_rx_inventory/inventory.json`.
It records manifest digests, applied settings, device-counter bounds, and the
timeline checks. Source-overlap counts for 031521 and 065355 come from
`reports/2026_08_25_post_refill_24h_retrospective/capture-analysis-inventory.csv`;
the 105915 phase support comes from
`reports/2026_09_16_dual_rx_pilot_phase.md`.
