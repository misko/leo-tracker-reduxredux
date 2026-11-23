# The cumulative solver transfers to the saved India waveform

The current cumulative numerical route reduced single-core solver CPU by **32.6%** on the containing offer and **34.9%** on the omitted offer. It kept the valid fix and returned a false fix when the receiver was **1.500 km outside** the offered square, as named v3 did. It retained all **517 ordered owner and role rows per calibration arm**, and reproduced the earlier bare full-catalogue endpoints and RF RMS exactly. This is a retrospective result on one published simulated waveform with two offers. [Frozen protocol](india-cumulative-transfer-protocol.md) · [Scored summary](measurements/india-cumulative-transfer-summary.json) · [Verified solve receipts](measurements/india-cumulative-transfer.json.gz)

## Same detector evidence and original offers

The complete public India document has the earlier wide-GLRT detector signature and exactly matches the published waveform-derived detector bytes. It contains 2,400 candidate-probe rows, evenly split between two receivers, 1,200 delivery-clock records and the original ADC and UTC anchor. The signed public release also binds the original TrackConfig and 35 strictly causal TLE collections over 23 distinct payloads. Each worker verified those inputs against the published locks and loaded the archive from the existing `/tmp` tmpfs. The original named-v3 raw-bound manifest fields are absent from this older detector document. Both the installed named solver and the candidate consumed the complete unchanged document at the post-detector numerical boundary. [Original provenance and request IDs](india-saved-transfer.md) · [Earlier covariance comparison](../single-core-2x/covariance-geographic-transfer.md)

The two existing 25 km squares and their sky screens remain as published. Receiver truth is **3.576 km inside** one square and **1.500 km north of the north face** of the other. Both centers use the known simulated longitude. The same cumulative route ran on both offers and used the supplied region and its causal catalogue. Public truth entered only in the separate scoring process after the four solve receipts existed.

## Matched numerical results

Within each route and offer, both calibration arms use the same factors, candidate set, original search settings and solver grid budget. Each pair of error and RMS values is fixed-zero / fitted `c`.

| Offer and route | Decision | Horizontal error (km) | Solver RF RMS (Hz) | Solve CPU (s) | Solve elapsed (s) |
|---|---|---:|---:|---:|---:|
| Containing, named v3 | Valid fix | 1.017 / 0.751 | 15.53635 / 15.30584 | 5.602 | 5.603 |
| Containing, cumulative | Valid fix | 1.035 / 0.766 | 15.53854 / 15.30692 | 3.775 | 3.779 |
| Omitted, named v3 | False fix | 1.580 / 1.534 | 15.63058 / 15.45128 | 5.863 | 5.864 |
| Omitted, cumulative | False fix | 1.586 / 1.538 | 15.63135 / 15.45071 | 3.814 | 3.815 |

Combined CPU fell from **11.465 to 7.590 s**, a ratio of **0.662**. Cumulative horizontal error grew by **17.9 / 15.4 m** on the containing offer and **5.7 / 3.9 m** on the omission. Fitting `c) lowered RF RMS and horizontal error within each route on both offers. The cumulative fitted RMS on the omission is about **0.00057 Hz** lower than named v3 while its position error is about **3.9 m** higher. Neither calibration arm resolved the omitted region. [Exact coordinates and ownership comparisons](measurements/india-cumulative-transfer-summary.json)

Both named runs reproduced the previous signed India positions, RF RMS, owner rows, numerical grids, path and objective replay. Both candidate runs completed on the reconstructed signed fit without the installed fallback. They changed the path and grid digests against named v3 and kept exact objective replay with **179** complete grid points on the containing offer and **137** on the omission. The optimized Graph used 2,339 ordered edges and 24 tracks on both offers. Exact phase forecast was active in both runs. The checked native grid path made 356 and 272 selected design calls, and each offer recorded four exact projection parity checks. [Per-method and per-component receipts](measurements/india-cumulative-transfer.json.gz)

## Why the regional decision persists

The cumulative route checked the region before fitting, stopping at `inside_score` after 25 probes on the containing square and 26 on the omitted square. This cost 0.156 and 0.149 CPU seconds, respectively. The omitted endpoint also fired the normal signed boundary check, so the candidate paid for both 26-probe checks on that offer. Prepared catalogue reuse served both. The named omitted fit fired the ordinary boundary check once and reached the same 26-probe result. The earlier complete 96-point check showed an exterior best sample **3.125 km** beyond the north face on the omission. The shared released guard requires a **25 km** exterior clearance there. Earlier ordering leaves that criterion in force. [Complete probe evidence](india-regional-diagnostic.md) · [Early proof behavior](early-region.md)

The earlier bare full-catalogue fit with the separate prepared-catalogue handoff used **3.855 / 4.053 CPU s** for containing and omitted offers in its own session. The cumulative composition adds newer Graph, numerical preparation, early proof and grid work to those same endpoints. The fresh matched named-v3 clocks above establish the comparison in this session. Individual gains from the newer components and end-to-end acquisition, rendering and web performance were outside these clocks.

## Reproduction

Run from the research worktree with the installed v3 payload and the earlier pinned tmpfs India packet and four reviewed native libraries. The solve clock starts at the verified in-memory handoff and ends with paired numerical evidence. One early candidate attempt stopped in phase-forecast instrumentation because its audit list lacked initialization. The corrected candidate kept the frozen scientific settings, and the measured stock containing control was retained. The retained result has all four successful numerical receipts. Eighteen focused tests passed and Ruff found no diagnostics. [Driver](india_cumulative_transfer.py) · [Component tests](../../../tests/pipeline_eval/test_india_cumulative_transfer.py)

```sh
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
frozen=/opt/leo-algo08/algo08v3/payload
out=$(mktemp -d /dev/shm/leo-india-cumulative.XXXXXXXX)
script=reports/ALGO08/v3/india_cumulative_transfer.py
export OMP_NUM_THREADS=1 OMP_THREAD_LIMIT=1 OPENBLAS_NUM_THREADS=1
export MKL_NUM_THREADS=1 BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
export TMPDIR="$out"
locked() {
  flock -x /tmp/leo-algo08v2-2x-bench/gauss.lock nice -n 15 ionice -c 2 -n 7 taskset -c 2 "$@"
}
export PYTHONPATH="$PWD/reports/ALGO08/v3:$frozen:$release/src:$release:$PWD"
for pair in matched-tile:stock matched-tile:cumulative omitted-tile:cumulative omitted-tile:stock; do
  offer=${pair%:*}
  route=${pair#*:}
  locked timeout -s INT -k 3s 25s "$release/venv/bin/python" -BPs "$script" run "$offer" "$route" "$out/$offer-$route" || exit 1
done
export PYTHONPATH="$PWD/reports/ALGO08/v3:$PWD/src:$PWD:$release/src:$release"
locked "$release/venv/bin/python" -BPs "$script" score "$out" "$out/result.json.gz" "$out/summary.json"
```
