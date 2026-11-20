# Exact geometry after ordinary IQ-derived GLRT

On the same fresh anonymous tracks and fitter packets, the exact geometry solver and the original robust EM each issued four fixes on six recordings. The median error among those matched fixes improved from 1.540 to 1.124 km with `c = 0`, and from 1.666 to 0.996 km with fitted `c`. The improvement was concentrated in DS26-0036. Both methods withheld DS29-0082 and DS29-0247. Six new lean fits reproduced their previous results exactly. [Protocol](PROTOCOL.md) · [Exact geometry positions](positions.jsonl.gz) · [Matched lean controls](control-positions.jsonl.gz) · [Prediction seal](prediction-lock.json)

| Recording | Lean robust EM error | Exact geometry error | Ordinary GLRT + v5 error |
|---|---:|---:|---:|
| DS26-0036 | 1.843 / 2.369 km | 0.881 / 0.431 km | 0.231 / 0.186 km |
| DS26-0122 | 2.206 / 2.209 km | 2.750 / 2.745 km | 1.254 / 1.254 km |
| DS26-0237 | 0.524 / 0.790 km | 0.439 / 0.732 km | 0.896 / 0.821 km |
| DS29-0082 | Withheld, guess 2.115 / 1.713 km | Withheld, guess 1.337 / 0.914 km | 2.802 / 2.662 km |
| DS29-0174 | 1.237 / 1.122 km | 1.367 / 1.261 km | 1.159 / 1.225 km |
| DS29-0247 | Withheld, guess 9.564 / 9.551 km | Withheld, guess 9.649 / 9.560 km | 0.711 / 0.980 km |

Each pair gives `c = 0` / fitted `c`. The exact fit improved two matched fixes and worsened two in both calibration arms. Conditional Doppler RMS improved on three of six recordings in each arm, including withheld DS29-0082. Fitting `c` reduced exact geometry's RMS on all six and lowered error on three of four issued fixes. The file records each arm's frequency score and the corresponding error for the capture-era v5 reference. [Per-recording scores](scores.csv) · [Error distributions](summary.json)

Both new methods rebuilt the tracks from ordinary native GLRT factors. They saw the same anonymous measurements, clock authority, causal TLEs and original 25 km tile. The exact native, observation and fitter-packet hashes match the prior lean ordinary fit for all six. For DS26-0036 and DS29-0082, the inputs come from successful whole-IQ archive replays independently completed earlier in this session. Those factors are byte-identical to the published ordinary archive. The four remaining inputs come directly from their qualified complete ordinary artifacts. The exact geometry comparison reused those detector factors and ran fresh tracking and both fitters. [Earlier independent raw-IQ proof](../../2026_11_19_short_receiver/raw-robust/README.md)

Pinned tracker replay including decode, authority checks and packet preparation took a median 1.77 s. Median fit time was 1.96 s for exact geometry and 1.91 s for lean robust EM. The fit processes peaked at 154,908 KiB and 154,816 KiB respectively. The original v5 comparators remain external to the numerical worker. [Qualification runner](../../../tools/pipeline_eval/qualification/raw_orbit_fit.py) · [Packet binding tests](../../../tests/pipeline_eval/test_raw_orbit_fit.py)

```sh
env OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  taskset -c 0-3 .venv/bin/python -B -m tools.pipeline_eval.qualification.raw_orbit_fit \
  --upstream /tmp/raw-robust-fresh --work /tmp/raw-orbit-fit-work \
  --out /tmp/raw-orbit-fit-report --cpus 0 1 2 3
```

The upstream directory is the `--fresh` output of the linked raw-robust reproduction. The runner verifies the published ordinary lean packet and the locked exact geometry sources before it launches either fitter.
