# Per-recording Starlink TLE candidate review: RX0 10 MS/s

This review uses the same **47 sealed recordings from September 14, 2026,
15:28–23:28 UTC** as the
[eight-hour scanner report](2026_09_14_eight_hour_rx0_10msps_pss_glrt_tle.md). The radio is
`104000bac4950008230026001b440a003a`, physical RX0, at 10 MS/s. It uses retained
IQ and archived Space-Track element sets; no new RF collection is involved.

**The data support candidate shortlists, not confirmed satellite identities.**
A single recording can contain several transmitters and several competing
interpretations of a track. Assigning one satellite name to each file would
overstate what these measurements establish.

All **47 recordings** were screened, covering **647 eligible unique tracklets**.
Of these, **526** pass the descriptive checks below, with at least one in each
recording. These counts are correlated tracklets, not satellite counts. The
three stronger audits all abstain. All 47 per-recording PNGs and evidence
archives are included; there are no unavailable recordings in this review.

The [per-recording index](figures/2026_09_15_rx0_10msps_recording_tle_review/README.md)
links each UTC timestamp and recording ID to its complete track table, measured
CFO/TLE overlays, residual plots, top-three training candidates, heldout rank,
negative-control assessment, and downloadable evidence. The
[machine-readable summary](figures/2026_09_15_rx0_10msps_recording_tle_review/summary.json)
contains final coverage and diagnostic counts.
The [element-set identities](figures/2026_09_15_rx0_10msps_recording_tle_review/shortlist-element-identities.json)
pin shortlisted NORADs to their precise element epochs and pair digests, and
[provenance](figures/2026_09_15_rx0_10msps_recording_tle_review/provenance.json)
records the source-code hashes and numerical-library versions.

## What a candidate match means

Measured fractional GLRT observations are reconstructed into alias-aware tracks
**before opening the catalogue**. The source stream is native 10 MS/s; the
offline analysis uses one 20 ms probe per complete 120 ms visit. These are
sparse observations of a recording, not continuous carrier tracking.

Every unique reconstructed track with at least 20 observations and at least
20 seconds between its first and last observation enters the exploratory
screen. Alternative global hypotheses can share tracks; shared track IDs are
screened once. Cross-channel tracklets remain correlated and their counts
must not be interpreted as independent detections.

For each recording, the latest archived catalogue collected before the earliest
wrong-time prediction opportunity is selected. The observer is the previously
configured Spinnaker, Sausalito site. Source and catalogue digests, site
coordinates, and exclusions are retained in each recording's evidence.

A coarse orbital grid identifies possible horizon-visible candidates. Each
candidate is then propagated with SGP4 at **every observation center** for each
integer time shift from −5 through +5 seconds. Scoring uses those exact-time
predictions, not interpolation of the coarse grid. Doppler and observations
share the 11.2 GHz RF reference. This screen uses observation centers rather
than integration over each 20 ms measurement support.

The first 60% of observations select the candidate, time shift, and one constant
carrier offset. The final 40% is scored without refitting. The offset absorbs
unknown carrier/receiver bias and absolute alias choice; it is not a measured
oscillator calibration. Each candidate is allowed the same fitting opportunity.
No measured CFO slope is fitted into the orbital model.

The trajectory detector has already used the whole recording before this split.
Heldout therefore applies to catalogue/offset fitting, not to a fully prospective
validation of the detector and track-selection pipeline.

The screen also fits independent catalogues at −500 and +500 seconds and linear
and quadratic radio-drift models. A descriptive pass requires the training
leader to remain first on heldout data, no exact candidate tie, no time-shift
boundary, horizon visibility throughout measured support, and a lower heldout
RMS than both wrong-time leaders and both radio models. Small score margins
remain small evidence; these criteria do not supply a calibrated probability.

## Why some existing catalogue products were unavailable

The strict matcher rejects an incomplete catalogue propagation. For example,
the catalogue used for `scan-hop-24e4b051b0fbc5ca` contains SGP4-error-6 objects
`STARLINK-34343 DEB` (NORAD 69730) and `STARLINK-37793` (NORAD 100286). Excluding
only objects labelled debris therefore does not resolve that failure.

This research screen records all orbital-only exclusions: failed propagation,
implausible altitude, or labelled debris. These checks cover the whole recording
and wrong-time fields, without consulting measured signal fit. **The resulting
shortlist is conditional on the propagatable catalogue subset.** It does not
claim that excluded objects could not have transmitted, and it does not rewrite
the production pipeline's stricter completeness policy.

## A stronger audit of three promising examples

The first three chronologically available recordings among the original 41
complete analyses with descriptive passes were selected for a second check,
using the longest passing track in each. The six later backfills did not change
that frozen audit selection.
This is a post-hoc audit of examples, not an independent validation cohort.
The existing covariance-aware, support-integrated matcher uses the same
orbital-only exclusions and its established chronological/wrong-time controls.

| Recording | Screen and stricter matcher leader | Track support | TLE heldout negative log score | Best radio-model score | Stricter conclusion |
|---|---:|---:|---:|---:|---|
| `scan-hop-24e4b051b0fbc5ca` | NORAD 60413 | 36.80 s | 120.73 | 115.27 | Abstain |
| `scan-hop-c2313aebc38416ef` | NORAD 63795 | 50.41 s | 174.94 | 156.48 | Abstain |
| `scan-hop-499abcb9ca352397` | NORAD 63780 | 38.97 s | 137.00 | 129.65 | Abstain |

Lower negative log score is better; compare models within a row, not across
rows with different support. All three leaders remain first on heldout data,
but all three fail `radio-polynomial-null-not-worse-on-heldout`.

The simple RMS screen and the stricter matcher answer different questions.
RMS describes curve agreement; the stricter predictive score includes the
declared covariance and nuisance uncertainty. A lower RMS alone does not prove
that the orbital explanation is better supported than receiver drift.
The [full audit evidence](figures/2026_09_15_rx0_10msps_recording_tle_review/deep-checks/README.md)
preserves all candidate and control scores.

## Limits and reproduction

PSS detections are not used as identity evidence. The current PSS engine's
pilot-only false tracks remain an unresolved qualification issue. GLRT aliases,
receiver drift, multipath, short nearly linear arcs, catalogue errors, and
unknown antenna illumination can all create plausible orbital matches.
Repeated labels on nearby RF lanes are useful diagnostics, not independent
confirmation. Neither TLE visibility nor a matching Doppler slope demonstrates
that a particular satellite transmitted the recorded waveform.

The scripts operate through read-only capture adapters and separate research
outputs. Six initially missing offline analyses are backfilled separately;
the original eight-hour production snapshot is preserved. Published evidence
contains capture/analysis/catalogue digests and exact per-recording dispositions.

```bash
PYTHONPATH=src:. OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python \
  tools/review_rx0_scanner_tles.py \
  --sessions reports/figures/2026_09_14_eight_hour_rx0_10msps_pss_glrt_tle/sessions.csv \
  --analysis-root /srv/bulk/leo/experiments/20260915-rx0-tle-review/analysis \
  --output /tmp/rx0-tle-review-fresh
PYTHONPATH=src:. OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python \
  tools/review_rx0_scanner_tles.py \
  --sessions reports/figures/2026_09_14_eight_hour_rx0_10msps_pss_glrt_tle/sessions.csv \
  --output /tmp/rx0-tle-review-fresh
PYTHONPATH=src:. python tools/validate_scanner_tle_screen.py /tmp/rx0-tle-review-fresh
PYTHONPATH=src:. python tools/publish_scanner_tle_review.py \
  /tmp/rx0-tle-review-fresh /tmp/rx0-tle-report
```

`backfill_scanner_review_metrics.py` handles missing analyses into an explicit
research root; `review_rx0_scanner_tles.py --analysis-root` reads those products.
The six backfilled products are retained under the research root above. The
second invocation fills the other 41 from the production analysis store,
reusing the six successful screens. Error records are retried; successful
screens are cached, so use a fresh destination when changing the method.
The published evidence pins each analysis digest separately.
`check_scanner_tle_shortlist.py` reproduces the three post-hoc stronger checks;
their recording IDs are frozen in the tool so later backfill cannot change the
audit cohort.
