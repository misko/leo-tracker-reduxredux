# ALGO08v3 and the charted single-core candidate on all DS30 recordings

The primary population is all 455 recordings in the original DS30 manifest, SHA-256 `a4ce879975be0593f1adeb7c106f31660c6c423f17e2c7858985244530dc0eb8`. This includes all 44 interrupted captures. The earlier 100-recording ALGO08v3 release panel is a predefined subset. Previously measured times on either subset remain historical controls. Every new timed comparison requires both algorithms to process the same original recording through their normal signed terminal outcome. [DS30 enrollment](../../2026_11_20_ds30_fast/dataset/evaluation-units.json) · [Original release cohort](ds30-100/recordings.csv)

Compare installed ALGO08v3 `6cdbac1e8496bfeaf8f3eefb90c936c65829629cc42d04b4a9bab7c6e97cf50f` with the charted integrated original-file candidate at `b54ea2104`. The candidate uses the sparse 8 ms two-scan receiver with 20 ms anchors, single ranking on refusal, the six-sheet Cairo option and independent PNG verification. Its general original-file adapter was calibrated against the existing complete DS30-0016 result. The supplied region, causal data, source identity and image requirements are matched per recording. The candidate uses the original cold catalogue path where the portable index does not precede the recording. Saved-detector experiments, packed-input clocks, alternate-member thinning and selective recheck experiments are separate studies. [Charted original-file recipe](integrated-original-protocol.md)

Run serially with the Gauss benchmark lease, a single numerical thread on one CPU, low process and I/O priority, and storage-pressure admission. Retain the assigned launch order and all failed attempts. Choose the initial triage by original-input availability and size before checking candidate results. Use direct authenticated original inputs and the signed historical causal snapshot; charge waveform processing to each measured worker. Report pre-launch staging or admission separately. Keep site references outside both workers and join after the prediction receipts are sealed. The original reference audit uses operator site authority bound to each recording's time and hardware identity. [Reference audit](../../2026_11_21_ds30_full/reference-audit.json)

Report paired elapsed and CPU distributions, fix, withholding and failure counts, both geographic calibration arms, and RF RMS separately. Each accuracy curve divides by all assigned recordings, including failures and withheld positions. Report fix-only error percentiles, paired error changes on shared fixes, gained and lost fixes, and the original 100-recording subset. Summed speedup is the ratio of total installed time to total candidate time. Paired median speedup is the reciprocal of the median candidate-to-installed time ratio. Show both launch-order strata. Keep the observing site and the full timing boundary visible in the result. Publish the final report when all 455 comparisons and their source identities are accounted for, regardless of the measured speedup. [Full-report scorer](full_successor_score.py)

For a read-only progress check, run the following command on a matching combined export and seal. It scores each completed stage and its newly added recordings. It also reports the number of remaining pairs that must finish within half the baseline time to meet the full median target. A positive `observed_candidate_wall_minus_half_baseline_s` is the saving below half-time that the remaining pairs must collectively contribute to reach the summed target. The result includes the export digest for reproducibility. The command reads only the ledger and original enrollment metadata.

```sh
python -m reports.ALGO08.v3.ds30_stage_progress "$campaign_root/rows-with-relocations.jsonl"
```

Run the scorer from the research checkout with the final driver export. It checks the assigned population, original input identity, one frozen build per role, terminal outcomes, both calibration arms and process clocks before writing the report.

Gauss retains the paired ledger at `/srv/postgres-nvme/leo-ds30-evaluation-20261124`. The immutable plan SHA-256 is `9deecea6ce5237d01d277370f57b2666f3b84ab96bba72fe0b668c7701d0fc99`. It assigns ALGO08v3 first on 228 recordings and the successor first on 227. The campaign unit is `leo-ds30-paired-evaluation-20261124.service`. The result export includes failures, the actual launch order, child and independent verification clocks, and the digest of each selected attempt. [Driver and restart instructions](ds30-paired-evaluation.md) · [Frozen candidate, checked inputs and restore procedure](integrated-original-batch.md)

For reproduction, use the final combined export, which includes the authenticated original-file pairs for the nine recordings that moved after accession. The published `summary.json` identifies its exact bytes in `attempt_export_sha256`. The command below runs from the research checkout, with `$published_report` pointing to the downloaded report directory and `$campaign_root` pointing to the Gauss ledger. It uses the sealed predictions and performs zero waveform reads. The five figures include wall-time and position-error distributions, their histograms, and the joint speed/error comparison for each recording. [Original-file relocation and combined export](ds30-original-relocation.md)

```sh
expected=$(python -c 'import json,sys; print(json.load(open(sys.argv[1]))["attempt_export_sha256"])' "$published_report/summary.json")
revision=$(python -c 'import json,sys; print(json.load(open(sys.argv[1]))["report_renderer_revision"])' "$published_report/summary.json")
test "$(git rev-parse HEAD)" = "$revision" || exit 1
python -m reports.ALGO08.v3.full_successor_score \
  "$campaign_root/rows-with-relocations.jsonl" "$report_dir" --expected-sha256 "$expected" \
  --renderer-revision "$revision" --offered-region "$campaign_root/offer.json"
```
