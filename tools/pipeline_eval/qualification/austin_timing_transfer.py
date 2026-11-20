"""Blind stock-four and fifth-center search on shifted Austin RF over sealed roof IQ."""

import argparse
import gzip
import json
from contextlib import ExitStack
from pathlib import Path
from time import perf_counter_ns, process_time_ns

import numpy as np

from ..__main__ import encoded, save_json
from ..variants import center_union
from ..variants.differential_runtime_fft import FftScout
from . import austin_waveform as wave
from . import center_union_gate as gate
from . import ordinary_front_eval
from .prefix_figures import csv_file

REPORT = wave.REPORT.with_name("austin-timing-transfer")
UNION_DIR = Path("/var/tmp/leo-center-union-20261119")
CACHE = Path.home() / ".cache/leo-capture-starts-20261119"
DONORS = dict(lower=("DS29-0519", 157), upper=("DS26-0162", 77))
RATIOS = (-24, -18, -12, -6, 0)
METHODS = ("stock4", "fifth", "sham")
ORIGINS_MS = (0, 20)
SEED = 7442532
SAMPLE_PHASE = 2.0
CFO_TOL_HZ = 1000.0
REPEATS = 3
FRAME_SAMPLES = round(wave.RATE / wave.FRAME_HZ)


def donor_inputs():
    locked = wave.stock.sealed(gate.REPORT, "evidence-lock.json")
    pair = {}
    for edge, (case, visit) in DONORS.items():
        tag = f"{edge}.json.gz"
        if tag not in locked["files"]:
            raise ValueError("missing archive authority for real-background window")
        payload = json.loads(gzip.decompress((gate.REPORT / tag).read_bytes()))
        row = next(r for r in payload["measured"] if (r["case"], r["visit"]) == (case, visit))
        if row["status"] != "processed" or row["edge"] != edge or row["channel"] != 6:
            raise ValueError("background must have the same acquired RF channel and pilot edge")
        path = CACHE / case / f"visit-{visit}.ci16"
        raw = path.read_bytes()
        checksum = wave.digest(raw)
        if checksum != row["iq_sha256"].removeprefix("sha256:") or len(raw) != 1_600_000:
            raise ValueError("archived roof IQ changed")
        pair[edge] = (
            np.frombuffer(raw, dtype="<i2").reshape(-1, 2, 2),
            dict(case=case, visit=visit, sha256=checksum, channel=row["channel"], edge=edge),
        )
    return pair


def schedule():
    rng = np.random.default_rng(SEED)
    return [
        dict(
            edge=edge,
            origin_ms=start,
            rx=(i + j) % 2,
            epoch_shift_samples=int(rng.integers(271, 13062)),
            cfo_shift_hz=int(rng.integers(-60000, 60001)),
        )
        for j, edge in enumerate(wave.EDGE_HZ)
        for i, start in enumerate(ORIGINS_MS)
    ]


def mix(donor, emission, target_rx, ratio_db, *, clean=False):
    output = donor.copy()
    background = donor[:, target_rx, :].astype(np.float32)
    if emission is None:
        return output, None
    target = np.column_stack((emission.real, emission.imag))
    power = np.mean(target * target, dtype=np.float64)
    floor = np.mean(background * background, dtype=np.float64)
    if power <= 0 or floor <= 0:
        raise ValueError("known source and donor must both have nonzero power")
    gain = np.sqrt(floor / power * 10 ** (ratio_db / 10))
    output[:, target_rx, :] = wave.ci16(
        gain * emission + (0 if clean else background[:, 0] + 1j * background[:, 1])
    )[0][:, 0, :]
    return output, float(gain)


def moved(samples, event):
    freq = event["cfo_shift_hz"] / wave.RATE
    spin = np.exp((2j * np.pi * freq) * np.arange(len(samples), dtype=float)).astype(np.complex64)
    return np.roll(samples, event["epoch_shift_samples"]) * spin


def measure(samples, stock, union, scout, edge, index):
    payloads, traces, measured, proposals = {}, {}, {m: [] for m in METHODS}, {}
    for repetition in range(REPEATS):
        offset = (index + repetition) % len(METHODS)
        for mode in METHODS[offset:] + METHODS[:offset]:
            wall, cpu = perf_counter_ns(), process_time_ns()
            if mode == "stock4":
                result, trace, hint = stock.analyze(samples, include_timings=True), None, None
            else:
                hint = tuple(c[0] if c else None for c, _ in scout(samples, edge))
                if mode == "sham":
                    hint = tuple(
                        (h + FRAME_SAMPLES // 2) % FRAME_SAMPLES if h is not None else None
                        for h in hint
                    )
                result, trace = union(samples, hint, timings=True)
            timing = dict(
                cpu_ms=(process_time_ns() - cpu) / 1e6, wall_ms=(perf_counter_ns() - wall) / 1e6
            )
            measured[mode].append(timing)
            signature = ordinary_front_eval._payload(result)
            if (
                encoded(signature) != encoded(payloads.setdefault(mode, signature))
                or trace != traces.setdefault(mode, trace)
                or hint != proposals.setdefault(mode, hint)
            ):
                raise ValueError("matched rerun changed a native candidate or hint")
    baseline, null_trace = union(samples)
    if encoded(baseline) != encoded(payloads["stock4"]):
        raise ValueError("null hint does not exactly preserve stock output")
    for mode in ("fifth", "sham"):
        gate.preserved(null_trace, traces[mode])
    traces["stock4"] = null_trace
    return dict(payloads=payloads, timings=measured, traces=traces, hints=proposals)


def run(archive_path, out):
    if (out / "prediction-lock.json").exists():
        raise FileExistsError("Austin transfer predictions already sealed")
    wave.stock.sealed(wave.REPORT, "score-lock.json")
    wave.stock.sealed(wave.REPORT, "native-lock.json")
    archive, labels, authority = wave.archive(archive_path)
    assets, policy = gate.release(UNION_DIR)
    if policy["library_sha256"]["stock"] != wave.stock.LIBRARY_SHA:
        raise ValueError("folded comparisons must use the same compiled stock detector")
    donors = donor_inputs()
    events = schedule()
    paths = (
        Path(__file__),
        Path(wave.__file__),
        Path(center_union.__file__),
        Path(gate.__file__),
        Path(FftScout.__module__.replace(".", "/") + ".py").resolve(),
        out / "PROTOCOL.md",
    )
    save_json(
        out / "source-lock.json",
        dict(
            files={str(p): wave.stock.digest(p) for p in paths},
            used_libraries={
                k: wave.stock.digest(Path(assets[k])) for k in ("stock", "union", "fftw")
            },
            donor_authority_sha256=wave.stock.digest(gate.REPORT / "evidence-lock.json"),
            waveform_receipt_sha256=wave.stock.digest(wave.REPORT / "score-lock.json"),
            archive_sha256=wave.ARCHIVE_SHA,
            donors={k: v for k, (_, v) in donors.items()},
            perturbation_commitment=wave.digest(encoded(events)),
            power_ratios_db=RATIOS,
            repeats=REPEATS,
        ),
    )
    output = []
    for edge, (donor, _) in donors.items():
        narrow = wave.extract_edge(archive, authority["actual_center_hz"], edge)
        with ExitStack() as stack:
            contexts = gate.bind(stack, assets, edge)
            union = center_union.UnionCall(contexts["union"])
            scout = stack.enter_context(FftScout(assets["fftw"], edge))
            cases = [("donor-only", None, None, None)]
            for event in (e for e in events if e["edge"] == edge):
                start = event["origin_ms"] * wave.RATE // 1000
                emission = moved(narrow[start : start + wave.DWELL_SAMPLES], event)
                cases.extend(("mixed", event, ratio, emission) for ratio in RATIOS)
                cases.append(("clean", event, 0, emission))
            for kind, event, ratio, emission in cases:
                receiver = event["rx"] if event else 0
                mixture, gain = mix(donor, emission, receiver, ratio, clean=kind == "clean")
                result = measure(mixture, contexts["stock"], union, scout, edge, len(output))
                output.append(
                    dict(
                        edge=edge,
                        kind=kind,
                        origin_ms=event["origin_ms"] if event else None,
                        receiver=receiver,
                        ratio_db=ratio,
                        gain=gain,
                        iq_sha256=wave.digest(mixture.tobytes()),
                        **result,
                    )
                )
    wave.stock.pack(out, "native-outputs.jsonl.gz", output)
    names = ("source-lock.json", "native-outputs.jsonl.gz")
    save_json(
        out / "prediction-lock.json",
        dict(files={n: wave.stock.digest(out / n) for n in names}, windows=len(output)),
    )
    score(out, output, events, labels)


def identify(candidate, epoch, cfo):
    e = candidate["epoch"] + candidate["fractional_epoch"]["offset_samples"]
    f = candidate["fractional_epoch"]["tracking_cfo_hz"]
    loss = wave.circular(e - epoch, wave.RATE / wave.FRAME_HZ)
    delta = wave.circular(f - cfo, wave.ALIAS_HZ)
    return abs(loss) <= SAMPLE_PHASE, abs(delta) <= CFO_TOL_HZ


def complete(candidates):
    return [
        c
        for c in candidates
        if c["fractional_epoch"]["status"] == "complete"
        and c["fractional_epoch"]["margin"] >= wave.MARGIN
    ]


def score(out, output, events, labels):
    wave.stock.sealed(out, "prediction-lock.json")
    plan = wave.stock.read(out / "source-lock.json")
    if wave.digest(encoded(events)) != plan["perturbation_commitment"]:
        raise ValueError("timing perturbation truth changed before unblinding")
    known = wave.ordered_frames(labels)
    import csv
    from statistics import median

    with (wave.REPORT / "conditioned-frames.csv").open(newline="") as source:
        frame_frequencies = list(csv.DictReader(source))
    truth = {}
    for e in events:
        edge, offset = e["edge"], e["origin_ms"]
        start = offset / 1000
        phase = min(t for _, t in known if start <= t < start + 0.02)
        baseline = median(
            float(r["mixer_relative_hz"])
            for r in frame_frequencies
            if r["edge"] == edge and r["template"] == "exact"
        )
        truth[edge, offset] = dict(
            e,
            true_epoch_samples=(phase - start) * wave.RATE + e["epoch_shift_samples"],
            true_cfo_hz=baseline + e["cfo_shift_hz"],
        )
    scores = []
    for data in output:
        edge, initial = data["edge"], data["origin_ms"]
        t = truth.get((edge, initial))
        r = data["receiver"]
        for m in METHODS:
            rows = data["payloads"][m]["rows"]
            passes = [complete(row["candidates"]) for row in rows]
            endpoint = max(passes[r], key=lambda c: c["fractional_epoch"]["margin"], default=None)
            target_hits = (
                [identify(c, t["true_epoch_samples"], t["true_cfo_hz"]) for c in passes[r]]
                if t
                else []
            )
            phase, frequency = (
                identify(endpoint, t["true_epoch_samples"], t["true_cfo_hz"])
                if endpoint and t
                else (False, False)
            )
            hinted = data["hints"][m]
            epoch_hint = hinted[r] if hinted is not None else None
            scores.append(
                dict(
                    edge=edge,
                    kind=data["kind"],
                    origin_ms=initial,
                    ratio_db=data["ratio_db"],
                    method=m,
                    planted=t is not None,
                    target_gate_candidates=len(passes[r]),
                    other_gate_candidates=len(passes[1 - r]),
                    target_gate_winner=endpoint is not None,
                    gated_phase_hit=any(p for p, _ in target_hits),
                    gated_phase_cfo_hit=any(p and f for p, f in target_hits),
                    winner_phase_hit=phase,
                    winner_phase_cfo_hit=phase and frequency,
                    off_target_gate_candidates=len(passes[r])
                    - sum(p and f for p, f in target_hits),
                    target_hint=epoch_hint,
                    added_epochs=data["traces"][m][r]["added_epochs"],
                    retained_extra=data["traces"][m][r]["retained_extra"],
                    cpu_ms_median=median(x["cpu_ms"] for x in data["timings"][m]),
                    wall_ms_median=median(x["wall_ms"] for x in data["timings"][m]),
                )
            )
    csv_file(out / "transfer-scores.csv", scores)
    save_json(out / "truth-after-lock.json", list(truth.values()))
    names = ("prediction-lock.json", "transfer-scores.csv", "truth-after-lock.json")
    save_json(out / "score-lock.json", dict(files={n: wave.stock.digest(out / n) for n in names}))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("archive", type=Path)
    p.add_argument("--out", type=Path, default=REPORT)
    options = p.parse_args()
    run(options.archive, options.out)


if __name__ == "__main__":
    main()
