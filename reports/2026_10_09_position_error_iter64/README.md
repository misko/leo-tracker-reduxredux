# Iteration64: metadata-only retries preserve full cohort coverage

DS16-020 (historical S14) and DS16-035 (S27) failed iteration51 replay output
serialization with `KeyError('bank')`. Their corrected historical baseline
documents omit bank metadata; the numerical baseline and recorded inputs remain
available. These are setup/output failures, not localization convergence failures.

Both original immutable failure receipts remain in iteration51/results. This
separately frozen retry uses the original case document's bank and TLE snapshot
metadata only when serializing a new replay. It asserts matching session, input
and analysis digests and equality of the reconstructed bank's satellite IDs.
The baseline scores, observations, starts, priors, c locks, regional budgets,
selection rule and downstream model are unchanged. New caches/results are isolated
under this iteration. No original numerical source or result is overwritten.

The retry was launched for both members; no successful outcome is claimed in
this launch report. The cohort reporter incorporates only completed, protocol-
bound retries and retains original attempts plus the exact completion source.
Failed or pending retries remain explicit; neither member is excluded.

![Current full-cohort comparison](../2026_10_09_position_error_iter51/comparison.png)

The cohort report now includes separate DS16 original48/added15 metrics and
DS18 prior-registry24/unmatched10 metrics, with exact membership assertions,
coverage, paired regressions and convergence/fallback counts. No earlier registry
match is not evidence of independent validation. All evaluated recordings are
consumed research. The scientific goal still requires full148 coverage and
further improvements; subgroup means never replace full-dataset results.

Frozen retry commit0d13db115. Public contracts, production settings, fixtures,
QNAP corpus and RF collection are unchanged. The live hard/smooth pilots retain
their original frozen numerical implementations and budgets.
