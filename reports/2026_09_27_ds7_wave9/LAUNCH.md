# Wave 9 final chronological group 10

This launch is frozen against the merged Wave 8 predecessor:

- frozen input: `reports/2026_09_27_ds7_wave8/inputs/inputs-first64-group8-08-09-ready-v1.json`
- frozen SHA-256: `0e78b905accbdb83848aa1e844c5681e80d9bc4dfb4ac88850e4a27db6e5273e`
- unfrozen index: `reports/2026_09_27_ds7_wave8/inputs/inputs-first64-group8-08-09-index.json`
- index SHA-256: `07a933fa12c7ea91429ebc26a283070df77e8d56e69788c3d01221ba2ee70c62`
- predecessor state: 80 ready and 8 unavailable, with all 88 identities validated.

Select chronological `single-073` through `single-080`, exactly `group8-10`, before their predictions or scores. Captures 081--088 are already prepared and evaluated and are outside this launch. Group 10 owns only captures 073--080 under `inputs/group10/`, starts from the merged-80 index and frozen contract, and never modifies its predecessor.

## Preparation policy

This is the sole source-preparation worker for Wave 9. It:

- uses unchanged `tools/ds7_combined_export.py`, SHA-256 `6b56233bd944b2283146b56b632b3336fe9d6844fda25c54eff04eb48a9df729`, and the unchanged Wave 4-closed exporter policy;
- writes banks only below `.leo/ds7-wave9/group10/`;
- has a 1,200-second outer wall cap, 1,180-second internal deadline, and 240-second per-capture cap;
- inherits a 3 GiB address-space ceiling, one CPU/BLAS thread, and nice 19;
- uses cached public source and archive ports, with no raw IQ, RF collection, reference, pose interpretation, score access, or source/production mutation;
- stops on failure or lease exhaustion, retains partial outputs, and never overwrites an attempt;
- freezes progressive 88-row snapshots, preserving the prior 80 ready rows exactly and adding only its own validated captures.

Require at least 12 GiB `MemAvailable` immediately before dispatch. At most one DS7 fitter may overlap preparation. Do not start additional scientific experiments during this worker.

## Reviewed dispatch command

This command is prepared but must not be run until root explicitly dispatches Wave 9.

```bash
sudo -n prlimit --as=3221225472 -- timeout --signal=TERM --kill-after=10s 1200s nice -n 19 env OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 /opt/leo-tracker/current-api/.venv/bin/python reports/2026_09_27_ds7_wave9/inputs/group10/controller.py --repo /home/mouse9911/gits/leo-tracker-reduxredux --plan /home/mouse9911/gits/leo-tracker-reduxredux/reports/2026_09_27_ds7_evaluation_setup/plans/budgets/plan.json --start-index /home/mouse9911/gits/leo-tracker-reduxredux/reports/2026_09_27_ds7_wave8/inputs/inputs-first64-group8-08-09-index.json --start-frozen /home/mouse9911/gits/leo-tracker-reduxredux/reports/2026_09_27_ds7_wave8/inputs/inputs-first64-group8-08-09-ready-v1.json --output /home/mouse9911/gits/leo-tracker-reduxredux/reports/2026_09_27_ds7_wave9/inputs/group10 --bank-root /home/mouse9911/gits/leo-tracker-reduxredux/.leo/ds7-wave9/group10 --python /opt/leo-tracker/current-api/.venv/bin/python --first-ordinal 73 --expected-start-ready 80
```

## Downstream policy

Preparation does not authorize fitting or scoring. After root validates each published snapshot, a separately bounded scientific panel may use the Wave 4 validated batched arm with unchanged configuration, masks, starts, bounds, candidate policy, and optimizer. Every single runs once; the group runs only after all eight captures are ready. Preserve every failure and do not choose controls or members using geographic error.
