# RX0 replay at the 150802 RX1 long-branch anchors

Date: 2026-08-25

## Outcome

The bounded raw-IQ replay materially improves the **precision and cross-receiver
registration** of the existing RX0 candidate branch, but it does not improve
its independent temporal coverage.

Over the common RX0/RX1 interval 43.6–51.35 s, all 15 RX1 primary anchors were
searched independently on RX0 over one complete 750 Hz frame period (3,334
integer epoch hypotheses) and a ±2.5 kHz CFO neighborhood in 250 Hz steps. The
first 60% UTC fold calibrated an RX0-minus-RX1 integer epoch offset of exactly
0 samples from three strong exact-versus-rolled Qin anchors. Applying that
frozen offset and the target-binding gates to both folds retained 9 anchors: 5
before the fixed 48.25 s split and 4 after it.

Those anchors produced 126 even-fold research-supported rows (14 per anchor).
The 15th nominal opportunity in each 20 ms window was an explicitly recorded
incomplete endpoint. The stricter primary frame-CFO contract supports 117 of
the 126 rows: 66 in the first-60% calibration fold and 51 in the final-40%
evaluated conditional fold. All nine primary rejections are explicitly retained
in the ledger and have reason `even_odd_disagreement_above_maximum`.

The authoritative primary-contract line has slope -3,589.828 Hz/s and 25.058
Hz RMS. Its first-60% fit predicts the final-40% evaluated conditional fold at
27.874 Hz RMS. The research companion's even-fold line has slope -3,587.933
Hz/s and 35.788 Hz RMS; its corresponding evaluated-fold error is 36.812 Hz.
After reducing the research companion to one median per anchor, the 9-point fit
has slope -3,587.599 Hz/s and 13.818 Hz RMS; the 5-anchor calibration line
predicts the 4-anchor evaluated conditional fold at 18.690 Hz RMS.

The persisted RX0 branch contains 67 GLRT observations over 43.6–51.35 s, with
slope -3,576.124 Hz/s and 152.082 Hz residual RMS. The 117 primary-supported
rows—and the broader 126-row even-fold research companion—are not independent
epochs: they are clustered inside nine 20 ms windows spanning 45.475–50.5 s.
Therefore the lower primary residual and denser rows are a conditional
measurement-quality improvement, not evidence that the old branch gained
coverage or that the effective sample size doubled.

## Cross-receiver result

All 126 even-fold research-supported RX0 frames have an RX1 supported frame
within two samples. The sample
offset distribution is -1: 17, 0: 66, +1: 38, and +2: 5; 66 starts match
exactly. On this common frame set:

- RX0 slope: -3,587.933 Hz/s;
- RX1 slope: -3,578.230 Hz/s;
- RX0-minus-RX1 slope: -9.703 Hz/s;
- median RX0-minus-RX1 CFO: 613,784.110 Hz;
- RX0-minus-RX1 line residual RMS: 69.009 Hz.

This is useful receiver-relative evidence that both chains see the same local
Doppler shape after a large nuisance CFO offset. It is not independent-clock
evidence: RX0 and RX1 share one Pluto sample-counter/LO domain.

## Specificity and continuity gates

The RX0 search did not copy the RX1 epoch. Each 20 ms IQ window searched the
full frame ambiguity and a local CFO neighborhood. Exact Qin and the 17-symbol-
rolled control independently maximized over the same search domain. Target
binding then required exact score at least 0.10, positive exact-minus-control
margin, and agreement within 4 samples of the training-calibrated receiver
delay.

The source recording is counter-authoritative: 150,000,000 observed samples
equal the device span, with zero gaps, missing samples, overflows, clipped
samples, constant-IQ refills, or gap-map boundaries. Three of the 15 searched
windows cross application refill markers; the markers are retained as audit
evidence and correctly do not force a reset on this counter-contiguous capture.

## Scientific limits

- The existing RX0 trajectory supplied the CFO seed and alias +2; the replay is
  conditional on that candidate branch.
- Local alignment and frame membership use known Qin symbols, so this is not an
  untouched end-to-end validation fold.
- The first 60% calibrates receiver delay. The final 40% is an evaluated
  conditional fold, not an untouched or preserved holdout: local alignment and
  membership still use Qin evidence from those windows.
- The result strengthens a shared signal-shape case. It does not establish a
  NORAD identity or prove that the branch belongs to one physical satellite.

## Reproduction and evidence

```bash
rx0_replay_root=$(mktemp -d /tmp/leo-rx0-anchor-replay.XXXXXX)
uv run python tools/prototype_rx0_cross_receiver_anchor_replay.py \
  --output-root "$rx0_replay_root"
uv run pytest -q -m 'not real_corpus and not legacy_oracle' \
  tests/analysis/test_rx0_cross_receiver_anchor_replay_tool.py
uv run pytest -q -m real_corpus \
  tests/analysis/test_rx0_cross_receiver_anchor_replay_tool.py
uv run ruff check \
  tools/prototype_rx0_cross_receiver_anchor_replay.py \
  tests/analysis/test_rx0_cross_receiver_anchor_replay_tool.py
```

- Summary JSON SHA-256:
  `19d591ec60ef12e0b29fbff0c5bb917fb19082755e510b17fdb9c67dda1392de`.
- Frame ledger SHA-256:
  `dffbea6836e66f97281ee74f9380b063eefddafe1432d8d6bde494b03038e832`.
- Artifact manifest SHA-256:
  `a5422aa6d6a283c3282c04dd9e8c0f21bc63617ac929bc598533f29974da5cdc`.
- Tool SHA-256:
  `586efda332f1d4ee4329eab5ea95a8ff52e0d4d0e23c3c1b890eaa6bcff53084`.
- Scientific configuration SHA-256:
  `c04640173c07dd8c5933c58b84ae3c21b25356e21680f480b3838069682406f2`.

The stable scientific summary excludes runtime and uses a relative ledger path.
At startup and shutdown the tool pins and rechecks the tool/configuration and
all inputs. It also proves that the RX1 evidence-declared uncompressed row
digest equals the digest obtained by decompressing the committed gzip ledger.
