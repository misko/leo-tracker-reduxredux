# Partial-soak QAM, pilot, and Doppler scouting report — 2026-08-19

Status: diagnostic evidence only; not a soak, calibration, detection, or WP11
acceptance receipt.

This report turns the intentionally stopped
`production-24h-20260819-01` run into an immediate software/science baseline.
It uses immutable trial evidence and bounded current-run catalog summaries. It
does not relabel the recordings or make a specificity, attribution, payload,
single-RX, centered-calibration, or endurance claim.

## Acquisition evidence

- 521 contiguous committed dual-radio sessions.
- 38,471.6 active seconds before cooperative cancellation.
- Zero failed or degraded trials and zero policy violations.
- Every session contains exactly two 150,000,000-sample radio streams
  (300,000,000 samples total in the trial receipt).
- Zero reported gaps and zero reported overflows.
- Estimated overlap fraction:
  - minimum: `0.9994009749666667`;
  - p10: `0.9999633246333334`;
  - median: `0.99999094685`;
  - p90: `0.9999986787333334`; and
  - maximum: `0.9999999792833333`.
- Inter-capture gap median/p90/maximum: 13.765 / 16.014 / 19.070 seconds.

The profile is `starlink-ch4-lower-2p5m-60s`, not the centered WP11 profile.
Each radio stream contains RX0 and RX1. Consequently these normal-workflow QAM
summaries may include the ordinary dual-receiver evidence/combination and are
not substitutes for the required centered single-RX1 comparison.

Stream identity was checked against the committed manifest:

| Scope | Radio | Serial |
|---|---|---|
| `stream-0` | `radio_pluto_5d4d` | `1040005e0b100007100010000bf33a5d4d` |
| `stream-1` | `radio_pluto_19f2` | `10400056f695001322002d0010ad1719f2` |

## Current Standard presentation summaries

All 521 sessions now have one available `qam.presentation` summary for both
streams: 1,042 stream summaries in total.

| Metric | stream-0 | stream-1 |
|---|---:|---:|
| Mean QAM accuracy | 0.6915 | 0.6820 |
| p10 | 0.2813 | 0.2821 |
| p25 | 0.4200 | 0.4142 |
| Median | 0.8050 | 0.7808 |
| p75 | 0.9263 | 0.9113 |
| p90 | 0.9588 | 0.9488 |
| Maximum | 0.9821 | 0.9825 |
| Sessions at or above 0.60 | 334 | 337 |
| Sessions at or above 0.80 | 263 | 248 |
| Sessions at or above 0.90 | 171 | 152 |

Paired-session results:

- 521 sessions contain both stream summaries;
- 195 have both streams at or above 0.80;
- 117 have both streams at or above 0.90;
- paired QAM correlation is 0.6708;
- median of the weaker stream in each pair is 0.6529; and
- best paired weaker-stream accuracy is 0.9742.

These values demonstrate abundant known-symbol QAM recovery opportunities on
both radio paths. They remain candidate-only metrics under the uncentered,
ordinary Standard pipeline.

## CFO and Doppler scouting

| Metric | stream-0 | stream-1 |
|---|---:|---:|
| Baseband CFO p10 | -219,666.9 Hz | -268,470.0 Hz |
| Baseband CFO median | -112,935.0 Hz | -159,291.3 Hz |
| Baseband CFO p90 | +359,485.1 Hz | +19,447.9 Hz |
| Doppler slope p10 | -6,221.0 Hz/s | -4,509.3 Hz/s |
| Doppler slope median | -36.0 Hz/s | -270.3 Hz/s |
| Doppler slope p90 | +7,108.4 Hz/s | +5,301.6 Hz/s |

The broad distributions are consistent with multiple signal opportunities and
different time-varying carrier trajectories. They are not intrinsic LNB-error
measurements. The centered calibration campaign must independently measure the
trusted receiver/path prior and its uncertainty.

## Candidate-cloud saturation and UI consequence

Every current summary reports 256 retained candidates, which is the bounded
presentation maximum. This confirms that the current page's repeated candidate
cards are a saturated hypothesis inventory rather than 256 detection claims.
The useful next interface is time × CFO/track visualization with a compact
selected-candidate inspector, as specified in `plan2.md`.

Scientific confidence across the summaries includes `candidate` and `rejected`.
No summary is promoted to calibrated specificity by this report.

## High-quality paired examples

The following immutable session IDs are useful for existing-data UI,
re-analysis, time-series, and candidate-lineage development:

| Session | stream-0 QAM | stream-1 QAM |
|---|---:|---:|
| `production-24h-20260819-01-trial-00000132` | 0.9821 | 0.9742 |
| `production-24h-20260819-01-trial-00000379` | 0.9733 | 0.9750 |
| `production-24h-20260819-01-trial-00000033` | 0.9788 | 0.9717 |
| `production-24h-20260819-01-trial-00000197` | 0.9742 | 0.9713 |
| `production-24h-20260819-01-trial-00000081` | 0.9725 | 0.9713 |

Use these first for bounded UI and re-analysis tests because both streams carry
strong existing QAM evidence. Do not copy them into CALIBRATION or ACCEPTANCE
inventories.

## Immediate conclusion

No additional broad scouting capture is justified. The disk corpus already
contains hundreds of useful dual-radio examples spanning high and low QAM,
wide CFO, and positive/negative Doppler slopes. Development should now iterate
on:

1. fast recording discovery and explicit re-analysis;
2. correctly scaled time/CFO candidate and track views;
3. QAM/EVM and carrier evidence over time where the scientific producer has
   actual temporal samples;
4. honest Quick/Standard/Research execution and comparison; and
5. only afterward, two short three-session centered calibration blocks and the
   three bounded ten-session WP11 acceptance blocks.
