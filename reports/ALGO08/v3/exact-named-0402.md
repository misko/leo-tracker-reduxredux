# Exact named composition on DS30-0402

The frozen exact named solver took **66.203 s** through verified saved publication and exit on DS30-0402, versus **73.351 s** for the same-packet installed named control, a **1.108×** speedup. Both reproduced all **4,821 ordered owner and role rows per arm**, both calibration positions and RF residuals, the terminal and objective, the standard 179-point grid and recorded path, and all eight PNGs by encoded and decoded hash. The composition now reproduces the installed named publication on **4 of 4** saved physical recordings. [Frozen protocol](exact-named-0402-protocol.md) · [Verified DS30-0402 receipt](measurements/exact-named-DS30-0402.json.gz) · [Four-case comparison](measurements/exact-named-saved-panel-four.json)

| Saved physical recording | Issued / admitted | Wall through exit, named → exact | CPU through exit, named → exact | Wall ratio |
|---|---:|---:|---:|---:|
| DS30-0160 | 3,691 / 2,354 | 15.999 → 10.330 s | 15.994 → 10.317 s | 1.549× |
| DS30-0316 | 3,042 / 2,702 | 18.358 → 16.887 s | 18.353 → 16.829 s | 1.087× |
| DS30-0374 | 6,770 / 4,644 | 28.324 → 23.630 s | 28.268 → 23.616 s | 1.199× |
| DS30-0402 | 6,773 / 6,761 | 73.351 → 66.203 s | 73.254 → 66.184 s | 1.108× |
| Sum | 20,276 / 16,461 | 136.033 → 117.050 s | 135.868 → 116.945 s | 1.162× |

Median case ratios are **1.153× wall** and **1.152× CPU**. The CPU ratio of summed times is **1.162×**. No comparison reached 1.6×. The four clean saved clocks exclude the earlier 4.320 s standalone portable index export and the 1.127 s rejected DS30-0316 metadata startup. Charging both once yields 1.110× on summed wall time. The processes used the signed deployed 20 ms detector documents and include startup, solver, publication, and in-process product verification. The historical controls have separate process and cache conditions. The clocks exclude raw acquisition. [Prior three-case comparison](exact-named-dense.md)

| DS30-0402 arm | Horizontal error, either solver | RF RMS, either solver | Original ordered owners retained |
|---|---:|---:|---:|
| `c = 0` | 863.651 m | 100.672203 Hz | 4,821 / 4,821 |
| Fitted `c` | 860.302 m | 100.576460 Hz | 4,821 / 4,821 |

DS30-0402 solve CPU fell from 68.774 to 61.774 s. The original-order constrained gate activated on one proposal. It spent **15.252 CPU s** in the constrained call, including **15.104 s** across ten phase fits and 393 optimizer visits. It ran 82,137 screens, 48,732 white profiles, and 33,405 whitening calls. The 124 screen setup operations cost 2.237 ms CPU inside that scope. The gate accounted for 24.7% of candidate solve CPU. No source fallbacks were observed. The paired launch provides a combined speed difference and a measured active-gate cost. A separate earlier prepared-gate-only run paid 15.128 CPU s for the same constrained work and completed in 68.589 s. [Gate-only experiment](stock-exact-gate-0402.md)

DS30-0402 supplied the constrained gate development fixture. The earlier **55.830 s** fitted-first run used a veto and executed five phase fits and 58 optimizer visits. The **53.403 s** fitted-first combination also used a different Graph, forecast, and direct renderer. It reproduced the science, with two gray image layers below the visual acceptance threshold. The present candidate retained the deployed order and standard renderer, and its gate ran all ten fits. [Fitted-first veto](paired-veto-0402.md) · [Fitted-first combination and image comparison](named-combined-0402.md)

The fastest separately verified exact saved publication on this recording remains **49.712 s** elapsed with the fitted-first veto and wider exact likelihood fallback. It used the wider path on 239 unsupported calls, retained 4,821 ordered owners per arm, and reproduced the named positions, RF fits, grid, path, and all eight PNGs. The 66.203 s measurement belongs to the frozen composition tested across four recordings. [Wider fitted-first replay](wide-private-0402.md)

The candidate compacted all 1,664 grouped rank calls, used 356 checked predictive-map geometry calls, and reused all eight verified PNG reads. Its earlier DS30-0008 index had zero hits among 42 consumed distinct bodies. The 136 verified causal reads used 243,221,853 logical bytes from the 48 original snapshots already in tmpfs, a resident view of 85,823,046 bytes. No new staging, backing catalogue reads or waveform reads took place. The same low-priority CPU 2 lock serialized the single candidate execution, offline checks and component tests. Fifteen tests passed. The numerical route file is unchanged from `ec4a1f01d`. [Staged request adapter](exact_named_0402.py)
