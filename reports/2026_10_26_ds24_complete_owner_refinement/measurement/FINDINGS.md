# Complete accepted-owner measurement refinement

All **159 original native observations** from the four frozen owners completed payload, whole-window archived-candidate parity and local refinement checks. Eight exact prior results were reused and 151 new paired detector calls were made. Every point passed the frequency and margin numerical checks, with no boundary hits, fallbacks, failed slots, retries or replacements. The complete measurement vector is therefore available for the separately controlled position experiment; this branch makes no position or recorded-frequency accuracy claim.

The native CFO changes span **−154.658 to +200.633 Hz**. They occur in both high-susceptibility targets and lower-susceptibility controls and vary over each complete owner. All 159 original residual CFOs were zero, meaning that their original final CFOs equaled the acquisition-stage estimate. Continuous refinement changes that result within the original winning score cell; it does not establish that the acquisition error equals the change.

| Case and fixed role | Original complete owner | Points | Change range (Hz) | Change RMS (Hz) | Descriptive quadratic RMS before → after (Hz) |
|---|---|---:|---:|---:|---:|
| 0010 target | RX1 CH7 T001 | 38 | −154.658 to +160.807 | 60.803 | 535.274 → 533.831 |
| 0010 control | RX2 CH4 T004 | 37 | −94.957 to +134.693 | 58.756 | 145.875 → 146.453 |
| 0011 target | RX2 CH4 T000 | 64 | −101.253 to +200.633 | 75.023 | 362.493 → 372.004 |
| 0011 control | RX1 CH1 T007 | 20 | −113.458 to +111.437 | 62.136 | 62.390 → 88.071 |

![Complete original-owner changes](report/complete_owner_changes.png)

The targets, controls, all IDs and owner membership were inherited without reselection from the previous RF-only panel. Eight stars show exact reuse of the earlier fixed time-quantile measurements. The remaining 151 physical windows are distinct, so no additional deduplication reduced the new call count. These are development scans and RF-selected owners, not a fresh or representative accuracy panel. Selection used a fixed local Gaussian/VI susceptibility calculation under the original nuisance assumptions, including absent physical-mode uncertainty for some families; it did not measure a bad-family bias or promise calibrated position precision.

## What the measurement comparison establishes

The historical detector returned 2,544 acquisition candidate records across the 159 physical windows. The immutable tracking exports contain **1,849 complete fractional candidate rows** across both receivers. Every archived row, including counts/order/rank, integer and fractional epoch, CFO, exact/control scores, margin and original gate, matched its historical replay. All compared floating errors were exactly zero. Returned records and archived parity rows are separate denominators in [candidate_parity.csv](report/candidate_parity.csv).

Only the original receiver's original winning rank was refined, using the unchanged previous refiner and historical runtime/policy. Integer/fractional epoch, within-symbol demodulation, symbol set, ownership, admission and alias decisions were unchanged. Both exact and control scores were refined inside their original winning residual-frequency cells; their independent direct-reference numerical guards passed. This is local numerical stability, not a globally certified peak or physical single-source test.

The method has prior art in [the existing GLRT64 continuous-refinement tool](https://github.com/misko/leo-tracker-reduxredux/blob/main/tools/report_470384_continuous_glrt_refinement.py). This iteration tests its bounded DS24 complete-owner transfer under exact historical parity. It does not introduce continuous GLRT refinement as a new algorithm.

![Fixed-degree descriptive temporal structure](report/descriptive_structure.png)

The degree-2 description was fixed before execution: separate unweighted Legendre fits before and after refinement, on each complete owner's unchanged time range and native IDs. RMS decreases for one owner and increases for three. This is not a physical satellite residual or error metric, and neither direction establishes better or worse true CFO. No point was trimmed, and no polynomial result changed a gate or selected the downstream vector.

## Complete vector, timing and audit scope

[corrections.json](corrections.json) preserves one row per native ID with original, proposed and downstream CFO, qualification/fallback/status flags and owner identity. All 159 downstream values are qualified refinements in this run. The declared fallback rule remains explicit: a numerical-unqualified point would retain original CFO without dropping it; a payload/parity failure would additionally make complete-input coverage false. The full [all-slot CSV](report/all159_slots.csv), [owner summary](report/owner_summary.csv) and [descriptive temporal rows](report/temporal_descriptive.csv) retain every observation.

The delta is **native refined minus native original**. Any later graph-value injection must add that delta to the existing values without rewrapping or changing aliases. The identical 159-ID vector applies to both c0 and fitted-c; the measurement operation itself does not use c. Position likelihood membership and original owner identities are not rebuilt by this branch.

Preparation and execution consumed **337.479 cumulative worker-seconds**, below the original 480-second cap. This includes 10.821 seconds of charged metadata/tests/preparation, the failed-freeze allowance, and both measured worker process durations. Two fixed batches made 76 and 75 new paired calls under one BLAS thread each. Their original runtime identities matched before and after. Both processes exited zero with empty stderr.

An initial user-side freeze attempted to hash service-readable source-input bytes and failed at that permission boundary, after successful public metadata preparation. Its [source](complete_preparation01.py), [failure receipt](failed_freeze01.json) and original preparation are preserved. The final protocol separates metadata-verified public input/index digests from user-readable source bindings; service workers verified those public bytes again before payload access. No metadata retry, payload read before authorization, permission/configuration change or scientific-rule change occurred.

The exact [protocol](protocol.json), [preparation](preparation02.json), [all requests](requests.json) and [RF seal](RF_seal.json) bind the completed run. Independent [preflight](../audit/measurement_preflight.json) and [terminal audit](../audit/measurement_terminal.json) passed. The terminal audit checked all 159 slots, 9,245 archived floating fields exactly, and 318 saved-correlation direct complex-score cells with maximum error below 9e−15, without new IQ or detector calls. No new RF, IQ extraction method, orbit propagation, catalogue nomination, graph fit, position fit, GPS read or operational change was performed here.

## Replay and publication limits

The narrow reader used public `FastSegmentSource` with explicit frozen segment/index authority and fully exhausted each bounded iterator. QNAP input remained read-only. Replay requires those external raw segments/indexes, original tracking/input files and the exact historical deployment and environment in the protocol. Neither IQ nor a standalone historical runtime is republished.

Full paired detector results and derived exact/control correlations are preserved locally in `worker0.json` and `worker1.json`, hash-bound by the RF seal. A compact publication retains all 159 correction/flag rows, parity denominators, figures, source/tests, protocols and provenance. [local_artifacts.json](local_artifacts.json) identifies larger local evidence and its hashes. The separately owned position stage must evaluate frequency/score behavior, original gates and geographic accuracy independently; this report alone supports no localization improvement or rollout.
