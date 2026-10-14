# Model A: retained v1 failures and measured runtime amendment

The first four explicit v1 units on coverage 009/013 saved **eight stationary
scientific calls** before their outer attempts failed. No position reference was
joined, no failed unit was retried, and the remaining twenty units were stopped
before launch. The original frozen runner and all failed namespaces remain
unchanged.

| Case / start 0 condition | High fit s | Final fit s | Outer process s | Retained failure |
|---|---:|---:|---:|---|
| 009 original high | 0.824616 | 1.362159 | 74.55 | NumPy int64 tuple serialization |
| 009 low-timing lock | 0.126274 | 2.647781 | 92.92 | Whole-unit deadline during recursive post-audit |
| 013 original high | 2.598519 | 4.192770 | 92.82 | Whole-unit deadline during recursive post-audit |
| 013 low-timing lock | 0.079422 | 2.131603 | 71.26 | NumPy int64 tuple serialization |

The original serializer recurses into lists but leaves tuples unchanged. The
new runner passed a tuple of NumPy receiver IDs as `fixed_shift_receivers`.
That new runner metadata bug escaped its mocked orchestration tests. The v2
tests therefore execute the actual public runtime, original objectives,
optimizers, sequential core and file writer on synthetic orbit/input ports.
They do not mock scientific fitting or terminal serialization.

Two separate **zero-fit** profiles bind their profiler and frozen parent bytes:

| Case | Source closure traversal s | Qualified recursive parent read s | Original training preparation s | Total profile s |
|---|---:|---:|---:|---:|
| 009 | 3.557251 | 21.214766 | 18.415190 | 43.277070 |
| 013 | 5.067682 | 29.478732 | 16.923108 | 51.585002 |

All six original A receipt checks together took under 0.1 s on each case.
Both profiles made zero optimizer, objective and predictor calls and loaded no
reference or held observations. Repeating full recursive parent qualification
after fitting can exhaust the 90 s unit budget even when fitting takes only a
few seconds. Increasing scientific call budgets would not address that cost.

## Corrected bounded adapter

`tools/ds21_model_a_timing_runtime_v2.py` qualifies the genuine v1 parent reader
once at its own freeze, preserving every original source/semantic check. It
then pins an exact-byte manifest of live sources, ancestor archives, original
inputs, case/partition frames, causal bank, initialization, original A receipts
and failed v1 attempts. Per-unit checks hash those bytes and verify the original
directory inventories rather than rebuilding the recursive chain.

The narrow reusable port, `tools/model_a_verified_manifest.py`, rejects edits,
missing files and added unpaired authority files. It pins only exact case/stage
directories, leaving unrelated active sibling cases outside the manifest.
`development-errors*` filenames are the explicitly excluded derived reports;
they do not authorize changes to scientific source or receipt trees.
This port cannot confer qualification by itself: its caller must first use the
genuine scientific reader, then bind the resulting authorities.

Training still uses the exact original `prepare_training_case`,
`validate_preparation` and `load_bank` ports and the same frozen candidate
indices. The original low/high/final mathematical models, own-path seeds,
observations, fitted c, priors and 25 km local domains remain matched. Both
conditions use the same amended runtime. Preparation has a separately declared
**30 s** bound, justified by the measured 16.9–18.4 s cost; the complete unit
retains **90 / 105 / 110 s** internal / external TERM / external KILL bounds.
Scientific high/final calls retain **20 s and 600 iterations**. Five seconds
are reserved for final byte checks before admitting another call. A source-bound
zero-fit v2 qualification must measure actual byte-check and preparation costs
before remaining scientific units are admitted.

The two completed start-0 calls per case can be recovered **as metadata only**.
Recovery validates the retained failed outer attempt and exact high/final
launch/call/termination triples, identities, own-path physical seeds, original
options/domain, stationarity and timing-lock scope. It never predicts, evaluates
an objective or runs an optimizer. Every recovered scientific numerical field
stays exactly equal to its original call receipt. The lost in-memory calibration
projection and offset/timing diagnostic are explicitly unavailable rather than
fabricated. Each new terminal says `recovered-metadata-only`, references the
unchanged original failure and declares zero recovery scientific calls.

The remaining ten units per case may make at most **20 new calls**. Together
with four reused v1 calls per case, the original 24-call-per-case matrix budget
is unchanged. The original failed attempts remain failures; their successful
individual scientific calls are not represented as new fits. All twelve v2
unit outcomes and both training-objective selectors must be sealed before the
configured-reference evaluation. No reference join is authorized on the
incomplete failed v1 matrix.

New component tests cover real synthetic end-to-end writing for both conditions,
NumPy tuple normalization, exact-byte edits/deletions/added receipt inventory,
derived-report exclusions, unrelated sibling cases, orphan refusal and exact
receipt-only recovery of both failure types, wrong inherited-low identity after
rehashing the terminal, and prerequisite stage inventory. The 14-test suite passed in
2.26 s; Ruff passes. Root independent source review and real zero-fit v2
qualification precede any remaining fit. The generic full-pipeline runtime
problem is a separate coordinator-owned follow-up; this adapter stays scoped
to the declared A timing experiment.
