# Disjoint trailing pilot confirmation

On the first 64 signed visits of public North, one fixed check on five trailing pilot frames rejected **23 of 46** short hypotheses without a named-v3 selection match and retained **12 of 12** shared matches. It kept **26 of 27** matches to the strongest real 20 ms factor on the physical weak clips. The predeclared screen passed at the boundary for North rejection. The broader weak comparison kept **30 of 32** matches to any real 20 ms factor. Both removed weak factors came from one physical stereo visit. Checking every positive adds about **1.4 dense CPU seconds** at the observed per-positive cost. [Frozen protocol](tail-confirm-protocol.md) · [Receipt and signed lane rows](measurements/tail-confirm.json.gz)

## Enrollment and signed decisions

The North panel covered both radios on the first complete resident tmpfs member of the public simulation. Every one of the 128 scheduled stock-short lane tuples, including empty results and 16 scheduled 20 ms anchor calls, agreed byte-for-byte with its sealed original mixed receiver probe. The 112 nonanchor lanes enrolled 58 short positives. The physical panel covered 18 previously saved DS26 weak challenge clips, with 34 short positives across 36 stereo lane opportunities. Matched original DS30 weak waveform was unavailable. The clips were passively resident and verified by archive and clip digest. No physical archive recordings were read and measured process storage input was zero. [Input and factor pins](measurements/tail-confirm.json.gz)

The short result used its measured integer epoch, fractional epoch and final signed CFO. A comparison counted as shared within two wrapped samples and 250 Hz of signed CFO. Raw 20 ms outputs here are diagnostic calls on the same samples. The named-v3 comparison uses the pre-existing selected probe packet, whose per-lane admission differs. The two columns report retained over original short hypotheses in each cohort. The North and weak short positives included 20 negative and 38 positive CFOs, and 18 negative and 16 positive CFOs, respectively.

| Panel and reference | Radio | Shared retained | Short-only retained | Full-only lanes | Both empty |
|---|---|---:|---:|---:|---:|
| North named-v3 selection | Both | 12/12 | 23/46 | 0 | 54 |
| North named-v3 selection | 0 | 6/6 | 10/22 | 0 | 28 |
| North named-v3 selection | 1 | 6/6 | 13/24 | 0 | 26 |
| North raw 20 ms selected or any | Both | 25/25 | 10/33 | 6 | 48 |
| North raw 20 ms selected or any | 0 | 13/13 | 3/15 | 5 | 23 |
| North raw 20 ms selected or any | 1 | 12/12 | 7/18 | 1 | 25 |
| DS26 weak raw 20 ms selected | Both | 26/27 | 6/7 | 2 | 0 |
| DS26 weak raw 20 ms selected | 0 | 13/13 | 4/5 | 0 | 0 |
| DS26 weak raw 20 ms selected | 1 | 13/14 | 2/2 | 2 | 0 |
| DS26 weak raw 20 ms any | Both | 30/32 | 2/2 | 2 | 0 |
| DS26 weak raw 20 ms any | 0 | 16/17 | 1/1 | 0 | 0 |
| DS26 weak raw 20 ms any | 1 | 14/15 | 1/1 | 2 | 0 |

Short-only includes nine North hypotheses with a different raw 20 ms output on that same lane and seven weak hypotheses with a different strongest raw 20 ms output. On rejected stereo clip `DS26-0162-v1534-rx0`, receiver 0 matched a released factor near −307.5 kHz with a tail margin of −0.00183. Receiver 1 matched the highest-margin released factor near +369.1 kHz and had a tail margin of −0.00774. The gate withholds carriers that are unsupported in the tail even when the full visit supports them. Named and raw 20 ms matches are comparison evidence. This single member does not establish rejection across all 622 surplus North factors or effects on localization. [Earlier North findings](north-causal-transfer.md)

## Independence and controls

At 10 MS/s each frame uses the stock rounded origin `epoch + (40000 * frame + 1) / 3` with integer division. The selected 64-symbol verification block and its 16 fractional taps across frame indices 9–13 can read native indices 120079 through 189577 inclusive over the entire admitted epoch and offset domain. The helper copies up to 40 guard samples on either side, leaving every potential trailing input disjoint from the short receiver's first 120000 samples. It uses one fixed interpolation offset and the original signed rotation for each origin. Per-frame powers preserve independence under unknown inter-frame phase. The numerator and per-template ceiling compute the original GLRT at zero residual in real arithmetic. The direct evaluation skips the FFT bank and can round differently. [Native helper](tail_confirm.inc)

Both signed radios on each pilot edge passed the persistent and late-carrier checks, four lanes each. All four early-only lanes had verified short hypotheses and failed trailing verification. Tail-only carriers showed up in the original raw 20 ms outputs on all four lanes and produced no short nominations. Silence and noise-only made no short or full output on all eight lanes. Poisoning outside the fixed trailing span produced exactly the same tail scores for each nominated control. Zeroing the trailing samples left all original short tuples unchanged and returned exactly zero for both tail templates on integer and fractional paths. The rolled-waveform controls retained all four shifted-epoch hypotheses, which both original receivers also found. The gate measures independent support for the nominated phase and frequency. A systematic shifted-epoch match can persist across both apertures.

The earlier local pilot readout reused different symbols within the original frame support and estimated a new residual. Distributed aperture used late samples when choosing the hypothesis. Coherent block nomination used a smaller candidate proposal and paid the complete original verification. This trial keeps late samples out of nomination, uses the already chosen signed coordinates and pays only their fixed score. [Scout readout](scout-readout.md) · [Distributed aperture](distributed-aperture.md)

## Paid receiver cost

Four alternating-order passes timed all lane calls, factor extraction and the threshold wrapper. North kept both radios on all 64 visits and charged the scheduled anchors in each arm. The diagnostic full calls ran once and were charged separately at 269.308 ms CPU / 269.401 ms elapsed for North and 137.547 / 137.605 ms for weak. The table reports medians over repeated arms.

| Panel | 12 ms schedule CPU / elapsed | Schedule plus tail CPU / elapsed | Paired marginal CPU | Mean tail CPU per positive |
|---|---:|---:|---:|---:|
| North, 58/112 short positives | 142.713 / 142.743 ms | 155.098 / 155.108 ms | +12.176 ms | 218.2 µs |
| Weak, 34/36 short positives | 43.495 / 43.503 ms | 50.904 / 50.927 ms | +7.386 ms | 216.2 µs |

Intake took 385.8 ms CPU / 387.0 ms elapsed, including the North decoder and 84,305,903 logical tmpfs descriptor bytes. Native context and pilot setup were 442.3 ms CPU / 442.3 ms elapsed. Helper compilation elapsed 327.4 ms in a separate step. The extra tail work projects to **1.379–1.392 CPU seconds** at the previously observed 6,380 of 11,834 dense short positives. The projection excludes solver effects and storage waits. The new check always adds CPU when a factor is present. There is no measured offsetting reduction in downstream time. No sparse sentinel or position run was performed. [Dense positive workload](anchor-exposure.md)

## Reproduce

The receipt contains exact factor tuples, held scores, sample counters and digests, before/after passive residency, all repetitions and the compiled helper pins. Uncompressed receipt SHA-256 `5d99221d07c3dd8d121f2cdbf924aa9250b3d633b091cb49a3ac5197ade6b295`. Four focused tests passed.

```sh
bench=/tmp/leo-algo08v2-2x-bench
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
payload=/opt/leo-algo08/algo08v3/payload
tree=/home/mouse9911/gits/leo-tracker-reduxredux
low() {
  flock -x -w 90 "$bench/gauss.lock" ionice -c2 -n7 nice -n15 taskset -c 2 timeout -k 4s 50s \
    env OMP_NUM_THREADS=1 OMP_THREAD_LIMIT=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
    BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH="$PWD/reports/ALGO08/v3:$PWD:$release/src:$release:$payload" "$@"
}
low "$release/venv/bin/python" -BPs -m reports.ALGO08.v3.tail_confirm /var/tmp/leo-tail-confirm-new > /var/tmp/leo-tail-confirm-new.json
low "$tree/.venv/bin/python" -BPs -m pytest -q tests/pipeline_eval/test_tail_confirm.py
```
