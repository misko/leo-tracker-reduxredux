# Verified post-fix dual-RX dwell for phase analysis

**Selected capture: `cap-20260825T010019-89c2889553e0`, stream-1, radio `192.168.1.21`, RX0 and RX1.** Recorded August 25, after the August 24 continuity-buffer deployment. This replaces the unsuitable pre-fix example as the proposed input for subsequent phase analysis.

The dwell has 60 seconds of IQ at 2.5 MS/s: **150,000,000 complex samples per receiver**. Sample-counter duty is **100% across the captured device span**. This does not mean 100% campaign duty including setup, settling or time between recordings.

| Integrity check | Result |
|---|---:|
| Hardware sample-loss observability | Enabled, continuity v2 |
| First device counter | 711533164755 |
| Last device counter, inclusive | 711683164754 |
| Counter span / observed samples | 150,000,000 / 150,000,000 |
| Refills | 573 |
| Independently checked adjacent counter transitions | 572 / 572 contiguous |
| Reported gaps / missing samples / overflows / enqueue failures | 0 / 0 / 0 / 0 |
| Kernel buffers | 8 |

The timeline was rehashed against its manifest digest and every adjacent refill was checked using `next.counter == current.counter + current.sample_count`. This is hardware-counter evidence, unlike the earlier pre-fix host-time estimate.

## Recommended interval: 31.800–32.800 seconds

Both receiver branches overlap from 21.650 through 34.275 seconds. Within the recommended one-second interval, **36 paired probes** have source-observation associations to both selected branches. The archived probe cadence is 25 ms, giving 40 potential starts per second. The four unpaired associations are detection/trajectory-selection coverage, not missing IQ.

| GLRT64 statistic on the 36 paired probes | RX0 | RX1 |
|---|---:|---:|
| Median exact-template score | 0.516 | 0.723 |
| Minimum exact-template score | 0.398 | 0.616 |
| Median control-template score | 0.0394 | 0.0455 |
| Minimum exact-minus-control margin | 0.358 | 0.576 |

This is strong simultaneous Starlink known-pilot evidence in both receivers. It does not by itself prove a unique satellite identity or broadband phase coherence; those remain analysis outputs, not selection assumptions.

The exact paired raw slice was reread with storage verification enabled: shape `(2500000, 2, 2)` for samples, receivers, and I/Q. Its SHA-256 and the source-product digests are recorded in the [verification result](figures/2026_09_22_postfix_dual_selection/verification.json). No new capture was made.

Selection was bounded and reproducible: start with the first entry in the previously published [post-fix retrospective inventory](2026_08_25_post_refill_24h_retrospective/capture-analysis-inventory.csv), take its published stream-1 paired branches, and select a one-second interval maximizing paired source-associated probe count, then its minimum GLRT margin. This is a useful example, not a claim of global optimality over the archive.

Sealed analysis run: `capture-34471d9087a94ec1b043951350de3956`. The [read-only verification script](figures/2026_09_22_postfix_dual_selection/verify.py) uses the existing research checkout's storage reader and source-association helpers at commit `660bd85a2ccb4622868f1136443c99587a216db6`:

```bash
env PYTHONPATH=/home/mouse9911/gits/leo-tracker-adaptive-geometry-phase/src:/home/mouse9911/gits/leo-tracker-adaptive-geometry-phase/tools \
  /home/mouse9911/gits/leo-tracker-adaptive-geometry-phase/.venv/bin/python \
  reports/figures/2026_09_22_postfix_dual_selection/verify.py > /tmp/postfix-dual-selection.json
```

Source manifest: `/srv/bulk/leo/recordings/2026/08/25/cap-20260825T010019-89c2889553e0/manifest.json`.
