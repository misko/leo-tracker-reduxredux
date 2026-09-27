# Reserved constructed validation result

The frozen tone-removal rescue passes the predeclared constructed-validation
gates on all 26 previously reserved cases. This split is now consumed validation;
it must not be described as unopened or used for further tuning followed by a
claim of independent validation. Original manifests remain immutable historical
records; `generated.json` records the newly materialized validation IQ.

| Rate | Application mean CPU | Candidate mean CPU | Aggregate CPU speedup | Candidate wall maximum | Calls above 120 ms |
|---|---:|---:|---:|---:|---:|
| 2.5 MS/s | 1343.76 ms | 32.94 ms | 40.80x | 77.58 ms | 0/13 |
| 5 MS/s | 3624.72 ms | 75.25 ms | 48.17x | 203.46 ms | 4/13 |

Both the unchanged native tracked baseline and candidate produce 38
truth-associated positive receiver decisions, ten correct negatives, and four
inactive weak pilots. All required negative policies pass; no active output is
unassociated with constructed truth; primary-positive decisions are preserved
exactly; aggregate speedup exceeds 10x at each rate. The four weak misses are
explicit report-only outcomes, not counted as successful detections.

The candidate agrees with 35/37 reference-positive receiver identities. Both
reference differences are the symbol-region-support case, one per rate; native
outputs remain associated with injected truth. Native and application use
different symbol regions, so reference disagreement is not automatically a
physical detection error. These results mirror the previously observed regional
limitation; report it rather than erasing it with a visit-presence metric.

The key coverage limit is that all 80 Python candidate scores in eight rescue
acquisitions fail the proposal margin gate. There are zero native rescue seed or
confirmation calls and zero accepted rescues. This split therefore validates
unchanged primary behavior and bounded negative/weak rescue work, but cannot
independently validate the recorded development result's 11 recovered receivers
or the rescue scorer under positive held-out proposals. Recorded held-out
evaluation and larger interference cohorts remain outstanding. Ten constructed
negative receiver outcomes cannot establish a rare false-alarm rate.

## Execution and provenance

The candidate and validation protocol were frozen before generating IQ from the
old reserved seeds. Generation wrote only this directory, produced 93,603,328
bytes in 3.08 seconds, and reported zero clipped components. Metadata equality
was checked before generation with exact seeds/discrete fields and documented
1e-13 relative / 1e-12 absolute floating-point tolerance for reduction roundoff.
Unlike the protocol's CPU0 intent, generation itself was not affinity pinned;
its elapsed time is not a benchmark. Evaluation was pinned to CPU0, with all
numerical-library threads set to one, and completed in 67.18 seconds.

Complete-call timing includes conversion, primary/controller work and rescue
work. File reading, hashing, initialization and serialization are excluded.
Methods rotate within each case and use independent causal state. Every input
hash remained unchanged; both source inventories rehashed successfully after
evaluation. Original real holdout data was not opened.

The initial evaluation stopped before any detector call because its timing
helper was addressed through the wrong imported module. Its zero-row failure
receipt is preserved as `results.json`. The separately frozen
`run_timing_adapter.py` binds the existing timing helper and writes a distinct
`results.timing_adapter.json`. It changes neither scientific code nor membership.
Four validation/adapter tests pass. This wiring correction is recorded rather
than presented as an uninterrupted original run.

- Candidate-validation source lock: `bf3cd5cd2e731d72809e076a6348bc935ee1a5749f8553e5c7c190e75d28da22`
- Timing adapter lock: `82946208c32c7011d434e3d4cb34f93893b55a173f7812ff1a57b5c32daf374b`
- Generated IQ manifest: `f6cca1a97a15838cbabc581a30c87b078ee5afcf814b46060a0b3d92482aa402`
- Completed result: `2a27ba4e69aee961e92800b8285fabe8ebff1ba8b1d578f0408a961b9dabd531`
