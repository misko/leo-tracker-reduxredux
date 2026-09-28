# Wave 8 chronological groups 08 and 09

This launch is frozen against the merged Wave 7 predecessor:

- frozen input: `reports/2026_09_27_ds7_wave7/inputs/inputs-first48-group8-06-07-ready-v1.json`
- frozen SHA-256: `eef2e7f6760f63417b035ba3fabb43de88eae467242b1c5c45132cc755bd384c`
- unfrozen index: `reports/2026_09_27_ds7_wave7/inputs/inputs-first48-group8-06-07-index.json`
- index SHA-256: `c1df609ba5fc2e02d34b7d65a7b25384705fb6eb84cd1b882dc8a7655aea53b7`
- predecessor state: 64 ready and 24 unavailable, with all 88 identities validated.

Select chronological `single-057` through `single-072`, exactly `group8-08` and `group8-09`, before their predictions or scores. Group 08 owns captures 057--064 under `inputs/group08/`; group 09 owns captures 065--072 under `inputs/group09/`. Each starts independently from the same merged-64 index and frozen contract. Root combines their disjoint additions later; neither controller modifies the predecessor or the other group's artifacts.

## Preparation policy

At most these two source-preparation workers may run concurrently. Each worker:

- uses unchanged `tools/ds7_combined_export.py`, SHA-256 `6b56233bd944b2283146b56b632b3336fe9d6844fda25c54eff04eb48a9df729`, and the unchanged Wave 4-closed exporter policy;
- writes banks only below `.leo/ds7-wave8/group08/` or `.leo/ds7-wave8/group09/`;
- has a 1,200-second outer wall cap, 1,180-second internal deadline, and 240-second per-capture cap;
- inherits a 3 GiB address-space ceiling, one CPU/BLAS thread, and nice 19;
- uses cached public source and archive ports, with no raw IQ, RF collection, reference, pose interpretation, score access, or source/production mutation;
- stops on failure or lease exhaustion, retains partial outputs, and never overwrites an attempt;
- freezes progressive 88-row snapshots, preserving the prior 64 ready rows exactly and adding only its own validated captures.

Require at least 12 GiB `MemAvailable` immediately before dispatch. At most one DS7 fitter may overlap the two preparation workers. Do not start additional scientific experiments during the pair.

## Reviewed dispatch commands

These commands are prepared but must not be run until root explicitly dispatches Wave 8.

```bash
sudo -n prlimit --as=3221225472 -- timeout --signal=TERM --kill-after=10s 1200s nice -n 19 env OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 /opt/leo-tracker/current-api/.venv/bin/python reports/2026_09_27_ds7_wave8/inputs/group08/controller.py --repo /home/mouse9911/gits/leo-tracker-reduxredux --plan /home/mouse9911/gits/leo-tracker-reduxredux/reports/2026_09_27_ds7_evaluation_setup/plans/budgets/plan.json --start-index /home/mouse9911/gits/leo-tracker-reduxredux/reports/2026_09_27_ds7_wave7/inputs/inputs-first48-group8-06-07-index.json --start-frozen /home/mouse9911/gits/leo-tracker-reduxredux/reports/2026_09_27_ds7_wave7/inputs/inputs-first48-group8-06-07-ready-v1.json --output /home/mouse9911/gits/leo-tracker-reduxredux/reports/2026_09_27_ds7_wave8/inputs/group08 --bank-root /home/mouse9911/gits/leo-tracker-reduxredux/.leo/ds7-wave8/group08 --python /opt/leo-tracker/current-api/.venv/bin/python --first-ordinal 57 --expected-start-ready 64
```

```bash
sudo -n prlimit --as=3221225472 -- timeout --signal=TERM --kill-after=10s 1200s nice -n 19 env OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 /opt/leo-tracker/current-api/.venv/bin/python reports/2026_09_27_ds7_wave8/inputs/group09/controller.py --repo /home/mouse9911/gits/leo-tracker-reduxredux --plan /home/mouse9911/gits/leo-tracker-reduxredux/reports/2026_09_27_ds7_evaluation_setup/plans/budgets/plan.json --start-index /home/mouse9911/gits/leo-tracker-reduxredux/reports/2026_09_27_ds7_wave7/inputs/inputs-first48-group8-06-07-index.json --start-frozen /home/mouse9911/gits/leo-tracker-reduxredux/reports/2026_09_27_ds7_wave7/inputs/inputs-first48-group8-06-07-ready-v1.json --output /home/mouse9911/gits/leo-tracker-reduxredux/reports/2026_09_27_ds7_wave8/inputs/group09 --bank-root /home/mouse9911/gits/leo-tracker-reduxredux/.leo/ds7-wave8/group09 --python /opt/leo-tracker/current-api/.venv/bin/python --first-ordinal 65 --expected-start-ready 64
```

## Downstream policy

Preparation does not authorize fitting or scoring. After root validates each published snapshot, a separately bounded scientific panel may use the Wave 4 validated batched arm with unchanged configuration, masks, starts, bounds, candidate policy, and optimizer. Every single runs once; a group runs only after all eight of its captures are ready. Preserve every failure and do not choose controls or members using geographic error.
