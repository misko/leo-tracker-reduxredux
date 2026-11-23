# Graph time proof transfers on the remaining 124-visit DS30 recording

The proof-enabled candidate completed warm acquisition through publication and exit in **0.921 s** on DS30-0102. Named ALGO08v3 took **2.136 s**. Both exited successfully and withheld for `no_active_curvature`. The candidate-to-named elapsed ratio was **0.431**, or **2.32×** on this pair. [Machine receipt and pre-score seal](measurements/short-time-proof-0102.json.gz)

## Prospective original-data pair

The signed 455-recording inventory has two entries with 64–127 issued visits. DS30-0180, at 92 visits, supplied the development result. DS30-0102, at 124 visits, was the only remaining entry. Enrollment used issued counts and authenticated the selected binding at `27af68985485eb20861757291452ed9210c3be906831bd729808fb212ab3e7b6` before either process started. The candidate went first with `--prove-empty-graph --one-pass-web-png --prove-graph-time-support`. Both processes used the original operator offer bytes, the same input and causal cutoff, one pinned Gauss CPU, nice 15, and best-effort I/O priority 7. [Development case](short-time-proof-0180.md) · [Shared launcher and scorer](short_raw_0180.py)

| Complete warm process | Proof-enabled candidate | Named ALGO08v3 |
| --- | ---: | ---: |
| Wall to exit, s | 0.921074 | 2.136125 |
| CPU to exit, s | 0.918933 | 2.134586 |
| Issued / admitted stereo visits | 124 / 122 | 124 / 122 |
| Verified receiver probes | 244 | 244 |
| Selected factors | 120 | 70 |
| c = 0 decision | Withheld | Withheld |
| Fitted c decision | Withheld | Withheld |

The pinned installed graph requires eight points and a six-second span for a seed. The longest candidate lane contained 13 points. Across the candidate's 120 winners, the largest time span among eligible groups was **4.9651958 s**. The time proof withheld through the standard writer before solver startup. Authenticated acquisition took 0.545 s and the candidate decision and publication interval took 0.016 s. The complete process comparison includes the differing receiver recipes. The measured ratio cannot isolate the speed contribution of the time proof alone.

## Conditioning and verification

The two original compressed members started with zero of 36,096 observed pages resident. One bounded, read-only conditioning pass charged **147,843,885 bytes**, 1.038 s wall, 0.028 s CPU, and 288,768 input blocks. Both launches observed all 36,096 pages resident. The archive stage copied **51,836,455 unique bytes** in 0.029 s and preserved 51 signed snapshot names through 29 distinct bodies. The conditioning and archive setup precede the warm process clocks.

The post-score verification matched both launches to the named release fingerprint and frozen launcher SHA-256. The candidate bootstrap and graph guard matched their original source digests at `a996ef001`. Both runs used the same signed recording authority, operator offer, opportunity digest, clock cutoff, and two excluded visits. Each run's own detector and terminal digests were verified against its publication. The pre-score seal covers 24 output and receipt files. Both verified terminals had null position endpoints for c = 0 and fitted c, empty media, and no geographic score. The original survey was unnecessary for those two calls.

An initial coordinator import failed before conditioning or launch. A post-score import then loaded the installed storage module ahead of the read-only repository scorer. The scorer recovered against the existing pre-score seal with no further physical replay. Sixteen focused tests passed under the same Gauss lock. [Component tests](../../../tests/pipeline_eval/test_short_raw_transfer.py) · [Full receipt](measurements/short-time-proof-0102.json.gz)
