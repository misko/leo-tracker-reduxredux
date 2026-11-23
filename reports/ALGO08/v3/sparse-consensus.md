# Position fixes after paying for every third stereo visit

On DS30-0016, allowing eight seconds of future verified RF evidence recovered 135 selections from paid visits. The original continuation on the same visits selected six. The downstream solver still failed to produce a fix. On the southern simulation the sparse selector returned zero factors in either region offer. The matched complete receiver selection produced fixes on both containing cases. The frozen accuracy and fix gates stopped this route before a raw replay. [Protocol](sparse-consensus-protocol.md) · [Scored results](measurements/sparse-consensus-summary.json)

| Input | Paid antenna lanes | Archived CPU for all / paid native calls | Complete / sparse causal / sparse buffered selections | Matched complete outcome | Sparse buffered outcome |
|---|---:|---:|---:|---|---|
| DS30-0016, containing | 476/1,426 | 4.631 / 1.505 s | 440 / 6 / 135 | Fixed. Errors 1.644 / 1.661 km | Solver error, empty observation mask during cavity nomination |
| Southern simulation, containing | 800/2,400 | 6.357 / 2.128 s | 456 / 0 / 0 | Fixed. Errors 0.817 / 1.101 km | Withheld for lack of curvature |
| Same southern recording, displaced offer | 800/2,400 | 6.357 / 2.128 s | 456 / 0 / 0 | Both receivers supported an exterior position | Withheld for lack of curvature |

Errors are horizontal, in fixed-zero / fitted calibration order. On the complete physical recording the RF RMS was 109.375 / 109.479 Hz, and on the southern containing offer it was 6.502 / 6.392 Hz. The buffered route produced no fitted coordinates or comparable RF residuals. Its empty-support withholding on the displaced offer provided no geographic discrimination because it withheld on the containing offer as well. [Per-arm evidence and solver receipts](measurements/sparse-consensus-summary.json.gz)

The two pre-continuation ledgers came from an earlier archived two-scan receiver. Both arms used the same original waveform factors, offer, causal orbit archive and cold signed solver configuration. Sparse inference admitted verified alternative carriers only from its paid visits, before satellite association. Paid native CPU sums the original per-lane clocks. The archived complete acquisition used 6.592 and 9.422 CPU seconds respectively. File I/O, publication and full-service elapsed savings were unmeasured. The sparse selection itself took 2.7 ms on DS30-0016 and 0.8 ms on the southern recording. These numbers come from one replay each. [Input binding and selector](sparse_consensus_trial.py) · [Frozen voting rule](sparse_consensus.py)

## Reproduce

Run in the research checkout on Gauss with an empty output directory. The scoring step opens the references only after all six receipts exist.

```sh
out=$(mktemp -d)
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
payload=/opt/leo-algo08/algo08v3/payload
locked() {
  flock -x /tmp/leo-algo08v2-2x-bench/gauss.lock ionice -c2 -n7 nice -n15 taskset -c 2 \
    env OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 \
    "$@"
}
for c in DS30-0016 south-containing south-far; do
  for m in complete buffered; do
    locked env PYTHONPATH="$PWD/reports/ALGO08/v3:$payload:$release/src:$release:$PWD" \
      "$release/venv/bin/python" -BPs reports/ALGO08/v3/sparse_consensus_trial.py "$c" "$m" "$out/$c-$m.json"
  done
done
locked env PYTHONPATH="$PWD/reports/ALGO08/v3:$PWD:$PWD/src" \
  /home/mouse9911/gits/leo-tracker-reduxredux/.venv/bin/python -BPs \
  reports/ALGO08/v3/sparse_consensus_score.py "$out" "$out/summary.json"
```
