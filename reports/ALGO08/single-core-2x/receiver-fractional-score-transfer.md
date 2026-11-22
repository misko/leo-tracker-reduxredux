# Exact fractional score transfer across two saved prefixes

**Use the all-factor verifier for the next shared receiver composition.** It matched every deployed probe row on the dense lower-pilot and sparse upper-pilot prefixes. Selected-score repair cost 2.84% more acquisition CPU on the dense slice and 0.39% more on the sparse slice. The two-prefix summed CPU cost was 1.83% higher for selected-score repair across matched cycles. The all-factor verifier also removes the deferred repair state and evaluates the exact margins before candidate gating and continuation. [Timing and parity receipt](measurements/fractional-score-transfer.json)

The comparison uses the first 128 scheduled DS30-0008 visits with the lower pilot and the first 128 scheduled visits of the southern public simulation with the upper pilot. Each process authenticates the original manifest and decodes the prefix once. It then passes the memory-resident windows through four fresh instances per arm of the normal acquisition entry. Cyclic arm order balances startup and cache effects. The test stops before solving or publication.

All arms see the same authenticated IQ, capture-quality policy, clock records, lane metadata, and causal history. The two exact builds compare every published probe row with deployment. The spectral parent provides the CPU control, and its differences are counted by retained availability, carrier identity or gate, and continuous score. The DS30-0008 replay also checks the deployed and selected probe digests extracted from the existing full publications. The southern replay checks the archived deployed and spectral parent probe digests. The earlier DS30-0016 result is reused from its existing receipt. [Dense publication](measurements/DS30-0008-fractional-selected.json) · [Southern publication](measurements/spectral-terminal-south-inside.json) · [Earlier prefix and frozen receiver identities](receiver-fractional-absolute-score.md)

| Prefix | Probe rows | Retained ranks 0 / 1 | Deployed CPU | Spectral parent CPU | All-factor CPU | Selected-score CPU | Paired selected change from all-factor |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| DS30-0008, lower pilot | 256 | 78 / 6 | 1,900.32 ms | 619.02 ms | 701.10 ms | 718.28 ms | +2.84% |
| Southern simulation, upper pilot | 256 | 44 / 0 | 1,302.33 ms | 462.11 ms | 480.71 ms | 481.34 ms | +0.39% |
| DS30-0016, previous prefix | 232 | 52 / 1 | 1,548.70 ms | 511.74 ms | 576.48 ms | 584.98 ms | +0.42% |

The table lists medians for each arm and the median of matched CPU ratios for the final column. Selected-score repair was 0.85–4.06% slower on every dense repeat. The southern paired differences ranged from 1.37% faster to 1.09% slower. The southern timings support near parity on this prefix. The two new prefixes had zero quality exclusions. The earlier DS30-0016 prefix excluded 12 of its 128 visits.

| Prefix | Two-factor lanes | Pair-factor repairs | Retained single repairs | Already exact |
| --- | ---: | ---: | ---: | ---: |
| DS30-0008 | 80 | 152 | 33 | 9 |
| Southern simulation | 0 | 0 | 44 | 0 |
| DS30-0016, previous prefix | 41 | 79 | 30 | 3 |

The spectral parent preserved all selected ranks, signed CFOs, epochs, gates, and availability. Continuous scores differed in 80 retained DS30-0008 rows and all 44 southern retained rows. The largest absolute margin changes were 1.19 × 10⁻¹³ and 2.15 × 10⁻¹⁴, respectively. Both exact builds restored the deployed score bytes on every retained row. The timing comparisons cover acquisition on these saved prefixes. They do not establish a full-publication speedup or independent positioning accuracy.

## Reproduction

Run the two prefix commands consecutively under one available Gauss lock. The frozen launcher loads its checked private receiver bytes. The capture hook terminates at the acquisition boundary. The normal deployed library is `f37673f0…`, the spectral parent is `b63cf5b0…`, the all-factor exact library is `2258f592…`, and the selected-score library is `a5862937…`.

```bash
export ALGO_PREFIX_BENCH=/tmp/leo-algo08v2-2x-bench
export ALGO_PREFIX_SCRIPTS=/tmp/leo-algo08v2-2x/reports/ALGO08/single-core-2x
export ALGO_PREFIX_RELEASE=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
export ALGO_PREFIX_BUNDLE="$ALGO_PREFIX_BENCH/integration-fractional-absolute-selected-v3"
flock -n "$ALGO_PREFIX_BENCH/gauss.lock" ionice -c2 -n7 nice -n15 taskset -c 2 timeout 90s \
  bash -eu -c '
  prefix() {
    sudo -n -u leo -- env OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
      PYTHONDONTWRITEBYTECODE=1 \
      PYTHONPATH="$ALGO_PREFIX_BUNDLE:$ALGO_PREFIX_RELEASE/src:$ALGO_PREFIX_RELEASE" \
      "$ALGO_PREFIX_RELEASE/venv/bin/python" -BPs \
      "$ALGO_PREFIX_SCRIPTS/receiver_fractional_selection_trial.py" \
      "$ALGO_PREFIX_BUNDLE" "$ALGO_PREFIX_BENCH/integration-spectral-vectors-wrapped-longitude" \
      "$ALGO_PREFIX_BENCH/integration-fractional-absolute-all" "$2" /srv/bulk --case "$1"
  }
  prefix DS30-0008 /srv/bulk/leo-dev/ds30-full-20261121/bindings/DS30-0008.json
  prefix public-south /tmp/leo-regional-qZJKBw4W/public/panel.json
  '
```
