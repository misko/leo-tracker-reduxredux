# Full saved IQ through the slim direct receiver

One 512 MiB Linux service replayed the complete **300.018 s** DS29-0082 recording with the prepared-fractional GLRT worker and then returned both positions through the 78-source slim direct receiver. Time from raw entry to both positions was **94.616 s**. The service lifetime was **95.690 s**, at a **536,870,912-byte** cgroup peak with zero swap and zero OOM kills. Both coordinates and conditional Doppler RMS values matched the earlier prepared and ordinary stock whole-IQ controls exactly. [Both-arm charts](charts/index.html) · [Timings](timings.csv) · [Source and service receipt](receipt.json)

## Raw replay and numerical handoff

The prepared-fractional worker read all 14 authenticated segments through the installed acquisition wrapper. It retained all 6,772 scheduled visits, including the original 1,904 invalid-capture exclusions, and ran 4,868 valid native calls on CPUs 18 and 19. It emitted 9,736 probe rows and 43,375 candidates, including 7,962 positive candidates. Both raw lanes matched the sealed ordinary controls, and all these counts matched the earlier prepared replay. The fresh factor SHA-256 is `5557acb61ef5bb366f0d15c7a76f0d26eec5ae4b2f149443fde1e6754bcf9e51`, identical to the previous prepared file. The normalized scientific factors also matched the ordinary stock detector. [Fresh authenticated factor bytes](native.json.gz) · [Visit and numerical counters](comparison.json)

After factor and truth-free request validation, the raw orchestrator replaced itself inside the same cgroup and PID with the slim numerical entry on CPU 18 at nice 10. The handoff gave that entry explicit paths and digests for the stored factors and track configuration, the read-only causal archive, the original 25 km tile and broad screen, and the prebuilt native bound and projector. The numerical process recorded zero evaluation or qualification imports. The raw replay uses the existing corpus qualification launcher and installed acquisition wrapper. Its unchanged assembly still builds a temporary projector during qualification. The slim receiver uses its separately verified prebuilt projector. [Protocol](PROTOCOL.md) · [Handoff and cgroup evidence](stages.json.gz) · [78-source and binary ledger](source-lock.json)

## Resource scopes

| Measured quantity | Ordinary stock | Prior prepared | Prepared → slim direct |
|---|---:|---:|---:|
| Raw authentication, decode and GLRT wall s | 88.071 | 78.995 | 60.963 |
| Raw cgroup CPU s | 163.959 | 147.968 | 113.501 |
| Assembly and parity wall s | 0.799 | 2.006 | 1.725 |
| Process handoff wall s | 0.137 | 0.173 | 0.054 |
| Position interval wall / CPU s | 41.218 / 40.803 | 41.612 / 40.687 | 31.874 / 31.733 |
| Raw entry to positions wall / CPU s | 130.225 / 205.571 | 122.787 / 190.671 | 94.616 / 146.982 |
| Position process peak RSS KiB | 479,256 | 478,160 | 321,540 |
| Observed 20 ms-or-faster native calls | 44 / 4,868 | 861 / 4,868 | 4,076 / 4,868 |

The current systemd service used 148.043 CPU seconds including startup and teardown. The cgroup had already reached 512 MiB by position entry, so full-service memory peak differs from the position process’s 321,540 KiB RSS high-water. The same prepared raw binary was used in both prepared replays. Its measured raw interval also changed substantially, so the 28.17-second whole-replay difference against the prior prepared run cannot be attributed to the handoff alone. Both prior measurements occurred at other times on the same shared host. These are stored replay measurements on one recording. [Scope-specific resource data](timings.csv) · [Earlier prepared study](../../streamlined/whole-fractional/README.md) · [Earlier ordinary study](../../streamlined/whole-pair/README.md)

## Both calibration arms

The direct worker and both controls fit 2,044 observations in 70 tracks, evaluated three initial branches, and made 2,494 compact projections. All kept the signed incumbent after cavity nomination. The frequency objective values were 11,815.163224720734 and 11,818.344654360739, matching the earlier unrestricted direct receiver on the normalized ordinary factors. Geographic error is measured separately from conditional Doppler RMS. [Scores](scores.csv) · [Published coordinates](positions.jsonl.gz) · [Earlier frequency objectives](../../streamlined/direct-cavity/scores.csv)

| Arm | Latitude | Longitude | Horizontal error km | Conditional Doppler RMS Hz |
|---|---:|---:|---:|---:|
| `c = 0` | 37.873858439 | −122.490523446 | 2.789469 | 106.672251 |
| Fitted `c` | 37.872828354 | −122.488485228 | 2.654183 | 106.588481 |

## Run the slim position command from factors

Run from a prepared slim package directory with its local native manifest and projector already built. The position CLI accepts explicit input paths and a caller-declared SHA-256 for the decompressed factor bytes. It uses the causal TLE archive’s read-only layout and checks each snapshot it consumes. The measurement used Linux x86-64 CPython 3.12 with the sealed scientific environment and a single numerical thread.

```sh
export PYTHONPATH="$PWD"
export TMPDIR="$local_disk_scratch"
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 BLIS_NUM_THREADS=1
python -B -m tools.pipeline_eval.variants.v5_direct_lifetime \
  --native "$native_glrt" --native-sha256 "$native_sha256" --session "$session_id" \
  --track-config "$track_config" --config-sha256 "$config_sha256" \
  --archive "$causal_tle_root" --native-backend native/manifest.json \
  --library projector.so --tile "$tile_lat" "$tile_lon" \
  --screen-center "$screen_lat" "$screen_lon" --width-km 25
```
