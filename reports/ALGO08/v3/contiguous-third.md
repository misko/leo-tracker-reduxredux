# Localization from the first third of stereo visits

The fixed first-third schedule failed the position screen on both containing offers. On dense DS30-0008 it cut saved solver and grid CPU from 38.271 s with full signed-enabled data to 11.176 s, while adding **3.059 km** horizontal error for (c=0) and **2.755 km** for fitted (c). The southern containing fix added 1.394 and 1.733 km. Both cutoffs qualified for the signed correction and completed the standard numerical evidence. The original exterior check withheld the displaced southern offer. [Frozen protocol](contiguous-third-protocol.md) · [Numerical summary](measurements/contiguous-third-summary.json) · [Sealed run and score receipts](measurements/contiguous-third.json.gz)

## Measured outcomes

| Offer and saved packet | Solver and grid CPU (s) | Saved handoff to publication elapsed (s) | (c=0) error (km) | Fitted (c) error (km) | (c=0) RF RMS (Hz) | Fitted (c) RF RMS (Hz) |
|---|---:|---:|---:|---:|---:|---:|
| Dense, full stock | 53.964 | 57.161 | 1.639 | 1.512 | 129.703 | 129.663 |
| Dense, full signed-enabled | 38.271 | 41.526 | 1.086 | 1.080 | 128.821 | 128.753 |
| Dense, first third signed-enabled | 11.176 | 13.365 | 4.146 | 3.835 | 131.365 | 131.283 |
| South containing, full stock | 4.407 | 6.142 | 0.817 | 1.101 | 6.502 | 6.392 |
| South containing, full signed-enabled | 3.884 | 5.593 | 0.817 | 1.101 | 6.502 | 6.392 |
| South containing, first third signed-enabled | 4.915 | 6.497 | 2.211 | 2.834 | 6.200 | 6.167 |
| South displaced, full stock | 6.271 | 6.385 | Withheld | Withheld | — | — |
| South displaced, full signed-enabled | 6.704 | 6.829 | Withheld | Withheld | — | — |
| South displaced, first third signed-enabled | 4.899 | 5.006 | Withheld | Withheld | — | — |

The fresh installed-v3 controls matched their archived positions, RF fits, owner digests, orbit policy, and scientific path and grid digests. All six returns produced a complete grid, with 179 evaluations per dense return and 137 per southern return. Both calibration arms replayed the endpoint objective with zero discrepancy. Each returned publication emitted and independently decoded eight PNGs. Each displaced publication withheld for `both_receivers_support_far_exterior`. All signed-enabled paths qualified and used the correction. The receipt shows zero fallback calls.

| CPU component (s) | Dense signed full | Dense signed first third | South containing signed full | South containing signed first third | South displaced signed full | South displaced signed first third |
|---|---:|---:|---:|---:|---:|---:|
| Joint proposal through ordinary finish | 25.966 | 6.888 | 1.236 | 0.947 | 1.616 | 1.038 |
| Signed qualification and finish | 2.254 | 0.452 | 0.180 | 0.146 | 0.172 | 0.147 |
| Exterior check | <0.001 | <0.001 | <0.001 | 1.682 | 2.895 | 1.884 |
| Standard numerical evidence | 6.424 | 1.349 | 0.435 | 0.187 | — | — |

On the southern containing offer, the prefix fit triggered 1.682 s of exterior probing. The full route stayed inside the guard threshold. That check more than offset the savings in proposal and numerical evidence, while still letting the inaccurate prefix fix publish. Dense discovery dropped from 13.950 to 2.899 CPU s and salvage from 5.043 to 1.613 s. Dense solver CPU was 4.83× faster than installed v3 and 3.42× faster than signed full. These clocks begin with saved input and include the solver's normal evidence. The portion outside the substage table includes input preparation and other solve work. The publication clock additionally covers the normal terminal and rendering boundary.

## Evidence removed by the cutoff

| Capture | Scheduled total → prefix | Quality-admitted stereo total → prefix | Selected factors full → prefix | Last prepared track point full → prefix |
|---|---:|---:|---:|---:|
| DS30-0008 | 6,772 → 2,257 | 6,765 → 2,253 | 7,016 → 2,451 | 299.817 → 99.907 s |
| South, same packet for both offers | 1,200 → 400 | 1,200 → 400 | 456 → 152 | 296.230 → 96.318 s |

The cutoff counts scheduled visits, including visits that failed acquisition quality. DS30-0008 had four such visits before the cutoff. A separate receiver projection defines its budget as one third of admitted visits. That gives 2,255 admitted stereo pairs and extends through global visit 2,258. This test stopped before global visit 2,257 and kept 2,253 admitted pairs. The southern definitions coincide.

Per arm, the dense prefix published 1,363 owners versus 4,440 for signed full and 4,472 for stock. It shared 1,302 owner observations with each full route. All 1,302 kept their satellite, and 13 switched between conditional and predictive roles. Compared with signed full, the prefix lost 3,138 selected observations and added 61 previously unselected observations that came from within the cutoff. The southern prefix kept 114 of 266 published owners, with no role or satellite changes among retained observations. Dense track inventory fell from 236 to 79 and the southern inventory from 30 to 8. The owner agreement and the lower southern RF residual coexist with materially worse positions, consistent with too little time and track support. A successful grid and the original guard did not catch either accuracy regression. Even a hypothetical perfect quality trigger would have to run the omitted receiver searches and solve again on both containing cases.

The earlier separated-quarter route kept the first and last quarters, with paid continuation warm-up before the last arc. It preserved a longer time span but lost a physical fix and worsened another by over 4 km. The interleaved masks spread omissions across the entire aperture and required new causal selections at retained visits if skipped visits would otherwise contribute selector history. This contiguous prefix carries forward the exact original winner on every admitted prefix visit because its released continuation reads only earlier factors. Later rows keep their measured metadata and have empty candidate arrays in the derived analysis packet. The raw capture authority and full inventory remain bound. [Separated quarters](../single-core-2x/channel-schedules.md) · [Interleaving](aperture.md)

## Streaming boundary

The origin is the midpoint of the original first hardware UTC bracket. The bracket's early edge is the TLE and phase-history cutoff, and all checked catalogue, source and validation times precede it. The dense full and cutoff runs used the same 1,476 initial satellite candidates and 7,769 pre-origin phase transitions. Event time is the counter relative to the opening bracket with the probe midpoint offset. Graph and event fits receive only admitted winning factors and their derived tracks. The sky bank propagates causal elements over at least 300 seconds, so its future states are predictions from pre-origin elements. The initially recorded bracket and visit counters suffice to define event times before the recording ends. [Frequency adapter](../../../src/leo/analysis/glrt_frequency_input.py) · [Causal orbit and phase inputs](../../../src/leo/operations/localization_v3_inputs.py)

The installed input adapter still validates every delivery clock for steps and derives its reported duration from the original last sample counter. Exactly one third also needs a known scheduled visit count or sealed inventory. This replay has those data for the whole record. A live implementation could start speculative work from the opening anchor and a known planned cutoff, then would need to check actual count, all later clock receipts and waveform hashes through seal before publication. Early waveform verification termination would change the required capture authority. The detector-call savings here are schedule counts. Raw traversal, hashing, cancellation CPU and end-to-end latency were outside the measurement.

## Reproduce

Run from the repository root with read access to the pinned ALGO08v3 release, the two capture inventories, and their saved detector and TLE evidence. Use a new writable `out` directory. The score command reads the reference only after all three runs have sealed their evidence.

```bash
runner=reports/ALGO08/v3/contiguous_third.py
python=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c/venv/bin/python
out=$(mktemp -d /var/tmp/contiguous-third.XXXXXXXX)
gauss() {
  flock -x /tmp/leo-algo08v2-2x-bench/gauss.lock \
    ionice -c2 -n7 nice -n15 taskset -c 2 timeout 300s \
    env PYTHONPATH="$PWD/reports/ALGO08/v3:$PWD:$PWD/src" OMP_NUM_THREADS=1 \
    OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 "$@"
}
for case in DS30-0008 south-containing south-far; do
  gauss "$python" -BPs "$runner" run "$case" "$out/$case" || exit
done
gauss "$python" -BPs "$runner" score "$out" "$out/receipt.json.gz" "$out/summary.json"
```
