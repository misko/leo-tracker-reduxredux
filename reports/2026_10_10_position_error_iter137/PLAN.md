# Full-cohort phase-model comparison preparation

Iteration 135 improved the consumed 12-scan fitted-c pilot mean from 1.117359 km to 1.033639 km and median from 0.905836 km to 0.807675 km. Nine scans improved and three regressed; the largest regression was 0.109111 km. This warrants a full-cohort controlled comparison, not deployment or a claim that the existing timing convention is a clock bug.

This preparation makes no recording, model, optimizer, or reference-error queries. No numerical protocol is frozen and no fits are authorized by this document.

## Membership and comparison

Use all 193 members of the frozen iteration 107 development authority: DS16 63, DS17 51, DS18 34, and newer development 45. Preserve DS16 original-48/added-15 and DS18 prior-exposure labels. Existing reserves remain closed. These are consumed research data, not independent validation.

The archived comparator is each member's **latest iteration 107 candidate selection**, including calibration recovery such as ac11. Do not substitute an older baseline or the pre-recovery regional winner. Archive fitted-c and zero-c results remain separate historical comparators. An archived zero-c result may have a different bank or region; that is not an input failure and must not exclude the member.

New ordinary-control and phase-model fits use the same fitted-selected bank, observations, nuisance priors, receiver baseline, satellite centres, vector, and clock coefficients. All four starts derive from the fitted selected endpoint. Both zero-c starts lock static c and RF-time coefficients to zero under the ordinary production rule. Apply the unchanged iteration 135 relative-phase objective globally, with its same budgets, qualification rules, and explicit archived fallback. Never choose a physical convention separately for a scan by score or reference error.

Report fresh-control versus phase effects separately from continuation effects relative to the archive. Frequency likelihood, priors, support, qualifications, runtime, and position accuracy are separate outcomes. All failures and fallbacks retain their membership rows. Full-cohort accuracy summaries require complete coverage; qualified-subset summaries, if useful, must state their denominator explicitly.

## Metadata feasibility receipt

`source_feasibility.py` reads saved checkpoint metadata through the documented iteration 105 `Overlay.get` port. It verifies checkpoint protocol and canonical value digests; it does not evaluate those values. `source-feasibility.json` records all 193 members and per-arm source hashes.

| Dataset | Members | Present, qualified fitted-c B7 | Present, qualified zero-c B7 |
|---|---:|---:|---:|
| DS16 | 63 | 63 | 63 |
| DS17 | 51 | 51 | 51 |
| DS18 | 34 | 34 | 34 |
| Newer development | 45 | 45 | 45 |

All referenced sanitized source documents exist. The 45 newer members use a different protocol schema without a top-level `model_identity`; this is a binding-resolution gap, not evidence of absent physical inputs. Resolve their exact identities from the documented newer source/loader bindings. Do not infer compatibility from presence alone.

The candidate containers total 29,810,811,202 bytes. Reading the baseline and candidate containers wholesale would repeat roughly 57 GB of metadata I/O. The B7 checkpoint `joint_state` already supplies vector, clock coefficients, clock nodes, final receiver baseline, and satellite centres. It does **not** establish the operationally selected satellite IDs, accepted stage, or source region. Qualified saved B7 receipts therefore do not by themselves prove that B7 was the selected endpoint.

## Lean inference binding

Prepare a small inference-only projection of each selected operational endpoint: session/input/analysis/evidence identities, selected stage/source region, satellite IDs in order, saved fitted vector/clock, final receiver baseline, nodes, centres, and required model policy. Bind the projection itself for inference admission; full reference-bearing report hashes may be retained as preparation provenance, but cannot be runtime gates. Use the clean iteration 131 public-input loader, as proven by iteration 132, without legacy reference/error equality checks.

For a selected B7 state, reconstruct the ordinary model using the saved final `receiver_baseline_hz`, nodes, and centres. Zero initialization knots are a candidate lean gauge representation: original knots affect the baseline subtraction and initial clock, while nodes determine clock design and precision, and the fit receives explicit saved clock seeds. This representation is **not approved for execution until parity tests pass**. Preserve exact 0.5 Hz/s slope precision and all other model fields.

If a selected stage is earlier than B7, record it explicitly. Do not silently convert a C6 or regional fallback into a B7 model or drop the member. Such cases need an exact corresponding reconstruction or a predeclared unchanged fallback row.

## Required admission tests before freezing fits

1. Synthetic original-knots versus final-baseline/zero-knots reconstruction must match score, full gradient, physical constraints, nuisance design, and precision at explicit saved vector/clock states, including nonzero timing and c.
2. Clean projection extraction must ignore poisoned reference/error fields and verify session, input, analysis, evidence, bank order, and all five physical input signatures. A mismatch produces a terminal input failure before any fit.
3. Saved fitted endpoint objective parity is mandatory on its exact selected model before fitting. Archived zero-c parity is checked only when that archived endpoint's bank/model matches; otherwise it stays a historical comparator, with no substituted endpoint or member exclusion.
4. Four-call flow tests must prove matched fitted-derived starts, zero-c locks, unchanged budgets, failed-attempt preservation, immutable resume, and no per-scan winner choice between physical conventions.
5. Reporting tests must preserve all 193 rows, distinguish archive qualification from fresh qualification, withhold incomplete census aggregates, and report matched-c position and frequency effects separately.

The next step is source projection and pure synthetic reconstruction tests. Actual input reconstruction, saved-objective evaluation, numerical freezing, and fitting require a separately reviewed protocol.

## Completed preparation follow-up

The streaming extractor scanned all 193 candidate containers once, retained only selected inference fields, and produced 193 selected projections (39,319,123 bytes total). All operational fitted-c and zero-c endpoints identify accepted stage B7, and their saved selected satellite lists agree within each member. This resolves the earlier stage-selection gap; it does not replace runtime physical input or saved-objective parity checks. The policy above still permits a different archived zero-c model if later physical reconstruction exposes one.

`bindings.json` resolves all 45 newer identities through their documented source descriptor `model_identity`, and binds the selected projections, compatible sanitized documents, membership/exposure metadata, and five expected physical input signatures. All 193 members have at least one exact-identity source document. Original candidate SHA256 values live separately in `preparation-provenance.json`; they are absent from the inference-bound selected projection, so a reference-field change cannot become inference admission through a whole-source hash.

Three synthetic tests pass. The actual production SlopePrior reconstructs bit-exact score and full vector/clock gradients from the final receiver baseline with zero initialization knots. Clock design, prior precision, parameter bounds, constraint matrix, constraint values, and Jacobians also match for fitted-c and zero-c, including nonzero relative timing and an active timing face. Separate extraction tests prove reference/error perturbations do not alter inference fields and reject a nonterminal source. These are synthetic preparation checks, not objective parity on recordings or a numerical experiment.
