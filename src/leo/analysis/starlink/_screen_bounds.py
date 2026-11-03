"""Conservative candidate bound for the pinned FP32 screen, research only.

This uses Cauchy-Schwarz and a conservative sliding-energy error allowance; it is
not inferred from observed screen errors. Unsupported geometry/ranges require the full grid.
Independent numerical qualification is still required before production use.
"""

import ctypes

import numpy as np


def bound(acquisition, args):
    values, template, rate, frequencies, symbols, epochs = args
    values, template = np.asarray(values), np.asarray(template)
    if (values.dtype != np.complex128 or template.dtype != np.complex128
            or values.ndim != 1 or template.ndim != 1 or not values.size or not template.size
            or values.size > 1_000_000 or not 1 <= rate <= 1e10
            or not frequencies or not np.isfinite(frequencies).all()
            or max(abs(x) for x in frequencies) > 1e8 or not 1 <= epochs <= values.size
            or not np.isfinite(values).all() or not np.isfinite(template).all()):
        return dict(eligible=False, reason='unsupported geometry or nonfinite input')
    # fegetround == FE_TONEAREST on the explicitly supported Linux/x86 runtime.
    if ctypes.CDLL(None).fegetround() != 0:
        return dict(eligible=False, reason='rounding mode is not nearest')
    starts = [round(s * rate * acquisition.OFDM_SYMBOL_DURATION_S) for s in symbols]
    stops = [round((s + 1) * rate * acquisition.OFDM_SYMBOL_DURATION_S) for s in symbols]
    if (not starts or any(s < 0 or t <= s or t > len(template)
                          for s, t in zip(starts, stops, strict=True))):
        return dict(eligible=False, reason='unsupported template geometry')
    taps = max(t - s for s, t in zip(starts, stops, strict=True))
    maximum_support = len(symbols) * (int(values.size / (rate / acquisition.FRAME_RATE_HZ)) + 2)
    if taps > 4096 or taps > values.size or maximum_support > 10_000:
        return dict(eligible=False, reason='unsupported operation count')
    x = float(max(np.max(np.abs(values.real)), np.max(np.abs(values.imag))))
    r = float(max(np.max(np.abs(template.real)), np.max(np.abs(template.imag))))
    if max(x, r) > 2.**40 or min(x, r) == 0:
        return dict(eligible=False, reason='unsupported amplitude range')
    reference_energy = min(float(np.sum(np.abs(template[s:t])**2))
                           for s, t in zip(starts, stops, strict=True))
    prefix = acquisition._power_prefix(values)
    minimum_received = np.inf
    maximum_energy_ratio = 1.
    k64 = values.size + 4
    gamma64 = k64*2.**-53 / (1-k64*2.**-53)
    for n in set(t - s for s, t in zip(starts, stops, strict=True)):
        received = prefix[n:] - prefix[:-n]
        valid = received > 0
        positive = received[valid]
        if positive.size:
            minimum_received = min(minimum_received, float(positive.min()))
            # The input-energy sum is nonnegative. Allow prefix-summation,
            # power-formation and subtraction rounding on BOTH endpoints.
            # The factor four exceeds gamma/(1-gamma) plus subtraction error
            # over the admitted <=1,000,000-sample domain.
            allowance = (4*gamma64*(prefix[n:][valid] + prefix[:-n][valid])
                         + 4*values.size*np.finfo(float).tiny)
            maximum_energy_ratio = max(maximum_energy_ratio,
                                       float(np.max(1 + allowance/positive)))
    if (not np.isfinite(reference_energy) or not np.isfinite(minimum_received)
            or min(reference_energy, minimum_received) < 2.**-500):
        return dict(eligible=False, reason='degenerate or exceptionally small normalization')
    # Half the estimated lower norm leaves a wide margin for FP64 reference
    # energy/sqrt rounding. Prefix differences are the actual deployed values.
    denominator_lower = .5 * np.sqrt(reference_energy * minimum_received)
    u = 2.**-24
    operation_count = 4*taps + 16
    gamma = operation_count*u / (1-operation_count*u)
    # Cauchy-Schwarz bounds the four-product L1 sum by 2*||x||*||rotated r||.
    # A factor 16 allows the rotation norm (even |cos|, |sin| <= 2), FP64
    # reference-energy estimation and norm rounding. Prefix cancellation is
    # covered separately by maximum_energy_ratio. This avoids combining two
    # unrelated global peaks with the weakest normalization in the recording.
    normalized_product_bound = 16*np.sqrt(maximum_energy_ratio)
    # Absolute allowance covers FP32 conversion/arithmetic underflow, including
    # flush-to-zero; input maxima prevent intermediate FP32 overflow.
    underflow_allowance = 64*taps*np.finfo(np.float32).tiny*(1+x+r)
    # The 1e-10 allowance exceeds FP64 error accumulation for <=10,000 supports;
    # it also covers magnitude, division and lower-bound construction rounding.
    error = (gamma*normalized_product_bound + underflow_allowance/denominator_lower
             + 1e-10*(1+normalized_product_bound))
    if not np.isfinite(error):
        return dict(eligible=False, reason='nonfinite error bound')
    return dict(eligible=True, absolute_error=float(np.nextafter(error, np.inf)),
                max_taps=taps, maximum_support=maximum_support,
                max_sample_component=x, max_reference_component=r,
                maximum_energy_ratio=maximum_energy_ratio,
                normalized_product_bound=float(normalized_product_bound),
                denominator_lower=float(denominator_lower), gamma=float(gamma),
                production_qualified=False)
