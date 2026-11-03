# DS11 joint physical-identity mixture proposal

## Scope and census

This proposal uses only the training observations and the original same-scan
IID endpoint. It does not read held observations or a reference position. The
physical identity for each bank candidate comes from the digest-bound archived
catalogue sidecar; candidate slot numbers are never treated as identities.

The frozen association rule is deliberately selective:

1. At the original IID endpoint, compute each track's conditional candidate
   mass from its training likelihood.
2. Assign a physical NORAD only when the largest mass is at least 0.90.
   Otherwise preserve the track as an independent ambiguous singleton.
3. Form a group from tracks with the same selected physical NORAD only when
   that identity occurs in at least two exact `(receiver_id, rf_hz)` strata.
   Once the cross-stratum condition is met, include every track assigned to
   that identity in the scan.

The screen-8 census is stored in `overlap.json`. Across 489 tracks, 483 have a
strong assignment and 6 remain ambiguous. There are 112 repeated selected
NORADs; 111 span receiver/RF strata and contain 423 tracks (86.50% of all
tracks). Of the 111 feasible groups, 90 span receivers, 90 span RF values, and
69 span both. Their size distribution is:

| tracks per group | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| groups | 39 | 16 | 21 | 15 | 11 | 4 | 2 | 2 | 1 |

The intersection of the groups' retained physical candidate sets is always
nonempty and always contains the selected identity. Its median size is 8,
mean size is 8.05, minimum is 2, and maximum is 15. The proposed grouped
calculation therefore covers 3,073 track/candidate cells on this panel.

Candidate overlap alone is not an association rule: 5,550 of 13,079 (42.43%)
cross-stratum track pairs share at least one retained candidate, while only
763 (5.83%) share the same strong selected identity. The 0.90 physical-identity
rule supplies the needed selectivity without looking at held or reference
data.

| screen index | tracks | ambiguous | joint groups | grouped tracks | cross RX | cross RF |
|---:|---:|---:|---:|---:|---:|---:|
| 0 | 62 | 2 | 14 | 52 | 12 | 11 |
| 4 | 61 | 0 | 11 | 53 | 11 | 10 |
| 8 | 61 | 0 | 15 | 53 | 11 | 12 |
| 12 | 59 | 1 | 13 | 50 | 9 | 12 |
| 16 | 58 | 1 | 18 | 53 | 13 | 13 |
| 20 | 63 | 1 | 14 | 53 | 11 | 12 |
| 24 | 64 | 1 | 11 | 54 | 10 | 9 |
| 28 | 61 | 0 | 15 | 55 | 13 | 11 |

## Smallest coherent model

Use one variant, `joint_identity`. For track `t` and physical candidate `c`,
let `ell[t,c](x)` be the existing Student-t4 training log likelihood after
profiling a separate stationary CFO for that track/candidate pair. For frozen
group `g`, let `C[g]` be the intersection of the retained physical candidate
sets of its tracks. Its contribution is

```
logsumexp(c in C[g], sum(t in g, ell[t,c](x))) - log(catalogue_size).
```

The catalogue prior is applied once because the group has one shared latent
identity. Candidate indices are resolved independently in each track by
physical NORAD. A candidate invisible in any member has joint likelihood zero.
Every ungrouped or ambiguous track keeps the original IID contribution:

```
logsumexp(c, ell[t,c](x)) - log(catalogue_size).
```

The group gradient uses one responsibility per shared identity, multiplied by
the sum of that candidate's per-track position/time gradients. Each track's
CFO is still profiled independently. The model shares no CFO, residual, scale,
or continuous nuisance parameter and drops no observation.

This is a training-frozen empirical-Bayes association likelihood over
truncated candidate banks. It is not a normalized posterior. The main modeling
risk is sharper evidence when residual errors remain correlated across tracks;
the one-arm screen should test the untempered identity-sharing hypothesis
before introducing any extra power or weight parameter.

The numerical cost is feasible. It performs the same per-track prediction and
CFO profiling as IID and replaces track-level mixture reduction with a small
group reduction. The screen census has only 3,073 grouped track/candidate cells
and at most 15 shared candidates in a group.

## Required component tests

1. Exact IID score and gradient parity when no eligible group exists, including
   all singleton and ambiguous inputs.
2. A hand-computed two-track/two-identity group score and gradient, including
   the single catalogue normalizer.
3. Physical-candidate slot permutation invariance across tracks, and rejection
   of duplicate NORADs within a track bank.
4. Independent CFO preservation: each track/candidate pair is profiled
   separately, and changing one synthetic track cannot reuse or alter another
   track's fitted offset.
5. Finite-difference agreement for position and scan-time gradients on grouped
   data.
6. Frozen membership and model output invariance to held observations and
   reference-position changes.
7. Full observation accounting plus rejection of an empty candidate
   intersection; verify that every frozen selected identity occurs in its
   group's intersection.
8. Resource binding tests for the original IID receipt, scan/session, candidate
   bank, identity sidecar, and their declared hashes.

No fit should run until the model and these tests have been reviewed. If
approved, the bounded evaluation is the single `joint_identity` arm on the
existing screen-8 indices with the standard four starts, 90-second fit cap,
one BLAS thread, and one worker.
