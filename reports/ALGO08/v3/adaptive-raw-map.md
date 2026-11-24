# Adaptive diagnostic map on two original public recordings

The independent North and South containing runs used the original signed 1,200-visit simulations, 20 ms two-scan anchors and native 8 ms on every other visit, through raw acquisition, both fitted arms, eight decoded PNGs and successful process exit. Each produced the exact same signed detector packet, held history decision, geographic terminal and ordered owners as its earlier full-layout 20/8 ms run. North took 0.299 s less through exit. South took 0.232 s more even though exact posterior mapping saved about 0.264 s.

| Through exit | Installed ALGO08v3 elapsed | Full map 20/8 CPU / elapsed | Adaptive 20/8 CPU / elapsed | Adaptive minus full elapsed |
| --- | ---: | ---: | ---: | ---: |
| North | 16.133 s | 10.826 / 10.828 s | 10.527 / 10.530 s | −0.299 s |
| South | 14.370 s | 10.465 / 10.466 s | 10.697 / 10.699 s | +0.232 s |

North's recently refreshed installed comparator and South's earlier installed comparator are historical to this test, as are both ordinary 20/8 clocks. The adaptive children ran once each in that order. The same terminal and evidence through exit were verified, but there is no balanced estimate of timing variability. North is 1.53× and South 1.34× as fast as their named controls and both elapsed clocks remain above half of named. [North named control](measurements/current-north-control.json.gz) · [North full-layout control](eight-ms-native-live.md) · [South full-layout and named controls](eight-ms-south-transfer.md)

| Stage elapsed | North full → adaptive | South full → adaptive |
| --- | ---: | ---: |
| Signed acquisition | 5.074 → 5.060 s | 5.022 → 5.413 s |
| Held selector | 0.066 → 0.067 s | 0.064 → 0.064 s |
| Decision and publication | 5.174 → 4.917 s | 4.888 → 4.680 s |
| Post-fit scientific evidence, within publication | 0.574 → 0.316 s | 0.577 → 0.313 s |
| Position map alone, within that evidence | 0.519 → 0.262 s | 0.529 → 0.263 s |

Both original recordings and their indexes were fully resident in tmpfs before and after the timed children. North had 385,609 payload pages and 188 index pages, with 1,579,423,424 authenticated compressed and 1,920,000,000 decoded bytes. South had 384,361 payload pages and 188 index pages, with 1,574,298,988 authenticated compressed and 1,920,000,000 decoded bytes. Both ran all 304 anchor and 2,096 short radio calls. North charged two major faults and 40 input blocks process-wide, included in its elapsed and unassigned to a specific operation. South charged zero of either. No waveform conditioning, copying or backing-store waveform access occurred. The first North orchestration preflight encountered an incorrect tooling import order before creating an output root or starting the timed child. The corrected import order is below.

## Matched scientific result

| Case | Ordered owners, both arms | Position error c = 0 / fitted c | RF RMS c = 0 / fitted c | Actual grid points | Original low points, minima or failures missed |
| --- | ---: | ---: | ---: | ---: | ---: |
| North | 342 | 0.112 / 0.128 km | 9.133 / 8.921 Hz | 78 / 137 | 0 / 0 |
| South | 304 | 0.325 / 0.363 km | 10.213 / 10.108 Hz | 79 / 137 | 0 / 0 |

The comparison uses conditional RF RMS from the sealed fit. It keeps the survey check separate from RF. Named ALGO08v3 had North position errors of 0.106/0.141 km and RF RMS of 5.406/5.167 Hz. Its South errors were 0.817/1.101 km and RF RMS 6.502/6.392 Hz. Both adaptive candidates retained the containing fix. The signed calibration endpoints, complete ordered owner rows, fixed-position objective replay, graph proof, held selector decision, and original recorded path matched exactly. The named original final fit was applied on both. Portable indexing reused 11 original causal archive bodies on each run, with 272 compact catalogue rank calls on North and 240 on South.

The grid took one exact measurement for each arm at every sampled location, with 154 and 156 native nonendpoint posterior calls respectively. Every retained full-grid score and failure flag stayed exact. Of the omitted 59 North and 58 South coordinates, neither arm lost a minimum, point within 4.5 conditional loss of the original minimum, or failed trial. The renderer draws actual evaluated points on the original geographic frame. Seven PNGs per site reproduced the encoded bytes, pixels and dimensions. The revised position PNG retained its dimensions and passed file-hash and decoded verification. The sample and PNGs are published in the separate research namespace under each original raw run root. The raw decision and all acquisition and owner receipts follow their original boundary.

The two adaptive raw runs used the containing offers. Previously archived nearby omitted offers can exercise the numerical map selection independently, but these runs do not measure new omitted-offer decisions. The existing South 20/8 omission was a false fix and a post-fit map cannot change it. These geographic simulations also leave the physical half-time requirement unresolved. [South omitted-offer result](eight-ms-south-transfer.md)

## Reproduction

The frozen adapter is the original f8f1fec25 sample and layout. The normal combined CLI forwards the opt-in map switch to the raw bootstrap. The bootstrap enters the layout only after the signed receiver-first acquisition and causal EOF selector. The raw 20/8 recipe remains independent of this publication option. The two measured source revisions differ only in the offline scoring script and its tests. The unchanged worker files and all libraries are pinned at launch. Before South, the independent readback verified North's exact native, terminal, endpoint, owners, grid and figures, and North saved more than the frozen 0.20 s elapsed margin. [Protocol](adaptive-raw-protocol.md) · [Frozen bindings, exact maps and verified evidence](measurements/adaptive-raw-map.json.gz)

From the repository root, set the tooling paths below, and run each phase from the original tmpfs staging owner under the shared Gauss lock. The raw subprocess is the original isolated CLI with its historic options recorded verbatim in the binding. The score runs after child exit, so its readback and the passive residency checks do not enter the child clock.

```bash
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
payload=/opt/leo-algo08/algo08v3/payload
export PYTHONPATH="$PWD/reports/ALGO08/v3:$PWD:$payload:$release/src:$release:$PWD/src"
export OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 OMP_NUM_THREADS=1
export OMP_THREAD_LIMIT=1 BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
locked() {
  flock -w 60 /tmp/leo-algo08v2-2x-bench/gauss.lock \
    nice -n 15 ionice -c 2 -n 7 taskset -c 2 \
    "$release/venv/bin/python" -BPs reports/ALGO08/v3/adaptive_raw_trial.py "$@"
}
output=/dev/shm/leo-v3-north-adaptive-raw-reproduction
locked prepare "$output"
locked launch "$output"
locked score "$output"
```

Five focused tests exercise exact command substitution, source import scoping, independent per-arm low-loss checks, passive counts and exact selector binding.
