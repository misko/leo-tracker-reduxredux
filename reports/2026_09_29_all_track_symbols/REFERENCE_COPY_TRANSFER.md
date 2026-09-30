# Can full-band header repetitions improve local bit recovery?

One same-sign header relation survives the full-band reference split within
the upper-edge carrier coverage, but it does not transfer consistently enough
to justify combining local observations as copies of one bit. No relation
survives in the tested lower-edge coverage. This excludes neither conditional
repetition nor higher-order coding.

## Frozen selection

Use the existing 78-frame public hard-reference cache, remove its published
template rotations, and restrict to symbols 2–7. Upper bins are 476–487 and
496–507; lower bins are 516–527 and 536–547. These match the original local
24-data-carrier caches. Pilot bins are excluded.

The first 39 reference frames select exact copies or complements using the
existing `header_copies.select_pairs` implementation. Each discovery coordinate
must pass the hard-axis gate on every frame and show each bit value at least
twice. One fixed representative per identical/complemented trace group is used,
not all pairwise links. The remaining 39 frames must all pass the quality gate
and the frozen equality or complement relation, with no polarity refit.

| Edge | Discovery representative links | Later-reference survivors |
|---|---:|---:|
| Upper | 25 | 1 |
| Lower | 14 | 0 |

The upper survivor is **OFDM symbol 2, FFT carriers 480 and 486, equal sign**.
Both have 33 positive observations among all 78 reference frames. Thus it is
not simply a pair of constant reference bits. However, all reference frames
belong to one public acquisition and have been used in previous exploratory
work; this is an algorithmic split, not a pristine project-wide holdout.

## Local transfer without reselection

Freeze those coordinates and equal polarity, then inspect every jointly
pilot-qualified evaluation frame in the existing S13, S22, and S23 paired
caches. No confidence filtering, receiver selection, or polarity fitting is
performed using local outcomes.

| Visit | Frames | RX0 equality / marginal baseline | RX1 equality / marginal baseline |
|---|---:|---:|---:|
| S13 | 20 | 70.0% / 52.5% | 45.0% / 50.0% |
| S22 | 32 | 65.6% / 46.5% | 53.1% / 48.0% |
| S23 | 42 | 69.0% / 67.5% | 78.6% / 76.5% |

Marginal baseline is the agreement expected from the two observed positive-sign
fractions under independence. S23 illustrates why a large raw equality fraction
can be uninformative: its baseline is nearly as high. The other visits give
different outcomes between receivers. Noise, calibration, conditional behavior,
or differences between acquisitions remain possible explanations; the table
does not prove a universal copy rule or its absence at the transmitter.

Consequently these positions must not be averaged or majority-combined as
verified redundant bits. The experiment supplies no new decoded field and no
improved bit stream. It narrows one concrete path to error reduction without
forcing a decoder onto an unvalidated relation.

## Reproduction

`reference_copy_transfer.py` records all surviving relations and local checks
under ignored `local/reference-copy-transfer/summary.json`, with method,
reference, template, and evaluated local-cache hashes. Numerical observations
remain uncommitted. Two synthetic tests verify rejection of a relation broken
only in evaluation and exclusion of an unqualified evaluation observation.
All 31 research tests and Ruff checks pass. No RF collection, download, commit,
or deployment was performed.
