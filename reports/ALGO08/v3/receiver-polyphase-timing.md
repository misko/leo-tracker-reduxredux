# Folding the quarter-rate timing scout

On two saved prefixes, folding the timing inverse transform while computing every epoch preserved all 138 ordered factor records and the sole causal selection. Native CPU increased about 2–3%. Computing only one timing phase saved native CPU but lost 14 verified factors, including the dense prefix's sole causal selection. Neither arm merits a full-recording replay.

## Computation

Both raw and signed-residual scouts form the original eight quadratic lag sequences from the two complex quarter-rate modes. Each sequence receives the frozen 4,800-point forward FFT and complex pilot filter. With filtered spectrum \(Y\) and \(H=N/2\), the two subsequences of the inverse DFT are

\[
 N y[2j] = \sum_{k=0}^{H-1} (Y[k]+Y[k+H]) e^{2\pi i k j/H}, \qquad
 N y[2j+1] = \sum_{k=0}^{H-1} (Y[k]-Y[k+H]) e^{2\pi i k/N} e^{2\pi i k j/H}.
\]

The full-grid arm computes both folds, applies the same per-epoch energy denominator, and ranks all 3,333 epochs. Its inverse is equal in exact arithmetic but uses a different Float32 reduction. The half-grid arm computes only the even fold and ranks its 1,667 exact-arithmetic samples. An interior peak can shift by one quarter-rate sample when its adjacent even scores support that shift by quadratic interpolation. Carrier FFTs still use the original 2.5 MS/s modes, all 12 proposed epochs, and the original signed eligibility. Coarse native refinement, independent pilot gates, signed cancellation, original-I/Q fractional scores, and causal continuation receive the resulting proposals. Folding occurs after the magnitude-invariant lag products and leaves the signed carrier bandwidth on the original scout grid. [Native kernel](../../../tools/pipeline_eval/variants/experimental/receiver_polyphase_timing.inc) · [Sampling-floor audit](../single-core-2x/receiver-rate.md)

The earlier full-aperture differential scout lost 25 of 112 factors. The prior tracking shortcut lost 30 of 152 and 9 of 53 continued selections. A shorter-window scout and a raw fixed bank also missed second-scan evidence. Exact pruning of the carrier and refinement banks had low stage ceilings. The fold keeps the full original lag aperture and recomputes each timing score from the actual signed residual. [Differential scout](differential-fold.md) · [Tracking](../single-core-2x/receiver-tracking.md) · [Joint blocks](joint-blocks.md) · [Carrier FFT bounds](carrier-fft-bound.md) · [Refinement bounds](refine-bound.md)

## Receiver and continuation

The detector experiment uses the 18 sealed DS26 weak-carrier visits and the first 48 authenticated DS30-0008 visits. Across both slices the native measurement covers 132 independent antenna calls per repeat. Five repeats alternate arm order by lane with FFT plans ready and I/Q in memory. Native clocks end after the detector returns. Continuation starts empty per recording with separate history for each arm.

| Arm and slice | Installed factors, primary / residual | Matched factors, primary / residual | Unmatched additions | Continued, installed → candidate |
|---|---:|---:|---:|---:|
| Full-grid weak | 36 / 22 | 36 / 22 | 0 | 0 → 0 |
| Full-grid dense | 52 / 28 | 52 / 28 | 0 | 1 → 1 |
| Half-grid weak | 36 / 22 | 36 / 19 | 1 | 0 → 0 |
| Half-grid dense | 52 / 28 | 47 / 22 | 0 | 1 → 0 |

Matches are one-to-one within two wrapped native samples and 250 Hz signed CFO. Every full-grid tuple matched byte for byte. Among matched half-grid factors, the largest changes were 0.00585 samples and 97.70 Hz weak, and 0.00361 samples and 36.06 Hz dense. A lost weak residual had an exact-minus-control margin of 0.2601. A lost dense primary had a margin of 0.2418. The lost causal selection was the dense primary at visit 44, lane 0, with a margin of 0.1066 and CFO −415,950.94 Hz. A high-margin pilot on the stock path can disappear upstream of the half-grid arm's confirmation. [Input identities, factor changes and continuation votes](measurements/receiver-polyphase-timing.json)

These prefixes do not support a position comparison. A missing causal selection and the CFO changes among retained factors are direct risks for orbit support and the position objective. The full-grid arm's Float32 FFT order can affect close timing ranks elsewhere even though this pair preserved factor bytes. A successor with a measured acquisition gain would still need independent geographic evidence, containing and omitted regions, and matched zero- and fitted-`c` frequency-fit and position outcomes.

## Timing budget

The changed timing objects trained on the same site-free generated recipe as installed v3. The rebuilt stock receiver and stock timing object reproduced the archived installed bytes. The variants kept the installed object recipe for the surrounding receiver. Stage clocks come from separate PGO builds with inline instrumentation and identical factor and continuation digests.

| Arm and slice | Median native CPU, installed → candidate | Median native elapsed, installed → candidate | Paired CPU change |
|---|---:|---:|---:|
| Full-grid weak | 143.01 → 145.50 ms | 143.05 → 145.54 ms | +2.09% |
| Full-grid dense | 263.66 → 270.92 ms | 263.77 → 271.02 ms | +3.22% |
| Half-grid weak | 142.81 → 141.46 ms | 142.86 → 141.51 ms | −1.23% |
| Half-grid dense | 261.18 → 247.27 ms | 261.26 → 247.37 ms | −5.41% |

| Slice | Stock scouts | Stock decimation / modes / lag / carrier per scout | Half-grid lag per scout | Stock native refinement per scout |
|---|---:|---:|---:|---:|
| Weak | 72 | 150 / 177 / 170 / 142 µs | 158 µs | 290 µs |
| Dense | 148 | 152 / 169 / 174 / 142 µs | 163 µs | 299 µs |

The measured half-grid dense lag saving of about 11.5 µs per scout would remove about 1.7 ms at the stock count. The full-call clock also reflects five fewer residual scouts per repeat and less verification. Even making every dense mode projection, timing and carrier operation, and FIR decimation free saves approximately 0.98 ms per lane, or 13.3 CPU seconds if the measured prefix rate transfers to 13,530 lanes. The earlier dense receiver target called for about 20 seconds saved. This ceiling leaves the verifier, native refinement, signed cancellation, verified I/Q reads, launch and acquisition handoff. [DS30-0008 resident native budget](differential-fold.md) · [Whole publication timing](single-core-target.md)

An oracle that reran the installed detector only on lanes with missing or unmatched factors would retry 3 of 36 weak lanes and 10 of 96 dense lanes, at median measured control costs of 12.55 and 40.42 ms per repeat. Charging those retries after the half-grid call makes it **7.60% slower weak and 10.06% slower dense**, before any routing work. Requiring equal factor bytes raises the oracle cost to about 27% slower on both slices. A rule that retries when fewer than two factors return would rerun 16 weak and 74 dense lanes, while missing the weak substitution that returned two factors. [Per-lane measured retry estimates](measurements/receiver-polyphase-timing.json)

A 2× solver on the team's historical controls requires acquisition below 47.31% and 42.47% of its original elapsed clock. The earlier sealed-reader study assigned 41–50% of acquisition **CPU** to verified I/Q on the shorter DS30-0016 and DS30-0374 prefixes with a different receiver lineage. At a 41% fixed share, meeting those elapsed ratios would allow about 11% and 2.5% of the original remaining work under a fully CPU-bound model. At 50% the assumed fixed share exceeds both budgets.

For warm DS30-0008, about 36.5 seconds of receiver CPU extrapolated from resident samples and 52.70 seconds of measured acquisition elapsed give about 16.2 seconds, or 31%, for waiting, verified reads, decode, calls around the receiver and other acquisition work. That residual is an estimate across different scopes. With a 2× solve and the observed 3.34-second publication tail, the acquisition allowance would be 24.68 seconds. Holding the estimated 16.2-second residual fixed leaves about 8.5 seconds for the native receiver, a 77% reduction. Even zeroing the complete native scout stage through confirmation would remove about two-thirds of current native CPU on the measured dense prefix, before signed cancellation and the original-I/Q verifier. The stages audited here provide no route to close the balance. The verified format requires compression decode, manifest and chunk checks, and window digests. Larger acquisition gains would have to encompass both scans, refinement and verification alongside those mandatory operations. [Historical reader CPU breakdown](../single-core-2x/receiver-ingress.md) · [Dense warm elapsed and stage budgets](single-core-target.md)

## Reproduce

Use the shared lock and archived PGO recipe. The runner stops at continuation on the two saved slices. The authenticated physical reader runs as the existing capture account. The deployed receiver and pilot assets are read directly. The measured receipt repeats the same saved comparison with library digests checked against the first build. The component run passed 12 tests, including native folding of both phases, signed-CFO and wrapped-epoch matching, and retry accounting.

```sh
bench=/tmp/leo-algo08v2-2x-bench
tree=/home/mouse9911/gits/leo-tracker-reduxredux
release=/opt/leo-algo08/current
installed=/opt/leo-algo08/algo08v3/payload/receiver.so
binding=/srv/bulk/leo-dev/ds30-full-20261121/bindings/DS30-0008.json
weak="$tree/reports/2026_11_20_single_scan_glrt/satellite-reference.zip"
lock() {
  flock -x "$bench/gauss.lock" nice -n 15 ionice -c2 -n7 taskset -c 2 timeout 55s "$@"
}
lock sudo -n -u leo env OMP_NUM_THREADS=1 OMP_THREAD_LIMIT=1 OPENBLAS_NUM_THREADS=1 \
  MKL_NUM_THREADS=1 BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 \
  PYTHONPATH="$PWD:$release/src:$release" "$release/venv/bin/python" -BPs \
  -m reports.ALGO08.v3.receiver_polyphase_trial \
  "$bench/receiver-fractional-exact-v1" "$bench/spectral-vectors-combined-v1.json" \
  /var/tmp/leo-v3-polyphase-new "$installed" "$release/assets" "$weak" "$binding" /srv/bulk
lock env OMP_NUM_THREADS=1 OMP_THREAD_LIMIT=1 OPENBLAS_NUM_THREADS=1 \
  MKL_NUM_THREADS=1 BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 \
  PYTHONPATH="$PWD:$release/src:$release" "$tree/.venv/bin/python" -BPs -m pytest -q \
  tests/pipeline_eval/test_receiver_polyphase_timing.py \
  tests/pipeline_eval/test_receiver_cfo_peak_bound.py tests/pipeline_eval/test_receiver_differential_fold.py
```
