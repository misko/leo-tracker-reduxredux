# Upper-edge transfer lead: concentrated support

The exploratory eight-group upper-edge lead is largely driven by a small group
and one recording session. This weakens an interpretation as a broadly recurring
header field, without erasing the original controlled result.

## Frozen-model attribution

Reuse the discovery memberships from `frame-transfer.json`; do not select a new
partition or refit a hierarchy. Reconstruct the same frozen centroids and require
exact agreement with the saved group-wise held recall. Verify raw artifact hashes.

For each observation, compute the exact expected match probability under uniform
prediction shuffling within its session/channel/rate/receiver stratum. Subtract
that expectation from its observed match indicator and weight by
`1 / (8 × discovery group size)`. Summing these terms gives the excess in macro
recall, without Monte Carlo error in the baseline.

Held balanced accuracy is 19.223%; the exact conditional baseline is 15.510%;
the excess is **3.712 percentage points**. The earlier sampled baseline was
15.4%, consistent with Monte Carlo variation. Neither is the naive 12.5%
eight-class baseline.

![Contribution by discovery group](local/transfer-attribution.png)

| Group | Entries | Contribution, percentage points |
|---|---:|---:|
| 0 | 322 | +0.026 |
| 1 | 34 | +0.643 |
| 2 | 30 | +0.104 |
| 3 | 8 | 0 |
| 4 | 17 | 0 |
| 5 | 14 | +0.595 |
| 6 | 9 | 0 |
| 7 | 4 | +2.344 |

Group 7 supplies **63.1% of the excess**. It has one correct held prediction
out of four, versus conditional expected recall of 6.25%. Its members are:

| Observation | Rate | RX / channel | Pilot coherence | Conditional candidate |
|---|---:|---|---:|---|
| DS10-F121-T0037 | 5 MS/s | 1 / 2 | 0.5120 | None |
| DS10-F160-T0030 | 5 MS/s | 1 / 2 | 0.5054 | 59464 |
| DS7-F038-T0037 | 5 MS/s | 0 / 3 | 0.5088 | None |
| DS9-F001-T0010 | 7.5 MS/s | 0 / 3 | 0.5171 | None |

All four have coherence close to the >0.5 qualification threshold. This is a
quality concern, not proof that the observations are noise. Only one has a
conditional satellite annotation, so this group cannot demonstrate repeated
identity. Two have no accepted known-tail state; the others have states 7 and 3.
That does not establish T-code independence of the early symbols.

## Session sensitivity

The largest session contribution is 2.363 percentage points, from
`scan-fw-9ff05ce7587e39c7` (six entries). Omitting that session while holding
centroids and group labels fixed reduces the macro excess to **1.349 points**.
Omission recomputes class weights; it is not a retrained or independent model.
Across all 149 session omissions, excess ranges from 1.349 to 4.540 points;
no class disappears, so no omission required abstention.

This is post-selection sensitivity analysis, not a new p-value or a rejection
of the original family-controlled test. It shows why the lead should not be
described as strong or distributed evidence of a firmware field. The appropriate
next discriminator is whether the small group's repeatability survives a recovery-
quality or common-phase check, not assigning its cluster number to a prefix enum.

## Reproduction

`transfer_attribution.py` verifies source hashes, freezes the previous partition,
and saves every observation's contribution, group metadata and session omission
result. Its focused test checks conditional expectations and abstention when a
class disappears. It and Ruff pass. No source data or prior result was modified.

```sh
OPENBLAS_NUM_THREADS=1 uv run --no-project --with numpy --with scipy --with matplotlib python reports/2026_09_29_firmware_cluster_reaudit/transfer_attribution.py
uv run --no-project --with numpy --with scipy --with pytest pytest -q reports/2026_09_29_firmware_cluster_reaudit/test_transfer_attribution.py
```
