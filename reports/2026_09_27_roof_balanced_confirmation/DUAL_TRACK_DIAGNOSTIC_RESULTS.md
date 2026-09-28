# Why the dual reception model still misses geographic accuracy

Two bounded diagnostics completed in 75.6 and 88.7 seconds. Each prior evaluated
only three unique saved winning positions, with fresh independent full-catalogue
frequency fits. All original/shared-detection/dual score arms reproduce their
frozen geographic scores exactly (maximum difference zero). No new position,
reference coordinate, candidate borrowing, model fitting or search was used.

These are post-outcome diagnostics of 339af and 53ce, not a new evaluation cohort.
Candidate identities remain model associations, not decoded satellite truth.

## The 339af regression is not dominated by newly switching MAP identities

The dual model moves away from the original/shared-detection winner and worsens
distance error from 1.9585 to 2.3884 km for Sacramento and from 1.6095 to 2.5797
km for Reno. Under the dual objective, the right-minus-left score attribution is:

| Prior | Doppler delta | Detection-increment delta | Conditional-ratio-increment delta | Joint delta |
|---|---:|---:|---:|---:|
| Sacramento | -0.00148319 | +0.00002370 | +0.00105148 | -0.00040802 |
| Reno | -0.00379398 | -0.00005914 | +0.00193455 | -0.00191857 |

Negative joint delta favors the dual winner. On both priors, the move gives a
better Doppler-only score despite worse distance error. The remaining conditional
ratio increment opposes the move, but no longer outweighs the Doppler preference.
This is consistent with reducing ratio confidence removing both harmful and
helpful corrections; it is not evidence for selecting confidence per scan.

Of 64 tracks, 62 keep the same joint MAP identity across these two positions.
Those 62 contribute -0.00322883 (Sacramento) and -0.00546663 (Reno) to the joint
change. The two tracks whose joint MAP changes contribute +0.00282081 and
+0.00354806, respectively: **the switching tracks oppose the selected move**.
Shortlists change for two Sacramento tracks and four Reno tracks; held-frequency
MAP changes for one and three, respectively. Stable joint MAP still permits
substantial changes in candidate probabilities.

## The 53ce Sacramento regression exposes identity reweighting

Moving from the Doppler-only winner (5.5377 km error) to the dual winner
(6.0323 km error), all 62 tracks retain the same joint MAP satellite ID. Four
shortlists and one held-frequency MAP change. The usual telescoping attribution
is Doppler +0.00276140, detection increment -0.00330888, conditional ratio
increment -0.00244979, yielding joint -0.00299728.

It would be misleading to interpret these increments as independent physical
antenna-gradient forces. They include the effect of reception evidence changing
which candidate frequencies dominate the mixture.

An exact second decomposition is possible because the same joint MAP candidate
k exists at both positions for every track. Let l_k be its normalized training
log prior, F_k/d_k/r_k its held-frequency/detection/ratio log likelihoods, p_k its
joint posterior probability, and N the full reserve count. The identity

    joint_score = -(l_k + F_k + d_k + r_k)/N + log(p_k)/N

is exact for any supported candidate k; it does not approximate the mixture by
a hard assignment. Apply it at both positions using their independently fitted
values and the unchanged occupied-second weights. For 53ce Sacramento:

| Weighted score-change component | Value |
|---|---:|
| Training-prior term | +0.0000764442 |
| Held-frequency likelihood at the common joint MAP identities | -0.0034492902 |
| Detection likelihood at those identities | +0.0000112192 |
| Ratio likelihood at those identities | +0.0000309755 |
| Exact mixture correction, log joint posterior | +0.0003333748 |
| Sum | -0.0029972765 |

The directly evaluated detection and ratio changes at these fixed identities
actually **oppose** the move slightly. Their sum is about +0.0000422, while the
conditional frequency improvement is -0.0034493. Thus the geographic preference
is dominated by the frequency fits of the identities supported by the joint
model, not a large direct local directional pull. At the dual winner, five of
62 joint MAP identities differ from the frequency-only posterior MAP.

For 53ce Reno, all 62 joint MAP identities likewise remain stable from the
Doppler-only to dual position. Fixed-identity detection plus ratio changes sum
to approximately +0.00000114, while the conditional frequency term is
-0.00216224; the full joint change is -0.00243895. That position happens to have
a slightly smaller radial error, but the same distinction applies.

These calculations were independently reconstructed from the candidate-aligned
arrays in the saved diagnostics, and their weighted sums close to the joint
score changes within 1e-10. They identify a scoring mechanism, not which physical
satellite association is correct or why its orbit/frequency model is biased.

## Next useful test

The calibration audit found within-track direction information, so removing all
RX information is not justified. But better reception prediction is insufficient:
we need to test whether RX-updated identity probabilities improve prediction of
**separate held-out Doppler observations** at calibration locations.

A bounded calibration-only diagnostic should compare frequency-only and
frequency-plus-RX identity inference on one observation block, then score a
disjoint frequency block. Receiver-model coefficients must be fitted without
the held calibration recording, and observation splits must avoid same-frame
reuse. No reference-location candidate list may enter an evaluation prior.
This directly checks whether reception-supported associations help the frequency
evidence used for localization, before another geographic search is justified.

The unused confirmation cohort remains untouched. No estimator change or
improved-resolution claim follows from this diagnostic.

Artifacts: `dual-track-diagnostic-scan-fw-339af454a2aab2f4.json`,
`dual-track-diagnostic-scan-fw-53ce822d78d476ba.json`,
`dual-track-attribution.json`, and `DUAL_TRACK_DIAGNOSTIC_PROTOCOL.md`.
