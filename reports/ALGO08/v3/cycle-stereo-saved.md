# Complete donor cycles preserved North’s history decision and lost position accuracy

North’s whole-cycle 8 ms packet produced a fix with **2,671.1 / 2,663.0 m** error for fixed-zero and fitted calibration. Both errors exceeded the preregistered admission allowances, ending the weak transfer. Its RF residuals improved relative to both prior 8 ms routes. The accepted signed finish had **48 owners in two satellite families**, down from 342 owners with measurements on every visit. [Frozen schedule](cycle-stereo-protocol.md) · [Signed inputs, verified publication and score](measurements/cycle-stereo-saved.json.gz)

| Original North containing offer | `c = 0` / fitted error, m | `c = 0` / fitted RF RMS, Hz |
| --- | ---: | ---: |
| Installed ALGO08v3 | 105.690 / 140.779 | 5.406 / 5.167 |
| All-visit 8 ms, combined solver | 111.954 / 128.086 | 9.133 / 8.921 |
| Individual-visit mask, combined solver | 771.969 / 162.150 | 11.590 / 9.899 |
| Whole-cycle mask, combined solver | **2,671.052 / 2,663.022** | **7.449 / 7.446** |

The verified schedule omitted 672 of 2,096 short lane calls in 336 stereo visits and preserved all 304 full calls. The held gains were **+55.04 / +45.99 nats**, so the original history route retained 240 factors. This lost 168 previously selected observations on omitted visits and another 48 on paid visits, including 20 paid full anchors. The 48 final owners, 24 each from NORADs 52551 and 65804, were conditional in both arms. All were shared with the all-visit control and retained their owners and roles. The earlier individual mask had 319 owners per arm. It shared 36 with the whole-cycle fit and had the same roles and NORADs on those observations. The held-anchor test preserved the choice of route while the selected orbit coverage still collapsed. [All-visit science](eight-ms-native-live.md) · [Individual-mask comparison](whole-stereo-8ms.md)

The ordinary saved solver exercised both requested optimizations. It used 11 portable orbit-sidecar hits and compacted all 64 rank profiles. Regional preparation used 25 probes, 190 graph points and 20 tracks and stopped at `inside_score`. The solver accepted the named final fit without inference fallback. Both calibration arms, 137 grid points, the position path and eight decoded PNGs passed independent verification. The original 25 km offer, raw authority, signed metadata and causal cutoff were unchanged. The published native digest `3d164600a3af30e060029be98af0556e1e79d5b6bef0828f0e2dc6e50e31c77e` matched the supplied bytes and the independently reconstructed schedule and history.

| North timing scope | All-visit 8 ms | Individual-visit mask | Whole-cycle mask |
| --- | ---: | ---: | ---: |
| Through exit, elapsed / CPU s | 10.828 / 10.826 raw | 5.747 / 5.742 saved | **4.476 / 4.474 saved** |
| Numerical solver, CPU s | 3.345 | 3.431 | **2.403** |
| Mask, held selection and signed staging, CPU s | — | 0.056 | **0.046** |

The whole-cycle saved launch spent 4.116 s user and 0.358 s system CPU, with zero input blocks and major faults. Adding the original planner raises its saved CPU charge to **4.520 s**. The independent input-stage verification for both supplied packets took another 0.048 CPU s outside launch. The preexisting model credits 0.595 CPU s in omitted North calls at the measured original mean, or **0.550 s** after planning. It retains all source verification and 20 ms anchor work. Weak DS30-0016’s sealed plan also kept its old route, unfiltered, at 369 selected factors and **0.287 s** estimated credit after planning. The accuracy gate stopped before its solver. There were no waveform calls. Saved and raw through-exit clocks cover different work.

Use `cycle_stereo_saved.py stage FRESH_TMPFS_ROOT`, then `run ROOT north` and `score ROOT north` on CPU 2 under the shared Gauss lock, nice 15, I/O priority 7 and one numerical thread. The original planner and detector document digests for both sites are pinned in the launcher. An initial metadata staging attempt stopped on a clock arithmetic error before starting a child. Freeze `8e4a29805` includes that correction. One complete North process ran. Five focused tests passed. [Saved runner](cycle_stereo_saved.py) · [Admission test](../../../tests/pipeline_eval/test_cycle_stereo_saved.py)
