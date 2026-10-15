# A029/A071: path switching and frozen-shift qualification

The source audit confirms unresolved A failures on both cases and finds **no
failed coverage A stage to rescue**. Every current low/high/final stage is
strict (18/18 per case). Both final selectors switch away from the common
low-stage training winner. Frozen receiver contrasts are not stationary when
released into the original joint calibration family. These are training-only
findings; this report performs no position-reference calls or new fits.

## Source inventory, without a reference

| Case | Original → coverage candidates | Common / removed / added | Uniform per-candidate q ratio | Preserved original centers |
|---|---:|---:|---:|---:|
| 029 | 42 → 25 | 23 / 19 / 2 | 1.680000 | 0/6 |
| 071 | 57 → 39 | 34 / 23 / 5 | 1.461538 | 1/6 |

Full observations, clock nodes, preparation metadata and training partition
are identical across the two versions of each recording. These are replaced
banks and proposals, not nested expansions. No cross-bank MAP comparison is
made. Genuine twelve-unit scientific readers and exact source/cache manifests
validate each matrix before this receipt audit.

Original 029 has all 18 stages strict. Original 071 has 15 attempted stages:
start 1 fails high, start 5 fails low, four final paths remain eligible. Those
old failures remain unchanged. Current coverage has all six final paths eligible
in each case. The earlier 029 fixed 44-satellite union/twelve-start pilot also has all
36 stages strict and retains its unchanged training winner; it is not rerun.

Every original/current A local disk has radius 25 km inside the unchanged 250 km
regional prior. Six such disks cover **at most 6%** of the prior's area, from
the sum-of-disk-areas bound; twelve cover at most 12%. This proves incomplete
prior search without inspecting a configured station. It does **not** establish
that the relevant solution is outside the present disks. The deterministic
16-cell cover with centers `{-150,-50,50,150}²` and local radius `100√2` km
is separately certified to cover the entire prior bounding square, provided
every fit retains the original global prior disk. No new cells are fitted here.

Existing B/C conditional training sources remain explicit. Both cases have
eligible B-all/low/high and C-low/high sources; C-all is unavailable on 071.
All current B/C selected positions lie within at least one current A disk.
In071, the B full training winner's position already lies in A's existing
search region. A's sequential low/high stages are not relabeled as independent
half-only A pipelines.

## Across-path switching versus within-path movement

| Case/version | Low-training winner → final winner | Chosen path's low-J regret | Own low → final km | Global low winner → chosen final km |
|---|---|---:|---:|---:|
| 029 original | 0 → 0 | 0 | 4.676725 | 4.676725 |
| 029 coverage | 0 → 4 | 588.984074 | 3.922760 | 33.254744 |
| 071 original | 0 → 0 | 0 | 2.839765 | 2.839765 |
| 071 coverage | 0 → 2 | 645.409102 | 14.795729 | 51.837269 |

These are distances between saved training states in the unchanged regional
coordinate system, not errors to a reference. High-stage geography stays fixed.
Selected high-stage satellite timing changes have RMS 2.303 s on 029 and 2.188 s
on 071. Low-score preference, final path switching, and final within-path motion
must therefore remain separate explanations.

Adding the exact saved high-offset prior to every final objective leaves all
four original/coverage selectors unchanged. Coverage penalties range 0.363–0.685
on 029 and 0.223–0.379 on 071, much smaller than relevant score gaps. Missing the
constant prior is a real bookkeeping distinction, but does not explain these
selectors. This metadata calculation is not a new fit or a substitute for
jointly releasing the contrasts.

## Exact common-family qualification: 46 objectives, zero fits

All six original coverage A final states per case are transferred into the
**existing original B joint folded-frequency family**. For receiver r,

`a_centered[r] = a_raw[r] + f_high[r] * delta[r]`.

Thus `a_centered + (high-f_high)*delta` equals the original
`a_raw + high*delta` on every native row. No timing, clock, c, slope, alias
representative, bank, window or local domain is changed or projected.
The exact legacy classes have **no common-intercept prior**. Timing and
common-clock priors remain unchanged, while each physical contrast retains
its original 50 kHz prior. The fixed arm adds that frozen contrast's constant
prior explicitly; the free arm includes the same prior as a parameter penalty.
There is no hidden intercept penalty or prior change between the two arms.

Each case uses 23 objective evaluations: six source/fixed/free triples, one
exact historical B incumbent replay, and four centered-offset finite-difference
probes at the original training-selected A state. The metadata source audits
used zero objectives and took 1.336/1.199 s; actual numerical qualification took
**0.708/0.753 s** for 029/071. There are no explicit additional orbit predictions
outside those objective evaluations, no optimizers and no reference reads.

Across all twelve states, maximum closure errors are:

| Quantity | Maximum absolute discrepancy |
|---|---:|
| Native-row calibration | 1.46e-11 Hz |
| Objective / NLL | 7.28e-12 |
| Physical gradient | 7.90e-10 |
| Common-clock gradient | 2.71e-14 |
| Prior ledger | 3.57e-12 |
| Posterior responsibilities | 5.84e-13 |

The exact B incumbents replay strictly: 029 J 33977.015658/KKT 0.000465086;
071 J 35276.749686/KKT 0.000276309. All twelve A states have nonstationary newly
released offsets, despite their strict original constrained convergence.
At the training-selected states, the centered offset derivatives multiplied
by the original 5000 Hz solver scale are 029 `[-702.180,228.213]` and 071
`[392.726,763.165]`. Central FD with step 0.01 Hz agrees within 3.8e-10/Hz.
The original independent KKT rule is unchanged; large released gradients are
not themselves a position-accuracy claim.

## Approved bounded next test

The exact-source matched control uses all six genuine A final states in each
case, each under fixed and released contrasts: **24 new full fits maximum**.
Both arms receive 20 s, 2000 actual objectives including one reserved independent
audit, and 600 iterations, with their original 25 km disks and global prior.
All six qualified A fixed states (including their constant prior) and the exact
B joint incumbent remain in their appropriate own-family training selectors.
Both complete case matrices must seal before any new position comparison.

This is an A sequential-initialization/constraint-release sensitivity using
existing B mathematics, not a new architecture. Earlier inherited pipeline
costs differ. It changes neither q nor visibility nor candidates, and it does
not claim that a better training fit will improve geography. Outcomes are not
included in this qualification report.

Component validation: 7 source-inventory tests, 8 transport/qualification tests
and 5 control integration/receipt tests passed; Ruff passed. The transport tests
cover exact prior partition, centered/raw-intercept chain-rule finite differences,
and rejection of changed clock priors or hidden likelihood implementations.

The source-frozen inventories and qualifiers live under
`/srv/bulk/leo-research-ds21-ds22/2026_10_14/model-a-{unresolved-source,contrast-release-qualification}-{029,071}-v1`.
[The numeric certificate](model_a_029_071_qualification_results.json) retains
all source paths, banks, centers, stage failures, priors, gradients and hashes.
These repeatedly examined development recordings are not independent validation.
