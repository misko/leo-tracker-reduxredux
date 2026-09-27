# TG11 v1078 extra-decision diagnostic

The disputed TG11 timing/CFO hypotheses also pass the current Python
`conditioned_glrt64_score` when scored directly. The scanner's acquisition
stage did not retain those hypotheses among its ten candidates per probe. This
diagnostic therefore identifies an acquisition miss, rather than a native-only
positive caused by the final score implementation.

For the extra RX0 pair:

| Probe | TG11 epoch | CFO | Native blind margin | Native integer margin | Python integer margin |
|---:|---:|---:|---:|---:|---:|
| 4 | 6.9769 samples | -86,074.6 Hz | 0.09576 | 0.09547 at epoch 7 | 0.13562 at epoch 7 |
| 10 | 9.1503 samples | -86,087.5 Hz | 0.11411 | 0.11303 at epoch 9 | 0.11677 at epoch 9 |

Both Python margins exceed the unchanged 0.025 gate. Their returned tracking
CFOs differ by only 12.9 Hz, and the probes are 60 ms apart, so they satisfy the
scanner's pair rule if acquisition supplies them. Yet the closest candidates in
the scanner's complete 110-candidate RX0 response were 48.66/49.53 us and
84.72/84.73 kHz away. They fail the frozen 2 us/8 kHz identity tolerances.

The retained v1077 comparator positive anchors the procedure. Its two native
blind margins were 0.64676 and 0.62052; direct Python integer margins were
0.62274 and 0.63085. The application search already had matching identities for
both anchor coordinates.

The comparison does not assume the native and Python statistics are identical.
The pinned native profile alternates final-score symbols 2..65 and 152..215 on
successive frames, as implemented in deployment `presence.c` lines 621 and
645--654. The current Python score fixes symbols 2..65 for every frame in
`pilot_methods.py` lines 486--521. Native blind scoring can also apply tone
nuisance conditioning and fractional interpolation, while guided scoring uses
raw strided IQ and Python accepts integer timing only. In these four coordinates:

- all paths had 15 supporting frames;
- native nearest-integer and Python nearest-integer scores agreed on the gate;
- native blind and native raw guided exact margins reproduced one another, with
  zero recorded receipt-margin delta;
- nearest integer timing remained positive, so fractional interpolation was not
  required for either v1078 decision;
- the current-repository templates were used explicitly, with exact/control
  complex64 hashes recorded in `results.json`;
- CI16 and complex64 probe hashes were recorded separately, and caller IQ was
  unchanged.

Median point-score CPU was 0.187--0.197 ms for native exact guided scoring and
1.211--1.271 ms for the Python nearest-integer scorer. These are diagnostic
point costs, not complete-detector latency and not another speed qualification.

The scientific gate from phase one remains failed. This diagnostic neither
adjudicates the physical signal nor converts the additional decision into truth.
It supports a specific next design: native acquisition may propose timing/CFO,
but the canonical Python statistic must freshly confirm those proposals before a
decision. Such a detector needs its own frozen control and real-data gates. No
threshold was changed, no broader replay was run, and no holdout was opened.

Artifacts:

- `config.json` and `source_lock.json`: hypotheses and sources frozen before DSP.
- `results.json`: every raw score, support count, coordinate, nearest application
  candidate, template/layout hash and timing repetition.
- `run_diagnostic.py`: bounded two-case diagnostic runner.

