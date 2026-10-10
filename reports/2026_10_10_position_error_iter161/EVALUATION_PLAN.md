# Postseal position evaluation

Preparation only. No reference coordinates are read by this plan. Publish a
separate evaluation protocol before execution; inference and its 72 attempted
fit receipts remain immutable.

Require all 12 declared members and all six cells per member to seal: full data,
training fold 0 and training fold 1, each with fitted-c and c = 0. Verify the
inference protocol, source/input hashes, matching claims, cell identities and
terminal statuses before importing an evaluation port. Failures count toward
coverage but never receive invented position estimates. Orphan claims and
missing cells block evaluation.

## Evaluation authority and narrow API

Use iteration 107's public research `evaluation_document(member)` and
`evaluate_fit(operation, document)` ports only after this terminal gate. Pin
its protocol file SHA256
`24df105bf4618947162f9438ea2a77115d1baa134a00b5f7b48279942848d227`.
Prepare an evaluation-only source closure from iteration 154's
`evaluation_source_sha256`; verify that closure before loading the ports.
These hashes are evaluation admission, not inference dependencies.

Resolve the exact label through the frozen 107 inventory, then compare its
session to `member.binding.session_id`. Authenticate the existing sanitized
document path/hash and compare session, input manifest, analysis manifest and
evidence identities plus `configuration.prior` to the evaluation document.
Do not call iteration 129's callback unchanged: it expects a `membership`
field that the 155/160 member schema does not contain.

For a qualified cell, wrap its retained solver fit as the operation expected
by `evaluate_fit`, preserving its original vector, clock and joint-state
fields. Return its existing geographic `error_km`; never refit or change a
coordinate convention. Cache the authenticated evaluation document once per
member. A missing required solver field or mismatched prior is an explicit
evaluation failure, not a replacement endpoint.

## Comparisons and denominators

Report all 72 statuses and independent qualification outcomes. For each c arm,
compare training fold 0 and training fold 1 separately against the fresh full
control. Do not select the better fold or c arm. Report mean, median, p95 and
worst error for each method, with its qualified/evaluable denominator and
failure counts. Withhold a full 12-member method aggregate if any member is
unavailable; a labeled qualified subset may be shown separately.

Paired comparisons use only members qualified and evaluable for both methods;
report pair counts, improved/equal/regressed counts, every regressing label,
mean delta and maximum regression. Use the same declared equality tolerance
for every pair. Describe all-pair results as consumed-data sensitivity.

Give separate DS16, DS17 and DS18 tables, four members per dataset. These are
pilot subsets, not the full 63/51/34 authorities or independent validation.
Keep historical endpoints as explicitly historical context only, if included;
the fresh full-data fit is the matched control. No failed fit falls back to
its historical endpoint. The official 193-member research metric remains
unchanged.

Plot both c arms, all three methods and qualification/missing markers. Keep
held likelihood, training priors, frequency fit and position error separate.
Better held or in-sample likelihood is not proof of better localization.
Full-data bank, start, retained region and satellite-center conditioning remain
explicit; acquisition-disjoint folds do not establish statistical independence.

## Required reporter tests and publication

Use synthetic receipts to prove missing/foreign claims or the last unsealed
cell prevent every evaluation callback. Check failed/unqualified fits remain
in coverage, paired denominators exclude unavailable endpoints without
zero-filling, c arms cannot cross, and all regression labels are retained.
Publish receipt/protocol/evaluation-source hashes alongside the report and
visualizations. No posthoc method winner becomes an operational policy.
