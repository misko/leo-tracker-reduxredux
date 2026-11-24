# Adaptive 20/8 ms candidate withholds on DS30-0107

The frozen all-visit 20/8 ms candidate reached the legitimate `no_active_curvature` terminal on complete physical DS30-0107 in **0.508 s elapsed**, compared with **1.417 s** for fresh installed ALGO08v3. The **2.79×** comparison includes one fresh process per arm through exit. Both exited successfully and published the ordinary withholding record, with null position and RF RMS in both calibration arms. The configured adaptive map stayed unpublished. [Frozen protocol](adaptive-withhold-0107-protocol.md) · [Paired native, HTTP and timing evidence](measurements/adaptive-withhold-0107.json.gz)

| Fresh process, candidate first | Elapsed through exit (s) | CPU through exit (s) | Native packet sealed (s after launch) | Terminal sealed (s after launch) |
| --- | ---: | ---: | ---: | ---: |
| Adaptive 20/8 ms | 0.508234 | 0.506165 | 0.458010 | 0.458845 |
| Installed ALGO08v3 | 1.417264 | 1.414697 | 1.202878 | 1.241683 |

Both processed the same signed inventory and original 25 km offer, with 29 issued visits, 27 admitted stereo visits, and two invalid visits. The original cutoff was `1794702096144017710` and the staged causal archive retained all 51 verified snapshots. A private read-only bind exposed the original canonical path from tmpfs. All 8,184 compressed payload and 20 index pages stayed resident. The complete 33,519,983-byte compressed member and 78,609-byte index were already staged. There were zero backing waveform reads or conditioning bytes. The candidate and installed process recorded 8 and 32 process input blocks, respectively, and one major fault each. These process-wide counters do not identify a file. [Earlier input and exact named comparison](eight-ms-0107-pair.md)

The native candidate and installed packets each exactly reproduced their earlier independent DS30-0107 packet and terminal digest, with identical order and identity across all 54 stereo opportunities. The candidate paid 16 original full two-scan calls and 38 native short calls, returning six full and 13 short factors. Its held-route selector chose unfiltered and performed zero CFO remeasurements. Installed ALGO08v3 exported zero factors, matching its archived named packet. The candidate's original graph proof bound all 19 factors and measured a largest same-lane span of 0.7079473 s against the 20 s track requirement. The candidate performed one authenticated acquisition and one verified handoff. Its acquisition consumed 132.848 CPU ms, with 36.706 and 30.861 ms in the full and short native calls. The graph proof withheld before scientific imports, adaptive sampling, orbit transfers, catalogue ranks or plotting. The clocks measure a physical withholding case. [Original full two-scan candidate](eight-ms-native-live.md) · [Adaptive raw route](adaptive-raw-protocol.md)

The released standard-analysis HTTP router returned 200 and the correct `withheld` state, run and session IDs, original offer, native input and terminal digests for each process. Both ordinary withholding documents returned empty arms and artifacts. The signed terminals held null positions and the evaluated RF summaries were null for `c = 0` and fitted `c`. All eight official PNG routes and the grid and path routes returned 404 on each publication. Both fresh trees contained zero PNGs, grid files, path files or adaptive publication directories. The web audit ran in-process against the real released router and filesystem reader after timing. [Exact HTTP responses and file checks](measurements/adaptive-withhold-0107.json.gz)

## Reproduce

Use freeze `f918d6eef` on North adaptive scorer tip `f7ac34bbe`. In a private mount namespace, bind the existing recording beneath `/dev/shm/leo-v3-continued-cfo-0107-pair01` read-only at its original recording path. Use the same low-priority Gauss lock, CPU 2, nice 15, I/O priority best-effort 7 and one numerical thread. Run as `leo` using the installed release Python and set `PYTHONPATH` to the checkout, its `reports/ALGO08/v3` directory, and the release's `src` and root. [Paired runner](adaptive_withhold_0107.py) · [Component tests](../../../tests/pipeline_eval/test_adaptive_withhold_0107.py)

```bash
python -Bm reports.ALGO08.v3.adaptive_withhold_0107 launch /dev/shm/adaptive-withhold-pair
PYTHONPATH="$PWD/src:$PYTHONPATH" python -Bm reports.ALGO08.v3.adaptive_withhold_0107 score \
  /dev/shm/adaptive-withhold-pair --output /dev/shm/adaptive-withhold-score.json
```

The initial post-clock scorer resolved the older installed storage API. Adding checkout `src` selected the read-only audit API and the signed pair remained untouched. The API router and standard publication store used for the HTTP check hash-identically to the released copies. Twelve focused and adjacent tests passed. The uncompressed score SHA-256 is `5922021a53707a47dd05023c64e3df2a6be638fae519205bfc66a9203130092d`.
