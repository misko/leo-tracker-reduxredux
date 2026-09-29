# Held-out rate-gate transfer panel

This prepares independent saved-IQ validation for a coarse-score gate tuned on
DS7.  It performs no candidate execution and makes no performance or quality
claim.  The panel reuses the already sealed DS8 and DS9 mixed-rate selections:
32 dwells from each dataset, with four metadata-spaced dwells per rate/edge
cell.  Each 32-dwell run begins with its eight 2.5 MS/s dwells, where the
proposed threshold is most aggressive, then covers 5, 7.5, and 10 MS/s.

`selection.json` binds all 64 contexts to the 680-dwell input receipt, IQ file
hashes, frozen DS8/DS9 baseline, proposal-feature rows, and existing ungated
full-search reference rows.  IQ remains under `/var/tmp`; this report neither
copies it nor writes to QNAP.  The evaluator accepts `--inputs`, so the dataset
root is explicit rather than inherited from the DS7 harness.

After a host gate build is sealed, run DS8 first and then DS9:

```sh
python3 reports/2026_09_29_arm_rate_gate_transfer/evaluate.py \
  --binary GATE_BINARY --receipt GATE_BUILD_RECEIPT \
  --inputs /var/tmp/leo-arm-ds89-validation/inputs \
  --reference reports/2026_09_29_arm_psd_proposal/host-ds8-full-v2 \
  --features reports/2026_09_29_arm_lag_discovery/ds8-32-v1/rows.jsonl \
  --radius 2 --top 4 --allow-proposal-changes --output host-ds8-gate
python3 reports/2026_09_29_arm_rate_gate_transfer/audit.py \
  --cohort reports/2026_09_29_arm_rate_gate_transfer/host-ds8-gate

python3 reports/2026_09_29_arm_rate_gate_transfer/evaluate.py \
  --binary GATE_BINARY --receipt GATE_BUILD_RECEIPT \
  --inputs /var/tmp/leo-arm-ds89-validation/inputs \
  --reference reports/2026_09_29_arm_psd_proposal/host-ds9-full-v2 \
  --features reports/2026_09_29_arm_lag_discovery/ds9-32-v1/rows.jsonl \
  --radius 2 --top 4 --allow-proposal-changes --output host-ds9-gate
python3 reports/2026_09_29_arm_rate_gate_transfer/audit.py \
  --cohort reports/2026_09_29_arm_rate_gate_transfer/host-ds9-gate
```

The reference rows select and inventory the held-out contexts; the independent
audit scores gate output against the original DS8/DS9 full-search baseline.
Report each dataset and each rate separately.  Do not pool the 64 dwells into a
DS7 denominator or interpret unmatched positive candidates as false alarms.

## Broad 2.5 MHz ARM reference

`reference-wave4-2500` is an order-preserving filter of every 2.5 MHz row in
the sealed Wave4 host704 run: 152 dwells and 3,344 receiver/windows.  It adds no
selection and can be passed directly as `--reference` to the fused evaluator.
`source-bindings.json` records source and filtered hashes, and
`test_wave4_2500_reference.py` verifies exact row and context equality.

```sh
python3 reports/2026_09_29_arm_fused_pipeline/evaluate.py --arm \
  --binary ARM_BINARY --receipt ARM_BUILD_RECEIPT \
  --reference reports/2026_09_29_arm_rate_gate_transfer/reference-wave4-2500 \
  --inputs /var/tmp/leo-ds7-large-arm-20260928 \
  --features reports/2026_09_29_arm_proposal_features/host704-omit-power-v1/rows.jsonl \
  --radius 2 --top 4 --allow-proposal-changes --output ARM_OUTPUT
```

The fused adapter still reads the bound feature inventory even though the
four-argument fused binary calculates proposals internally.  No ARM execution
was performed while preparing this reference.  `STATIC_ANALYSIS.md` records
exact-output overhead opportunities outside the separately owned peak-ranking
optimization.
