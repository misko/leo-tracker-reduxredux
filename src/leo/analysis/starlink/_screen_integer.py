"""Research-only integer reference-quantization bound; unsupported IQ falls back."""

import numpy as np

from ._screen_bounds import bound as floating_bound


def bound(acquisition, args):
    result = floating_bound(acquisition, args)
    if not result['eligible']:
        return result
    values, template, rate, frequencies, symbols, epochs = args
    if (np.any(values.real != np.rint(values.real))
            or np.any(values.imag != np.rint(values.imag))
            or result['max_sample_component'] > 32767):
        return dict(eligible=False, reason='integer screen requires signed integer IQ')
    starts = [round(s * rate * acquisition.OFDM_SYMBOL_DURATION_S) for s in symbols]
    stops = [round((s + 1) * rate * acquisition.OFDM_SYMBOL_DURATION_S) for s in symbols]
    rmax = max(max(np.max(np.abs(template[s:t].real)), np.max(np.abs(template[s:t].imag)))
               for s, t in zip(starts, stops, strict=True))
    qmax = min(32767., np.floor((2.**31 - 1) /
                               (2 * result['max_taps'] * result['max_sample_component']))) - 1
    scale = qmax / (2*rmax)
    if not np.isfinite(scale) or scale <= 0:
        return dict(eligible=False, reason='unsafe integer accumulation scale')
    relative = max(np.sqrt(2*(t-s)) / (scale*np.linalg.norm(template[s:t]))
                   for s, t in zip(starts, stops, strict=True))
    error = relative*np.sqrt(result['maximum_energy_ratio']) + 1e-10*(1+relative)
    return dict(result, absolute_error=float(np.nextafter(error, np.inf)),
                reference_scale=float(scale), quantized_maximum=float(qmax),
                error_model='integer IQ / int16 reference quantization norm bound',
                production_qualified=False)
