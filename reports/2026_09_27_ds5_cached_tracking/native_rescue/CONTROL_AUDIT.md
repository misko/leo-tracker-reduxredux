# Independent audit of the frozen control result

This audit reads only the frozen control receipt and construction metadata. It
does not rerun either detector or open diagnostic, recorded-development,
validation, or holdout IQ. The candidate fails its first scientific gate.

The receipt is complete and source-stable. `results.controls.json` has SHA-256
`cddba5d93b7093b9e95fe522233a292635a000f25c034e35b61fae92d4cb0727` and
embeds the exact 103-file source lock whose file SHA-256 is
`0c12603cba55e137501032577f36bb8c7b0a0c3bbe7e06da34a949c687cabb54`.
Every current source digest in that lock matches. All 42 ordinary rows say the
input remained immutable; all 24 supplemental rows also say the parent source
hash remained stable. The receipt is stage `controls`, has no predecessor
receipt, sets both `validation_opened` and `holdout_opened` false, and contains
only legacy control and constructed metadata-sequence cohorts. No later result
file exists in this directory.

## False decisions

There are five failed receiver-policy checks, but only three distinct physical
receiver waveforms. The ordinary 42-occurrence suite contributes the first two.
The orientation audit repeats those same arrays in their original orientation
and adds the third failure after moving a different parent's RX1 into the
candidate's deterministic RX0 rescue position.

| Physical parent / orientation | Evaluated RX (parent RX) | Constructed tone | Candidate rank | Python margin | Native seed margin | Native confirmation margin | Scoring CFO (Hz) | Python physical CFO (Hz) | Native physical CFO (Hz) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `control-tone-upper-r5000000-s13903-13904` / original | 0 (0) | -172986 Hz | 1 | 0.04612223009353458 | 0.027514140669878215 | 0.026884927616215054 | 226920.23344351893 | 134146.7959435166 | 134590.68798897346 |
| `lag3-r5000000-tone` / original | 0 (0) | -266667.25 Hz | 5 | 0.06654893156547416 | 0.025090667388902595 | 0.026917255504387297 | 174582.8351022536 | 179465.6476022537 | 179465.6476022536 |
| `control-tone-lower-s3901-3902` / `rxswap-v1` | 0 (1) | -172712 Hz | 8 | 0.05718563901096427 | 0.028001122505043066 | 0.025987862300819287 | 268566.54125623516 | 273449.3537562353 | 273449.35375623516 |

The first row appears once in the ordinary suite and identically in the
supplemental original-orientation execution. The second does too. The third
appears only in the swapped execution. Thus the two supplemental original
failures are repeats rather than independent tones, while the mirrored failure
is a genuinely different parent receiver and carrier. No parent failed in both
orientations.

For all three unique failures, the acquired/scoring CFO returned by each native
point exactly equals the Python scoring CFO. Seed and confirmation use the same
local epoch and the same native physical CFO, so their circular timing residual
and physical-CFO difference are both zero. Probe starts are exactly 20 ms apart:

| Parent | Local epoch (samples) | Probe starts (samples) | Source epochs | Support per point |
|---|---:|---:|---:|---:|
| `control-tone-upper-r5000000-s13903-13904` | 1900 | 0, 100000 | 8055001900, 8055101900 | 15, 15 |
| `lag3-r5000000-tone` | 962 | 0, 100000 | 12004207962, 12004307962 | 15, 15 |
| `control-tone-lower-s3901-3902` RX1 via swap | 1487 | 0, 50000 | 8010001487, 8010051487 | 15, 15 |

Every point reports status zero, valid bounds, complete fractional processing,
and valid support. The accepted hypotheses are detector outputs and should not
be confused with the constructed carrier frequencies in the table. In
particular, these failures show that two fresh fixed-hypothesis raw scores and
perfect hypothesis consistency do not reject a persistent tone.

The ordinary parent NPY hashes are
`6cdfb3684d2abf1f450f247328d6580f21c6e1f71332020d5c8282954d3cd77c`
and `7a2cd32f113bc3ad0c9d7371ef9aed32d4edb6612b46676bf7d26ce805830899`
for the two 5 MS/s failures. The 2.5 MS/s mirrored failure has parent NPY hash
`2a277a84471683ccc9895fde46568e9123deac4d26802e5d3a5b33691eda4e1a`
and derived swapped CI16 payload hash
`0726ad7c7f16ef0f764ad9c74ccf07971b55017f31b2201daa6b4198addc675d`.

## Preservation and accounting

The unchanged primary controller produced 52 active receiver decisions in the
ordinary suite. All 52 final rescue outputs preserve the complete primary
decision object exactly. Only two primary-inactive decisions changed, and both
are the false tone rescues above. The supplemental baseline and primary rescue
controller were inactive throughout, so that audit had no primary positive to
preserve.

The saved counters are internally consistent for every ordinary and
supplemental execution: no acquisition retained more than ten candidates,
scores do not exceed retained candidates, event count equals score count,
confirmation calls do not exceed seed calls, and at most one event is accepted
per execution. Across the ordinary suite the candidate ran 16 acquisitions,
scored 148 candidates, made 36 seed calls and four confirmation calls, and
accepted two. These facts validate the bounded-work accounting; they do not
rescue the failed tone-rejection claim.

The supplemental audit is scientifically useful because the ordinary fixed
RX0-first rule missed the vulnerable RX1 tone in
`control-tone-lower-s3901-3902`. Its 12 parents are paired orientation checks,
not 24 independent noise or tone realizations. The evidence therefore supports
rejection of this raw-score rescue rule and motivates nuisance-preserving
fixed-hypothesis confirmation, but it does not estimate a population false
positive rate.
