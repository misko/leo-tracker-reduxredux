# Wave 7 chronological groups 06 and 07

This launch is frozen against the merged Wave 6 predecessor:

- frozen input: `reports/2026_09_27_ds7_wave6/inputs/inputs-first32-group8-04-05-ready-v1.json`
- frozen SHA-256: `90d3d9a95409bcdf1ed875edb0c5ebeaff1b59c17d1c373342ef1184d5e04806`
- unfrozen index: `reports/2026_09_27_ds7_wave6/inputs/inputs-first32-group8-04-05-index.json`
- index SHA-256: `39207d12fd6967a5f068cb20d64bee15d445885c7ed2002339bb05a54dca307d`
- predecessor state: 48 ready and 40 unavailable, with all 88 identities validated.

Select chronological `single-041` through `single-056`, exactly `group8-06` and `group8-07`, before their predictions or scores. Group 06 owns captures 041--048 under `inputs/group06/`; group 07 owns captures 049--056 under `inputs/group07/`. Each starts independently from the same merged-48 index and frozen contract. Root combines their disjoint additions later; neither controller modifies the predecessor or the other group's artifacts.

## Preparation policy

At most these two source-preparation workers may run concurrently. Each worker:

- uses unchanged `tools/ds7_combined_export.py`, SHA-256 `6b56233bd944b2283146b56b632b3336fe9d6844fda25c54eff04eb48a9df729`, and the unchanged Wave 4-closed exporter policy;
- writes banks only below `.leo/ds7-wave7/group06/` or `.leo/ds7-wave7/group07/`;
- has a 1,200-second outer wall cap, 1,180-second internal deadline, and 240-second per-capture cap;
- inherits a 3 GiB address-space ceiling, one CPU/BLAS thread, and nice 19;
- uses cached public source and archive ports, with no raw IQ, RF collection, reference, pose interpretation, score access, or source/production mutation;
- stops on failure or lease exhaustion, retains partial outputs, and never overwrites an attempt;
- freezes progressive 88-row snapshots, preserving the prior 48 ready rows exactly and adding only its own validated captures.

Require at least 12 GiB `MemAvailable` immediately before dispatch. At most one DS7 fitter may overlap the two preparation workers. Do not start additional scientific experiments during the pair.

## Reviewed dispatch commands

These commands are prepared but must not be run until root explicitly dispatches Wave 7.

```bash
sudo -n prlimit --as=3221225472 -- timeout --signal=TERM --kill-after=10s 1200s nice -n 19 env OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 /opt/leo-tracker/current-api/.venv/bin/python reports/2026_09_27_ds7_wave7/inputs/group06/controller.py --repo /home/mouse9911/gits/leo-tracker-reduxredux --plan /home/mouse9911/gits/leo-tracker-reduxredux/reports/2026_09_27_ds7_evaluation_setup/plans/budgets/plan.json --start-index /home/mouse9911/gits/leo-tracker-reduxredux/reports/2026_09_27_ds7_wave6/inputs/inputs-first32-group8-04-05-index.json --start-frozen /home/mouse9911/gits/leo-tracker-reduxredux/reports/2026_09_27_ds7_wave6/inputs/inputs-first32-group8-04-05-ready-v1.json --output /home/mouse9911/gits/leo-tracker-reduxredux/reports/2026_09_27_ds7_wave7/inputs/group06 --bank-root /home/mouse9911/gits/leo-tracker-reduxredux/.leo/ds7-wave7/group06 --python /opt/leo-tracker/current-api/.venv/bin/python --first-ordinal 41 --expected-start-ready 48
```

```bash
sudo -n prlimit --as=3221225472 -- timeout --signal=TERM --kill-after=10s 1200s nice -n 19 env OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 /opt/leo-tracker/current-api/.venv/bin/python reports/2026_09_27_ds7_wave7/inputs/group07/controller.py --repo /home/mouse9911/gits/leo-tracker-reduxredux --plan /home/mouse9911/gits/leo-tracker-reduxredux/reports/2026_09_27_ds7_evaluation_setup/plans/budgets/plan.json --start-index /home/mouse9911/gits/leo-tracker-reduxredux/reports/2026_09_27_ds7_wave6/inputs/inputs-first32-group8-04-05-index.json --start-frozen /home/mouse9911/gits/leo-tracker-reduxredux/reports/2026_09_27_ds7_wave6/inputs/inputs-first32-group8-04-05-ready-v1.json --output /home/mouse9911/gits/leo-tracker-reduxredux/reports/2026_09_27_ds7_wave7/inputs/group07 --bank-root /home/mouse9911/gits/leo-tracker-reduxredux/.leo/ds7-wave7/group07 --python /opt/leo-tracker/current-api/.venv/bin/python --first-ordinal 49 --expected-start-ready 48
```

## Downstream policy

Preparation does not authorize fitting or scoring. After root validates each published snapshot, a separately bounded scientific panel may use the Wave 4 validated batched arm with unchanged configuration, masks, starts, bounds, candidate policy, and optimizer. Every single runs once; a group runs only after all eight of its captures are ready. Preserve every failure and do not choose controls or members using geographic error.
