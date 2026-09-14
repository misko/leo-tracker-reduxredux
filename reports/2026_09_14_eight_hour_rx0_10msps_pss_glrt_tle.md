# Eight-hour RX0 10 MS/s adaptive scanner: GLRT, timing, Doppler, and TLE evidence

This report freezes scanner captures whose first-sample UTC estimate lies in
**2026-09-14 15:28:00 UTC through 23:28:00 UTC, end exclusive**. It analyzes the
existing corpus only. Production acquisition was left running. The cohort is
one radio, serial `104000bac4950008230026001b440a003a`, physical RX0, at
10,000,000 complex samples/s. All 47 sealed captures in the window satisfy those
bindings and have qualified host-bracketed device-counter UTC.

The strongest supported conclusions are:

* 47 of 48 ten-minute opportunities produced sealed 300-second sessions. Median
  valid source-counter duty was **95.2415%** (session bootstrap 95% interval
  **95.2382–95.2472%**), for **13,431.96 s** of valid IQ. One run failed at about
  17:21:47 UTC after 718 events with SPF error `-84`; its unsealed spool remains
  separate and is excluded from numerical analysis.
* Online, decimated GLRT feedback called 77,792 of 111,933 complete visits
  detected (**69.50%**). This is an adaptive, correlated sequence and is not an
  unbiased probability of detection.
* Forty sessions had completed offline trajectory products: **1,492 GLRT
  tracklets and 32,101 associated CFO observations**. The median tracklet RMS
  about its own local linear CFO model was **205.44 Hz**; the 10th–90th percentile
  range was **58.72–733.21 Hz**. The median session-pooled RMS was **470.38 Hz**
  (session bootstrap 95% interval **430.14–496.44 Hz**). These are fit residuals,
  not calibrated error against a known carrier.
* Five sessions completed TLE scoring and yielded 20 candidate rows. **All 20
  recommend abstention and all 20 fail the radio-polynomial heldout control.**
  No row claims identity. Thirty-five other trajectory products could not score
  a catalogue because population propagation was incomplete. The data support
  Doppler-like trajectories, but no satellite identification.
* The production cohort has **zero PSS products**. It is therefore impossible to
  construct a matched PSS-versus-GLRT comparison for these eight hours without
  introducing a new, unvalidated replay method. The retained September 12
  five-dwell experiment supplies the honest historical paired comparison.

![Capture duty and online detections](figures/2026_09_14_eight_hour_rx0_10msps_pss_glrt_tle/capture-duty-and-detections.png)

## Cohort and coverage

The expected slots are 15:30 through 23:20 UTC at ten-minute spacing. Forty-seven
sealed sessions cover all slots except 17:20. The successful sessions contain
111,933 complete 120 ms visits, with 1,108–2,078 online detections per session
(median 1,690). Median first-sample UTC bracket width was 1.269 ms and the maximum
was 1.730 ms. That UTC authority is adequate to place observations on the TLE
time axis, but it is far wider than nanosecond-scale receiver-relative timing
residuals and cannot establish absolute time of arrival at that scale.

The 17:20 attempt, `scan-hop-7c83550dd510d00f`, failed after 718 events. The
journal records `SPF hop scheduler failed: error=-84` and
`Invalid or incomplete multibyte or wide character`. It remains an unsealed NVMe
spool and is excluded because it has no terminal capture manifest. The remaining
47 captures total **346.52 GiB compressed**. Queue telemetry shows no evidence
that analysis changed acquisition; the analysis worker ran separately at low
CPU/I/O weight.

At report generation, 38 of 47 captures had the complete seven-PNG presentation
set, 40 had tracking products, and 41 had controlled-refinement products. The
remaining items were analysis completeness gaps, not missing sealed IQ. The
frozen [PNG inventory](figures/2026_09_14_eight_hour_rx0_10msps_pss_glrt_tle/png-inventory.csv)
names them explicitly.

## GLRT detection and Doppler/CFO evidence

Each radio visit records native 10 MS/s RX0 IQ. The real-time decision path
applies a fixed 161-tap Q15 decimator by four, then runs six 20 ms screens at
2.5 MS/s and at most one confirmation. This confines decision compute while
retaining the wider native stream for replay. `feedback_outcome=detected` is the
online count used above. It depends on the adaptive scheduler's preceding state,
the chosen channel, and repeated views of the same signal; it is not an
independent Bernoulli trial.

The offline overview analyzes one 20 ms fractional GLRT probe per complete
120 ms visit. It therefore samples one sixth of retained IQ time, or about 15.9%
of wall time after multiplying by measured capture duty. Unsampled intervals are
not interpolated. This sparse analysis is a major reason that the plotted
detection/trajectory evidence looks thinner than dense short-dwell reports even
though the native recording duty is high.

For trajectory construction, CFO is scaled to a canonical 11.2 GHz RF reference.
The persisted algorithm searches weighted Hough lines, unwraps relative aliases
at the configured 227.273 kHz spacing, then refines a local straight line. Each
tracklet spans at least 8 s, uses at least 8 points, allows at most 2 s gaps, and
uses a 2.5 kHz residual gate. `residual_rms_hz` is the RMS of de-aliased CFO
points around that fitted local line. It is not the RMS of raw absolute CFO and
does not resolve the absolute alias.

Across 40 completed products, the median normalized local rate was
**−3,706.88 Hz/s**. The broad residual distribution is expected from sparse
adaptive visits, mixed physical emitters, multipath, false associations, and
piecewise rather than full-pass linearity. A rate in the satellite-like range
does not establish an orbit.

![GLRT rate and fitted residuals](figures/2026_09_14_eight_hour_rx0_10msps_pss_glrt_tle/glrt-tracklet-rate-residuals.png)

The session-pooled statistic is
`sqrt(sum(observation_count * tracklet_RMS^2) / sum(observation_count))`.
Its confidence interval resamples completed sessions 5,000 times, preserving the
session as the dependence cluster. The tracklet percentile range is descriptive;
points within a tracklet and repeated adaptive visits are correlated.

The closest recent carrier baselines are deliberately favorable and much shorter:
the September 12 paired five-dwell report found alternating-heldout quadratic CFO
residuals of **4.79–43.35 Hz** at native 25 MS/s and **4.95–44.01 Hz** on the
same-ADC 2.5 MS/s downsample. A separate report found **13–28 Hz** on selected
50–75 ms local pilot windows. Those values are not directly comparable to the
present 8–50 s sparse Hough associations. The current 205 Hz tracklet median and
470 Hz session-pooled median show the cost of the actual long-scan association
problem; they do not show that 10 MS/s intrinsically worsens the carrier
estimator.

## Timing evidence and raw-versus-fitted residuals

The current production profile publishes fractional GLRT epoch estimates, but
it does not publish a continuous absolute time-of-arrival truth series. The
direct current-window timing check is instead the bounded shift-recovery product:
16 stored-IQ probes per session receive known synthetic frequency or delay
perturbations and are compared with their same-probe baseline. Forty-one sessions
had completed this product at generation time.

For the injected-delay case, 298 common probes out of 656 attempts were recovered
by all four profiles. Pooled delay recovery RMS was **2.537 ns** for joint512,
**2.925 ns** for local512, **2.927 ns** for grid512, and **3.094 ns** for grid8192.
For the injected-frequency case, 303/656 common probes yielded delay self-
consistency RMS of **0.938 ns** for joint512, **1.070 ns** for local512,
**1.070 ns** for grid512, and **1.688 ns** for grid8192. These are conditional
relative recovery errors on the common recovered subset, not absolute UTC
accuracy, general detection timing RMS, or independent samples.

The frequency-injection results expose why raw and alias-folded RMS must remain
separate. One alias change makes the pooled raw CFO RMS about **13.05–13.06 kHz**
for all profiles. After folding by the declared alias interval, the RMS is
**5.268 Hz** for joint512, **5.300 Hz** for local512, **15.287 Hz** for grid8192,
and **26.519 Hz** for grid512. Reporting only the folded value would hide the
one branch error; reporting only raw RMS would hide the otherwise precise local
recovery. In the injected-delay case there were no alias changes, so raw and
folded CFO RMS agree; joint512 was **1.285 Hz**.

![Controlled refinement RMS](figures/2026_09_14_eight_hour_rx0_10msps_pss_glrt_tle/controlled-refinement-rms.png)

## PSS and the matched historical comparison

No PSS analyzer ran on these production sessions and no PSS product is persisted.
The 10 MHz edge recording is usable for some partial-band PSS experiments, but
the production adapter and acceptance policy were not validated for this cohort.
Running a new search now would create a method-selected post-hoc result rather
than the requested matched production comparison.

The September 12 five-dwell experiment remains the strongest matched evidence.
It used the same ADC at native 25 MS/s and a derived 2.5 MS/s stream, plus a
separate 2.5 MS/s radio. On alternating-observation quadratic fits:

| Measurement | Five-dwell RMS range | Conditioning |
|---|---:|---|
| Native 25 MS/s PSS | 3.18–5.12 ns | causal accepted points after explicit ±120 ns prediction gate; 71.41–99.57% accepted |
| Native 25 MS/s fractional GLRT | 10.53–11.94 ns | 215–224 completed refinements of 224 |
| Same-ADC derived 2.5 MS/s fractional GLRT | 21.34–26.27 ns | 207/207 completed in each dwell |
| Other-radio 2.5 MS/s fractional GLRT | 21.02–33.02 ns | 223/223 completed in each dwell |

![Historical unmatched timing comparison](figures/2026_09_14_eight_hour_rx0_10msps_pss_glrt_tle/historical-pss-glrt-timing-comparison.png)

The PSS figure is labeled historical and unmatched. Its 3–5 ns result is
conditional repeatability after a causal outlier gate, not absolute arrival-time
accuracy. The GLRT and PSS estimators also use different cadence, aperture, and
selection. The paired experiment supports wideband PSS for precise frame timing
and narrowband GLRT for carrier tracking; it does not provide a universal ratio
or a direct 10 MS/s PSS number.

## TLE correlation and association limits

All current captures have qualified UTC, so UTC itself did not block catalogue
matching. The eligible snapshot contained about 11,128 objects and was collected
a median **55.52 minutes** before the associated captures. Across 40 trajectory
products there were 1,071 eligible physical groups, 159 attempted groups, and
113,096 projected candidates. The four-group per-session work bound intentionally
defers most eligible groups.

Five sessions at 19:10, 19:30, 19:40, 19:50, and 20:00 UTC completed four
catalogue comparisons each. Each row considered 470–505 nominal candidates.
Although several training leaders remained first on heldout data and beat the
±500 s wrong-time controls, **the radio-polynomial null was not worse on heldout
data for every one of the 20 rows**. Six also lost their catalogue leader on
heldout data; six had heldout-rank instability; three hit the searched time-shift
boundary; and five failed at least one wrong-time control. Therefore all 20 rows
recommend abstention, and the reported NORAD numbers are diagnostic candidates,
not identifications.

The other 35 products ended `tle_state=unavailable` with
`PersistentHopTleMatchInputError: catalogue population propagation is incomplete`.
This is a catalogue pipeline failure after trajectories were reconstructed, not
evidence that the trajectories were absent. The full diagnostic rows are frozen
in [tle-candidates.csv](figures/2026_09_14_eight_hour_rx0_10msps_pss_glrt_tle/tle-candidates.csv).

## What 10 MS/s helps and hurts

10 MS/s helps the operational scanner in three measured ways. It permits one
connected receiver to sustain the stream comfortably; the bounded 30 s transport
test measured 100% RX0 counter duty, compared with 61.560149% when both receivers
were streamed at 10 MS/s each. It preserves four times the sample density of the
2.5 MS/s decision path for later fractional timing and local CFO refinement. It
also retains more partial-band waveform bandwidth, which historical PSS work
shows can matter strongly for timing peak quality.

It does not make sparse analysis dense. The automatic offline view still uses
one 20 ms probe per 120 ms visit, and the real-time decision intentionally
decimates to 2.5 MS/s. It also costs storage and compute: this window produced
346.52 GiB compressed, and only 38/47 full seven-PNG sets were complete by report
generation. The 10 MS/s rate cannot recover the approximately 240 MHz full
channel, cannot by itself resolve carrier aliases, and cannot turn millisecond
host UTC brackets into nanosecond absolute timing.

The matched historical carrier experiment found nearly identical CFO residuals
at native 25 MS/s and its same-ADC 2.5 MS/s downsample, while timing degraded at
the narrower rate. That supports the present split: preserve native 10 MS/s IQ
for timing/refinement, decimate for real-time decisions, and interpret Doppler
quality from measured residuals rather than sample rate alone.

## Prior reports reviewed

This analysis reconciles the relevant reports retained during the preceding five
days:

* [Timing, frequency resolution, and FPGA review](2026_09_12_timing_frequency_resolution_and_fpga_review.md)
  for PSS/GLRT definitions, prior RMS values, UTC cautions, and transport duty.
* The retained `reports/2026_09_12_fpga_branch_review_and_simpler_tracking_plan.md`
  research artifact for the historical 8.59/8.31 ns cabled PSS result and
  selected native/downsampled estimator differences.
* The retained `reports/2026_09_12_rx0_10msps_30s/README.md` and
  `reports/2026_09_12_dual_rx_10msps_30s/README.md` research artifacts for the
  100% versus 61.560149% transport comparison.
* [Saved-IQ coverage review](2026_09_13_radio20_saved_iq_coverage.md) for the
  conditional nature of phase/Doppler claims.
* [Five 300 s 30 MS/s tracking captures](2026_09_14_radio20_five_300s_30ms_tracking.md)
  as a separate high-rate acquisition comparison; those captures had 89.62%
  nominal RF duty and four of five acquisition failures and are not pooled here.
* `/srv/bulk/leo/experiments/paired-five-glrt-pss-tle-20260912-v4/report.md`
  for the matched five-dwell PSS, fractional GLRT, carrier, and historical TLE
  experiment.

## Reproduction and frozen artifacts

Run the analysis with the production Python environment, which supplies NumPy
and Matplotlib:

```bash
sudo /opt/leo-tracker/current-api/.venv/bin/python \
  reports/figures/2026_09_14_eight_hour_rx0_10msps_pss_glrt_tle/analyze_window.py \
  --output reports/figures/2026_09_14_eight_hour_rx0_10msps_pss_glrt_tle
```

The script selects by `timing.first_sample_estimate_utc_ns`, never directory
mtime. [summary.json](figures/2026_09_14_eight_hour_rx0_10msps_pss_glrt_tle/summary.json)
contains the aggregate values and bootstrap intervals. `sessions.csv`,
`tracking-sessions.csv`, `tracklets.csv`, `refinement-metrics.csv`,
`tle-candidates.csv`, and `png-inventory.csv` retain the rows behind the report.
[source-manifests.csv](figures/2026_09_14_eight_hour_rx0_10msps_pss_glrt_tle/source-manifests.csv)
records every source path and its declared document digest. The manifest digests,
exact UTC interval, explicit exclusions, and generated timestamp make the frozen
result auditable even as later analysis products continue to arrive.
