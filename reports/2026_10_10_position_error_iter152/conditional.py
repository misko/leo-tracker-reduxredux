"""Two receiver-separated scalar slices of an existing joint objective.

No optimizer, quadrature, recording loader or geometry approximation. Construction
calls the supplied objective once; each scalar evaluation calls it once more.
"""

import numpy as np

from math_core import amplitude_interval


class ConditionalModes:
    def __init__(self, model, vector, clock, *, arm):
        if arm not in ("fitted-c", "zero-c"):
            raise ValueError("unknown c arm")
        self.model = model
        self.vector = np.array(vector, dtype=float, copy=True)
        self.clock = np.array(clock, dtype=float, copy=True)
        if (self.vector.shape != (model.size,) or model.size < 8
                or self.clock.ndim != 1 or not np.isfinite(self.vector).all()
                or not np.isfinite(self.clock).all()):
            raise ValueError("invalid joint state")
        count = model.smooth_clock_count
        if not isinstance(count, (int, np.integer)) or count < 2 or count % 2:
            raise ValueError("two nonempty equal smooth blocks required")
        if len(self.clock) < count + 2 or np.any(abs(self.clock) > 2000):
            raise ValueError("invalid coefficient layout or box")
        if np.any(abs(self.clock[-2:]) > 1000):
            raise ValueError("RF-time coefficient outside its existing box")
        if arm == "zero-c" and (self.vector[6] != 0 or np.any(self.clock[-2:] != 0)):
            raise ValueError("zero-c static/RF-time locks violated")
        if getattr(model, "fixed_rf_drift", False) and np.any(self.clock[-2:] != 0):
            raise ValueError("fixed RF-time lock violated")
        precision = np.asarray(model.precision, float)
        design = np.asarray(model.clock_design, float)
        receiver = np.asarray(model.observations.receiver)
        size = len(self.clock)
        if (precision.shape != (size, size) or design.shape != (len(receiver), size)
                or receiver.ndim != 1 or not np.isin(receiver, (0, 1)).all()
                or not np.isfinite(precision).all() or not np.isfinite(design).all()):
            raise ValueError("invalid precision/design/receiver layout")
        if not np.allclose(precision, precision.T, rtol=0, atol=1e-12):
            raise ValueError("asymmetric precision")
        m = count // 2
        self.slices = (slice(0, m), slice(m, count))
        block = precision[:m, :m]
        if not np.allclose(block, precision[m:count, m:count], rtol=0, atol=1e-12):
            raise ValueError("receiver precision differs")
        for r, selection in enumerate(self.slices):
            others = np.r_[np.arange(selection.start), np.arange(selection.stop, size)]
            if np.any(abs(precision[selection][:, others]) > 1e-12):
                raise ValueError("selected smooth block has cross-precision")
            if np.any(design[receiver != r, selection] != 0):
                raise ValueError("cross-receiver smooth design")
        eigenvalues, eigenvectors = np.linalg.eigh(block)
        if eigenvalues[0] <= 0 or not np.isfinite(eigenvalues).all():
            raise ValueError("proper smooth prior required")
        if m > 1 and eigenvalues[1] - eigenvalues[0] <= 1e-10 * max(abs(eigenvalues)):
            raise ValueError("lowest prior eigenspace is ambiguous")
        self.precision = float(eigenvalues[0])
        self.direction = eigenvectors[:, 0].copy()
        # Prior-only deterministic sign; integration is invariant to this choice.
        if self.direction[np.argmax(abs(self.direction))] < 0:
            self.direction *= -1
        self.amplitudes = np.array([self.direction @ self.clock[s] for s in self.slices])
        self.remaining = [self.clock[s] - self.direction * a
                          for s, a in zip(self.slices, self.amplitudes, strict=True)]
        self.intervals = tuple(amplitude_interval(self.direction, rest) for rest in self.remaining)
        self.anchor_value, self.anchor_clock_gradient = self._evaluate(self.clock)
        for value in (self.vector, self.clock, self.direction, self.amplitudes,
                      self.anchor_clock_gradient, *self.remaining):
            value.setflags(write=False)

    def _evaluate(self, clock):
        value, physical_gradient, clock_gradient, _ = self.model.evaluate_joint(
            self.vector.copy(), np.array(clock, copy=True)
        )
        physical_gradient = np.asarray(physical_gradient, float)
        clock_gradient = np.asarray(clock_gradient, float)
        if (not np.isfinite(value) or physical_gradient.shape != self.vector.shape
                or clock_gradient.shape != self.clock.shape
                or not np.isfinite(physical_gradient).all()
                or not np.isfinite(clock_gradient).all()):
            raise ValueError("nonfinite or invalid objective result")
        return float(value), clock_gradient.copy()

    def scalar(self, receiver, amplitude):
        if receiver not in (0, 1) or not np.isfinite(amplitude):
            raise ValueError("invalid receiver/amplitude")
        lower, upper = self.intervals[receiver]
        if not lower <= amplitude <= upper:
            raise ValueError("amplitude outside original coefficient box")
        clock = self.clock.copy()
        # Delta form preserves the exact supplied anchor at its own amplitude.
        clock[self.slices[receiver]] += self.direction * (amplitude - self.amplitudes[receiver])
        value, gradient = self._evaluate(clock)
        return dict(value=value, difference=value - self.anchor_value,
                    gradient=float(self.direction @ gradient[self.slices[receiver]]))

    def marginal_score(self, log_integrals):
        """Combine externally established log ∫exp(-D_r) da; perform no integration."""
        logs = np.asarray(log_integrals, float)
        if logs.shape != (2,) or not np.isfinite(logs).all():
            raise ValueError("two finite log integrals required")
        return float(self.anchor_value - logs.sum() - np.log(self.precision / (2 * np.pi)))
