# Receiver aperture and selection on DS30-0049 and DS30-0016

In the six complete staged DS30-0049 members, restoring 20 ms between two-scan anchors recovered six of the seven installed-owned lanes that had become empty. Restoring cancellation at 8 ms recovered none. The opt-in 20 ms primary nonanchor mode subsequently completed an independent, full DS30-0016 publication. Its position error improved by 0.240 km at `c0` and 0.288 km at fitted `c` relative to the installed receiver. It regressed by 0.913 km and 0.394 km relative to the charted 8 ms route and failed the frozen 0.25 km development threshold in both arms. Keep the mode as a separate development option.

## DS30-0049 detector prefix

The input comprised six authenticated, consecutive original compressed members with 384 visits, of which 362 were admitted and 22 invalid. Both lanes of every admitted visit were included. All four native measurement paths used the same 92 two-scan anchor lanes in the selector replay, leaving 632 nonanchor lanes per cell. At the 64-visit check and at the 384-visit frontier, the installed `20 ms two scans / continuation` and successor `8 ms primary / strongest` diagonals matched their stored public detector rows exactly. Both short native symbols were invariant to saturated suffix samples in 32 first-in-stream checks. Each directly measured primary factor array equaled the exported rank-zero array of its corresponding two-scan cell on every lane.

The full installed publication had 320 owners in each calibration arm. Of them, 44 became empty and 21 were strongly displaced in the successor. This authenticated prefix contained 101 installed-owned lanes, including seven of the empty losses and two of the displaced losses. Ownership-based comparisons are identical for both arms. A factor counts as recovered if the signed CFO is within 250 Hz and the wrapped fractional epoch within two samples of the installed factor. The table uses the actual two-scan or primary callback times for the scheduled slots and separates the per-selector outcome. Each cell has 724 scheduled lane calls.

| Nonanchor receiver | Selector | All positive lanes | Recovered of 101 owners | Empty loss recovery of 7 | Displaced loss recovery of 2 | Matching alternatives before selection | Diagnostic native CPU |
|---|---|---:|---:|---:|---:|---:|---:|
| 20 ms two scans | Continuation | 184 | 101 | 7 | 2 | 101 | 1.599 s |
| 20 ms two scans | Strongest | 239 | 101 | 7 | 2 | 101 | 1.599 s |
| 20 ms primary | Continuation | 176 | 96 | 6 | 2 | 100 | 1.259 s |
| 20 ms primary | Strongest | 239 | 100 | 6 | 2 | 100 | 1.259 s |
| 8 ms two scans | Continuation | 135 | 74 | 0 | 1 | 78 | 1.056 s |
| 8 ms two scans | Strongest | 245 | 75 | 0 | 0 | 78 | 1.056 s |
| 8 ms primary | Continuation | 129 | 73 | 0 | 0 | 77 | 0.756 s |
| 8 ms primary | Strongest | 238 | 77 | 0 | 0 | 77 | 0.756 s |

At 8 ms both searches lacked matching native alternatives on all seven empty losses. One of the two strongly displaced lanes had a matching 8 ms second rank recovered by Continuation alone. At 20 ms one stock owner required cancellation and the strongest selector recovered all other 100 exactly. The original held-selector check preferred unfiltered strongest on both the prefix and the whole capture. The measured native saving for 20 ms primary nonanchors was 0.340 s (21.3%) against two scans on the prefix. It cost 0.503 s more than the measured 8 ms primary cadence. The callbacks were interleaved and the diagnostic assay took 6.96 s wall and 6.93 s CPU, inclusive of intake and both selector replays. The first setup exited before waveform access due to import ordering, taking 1.52 s wall and 1.06 s CPU. Prior 12 ms and checked one-scan receiver studies used different native paths.

The complete DS30-0049 capture had zero resident bytes across its 16 original payload members (1,202,056,196 encoded bytes). The authenticated local stage ended inside member seven. This assay read the six full members and performed no full-capture solve or new backing waveform read.

## Independent DS30-0016 raw transfer

The ordinary original-file publication entry received `--full-primary-nonanchors` in place of `--sparse8-primary`, with the `--short-binary` argument removed. It used the historical original `--recording`, `--region` and `--archive`, and the same causal cutoff and portable index. The independent detector recipe and original signed recording authority were both verified. All 808 visits were reconciled, including 713 valid and 95 invalid visits. The receiver paid 186 full two-scan lane calls and 1,240 full primary calls on the 1,426 admitted lanes. The output verified both calibration arms, the full 179-position grid, the original path and all eight PNGs.

| DS30-0016 raw publication | Horizontal error `c0` / fitted `c` | Terminal RF RMS `c0` / fitted `c` | All-owned RF RMS `c0` / fitted `c` | Detector positives | Owners in each arm | Process wall / CPU |
|---|---:|---:|---:|---:|---:|---:|
| Installed full 20 ms | 1.644 / 1.661 km | 109.375 / 109.479 Hz | 106.837 / 106.555 Hz | 440 | 109 | 10.861 / 10.855 s |
| Charted 8 ms nonanchors | 0.490 / 0.980 km | 134.021 / 133.740 Hz | 135.547 / 136.859 Hz | 506 | 115 | 7.053 / 7.050 s |
| Full 20 ms primary nonanchors | 1.404 / 1.374 km | 140.262 / 140.256 Hz | 140.257 / 150.882 Hz | 552 | 164 | 10.361 / 10.165 s |

The opt-in receiver retained a positive on all 440 installed-positive lanes, with 425 identical selected factors. Relative to charted, 414 lanes were jointly positive with 74 identical selected factors, 92 lanes were positive only on charted, and 138 were positive only on full primary. The opt-in preserved 107 of 109 installed observation/satellite owner pairs and 110 of 115 charted pairs in each arm. The two installed satellites, 63510 and 64015, persisted. Fitted `c` reduced terminal RF RMS by 0.005 Hz and horizontal error by 0.030 km for full primary, while its all-owned RF RMS rose by 10.625 Hz. The increased factor and owner counts coincided with worse geographic results against charted.

The raw worker measured 3.375 s of receiver callback CPU against 1.504 s charted, and 5.599 s authenticated acquisition wall against 2.923 s charted. The charted and installed clocks are historical. The candidate process reported 80,560 input blocks whose paths were uninstrumented. The original recording was on a read-only tmpfs bind and its complete 993,933,681-byte extent was confirmed resident immediately before and after. The successful controller including setup and probe took 14.37 s wall and 13.76 s CPU. A first controller setup failed at a missing Python import before its child launch, taking 0.07 s wall and 0.06 s CPU. This run establishes geographic and detector behavior on one independent case. Its timing supports no runtime promotion or 2× claim.

[DS30-0049 fixed protocol](ds30-0049-receiver-factorial-protocol.md) · [DS30-0049 sealed evidence](measurements/ds30-0049-receiver-factorial.json.gz) · [DS30-0016 fixed protocol](ds30-0016-full-primary-transfer-protocol.md) · [DS30-0016 sealed evidence](measurements/ds30-0016-full-primary-transfer.json.gz)
