**Independent audit: useful ordering bounds, incomplete replay, no localization claim**

The authoritative [terminal audit](terminal02.json) passes. It independently
reconstructs the saved-input digests, original causal phase parameters, support
masses, complete inner/root evidence bounds, strict null check and nine-model
ordering decisions. No audit propagation, new integral or position fit was run.
Preflight used synthetic geometry and dense observation-space oracles; the old
scientific capsule and every protocol-bound input remain unchanged.

The replay retains all 12 old observations and 24 c-arm slots. Seventeen arms
have complete results, covering 136 candidate rows; another four candidate
checkpoints belong to the incomplete arm. Seven arm results are unavailable,
explicitly retained rather than replaced. The two arms observe the same draws
and are not independent realizations.

| Original condition | Arm | Selected draws | Complete arm results | Certified model ordering | New absolute-score qualification |
| --- | --- | ---: | ---: | ---: | ---: |
| Physical | c0 | 8 | 7 | 6 | 0 |
| Physical | fitted c | 8 | 6 | 5 | 0 |
| Declared polynomial null | c0 | 4 | 2 | 2 | 0 |
| Declared polynomial null | fitted c | 4 | 2 | 2 | 0 |

The 15 ordering certificates follow the explicit rule that a winning lower
log-evidence bound exceeds every competing upper bound, including the null.
They do not imply that individual scores meet absolute 1e-3 precision. All 136
complete candidate rows fail that stronger absolute certification; enclosure
widths range from about .0677 to 696,474 objective units. The old metric was a
quadrature guard without this physical hidden-mode enclosure, so its pass rate
cannot be presented as the same certification becoming worse.

The two completed blocked orderings are 0010 trial0 in both arms: the frozen
null Cholesky/eigensolve guard requires agreement within 1e-7 and sees about
4.78e-7/4.91e-7. Independent augmented-QR agrees within the separate 1e-6 null
evidence allowance, but the stricter guard remains binding. A third predicted
strict-guard failure, trial3 fitted c, was not reached. No threshold was changed.

**What the support correction establishes**

The previously all-domain-blocked rival 100539 now has approximately .950928605
of the original phase prior on certified visible support. Root brackets carry
about 3.98e-12 prior mass. Invisible phases contribute zero likelihood; the
visible mass is not renormalized. The 56530 winner in that trial is certified
in both arms. This resolves an inappropriate whole-domain veto under the new
declared nominal-visibility-event law, not a wrong raw identity decision.
This event uses nominal phase-shifted position, not visibility integrated over
physical-position modes or calibrated GLRT detection probability.

The two completed null observations are certified null winners in both arms,
with conservative minimum log-evidence margins above 155,000. For such gaps,
requiring every losing score to absolute 1e-3 precision adds computation without
changing the ordering question. Bounds address that question without relaxing
the frozen precision outcome. These deliberately extreme polynomial sources
still do not calibrate clutter rejection or real satellite acceptance.

An independent analytic fixture exposed the first draft's false convergence:
log-tanh-sinh and GL32/64 both missed 99% of an off-grid mixture while agreeing.
Its [failed receipt](narrow_mode_precheck.json) is preserved. The mandatory
physical mean/covariance derivative enclosures prevent agreement alone from
qualifying such a result. [Preflight](preflight.json) and
[independent numerical checks](numerical_precheck.json) verify the relevant
algebra and direct density controls; they are not a universal black-box
quadrature guarantee.

**Budget and technical provenance**

The producer used 477.012821 scientific worker-seconds, including preparation,
and 299.839316 s wall time. 0011 completed all six trials. 0010 reached its
preallocated approximately 300 s shared wall deadline during trial2 fitted c;
trials2-5 retain failure status, with completed partial-arm artifacts preserved.
The conservative two-worker allocation does not redistribute unused worker
time. There is no retry, budget extension, new draw, nomination or position fit.

The initial [terminal receipt](terminal.json) failed only because an unbound
reporting script changed while the RF file manifest was being sealed. Its exact
RF-sealed bytes were restored and final reporting separately versioned. The
passing second audit checks every original RF hash without exemption. The first
receipt and [exact original audit source](terminal01.py) remain preserved.
The final audit seal reports cumulative check time including that failed pass;
the second receipt's own cumulative field alone excludes the first terminal pass.

**Decision and smallest next test**

Close this enabling branch. It changes neither position data nor the operational
reference and does not identify the cause of localization error. The original
generator/full-parent versus shortlist-cavity conditioning difference remains.
There is no reason to continue broad numerical engineering merely to make all
individual loser scores precise. If close comparisons cannot be ordered under
the fixed cap, retain abstention rather than expand this effort.

The smallest useful next design is one response-free confusable pair/layout,
under one explicitly shared conditional background, with the same observations,
priors and nuisance inference in ordinary-nomination and separately labeled
known-identity controls. Start with a small fixed weak-axis score profile in
both c arms. Truth may select the explicit oracle control, never backfill the
ordinary shortlist. If ambiguity persists with the correct label, assignment
alone is not sufficient; if only the ordinary branch fails, selection/identity
is implicated within that conditional model. This tests a difficult ambiguity,
unlike another batch of easy rank1 physical draws. No fresh control or position
campaign is authorized by these findings.

Broader priorities and verified prior work remain in [the independent review](REVIEW.md).
