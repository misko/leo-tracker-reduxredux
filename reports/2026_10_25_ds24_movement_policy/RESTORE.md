# Restore and inspect the research artifacts

The report, tables, primary figures, protocols and audit receipts are ordinary
Git files. Large covariance arrays, full fit records and input-ownership tables
are preserved in the [research release](https://github.com/misko/leo-tracker-reduxredux/releases/tag/research-ds24-movement-policy-r01-20261025).
The [publication index](publication_index.json) lists every archive, download URL,
byte count, SHA-256 and member path. [ASSET_SHA256SUMS](ASSET_SHA256SUMS) provides
an ordinary checksum list.

There are **57 assets totaling 1,853,361,230 bytes**; the largest is 44,922,880
bytes. All 1,152 covariance vectors and full saved scientific results are
included. No raw IQ is included.

## Choose only the evidence you need

- `movement_DS24-XXXX_partNN.tar`: compressed NPZ vectors and all six completed
  fold-job records for that scan. Each tar contains whole files, so these are
  independent archives rather than byte fragments of a larger tar.
- `shared_scientific_metadata.tar.gz`: full movement input manifest, independent
  baseline native-ID/noise inventory, job claims/receipts/logs, per-case numerical
  audits and the preserved initial geographic-reporting artifacts.
- `recovery_DS24-XXXX_original.tar.gz`: original parent/target inventory, ordinary
  and rescued graph trials, original support failures and superseded DBG01 views.
- `recovery_DS24-XXXX_support_versions.tar.gz`: repaired support fits, raw-arm
  checkpoints, strict decisions and the no-refit active-incumbent correction.
- `actual_runtime_source_capsule.tar.gz`: the 358 external scientific Python
  source files actually imported or bound by the experiment. The broad recovery
  source hash inventory remains in its protocol; unused source bytes are omitted.

For example, download the 0095 movement files from the release using GitHub CLI:

```sh
gh release download research-ds24-movement-policy-r01-20261025 \
  --repo misko/leo-tracker-reduxredux \
  --pattern 'movement_DS24-0095_part*.tar' \
  --dir /path/to/downloaded-assets
```

Download all assets by omitting `--pattern`. Verify downloaded files against
`ASSET_SHA256SUMS` in the same download directory. Each selected asset has a
separate SHA-256 entry; unavailable unselected assets are not evidence failures.

## Restore archive members

Extract selected `.tar` or `.tar.gz` files into a fresh copy of this report
directory. Member paths are relative to that report root; for example, the
movement archives restore `movement/arrays/` and `movement/results/`. Extracting
all assets restores all archived report-relative scientific files.

The source capsule restores `source/repository/`, `source/previous_study/`,
`source/previous_witness/` and `source/feasible_deps/`. Its index maps these files
to the original paths and hashes. Three already-dirty imported repository files
are exact research snapshots; extraction does not replace production files.
Keep source restoration and any replay in an isolated checkout.

## Numerical inspection versus full scientific replay

The saved NPZ arrays contain raw held residuals, joint uncertainty factors,
native noise, IDs, family ownership, held design, prior/group information and
the training posterior factorization. The independent Gaussian SVD implementation
is in `audit/movement_audit.py`; its numerical helper can inspect these arrays
without RF collection or a new position fit.

Full input/causality/source audits deliberately verify the original absolute
bindings. Reproducing those checks requires the frozen local corpus, recorded
research environment and original dependency layout, or an explicitly reviewed
path remap. A Git checkout plus these result assets is not a standalone raw-radio
distribution. Existing result directories must never be refrozen or overwritten.

The final geographic evaluator is separate from inference. The original,
repair01 and eligibility02 recovery seals and the movement seal establish the
scientific decisions before geographic reporting. Technical failures, stricter
controls and superseded plot provenance remain available in the archives.
