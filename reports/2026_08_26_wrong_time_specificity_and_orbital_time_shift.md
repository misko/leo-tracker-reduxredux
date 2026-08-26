# Wrong-time specificity is not an orbital time-correction bound

Date: 2026-08-26 UTC

Status: **interpretation addendum; local paper and frozen protocol reviewed; no
new association run**

## Decision

The final holdout's `±15 minutes` through `±5 hours` controls are reasonable as
a deliberately broad **catalogue-specificity null**. They are not plausible
values of a fitted receive-clock or TLE epoch correction. The primary final
holdout association actually fixed `tau = 0` and fitted only one constant CFO
offset per path.

Each of the 40 controls propagated the complete frozen Starlink catalogue at a
deliberately wrong epoch, recomputed the visible candidate population, and
asked whether the best wrong-time field fit the observed short CFO arc as well
as the true-time field. With empirical

```text
p = (1 + number of wrong-time fields no worse than true time) / 41,
```

the eight evaluable captures had 6, 10, 10, 14, 17, 25, 34, and 36 controls no
worse than true time. Thus 0/8 passed the `p <= 0.05` gate. This supports the
narrow conclusion that the short, nearly linear arcs did not uniquely encode
catalogue time. It does not estimate a five-hour orbit error.

The null is a conservative rank-style stress test rather than a calibrated
posterior probability of identity: wrong-time skies are correlated, their
visible populations differ, and the controls are intentionally far outside
capture-clock uncertainty. Future long-arc work should retain two separately
named quantities:

1. `tau_physical`, fixed at zero or restricted by a preregistered clock/orbit
   error model; and
2. `delta_null`, the broad wrong-time field used only to measure catalogue
   specificity.

Conflating them would turn a useful negative control into an unphysical fitted
nuisance.

## What the two long arcs say about physical `tau`

| Arc | Tested physical sensitivity | Result | Interpretation |
|---|---:|---|---|
| `9981`, 30 s | primary `±0.30 s`; wider `±2 s` post-hoc | primary optimum `-0.30 s` boundary; wider winner near `-0.95 s` | capture-clock half-width is only about `0.00053 s`; these shifts are orbital/TLE/model sensitivity, not clock correction |
| `150802`, 13.825 s | primary directional fits `±2 s`; separate `±30 s` degeneracy test | fixed `tau=0` held out better than fitted tau; directional fits chose about `-0.345 s` and `+0.790 s`; a different NORAD won near `-22.5 s` under the wide search | the extra time parameter was unsupported; the wide result demonstrates catalogue multiplicity, not a plausible clock correction |

These results support small, explicitly bounded sensitivities and fixed-time
baselines. They do not establish one universal bound. Even `±60 s` is not
justified by these reports as an estimated prior: at LEO velocity it represents
a very large along-track displacement. The bound should come from TLE
age/quality and an ephemeris-error model, not from whichever search range gives
the lowest radio residual.

## Review of *Unveiling Starlink for PNT*

The locally supplied PDF was Kozhaya, Saroufim, and Kassas, *Unveiling Starlink
for PNT*, **Navigation** 72(1), 2025,
[DOI 10.33012/navi.685](https://doi.org/10.33012/navi.685). The reviewed local
file was 8,762,003 bytes with SHA-256
`0023d1e240d0f9bb8bb4b289eaf83c08714a6ce7d86007a976d24874223497fa`.

Sections 7.2, 8.1, 8.2.2, and 8.3 repeatedly treat TLE+SGP4 satellite position
as truth **after temporal and orbital errors have already been corrected using
knowledge of the receiver position**, citing Hayek et al. (2024). The PNT paper
does not expose that correction as a fitted scalar `tau`, state a numerical
time-shift search interval, or justify `±60 s`, `±2 s`, or `±5 h` bounds. Its
reported post-2024 Doppler residuals are conditional on that corrected
ephemeris assumption and therefore cannot validate association from an
uncorrected public TLE.

The paper's every-one-second CFO corrections are a different phenomenon:
signal/transmitter corrections observed in pre-2024 OFDM tracking. They are not
one-second TLE epoch updates and do not justify an orbital `tau` bound. The
paper also notes that the data-less pilot tones did not exhibit those OFDM
corrections, which further argues against importing that parameter directly
into this repository's Qin edge-pilot association model.

## Follow-on primary evidence narrows the useful sensitivity

Hayek and Kassas, *Modeling and Compensation of Timing and Spatial Ephemeris
Errors of Non-Cooperative LEO Satellites With Application to PNT*, IEEE TAES
61(3), 2025, [DOI
10.1109/TAES.2024.3513286](https://doi.org/10.1109/TAES.2024.3513286), is a
follow-on to the Hayek et al. (2024) method cited by the PNT paper. The
[official author PDF](https://people.engineering.osu.edu/media/document/2025-07-23/kassas_modeling_and_compensation_of_timing_and_spatial_ephemeris_errors_of_non_cooperative_leo_satellites_with_application_to_pnt.pdf)
models an equivalent argument-of-latitude correction jointly with a separate
clock drift term for Doppler; it is not a bare unconstrained receive-time fit.

Its experimental Table IV gives the following Starlink epoch-time adjustments:

| Starlink NORAD | TLE age | carrier-phase adjustment | Doppler adjustment |
|---:|---:|---:|---:|
| 44973 | 17:44:49 | 1.7317 s | 1.7423 s |
| 47135 | 32:07:48 | 1.0152 s | 1.0256 s |
| 51138 | 20:56:18 | 0.9365 s | 0.9461 s |

Thus that primary experimental sample found about `0.94–1.74 s` for Starlink
TLEs roughly `18–32 h` old. This is valuable scale evidence, not a universal
bound: there were only three Starlink satellites, the adjustment also absorbs
propagation error, and ground-truth ephemerides were unavailable.

The final holdout's snapshot age and element age must also not be conflated.
The frozen snapshots were retrieved only `0.59–1.94 h` before the eight
evaluable captures, but their selected top-ranked TLE **elements** were
`14.2–41.5 h` old at first sample. Those ranges are derived from the frozen
[protocol](../config/analysis/final-doppler-holdout-satellite-protocol-v3.json),
[score](figures/2026_08_26_final_doppler_holdout_attempt2-score.json), and exact
TLE epochs. A recently downloaded catalogue can therefore still contain an
older element for the selected satellite.

## Recommended long-arc protocol

For the newly frozen
[POST-FIX long-arc cohort](2026_08_26_post_fix_long_arc_research_cohort.md):

1. make `tau=0` with a free constant CFO offset the primary baseline;
2. for frozen elements no more than 48 h old, predeclare `±2 s` as the
   age-informed physical sensitivity and `±5 s` as a separate stress
   sensitivity; treat neither as a learned universal prior;
3. report boundary hits and bidirectional or rolling-origin tau stability;
4. add a **near-time catalogue null** at `±15`, `±30`, `±60`, `±120`, and
   `±300 s`, while retaining the current `±15 min` through `±5 h` family as
   the **far-time catalogue null**; neither null may optimize `tau_physical`;
   and
5. require candidate recurrence across independent long arcs before making an
   identity claim.

This preserves the valid conclusion from the final holdout—short arcs were not
time-specific—while giving the two curved POST-FIX arcs a fairer and physically
interpretable association test.
