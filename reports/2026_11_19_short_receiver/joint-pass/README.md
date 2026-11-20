# Joint native carrier and frame-delay identity

The receiver returned two of six archive fixes in each calibration arm with the original 25 km tile. It withheld all three omitted-region offers in both arms. Original v5 returned all six with the matched tile. The closest two forced positions in the omitted arm were still 49.51 and 256.31 km from truth with fitted calibration. [Recording-level errors](position-errors.csv) · [Matched predictions](matched-tile.jsonl.gz) · [Omitted predictions](omitted-tile.jsonl.gz)

| Recording | Result in both matched arms | Forced or returned error (km), zero / fitted | Original v5 error (km), zero / fitted |
|---|---|---:|---:|
| DS26-0036 | Withheld | 13.305 / 11.631 | 1.278 / 1.208 |
| DS26-0122 | Returned | 3.883 / 3.887 | 0.751 / 0.747 |
| DS26-0237 | Withheld | 6.410 / 6.441 | 0.362 / 0.271 |
| DS29-0082 | Withheld | 9.485 / 5.991 | 0.567 / 0.517 |
| DS29-0174 | Withheld | 12.665 / 12.253 | 0.885 / 0.917 |
| DS29-0247 | Returned | 4.513 / 5.120 | 1.320 / 1.458 |

Across all six forced or returned matched estimates, fitted calibration changed position error by a paired median of −0.204 km. Error increased on both returned recordings. The fitted coefficient changed held-out conditional frequency RMS by a paired median of −4.17 Hz. DS26-0122 held at 180 Hz in each arm. DS29-0247 held at 415 and 406 Hz. On its omitted offer, DS29-0247 fit the prefix at 133 Hz with fitted calibration and rose to 685 Hz on held-out observations, above the 500 Hz return gate. [Prefix and holdout frequency rows](conditional-frequency.csv) · [Paired summary](summary.json)

The estimator keeps CFO and native modulo-frame epochs on anonymous triplet-walk fragments. It tests whether each training fragment's timing follows its integrated carrier rate before enabling a range-delay factor. Among the six matched recordings, 40 of 314 extracted fragments qualified. The chosen orbit labels used six of those timing-qualified fragments across three recordings. Neither returned archive fix used a timing factor. The field returns therefore give no direct measure of how much epochs improve position. [Selected orbit labels and train/holdout counts](matched-tile.jsonl.gz) · [Separate development oracle](../observability/README.md)

The model fits one fractional transmitter frequency offset and one orbit time correction per selected orbit across receiver and RF lanes. It profiles a separate constant and drift for frame timing on each qualified lane pass. No common frame epoch across RF carriers is assumed. Identity, candidate support, aliases and geographic fitting use the prefix, with two calibration fits on the same fixed observations and candidate identities. The final third of each retained fragment checks the frequency and frame predictions without another fit. The initial GLRT tracklet linkage uses the entire fragment. The selected labels on the archive recordings are anonymous estimates. [Protocol](PROTOCOL.md) · [Implementation](../../../tools/pipeline_eval/variants/joint_pass_id.py)

The nine isolated workers finished within their 90 s deadlines. Matched median worker wall time was 9.87 s, ranging from 5.85 to 14.15 s on the shared host. Omitted median worker time was 7.04 s. Each omitted run used the first offer in its frozen missing-region query, with the same native capture and TLE as its matched run. The sealed receipts record these digests, the supplied offers and separate forced and returned coordinates. [Source lock](source-lock.json)

Four planted tests check modulo-frame and shuffled timing, the chronological prefix boundary, cross-RF orbit identity, and the coupled carrier and frame fit. In the separate fresh four-site panel, both arms returned four of four supplied-region signal trials. Median error was 0.830 km at zero calibration and 0.316 km at fitted calibration. The zero-calibration arm withheld all four omitted trials. The fitted arm falsely returned one estimate 48.625 km from truth. The shuffled capture withheld in both arms. [Component tests](../../../tests/pipeline_eval/test_joint_pass_id.py) · [Prospective supplied and omitted sites](../fresh-scenes/README.md)

A post-seal identity audit matched each selected synthetic fragment's midpoint and RF channel to the planted transmission schedule. The receiver recovered 91 of 95 chosen lane identities and 46 of 48 planted emitters in supplied-region runs. All 95 chosen fragments used frame timing. The fitted false fix recovered 11 of 20 chosen lane identities, with six correct emitters. The remaining mixture passed with 447 Hz held-out carrier RMS, 71.9% carrier inliers within 450 Hz and 0.375 µs median held-out frame RMS. Its zero-calibration detection lay near the tile edge and had 69.4% carrier inliers, so it withheld. The source and prediction locks were checked before opening the emitter schedule. [Per-site identity audit](fresh-identity-audit.csv) · [Sealed synthetic scores](../fresh-scenes/scores.json)

```sh
nice -n 15 .venv/bin/python -m tools.pipeline_eval.qualification.joint_pass_trials replay \
  --scratch /tmp/leo-joint-pass --report /tmp/leo-joint-pass-report --cpus 2 3 4 5
.venv/bin/python -m tools.pipeline_eval.qualification.joint_pass_trials score \
  --report /tmp/leo-joint-pass-report
```

Use `audit-fresh-identity --fresh-panel` with the sealed working directory from the fresh-scene run to rebuild the identity audit.
