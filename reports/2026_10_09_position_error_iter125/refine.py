"""Research-only one-peak CFO refinements; admission scores stay unchanged."""

import numpy as np

STEP_S = 4.4e-6
SIZE = 512
DELTA_HZ = 1 / (SIZE * STEP_S)


def polynomial(values):
    values = np.asarray(values, complex)
    if values.ndim != 2 or values.shape[1] != 64 or not np.isfinite(values).all():
        raise ValueError("finite frames by 64 symbol correlations required")
    fft = np.fft.fft(values, n=128, axis=1)
    coefficients = np.fft.ifft(np.sum(abs(fft) ** 2, axis=0))[:64]
    ceiling = float(np.sum(np.sum(abs(values), axis=1) ** 2))
    if ceiling <= 0:
        return np.zeros(64, complex), np.zeros(SIZE), 0
    coefficients /= ceiling
    packed = np.zeros(SIZE, complex)
    packed[:64] = coefficients
    packed[-63:] = coefficients[1:][::-1].conj()
    spectrum = np.fft.fft(packed).real
    return coefficients, spectrum, int(np.argmax(spectrum))


def evaluate(coefficients, bins):
    lag = np.arange(1, 64)
    omega = -2j * np.pi * lag / SIZE
    terms = coefficients[1:] * np.exp(omega * bins)
    return (
        float(coefficients[0].real + 2 * terms.real.sum()),
        float(2 * (terms * omega).real.sum()),
        float(2 * (terms * omega**2).real.sum()),
    )


def wrap_frequency(bins):
    return float(((bins + SIZE / 2) % SIZE - SIZE / 2) * DELTA_HZ)


def refine(values, *, native_bin=None):
    coefficients, spectrum, index = polynomial(values)
    if native_bin is not None:
        if not isinstance(native_bin, (int, np.integer)) or not 0 <= native_bin < SIZE:
            raise ValueError("invalid native winner")
        if index != native_bin:
            raise ValueError("native/Python winner mismatch; no alternate tie policy")
        index = int(native_bin)
    base = float(spectrum[index])
    neighbors = spectrum[[(index - 1) % SIZE, index, (index + 1) % SIZE]]
    offset = 0.0
    reason = "nonpositive-or-flat"
    if np.all(neighbors > 0):
        a, b, c = np.log(neighbors)
        curvature = a - 2 * b + c
        if curvature < -np.finfo(float).eps:
            proposal = float(np.clip(0.5 * (a - c) / curvature, -0.5, 0.5))
            if evaluate(coefficients, index + proposal)[0] >= base:
                offset, reason = proposal, "accepted"
            else:
                reason = "exact-power-decreased"
    current = float(index)
    current_score = base
    accepted = 0
    newton_reason = "maximum-three-steps"
    for _ in range(3):
        _, gradient, hessian = evaluate(coefficients, current)
        if not hessian < 0 or not np.isfinite([gradient, hessian]).all():
            newton_reason = "nonnegative-curvature"
            break
        candidate = float(np.clip(current - gradient / hessian, index - 0.5, index + 0.5))
        score = evaluate(coefficients, candidate)[0]
        if score < current_score:
            newton_reason = "exact-power-decreased"
            break
        current, current_score = candidate, score
        accepted += 1
    return {
        "native_bin": index,
        "coarse_hz": wrap_frequency(index),
        "coarse_score": base,
        "logparabola_hz": wrap_frequency(index + offset),
        "logparabola_reason": reason,
        "newton_hz": wrap_frequency(current),
        "newton_steps": accepted,
        "newton_reason": newton_reason,
        "newton_score": current_score,
    }
