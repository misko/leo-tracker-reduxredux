# Dataset configuration index

For DS7 loading, model execution and scoring, see the [evaluation workflow](ds7-evaluation.md) and [parallel SOL-agent plan](ds7-parallel-plan.md). Model-arm configurations are in [`config/ds7/`](../../config/ds7/); they are separate from the frozen dataset membership below.

Dataset membership configurations live in dated **`reports/` directories**, rather than a central `configs/datasets/` folder. The authorities below are immutable snapshots; analyzer/method settings are separate. Historical links are pinned to repository commit `75b76f66974c78588c6599822e8007aaa767466b`, because some are newer than this working checkout. DS7 is newly minted locally.

| Dataset | Authoritative membership config | Scope |
|---|---|---|
| DS1 | [reports/2026_09_24_ds1/dataset.json](https://github.com/misko/leo-tracker-reduxredux/blob/75b76f66974c78588c6599822e8007aaa767466b/reports/2026_09_24_ds1/dataset.json) | 339 recordings; frozen protocol and splits in the same directory |
| DS2 original | [reports/2026_09_24_ds2_final_manifest/manifest.json](https://github.com/misko/leo-tracker-reduxredux/blob/75b76f66974c78588c6599822e8007aaa767466b/reports/2026_09_24_ds2_final_manifest/manifest.json) | Original 20-recording frozen corpus |
| DS2-22 successor | [reports/2026_09_24_ds2_sep24_rerun_22/manifest.json](https://github.com/misko/leo-tracker-reduxredux/blob/75b76f66974c78588c6599822e8007aaa767466b/reports/2026_09_24_ds2_sep24_rerun_22/manifest.json) | 22 recordings; preserves the original 20 and adds two compatible complete captures |
| DS3 | [reports/2026_09_24_ds3_all_captures/manifest.json](https://github.com/misko/leo-tracker-reduxredux/blob/75b76f66974c78588c6599822e8007aaa767466b/reports/2026_09_24_ds3_all_captures/manifest.json) | 56 captures; derived tracking authority is `inference-manifest.json` beside it |
| DS4 | [reports/2026_09_25_ds4_post_ds3_captures/manifest.json](https://github.com/misko/leo-tracker-reduxredux/blob/75b76f66974c78588c6599822e8007aaa767466b/reports/2026_09_25_ds4_post_ds3_captures/manifest.json) | 91 admitted captures; `evaluation-units.json` beside it |
| DS5 | [reports/2026_09_26_ds5_since_local_midnight/manifest.json](https://github.com/misko/leo-tracker-reduxredux/blob/75b76f66974c78588c6599822e8007aaa767466b/reports/2026_09_26_ds5_since_local_midnight/manifest.json) | 42 captures; `evaluation-units.json` beside it |
| DS6 | [reports/2026_09_27_ds6_roof/manifest.json](https://github.com/misko/leo-tracker-reduxredux/blob/75b76f66974c78588c6599822e8007aaa767466b/reports/2026_09_27_ds6_roof/manifest.json) | 43 roof captures; evaluation units, approved inventory and pose evidence beside it |
| DS7 | [reports/2026_09_27_ds7_post_ds6/manifest.json](../../reports/2026_09_27_ds7_post_ds6/manifest.json) | 88 complete post-DS6 recordings; evaluation units, approved proposal, mint verification and pose evidence beside it |
| DS8 | [reports/2026_09_28_ds8_post_ds7/manifest.json](../../reports/2026_09_28_ds8_post_ds7/manifest.json) | 65 complete post-DS7 recordings; sealed membership, 65 pose companions and offline verifier beside it; disjoint from DS7 |
| DS8 | [reports/2026_09_28_ds8_post_ds7/manifest.json](../../reports/2026_09_28_ds8_post_ds7/manifest.json) | 65 complete post-DS7 recordings, finalized by 2026-09-28 00:22:59 UTC; 143,988 visits; sealed membership and pose evidence; raw IQ referenced in place |

DS2 inventory and portable-evaluation directories contain related historical views, not replacements for the named frozen versions above. DS1–DS7 are not necessarily mutually disjoint datasets: in particular DS2 is represented within DS3. Do not concatenate the numbered datasets without deduplicating session IDs and source manifest digests.

For algorithm configuration, see [DS2 model-registry.json](https://github.com/misko/leo-tracker-reduxredux/blob/75b76f66974c78588c6599822e8007aaa767466b/reports/2026_09_24_ds2_model_registry/model-registry.json) and [DS5 method-registry.json](https://github.com/misko/leo-tracker-reduxredux/blob/75b76f66974c78588c6599822e8007aaa767466b/reports/2026_09_26_ds5_all_methods/method-registry.json). These configure particular evaluations, not the raw corpus. DS7 records per-capture acquisition settings and observed analysis configuration/digests in its manifest; it does not select a winning localization method or a new training split.
