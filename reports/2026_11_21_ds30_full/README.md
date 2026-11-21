# Full DS30 validation of algo07v5 and compact v5 with two-scan cancellation

This evaluation assigns both pipelines to all 455 recordings in DS30 revision 1. It includes 411 complete acquisitions and the recorded portion of each of the 44 interrupted acquisitions. Eight sessions appeared in the earlier detector comparison. The other 447 are new to this comparison. [Full results](RESULTS.md) · [Cumulative position error](position-error.png) · [Paired runtime](runtime.png)

All 455 session identities are unique. The recorded clocks and capture-quality checks admit 2,581,792 of 2,878,757 visits, or 5,163,584 antenna opportunities. The 68 reconstructed inputs cover 24 complete and 44 interrupted captures. Reconstructing the inputs on the eight previously evaluated sessions reproduced every archived clock, quality exclusion and receiver header. [Input audit](input-audit.json) · [Frozen protocol](PROTOCOL.md) · [Recording roster](cohort.json) · [Earlier eight-session results](../2026_11_20_ds30_fast/README.md)

| Pipeline | Signal measurements | Position solver |
|---|---|---|
| Original GLRT + algo07v5 | Published original-GLRT measurements when the DS30 manifest binds them, otherwise fresh GLRT on the recorded samples | Original fast no-repair baseline with scientific archive validation |
| Two-scan cancellation + compact v5 | Fresh timing-first search on both antennas, subtraction of the first pilot, search of the residual, and final GLRT verification | Five-refresh secant solver with the two previously published orbit-support retries |

Both pipelines use the same search region and the same capture-era orbit files per recording. Each computes a fitted RF calibration and a fixed-zero calibration. For recordings without a published timing contract, the driver reconstructs both antenna headers, the clock anchor and capture-quality exclusions from signed indexes. Each fresh detector also verifies the individual I/Q windows. An interrupted capture can end with a signed zero-sample visit. The replay verifies the digest of the empty payload, counts the visit as excluded and passes the earlier usable samples to each receiver. Scoring joins the operator's Gauss roof reference after every prediction is locked.

## Reproduce on Gauss

Use the project environment with the research dependencies and native extensions installed. The input preparation needs read access to the recording archive, the historical orbit archive and the frozen DS29 and DS30 fixtures. It writes to the study's own snapshot. A recording can start as soon as its input binding is complete.

```sh
export PYTHONPATH=.:src
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
sudo -n -- env PYTHONPATH=.:src OPENBLAS_NUM_THREADS=1 .venv/bin/python -Bu -m tools.pipeline_eval.qualification.ds30_full_inputs
sudo -n -u "$(id -un)" -g leo -- env PYTHONPATH=.:src OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 nice -n 5 ionice -c2 -n5 .venv/bin/python -Bu -m tools.pipeline_eval.qualification.ds30_full --cpus 0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15
sudo -n -- env PYTHONPATH=.:src OPENBLAS_NUM_THREADS=1 .venv/bin/python -Bu -m tools.pipeline_eval.qualification.ds30_full_score score
```

The work directory on Gauss is `/srv/bulk/leo-dev/ds30-full-20261121`. The two pipelines run serially on the same assigned CPU for each recording. The order rotates through the seeded roster. The run command resumes completed outcomes and acquisition receipts. The scoring command verifies the roster, signed input bindings, predictions, scientific settings and successful original-v5 archives. It reports solver elapsed time for archived detections and measures end-to-end time where both raw detection and solving ran.

To verify the published tables from a checkout with the research dependencies, run `PYTHONPATH=.:src .venv/bin/python -m tools.pipeline_eval.qualification.ds30_full_verify`. This verifies each scored position using a second great-circle distance calculation, then checks the counts, error percentiles, timing medians and artifact hashes.
