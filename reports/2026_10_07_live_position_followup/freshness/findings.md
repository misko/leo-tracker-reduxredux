# TLE freshness restoration

At 2026-10-07 00:58:56 UTC the existing enabled timer was started. Its persistent catch-up ran the existing collector once, completing successfully in 4.893 seconds with no collection errors. Both providers published immutable snapshots. The timer was active/waiting afterward, with the next hourly trigger scheduled for 01:01:24 UTC at observation time.

Verification used the supported `TleArchiveReader` to list and digest-verify the latest snapshot for each provider. Actual TLE line-1 epochs were parsed with the standard two-digit year rollover rule. Ages below are relative to observation time; they describe each entire provider catalogue, not just visible or assigned satellites.

| Provider | Collection age before / after | Median element age before / after | After min / max element age | Elements over 24 h after |
| --- | --- | --- | --- | --- |
| Space-Track | 52.93 h / 8.88 s | 62.82 h / 14.55 h | 1.24 h / 102.83 h | 1,239 / 11,139 |
| Hugging Face | 56.93 h / 6.64 s | 79.68 h / 24.20 h | 16.32 h / 379.16 h | 5,505 / 10,670 |

Fresh collection therefore materially improves typical element age, but some returned elements remain old. The new Space-Track digest is `sha256:880b67c160888672ff09cf669b6ef5e6b8130f120b88b9c57fa44f397548cee8`; its collection time is 00:58:58.384013 UTC. Complete before/after provenance is in `findings.json`.

The journal records the timer being cleanly stopped on October 4 at 21:16:08 UTC after its last trigger at 21:02:27. Available unit logs do not identify who stopped it or why. Existing service logs also include a nonfatal Matplotlib cache-directory warning.

The prior live-position review pinned historical snapshot digests and verified them through the archive reader (`cases.py`). Its 46.60–50.82 h collection ages and 62.10 h median of per-scan median element ages apply to that earlier scan sample; they are not the full-catalogue before measurements here. Existing historical receipts remain pinned. This operation establishes collection freshness, not better localization accuracy.

Operational scope: only the existing timer was started and its collector wrote its normal local TLE archive. No RF collection, recorder restart, QNAP modification, configuration deployment, component change, commit, or push was performed.

## Caught source-selection issue

A fresh download is not necessarily the best ephemeris. The deployed regional CLI calls `select_latest_before(capture_start - 505 s)` without a provider. The reader chooses the largest strictly preceding collection timestamp. Hugging Face was collected 2.23 seconds after Space-Track, so the current policy selects Hugging Face for captures starting after 01:07:25.615516217 UTC, until a newer causally eligible snapshot appears. This was verified by calling the deployed selector at cutoff `1791334740615516218` ns (one nanosecond after the Hugging Face collection).

Digest-verified NORAD overlap confirms that this is a material source-quality issue: of 10,665 shared objects, Space-Track has newer actual element epochs for 9,174, identical epochs for 1,491, and older epochs for none. Its median epoch advantage is 9.40 hours, maximum 72.19 hours. The complete inventories differ: Space-Track has 474 exclusive IDs and Hugging Face has 5. Epoch recency is evidence about input freshness, not a localization-accuracy guarantee.

The lean proposed follow-up is a pure research policy with explicit preferred-provider causal selection (Space-Track), documented collection-age and element-age bounds, and whole-snapshot fallback to Hugging Face. Record provider, digest and actual epoch quality. Test strict causality, provider preference despite later fallback download, bounded fallback, deterministic ties, explicit unavailability, and preservation of the entire selected inventory. Avoid per-ID element cherry-picking. Matched numerical comparisons must use the same full chosen candidate bank across their compared arms. No production policy or persisted contract was changed here.

The scheduled 01:01:24 UTC collector subsequently fired and succeeded with no errors; both providers were intentionally rate-limited by persistent attempt/success gates following the catch-up refresh. The timer remains active/waiting, next trigger 02:01:28 UTC at verification time.
