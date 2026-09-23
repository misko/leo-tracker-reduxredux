# Eight-hour RX0/RX1 GLRT baseline before array rotation

Date: 2026-09-23. Radio: `radio_pluto_19f2` (r21).
Capture-start window: **2026-09-23 06:39:14 UTC inclusive to 14:39:14 UTC exclusive**.
This report audits existing recordings. No RF collection or production settings
were changed to produce it.

## Baseline counts

| Capture sample rate | RX0 GLRT detections | RX1 GLRT detections | Analyzed / captured recordings |
| --- | ---: | ---: | ---: |
| 2.5 MS/s | 5,674 | 21,552 | 13 / 15 |
| 10 MS/s | 9,693 | 25,275 | 16 / 17 |
| 15 MS/s | 4,960 | 18,164 | 16 / 16 |
| **Total** | **20,327** | **64,991** | **45 / 48** |

A detection is a complete fractional GLRT candidate passing the **0.025 margin
gate**, before trajectory reconstruction or long-track selection. Multiple
passing candidates in a probe are counted individually. Repeated detections
are not independent satellites, tracks, or receiver-position fixes.

All 48 recordings completed, had attested source spans, and retained all their
completed visits. Each capture spans 300 seconds; the window contains 240
minutes of capture time, of which 225 minutes have complete analyzed products
in this frozen audit. There were no fixed-hop captures in the window.

## Exposure-normalized comparison

The two receivers have identical probe counts within each rate. Across rates,
recording counts and probe counts differ, so use normalized measures as well
as raw counts for the rotation comparison.

| Rate | Probes per RX | RX0 detections / 1,000 probes | RX1 detections / 1,000 probes | RX0 probes with >=1 detection | RX1 probes with >=1 detection | RX0 / RX1 detection ratio |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 2.5 MS/s | 28,808 | 196.96 | 748.13 | 11.91% | 32.72% | 0.263 |
| 10 MS/s | 35,663 | 271.79 | 708.72 | 11.22% | 31.35% | 0.384 |
| 15 MS/s | 25,935 | 191.25 | 700.37 | 7.93% | 31.59% | 0.273 |

RX0 is lower at all three rates in this baseline. This alone does not establish
whether the cause follows a receiver/LNB chain or its physical orientation.
Per-probe detection multiplicity and the fraction of probes with any detection
are different measurements; both are retained for tomorrow's comparison.

## Analysis coverage and verification

The following completed captures did not have complete GLRT publications at
audit time. They are excluded from the totals, not counted as zero detections.

| Capture start (UTC) | Session | Rate | Analysis state at audit |
| --- | --- | ---: | --- |
| 2026-09-23 14:10:01.924 | `scan-fw-25454cd8b0e8d9d1` | 10 MS/s | Metrics incomplete |
| 2026-09-23 14:20:08.431 | `scan-fw-ab751e645872510a` | 2.5 MS/s | Analysis publication absent |
| 2026-09-23 14:30:28.399 | `scan-fw-1aa1d50103d97388` | 2.5 MS/s | Analysis publication absent |

The audit used the read-only scanner storage adapters. It validated capture
bindings, sealed visit products, visit inventory and digests against each
metrics manifest. Summed per-receiver passing-candidate counts independently
reconciled to the manifest totals; acquired-candidate totals also reconciled.
Only the binding selected by the current production analysis policy was counted,
so historical analysis versions do not duplicate detections. Every completed
analysis used the 0.025 gate and a 20 ms probe with 120 ms stride.

The evidence is a frozen publication snapshot. Later completion of these three
analyses should produce a separately labeled baseline revision; preserve these
original totals and CSV rather than silently replacing them.

## 180-degree rotation experiment

At approximately **2026-09-23 14:44 UTC**, the operator stated an intention to
rotate the array 180 degrees immediately. This is the announcement/log time,
not a measured completion timestamp. Completion time, rotation axis, and
unchanged cable-to-LNB connections were unconfirmed when the baseline was published.
See the [station geometry observation log](../deploy/station/GEOMETRY_NOTES.md).

**Completion update:** the operator subsequently confirmed "i just rotated the
array 180deg", logged at **2026-09-23 14:49:09 UTC**. Use that confirmation time
as a conservative post-rotation boundary; the precise physical completion time
was not measured. Exclude captures overlapping the approximate 14:44:00–14:49:09
UTC transition interval. Rotation axis and cable continuity remain unconfirmed.

The intended test is whether the lower detection yield stays with **RX0** or
changes receiver after rotating the physical array. Keep electrical receiver
labels tied to their original LNBs and cables for that interpretation. A cable
swap would be a different intervention and must be logged separately.

On **2026-09-24**, compare existing recordings whose entire capture intervals
are after confirmed rotation completion. Prefer the same eight-hour UTC window
(06:39:14 to 14:39:14) for a first matched comparison, once its analysis finishes.
This is a comparison plan, not a scheduled job or authorization for a new
overnight collection campaign.

1. Record the completion boundary and exclude captures overlapping array movement
   or an uncertain transition interval. Verify physical cable mapping.
2. Reuse the same candidate-count definition, gate, analysis policy and
   per-rate RX0/RX1 table. Report complete/pending analysis coverage explicitly.
3. Compare detections per 1,000 evaluated probes and the fraction of probes with
   any passing detection, alongside the RX0/RX1 ratio. Break down by RF target
   and per recording when possible so different target exposure does not masquerade
   as a receiver change. Re-read baseline products if target-level detail is needed;
   the saved CSV aggregates each recording across targets.
4. Check gain, tuning/target distribution, sample rates, firmware/analysis
   revisions, mounting height/tilt, and obstruction changes. Same UTC window
   does not guarantee identical satellite geometry or signal activity.
5. If RX0 remains lower, that supports an effect tied to its receiver/LNB/cable
   chain. If the asymmetry reverses and RX1 becomes lower, that supports an
   orientation/site effect. Either outcome is evidence, not a diagnosis; mixed
   or rate-specific changes require further separation of these factors.

## Evidence and reproduction

- [Per-recording CSV](figures/2026_09_23_eight_hour_glrt/per-recording.csv)
- [Complete audit evidence](figures/2026_09_23_eight_hour_glrt/evidence.json)
- [Recording inventory script](figures/2026_09_23_eight_hour_glrt/scan_8h_inventory.py)
- [Verified GLRT counting script](figures/2026_09_23_eight_hour_glrt/scan_8h_counts.py)

With a production-compatible project environment and read access to scan storage:

```bash
PYTHONPATH=src .venv/bin/python reports/figures/2026_09_23_eight_hour_glrt/scan_8h_inventory.py \
  --end-utc 2026-09-24T14:39:14Z --hours 8 --output /tmp/rotation-next-day-inventory.json
PYTHONPATH=src .venv/bin/python reports/figures/2026_09_23_eight_hour_glrt/scan_8h_counts.py \
  --inventory /tmp/rotation-next-day-inventory.json --output /tmp/rotation-next-day-counts.json
```

These scripts analyze saved publications only and do not start acquisition or
GLRT processing. Unavailable analysis remains explicit. The counting script
currently handles adaptive recordings; if fixed-hop recordings enter a future
inventory it reports them as unsupported rather than silently dropping them.
The script wrappers were parameterized after this audit; the counting logic
and archived evidence are unchanged. Re-running later can see more complete
analysis publications than this frozen audit did.
