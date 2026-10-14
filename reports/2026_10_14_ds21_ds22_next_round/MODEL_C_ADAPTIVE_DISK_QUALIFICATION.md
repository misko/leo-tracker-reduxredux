# Retrospective C adaptive-disk qualification

The generic training-only policy reproduces the two previously sealed mechanism
releases without new fits. Source-frozen qualification completed in 33.803 seconds
including preparation: 62 objective evaluations, zero new optimizer calls. All 18
original endpoints remain in the eligibility inventory.

| Cohort/case | Accepted originals | Qualifying starts | Training-selected endpoint | Objective |
|---|---:|---|---|---:|
| Before031 | 2/6 | 1, cold-1 | Carried release, start1 | 33519.043761 |
| After003 | 6/6 | 4, shape-high | Carried release, start4 | 27116.940694 |
| After023 | 3/6 | None | Original, start1 | 28547.848276 |

Both carried calls used the exact original endpoint vector/nuisance, unchanged
20-second/600-iteration fitted-c options, and a 25 km disk recentered on their
own endpoint. Saved raw/effective starts, source endpoint/center identity and
returned objective, likelihood NLL and physical KKT were independently checked.
The seven nonstationary original endpoints were retained as ineligible rather
than discarded from the source inventory. The live bounded port was tested with
the real fitter; nine component/driver tests and Ruff passed.

These are the same physical endpoints already reported: configured errors
before031 26.287029→10.221273 km and after003 5.214916→1.820655 km; interior
after023 remains 5.258300 km. No new reference or held data were loaded by this
qualification. It establishes that the rule, applied to all six starts, carries
exactly those two releases. It is retrospective mechanism qualification and does
not provide new independent accuracy validation. Before031 demonstrates original
whole-union exclusion; after003 demonstrates a winning-path disk restriction,
because another original disk contained its released endpoint. Neither result
meets the sub-kilometer target.

The relevant scientific inventory is 18 original C-all calls and two carried
policy release calls. Four prior incidental mechanism controls, the other case
model calls, initialization and discovery costs remain separate. Zero new fits
does not mean zero preparation or zero upstream cost.

Authoritative local namespace:
`local/model-c-adaptive-disk-qualification-v1`. Protocol source commit
`399bb3aa3`; 2407 source/input/receipt bindings were frozen before preparation.
Terminal SHA256 `6010be04c383358bfa27374b1b250b434fdc28a32a0705960242d7e66b8d94ce`;
seal SHA256 `dfea91b0f7dc85724f348a1389b31acaee3fe57524b5b12b182f04cd7f2a5759`.
The qualification includes 180-second internal, 195-second TERM and 200-second
KILL whole-operation limits. Original scientific sources/results are preserved.

The next prospective screen is separately frozen for all six genuine C-all
endpoints of before029, before037 and after029. No additional release fit follows
automatically; trigger counts and a concrete call budget must be reviewed first.
