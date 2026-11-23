# Fixed publication work on the weak physical fit

On the genuine saved DS30-0016 short packet, fresh imports outside the solve and renderer took **0.927 CPU s** and the eight independently decoded image checks took **0.312 CPU s**. Reusing the original verified PNG reads removed eight repeat read-and-hash calls covering **2,593,567 bytes**. The repeated calls took only **4.15 ms CPU** in the control, excluding the separately counted JSON parsing. The instrumented worker clock was **5.084 → 5.088 s elapsed**. This pair shows exact evidence reuse and no demonstrated end-to-end gain. [Frozen protocol](saved-overhead-protocol.md) · [Paired receipt](measurements/saved-overhead-DS30-0016.json.gz)

## Original raw boundary

The prior matched raw candidate took 8.638 s through exit. Authenticated acquisition took 3.392 s, the solve 2.617 s, and rendering 1.132 s. The difference is **1.498 s elapsed and 1.494 CPU s**. The raw scan report was written at 8.147 s, leaving 0.492 s through exit. These are the original charged timestamps, with no waveform replay. The fresh saved control had 1.592 s elapsed outside solve and rendering. Its independent PNG checks price part of the raw publication tail, and the two scopes omit different acquisition setup. [Authoritative cumulative raw pair](unified-short-layout.md)

## Exclusive saved clocks

Values are CPU unless marked elapsed. Nested operations count once. Imports inside solving or rendering stay inside those stages. PNG decoding includes the independent RGBA digest. The residual includes interpreter and launcher work before the instrumented entry, the receipt and diagnostic output, and process exit. Timer and wrapper work is included in the pair and partly remains unclassified.

| Stage | Original | Verified read reuse |
| --- | ---: | ---: |
| Solve | 2.627 s | 2.602 s |
| Render and encode | 1.151 s | 1.167 s |
| Fresh imports outside solve and render | 926.7 ms | 945.0 ms |
| Eight independent PNG decode and RGBA checks | 311.7 ms | 314.1 ms |
| Checked source and asset loading | 1.39 ms | 1.29 ms |
| Saved packet load, two inventory checks and signed validation | 2.02 ms | 2.06 ms |
| Graph eligibility proof | 6.48 ms | 6.53 ms |
| In-process handoff | 0.004 ms | 0.004 ms |
| JSON encoding and decoding | 18.80 ms | 18.44 ms |
| Persistence, fsync, sealed detector read, manifest and sidecars | 4.63 ms | 4.43 ms |
| Official PNG read and SHA verification | 2.69 ms | 4.07 ms |
| Research PNG reread and SHA verification | 4.15 ms | 0 |
| Remaining research evidence assembly | 0.35 ms | 0.12 ms |
| Remaining inside the instrumented worker | 22.11 ms | 22.55 ms |
| Outside the instrumented worker | 287.17 ms | 217.21 ms |
| External CPU through exit | 5.366 s | 5.304 s |
| External elapsed through exit | 5.371 s | 5.306 s |

The original and reuse processes were launched in that order, with 3,104 and zero dependency input blocks respectively. The 65 ms external wall difference comes with a 70 ms shift in the elapsed time outside the instrumented worker. The worker itself took 8 ms more CPU with reuse. The observed duplicate read and hash is the defensible ceiling for that operation. All serialization and JSON decoding together cost less than 19 ms in the saved control. The trial did not remove any scientific work or verification.

## Matching publication evidence

The optional `--reuse-verified-png-reads` mode uses the bytes returned by the first official `artifact` call after digest verification. It immediately decodes them and retains only the size and digest evidence for the fresh root, run, figure and SHA. The existing verifier still matches the terminal, committed manifest and sidecars, and any missing figure key uses normal readback. The observed run reused all eight exact keys with zero fallbacks. Both processes performed the original 22 fsync calls. [Opt-in adapter](verified_png_reads.py) · [Cumulative entry](unified_short_bootstrap.py)

The published detector documents match the original sealed digest. Both arms reproduced all 116 owner and role rows per calibration, the fixed-zero and fitted endpoints, RF RMS, terminal, scientific grid and path, and all eight encoded PNGs and decoded RGBA arrays. The grid and path independently identify the same real position image in both roots. Sixteen component tests passed. No original waveform data was opened.

Run `saved_overhead.py PRIVATE_TMPFS/trial` in the same installed environment, using CPU 2, the shared Gauss lock, nice 15, I/O priority 7 and one numerical thread. The driver reads the earlier matched raw receipt and its sealed detector packet, then starts one fresh saved process per arm. The measurement receipt expands to SHA-256 `ef7e7a484b77442de8b1294cca41d661758a1075ec9e3744a40a6690be158d10`. [Driver](saved_overhead.py)
