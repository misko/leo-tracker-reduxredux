"""Execute one genuine capped arrival-paced replay of the fused detector."""

import argparse
from contextlib import contextmanager
from pathlib import Path
from threading import local
from unittest.mock import patch

from .. import whole_iq
from ..__main__ import ROOT, local_output, save_json, write
from ..variants.dual_lane import DualLane
from . import arrival_queue as pace
from .full_v5_check import _sha

CASE = "DS26-0026"
MAIN, HELPER = 20, 21
MODE = "candidate"
METHOD = "combined_native_fifth"
MODULE = "tools.pipeline_eval.qualification.combined_native_pace"
REPORT = ROOT / "reports/2026_11_19_receiver_screening/latency-and-support/combined-native"
PACED = REPORT / "paced"
LIBRARY = "libleo-dual-lane.so"
DETECTOR = "libleo-adaptive-detector.so.1"


def freeze(work):
    from . import combined_native_eval as evaluation
    from . import fresh_adaptive as historical
    from . import fresh_replay

    native_lock = REPORT / "native-source-lock.json"
    qualified = whole_iq.read(work / "native-results.json")
    if qualified["source_lock_sha256"] != _sha(native_lock) or set(qualified["cases"]) != set(
        evaluation.CASES
    ):
        raise ValueError("complete local exact detector gate is absent")
    observed = [
        pair
        for case in qualified["cases"].values()
        for row in case["rows"]
        for pairs in row["modes"].values()
        for pair in pairs
    ]
    required = len(evaluation.CASES) * (48 * 2 + 3 * 3) * 3
    if len(observed) != required or not all(evaluation.same_roles(pair) for pair in observed):
        raise ValueError("fused detector did not pass the sealed paired roster")
    plan = whole_iq.read(historical.REPORT / "DS26-0026-source-lock.json")
    old = plan["cases"][CASE]
    branch = old["modes"]["fifth"]
    cutoff = whole_iq.checked(historical.REPORT / branch["events"], branch["sha256"])
    original_plan = fresh_replay.REPORT / "source-lock.json"
    reference, _, lineage = historical.checked_inputs(
        fresh_replay.WORK, whole_iq.read(original_plan), CASE
    )
    if lineage != old["parents"]:
        raise ValueError("fifth source did not retain the full authenticated waveform")
    old_join = pace.readgz(cutoff)
    for joined, sealed in zip(old_join, reference["fifth"], strict=True):
        science = {k: v for k, v in joined.items() if k not in ("stock", "fifth")}
        if (
            any(sealed[k] != v for k, v in science.items())
            or sealed["full_visit_sha256"] != joined["fifth"]
        ):
            raise ValueError("prior independently measured fifth envelope did not bind its arrival")
    PACED.mkdir(exist_ok=False)
    events = PACED / "DS26-0026-fifth-reference.json.gz"
    pace.writegz(events, reference["fifth"])
    source = PACED / "source-lock.json"
    built = work / "build/build.json"
    closure = whole_iq.read(built)
    assets = {
        name: dict(path=str(whole_iq.checked(built.parent / name, digest)), sha256=digest)
        for name, digest in closure["files"].items()
    }
    programs = (
        Path(__file__),
        Path(pace.__file__),
        Path(evaluation.__file__),
        Path(historical.__file__),
        Path(ROOT / "tools/pipeline_eval/variants/dual_lane.py"),
        native_lock,
        built,
        historical.REPORT / "DS26-0026-source-lock.json",
        original_plan,
        REPORT / "PROTOCOL.md",
    )
    save_json(
        source,
        dict(
            cases={
                CASE: dict(
                    old, cpu=MAIN, modes={MODE: dict(events=events.name, sha256=_sha(events))}
                )
            },
            local_pair_sha256=_sha(work / "native-results.json"),
            assets=assets,
            programs={str(p): _sha(p) for p in programs},
            cpus=[MAIN, HELPER],
            historical_reference=dict(
                core=18, order=["adaptive", "fifth"], cutoff_sha256=_sha(cutoff)
            ),
            memory_max=whole_iq.MEMORY,
            memory_swap_max=0,
            limit_s=pace.LIMIT_S,
            waiting_slots=pace.WAITING,
        ),
    )
    save_json(work / "launch-lock.json", dict(source_lock_sha256=_sha(source)))


@contextmanager
def raw_configuration():
    counters = local()
    original = pace.native_visit

    def detector(capture, mode, assets, stack):
        if mode != MODE:
            raise ValueError("one paced attempt was declared for fifth mode")
        lib = whole_iq.checked(Path(assets[LIBRARY]["path"]), assets[LIBRARY]["sha256"])
        whole_iq.checked(Path(assets[DETECTOR]["path"]), assets[DETECTOR]["sha256"])
        native = stack.enter_context(DualLane(lib, capture["edge"], helper_cpu=HELPER))

        def detect(samples):
            result, profile = native.analyze(samples, "fifth", trace=True)
            a, b = profile["lanes"]
            if (a["cpu"], b["cpu"]) != (MAIN, HELPER):
                raise ValueError("paced dual native worker lost its declared physical cores")
            counters.helper = b["cpu_ns"]
            return result

        return detect

    def native_visit(frame, analyze, detect, policy):
        counters.helper = 0
        packet, (wall, caller) = original(frame, analyze, detect, policy)
        return packet, (wall, caller + counters.helper)

    with patch.multiple(
        pace,
        CPUS={CASE: MAIN},
        MODES=(MODE,),
        MODULE=MODULE,
        build_native=detector,
        native_visit=native_visit,
    ):
        yield


def raw(work):
    with raw_configuration():
        pace.replay(work, PACED)


def fit(work):
    from . import adaptive_arrival_position as emitted
    from . import fresh_adaptive as historical
    from . import fresh_replay, support_cross_trial
    from .arrival_queue_results import observed, terminal
    from .fractional_runtime_whole import verify_request
    from .phase_support_results import pack

    planned = pace.plan(work, PACED)
    spec = planned["cases"][CASE]
    bound = spec["modes"][MODE]
    events = pace.readgz(whole_iq.checked(PACED / bound["events"], bound["sha256"]))
    attempt = work / CASE / MODE
    trace, witness, service, ok = terminal(attempt, events)
    pace.writegz(PACED / "trace.json.gz", trace)
    save_json(PACED / "raw-summary.json", observed(trace, witness, CASE, METHOD, ok, events))
    save_json(PACED / "raw-service.json", service)
    save_json(PACED / "raw-witness.json", witness)
    if not ok:
        raise ValueError("the single paced replay lacks a complete verified capture")
    release = whole_iq.read(fresh_replay.REPORT / "source-lock.json")
    refs, docs, parents = historical.checked_inputs(fresh_replay.WORK, release, CASE)
    if parents != spec["parents"] or refs["fifth"] != events:
        raise ValueError("actual run was not verified against the frozen complete fifth branch")
    reference_lock = whole_iq.read(fresh_replay.REPORT / "prediction-lock.json")
    emitted.verify_original_packet_hashes(
        whole_iq.checked(
            fresh_replay.REPORT / "visits.jsonl.gz", reference_lock["files"]["visits.jsonl.gz"]
        ),
        CASE,
        docs,
        refs,
    )
    probes = emitted.matched_probes(docs)["fifth"]
    chosen = [r["visit"] for r in trace if r["outcome"] == "emitted"]
    if not chosen or not set(chosen) <= probes.keys():
        raise ValueError("paced emissions do not identify complete physical probe pairs")
    retained = [p for visit in chosen for p in probes[visit]]
    base = docs["fifth"]
    physics = release["cases"][CASE]
    physical = pace.recording_to_v5.digest(
        [METHOD, witness["output_sha256"], parents["fifth"], chosen]
    )
    candidate_sha = "sha256:" + planned["assets"][DETECTOR]["sha256"]
    doc = dict(
        base,
        source=dict(base["source"], probes=retained, analysis_manifest_sha256=physical),
        provenance=dict(
            base["provenance"],
            scope="Fifth native factors from byte-verified actual fused paced outputs",
            detector_sha256=candidate_sha,
            run_id="replay-" + physical[7:39],
            processed_windows=len(chosen),
        ),
    )
    condition = "position-fused"
    folder = work / CASE / condition
    recording = folder / "recording"
    recording.mkdir(parents=True, exist_ok=False)
    native = recording / "native.json"
    write(native, (pace.recording_to_v5.encoded(doc) + "\n").encode())
    request = recording / "request.json"
    with fresh_replay.patched_case(release):
        case, prior = whole_iq.binding(CASE)
    digest = whole_iq.recording.bind_request(case, native, request)["native_sha256"]
    verify_request(whole_iq.read(request), prior, native_path=native, native_sha256=digest)
    row = dict(
        id=CASE,
        condition=condition,
        mode="matched-tile",
        method=METHOD,
        cpu=MAIN,
        tile=physics["tile"],
        catalog_sha256=physics["catalog_sha256"],
        paired_capture_sha256=physics["capture_native_sha256"],
        original_request_sha256=physics["request_sha256"],
        native_sha256=_sha(native),
        request_sha256=_sha(request),
        emitted=len(chosen),
        verified_raw_envelope_sha256=witness["output_sha256"],
    )
    save_json(
        PACED / "position-input-lock.json",
        dict(
            row=row,
            archive=parents,
            memory_max=whole_iq.MEMORY,
            limit_s=support_cross_trial.LIMIT,
            program_sha256=_sha(Path(__file__)),
        ),
    )
    save_json(folder / "plan.json", {"receiver": release["receiver"]})
    save_json(folder / "raw.json", dict(native_sha256=digest, request_sha256=_sha(request)))
    measured = support_cross_trial.service(work, row)
    pack(PACED / "positions.jsonl.gz", [measured])
    files = (
        "source-lock.json",
        "raw-summary.json",
        "raw-service.json",
        "raw-witness.json",
        "trace.json.gz",
        "position-input-lock.json",
        "positions.jsonl.gz",
        bound["events"],
    )
    save_json(
        PACED / "position-lock.json", dict(files={n: _sha(PACED / n) for n in files}, cases=[CASE])
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("action", choices=("freeze", "raw", "fit", "worker"))
    p.add_argument("work", type=local_output)
    arguments = p.parse_args()
    if arguments.action == "worker":
        with raw_configuration():
            pace.execute(arguments.work)
    else:
        {"freeze": freeze, "raw": raw, "fit": fit}[arguments.action](arguments.work)
