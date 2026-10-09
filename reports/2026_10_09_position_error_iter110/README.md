# Frozen persistence pilot: awaiting execution

The twelve-recording pilot is frozen, with no recording fit yet run. All ten
synthetic preparation tests pass. The two available numerical worker slots remain
occupied by the full193 recovery comparison in iteration107. Production B7 is
unchanged, and the 0.4 km mean position-error objective remains unmet.

Protocol SHA256: `64797ea7bdb2b04f0561fc876e7bb82b3911b27456b0702cc4ceb9b4be18758c`.
All 2,333 source hashes were verified after freezing. The preparation documents
describe their pre-freeze state; this page records the subsequent freeze.

The experiment tests whether weak satellite-identity evidence benefits from
linking nearby observations. The marginal-preserving transition avoids changing
the per-observation satellite prior. It compares fixed rho=0.5 with rho=0, using
the same bank, observations, starts and other priors, separately for fitted-c and
c=0. No cross-model score selects an operational winner.

The [full148 ambiguity census and visualization](../2026_10_09_position_error_iter108/RESULTS.md)
motivates a small mechanism trial: only 43.6% of observations have eligible links,
and most linked observations already have high model confidence. Confidence is
not correctness, and a position benefit is unproven.

| Dataset | Selected inventory labels |
|---|---|
| DS16 | 020, 024, 054, 058 |
| DS17 | 006, 015, 027, 031 |
| DS18 | 013, 023, 024, 029 |

The fixed seed ranks all148 members without reading their position errors or
quality. All selected recordings are consumed development data. Failures remain
in coverage; there are no replacement draws. Full membership, ranks, session IDs,
source bindings and progression criteria are in [protocol.json](protocol.json).

There are at most48 fits. Each uses the existing 90-second solver budget and
600-iteration limit; the time check occurs between objective calls and is not a
hard process timeout. Actual time and objective evaluations must be reported.
Exclusive controller claims prevent automatic reruns after an interrupted launch.

The frozen screening rule requires all48 raw fits to qualify, at least5% fitted-c
mean improvement, a nonworsening fitted median, no increased worst error in either
arm, no paired regression above1 km, and at most5% c=0 mean degradation. These
are development screening conventions, not independent validation or deployment
approval. Reference coordinates remain evaluation-only apart from the explicitly
disclosed inherited provenance equality check.

See [preparation](PREPARATION.md) and [reviewed criteria](PILOT_REVIEW.md) for the
matched-start, clock-lock, failure and fallback details. No RF collection or
reserved-data access is involved.
