# Causal age-conditioned uncertainty design

The available evidence supports a tractable **one-arm predictive test**, but it does not yet support a geographic fit. The DS11 audit shows a weak monotone association between exact element age and residual scale without using reference coordinates. Earlier DS7–DS9 data provide enough causally sourced residual cases to calibrate one fixed relation and a disjoint fixed-point population on which to reject it before any DS11 position comparison.

## Provenance and availability

The proposed feature is the age of the exact element selected by the numerical bank: capture start minus element epoch. Selection must reproduce the exporter exactly by taking the greatest `(element epoch, collection time, snapshot digest)` for each NORAD object among the bank manifest's pinned provider snapshots. A whole-snapshot age or provider label is not an acceptable substitute.

The 25 donor-only DS7–DS9 units contain 9,968 conditional candidate cases from 186 scans, 470,375 observations, and 6,088 `(scan, NORAD, exact RF)` source occasions. Their 372 manifest references resolve to 23 unique archived snapshots. A read-only archive inventory found every snapshot and an exact element record for every case, with no future-dated epoch. Donor ages span 0.084–4.271 days, covering the DS11 range of 0.345–3.047 days. The donor and fixed-point target scans are disjoint.

The nine earlier target panels contain 3,983 cases, 2,512 source occasions, and 73,877 held observations. The existing orbital replay already reproduces their saved bank positions, velocities, and fitted frequencies exactly. The donor banks have enough provenance to perform the same replay, but that numerical replay has not been run. It is a mandatory preflight because the previous inline DS11 age script was not retained and manifest-policy reconstruction alone is weaker than reproducing saved bank states.

These cases remain conditional on q020-fitted locations and training-selected, unverified candidate identities. They can test conditional predictive scale transfer; they cannot validate identity or prove that orbit error causes the residual association.

## Single frozen arm

For candidate element age `a` in days, use

`sigma(a; k) = sqrt(100^2 + (k * a)^2) Hz`, with `k >= 0`.

This is monotone, has one parameter, and nests the original Student-t4/100-Hz density exactly at `k=0`. Apply the candidate-specific scale to every shortlisted candidate, retain the full-catalogue divisor, candidate mixture, visibility, timing, and weak 1-MHz CFO prior, and profile each candidate's CFO at its own scale. The normalized density must retain its `-log(sigma)` term. Existing bank states remain unchanged; age changes uncertainty only.

Fit `k` once from donor **training observations only**. Average normalized log likelihood over observations within track, tracks within source occasion, source occasions within scan, and scans within dataset, with equal DS7/DS8/DS9 weight. This prevents repeated receivers and track-rich scans from acting like independent orbit solutions. Predeclare a finite numerical bound and reject a boundary optimum; do not compare several age laws or scales.

Evaluate the frozen coefficient at the saved target endpoints and candidate assignments. Reprofile CFO using target training observations, then score held observations with that training-derived offset. The comparison is `k=0` versus the one fitted `k` on identical cases. Require complete coverage, positive equal-weight held-log-density gain separately in DS7, DS8, and DS9, and a majority of paired source occasions improved. Preserve dataset, scan, source, and track denominators. Held values must never select the coefficient or another functional form.

Only a passing predictive result permits a DS11 model to be implemented. Its index-0 `k=0` control must reproduce original score, gradient, and endpoint; the single frozen `k` arm then receives the existing eight-scan screen and observed-information audit. DS11 reference errors may be opened only after numerical and scientific qualification. No coefficient, scale, or age cutoff may be changed from those geographic outcomes.

## Causal freshness check comes first

The current exporter does more than require information available before recording. It selects the latest snapshot from each provider strictly before `capture_start - 505 seconds`, then chooses newest-per-object elements only among those two snapshots. The installed archive API itself requires only a snapshot strictly before the measurement time. The guard entered the reviewed history in commit `77acf92a2d0f2a427f0fa662b6388e34622c7e14` without a comment, test, protocol statement, or commit-message rationale. Its exact purpose is therefore unknown.

The archive filename timestamp is not a completion time: `collect_provider` records `time.time_ns()` before the network fetch, then validates, writes, flushes, and fsyncs the response. A filename timestamp before capture cannot by itself prove that the bytes were available. For the five affected DS11 scans, the completion audit instead recomputed the exact archive digest, inspected file birth and modification time, and matched a systemd journal `status=published` receipt for that digest. Every receipt precedes capture: indices 10, 13, 16, 27, and 31 have margins of 279.146, 469.368, 259.800, 42.881, and 184.092 seconds respectively. These are operational local timestamps rather than signed external attestations, but they directly establish local availability under the user's causal criterion.

The metadata inventory found zero rescues among 3,071 candidate occasions when it retained the same 505-second cutoff. Moving only the cutoff to actual capture start changed element bytes in five scans. The semantic audit reduces those 369 byte changes to 96 parsed SGP4-input changes: 75 are only one-unit (`1e-7`) eccentricity quantization differences. Index 10 has one meaningful newer element that was not the current MAP candidate. Index 31 has 20 meaningful newer elements; two current MAP NORAD objects support eight tracks and 220 training observations. Indices 13, 16, and 27 contain only the quantization changes. This supports a bounded five-scan matched freshness comparison, while preserving unchanged candidates and all other scans exactly. It does not justify removing the guard as a general production policy.

Before an age law, compare the current policy with two metadata-only causal inventories:

1. newest-per-object over every archived snapshot in the prior three days under the same `start - 505 seconds` cutoff, which detects rollback, omission, or stale rows in the latest provider snapshots;
2. newest-per-object over snapshots available before actual capture start, which separately measures records excluded only by the extra guard.

If the first inventory finds newer exact elements, a same-cutoff causal freshness repair is a more direct orbital-input test than widening uncertainty. Here only the second inventory changed meaningful elements, and the separate completion receipts establish that the selected bytes were already local before recording. Future-collected `+4 h` elements and offline newer-orbit results remain separate diagnostics and cannot support the primary causal positioning result.

## Cost and decision

The archive/provenance join is small: 23 unique donor snapshots and 51 MiB of retained donor case files; the read-only availability check completed in about four seconds. Based on the prior 3,983-case replay, a donor baseline replay is a single bounded one-thread job with a conservative 180-second cap. Scalar calibration and the 3,983-case fixed-point held comparison each fit within a separate 120-second, one-thread stage. No RF, download, propagation change, or position fit is required for these gates.

The one-arm age test is practical, but the causally fresher matched control should be resolved first because it changes the orbital input directly and needs no age law. Donor exact replay plus cross-dataset held prediction remain mandatory before the age-conditioned arm can reach DS11. Until then the age-conditioned family is a design candidate, not a promoted DS11 method.
