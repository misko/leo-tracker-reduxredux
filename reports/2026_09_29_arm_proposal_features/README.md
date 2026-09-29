# Four-feature proposal ablation

`proposal_feature_ablation` accepts the native proposal invocation:

```sh
proposal_feature_ablation RATE template.c128 IQ.ci16 --combined-only
```

It emits the existing `receiver_id`, `probe_index`, and `top4.combined` fields,
plus `feature_mask` on every JSONL row.  One bounded ablation is selected with
one of `--omit=lag1`, `--omit=lag3`, `--omit=lag5`, or `--omit=power`; the
omitted feature is not reference-transformed, folded, correlated, or ranked.
The all-four-feature control has no omission.  Peak separation remains five
samples and combined-only selection remains the original linear top-four path.

Run `python3 build.py` to cross-build the ARM receipt and build/test the host
control and ablation binaries.  It does not execute ARM or collect RF data.
