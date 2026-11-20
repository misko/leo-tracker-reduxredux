"""Compare fresh paired v5 fits after substituting two measured wideband IQ windows."""

import argparse
import gzip
import json
import os
import subprocess
from collections import Counter
from hashlib import sha256
from pathlib import Path
from resource import RUSAGE_CHILDREN, getrusage
from tempfile import TemporaryDirectory
from time import perf_counter, process_time

from .. import corpus
from ..__main__ import ROOT, THREAD_ENV, encoded, local_output, save_json, write
from ..scoring import ARMS, distance_km, validate_result
from ..variants import compact_finish
from ..variants.iq_stream import load_windows
from .full_v5_check import (
    BULK,
    PRODUCERS,
    _bind_producer,
    _from_native,
    _from_production,
    _load_case,
    _probe,
    _sha,
)
from .native_geometry_trial import (
    RATE,
    SEQUENCES,
    TIMES,
    _capture_reference,
    _manifest,
    _replay_native,
    compare_ranked,
    ranked_candidate,
)
from .recording_to_v5 import bind_request, digest, save

OUTPUT = ROOT / "reports/2026_11_19_position_atlas/native-geometry"
STAGE = ROOT / "reports/2026_11_19_receiver_streaming/native-geometry"
BINARY = Path("/tmp/leo-native-geometry-20261119/wideband-short/leo-native-adaptive-replay")
CAPTURE_PYTHON = Path(
    "/opt/leo-fast-graph/7cafccaced18e6b0fa9266bd18339d61f0f9c1f4/venv/bin/python"
)
BOUNDARY = "Two archived IQ windows with wideband factors plus capture-era GLRT to both v5 fits"
CONTROL = "archive_control"
CASES = {
    "DS26-0036": (10, (CONTROL, "native_geometry")),
    "DS29-0082": (11, ("native_geometry", CONTROL)),
}
MATCH_M = 1.0
MATCH_HZ = 1e-4


def _metadata(probe):
    return {key: value for key, value in probe.items() if key != "candidates"}


def compose(document, receipt):
    """Replace the measured rows only after binding the exact capture-era control factors."""
    source = document["source"]
    if (
        document["provenance"]["run_id"] != receipt["producer"]["run_id"]
        or source["input_manifest_sha256"] != receipt["producer"]["input_manifest_sha256"]
        or tuple(row["visit"] for row in receipt["windows"]) != SEQUENCES
    ):
        raise ValueError("the new factors do not bind the original capture run and visits")
    rows = {}
    fields = Counter()
    for visit in receipt["windows"]:
        for archive, fresh in zip(visit["production"], visit["wideband"], strict=True):
            key = archive["visit_index"], archive["receiver_id"]
            if (
                key[0] != visit["visit"]
                or key in rows
                or archive["valid_start_counter"] != visit["sample_start"]
                or _metadata(archive) != _metadata(fresh)
            ):
                raise ValueError("a replayed factor has different probe support")
            for before, after in zip(archive["candidates"], fresh["candidates"], strict=True):
                if (
                    before["candidate_rank"] != after["candidate_rank"]
                    or before.keys() != after.keys()
                ):
                    raise ValueError("a replayed factor has different candidate shape")
                fields.update(k for k in before if before[k] != after[k])
            rows[key] = (archive, fresh)
    if set(rows) != {(visit, receiver) for visit in SEQUENCES for receiver in (0, 1)}:
        raise ValueError("the replay needs both receivers at the two recorded visits")

    probes, untouched, changed = [], [], 0
    for probe in source["probes"]:
        key = probe["visit_index"], probe["receiver_id"]
        if key[0] not in SEQUENCES:
            probes.append(probe)
            untouched.append(probe)
            continue
        if key not in rows:
            raise ValueError("duplicate or extra archive probe at a measured visit")
        control, native = rows.pop(key)
        if probe != control:
            raise ValueError("the fresh capture producer differs from the archive")
        probes.append(native)
        changed += int(native != probe)
    if rows or not changed:
        raise ValueError("the archive omitted a bound probe or no native numerical change survived")
    auth = digest(
        [
            "partial-wideband-interval-v1",
            receipt["archive_sha256"],
            receipt["replay_sha256"],
            [(r["iq_sha256"], r["wideband"]) for r in receipt["windows"]],
        ]
    )
    output = dict(
        document,
        source=dict(source, probes=probes, analysis_manifest_sha256=auth),
        provenance=dict(document["provenance"], run_id="replay-" + auth[7:39], scope=BOUNDARY),
    )
    return output, dict(
        changed_probe_rows=changed,
        changed_candidate_fields=dict(fields),
        archived_probe_rows=len(untouched),
        untouched_probes_sha256=digest(untouched),
    )


def replay(case_id, binary):
    import numpy as np

    from leo.analysis.starlink import templates
    from leo.contracts.fast_scan_native import FastScanPolicyV2

    started = perf_counter()
    case = _load_case(case_id)
    stage = STAGE / f"{case_id}.json"
    stage_sha = _sha(stage)
    reference = json.loads(stage.read_bytes())
    replay_sha = _sha(binary)
    policy = FastScanPolicyV2()
    authority = _bind_producer(case, PRODUCERS[case_id], policy)
    location = case["recording"]["segments"][0]
    if (
        reference["case"] != case_id
        or reference["producer"] != authority
        or replay_sha != reference["wideband_replay_sha256"]
        or reference["segment_sha256"] != location["sha256"]
        or reference["archive_audit"]["archive_sha256"] != case["native"]["sha256"]
    ):
        raise ValueError("detector, producer or capture drifted from the earlier stage trial")
    windows = load_windows(
        dict(
            recording_path=str(BULK / location["path"]),
            recording_sha256="sha256:" + location["sha256"],
        ),
        SEQUENCES,
    )
    edge = windows[0].target["edge"]
    for window, recorded in zip(windows, reference["windows"], strict=True):
        if (
            window.sample_rate_hz != RATE
            or window.samples.shape != (TIMES, 2, 2)
            or window.samples.dtype != np.dtype("<i2")
            or window.target["edge"] != edge
            or window.iq_sha256 != recorded["iq_sha256"]
            or window.acquisition["global_visit"] != recorded["visit"]
            or window.acquisition["sample_start"] != recorded["sample_start"]
            or window.acquisition["sample_end"] != recorded["sample_end"]
        ):
            raise ValueError("archived IQ differs from the measured 20 ms input")
    exact, control = (
        np.asarray(templates.qin_edge_pilot_frame(RATE, edge, **kwargs), dtype="<c16")
        for kwargs in ({}, {"symbol_roll": templates.CONTROL_SYMBOL_ROLL})
    )
    if (
        dict(
            exact=sha256(exact.tobytes()).hexdigest(), control=sha256(control.tobytes()).hexdigest()
        )
        != reference["template_sha256"]
    ):
        raise ValueError("pinned pilot templates drifted from the measured input")
    production, geometries = zip(
        *(_capture_reference(window, policy) for window in windows), strict=True
    )
    for geometry, recorded in zip(geometries, reference["windows"], strict=True):
        for key in (
            "receiver_centers_hz",
            "residual_bounds_hz",
            "residual_grid_hz",
            "acquisition_calls",
        ):
            if encoded(geometry[key]) != encoded(recorded["geometry"][key]):
                raise ValueError("fresh detector geometry differs from the measured support")
    with TemporaryDirectory(prefix="wideband-measured-") as scratch:
        manifest = _manifest(Path(scratch), windows, geometries, exact, control)
        calls = _replay_native(binary, manifest, windows)
    rows = []
    for window, recorded, reference_result, call, geometry in zip(
        windows,
        reference["windows"],
        production,
        calls,
        geometries,
        strict=True,
    ):
        baseline, measured = [], []
        for control_probe, native_probe, previous in zip(
            reference_result.receivers,
            call["rows"],
            recorded["comparisons"],
            strict=True,
        ):
            rx = control_probe.receiver_id
            candidates = native_probe["candidates"]
            comparison = compare_ranked(
                [c.model_dump() for c in control_probe.candidates],
                [ranked_candidate(i, c) for i, c in enumerate(candidates)],
            )
            if (
                not comparison["equal_within_tolerance"]
                or comparison != previous["wideband"]["ranked"]
            ):
                raise ValueError("native factor comparison differs from the locked stage receipt")
            baseline.append(_probe(window, rx, map(_from_production, control_probe.candidates)))
            measured.append(
                _probe(window, rx, (_from_native(i, p) for i, p in enumerate(candidates)))
            )
        rows.append(
            dict(
                visit=recorded["visit"],
                iq_sha256=window.iq_sha256,
                sample_start=recorded["sample_start"],
                sample_end=recorded["sample_end"],
                production=baseline,
                wideband=measured,
                production_timing=geometry,
                wideband_timing=dict(
                    wall_s=call["call_wall_ms"] / 1000, cpu_s=call["call_cpu_ms"] / 1000
                ),
            )
        )
    if _sha(binary) != replay_sha or _sha(stage) != stage_sha:
        raise ValueError("a replay dependency changed during measurement")
    return dict(
        case=case_id,
        producer=authority,
        archive_sha256=case["native"]["sha256"],
        stage_sha256=stage_sha,
        replay_sha256=replay_sha,
        windows=rows,
        selective_replay_wall_s=perf_counter() - started,
    )


def _child_cpu():
    usage = getrusage(RUSAGE_CHILDREN)
    return process_time() + usage.ru_utime + usage.ru_stime


def _case(case_id, output, binary):
    cpu, order = CASES[case_id]
    if os.sched_getaffinity(0) != {cpu}:
        raise ValueError(f"{case_id} uses only preregistered CPU {cpu}")
    receipt_path = output / f"{case_id}-factors.json.gz"
    if receipt_path.exists():
        raise ValueError("choose a new directory for another selective measurement")
    subprocess.run(
        [
            str(CAPTURE_PYTHON),
            "-B",
            "-m",
            __spec__.name,
            "--case",
            case_id,
            "--replay-only",
            "--out",
            str(output),
            "--binary",
            str(binary),
        ],
        env=dict(os.environ, **THREAD_ENV, PYTHONPATH=str(PRODUCERS[case_id].root)),
        cwd=ROOT,
        check=True,
        timeout=90,
    )
    receipt = json.loads(gzip.decompress(receipt_path.read_bytes()))
    case = _load_case(case_id)
    archive, catalog = (BULK / case[k]["path"] for k in ("native", "catalog"))
    raw = archive.read_bytes()
    if (
        receipt["archive_sha256"] != sha256(raw).hexdigest()
        or _sha(catalog) != case["catalog"]["sha256"]
    ):
        raise ValueError("the complete archived GLRT or causal catalogue changed")
    composite, audit = compose(json.loads(raw), receipt)
    fits = []
    with TemporaryDirectory(prefix=f"wideband-position-{case_id}-") as scratch:
        folder = Path(scratch)
        composite_file = folder / "composite-native.json"
        save(composite_file, composite)
        for method in order:
            target = folder / method
            target.mkdir()
            control = method == CONTROL
            native = archive if control else composite_file
            bound = bind_request(case, native, target / "request-bound.json")
            start, cpu_start = perf_counter(), _child_cpu()
            result = compact_finish.run(bound, target)
            wall_s, cpu_s = perf_counter() - start, _child_cpu() - cpu_start
            result["boundary"] = (
                "Archival capture-era GLRT to both freshly run v5 fits" if control else BOUNDARY
            )
            timing = "production_timing" if control else "wideband_timing"
            result["metrics"].update(
                measured_windows=len(SEQUENCES),
                fresh_probe_rows=0 if control else 4,
                changed_probe_rows=0 if control else audit["changed_probe_rows"],
                detector_replay_wall_s=sum(r[timing]["wall_s"] for r in receipt["windows"]),
                detector_replay_cpu_s=sum(r[timing]["cpu_s"] for r in receipt["windows"]),
                native_to_v5_wall_s=wall_s,
            )
            for arm, endpoint in result.get("arms", {}).items():
                endpoint["rf_rms_hz"] = result["metrics"].get(f"{arm}_conditional_rms_hz")
            validate_result(result)
            fits.append(
                dict(
                    id=case_id,
                    method=method,
                    cpu=cpu,
                    input_sha256=bound["native_sha256"],
                    implementation_sha256=receipt["producer"]["code_sha256"]
                    if control
                    else receipt["replay_sha256"],
                    source_archive_sha256=receipt["archive_sha256"],
                    downstream="complete v5 compact finish",
                    downstream_source_sha256=_sha(Path(compact_finish.__file__)),
                    detector_receipt_sha256=_sha(receipt_path),
                    catalogue_sha256=case["catalog"]["sha256"],
                    splice_audit=None if control else audit,
                    worker_wall_s=wall_s,
                    worker_cpu_s=cpu_s,
                    result=result,
                )
            )
            save_json(output / f"{case_id}-{method}.json", fits[-1])
            print(case_id, method, result["status"], round(wall_s, 2), flush=True)
    return fits


def pack(output):
    pairs = []
    for case in CASES:
        expected = _load_case(case)
        capture_sha = expected["native"]["sha256"]
        catalog_sha = expected["catalog"]["sha256"]
        measurement_sha = _sha(output / f"{case}-factors.json.gz")
        archive, native = (
            json.loads((output / f"{case}-{method}.json").read_bytes())
            for method in (CONTROL, "native_geometry")
        )
        for method, row in zip((CONTROL, "native_geometry"), (archive, native), strict=True):
            if (
                row["id"] != case
                or row["method"] != method
                or row["source_archive_sha256"] != capture_sha
                or row["catalogue_sha256"] != catalog_sha
                or row["detector_receipt_sha256"] != measurement_sha
                or row["downstream_source_sha256"] != _sha(Path(compact_finish.__file__))
                or row["cpu"] != CASES[case][0]
            ):
                raise ValueError("paired fits differ from the preregistered case and solver")
        if archive["input_sha256"] != "sha256:" + capture_sha or (
            archive["input_sha256"] == native["input_sha256"]
        ):
            raise ValueError("paired fits must bind exact archive and distinct modified inputs")
        pairs.append((archive, native))
    locks = {}
    for index, name in enumerate(("control-positions.jsonl.gz", "positions.jsonl.gz")):
        rows = b"".join(encoded(pair[index]) + b"\n" for pair in pairs)
        data = gzip.compress(rows, mtime=0)
        write(output / name, data)
        locks[name] = sha256(data).hexdigest()
    save_json(output / "position-lock.json", dict(cases=list(CASES), files=locks))

    ids, files = corpus._selection("smoke")
    refs = {r["id"]: r for r in corpus._references(ids, files)}
    comparisons = []
    for archive, native in pairs:
        case = archive["id"]
        for arm in ARMS:
            before, after = (r["result"].get("arms", {}).get(arm, {}) for r in (archive, native))
            p0, p1 = before.get("latlon"), after.get("latlon")
            rms0, rms1 = before.get("rf_rms_hz"), after.get("rf_rms_hz")
            separation = distance_km(p0, p1)
            difference = abs(rms0 - rms1) if rms0 is not None and rms1 is not None else None
            comparisons.append(
                dict(
                    id=case,
                    arm=arm,
                    control_latlon=p0,
                    native_latlon=p1,
                    control_error_km=distance_km(p0, refs[case]["truth"]),
                    native_error_km=distance_km(p1, refs[case]["truth"]),
                    control_rf_rms_hz=rms0,
                    native_rf_rms_hz=rms1,
                    control_final_status=archive["result"]["status"],
                    native_final_status=native["result"]["status"],
                    control_fit_wall_s=archive["worker_wall_s"],
                    native_fit_wall_s=native["worker_wall_s"],
                    control_frequency_score=archive["result"]["metrics"].get(
                        f"{arm}_frequency_score"
                    ),
                    native_frequency_score=native["result"]["metrics"].get(
                        f"{arm}_frequency_score"
                    ),
                    coordinate_displacement_m=None if separation is None else separation * 1000,
                    rf_rms_delta_hz=difference,
                    matched=(
                        archive["result"]["status"] == native["result"]["status"]
                        and separation is not None
                        and separation * 1000 <= MATCH_M
                        and difference is not None
                        and difference <= MATCH_HZ
                    ),
                )
            )
    save_json(output / "comparison.json", comparisons)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--case", choices=CASES)
    p.add_argument("--out", type=Path, default=OUTPUT)
    p.add_argument("--binary", type=Path, default=BINARY)
    p.add_argument("--replay-only", action="store_true")
    p.add_argument("--pack", action="store_true")
    args = p.parse_args()
    output = local_output(args.out)
    output.mkdir(parents=True, exist_ok=True)
    if args.pack:
        pack(output)
    elif args.case is None:
        p.error("provide a preregistered case or pack both finished pairs")
    elif args.replay_only:
        result = replay(args.case, args.binary)
        write(output / f"{args.case}-factors.json.gz", gzip.compress(encoded(result), mtime=0))
    else:
        _case(args.case, output, args.binary.resolve(strict=True))


if __name__ == "__main__":
    main()
