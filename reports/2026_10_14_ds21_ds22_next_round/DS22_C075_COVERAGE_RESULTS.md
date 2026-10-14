# C075 broad coverage: all 44 calls returned, none stationary

Both native-model arms remain **unavailable** after the full prespecified 44-call inventory. Neither the original-six subset nor the full-22 selector has a strictly accepted endpoint. All calls report solver_success false under the nominal 20-second budget; KKT ranges from 356.699 to 5557.408. No configured-reference comparison was performed for these unavailable selectors, and this is not evidence that broad coverage or native common clocks are scientifically ineffective.

The same 87-satellite union was used throughout. Each arm attempted all six original native endpoints on their own 25 km disks and all sixteen original coarse-grid states on 100 sqrt(2) km disks. Source qualifications established exact original native transport, zero-clock nesting, and complete-clock native-time calibration closure. The original-no-clock coarse projection loses 100.086–776.599 Hz RMS; the clock arm preserves those source functions. No propensity model was used.

## Orchestration completion preserves the scientific inventory

The initial five-worker paired-unit wave completed in 472.193 seconds. It returned 36 scientific fits: fourteen complete two-call units and eight units that completed projected-model fitting but refused admission of the clock fit because reconstruction plus first-call time exceeded the frozen 85-second cutoff. Original units 1–8 retain those failure receipts.

A separate source-frozen continuation inventoried every original claim and raw outcome, then executed only the eight absent clock calls. There were no original clock claims or attempted fits for those ordinals. Six one-call workers completed that finite wave in 146.247 seconds, under expanded outer orchestration bounds 180/195/200 seconds while preserving the scientific 20-second/600-iteration limits. No scientific call was repeated; the new authoritative seal combines exactly 36 original outcomes plus eight previously unattempted outcomes. It does not rewrite the failed original units as complete.

All 44 invocation CPU/wall ratios are 0.999620–0.999978. This does not indicate current CPU starvation, and does not establish an underlying physical or likelihood failure. Evaluation counts range from 1 to 315; increasing the bank and timing dimension substantially changes the amount of work completed under a fixed time budget.

## Prespecified next budget diagnostic

Minimum returned training objective within each model and disjoint source group chooses original endpoint ordinal 2 and coarse ordinal 7 in both arms. These are diagnostic endpoint scores, not accepted solutions:

| Model | Source group | Ordinal | Returned objective | KKT |
|---|---|---:|---:|---:|
| Original no clock | Original six | 2 | 40455.333097 | 511.271 |
| Original no clock | Coarse sixteen | 7 | 43085.342693 | 5557.408 |
| Native common clock | Original six | 2 | 39812.432827 | 1503.774 |
| Native common clock | Coarse sixteen | 7 | 40659.785400 | 1383.127 |

A separate matched fresh 20/60-second control may start from the **original qualified initializers** corresponding to those four entries, not their failed endpoints. This would add eight explicitly budgeted calls with unchanged domains and stationarity gates; it is not a retry inside the original namespace or a reference-selected experiment. Outcomes of that diagnostic are not included here.

## Evidence

- Original paired pilot source `b432ea6e3`; original qualification source `20621912f`; shared exact native control port `779f50cb3`.
- Completion source `98b73f081`; three recovery-inventory tests and Ruff pass. Original five pilot/helper tests passed.
- Original namespace: `/srv/bulk/leo-research-ds21-ds22/2026_10_14/ds22-c075-coverage-pilot-v1`.
- Explicit all-44 completion authority: `/srv/bulk/leo-research-ds21-ds22/2026_10_14/ds22-c075-coverage-completion-v1/terminal.json` and adjacent `seal.json`.
- Wave receipts: `ds22-c075-coverage-wave-v1` and `ds22-c075-completion-wave-v1` beneath the same bulk root.

The original cohort, failed calls, and configured-unconfirmed station limitation remain unchanged. No held or locked observations were used and no model is promoted.
