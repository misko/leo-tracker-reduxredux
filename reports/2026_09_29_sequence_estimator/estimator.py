"""Profile complex carrier gains; preserve held samples and state uncertainty limits."""

import numpy as np
from scipy.optimize import minimize, minimize_scalar

TS = 4.4e-6
SEED = np.array(list(map(int, "010010100010010010001000000000001000100000101000001010100010")))
WORDS = np.array([1 - 2 * (SEED ^ np.roll(SEED, -k)) for k in range(60)])
INIT = np.arange(20, 120)  # Array row zero is OFDM symbol 2.
SELECT = np.arange(140, 180)
FIT = np.arange(180, 220)
HELD = np.arange(220, 300)


def rotation(t, frequency_mhz, parameters):
    f, ppm = parameters
    return np.exp(2j * np.pi * t[:, None] * (f - frequency_mhz[None, :] * ppm))


def initial_frequency(values):
    """Profile independent gains; no assumption of common pilot-channel phase."""
    t = INIT * TS
    y = values[INIT]
    spectrum = np.sum(abs(np.fft.fft(y, n=8192, axis=0)) ** 2, axis=1)
    coarse = np.fft.fftfreq(8192, TS)[np.argmax(spectrum)]

    def objective(f):
        return -float(np.sum(abs(np.mean(y * np.exp(-2j * np.pi * f * t[:, None]), axis=0)) ** 2))

    fit = minimize_scalar(objective, bounds=(coarse - 1000, coarse + 1000), method="bounded")
    gain = np.mean(y * np.exp(-2j * np.pi * fit.x * t[:, None]), axis=0)
    coherence = np.sqrt(np.sum(abs(gain) ** 2) / np.mean(np.sum(abs(y) ** 2, axis=1)))
    return float(fit.x), float(coherence)


def select_state(values, mapping, coarse):
    y = values[SELECT] * np.exp(-2j * np.pi * coarse * (SELECT * TS)[:, None])
    models = WORDS[:, mapping[SELECT]]
    gains = np.mean(y[None] * models, axis=1)
    scores = np.sum(abs(gains) ** 2, axis=1) / np.mean(np.sum(abs(y) ** 2, axis=1))
    order = np.argsort(scores)
    return (
        int(order[-1]),
        float(np.sqrt(scores[order[-1]])),
        float(scores[order[-1]] - scores[order[-2]]),
    )


def fit(values, frequency_mhz, coarse):
    """All estimation uses FIT only; gains do not vary with time."""
    t = FIT * TS
    y = values[FIT]
    energy = max(float(np.mean(np.sum(abs(y) ** 2, axis=1))), 1e-30)

    def objective(p):
        gain = np.mean(y * rotation(t, frequency_mhz, p).conj(), axis=0)
        return -float(np.sum(abs(gain) ** 2)) / energy

    result = minimize(
        objective,
        [coarse, 0.0],
        method="Powell",
        bounds=[(coarse - 3000, coarse + 3000), (-300, 300)],
        options={"xtol": 1e-7, "ftol": 1e-10, "maxiter": 120},
    )
    return result.x, bool(result.success)


def held_error(values, frequency_mhz, parameters):
    gain = np.mean(values[FIT] * rotation(FIT * TS, frequency_mhz, parameters).conj(), axis=0)
    prediction = rotation(HELD * TS, frequency_mhz, parameters) * gain
    return float(
        np.sum(abs(values[HELD] - prediction) ** 2) / max(np.sum(abs(values[HELD]) ** 2), 1e-30)
    )


def evaluate(pilots, deviations, mapping, pilot_mhz, data_mhz):
    coarse, pc = initial_frequency(pilots)
    state, sc, margin = select_state(deviations, mapping, coarse)
    seq = deviations * WORDS[state, mapping]
    wrong = deviations * WORDS[(state + 1) % 60, mapping]
    combined_mhz = np.r_[pilot_mhz, data_mhz]
    arms = {}
    for name, values, mhz in [
        ("pilot", pilots, pilot_mhz),
        ("sequence", np.c_[pilots, seq], combined_mhz),
        ("wrong_state", np.c_[pilots, wrong], combined_mhz),
    ]:
        parameters, success = fit(values, mhz, coarse)
        arms[name] = dict(
            frequency_hz=float(parameters[0]),
            drift_ppm=float(parameters[1]),
            success=success,
            boundary=bool(abs(parameters[0] - coarse) > 2990 or abs(parameters[1]) > 299),
            held_pilot_nmse=held_error(pilots, pilot_mhz, parameters),
            held_sequence_nmse=held_error(seq, data_mhz, parameters),
        )
    return dict(
        state=state,
        state_coherence=sc,
        state_score_margin=margin,
        initial_pilot_coherence=pc,
        qualified=bool(sc > 0.5 and pc > 0.5),
        arms=arms,
    )
