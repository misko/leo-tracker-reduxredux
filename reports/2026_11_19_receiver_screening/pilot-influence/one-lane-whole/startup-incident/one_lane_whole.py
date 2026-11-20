"""Measure one physical antenna per valid RF revisit over two complete recordings."""

import argparse
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from .. import iq_service, whole_iq
from ..__main__ import ROOT, local_output, save_json
from ..variants import one_lane_schedule as policy
from ..variants import selective_capture, single_chain, staggered_native
from . import one_lane_whole_raw, receiver_choice_panel
from . import staggered_reconstruction_trial as parent
from . import whole_center_union as union
from .full_v5_check import _sha

REPORT = union.SCREEN / "pilot-influence/one-lane-whole"
WORK = Path("/var/tmp/leo-one-lane-whole-20261119")
MODULE = "tools.pipeline_eval.qualification.one_lane_whole"
HARD = "DS29-0082"
CPUS = {"DS26": [12, 13], "DS29": [14, 15]}
METHOD = "one_lane_whole"
STOCK = "one_lane_whole_stock"
FRESH = (
    "support-preserving/whole-center-union",
    "arrival-and-timing/fresh-replay",
    "latency-and-support/new-waveforms",
    "receiver-choice/fresh-panel",
    "acquisition-support/fresh-waveform",
)


def select():
    roster = []
    for folder in FRESH:
        path = union.SCREEN / folder / "source-lock.json"
        ((ident, row),) = [
            (key, value)
            for key, value in whole_iq.read(path)["cases"].items()
            if key.startswith("DS26-")
        ]
        roster.append(
            dict(
                id=ident,
                acquisition_sha256=row["recording"]["segments"][0]["sha256"],
                source=folder,
                source_sha256=_sha(path),
            )
        )
    return sorted(roster, key=lambda r: (r["acquisition_sha256"], r["id"]))


def freeze(work):
    roster = select()
    controls, _, stocks, _ = parent.load_controls()
    ids = [roster[0]["id"], HARD]
    release = whole_iq.read(receiver_choice_panel.REPORT / "source-lock.json")
    asset = release["detectors"]["control"]
    binary = whole_iq.checked(Path(asset["path"]), union.STOCK_SHA)
    work.mkdir(parents=True, exist_ok=False)
    plans, cases = {}, {}
    for ident in ids:
        case, request = whole_iq.binding(ident)
        prior = stocks[ident]
        if (
            case["native"]["sha256"] != prior["paired_capture_sha256"]
            or case["request"]["sha256"] != prior["original_request_sha256"]
            or case["catalog"]["sha256"] != prior["catalog_sha256"]
            or case["regions"][0] != prior["tile"]
        ):
            raise ValueError("stock controls differ from the original causal recording authority")
        mapped, _, clock = parent.tune_plan(case)
        ((path, transport, doc),) = parent.measured_source(ident, [prior["native_sha256"]])
        if (
            doc["source"]["input_manifest_sha256"] != clock
            or doc["provenance"]["detector_sha256"] != "sha256:" + union.STOCK_SHA
            or doc["source"]["session_id"] != case["session_id"]
        ):
            raise ValueError("control factors do not bind the actual stock wide binary and capture")
        library = work / "libraries" / ident / "wide-stock.so"
        library.parent.mkdir(parents=True)
        library.write_bytes(binary.read_bytes())
        whole_iq.checked(library, union.STOCK_SHA)
        schedule = library.with_name("dispatch.json")
        save_json(schedule, policy.dispatch(doc, mapped))
        schedule.chmod(0o644)
        kept = dict(
            path=path,
            transport_sha256=transport,
            native_sha256=prior["native_sha256"],
        )
        plans[ident] = dict(path=str(library), sha256=union.STOCK_SHA)
        cases[ident] = dict(
            id=ident,
            capture_native_sha256=case["native"]["sha256"],
            request_sha256=case["request"]["sha256"],
            catalog_sha256=case["catalog"]["sha256"],
            clock_authority=clock,
            recording=case["recording"],
            tile=case["regions"][0],
            orbit_snapshots=request["causal_snapshots"],
            cpus=CPUS[ident[:4]],
            cohort="prespecified hard" if ident == HARD else "manifest-ranked control",
            control=kept,
            dispatch=dict(path=str(schedule), sha256=_sha(schedule)),
        )
    programs = (
        Path(__file__),
        Path(one_lane_whole_raw.__file__),
        Path(policy.__file__),
        Path(single_chain.__file__),
        Path(selective_capture.__file__),
        Path(staggered_native.__file__),
        Path(parent.__file__),
        Path(whole_iq.__file__),
        Path(whole_iq.raw.__file__),
        Path(whole_iq.recording.__file__),
        Path(iq_service.__file__),
        REPORT / "PROTOCOL.md",
    )
    plan = dict(
        cases=cases,
        detectors=plans,
        memory_max=whole_iq.MEMORY,
        swap_max=0,
        limit_s=450,
        policy=policy.POLICY,
        selection=roster,
        prior_stock_lock_sha256=_sha(parent.roster.REPORT / "all-figure-lock.json"),
        prior_stock_prediction_sha256=controls["files"]["all-positions.jsonl.gz"],
        programs={str(p.relative_to(ROOT)): _sha(p) for p in programs},
        **{key: release[key] for key in ("receiver", "receiver_files", "native_sources")},
    )
    for root in (work, REPORT):
        path = root / "source-lock.json"
        save_json(path, plan)
        path.chmod(0o644)
    print(ids, _sha(REPORT / "source-lock.json"), flush=True)


def source(work):
    authority = REPORT / "source-lock.json"
    plan = whole_iq.read(whole_iq.checked(work / authority.name, _sha(authority)))
    for path, digest in plan["programs"].items():
        whole_iq.checked(ROOT / path, digest)
    return plan


def worker(attempt):
    plan = source(attempt.parents[1])
    entry = plan["cases"][attempt.parent.name]
    original = whole_iq.recording.native_document

    def assemble(*args, **kwargs):
        doc, counts = original(*args, **kwargs)
        dispatch = entry["dispatch"]
        visits = whole_iq.read(whole_iq.checked(Path(dispatch["path"]), dispatch["sha256"]))
        mapped, _, _ = parent.tune_plan(entry)
        masked, observed = policy.project(doc, mapped)
        if observed != visits or masked["source"]["probes"] != doc["source"]["probes"]:
            raise ValueError("fresh detector leaked the excluded lane or changed dispatch")
        return masked, counts

    raw = SimpleNamespace(__name__=one_lane_whole_raw.__name__, mark=whole_iq.raw.mark)
    with (
        patch.multiple(whole_iq, raw=raw, MODULE=MODULE),
        patch.object(whole_iq.recording, "native_document", assemble),
    ):
        whole_iq.worker(attempt)


def launch(work, ident):
    plan = source(work)
    row = plan["cases"][ident]
    # The common launch and publication expect the detector role as the dictionary key.
    run = dict(plan, detectors={"candidate": plan["detectors"][ident]})
    whole_iq.checked(Path(row["dispatch"]["path"]), row["dispatch"]["sha256"])
    with patch.object(whole_iq, "MODULE", MODULE), patch.object(iq_service, "MODULE", MODULE):
        union.service(work, ident, "candidate", run, evaluator=whole_iq.evaluate)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("freeze", "run", "worker", "position"))
    parser.add_argument("value", nargs="?")
    parser.add_argument("--work", type=local_output, default=WORK)
    args = parser.parse_args()
    if args.action == "freeze":
        freeze(args.work)
    elif args.action == "run":
        launch(args.work, args.value)
    elif args.action == "worker":
        worker(local_output(args.value))
    else:
        whole_iq.position(local_output(args.value))
