"""Recover signed long-aperture CFO at a fixed verified short-primary timing."""

import argparse
import ctypes as ct
import json
import subprocess
from contextlib import ExitStack
from hashlib import sha256
from math import isfinite, remainder, sqrt
from pathlib import Path
from statistics import mean, median

import numpy as np

from tools.pipeline_eval.variants.experimental.receiver_benchmark import read_archive

from .centered_primary import ORIGINAL, PREFIX_PIN, WEAK_PIN
from .mixed_aperture_receiver import INSTALLED_SHA, PILOT_SHA, NativePath, StereoSchedule, verified
from .mixed_aperture_trial import center, encoded, ordered, window
from .scout_readout_trial import check_machine, factor_bytes
from .tail_confirm import PAYLOAD, RELEASE, WEAK_ARCHIVE, build, clock, input_bytes, since

HERE = Path(__file__).resolve().parent
DEVELOPMENT = Path("/dev/shm/leo-v3-catalogue-read-overlap-run01")
HELD = Path("/dev/shm/leo-receiver-ceiling-0169-results01")
SIGNED_FULL = (
    Path("/tmp/ds30-v2-stage-all-6cdbac/DS30-0008/candidate/fast-scan-automatic-work/")
    / "algo08-v2-3dce9426edd1831eade2003d69a00297/detections.json"
)
PINS = {
    "dense_manifest": "ce9b1268764d420a07ed39df83c82a3657084bd221d49636d9e1eb21cbfefa41",
    "dense_full": "2df28e68ea845576ea5e8a02057bce32983dbafb469fa2c4f710a3d89729fa85",
    "dense_short": "7e4c4424e904920dc93fc214d471afdcf3ffde83c34334ec32c59d6cba1e8c40",
    "held_scope": "95a438f0904e4568b6f2a3618b7fbf691c29d0e2d352fd3727cc83d35b72aa9a",
    "held_full": "b1d8a32033373c5996217fe3a70e9e7fe5ae58ba3f75439052eacd2ff55cb453",
    "held_short": "2f9102ffead53766ccc71317243618ff415de7c537cd4bb81b7b8b57488eea13",
}
PERIOD = 13_333
REPEATS = 5
STEPS = (0.25, 0.5, 1.0)
MAX_CHANGE_HZ = 250.0


def file_sha(path):
    return sha256(path.read_bytes()).hexdigest()


def load(path, pin):
    return json.loads(verified(path, pin))


def save(path, result):
    with path.open("x") as stream:
        json.dump(result, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")


def factor_reference(full, short):
    """Fix the science denominator before the candidate frequency can change it."""
    references = [x for x in full if x[0] == 0]
    if len(references) > 1:
        raise ValueError("Long reference has multiple original primary factors")
    if not references:
        return None, None
    (reference,) = references
    phase = remainder(short[1] + short[2] - reference[1] - reference[2], PERIOD)
    frequency = short[3] - reference[3]
    return reference, dict(
        samples=phase, hz=frequency, matched=abs(phase) <= 2 and abs(frequency) <= 250
    )


def amend(short, diagnostics, step, tune):
    """Change only signed CFO when the disjoint tail supports the same branch."""
    if not short or diagnostics is None or not all(map(isfinite, diagnostics)):
        return short, "unavailable"
    full, prefix, tail, prefix_coherence, tail_coherence, exact, rolled, n = diagnostics
    if n < 4 or exact - rolled <= 0.025 or min(prefix_coherence, tail_coherence) < 0.70:
        return short, "tail_support"
    if abs(tail - prefix) > 400 or abs(full) > MAX_CHANGE_HZ:
        return short, "inconsistent"
    (row,) = short
    raised = row[3] + step * full
    if not tune - 800_000 <= raised <= tune + 800_000:
        return short, "alias_boundary"
    return ((*row[:3], raised, *row[4:]),), "updated"


class Refine:
    def __init__(self, binary):
        self.library = ct.CDLL(str(binary))
        call = self.library.short_cfo_refine
        call.argtypes = [
            ct.c_void_p,
            ct.c_void_p,
            ct.c_uint,
            ct.c_uint,
            ct.c_double,
            ct.c_double,
            ct.POINTER(ct.c_double),
        ]
        call.restype = ct.c_int
        self.call = call

    def diagnostics(self, path, iq, lane, short):
        if not short:
            return None
        (row,) = short
        if iq.shape != (200000, 2, 2) or iq.dtype != np.dtype("<i2") or not iq.flags.c_contiguous:
            raise ValueError("Need original full stereo I/Q for local CFO refinement")
        if row[0] != 0 or lane not in (0, 1):
            raise ValueError("Need exactly one original primary and unchanged radio")
        verify = ct.cast(path.native.ctx, ct.POINTER(ct.c_void_p))[1]
        out = (ct.c_double * 8)()
        status = self.call(verify, iq.ctypes.data, lane, row[1], row[2], row[3], out)
        return None if status else tuple(out)


def signed_rows(panel):
    from leo.contracts.fast_scan_native import FastScanPolicyV2
    from leo.scanner.fast_scan_analysis import valid_window_support
    from leo.storage.fast_scan import FastSegmentSource

    if panel == "dense":
        fixture = load(DEVELOPMENT / "fixture.json", PINS["dense_manifest"])
        entry, count = fixture["entry"], 24
        stock = load(SIGNED_FULL, PINS["dense_full"])
        mixed = load(DEVELOPMENT / "natural-a-serial.detections.json", PINS["dense_short"])
        pins = [fixture["iq_sha256"], PINS["dense_short"], PINS["dense_full"]]
    else:
        scope = load(HELD / "scope.json", PINS["held_scope"])
        entry, count = scope["entry"], 64
        stock = load(HELD / "1-stock.json", PINS["held_full"])
        mixed = load(HELD / "1-full-short.json", PINS["held_short"])
        pins = [mixed["iq"], PINS["held_short"], PINS["held_full"]]
        stock, mixed = stock["packet"], mixed["packet"]
    if HELD not in Path(entry["path"]).parents and DEVELOPMENT not in Path(entry["path"]).parents:
        raise ValueError("Only existing tmpfs staging is eligible")
    source = FastSegmentSource(entry, stop_sequence=count)
    probes = [
        {
            (d["visit_index"], d["receiver_id"]): d
            for d in p["source"]["probes"]
            if d["visit_index"] < count
        }
        for p in (stock, mixed)
    ]
    schedule = StereoSchedule(full_coverage=True)
    policy = FastScanPolicyV2()
    names, rows = [], []
    for item in source.windows():
        a, t = item.acquisition, item.target
        names.append(item.iq_sha256)
        if not valid_window_support(a, item.sample_rate_hz, item.samples.shape, (0, 1), policy):
            continue
        key = a["global_visit"]
        _, mode = schedule.visit(t["edge"], t, a)
        for lane in (0, 1):
            references = [p.pop((key, lane)) for p in probes]
            if any(
                (d["valid_start_counter"], d["edge"], d["channel"], d["actual_rf_hz"])
                != (
                    a["sample_start"],
                    t["edge"],
                    t["channel"],
                    a["actual_if_center_hz"] + t["lnb_lo_hz"],
                )
                for d in references
            ):
                raise ValueError("Staged radio or timing is outside the signed opportunity")
            rows.append(
                dict(
                    key=key,
                    edge=t["edge"],
                    lane=lane,
                    iq=item.samples,
                    tune=t["rf_center_hz"] - t["lnb_lo_hz"] - a["actual_if_center_hz"],
                    mode=mode,
                    stock=encoded(references[0]),
                    short=encoded(references[1]),
                )
            )
    if any(probes) or names != pins[0]:
        raise ValueError("Staged window digest or signed opportunity roster changed")
    return rows, dict(
        iq=names,
        stock_sha256=pins[2],
        short_sha256=pins[1],
        manifest_sha256=entry["manifest_digest"],
    )


def weak_rows(output):
    staged = output / "weak-clips.zip"
    with staged.open("xb") as out:
        subprocess.run(
            [
                "/usr/bin/python3",
                HERE / "centered_primary_cached.py",
                WEAK_ARCHIVE,
                str(24 * 1024**2),
            ],
            stdout=out,
            check=True,
            timeout=10,
        )
    verified(staged, WEAK_PIN)
    rows = []
    for metadata, samples in read_archive(staged, 18):
        visit = window(metadata, samples)
        for lane in (0, 1):
            rows.append(
                dict(
                    key=metadata["key"],
                    edge=metadata["edge"],
                    lane=lane,
                    iq=samples,
                    tune=center(visit),
                    mode="short_primary",
                    stock=None,
                    short=None,
                )
            )
    if len(rows) != 36:
        raise ValueError("Weak signed clip scope is incomplete")
    return rows, dict(weak_fixture_sha256=WEAK_PIN, logical_bytes=staged.stat().st_size)


def measure(rows, refine, Native, steps):
    results = []
    total = [
        dict(short_cpu_ns=0, short_wall_ns=0, increment_cpu_ns=0, increment_wall_ns=0)
        for _ in range(REPEATS)
    ]
    for index, row in enumerate(rows):
        lane, tune, iq = (row[k] for k in ("lane", "tune", "iq"))
        full, full_time = Native[row["edge"], "full"].run(iq, lane, tune)
        expected_full = row["stock"]
        if expected_full is not None and any(
            factor_bytes((f,)) not in {factor_bytes((x,)) for x in full} for f in expected_full
        ):
            raise ValueError(f"Installed signed reference changed at {row['key']}/{lane}")
        if row["mode"] == "full":
            if factor_bytes(ordered(full)) != factor_bytes(row["short"]):
                raise ValueError("Scheduled full anchor changed")
            continue
        short_path = Native[row["edge"], "short_primary"]
        last = None
        for rep in range(REPEATS):
            for adjusted in (True, False) if (index + rep) % 2 else (False, True):
                factor, ticks = short_path.run(iq, lane, tune)
                if row["short"] is not None and factor_bytes(factor) != factor_bytes(row["short"]):
                    raise ValueError(f"Signed short reference changed at {row['key']}/{lane}")
                if adjusted:
                    start = clock()
                    diagnostics = refine.diagnostics(Native[row["edge"], "full"], iq, lane, factor)
                    choices = {str(step): amend(factor, diagnostics, step, tune) for step in steps}
                    cost = since(start)
                    total[rep]["increment_cpu_ns"] += cost[0]
                    total[rep]["increment_wall_ns"] += cost[1]
                    current = factor, diagnostics, choices
                    if last is not None and last != current:
                        raise ValueError(
                            "Fixed-coordinate waveform refinement changed between repeats"
                        )
                    last = current
                else:
                    total[rep]["short_cpu_ns"] += ticks[0]
                    total[rep]["short_wall_ns"] += ticks[1]
        short, diagnostics, choices = last
        for updated, _ in choices.values():
            if len(updated) != len(short) or any(
                a[:3] + a[4:] != b[:3] + b[4:] for a, b in zip(updated, short, strict=True)
            ):
                raise ValueError("Refinement changed support, timing or original margins")
        reference, comparison = factor_reference(full, short[0]) if short else (None, None)
        results.append(
            dict(
                key=row["key"],
                lane=lane,
                edge=row["edge"],
                short=short,
                stock=reference,
                strongest=ordered(full),
                match=comparison,
                diagnostics=diagnostics,
                choices=choices,
                full_diagnostic_ns=full_time,
            )
        )
    return dict(rows=results, times=total)


def summary(rows, step):
    key = str(step)
    positives = [r for r in rows if r["short"]]
    common = [r for r in positives if r["match"] and r["match"]["matched"]]
    if not common:
        raise ValueError("No fixed short-to-full primary counterparts")
    before = [r["match"]["hz"] for r in common]
    after = [r["choices"][key][0][0][3] - r["stock"][3] for r in common]
    improved = sum(abs(a) < abs(b) for a, b in zip(after, before, strict=True))
    return dict(
        opportunities=len(rows),
        short_positives=len(positives),
        retained=len(positives),
        updated=sum(r["choices"][key][1] == "updated" for r in positives),
        matched=len(common),
        updated_matched=sum(r["choices"][key][1] == "updated" for r in common),
        improved=improved,
        degraded=sum(abs(a) > abs(b) for a, b in zip(after, before, strict=True)),
        strict_majority=2 * improved > len(common),
        bias_hz=[mean(before), mean(after)],
        median_signed_hz=[median(before), median(after)],
        median_abs_hz=[median(map(abs, before)), median(map(abs, after))],
        rms_hz=[sqrt(mean(v * v for v in values)) for values in (before, after)],
        median_abs_epoch_difference_samples=median(abs(r["match"]["samples"]) for r in common),
    )


def run(output, *, freeze_path=None):
    machine = check_machine()
    output.mkdir()
    installed, short = PAYLOAD / "receiver.so", ORIGINAL / "short-primary.so"
    verified(installed, INSTALLED_SHA)
    verified(short, PREFIX_PIN)
    source = HERE / "short_cfo_refine.inc"
    driver = file_sha(Path(__file__))
    if freeze_path is not None:
        freeze = json.loads(freeze_path.read_bytes())
        if freeze["driver_sha256"] != driver or freeze["extension_sha256"] != file_sha(source):
            raise ValueError("Held entry requires the frozen development implementation")
        steps = (freeze["step"],)
        panels = ("held-0169",)
    else:
        steps, panels = STEPS, ("dense", "weak")
    start = clock()
    binary, identity = build(output / "build", installed, source)
    compile_time = since(start)
    results = {}
    with ExitStack() as stack:
        native = {}
        for edge, pin in PILOT_SHA.items():
            asset = np.frombuffer(verified(RELEASE / "assets" / f"{edge}.f32", pin), dtype="<f4")
            for mode, library in (("full", installed), ("short_primary", short)):
                path = NativePath(library, asset, mode)
                stack.callback(path.close)
                native[edge, mode] = path
        refine = Refine(binary)
        for name in panels:
            start, io = clock(), input_bytes()
            clips, scope = weak_rows(output) if name == "weak" else signed_rows(name)
            intake = since(start)
            if input_bytes() != io:
                raise ValueError("Clip intake touched block storage")
            results[name] = measure(clips, refine, native, steps) | dict(
                scope=scope, intake_ns=intake
            )
            del clips
    all_rows = [r for p in results.values() for r in p["rows"]]
    scores = {str(step): summary(all_rows, step) for step in steps}
    for data in results.values():
        data["summary"] = {str(step): summary(data["rows"], step) for step in steps}
    result = dict(
        machine=machine,
        build=identity,
        compile_ns=compile_time,
        driver_sha256=driver,
        freeze_sha256=file_sha(freeze_path) if freeze_path else None,
        panels=results,
        summary=scores,
    )
    save(output / "result.json", result)
    if not freeze_path:
        eligible = [
            step
            for step in steps
            if scores[str(step)]["strict_majority"]
            and scores[str(step)]["rms_hz"][1] < scores[str(step)]["rms_hz"][0]
        ]
        selected = (
            min(eligible, key=lambda x: scores[str(x)]["rms_hz"][1]) if eligible else steps[0]
        )
        save(
            output / "freeze.json",
            dict(
                step=selected,
                eligible=eligible,
                driver_sha256=driver,
                extension_sha256=file_sha(source),
                result_sha256=file_sha(output / "result.json"),
            ),
        )


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("output", type=Path)
    cli.add_argument("--freeze", type=Path)
    args = cli.parse_args()
    run(args.output, freeze_path=args.freeze)
