# Coax repair verification, 2026-09-27

Both receiver paths now have substantial input, and both have strong known-pilot
evidence. This resolves the observed RX0 near-floor symptom after the operator's
coax repair. It does not independently identify the particular faulty connector
or establish a satellite identity, QAM decode, or calibrated RF power.

Two five-minute recordings completed at 2.5 MS/s, dual RX, 40 dB manual gain:

| Recording | Capture window, approximately UTC | Complete visits |
|---|---|---:|
| `scan-fw-60d9d1e77c14da0a` | 00:00–00:05 | 2,218 |
| `scan-fw-cd6a029d633dcc0e` | 00:05:05–00:10:08 | 2,214 |

Both completed without reported capture errors. Every hundredth raw visit was
sampled (23 per recording), verifying compressed and uncompressed chunk hashes.
The median per-component RMS counts were RX0/RX1 **137.6/120.3** for the first
recording and **136.2/116.2** for the second. The old scan's RX0 median was
approximately 0.95 counts. This is a sustained recovery across the sampled
visits, not merely one bright sample.

All 2,218 first-recording visit-analysis files were read. RX0 had **1,823** probes
passing the 0.025 fractional-margin gate; RX1 had **1,301**. With a conservative
0.10 margin threshold, counts were **1,820 RX0** and **1,286 RX1**. These are
probe counts, not independent satellites or a measured false-alarm probability.
The first recording's complete metrics manifest was published by the final
00:13:09 UTC snapshot. The second recording was also published, and its pilot
analysis was submitted to the normal queue. Raw input
recovery was checked in both recordings; the quoted pilot counts belong only
to the first.

The operator authorized back-to-back captures until both receivers showed
signal. A temporary controller was bounded to 30 minutes including the initial
capture, with a maximum of five additional five-minute captures. Unique salted
session IDs and separate summary directories preserved recordings within the
same ten-minute slot without falsifying capture timestamps. The repeated run
used the installed capture implementation and its normal ownership lock.
A no-RF dry run verified unchanged rate, receiver mask, duration, and slot
configuration; the strong-probe counting test passed.

Once the first partial pilot results clearly supported both receivers, further
repeats were held while the confirmation capture finished. The controller
stopped successfully at 00:10:21 UTC; no third diagnostic scan was launched.
The normal acquisition timer was restored automatically and resumed its normal
schedule. The confirmation recording was submitted to the normal spool
publisher, with the ordinary analysis queue timer active.

Evidence: [raw/capture snapshot](repair_verification.json),
[complete visit-analysis snapshot](repair_pilot_results.json).
These are additive investigation files; no pre-repair capture or production
analysis artifact was edited.
