# Giving the mixed receiver timing rows while keeping signed carrier search

On the active mixed schedule for the 48-visit dense prefix, four exact timing rows reduced native CPU from **120.30 to 90.13 ms** against the same rebuilt binary with ordinary search. All 217 ordered factors across the forced and scheduled aperture comparisons matched the pinned receiver, including 50 verified residual factors. For the full dense recording, the paired per-aperture ratios project **4.50 CPU s** of gross detector savings before estimating timing. Eight rows project **3.81 s**. The first-four zero-wait acquisition model needs **3.49 s**. Past timing and simultaneous peer measurements supplied every required row for **zero of 96** dense lanes within ±256 native samples. [Receipt](measurements/timing-only-oracle.json.gz) · [Acquisition requirement](warm-recording-budget.md)

## Measurement

The ordinary quarter-rate timing search computes 3,333 scores and retains twelve peaks with a circular exclusion. The carrier stage then takes the two best eligible signed bins per peak, applies its circular CFO exclusion, and passes the four highest normalized seeds into the stock full-rate bank. The oracle supplies only the distinct timing rows that contribute those four seeds, in their original order. The four-, eight-, and twelve-row arms fill the spare slots with the earliest remaining original timing peaks. Every supplied row still computes both complete carrier spectra. Signed full-rate refinement, the independent pilot gates, actual CI16 cancellation on reached 20 ms residual scans, original-sample fractional verification and continued-selection checks still run. Order of equal carrier scores is preserved. A hypothetical online estimator has to supply its own rows and order, with handling for candidates that are absent from its roster.

Earlier directed verification granted both exact timing and signed CFO and bypassed the scout. Earlier same-lane brackets and orbit proposals coupled timing and CFO prediction. The half-grid timing experiment retained the ordinary 12-row carrier search and omitted 14 factors. The timing-only measurement here separates knowledge of the phase rows from frequency and verification and prices the active primary-only short callback separately. [Directed verification](directed-verifier.md) · [Earlier brackets](../single-core-2x/receiver-brackets.md) · [Half-grid search](receiver-polyphase-timing.md)

| Saved scope | Lane calls per repeat | Pinned CPU ms | Same-build control CPU ms | Exact minimum CPU ms | Four CPU ms | Eight CPU ms | Twelve CPU ms |
|---|---:|---:|---:|---:|---:|---:|---:|
| Weak, full 20 ms | 36 | 137.64 | 133.42 | 111.00 | 110.64 | 113.80 | 117.02 |
| Weak, short 12 ms | 36 | 44.35 | 41.14 | 31.08 | 31.18 | 32.86 | 34.52 |
| Dense, full 20 ms | 96 | 253.34 | 246.42 | 201.83 | 199.51 | 205.95 | 212.98 |
| Dense, short 12 ms | 96 | 100.54 | 93.66 | 66.94 | 66.99 | 71.14 | 75.56 |
| Dense, actual mixed schedule | 96 | 126.97 | 120.30 | 90.60 | 90.13 | 94.86 | 99.62 |

All six positions rotate across three paired repeats on the same saved waveform. Native timing excludes oracle capture and marshaling, as an ideal estimator would supply the rows directly. The rebuilt full and short objects train on deterministic pilot, overlapping-pilot and noise signals on both edges and signed mixer centers. The two pinned binaries relinked byte for byte. The rebuilt control uses different PGO feedback and was faster than the pinned binary by about 6.7 ms on the dense mixed prefix. The projection attributes savings to the within-build comparison. All ordered rank, epoch, CFO and score bytes matched at every aperture and repeat, and separate continuation histories also agreed. The forced full dense prefix had one causal selection. The active mixed publication chooses the highest verified margin per scheduled lane, which also follows from identical factor bytes. [Replay and native overlays](timing_only_oracle.py)

## How accurate and cheap the estimator must be

On the actual mixed dense prefix, 105 reached scouts required two, three and four distinct phase rows on 2, 46 and 57 scouts respectively. The 36 weak mixed lanes required 201 rows over 60 scouts. Every scout needs its own independent current row set, including signed residual scouts. The budget scales the paired aperture-specific CPU ratios to the older full dense recording's measured **12.635 CPU s** on 11,834 short calls and **4.716 CPU s** on 1,696 full calls. Ingress, solving and publication are outside the native savings. [Dense receipts](dense-full-short-raw.md)

| Supplied timing rows | Gross projected saving | Time for estimation and retries | Mean extra CPU allowance per lane |
|---|---:|---:|---:|
| Exact minimum | 4.46 s | 0.97 s | 72 µs |
| Four | 4.50 s | 1.01 s | 74 µs |
| Eight | 3.81 s | 0.32 s | 24 µs |
| Twelve | 3.08 s | Below the target by 0.41 s | 0 µs |

If an estimator can decide before paying for the scoped native call, the four-row arm needs about **78%** of lanes to take the fast path at zero estimator cost under uniform projected savings. If it speculatively runs the whole scoped native call first and retries full price on a bad result, an average-cost calculation allows about **5.8%** retries with zero estimator cost. For eight rows those thresholds tighten to **92%** preflight success or **1.9%** speculative retries. Actual retry prices depend on which lanes miss. Even a perfect symbol-clock phase modulo the 44-sample symbol would leave about 303 positions in the frame. Giving away all timing work while still evaluating twelve signed carrier rows already falls short of the current dense requirement. The phase cue needs additional discrimination within the frame to reach four or eight useful rows.

## Prior and peer timing

The causal check uses at most two prior measured factor sets on the same recording, antenna, pilot edge, RF center and capture generation within two seconds. It transfers each measured epoch using the hardware sample counter and the exact 40,000-thirds-of-a-sample frame wrap. A separate oracle grants the already-measured simultaneous peer antenna's factors to each lane for free. A width includes all quarter-rate cells within the stated native-sample radius. The union counts exactly covered original timing rows and the lanes with coverage of all raw and reached residual rows. The cost of ranking the broader window is outside the four-, eight- and twelve-row clocks.

| Dense active scope | Required rows retained | Fully covered lanes | Mean searched quarter-rate cells per lane |
|---|---:|---:|---:|
| Prior or peer, ±4 samples | 11 / 370 | 0 / 96 | 3.0 |
| Prior or peer, ±16 samples | 21 / 370 | 0 / 96 | 11.2 |
| Prior or peer, ±64 samples | 41 / 370 | 0 / 96 | 39.6 |
| Prior or peer, ±256 samples | 59 / 370 | 0 / 96 | 145.5 |
| Prior or peer, ±1,024 samples | 79 / 370 | 1 / 96 | 489.4 |

On dense, 49 lanes had a same-radio recent timing set and 44 had peer factors. Twenty-two had neither. The weak clips are sparse retrospective challenges, and none had same-radio donor data inside the tested two-second horizon. Granting the opposite antenna free timing at ±1,024 still covered only 63 of its 201 required rows and zero whole lanes. Counts concern equivalence of the original nominee rows. Some omitted nominations may lose eventual confirmation. They do not measure the accuracy of a new shortlist or how often a novel satellite would be recovered.

## Reproduce

From this checkout, use the original weak archive and existing authenticated first dense member. The run is limited to the 18 weak stereo clips and 48 dense stereo visits. It stops before position solving. Four tests cover tied row ordering, multi-visit wrap, exact scope boundaries and all-arm clock aggregation. The first result reducer exhausted a generator after the installed arm. The sealed receipt recomputes the aggregate clocks from the original retained per-lane units and requires no rerun.

```sh
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
tree=/home/mouse9911/gits/leo-tracker-reduxredux
private=/srv/bulk/leo-dev/leo-physical-stage-envelope-2j7mlwtt
dense="$private/fast8-auto-20261113-075937-d9ab96ee-1-lower-segment-00000000"
work=$(mktemp -d /dev/shm/leo-v3-timing-oracle.XXXXXX)
flock -x /tmp/leo-algo08v2-2x-bench/gauss.lock ionice -c2 -n7 nice -n15 taskset -c 2 \
  env TMPDIR=/dev/shm OMP_NUM_THREADS=1 OMP_THREAD_LIMIT=1 OPENBLAS_NUM_THREADS=1 \
  MKL_NUM_THREADS=1 BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 \
  PYTHONPATH="$PWD:$release/src:$release" timeout 65s "$release/venv/bin/python" -BPs \
  -m reports.ALGO08.v3.timing_only_oracle bench "$work/native" "$release/assets" \
  "$tree/reports/2026_11_20_single_scan_glrt/satellite-reference.zip" "$dense" > "$work/receipt.json"
```

The sealed corrected uncompressed receipt is `0caad917eec9e02f0d1a6fa0ad57b3323175e16a429ef18053f1add2e22d10f9`. The initial per-lane receipt is `/dev/shm/leo-v3-timing-oracle-native.json`, SHA-256 `92cf3b07824864b609186971a9568cbec34c40a4b7188a2656239c7f1b562507`.
