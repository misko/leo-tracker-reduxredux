# Why the disjoint test failed: harmful RX evidence plus unstable frequency fits

This post-outcome diagnostic leaves all model settings, candidates, partitions,
and published outcomes unchanged. All four recordings were included in the
saved-score attribution; the two worst contributing X→Y tracks in each of the
two regressing recordings received a bounded component audit. No geographic
search or new validation result is claimed.

## 1. Exact contribution accounting

| Recording, X→Y | Total gain | Changed-MAP contribution | Unchanged-MAP contribution |
|---|---:|---:|---:|
| 127d8 | −0.0006613 | −0.0013772 (2 tracks) | +0.0007159 (53 tracks) |
| 8f4f | −0.0013133 | −0.0006826 (7 tracks) | −0.0006306 (37 tracks) |

Contributions use the full recording's occupied-second denominator and add
exactly. A stable MAP identity is not sufficient protection: damaging changes
to alternative probabilities also contribute to the 8f4f regression.

The separately fitted X/Y top-three candidate sets match in only **13/55**
supported tracks for 127d8 and **3/44** for 8f4f. Even the improving recordings
show only 8/49 and 7/31 identical sets. This instability is descriptive; it is
not a count of physically wrong satellites.

## 2. Which RX term drives the largest harmful changes?

Each row compares the RX-favored alternative against the frequency MAP
candidate before the RX update. Positive log-likelihood differences favor the
alternative. Probabilities below precede the common 50% uniform blend.

| Recording / track prefix | Comparison | Detection advantage | Ratio advantage | Observation pattern |
|---|---|---:|---:|---|
| 127d8 / 0eb468 | 69664 vs 100316 | +10.175 | 0 | 28 rx0 anchors, no other-RX matches |
| 127d8 / d9e092 | 64940 vs 47389 | +2.225 | +5.273 | 6 rx1 anchors, all matched |
| 8f4f / 6b6a58 | 57347 vs 57871 | +1.572 | +5.878 | 13 rx1 anchors, all matched |
| 8f4f / 2603aa | 57347 vs 57871 | +1.928 | +6.792 | 16 rx1 anchors, all matched |

For `0eb468`, candidate 100316 goes from frequency probability **0.9223** to
RX-updated **0.000452**. The held block strongly favors 100316 over the other
two saved candidates, producing a harmful predictive switch. All the RX odds
change comes from nondetection evidence; there is no ratio measurement here.

For `6b6a58`, candidate 57347 goes from **0.00537** to **0.9430**, mainly from
the ratio term. Held frequency evidence favors 57871. For `2603aa`, 57871
remains the MAP candidate, but its probability falls from **0.9605** to
**0.6069**, still worsening prediction. The two 8f4f tracks have no shared
physical-pair keys among their conditioning observations; exact reuse of a
matched RX pair is not the explanation for these two losses. They still need
not be independent physical satellite trajectories.

Thus removing only nondetections or only the ratio term would not address all
observed mechanisms. No such outcome-selected change was evaluated or promoted.

## 3. The frequency model is also inadequate in these examples

The following measurements fix each saved candidate and compare its original
conditioning CFO with a **diagnostic** Student-t CFO refit on the held block.
This refit uses held observations and must not be counted as predictive gain.

| Track / candidate | Held RMS with conditioning CFO | Held RMS after diagnostic CFO refit | CFO change |
|---|---:|---:|---:|
| 127d8 / 0eb468 / 100316 | 2178 Hz | 2193 Hz | −577 Hz |
| 127d8 / d9e092 / 47389 | 773 Hz | 630 Hz | +215 Hz |
| 8f4f / 6b6a58 / 57871 | 1374 Hz | 773 Hz | −1605 Hz |
| 8f4f / 2603aa / 57871 | 950 Hz | 383 Hz | −793 Hz |

These are the held-frequency winners **within each saved shortlist**, not
confirmed physical IDs. Student-t CFO fitting optimizes robust likelihood,
not RMS, so the first row's RMS can increase after refitting.

For the two 8f4f tracks, the same candidate's residual linear slopes change
from approximately **+21 to −342 Hz/s**, and **−0.38 to −302 Hz/s**, between
conditioning and held partitions. CFO changes are in Hz and are not drift
rates; the separately reported slopes are Hz/s. The 127d8 nondetection case
also retains kilohertz residuals after the CFO refit. A single constant offset
does not explain these tracks well across the recording.

This does **not** prove receiver oscillator drift. Wrong satellite identity,
TLE/timing error, track construction, changing channel/frequency behavior, or
other measurement mismatch can all produce such residuals. It also means
“RX overruled the correct satellite” is too strong: RX overruled a candidate
that predicted held frequency better under an imperfect frequency model.

## 4. What the evidence changes

The failure is not solely a weak RX weight or a single bad recording. Both RX
terms can contribute, while the reference frequency likelihood can be badly
misspecified even for its preferred candidate. Relative odds among three
imperfect candidates can look confident without a good absolute fit.

Before further RX-weight tuning, test frequency-model adequacy and track
continuity on the existing development corpus: distinguish shared receiver
frequency evolution from candidate-specific Doppler mismatch, and consider an
explicit unmodeled-track state rather than forcing every track into the
shortlist. Such alternatives need training-only calibration and held prediction;
free polynomials or held-CFO refits could erase location information and are
not proposed as validated fixes. RX geometry must then show incremental value
over that calibrated baseline before another geographic test.

The disjoint cohort is now diagnostic/development data. Its failed progression
gate stands. Better geographic resolution remains unproven.

## Reproducibility

`regression-diagnostic.json` contains the complete attribution for all tracks,
both directions, all four recordings. `failure-components-*.json` contain the
two bounded component audits, exact likelihoods, candidate-aligned CFO/RMS/slope
diagnostics, source hashes, and code hashes. The audits check reconstruction of
saved reception likelihoods within 1e-9 and frequency likelihoods within 1e-7.
Outputs refuse overwrite. The disjoint diagnostic suite has eight passing
tests, including saved contribution closure and component/receipt binding.
