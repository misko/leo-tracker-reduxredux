# Native coarse-score gate qualification

This isolated `.15` gate removes a retained hypothesis before fine precision,
conditioned scoring, and final GLRT when its coarse score is nonfinite or less
than `.15`. All 15,488 receiver-window rows remain present. Candidate JSON is
post-gate and its `candidate_count` equals the emitted candidate array length.

Host and ASan/UBSan ran the all-rate threshold/equality/`nextafter`/nonfinite
component test and inherited final-reuse, fine-budget, and moment-accuracy
tests. ARM was cross-compiled only.

The native 704-dwell host run emitted 119,445 candidates, removing 4,459 from
the 123,904 ungated inventory. The frozen standard audit recovered
19,226 / 19,581 hits (98.1870%), exactly matching the replay's `.15`
counterfactual recovery. Per-rate recovery was 4,515/4,573, 5,360/5,466,
5,100/5,186, and 4,251/4,356 at 2.5/5/7.5/10 Msps.

The audit permits variable post-gate candidate inventories and uses the frozen
standard matcher. Candidate and cache interactions are native-run results, so
the matching recovery does not assume replay equivalence beyond the audited
outcome. No ARM timing, speed, or quality claim is made.

Audit `candidates` is the frozen reference inventory; the audit now also
records explicit `reference_candidate_entries` and `emitted_candidate_entries`
for totals and every rate. The host values are 123,904 reference and 119,445
emitted entries. The physical four-dwell ARM units passed, but emitted all
704/704 reference candidates, so that panel provides no candidate-removal or
speed qualification for this gate.

For ARM follow-up, `audit.py --cohort PATH` accepts a completed cohort with
variable post-gate inventories. `test_audit.py` covers valid reduced arrays and
rejects count/payload mismatches or counts above eight. The fused evaluator
permits reduced inventories with `--allow-proposal-changes`: its candidate
difference count uses `zip_longest`, and its summary sums each emitted row's
`candidate_count`. Its default science comparison remains false for a removed
candidate, so the allow flag is required.
