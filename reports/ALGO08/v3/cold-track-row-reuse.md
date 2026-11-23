# Reuse centred track rows in full-catalogue cold discovery

On the genuine DS30-0008 12 ms short-receiver packet with the installed graph, centre-track reuse reduced cold ranking from **4.744 to 4.237 CPU seconds**, a **10.7%** reduction. The complete cold stage including the released finalist race went from **6.190 to 5.697 CPU seconds**. Both runs used all 1,476 cold catalogue orbits. All seven ordered scores, 784 component/candidate-index/NORAD/signed-alias records and diagnostic row digests matched exactly. The original race picked branch one with the same score of 36,359.307477323084, same fitted phases, and the same 7.361709 km east, 7.854880 km south cold site. Its prefix scores, evaluations and routing also match the sealed genuine short crossover. [Frozen protocol](cold-track-row-reuse-protocol.md) · [Full paired receipt](measurements/cold-track-row-reuse.json.gz) · [Previously sealed crossover](dense-full-short-crossover.md)

| Operation | Released CPU s | Reuse CPU s |
|---|---:|---:|
| Scan context setup | 0.042 | 0.045 |
| Full cold rank | 4.744 | 4.237 |
| 16 associations within rank | 1.857 | 1.388 |
| 1,792 curve likelihoods within association | 0.863 | 0.887 |
| Sparse shifted predictions within association | 0.158 | 0.159 |
| Other association work including gathers | 0.836 | 0.342 |
| Nominal projection within rank | 0.548 | 0.548 |
| Discovery statistics within rank | 0.721 | 0.703 |
| Seed improvement within rank | 0.365 | 0.345 |
| Original finalist race after rank | 1.405 | 1.414 |
| Scan, rank and race elapsed s | 6.191 | 5.697 |

The original centre statistics already gathered the observed track times, scaled the nominal Doppler by the track RF and took the whole-track horizon minimum. The reuse passes the same binary64 F-order rows to the original association. When phases move, it copies the nominal table in the same layout and replaces each shifted satellite row with the released sparse projection at the track's measurement times. It updates only those rows of the horizon mask. The same likelihood still evaluates every row, computes the original signed aliases and keeps the original tie order. The candidate used the cached full-catalogue tables in 1,344 requests covering 86.7 million cells. It copied 637.8 MB across all these requests and updated 2.24 million shifted cells. The four corners used 448 ordinary gathers. Both arms used the same centre cache, with a 119.8 MB retained track-table peak. [Implementation](cold_track_row_reuse.py) · [Eleven component tests](../../../tests/pipeline_eval/test_cold_track_row_reuse.py)

The pair starts from the same 208 installed-graph tracks and 112 active curved tracks after one unchanged 25-probe fused geographic proof, charged at 3.690 CPU seconds. Each arm gets a fresh scan context. The candidate ran first. Both use the pinned installed shared-discovery and sparse rank contexts. The recovered score adapter exposes the original stable-sorted scores. Branch work ends before salvage and paired calibration. Subtracting the measured 0.506 s saving from the historical 25.566 s complete saved solve would amount to 2.0% if all downstream costs remained the same. This comparison times one saved cold pair, with no new acquisition, end-to-end solve clock, or assessment of geographic accuracy. [Pair runner](cold_track_row_trial.py) · [Earlier exact centre arithmetic](blind-rank.md) · [Earlier contrast bounds](full-family-amortized.md)

One completed attempt discarded its in-memory pair when the post-run graph and proof gate compared integer receiver keys with stored JSON string keys. The recovery checks the canonicalized proof before timing and writes each arm separately before comparison. Two setup attempts also stopped before ranking while binding the historic detector verifier and compiling the extracted association method. Only the authorized recovery yielded a measurable pair. The original source receipt SHA-256 is `25b66bc527d7e9ea69ee8c8158f6f85ff38b9f908bd05bc1b123077591a97844`. Source pins and the complete signed ranks are in the receipt.

## Reproduce

The original detector launch source lives in the archived crossover checkout. Pass its source verifier explicitly so it can check the genuine saved packet against the historical launcher sources. Reuse the existing read-only saved receipt and pass a new output path in a private directory. The driver places `.reused.json` and `.released.json` next to it.

```sh
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
payload=/opt/leo-algo08/algo08v3/payload
raw=/var/tmp/leo-full-short-dense-DS30-0008
original=/var/tmp/leo-v3-dense-full-short-crossover
out=$(mktemp -d /var/tmp/leo-cold-track-rows.XXXXXXXX)
flock -x /tmp/leo-algo08v2-2x-bench/gauss.lock ionice -c2 -n7 nice -n15 taskset -c 2 \
  env PYTHONPATH="$PWD/reports/ALGO08/v3:$payload:$PWD:$release/src:$release" \
  OMP_NUM_THREADS=1 OMP_THREAD_LIMIT=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 \
  "$release/venv/bin/python" -BPs reports/ALGO08/v3/cold_track_row_trial.py \
  "$raw/publication" "$raw/process.json" /var/tmp/leo-dense-short-pins.0zaX7eSH/geographic.so \
  /var/tmp/leo-v3-dense-full-short-crossover-results/replay.json \
  "$original/reports/ALGO08/v3/dense_full_short_crossover.py" "$out/pair.json"
```
