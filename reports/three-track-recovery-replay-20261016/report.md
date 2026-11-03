# Replaying the three-trajectory recovery checkpoints

The `replay.py` command recomputes the published cold-checkpoint predictions and audits from the original recording export, the pinned TLE archive, the recorded analysis package, and the files in this directory. It does not load prior investigation files from `/tmp`, query PostgreSQL, acquire RF, run an optimizer, or change production.

It is checkpoint replay, not a claim that fresh discovery is solved. The original cold forward fold succeeds, while the reverse fold fails. Both outcomes must remain reproducible. Track membership was selected during the investigation and is explicitly recorded in the two derivations; it is not independently discovered by this replay.

## Inputs and runtime

- Recording export SHA256: `3a79382102760ac8e13f6d093e5b0be6bd168e68df4cb7f292cbf6fd87ebf612`.
- TLE snapshot SHA256: `c1341ed302fe6301e1dd4515e5bcee227d4c0c7aa975bdf572f8f3cbfd702072`.
- The manifest pins capsule files, analysis-package Python source, and NumPy/SciPy/SGP4 versions. A mismatch fails explicitly.
- The runtime must provide the original `leo` analysis package and scientific dependencies. The following command uses the installed package and interpreter used for the experiments; the repository's unrelated working changes are not runtime dependencies.

Run from any working directory, substituting the absolute capsule path if it has moved:

```bash
sudo -n env PYTHONDONTWRITEBYTECODE=1 \
  PYTHONPATH=/opt/leo-fast-auto/f141dbb30321bc8f9e8183576c511431ea60a6b3/worker/src \
  OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  /opt/leo-tracker/releases/47e2705e437722daa5e6d6bb1c252d54b7a21dbc/.venv/bin/python \
  /home/mouse9911/gits/leo-tracker-reduxredux/reports/three-track-recovery-replay-20261016/replay.py \
  --input /srv/bulk/leo/fast-scan-tracking-inputs/fast-9571943d3dccdf4f327e1346d1bf34b8.json \
  --tle-root /var/lib/leo/tle \
  --fold early_to_late --variant band_bias
```

Use `--variant cold` for either fold. Forward-only joint checkpoints are `band_bias` and `no_bias_from_band`; the latter records an additional training-only continuation initialized from the accepted band model, not a matched-budget comparison. Selecting an unavailable checkpoint fails rather than substituting a different model.

## What is recomputed

The command reconstructs the winning observation ordering, removes complete withheld probe groups, and verifies the exact derived-input hash. It verifies saved stage bytes against their original terminal receipts, rebuilds orbital banks from the pinned TLEs, and independently replays the selected training endpoint's feasibility, stationarity and objective. Calibration transport onto the original observation metadata must agree within one microhertz.

For joint checkpoints, it reconstructs the frozen frequency bases from the cold calibration, audits the training objective and the 0.001 stationarity threshold, and checks that adding 1,234,567 Hz to withheld measurements changes neither the training objective nor its gradients. It then recomputes withheld frequency RMS and intended assignment counts, requiring agreement with saved results within one microhertz. These tolerances check numerical reproduction, not physical measurement accuracy.

| Checkpoint | Early CH2 withheld RMS | CH4 withheld RMS | Late CH2 withheld RMS |
| --- | ---: | ---: | ---: |
| Cold forward | 130.93 Hz | 135.91 Hz | 172.53 Hz |
| Cold reverse, still failing | 1,474.83 Hz | 387.56 Hz | 2,146.59 Hz |
| Forward joint band model | 132.63 Hz | 143.64 Hz | 123.45 Hz |
| Forward simpler-model continuation | 131.51 Hz | 172.92 Hz | 115.52 Hz |

The forward joint band model retains all 63 withheld intended assignments. The simpler-model continuation retains 62/63. The reverse cold search selects different candidates and remains a failure. Frequency prediction and association evidence do not establish geographical accuracy or independently verified satellite identities.

## Validation

`validate_replay.py` runs all four checkpoint variants, checks rejection of a changed recording export and a changed checkpoint, and exercises fresh-rerun orchestration for both folds with an explicit stub instead of an optimizer. That orchestration test checks input hashes, the 480-second allowance, pinned TLE selection, rejection of a noncausal cutoff, and restoration of the original reader. Supply `--input` and `--tle-root` as above. The validator uses only newly created temporary test files; it does not depend on the old investigation namespace. `validation.json` records the executed validation result if present.

For the root-cause findings and negative discovery experiments, see [the cold-start report](../three-track-cold-start-20261016/report.md).

## Fresh discovery recipe

`rerun_cold.py` provides a separate fresh-discovery command. Use the same interpreter, package path, recording and TLE-root arguments as above, supply `--fold` and a new `--output` directory, and add `--run`. Without `--run`, it only reconstructs and hash-checks the training input and verifies the pinned archived TLE bytes. It refuses an existing attempt directory. The 480-second discovery limit is fixed, and terminal failure is retained rather than retried silently.

For an actual rerun, a process-local reader override selects the recorded causal snapshot by digest from the public archive-reader interface. No archive or installed package is modified, and no stored position, calibration, candidate identity or optimizer endpoint seeds discovery. Track rows are used only to remove the declared withheld probe groups. The checkpoint replay and fresh-discovery commands have different purposes: only checkpoint replay requires exact numerical agreement with stored results; a fresh optimizer run may return a different accepted or rejected endpoint.

Input preparation is validated for both folds. A new full discovery invocation is not claimed by the replay validation receipt; the earlier cold runs and their immutable terminal artifacts remain the executed full-pipeline evidence.

`--priority-view low` or `--priority-view high` changes which training view prioritizes adaptive spatial refinement. Every available channel remains in the later shared fit. This is an optimizer setting, not an adaptive RF recording. A bounded `low` reverse-fold run has now been executed and evaluated in the [grouped-track follow-up](../three-track-grouped-fit-20261016/report.md); it does not repair all three trajectories.

Research fit drivers can call `replay(args, return_context=True)` to receive the verified cold training input, original observations for evaluation, candidate bank, calibration seed, prior and immutable stage receipts. The capsule now includes all cold discovery-point receipts, so candidate retention can be reconstructed and checked without the original temporary attempt directories. This option returns before test scoring and does not refit a checkpoint.
