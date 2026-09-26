# Conditional multi-mode shared-instrument prototype

This bounded real-data prototype does **not** separate LNB/LO phase from source
geometry.  It tests the narrower, observable claim: whether the phase increment
from one simultaneously extracted mode transfers to the other mode better than
an unrelated-time control.  The two template modes are distinct alias groups,
but they are not confirmed distinct emitters.

## Model and identifiability

For mode `k`, the conditional model is `phase_k(t) = common(t) + mode_k(t)`.
If both terms are degree `p`, any degree-`p` polynomial can be moved from the
common term into every mode term.  The unconstrained design therefore has
`p+1` null directions.  `model.py` exposes that nullity and, only for a
representative decomposition, chooses the gauge in which the mode-specific
coefficient mean is zero.  This gauge does not turn the common curve into a
measured LO/LNB curve or make the residuals geometric phase.

Phase is unwrapped separately inside contiguous segments.  Missing intervals
and retunes start new segments, with no cycle-branch or phase-offset stitching.
The primary score predicts phase, and a secondary score uses increments; neither
fits a held-mode phase offset.

## Real-data result

The cache contains eight phase-blind selected visits, two modes per visit, and
17 simultaneous 7 ms windows per mode. A line fitted to target-minus-donor in
the first four windows is frozen. The held target is then predicted from the
donor phase at that same held time plus the frozen difference; no held target
sample or offset is fitted. Swapping donor and held mode gives 16 directed
evaluations, with 13 held phase windows each.

All primary scores use wrapped angular residuals, so independent `2π` choices
cannot improve or damage a method. The simultaneous donor plus frozen
difference had median held-phase RMSE 102.33 degrees (range 64.41--117.80). The
target-only linear-frequency baseline had median 103.78 degrees and the
target-only constant-phase baseline 110.52 degrees. The simultaneous method won
only 9 of 16 directed comparisons against the linear baseline and 10 of 16
against the constant baseline. The frozen-model, circularly shifted donor
control had median 106.99 degrees and lost only 9 of 16 comparisons. Wrapped
held-increment error was 100.22 degrees at the median.

Those residuals are close to the scale expected from poorly predicted circular
phase, and the win counts are not compelling. This real-data prototype therefore
does not establish useful LO/LNB separation or preserved geometric tracks. It
does establish a runnable, leakage-resistant test that a larger or cleaner
synchronized cohort can reuse.

This is not positive evidence of a usable shared contemporaneous component, nor
evidence that any such component is exclusively LO/LNB drift: mode-specific
tracking corrections, template timing, leakage, and common propagation can
also create transfer. The modes use identical IQ windows and the same
strongest-primary differential frequency correction, while retaining their own
fitted template epochs. Current-donor transfer
is a simultaneous correction; it is not a future forecast.

The 79 degree baseline orientation supplies a direction axis only.  With no
baseline length, source association, or independently known direction, this
experiment cannot label either mode residual as orbital geometry.

## Reproduction

From this directory, with the pinned environment:

```bash
python run.py
```

Outputs are `metrics.json` and `increment-transfer.png`.  Synthetic tests cover
the gauge-fixed relative decomposition, its explicit nullity, cycle branches
across missing data, and the wrong-time increment control.
