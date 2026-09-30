# Identity evidence: session effects and limited revisit support

The existing DS7–DS10 identity comparisons do **not validate a satellite
identifier**. Their strongest apparent real-sign association weakens under
trajectory-preserving controls, and episode-weighted retrieval does not beat
the nearest-time baseline in the best-supported same-session cohort. Sparse
cross-session and stronger-label coverage also prevents an exhaustive negative
claim about information in the recorded signals.

## Revalidated support

The audit reads the current deduplicated 1,393-entry metadata and the frozen
identity receipts. For every matched positive pair it independently checks
that both entries have the recorded conditional candidate label and that the
stored cross-session flag matches the actual sessions.

| Original matcher | Matched positive pairs | Cross-session | Distinct conditional candidates |
|---|---:|---:|---:|
| Strict same-channel | 1 | 0 | 1 |
| Broader same-channel pair matching | 30 | 1 | 25 |
| Broader different-channel/different-session matching | 7 | 7 | 3 |

The other five scope/tier combinations abstain. In particular, all stronger-label
experiments have no same-candidate pairs with suitable different-candidate
controls. A large count of different-candidate pairs does not repair missing
positive-control support. Conditional orbital candidate labels remain external
hypotheses, not identities decoded from RF or confirmed SATAddr values.

## Why the apparent lead is insufficient

In the broader same-channel comparison, the real-sign excess is .1031. The
original instrument-stratum test gave a corrected value .016; adding session
preservation gave .048. The trajectory-preserving maximum-statistic reference
instead gives **.356**. Of the 30 matched pairs, **29 are within a session**;
requiring at least 120 seconds of separation leaves just one pair. That pair
cannot establish general identity transfer.

The seven different-channel/cross-session pairs span only three conditional
candidates and fail session-preserving correction. They provide neither a
validated identity feature nor strong evidence that no such feature exists.
These are inspections of the complete prior controls, not new repetitions of
an already unsuccessful search.

## Episode-weighted retrieval

The audit independently regroups every stored query by `(session, candidate)`
and recomputes equal-episode metrics, so multiple receivers or gallery choices
cannot give one episode extra weight.

| Scope | Episodes | Sign retrieval credit | Nearest-time credit |
|---|---:|---:|---:|
| Same session/channel | 7 | .643 | .857 |
| Different session, same channel | 2 | .000 | .500 |
| Different session/channel | 5 | .333 | .000 |

Credit includes the original tie handling. The final row is too small to treat
as confirmed superiority: its saved descriptive interval for sign-minus-time
includes zero. The two-case same-channel result is likewise insufficient to
characterize all revisits. These small cohorts are not independent confirmation
of the original feature-selection screen.

## Stable coordinates are not yet specific

Six frozen stable-coordinate experiments (three DS10 donors, with/without
symbol 2) retain their exact coordinate lists and per-candidate comparisons
in the expanded ledger. Other conditional satellites can match these patterns
strongly. Many target comparisons have no strict matched controls; a high
raw agreement is therefore not evidence of a unique address. Receiver
consensus establishes repeatability before it establishes specificity.

The recent positive I-symbol 3/4/6 receiver result answers a different question:
whether two receivers share structured variation in the same excerpt. It does
not by itself repair the missing cross-visit identity demonstration here.

## Reproduction and status

```sh
uv run --no-project --with numpy python reports/2026_09_29_firmware_cluster_reaudit/identity_scope_audit.py
OPENBLAS_NUM_THREADS=1 uv run --no-project --with numpy --with matplotlib python reports/2026_09_29_firmware_cluster_reaudit/association_ledger.py
```

Ignored `local/identity-scope-audit.json` preserves complete pair experiments,
stable-coordinate comparisons, recomputed episode metrics and hashes. The
ledger adds 17 association families and now has 388 entries. All 22 component
tests pass, including a test that repeated gallery opportunities do not upweight
an episode. No new RF or broad scan was run. Semantic field mapping and the
remaining association inventory are still unresolved under the active goal.
