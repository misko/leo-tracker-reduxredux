"""Time independent signed-I/Q to compact-v5 runs on the sealed Gauss recording panel."""

import argparse
import ctypes as ct
import json
import os
import platform
import socket
import subprocess
import tempfile
from concurrent.futures import ProcessPoolExecutor, as_completed
from contextlib import contextmanager
from pathlib import Path
from time import perf_counter, process_time

import numpy as np

from ..variants import portable_field, v5_secant_fit
from ..variants.carrier_continuation import Continuation
from . import recording_to_v5
from .blind_compact_roster import LAST, OUT, WORK, seal
from .full_v5_check import _from_production, _probe, _sha, factor_candidate
from .reverse_glrt_reference import read_bound
from .reverse_glrt_report import read
from .single_scan_position import Factor
from .single_scan_roster import WORK as CHECKED_WORK
from .single_scan_trial import Native
from .timing_first_position import full_identity, raw_windows
from .two_carrier_position import ORIGINAL
from .two_carrier_roster import WORK as TWO_WORK

TRACE = Path(__file__).with_name("cancellation_factor_trace.c")
LIBS = {
    "original": ORIGINAL,
    "checked": CHECKED_WORK / "bin/checked-scan-factors.so",
    "cancellation": WORK / "bin/cancellation-factors.so",
}


def build():
    directory = LIBS["cancellation"].parent
    directory.mkdir(parents=True, exist_ok=True)
    recipe = read(LAST / "builds.json")
    command = list(recipe["builds"]["cancellation-x86-64"]["command"][:-2])
    i = command.index("-lm")
    command[i:i] = [str(TRACE), "-Wl,--wrap=portable_verifier_glrt"]
    command += ["-o", str(LIBS["cancellation"])]
    subprocess.run(command, check=True)
    libs = {m: _sha(p) for m, p in LIBS.items()}
    if (
        libs["original"] != read(ORIGINAL.with_name("reverse-build.json"))["binary"]["sha256"]
        or libs["checked"] != read(LAST / "position-build.json")["binary"]
    ):
        raise ValueError("receiver binary differs from the sealed Gauss measurements")
    assets = {edge: _sha(TWO_WORK / "embedded" / (edge + ".f32")) for edge in ("lower", "upper")}
    if assets != recipe["assets"]:
        raise ValueError("pilot assets changed")
    seal(
        OUT / "build.json",
        dict(
            libraries=libs,
            assets=assets,
            command=command,
            trace_sha256=_sha(TRACE),
            previous_build=_sha(LAST / "builds.json"),
            checked_build=_sha(LAST / "position-build.json"),
            compact_solver_sha256=_sha(Path(v5_secant_fit.__file__)),
            roster_sha256=_sha(OUT / "roster.json"),
        ),
    )


@contextmanager
def detector(method, edge):
    if method == "original":
        with portable_field.Detector(LIBS[method], edge) as original:

            def factors(w):
                return [
                    _probe(w, row.receiver_id, map(_from_production, row.candidates))
                    for row in original(w, w.receiver_ids)
                ]

            yield factors
        return
    asset = np.fromfile(TWO_WORK / "embedded" / (edge + ".f32"), dtype="<f4")
    receiver = Native(LIBS[method], asset)
    template = np.ascontiguousarray(asset[-80000:]).ctypes.data_as(ct.c_void_p)
    fn = (
        receiver.lib.single_scan_factors
        if method == "checked"
        else receiver.lib.cancellation_factors
    )
    fn.argtypes = (
        [ct.c_void_p, ct.c_void_p, ct.c_int, ct.c_double, ct.c_double]
        + ([ct.c_void_p] if method == "checked" else [])
        + [ct.POINTER(Factor)]
    )
    fn.restype = ct.c_int
    continuation = Continuation()

    def factors(w):
        mid = (
            w.target["rf_center_hz"] - w.target["lnb_lo_hz"] - w.acquisition["actual_if_center_hz"]
        )
        rows = []
        for lane in w.receiver_ids:
            vector = (Factor * 2)()
            arguments = [receiver.ctx, w.samples.ctypes.data, lane, mid - 800000, mid + 800000]
            if method == "checked":
                arguments.append(template)
            count = fn(*arguments, vector)
            if not 0 <= count <= 2:
                raise ValueError("native exported factors disagree with the receiver")
            candidates = [
                factor_candidate(
                    v.rank,
                    v.integer,
                    status="complete",
                    offset=v.offset,
                    cfo=v.hz,
                    exact=v.exact,
                    control=v.control,
                    margin=v.exact - v.control,
                )
                for v in vector[:count]
            ]
            if any(not c["passed_fractional_margin_gate"] for c in candidates):
                raise ValueError("receiver admitted an unverified candidate")
            row = _probe(w, lane, candidates)
            _, keep, _ = continuation.select(row)
            rows.append(dict(row, candidates=[] if keep is None else [candidates[keep]]))
        return rows

    try:
        yield factors
    finally:
        receiver.close()


def acquire(case, method, directory, bindings):
    document = read_bound(case["native"])
    source = document["source"]
    metadata = {
        (r["visit_index"], r["receiver_id"]): {k: v for k, v in r.items() if k != "candidates"}
        for r in source.pop("probes")
    }
    excluded = {r["visit"]: r for r in document["provenance"]["excluded_windows"]}
    edge = next(iter(metadata.values()))["edge"]
    iq_hashes, probes = [], []
    detector_wall = detector_cpu = 0.0
    total = case["recording"]["window_count"]
    with detector(method, edge) as receiver:
        for index, w in enumerate(raw_windows(case)):
            acq = w.acquisition
            retune = json.loads(acq["retune_receipt"])
            if (
                index != acq["global_visit"]
                or w.target["edge"] != edge
                or w.sample_rate_hz != 10_000_000
                or tuple(w.receiver_ids) != (0, 1)
                or any(
                    document["delivery_clocks"][index].get(k) != v
                    for k, v in retune["host_delivery_clock"].items()
                )
                or (index == 0 and retune["utc_clock_bracket"] != document["clock_anchor"])
            ):
                raise ValueError("recording clock, RF edge or antenna identity changed")
            iq_hashes.append(w.iq_sha256)
            if index in excluded:
                e = excluded[index]
                if e["iq_sha256"] != w.iq_sha256 or e["sample_start"] != acq["sample_start"]:
                    raise ValueError("excluded recording data changed")
                continue
            if not acq["complete"] or acq["quality_flags"] or w.samples.shape != (200000, 2, 2):
                raise ValueError("unexpected raw quality exclusion")
            start, cpu = perf_counter(), process_time()
            pairs = receiver(w)
            detector_wall += perf_counter() - start
            detector_cpu += process_time() - cpu
            for r in pairs:
                if metadata.pop((index, r["receiver_id"])) != {
                    k: v for k, v in r.items() if k != "candidates"
                }:
                    raise ValueError("fresh observation differs from archived hardware metadata")
                probes.append(r)
            if index % 1000 == 0:
                print(case["id"], method, index, "/", total, flush=True)
    authority = recording_to_v5.digest([source["input_manifest_sha256"], iq_hashes])
    if metadata or total != len(iq_hashes) or source["raw_recording_authority_digest"] != authority:
        raise ValueError("raw recording traversal is incomplete or mismatches its frozen identity")
    signature = recording_to_v5.digest([method, authority, bindings["libraries"][method], probes])
    source.update(probes=probes, analysis_manifest_sha256=signature)
    document["provenance"].update(
        run_id="blind-compact-" + signature[7:39],
        scope=method,
        detector_sha256="sha256:" + bindings["libraries"][method],
    )
    native = directory / "native.json"
    recording_to_v5.save(native, document)
    return dict(
        raw_authority=authority,
        visits=total,
        excluded=len(excluded),
        antenna_probes=len(probes),
        detector_cpu_s=detector_cpu,
        detector_wall_s=detector_wall,
        native_sha256=_sha(native),
        admitted=sum(
            any(v["passed_fractional_margin_gate"] for v in r["candidates"]) for r in probes
        ),
    )


def arm(case, method, cpu, builds):
    root = WORK / "runs" / case["id"] / method
    root.mkdir(parents=True, exist_ok=True)
    done = root / "outcome.json"
    if done.exists():
        prior = read(done)
        if (
            prior["roster_sha256"] != builds["roster_sha256"]
            or prior["build_sha256"] != _sha(OUT / "build.json")
            or prior["prediction_sha256"] != _sha(Path(prior["prediction_path"]))
        ):
            raise ValueError("previous experiment inputs or predictions differ")
        return prior
    directory = Path(tempfile.mkdtemp(prefix="attempt-", dir=root))
    start = perf_counter()
    capture = acquire(case, method, directory, builds)
    mid = perf_counter()
    print(case["id"], method, "acquired", capture["visits"], round(mid - start, 1), "s", flush=True)
    native = directory / "native.json"
    basic = directory / "basic.json"
    public = recording_to_v5.bind_request(case, native, basic)
    req = read(basic)
    req["job"]["identity"]["run_id"] = full_identity(case["id"], req)
    binding = directory / "binding.json"
    recording_to_v5.save(binding, req)
    public["request_path"] = str(binding)
    result = v5_secant_fit.run(public, directory / "solver", "secant")
    prediction = directory / "prediction.json"
    recording_to_v5.save(prediction, result)
    end = perf_counter()
    outcome = dict(
        case=case["id"],
        dataset=case["panel"],
        method=method,
        cpu=cpu,
        acquisition_wall_s=mid - start,
        solver_wall_s=end - mid,
        end_to_end_wall_s=end - start,
        status=result["status"],
        reason=result.get("reason"),
        prediction_path=str(prediction),
        prediction_sha256=_sha(prediction),
        binding_sha256=_sha(binding),
        **capture,
        roster_sha256=builds["roster_sha256"],
        build_sha256=_sha(OUT / "build.json"),
    )
    recording_to_v5.save(done, outcome)
    print(
        case["id"],
        method,
        "solver",
        result["status"],
        result.get("reason"),
        round(end - start, 1),
        "s",
        flush=True,
    )
    return outcome


def lane(row):
    os.sched_setaffinity(0, {row["cpu"]})
    builds = read(OUT / "build.json")
    for method, path in LIBS.items():
        if _sha(path) != builds["libraries"][method]:
            raise ValueError("changed receiver binary")
    for method in row["order"]:
        arm(row["case"], method, row["cpu"], builds)


def run():
    if socket.gethostname().split(".")[0] != "gauss":
        raise ValueError("the pinned end-to-end timing protocol requires Gauss")
    roster = read(OUT / "roster.json")["cases"]
    host = OUT / "host.json"
    if not host.exists():
        seal(
            host,
            dict(
                hostname=socket.gethostname(),
                platform=platform.platform(),
                model=next(
                    v.split(":", 1)[1].strip()
                    for v in Path("/proc/cpuinfo").read_text().splitlines()
                    if v.startswith("model name")
                ),
                performance_cores=Path("/sys/bus/event_source/devices/cpu_core/cpus")
                .read_text()
                .strip(),
                cpu_assignments={r["case"]["id"]: r["cpu"] for r in roster},
                load_at_start=os.getloadavg(),
            ),
        )
    failures = []
    with ProcessPoolExecutor(max_workers=len(roster)) as pool:
        futures = {pool.submit(lane, r): r["case"]["id"] for r in roster}
        for f in as_completed(futures):
            try:
                f.result()
            except Exception as e:
                print("infrastructure error", futures[f], repr(e), flush=True)
                failures.append((futures[f], repr(e)))
    if failures:
        raise RuntimeError(failures)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("build", "run"))
    (build if parser.parse_args().action == "build" else run)()
