# PSS versus fractional GLRT on recent dual-RX 10 MS/s scans

## Result

Yes, this repository has previously applied the published Starlink PSS to
recorded IQ and compared PSS-derived Doppler-rate point estimates with the
20 ms known-pilot GLRT.  The August 25 multi-dwell study found that PSS was
useful for frame timing, but all 10 PSS rate-fit 95% intervals included zero.
The median absolute PSS-minus-GLRT rate difference was 1.549 kHz/s, with
2.633 kHz/s RMSE and 9/10 sign agreement.  That result did not support PSS as
a standalone Doppler-rate estimator.

The same exact published PSS construction has now been replayed against ten
recent dual-receiver 10 MS/s scanner recordings.  PSS recovered a frame epoch
within 2 microseconds of the independently selected fractional-GLRT epoch in
12/20 receiver-visits: 9/10 on RX0 and 3/10 on RX1.

The raw PSS frequency maximum is not on a uniquely resolved absolute-frequency
branch.  The 12 raw PSS-minus-GLRT differences have 345.645 kHz median absolute
error and 410.607 kHz RMSE.  All are close to integer multiples of 113.636 kHz,
which is one half of the 4.4 microsecond symbol-frequency spacing.  This is a
PSS likelihood sidelobe/branch effect, not evidence for a 346 kHz physical
Doppler disagreement.

When the PSS result is lifted to the nearest 113.636 kHz branch using GLRT, the
12 paired frequency residuals have:

- 3.399 kHz median absolute error;
- 6.134 kHz RMSE;
- -2.625 kHz median signed error; and
- 16.555 kHz maximum absolute error.

That branch-conditioned comparison shows useful local frequency consistency,
but it is not an independent absolute-frequency validation because GLRT chooses
the PSS branch.  Both values are observed receiver CFO, containing receiver/LNB
frequency error as well as propagation Doppler; they are not isolated
spacecraft Doppler.

## Frozen cohort and method

The cohort is the ten latest completed, figure-ready, dual-RX **10 MS/s** scans
in the previously frozen eight-hour review window.  Alternating 2.5 MS/s scans
were excluded.  For each recording and receiver, the strongest candidate that
passed the persisted 120 ms fractional-GLRT margin gate was selected before PSS
was evaluated.  Therefore, the acquisition percentages describe a
GLRT-positive, post-hoc comparison cohort and not all scanner visits.

For each of the 20 selected visits, the replay:

1. reads the immutable recorded IQ through the read-only adaptive-hop store;
2. projects the exact Humphreys-equations-35--37 PSS onto the recorded 10 MHz
   edge slice using the recorded tuning geometry;
3. performs blind PSS acquisition over -1.2 to +1.2 MHz in 200 kHz steps;
4. accepts only qualified PSS modes whose folded frame epoch is within 2
   microseconds of the fractional-GLRT epoch; and
5. refines the PSS frequency over +/-120 kHz in 2 kHz steps before a
   log-parabolic peak interpolation.

PSS did not participate in recording selection or GLRT candidate selection.
GLRT epoch is used as an explicit timing confirmation gate.  In the optional
branch-conditioned statistic, GLRT is also used to choose the nearest PSS
frequency branch.

## `scan-fw-506bf7282490266d`

RX0 produced an aligned PSS result on channel 2 upper edge:

| quantity | value |
|---|---:|
| GLRT CFO | +64.101 kHz |
| raw PSS CFO | -280.264 kHz |
| PSS epoch error from GLRT | -0.328 microseconds |
| raw PSS - GLRT | -344.365 kHz |
| selected PSS branch lift | -3 x 113.636 kHz |
| branch-conditioned PSS - GLRT | -3.456 kHz |

RX1 did not yield a qualified PSS epoch within the 2 microsecond gate for its
selected visit.  Its selected GLRT candidate was weak (fractional margin
0.0443), so this is not evidence that PSS systematically fails on RX1; the
aggregate RX1 recovery rate is nevertheless materially lower and merits a
larger frozen-cohort follow-up.

## What can and cannot be compared

The 120 ms visits contain roughly 90 PSS frames, enough for one same-visit CFO
estimate.  They do not recreate the earlier six-second, one-estimate-per-second
PSS Doppler-rate experiment.  Repeated random scanner visits can contain
different spacecraft, so joining their CFO points into a rate without a
persisted signal identity would be scientifically invalid.

The defensible conclusion from this replay is therefore:

- PSS frame timing corroborates GLRT in 12/20 selected receiver-visits;
- after GLRT resolves the PSS sidelobe branch, local CFO agrees at the
  few-kilohertz level;
- raw PSS absolute frequency is not independently branch-resolved; and
- no new PSS Doppler-rate claim is supported by these 120 ms scanner visits.

## Artifacts

- `figures/2026_09_25_dual_rx_10msps_pss_glrt/paired-estimates.csv`
- `figures/2026_09_25_dual_rx_10msps_pss_glrt/summary.json`
- `figures/2026_09_25_dual_rx_10msps_pss_glrt/pss-vs-glrt-cfo.png`
- `figures/2026_09_25_dual_rx_10msps_pss_glrt/analyze.py`

The historical comparison is documented in
`reports/2026_08_25_multi_dwell_pss_sss_doppler.md`.
