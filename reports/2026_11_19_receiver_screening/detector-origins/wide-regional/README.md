# Wide regional prepared-fractional wave8

The 10 MS/s short-window release now searches **21 physical coarse CFO centers from −800 to +800 kHz**. The prepared narrow control reproduces the frozen release byte for byte. All six nonzero high-CFO canaries matched on both receivers in the wide build, and none matched in the narrow build. The admitted real panel widened 39 positive records to 41 at a 7.12% host CPU cost. [Qualification](qualification.json) · [Protocol](PROTOCOL.md)

## Build handoff

| Build | Purpose | x86 SHA-256 |
| --- | --- | --- |
| `/srv/bulk/leo-dev/20261119-wide-regional/control/libleo-adaptive-detector.so` | Original prepared fractional, exact frozen control | `e545c28554c9db50fe5aece28e7c8ce6ab2b2504db13ab946fbff0f0a190fe0d` |
| `/srv/bulk/leo-dev/20261119-wide-regional/wide/libleo-adaptive-detector.so` | Wide at 10 MS/s through the short-window entrypoints | `db80b772cf9f52941cc0073067816e571308cb43c3096516b77f73ed54986c66` |

Both builds are ABI version 1 with identical exported symbol names per architecture. Disk receipts identify the library and CLI bytes for both x86 and Cortex-A9. Native consumers receive the same result geometry and carry the library digest as provenance. The raw-stage trial for complete recordings is separate. [Build digests and receipts](build-digests.json)

## Search geometry and guards

The width follows the 800 kHz ceiling in the capture-era producer. The native release applies it to detector-input baseband without a CI16 transformation and keeps the original four differential proposals and their adjacent epochs, 80 kHz coarse step, local ±80 kHz fine search, eight retained candidates, and all scoring and gating calculations. The capture-era producer also computes a per-target sampled passband and uses a different epoch grid and retry schedule. This implementation targets width alone.

The wide coarse table uses a 24-lane stride for 21 valid CFO cells. The three padded cells stay outside peak collection and peak capacity. The preserved narrow path starts five columns into that table and exposes the original 0–10 bin indices. It remains active for other sample rates and longer dwells. Both fine and conditioned bounds use the active width. The unchanged 500 Hz fine FFT uses at most 321 cells per local search; the existing conditioned path uses at most 42 cells, including a clipped off-grid endpoint, in 64-cell arrays. The integer and fractional GLRT confirm within the same acquired-CFO bound. Final tracked CFO can exceed it because the original residual estimator adds to acquired CFO afterward. The ±810 kHz plants illustrate this behavior consistently on both targets.

The x86 library stayed at 2,509,080 bytes. The extra configured coarse-grid, accumulation and template arrays reserve approximately 3.1 MiB per 10 MS/s search workspace, including an existing double accumulation array that the FP32 path does not touch. Template and normalization arithmetic remains in native precision, with bounded four-lane ARM accumulator groups and matching tap order. The independent ASan/UBSan build from the actual widened source passed 24 short-window cases across both edges and all four supported rates, covering signed boundary plants, randomized CI16 rails and empty input. The compiled component test checks all 21 coarse CFO lanes and 1–45 taps against separately accumulated scalar scores. Ordinary-width short calls at 2.5, 5 and 7.5 MS/s match all non-timing fields for one and two receivers. At 10 MS/s, same-context long calls matched between builds after wide calls, and the next short call restored the same wide payload. [Canaries](canary-host.json) · [Cortex-A9 canaries](canary-arm.json) · [Sanitizers](sanitizers.json)

## Held saved-IQ panel

There were 15 admitted dual-RX, 1,600,000-byte visits out of 16 scheduled. DS29 had one unchanged capture-policy exclusion. The wider search retained candidates in the outer coarse band 89 times. Of 236 original and 240 wide candidate records, 151 shared coarse epoch/frequency identity and 70 also shared rank. Maximum one-to-one matching within two samples and 1 kHz matched 38 of 39 original positive records to 38 of 41 wide positives. The absolute tracked-CFO count above 400 kHz increased from three to six. These are detector diagnostics with no truth-based ranking or geographic fit in this panel.

| Target and scope | Regional coarse CPU sum | Detector CPU sum | Median detector CPU | ≤20 ms CPU / wall |
| --- | ---: | ---: | ---: | ---: |
| x86, 73 reused-context pairs | 97.11 → 141.58 ms | 1,025.03 → 1,098.00 ms | 13.84 → 14.81 ms | 73/73 → 73/73 / 72/73 → 73/73 |
| Cortex-A9 QEMU, 15 one-shot pairs | 589.73 → 1,118.78 ms | 5,601.24 → 6,273.95 ms | 364.16 → 419.21 ms | 0/15 → 0/15 / 0/15 → 0/15 |

Native host CPU median consumed 69% → 74% of the 20 ms visit interval. The timing scope is a hot detector context with an in-memory CI16 visit. It excludes capture, extraction, storage I/O and downstream fit. Emulated total CPU rose 12.01%, and process peak RSS including QEMU rose from 48,428 to 50,132 KiB. Physical embedded cost remains unmeasured. [Complete payload and timing receipts](prediction-lock.json)
