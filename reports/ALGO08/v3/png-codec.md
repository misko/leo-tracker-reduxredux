# Lossless encoding settings on the saved weak fix

Keep the installed libdeflate level 3. Zlib run-length coding saved **47.5 ms of encoding CPU** on the eight DS30-0016 figures but increased payload by **46.6%**. The complete render, official commit and decoded readback took **1.430 s CPU** at level 3 and **1.458 s CPU** with run-length coding. The larger PNGs also took longer to publish in both local-ext4 orders. Each encoder preserved all eight images pixel for pixel. [Frozen protocol](png-codec-protocol.md) · [Receipt](measurements/png-codec-DS30-0016.json.gz)

| Encoding | PNG bytes | Encode CPU, ms | Render, commit and verify CPU, s | Two complete elapsed observations, s |
|---|---:|---:|---:|---|
| Installed libdeflate level 3 | 2,593,567 | 168.0 | 1.430 | 1.492 / 1.369 |
| Libdeflate level 2 | 2,581,173 | 165.2 | 1.591 | 1.608 / 1.574 |
| Libdeflate level 6 | 2,522,979 | 177.0 | 1.432 | 1.482 / 1.383 |
| Zlib level 1, run-length strategy | 3,803,198 | 120.5 | 1.458 | 1.519 / 1.396 |

CPU values are medians of the two reversed passes from one reconstructed saved packet. The timed scope starts with the six Agg draws and includes eight encodes, the normal durable writer on tmpfs, verified readback, full RGBA digests and the extra research CRC checks. Render and decode variation exceeds the encoding differences between libdeflate levels. Level 2 saved only 2.8 ms and 12.4 kB. Level 6 added 8.9 ms and saved 70.6 kB. The installed Sub/Up row filter used 27.3 ms at level 3. The previous North encoder trial compared levels 1, 3 and 6. This study adds level 2 and run-length coding to the active weak one-pass publication. [Prior encoder trial](../single-core-2x/lossless-png.md) · [Prior weak renderer census](calibration-png-layers.md)

| Local NVMe ext4 write order | Encoder | Official commit, ms | Eight PNG fsync calls, ms |
|---|---|---:|---:|
| Level 3 first | Level 3 | 15.48 | 8.87 |
| Level 3 first | Run-length | 19.34 | 10.56 |
| Run-length first | Run-length | 18.13 | 10.55 |
| Run-length first | Level 3 | 17.16 | 9.94 |

Each temporary ext4 publication retained all fourteen original sync calls. The disk-only check excludes rendering and verification and is specific to this drive and load. Host-wide full I/O pressure averaged 50.93% over the previous ten seconds at the end of the probe. The extra 1.210 MB would consume the isolated 47.5 ms CPU savings at around 25.5 MB/s if transferred serially as part of publication or delivery. The transfer calculation assumes no overlap and is separate from the measured filesystem times. Even the isolated encoding gain is only 0.55% of the earlier 8.630 CPU-second raw-to-website run. [Weak raw result](unified-short-layout.md)

## Publication verification

Each mode used the same frozen DS30-0016 packet, causal archive, offered region, numerical result, Agg layout and native Sub/Up filter. The official media store emitted eight verified lossless PNGs from six draws. The incumbent reproduced every encoded hash from the original explicit-layout publication. Every alternate preserved decoded RGBA, original dimensions, mode, ordered non-IDAT chunks, DPI and text. The ordinary writer published its own content addresses. Both calibration arms, owners, grid and optimizer path matched the frozen output, and the two position sidecars rebound to the actually stored map. The ext4 check used that same writer. No waveform data was read.

The receiver, numerical solver, renderer and store were unmodified. The experiment patched only the existing encoder instance for the duration of each scoped render. The receipt and source lock expand to SHA-256 `07a69a7c2c213055e08b78c7671be501a5f094458a90396ced1c09d48d4511bd` and `7eb6b32212dfac46d8c8a92411acda29067cc8c14ece99d09f0f37d308b5c3f4`. [Driver](png_codec_trial.py) · [Source lock](measurements/png-codec-DS30-0016-source-lock.json.gz) · [Component tests](../../../tests/pipeline_eval/test_png_codec_trial.py)
