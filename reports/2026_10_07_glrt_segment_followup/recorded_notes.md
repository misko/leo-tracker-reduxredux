# Recorded segment follow-up

The bounded replay completed 48 receiver cases and 192 planted-signal controls.
Short segments recover one additional phase-wandering pilot in the strongest
holdout injection cell (4/8 versus 3/8). These small descriptive counts do not
establish better RF detection. Positive exact-minus-control evidence in a later
window also occurs for every strong wrong-pattern injection, so that sign alone
is insufficient for specificity. Method selection belongs to the separate
prespecified simulation development experiment, not these holdout results.

## Frozen design

The cohort uses the fifth and sixth real visits by visit index per rate/split in
the existing DS5 server-evaluation manifest: 24 visits, both RX, 48 receiver cases.
These visits differ from the first follow-up's first/second scored visits and
third/fourth covariance-training visits. They remain adjacent visits from the
same existing dataset and sessions, not a new external validation population.
Development, validation, and holdout scoring sessions remain disjoint. Every
input NPY hash, dtype, and shape is checked by the previous read-only helper.

Production `acquire_symbolwise` acquires eight common candidates from 0–20 ms.
It runs once per raw/injected case. Exact and built-in roll17 control correlations
are extracted at each retained timing/CFO for symbols 2..257. Only complete
256-symbol frames are retained; the same frame rows are used for every N64/128/256
comparison. This deliberately gives a matched-frame current64 baseline rather
than allowing it additional partially supported frames. The N comparisons add
pilot samples: increasing N is not a pure segmentation change.

Every segment length uses every symbol within its N: lengths 8/16/32/64,
exponential lag kernels 8/16/32, and a full coherent Gaussian comparison. Actual
exact/control template energies enter the likelihood normalization. Current
coherent margin preserves the raw baseline's coherent ceiling. All 17 primary
and margin-diagnostic statistics use the same 512-bin frequency grid and data.

Each method selects its first-window candidate and total CFO. The later 40–60 ms
window is scored at that same timing and total CFO, with exact/control evaluated
at one identical fixed frequency. It does not reacquire timing or maximize
frequency/control frequency again. Per-window rankings and fixed later scores
are retained. Natural-statistic and margin variants both remain prespecified;
this report does not select the holdout winner among them.

## Known planted-signal recovery

Injection backgrounds are the first selected fifth visit per rate for development
and holdout, both RX: eight backgrounds per split. Each background receives exact
Qin and unseen roll29 patterns at -30/-24/-18 dB integrated injected-IQ power
relative to original IQ power, with phase-increment sigma 0/.35 rad. This gives
192 matched trials. The phase process uses IID Gaussian increments accumulated
within each frame, resetting with independent uniform frame phase. The nominal
carrier is 57 kHz and epoch 137 samples. Phase paths/seeds and all settings are
frozen; the same injected amplitude is used in the separate later window.

Known recovery means timing within one symbol (4.4 us) and absolute total CFO within
5 kHz of the nominal planted carrier. Phase-walk CFO error is measured relative
to that carrier, not to an estimated incidental phase slope. None of the original
RF recordings are assigned positive/negative truth; they may contain strong
existing transmissions competing with the planted signal. No detection threshold
or RF false-alarm rate is estimated from the sparse unlabeled backgrounds.

| Holdout exact injection | Planted timing plus representable CFO in bank | Current64 winner recovery | Segment8 winner recovery N64/128/256 | Segment16 winner recovery N64/128/256 |
|---|---:|---:|---:|---:|
| sigma0, -30 dB | 2/8 | 0/8 | 0/0/0 of8 | 0/0/0 of8 |
| sigma0, -24 dB | 2/8 | 0/8 | 0/0/0 of8 | 0/0/0 of8 |
| sigma0, -18 dB | 7/8 | 4/8 | 4/4/4 of8 | 4/4/4 of8 |
| sigma.35, -30 dB | 2/8 | 0/8 | 0/0/0 of8 | 0/0/0 of8 |
| sigma.35, -24 dB | 2/8 | 0/8 | 0/0/0 of8 | 0/0/0 of8 |
| sigma.35, -18 dB | 7/8 | 3/8 | 4/4/4 of8 | 4/4/4 of8 |

In the last cell, Gaussian coherent, segment32/64, and kernels16/32 recover 3/8
at every N. Kernel8 recovers 3/8, 4/8, 3/8 for N64/128/256. The one additional
segment8/16 recovery at N64 is holdout 7.5 MS/s RX0: current chooses an alias at
-511.8 kHz, while these segment scorers select the planted candidate near 58 kHz.
Every primary method recovers 4/8 in the coherent sigma 0, -18 dB cell. Development
exact recovery is 0/8 for -30/-24 dB and 4/8 or 5/8 for -18 dB sigma 0/.35 respectively,
for every primary method and N. There is no robust recorded ranking advantage
established here.

The bank ceiling is calculated without method scores: a candidate has planted
timing and its seed-plus-FFT grid can represent the nominal 57 kHz within 5 kHz.
This allows residual CFO refinement; merely requiring seed CFO within 5 kHz would
understate the available bank. Results also retain timing-only survival,
seed timing/CFO survival, and per-method oracle recovery among all retained
candidate estimates. Upstream misses and wrong top-one ranking are distinct.

## Wrong-pattern and unmodified-window checks

At -18 dB, every primary N64 method has a positive later-window exact-minus-control
margin on 8/8 roll29 holdout trials, for both phase settings. Recovery of the
wrong pattern's nominal epoch/CFO is 0/8 for every method/N. Existing unknown RF
signals and timing-shift ambiguities can contribute to the positive margins;
these outcomes cannot be called a measured RF false-alarm rate. They do show
that positive fixed-frequency confirmation alone fails this wrong-pattern stress.
Full exact/control scores and the chosen timing/CFO make this limitation auditable.

On the unmodified holdout windows, positive later margins at N64 occur12/16 for
current and coherent Gaussian, 13/16 for segment8, 12/16 for segments16/32/64,
and 11/16 for all kernels. These are unknown-truth descriptive evidence counts,
not detection recall. The 256-symbol comparison changes both data quantity and
coherent model adequacy; no localization or calibrated improvement follows.

An additional cheap read-only replay of the previous production matrices covers
96 windows and 768 candidates at N64. Baseline scores reproduce exactly (maximum
error 0.0); scoring takes 1.047 CPU seconds. Holdout winner agreement with the
current scorer is 12/32 for segment8, 15/32 segment16, 17/32 segment32, 24/32 segment64,
and 18/23/26 of 32 for kernels8/16/32. This measures ranking changes on previously
analyzed observations, not additional validation data.

## Reproduction and artifacts

Runtime-only preflight on a development 10 MS/s injection took 0.541 CPU seconds,
including 0.489 acquisition and 0.027 all-method scoring/confirmation. No score
outcomes were inspected to change settings. The final run took 76.424 seconds
wall, 58.084 acquisition CPU, 9.054 extraction CPU, and 5.523 combined scoring CPU.
These are aggregate single-run costs, not per-method speed or tail latency.

```bash
.venv/bin/python reports/2026_10_07_glrt_segment_followup/recorded_segments.py freeze
env OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 timeout 240 .venv/bin/python reports/2026_10_07_glrt_segment_followup/recorded_segments.py run
.venv/bin/python -m pytest reports/2026_10_07_glrt_segment_followup/test_recorded_segments.py -q
.venv/bin/python -m ruff check reports/2026_10_07_glrt_segment_followup/recorded_segments.py reports/2026_10_07_glrt_segment_followup/test_recorded_segments.py
```

`recorded/selection.json` freezes cohort, acquisition parameters, and injection
settings; `provenance.json` records source/native-binary hashes and single-thread
environment. `results.json` contains all raw/injected banks, 17-method rankings,
known recovery diagnostics, and fixed later confirmation. `matrices.npz` caches
the raw256-symbol matrices for both windows. Injection matrices are reproducible
from the saved input hashes, deterministic seeds, amplitude scales, and source.
`prior_cached_comparison.json` contains the separately hashed prior-cache replay.
`preflight.json` and `run.log` retain bounded-run evidence.

The final methods source SHA256 is
`06c341391596c60dc885a5fafdcd4c169614dfe96a3492fff77c2f84fd2a7b33`.
Six component tests and Ruff pass. Tests cover separate deterministic cohorts,
session leakage, nonoverlapping window geometry, actual template energies,
shared banks/frozen later frequency, deterministic injection power/patterns,
matched nested support, and scale invariance. Source hashes are checked again
before results are written. Earlier reports and production files remain untouched.
