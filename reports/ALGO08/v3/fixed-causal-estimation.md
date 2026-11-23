# Causal estimation on fixed unfiltered short assignments

In the northern simulation, restricting the original assignments to causal measurements lowered fixed-zero RF RMS from **69.40 to 8.02 Hz** while increasing position error from **0.390 to 0.742 km**. Rebuilding the graph and assignments on the causal packet returned **0.128 km**. On weak DS30-0016, the fixed and rebuilt causal fits used the **same 107 observations, satellite IDs and roles**. Removing nine observations from the fixed unfiltered fit increased horizontal error in both arms and accounted for most of the degradation seen after rebuilding. [Frozen counterfactual](fixed-causal-estimation-protocol.md) · [Scored receipts](measurements/fixed-causal-estimation.json.gz)

## Fixed-assignment comparison

Each new solve ran the complete unfiltered graph and signed fit first. The archived unfiltered endpoints, RF RMS and owner rows reproduced exactly in both calibration arms. A separate forward continuation on the original signed packet supplied an ID mask. The refit kept the original components, orbit owners, aliases, conditional and predictive roles, likelihood powers and measurement weights. It masked the original conditional arrays and used the retained rows of the original predictive basis, with predictive whitening recomputed at the retained timestamps. The original prepared graph remained the authority for plotting and regional inspection. [Implementation](fixed_causal_estimation.py)

The diagnostic starts at each arm's unfiltered endpoint and phase reference. It therefore isolates changing the included observations within the existing model and starting basin. It cannot independently nominate a usable assignment. Both refits passed the original compatibility, owner and regional gates. The north repeated 25 regional projections and again passed the containing-offer check. Across the eight compared publications the scorer read all 64 figures, verified the saved science artifacts and complete 137-point northern and 179-point physical grids, and found zero endpoint objective replay difference. [Clocks, owners, plots and numerical checks](measurements/fixed-causal-estimation.json.gz)

| Case and estimator | Horizontal error, `c = 0` / fitted (km) | RF RMS, `c = 0` / fitted (Hz) |
|---|---:|---:|
| North, installed v3 | 0.106 / 0.141 | 5.406 / 5.167 |
| North, unfiltered short | 0.390 / 0.121 | 69.401 / 70.860 |
| North, fixed assignments and causal rows | **0.742 / 0.110** | **8.020 / 6.823** |
| North, causal rows and rebuilt assignments | 0.128 / 0.113 | 6.881 / 6.764 |
| DS30-0016, installed v3 | 1.644 / 1.661 | 109.375 / 109.479 |
| DS30-0016, unfiltered short | 1.311 / 1.694 | 121.526 / 120.291 |
| DS30-0016, fixed assignments and causal rows | **2.288 / 2.381** | **116.082 / 115.566** |
| DS30-0016, causal rows and rebuilt assignments | 2.473 / 2.542 | 115.878 / 115.358 |

The northern mask removed 40 conditional and seven predictive observations across 18 arcs. Compared with the rebuilt fit, the fixed model used 73 exclusive and the rebuilt model used 77 exclusive observations. They shared 227 observations with the same satellite, but 18 of those switched conditional or predictive role. Rebuilding changed substantially more than the total count. Dropping the 47 rows at the original assignments was insufficient to reproduce the rebuilt fixed-zero improvement. That improvement is associated with the different support and roles after rebuilding. The two fitted-`c` estimates stayed within 4 m of each other in error relative to the reference. This comparison leaves the contributions of those support changes, nuisance fitting and optimization basin unresolved. [Owner and role overlaps](measurements/fixed-causal-estimation.json.gz)

On DS30-0016, six conditional and three predictive observations were removed from three original arcs. The fixed and rebuilt fits then shared all 107 IDs, satellite labels and roles, while keeping their own graph and nuisance context. The fixed-mask degradation relative to the unfiltered fit was 977 m in fixed-zero and 687 m in fitted `c`. The rebuilt fit worsened another 184 m and 161 m. Changing which rows enter the likelihood therefore reproduced most of the degradation without graph rebuilding on this recording. In the fixed-mask fit, fitting `c` lowered RF RMS by 0.52 Hz and increased location error by 93 m. The northern fixed-mask fit showed a decrease in both quantities. The position implications differ across recordings. [Recorded positions, RF residuals and scored references](measurements/fixed-causal-estimation.json.gz)

## Saved-stage cost

| Saved input | Causal ID preparation CPU s | Mask, exact refit and fitted gates CPU s | Second regional check CPU s | Whole numerical solve CPU s | Fresh process CPU / elapsed s |
|---|---:|---:|---:|---:|---:|
| North | 0.017 | 0.043 | 0.248 | 4.030 | 7.258 / 7.260 |
| DS30-0016 | 0.013 | 0.026 | <0.001 | 2.704 | 5.589 / 5.591 |

The saved processes include the complete unfiltered fit, the diagnostic, and checked standard publication. The earlier controls have their own published clocks. No raw input was replayed, and the fixed-assignment diagnostic makes no speed claim. The first DS30-0016 worker stopped in diagnostic serialization because a stock fit history lacked an optional optimizer movement field. The successful rerun read only endpoint and RF RMS from the original fit. [Individual clocks and preserved failure](measurements/fixed-causal-estimation.json.gz)

## Reproduction

```sh
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
payload=/opt/leo-algo08/algo08v3/payload
driver="$PWD/reports/ALGO08/v3/fixed_causal_estimation.py"
slot() {
  flock -x /tmp/leo-algo08v2-2x-bench/gauss.lock nice -n15 ionice -c2 -n7 taskset -c 2 \
    timeout 100s sudo -n -u leo env OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
    OMP_THREAD_LIMIT=1 MKL_NUM_THREADS=1 BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 "$@"
}
slot PYTHONPATH="$PWD/reports/ALGO08/v3:$payload:$release/src:$release:$PWD" \
  "$release/venv/bin/python" -BPs "$driver" trial "$case" "$new_output"
slot PYTHONPATH="$PWD/reports/ALGO08/v3:$PWD/src:$PWD:$payload:$release" \
  "$release/venv/bin/python" -BPs "$driver" score "$case" "$new_output" --receipt "$new_receipt"
```

Use `north` and `physical` as the case names. Ten focused and adjacent tests passed. The decompressed receipt SHA-256 is `d4a220777ce8b054c6850b98917ae181b31786a5a838b84e39b8349280d94cc2`. [Component tests](../../../tests/pipeline_eval/test_fixed_causal_estimation.py)
