"""Audit which residual statistics survive retaining only primary pilot block dots."""

import argparse
import ctypes as ct
import json
from contextlib import ExitStack
from pathlib import Path

import numpy as np

from .receiver_benchmark import Receiver, digest, read_archive
from .receiver_cfo_peak_bound import V3_SHA, ranked, read_trace
from .receiver_differential_fold import measure, wrapped_distance

POINTS = 200_000
TICKS = 40_000
FRAMES = 14
WIDTH = 4_740
ROWS = (
    np.rint(np.arange(FRAMES) * (10_000_000 / 3_000)).astype(int)[:, None]
    + 22
    + np.arange(WIDTH)[None, :]
)


def blocks(epoch, rotated):
    """Views of the actual native pilot support, including partial edge blocks."""
    first = int(round(3 * epoch))
    for frame in range(first - TICKS, 3 * POINTS, TICKS):
        for symbol in range(2, 302, 64):
            lo = max(0, -(-(frame + 132 * symbol) // 3))
            hi = min(POINTS, -(-(frame + 132 * min(symbol + 64, 302)) // 3))
            if lo < hi:
                yield slice(lo, hi), rotated[3 * lo - frame : 3 * hi - frame : 3]


def primary_statistics(x, basis):
    model = np.zeros_like(x)
    orthogonal = np.zeros_like(x)
    for region, p in basis:
        squared = np.vdot(p, p).real
        if squared:
            model[region] = p * (np.vdot(p, x[region]) / squared)
            orthogonal[region] = p / np.sqrt(squared)
    return model, orthogonal


def quantize(values):
    return np.clip(np.rint(values), -32768, 32767)


def correction_error(raw, model, native_residual):
    direct = raw - model
    approximate = raw - np.rint(model)
    # Translating a nearest-even integer quantizer by an odd integer changes ties.
    ties = np.abs(model - np.rint(model)) == 0.5
    return dict(
        modeled_residual_differing_components=int(
            np.count_nonzero(quantize(direct) != native_residual)
        ),
        clipping_components=int(np.count_nonzero((direct < -32768) | (direct > 32767))),
        half_integer_components=int(np.count_nonzero(ties)),
        rounding_and_clipping_rms_adc=float(np.sqrt(np.mean((native_residual - direct) ** 2))),
        predicted_correction_differing_components=int(
            np.count_nonzero(approximate != native_residual)
        ),
    )


def secondary_statistics(residual, remainder, primary, primary_regions, alternative):
    """Energy of per-block alternate templates in the retained primary span."""
    energy, observed, from_remainder = 0.0, 0.0, 0.0
    retained = 0.0
    for region, wave in alternative:
        norm = np.vdot(wave, wave).real
        if norm == 0.0:
            continue
        energy += norm
        observed += abs(np.vdot(wave, residual[region])) ** 2 / norm
        from_remainder += abs(np.vdot(wave, remainder[region])) ** 2 / norm
        for primary_region in primary_regions:
            lo = max(region.start, primary_region.start)
            hi = min(region.stop, primary_region.stop)
            if lo < hi:
                window = wave[lo - region.start : hi - region.start]
                retained += abs(np.vdot(primary[lo:hi], window)) ** 2
    return dict(
        secondary_template_energy_retained=retained / energy,
        secondary_matched_energy_adc2=observed,
        secondary_without_raw_complement_adc2=from_remainder,
    )


def centered_rows(x, fir, center):
    if center:
        x = x * np.exp((-2j * np.pi * center / 1e7) * np.arange(len(x)))
    rows = np.convolve(x, fir, mode="same")[::4][ROWS]
    return rows - rows.mean(axis=1, keepdims=True)


def standardized(gram):
    scale = 1 / np.maximum(np.sqrt(np.maximum(gram.diagonal().real / WIDTH, 0)), 1e-12)
    return gram * scale[:, None] * scale[None, :]


def frame_statistics(raw, model, residual, fir, center):
    x, c, r = (centered_rows(z, fir, center) for z in (raw, model, residual))
    raw_gram = x @ x.conj().T
    correction_gram = c @ c.conj().T
    cross = x @ c.conj().T
    reconstructed = standardized(raw_gram - cross - cross.conj().T + correction_gram)
    ideal = x - c
    ideal_covariance = standardized(ideal @ ideal.conj().T)
    exact = standardized(r @ r.conj().T)
    _, raw_modes = np.linalg.eigh(standardized(raw_gram))
    _, exact_modes = np.linalg.eigh(exact)
    raw_top, exact_top = raw_modes[:, -2:], exact_modes[:, -2:]
    return dict(
        gram_identity_absolute_error=float(np.max(np.abs(reconstructed - ideal_covariance))),
        ideal_vs_ci16_covariance_relative_error=float(
            np.linalg.norm(reconstructed - exact) / np.linalg.norm(exact)
        ),
        raw_vs_ci16_top_two_min_overlap=float(
            np.linalg.svd(raw_top.conj().T @ exact_top, compute_uv=False)[-1]
        ),
    )


class TimingResult(ct.Structure):
    _fields_ = [
        ("epoch", ct.c_double),
        ("hz", ct.c_double),
        ("score", ct.c_double),
        ("confirmation", ct.c_int),
    ]


class TimingTrace:
    def __init__(self, receiver, asset):
        self.lib = receiver.lib
        self.fir = asset[4 * 13_333 : 4 * 13_333 + 81]
        self.pilot = asset[4 * 13_333 + 81 :]
        self.lib.timing_first_create.argtypes = [ct.c_int, ct.c_void_p, ct.c_void_p]
        self.lib.timing_first_create.restype = ct.c_void_p
        self.lib.timing_first_free.argtypes = [ct.c_void_p]
        self.lib.timing_first_free.restype = None
        self.lib.timing_first_detect.argtypes = [
            ct.c_void_p,
            ct.c_void_p,
            ct.c_int,
            ct.c_double,
            ct.c_double,
            ct.POINTER(TimingResult),
        ]
        self.lib.pilot_cancel.argtypes = [
            ct.c_void_p,
            ct.c_void_p,
            ct.c_int,
            ct.c_void_p,
            ct.c_void_p,
            ct.c_double,
            ct.c_double,
        ]
        self.handle = self.lib.timing_first_create(4, asset.ctypes.data, self.fir.ctypes.data)
        if not self.handle:
            raise ValueError("failed to create timing workspace")

    def close(self):
        self.lib.timing_first_free(self.handle)

    def confirm(self, iq, lane, center):
        result = TimingResult()
        status = self.lib.timing_first_detect(
            self.handle, iq.ctypes.data, lane, center - 800_000, center + 800_000, ct.byref(result)
        )
        if status:
            raise ValueError(f"timing failed with status {status}")
        return result

    def cancel(self, iq, lane, epoch, hz):
        output = np.empty_like(iq)
        rotated = np.empty(TICKS, dtype=np.complex64)
        status = self.lib.pilot_cancel(
            iq.ctypes.data,
            output.ctypes.data,
            lane,
            self.pilot.ctypes.data,
            rotated.ctypes.data,
            epoch,
            hz,
        )
        if status:
            raise ValueError(f"signed cancellation failed with status {status}")
        return output, rotated.astype(np.complex128)


def complex_lane(iq, lane):
    return iq[:, lane, 0].astype(float) + 1j * iq[:, lane, 1]


def by_components(x):
    return x.view(np.float64).reshape(len(x), 2)


def audit_lane(stock, traced, timing, iq, lane, center):
    expected = measure(stock, iq, lane, center)
    observed = measure(traced, iq, lane, center)
    if list(map(bytes, expected)) != list(map(bytes, observed)):
        raise ValueError("the timing trace changed a native factor")
    scans = read_trace(traced)
    fit = timing.confirm(iq, lane, center)
    if read_trace(traced) != scans[:1] or len(scans) != 1 + bool(fit.confirmation):
        raise ValueError("the standalone primary scan disagrees with the native two-scan path")
    result = dict(factor_ranks=[f.rank for f in expected])
    if not fit.confirmation:
        return result
    source = complex_lane(iq, lane)
    signed_iq, rotated = timing.cancel(iq, lane, fit.epoch, fit.hz)
    residual = complex_lane(signed_iq, lane)
    second = timing.confirm(signed_iq, lane, center)
    if read_trace(traced) != scans[1:]:
        raise ValueError("standalone signed cancellation changed the residual scout")
    primary = list(blocks(fit.epoch, rotated))
    model, direction = primary_statistics(source, primary)
    result.update(
        primary_epoch=fit.epoch,
        primary_hz=fit.hz,
        primary_block_dots=len(primary),
        epoch_rows_shared=len({row.index for row in scans[0]} & {row.index for row in scans[1]}),
        **correction_error(by_components(source), by_components(model), by_components(residual)),
        **frame_statistics(source, model, residual, timing.fir, center),
    )
    if any(f.rank == 1 for f in expected):
        (factor,) = (f for f in expected if f.rank == 1)
        if not second.confirmation:
            raise ValueError("system returned a residual factor without a residual confirmation")
        _, second_wave = timing.cancel(iq, lane, second.epoch, second.hz)
        target = factor.integer + factor.offset
        result.update(
            residual_epoch=second.epoch,
            residual_hz=second.hz,
            raw_epoch_near_residual=any(
                wrapped_distance(4 * row.index, target) <= 7 for row in scans[0]
            ),
            raw_seed_near_residual=any(
                wrapped_distance(4 * scans[0][i].index, target) <= 7
                and abs(
                    (bin_id if bin_id < 2048 else bin_id - 4096) * 2.5e6 / 4096 + center - factor.hz
                )
                <= 4550
                for i, _, bin_id, _ in ranked(scans[0], range(len(scans[0])))
            ),
            **secondary_statistics(
                residual,
                model - (source - residual),
                direction,
                [region for region, _ in primary],
                blocks(second.epoch, second_wave),
            ),
        )
    return result


def generated(pilot):
    from ...qualification.two_carrier_injections import mix, unit_wave

    rng = np.random.default_rng(813079)
    noise = rng.integers(-75, 76, size=(POINTS, 2, 2), dtype=np.int16)
    one, _ = unit_wave(pilot, 39997, 289_062.5, 72, False)
    far, _ = unit_wave(pilot, 20000, -289_062.5, 93, False)
    close, _ = unit_wave(pilot, 39997, 308_062.5, 125, False)
    both, _ = mix(noise, 0, [(one, 6), (far, 6)])
    return mix(both, 1, [(one, 6), (close, -3)])[0]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("reference", "trace", "assets", "weak"):
        parser.add_argument(name, type=Path)
    args = parser.parse_args()
    if digest(args.reference.read_bytes()) != V3_SHA:
        raise ValueError("unexpected ALGO08v3 reference library")
    results = {
        "reference_sha256": V3_SHA,
        "trace_sha256": digest(args.trace.read_bytes()),
        "assets": {},
        "weak": [],
        "generated": [],
    }
    with ExitStack() as stack:
        radios = {}
        for edge in ("lower", "upper"):
            asset = np.fromfile(args.assets / f"{edge}.f32", dtype="<f4")
            if asset.size != 4 * 13_333 + 81 + 2 * TICKS:
                raise ValueError(f"invalid {edge} pilot asset")
            results["assets"][edge] = digest(asset.tobytes())
            pair = tuple(Receiver(binary, asset) for binary in (args.reference, args.trace))
            for radio in pair:
                stack.callback(radio.close)
            timing = TimingTrace(pair[1], asset)
            stack.callback(timing.close)
            radios[edge] = (*pair, timing)
            iq = generated(timing.pilot.view(np.complex64))
            center = -50_000.0 if edge == "lower" else 50_000.0
            results["generated"].append(
                dict(
                    key=edge,
                    sha256=digest(iq.tobytes()),
                    center=center,
                    lanes=[audit_lane(*radios[edge], iq, lane, center) for lane in (0, 1)],
                )
            )
        for row, iq in read_archive(args.weak, 4):
            target = row["target"]
            center = (
                target["rf_center_hz"]
                - target["lnb_lo_hz"]
                - row["acquisition"]["actual_if_center_hz"]
            )
            results["weak"].append(
                dict(
                    key=row["key"],
                    sha256=row["sha256"],
                    center=center,
                    lanes=[audit_lane(*radios[row["edge"]], iq, lane, center) for lane in (0, 1)],
                )
            )
    print(json.dumps(results, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
