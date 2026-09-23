# Random-group phase-link replay

This directory replays the frozen 24-dwell multirate selection with seed
`20260923`. Six 20 ms groups are split within three successive 40 ms strata,
with one randomly assigned training group and one held-out group per stratum.
Carrier seeding, carrier fitting, and spectral-response fitting use training
groups. Within each held group, frequency set A predicts disjoint set B. A
different held RX1 group supplies the wrong-pair control.

Of the frozen selections, 2/8 dwells at 2.5 MS/s, 7/8 at 10 MS/s, and 6/8 at
15 MS/s pass the predeclared waveform gate. Two 2.5 MS/s dwells abstain: one
because a local phase increment is ambiguous near pi, and one because response
normalization has no A-band support. Neither was replaced. The rate groups
differ in sky, RF edge, receiver balance, and retained coverage, so these
counts do not establish a causal sampling-rate ranking.

The score is capture-level evidence for a common coherent waveform component.
The broadband dwell may contain multiple sources, and the strongest
phase-blind GLRT pair can differ among 20 ms probes. Therefore this evidence is
not bound to a specific GLRT episode, NORAD object, or position mode. Such use
requires frozen candidate membership or source-specific isolation. The two
shared-capture hypotheses in the replay are abstract invariance checks: their
equal weights demonstrate that current phase evidence cannot alter relative
satellite rank. Residual phase is not treated as calibrated geometry.

`comparison.json.gz` is the canonical full evidence and binds the frozen
selection, capture manifest, protocol, and numerical source hashes. The runner
uses compressed row checkpoints during replay, but they are omitted here
because the canonical comparison already contains them. `per-dwell.csv`
exposes every same-capture and wrong-pair metric; `summary.json` aggregates by
rate; and `random-phase-links-by-rate.png` plots the controls and applied
conditional composite research score.

The final replay verified that the hashes recorded in `comparison.json.gz`
match `phase_association.py`, `random_phase_validation.py`,
`broadband_alignment.py`, and `replay.py`. Reproduce the bounded replay and
summary from the repository root with:

```sh
sudo env PYTHONPATH="$PWD/src" OPENBLAS_NUM_THREADS=1 timeout 240s \
  "$PWD/.venv/bin/python" \
  reports/figures/2026_09_23_random_phase_links/replay.py
sudo env PYTHONPATH="$PWD/src" OPENBLAS_NUM_THREADS=1 \
  MPLCONFIGDIR=/tmp/random-phase-links-mpl "$PWD/.venv/bin/python" \
  reports/figures/2026_09_23_random_phase_links/summarize.py
```
