"""Authenticate the UT Austin exemplar and replay its Qin edges through stock wide GLRT."""

import argparse
import io
import json
import zlib
from contextlib import ExitStack
from hashlib import sha256
from pathlib import Path
from time import perf_counter, process_time
from zipfile import ZipFile

import numpy as np
import scipy
from scipy.fft import fft, ifft
from scipy.signal import firwin, resample_poly

from leo.analysis.starlink import native_short_window as native
from leo.analysis.starlink import templates

from ..__main__ import ROOT, save_json
from . import waveform_site_trial as stock
from .prefix_figures import csv_file

REPORT = ROOT / "reports/2026_11_19_receiver_screening/arrival-and-timing/austin-waveform"
SOURCE = REPORT.parents[1] / "physical/raw-source-audit.json"
ARCHIVE_SHA = "e3d32aa07944bed69762db4a968c4ea1e045abc9c0a9e8dd65659ef2c8bcaf2f"
BASENAME = "exemplar250-257"
ADC_RATE, RATE = 250_000_000, 10_000_000
DECIMATION = ADC_RATE // RATE
CENTER = 12_075_000_000
EDGE_HZ = dict(lower=CENTER - 115_312_500, upper=CENTER + 115_312_500)
DWELL_SAMPLES = RATE // 50
WINDOWS_MS = (0, 20, 30)
FRAME_HZ = 750
ALIAS_HZ = 1 / 4.4e-6
MODES = ("exact", "roll17", "shuffled")
PANEL = ("physical", "phase-null", "injected")
BASE_SEED = 31848
MARGIN = 0.025
TIME_TOLERANCE_SAMPLES = 10
FREQUENCY_TOLERANCE_HZ = 1000
FIR_TAPS = 801
FINE_NFFT = 32768
FINE_OFFSETS = tuple(range(-3, 4))
WIDE_CFO_HZ = 800_000


def digest(body):
    return sha256(body).hexdigest()


def archive(path, authority=SOURCE):
    audited = stock.read(authority)["ut_austin_raw_exemplar"]
    body = path.read_bytes()
    if len(body) != audited["archive_bytes"] or digest(body) != ARCHIVE_SHA:
        raise ValueError("raw ZIP differs from the frozen primary-source object")
    for rr in audited["http_ranges_verified"]:
        if digest(body[rr["first"] : rr["last"] + 1]) != rr["sha256"]:
            raise ValueError("previously bound primary-source range changed")
    with ZipFile(io.BytesIO(body)) as z:
        data = {}
        for member, checksum in audited["metadata_members_crc_verified"].items():
            raw = z.read(f"{BASENAME}/{member}")
            if digest(raw) != checksum:
                raise ValueError("primary archive metadata differs from previous audit")
            data[member] = raw
        meta = json.loads(data[f"{BASENAME}.json"])
        if (
            float(meta["rate"]) != ADC_RATE
            or meta["otwfmt"] != "sc16"
            or meta["freq"] != meta["freq_IF"]
            or float(meta["freq"]) != audited["actual_center_hz"]
            or float(meta["freq_shift"]) != 0
        ):
            raise ValueError("unsupported or changed source clock/encoding")
        iq = z.read(f"{BASENAME}/{BASENAME}.bin")
        if len(iq) != audited["raw_iq_uncompressed_bytes"] or (
            f"{zlib.crc32(iq):08x}" != audited["raw_iq_member_crc32_declared"]
        ):
            raise ValueError("raw waveform length or primary CRC changed")
    return np.frombuffer(iq, dtype="<i2").reshape(-1, 2), data, audited


def filter_taps():
    return firwin(FIR_TAPS, 4e6, fs=ADC_RATE, window=("kaiser", 8.6)).astype(np.float32)


def extract_edge(raw, sky_center, edge, *, sample_origin=0):
    """Tune a documented Qin lane and anti-alias decimate full-size source I/Q."""
    offset = EDGE_HZ[edge] - sky_center
    if abs(offset) + RATE / 2 >= ADC_RATE / 2:
        raise ValueError("complete narrowband detector support lies beyond the primary RF span")
    if raw.ndim != 2 or raw.shape[1] != 2 or len(raw) % DECIMATION:
        raise ValueError("need aligned interleaved ADC components")
    data = np.empty(len(raw), np.complex64)
    for i in range(0, len(raw), 250_000):
        end = min(i + 250_000, len(raw))
        n = sample_origin + np.arange(i, end, dtype=np.float64)
        data[i:end].real = raw[i:end, 0]
        data[i:end].imag = raw[i:end, 1]
        data[i:end] *= np.exp((-2j * np.pi * offset / ADC_RATE) * n).astype(np.complex64)
    return resample_poly(data, 1, DECIMATION, window=filter_taps())


def ci16(data):
    output = np.empty((len(data), 1, 2), dtype="<i2")
    maximum = max(float(np.max(np.abs(data.real))), float(np.max(np.abs(data.imag))))
    gain = min(1.0, 32000 / max(1.0, maximum))
    output[:, 0, 0] = np.rint(gain * data.real).astype("<i2")
    output[:, 0, 1] = np.rint(gain * data.imag).astype("<i2")
    return output, gain


def templates_at(edge):
    exact = templates.qin_edge_pilot_frame(RATE, edge)
    shifted = templates.qin_edge_pilot_frame(RATE, edge, symbol_roll=templates.CONTROL_SYMBOL_ROLL)
    first, stop, size = 88, 13288, 44
    reshaped = exact[first:stop].reshape(-1, size)
    sham = exact.copy()
    shuffled_control = exact.copy()
    rng = np.random.default_rng(BASE_SEED)
    sham[first:stop] = reshaped[rng.permutation(len(reshaped))].ravel()
    shuffled_control[first:stop] = reshaped[rng.permutation(len(reshaped))].ravel()

    def pair(a, b):
        return np.asarray(a, dtype="<c16"), np.asarray(b, dtype="<c16")

    return {
        "exact": pair(exact, shifted),
        "roll17": pair(shifted, exact),
        "shuffled": pair(sham, shuffled_control),
    }


def phase_null(data, seed):
    rng = np.random.default_rng(seed)
    spectrum = np.abs(fft(data))
    angles = 2 * np.pi * rng.random(len(data))
    return ifft(spectrum * np.exp(1j * angles).astype(np.complex64))


def inject(sky_center, edge, seed):
    """Generate one 250 MS/s truth waveform with the excerpt's sparse occupancy scale."""
    rng = np.random.default_rng(seed)
    phase_s = 0.0007312 if edge == "lower" else 0.0004764
    cfo = 118_250 if edge == "lower" else -78_450
    count = ADC_RATE // 50
    data = rng.normal(0, 370, size=(count, 2)).astype(np.float32)
    tpl = templates.qin_edge_pilot_frame(ADC_RATE, edge)
    base_angle = 2j * np.pi * (EDGE_HZ[edge] - sky_center + cfo) / ADC_RATE
    for tick in (0, 4, 9):
        start = round((phase_s + tick / FRAME_HZ) * ADC_RATE)
        active = 370 * tpl * np.exp(base_angle * np.arange(len(tpl)) + 2j * np.pi * rng.random())
        data[start : start + len(tpl), 0] += active.real
        data[start : start + len(tpl), 1] += active.imag
    return np.rint(data).astype("<i2"), dict(phase_s=phase_s, cfo_hz=cfo, frame_slots=[0, 4, 9])


def frozen(out, evidence, data):
    width = stock.read(stock.LIBRARY.with_name("width-receipt.json"))
    if stock.digest(stock.LIBRARY) != stock.LIBRARY_SHA or width["sha256"] != stock.LIBRARY_SHA:
        raise ValueError("compiled stock detector differs from previously qualified wide build")
    return dict(
        sources={
            str(p): stock.digest(p)
            for p in (
                Path(__file__),
                SOURCE,
                Path(templates.__file__),
                Path(native.__file__),
                out / "PROTOCOL.md",
                stock.LIBRARY.with_name("width-receipt.json"),
            )
        },
        archive_sha256=ARCHIVE_SHA,
        metadata_sha256={name: digest(body) for name, body in data.items()},
        primary_iq_sha256=digest(evidence.tobytes()),
        stock_wide=width,
        frame_template_sha256={
            edge: {m: [digest(v.tobytes()) for v in pair] for m, pair in templates_at(edge).items()}
            for edge in EDGE_HZ
        },
        filter_sha256=digest(filter_taps().tobytes()),
        numpy=np.__version__,
        scipy=scipy.__version__,
        window_offsets_ms=WINDOWS_MS,
        candidate_phase_tolerance_samples=TIME_TOLERANCE_SAMPLES,
        positive_cfo_tolerance_hz=FREQUENCY_TOLERANCE_HZ,
        conditioned_fft=FINE_NFFT,
        conditioned_sample_offsets=FINE_OFFSETS,
    )


def replay(archive_path, out):
    if (out / "native-lock.json").exists():
        raise FileExistsError("Austin blind-window predictions already sealed")
    raw, metadata, authority = archive(archive_path)
    save_json(out / "source-lock.json", frozen(out, raw, metadata))
    center = authority["actual_center_hz"]
    edges, rows, planted_truth = {}, [], {}
    for edge in EDGE_HZ:
        started, cpu = perf_counter(), process_time()
        values = extract_edge(raw, center, edge)
        if len(values) != ADC_RATE // DECIMATION // 20:
            raise ValueError("resampling changed the fixed relative excerpt length")
        edges[edge] = (
            values,
            dict(
                seconds=perf_counter() - started,
                cpu_s=process_time() - cpu,
                offset_hz=EDGE_HZ[edge] - center,
            ),
        )
        cases = []
        for offset in WINDOWS_MS:
            first = offset * RATE // 1000
            data = values[first : first + DWELL_SAMPLES]
            cases.extend(
                (
                    dict(panel="physical", offset_ms=offset, samples=data),
                    dict(
                        panel="phase-null",
                        offset_ms=offset,
                        samples=phase_null(data, BASE_SEED + offset),
                    ),
                )
            )
        planted, truth = inject(center, edge, BASE_SEED + int(edge == "upper"))
        cases.append(
            dict(panel="injected", offset_ms=0, samples=extract_edge(planted, center, edge))
        )
        planted_truth[edge] = truth
        # Fixed blind sequence. Native sees the same single-receiver CI16 shape for every arm.
        rng = np.random.default_rng(BASE_SEED + 4)
        rng.shuffle(cases)
        with ExitStack() as stack:
            detectors = {
                m: stack.enter_context(
                    native.NativeShortWindow(
                        str(stock.LIBRARY),
                        *pair,
                        sample_rate_hz=RATE,
                        receiver_count=1,
                        fractional_epoch=True,
                    )
                )
                for m, pair in templates_at(edge).items()
            }
            for case in cases:
                window, gain = ci16(case["samples"])
                for mode, detector in detectors.items():
                    wall, cpu = perf_counter(), process_time()
                    result = detector.analyze(window, include_timings=True)
                    rows.append(
                        dict(
                            edge=edge,
                            panel=case["panel"],
                            start_ms=case["offset_ms"],
                            template=mode,
                            quantizer_gain=gain,
                            iq_sha256=digest(window.tobytes()),
                            cpu_s=process_time() - cpu,
                            wall_s=perf_counter() - wall,
                            native=result,
                        )
                    )
    stock.pack(out, "native-outputs.jsonl.gz", rows)
    save_json(out / "transform-receipt.json", {edge: meta for edge, (_, meta) in edges.items()})
    names = ("source-lock.json", "native-outputs.jsonl.gz", "transform-receipt.json")
    save_json(
        out / "native-lock.json",
        dict(files={n: stock.digest(out / n) for n in names}, calls=len(rows)),
    )
    score(out, metadata, edges, rows, planted_truth)


def circular(delta, period):
    return (delta + period / 2) % period - period / 2


def ordered_frames(metadata):
    frames = json.loads(metadata["sliceInfo.json"])["frameSet"]
    full = [
        (idx, t)
        for idx, t in zip(frames["index"], frames["toa_s"], strict=True)
        if t >= 0 and t + 1 / FRAME_HZ <= 0.05
    ]
    if len(full) != frames["nWhole"]:
        raise ValueError("published relative frame references and complete waveform disagree")
    return full


def detector_score(rows, known, truth):
    output = []
    for row in rows:
        kind, m = row["panel"], row["template"]
        start = row["start_ms"] / 1000
        selected = (
            [t for _, t in known if start <= t and t + 1 / FRAME_HZ <= start + 0.02]
            if kind == "physical"
            else []
        )
        target = (selected[0] - start) * RATE if selected else None
        if kind == "injected":
            target = truth[row["edge"]]["phase_s"] * RATE
        if target is not None and m == "roll17":
            target -= templates.CONTROL_SYMBOL_ROLL * templates.OFDM_SYMBOL_DURATION_S * RATE
        complete = [
            c
            for c in row["native"]["rows"][0]["candidates"]
            if c["fractional_epoch"]["status"] == "complete"
        ]
        winner = max(complete, key=lambda c: c["fractional_epoch"]["margin"], default=None)
        endpoint = winner["fractional_epoch"] if winner else {}
        epoch = winner["epoch"] + endpoint["offset_samples"] if winner else None
        phase_residual = (
            circular(epoch - target, RATE / FRAME_HZ)
            if epoch is not None and target is not None
            else None
        )
        cfo = endpoint.get("tracking_cfo_hz")
        fold = (
            circular(cfo - truth[row["edge"]]["cfo_hz"], ALIAS_HZ)
            if kind == "injected" and cfo is not None
            else None
        )
        output.append(
            dict(
                edge=row["edge"],
                panel=kind,
                start_ms=row["start_ms"],
                template=m,
                candidates=len(complete),
                margin=endpoint.get("margin"),
                exact_score=endpoint.get("exact_score"),
                control_score=endpoint.get("control_score"),
                passed=bool(endpoint) and endpoint["margin"] >= MARGIN,
                epoch_samples=epoch,
                relative_phase_residual_samples=phase_residual,
                matches_relative_phase=abs(phase_residual) <= TIME_TOLERANCE_SAMPLES
                if phase_residual is not None
                else None,
                folded_known_cfo_error_hz=fold,
                plant_cfo_match=abs(fold) <= FREQUENCY_TOLERANCE_HZ if fold is not None else None,
                acquired_hz=winner.get("acquired_cfo_hz") if winner else None,
                tracking_cfo_hz=cfo,
                whole_author_frames=len(selected),
                detector_cpu_ms=1000 * row["cpu_s"],
            )
        )
    return output


def frame_scores(data, known, edge):
    """Compare equal per-frame hypotheses conditioned on authors' published relative TOA."""
    f = np.fft.fftfreq(FINE_NFFT, d=1 / RATE)
    valid = np.flatnonzero(np.abs(f) <= WIDE_CFO_HZ)
    output = []
    for frame, start in known:
        center = round(start * RATE)
        for m, pair in templates_at(edge).items():
            tpl = pair[0][88:13288]
            energy = float(np.vdot(tpl, tpl).real)
            best = (-1.0, 0, 0.0)
            for offset in FINE_OFFSETS:
                x = data[center + offset + 88 : center + offset + 13288]
                x_energy = float(np.vdot(x, x).real)
                if not x_energy:
                    continue
                search = np.abs(fft(x * tpl.conj(), n=FINE_NFFT)[valid]) ** 2 / (energy * x_energy)
                k = int(search.argmax())
                proposal = (float(search[k]), offset, float(f[valid[k]]))
                best = max(best, proposal)
            output.append(
                dict(
                    edge=edge,
                    frame=frame,
                    template=m,
                    score=best[0],
                    timing_offset_samples=best[1],
                    mixer_relative_hz=best[2],
                    template_hypotheses=len(valid) * len(FINE_OFFSETS),
                )
            )
    return output


def score(out, metadata, edges, rows, planted_truth):
    stock.sealed(out, "native-lock.json")
    known = ordered_frames(metadata)
    prediction = detector_score(rows, known, planted_truth)
    conditioned = [p for edge, (wave, _) in edges.items() for p in frame_scores(wave, known, edge)]
    csv_file(out / "native-scores.csv", prediction)
    csv_file(out / "conditioned-frames.csv", conditioned)
    save_json(
        out / "relative-frame-labels.json",
        dict(author_complete_frames=known, injected=planted_truth),
    )
    names = (
        "native-lock.json",
        "native-scores.csv",
        "conditioned-frames.csv",
        "relative-frame-labels.json",
    )
    save_json(out / "score-lock.json", dict(files={n: stock.digest(out / n) for n in names}))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("archive", type=Path)
    p.add_argument("--out", type=Path, default=REPORT)
    a = p.parse_args()
    replay(a.archive, a.out)


if __name__ == "__main__":
    main()
