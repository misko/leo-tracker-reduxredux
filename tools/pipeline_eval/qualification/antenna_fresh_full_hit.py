"""Bind a fresh partner-on-hit service to its own preceding stock raw capture."""

import argparse
import shutil
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from .. import whole_iq
from ..__main__ import ROOT, local_output, save_json, write
from ..variants import one_lane_schedule, single_chain
from . import antenna_fresh_full as trial
from . import on_hit_waveforms, on_hit_waveforms_raw, one_lane_whole_raw
from . import second_on_miss_whole as service
from . import second_on_miss_whole_raw as predecessor
from .full_v5_check import _sha
from .staggered_reconstruction_trial import tune_plan

MODULE = "tools.pipeline_eval.qualification.antenna_fresh_full_hit"


def roots(work, ident):
    return work / "hit-runtime" / ident, trial.REPORT / "dispatch" / ident


def stage(work, ident, stock_plan):
    root, report = roots(work, ident)
    dest = report / "source-lock.json"
    if dest.exists():
        raise FileExistsError("candidate dispatch is already frozen")
    stock = work / ident / "control"
    entry = stock_plan["cases"][ident]
    measured = whole_iq.read(stock / "raw.json")
    source = whole_iq.checked(stock / "recording/native.json", measured["native_sha256"])
    document = whole_iq.read(source)
    mapped, _, clock = tune_plan(entry)
    binary = stock_plan["detectors"]["control"]
    if (
        entry["clock_authority"] != clock
        or document["source"]["input_manifest_sha256"] != clock
        or document["source"]["session_id"] != entry["case"]["session_id"]
        or document["provenance"]["detector_sha256"] != "sha256:" + binary["sha256"]
    ):
        raise ValueError("completed stock native factors have a different waveform or detector")
    lib = root / "libraries" / ident / "wide-stock.so"
    lib.parent.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(whole_iq.checked(Path(binary["path"]), binary["sha256"]), lib)
    whole_iq.checked(lib, binary["sha256"])
    schedule = lib.with_name("dispatch.json")
    save_json(schedule, one_lane_schedule.dispatch(document, mapped))
    schedule.chmod(0o644)
    write(report / schedule.name, schedule.read_bytes())
    owned = (
        Path(__file__),
        Path(on_hit_waveforms_raw.__file__),
        Path(on_hit_waveforms.__file__),
        Path(one_lane_whole_raw.__file__),
        Path(predecessor.__file__),
        Path(service.__file__),
        Path(single_chain.__file__),
    )
    case = dict(
        entry,
        dispatch=dict(path=str(schedule), sha256=_sha(schedule)),
        stock_analysis_sha256=document["source"]["analysis_manifest_sha256"],
        stock_native_sha256=_sha(source),
        stock_raw_receipt_sha256=_sha(stock / "raw.json"),
    )
    plan = dict(
        stock_plan,
        cases={ident: case},
        detectors={ident: dict(path=str(lib), sha256=binary["sha256"])},
        programs=stock_plan["programs"] | {str(p.relative_to(ROOT)): _sha(p) for p in owned},
        stock_source_sha256=_sha(trial.REPORT / "source-lock.json"),
    )
    for path in (root / dest.name, dest):
        save_json(path, plan)
        path.chmod(0o644)


def source(work, ident):
    root, report = roots(work, ident)
    name = "source-lock.json"
    plan = whole_iq.read(whole_iq.checked(root / name, _sha(report / name)))
    whole_iq.checked(trial.REPORT / name, plan["stock_source_sha256"])
    for path, digest in plan["programs"].items():
        whole_iq.checked(ROOT / path, digest)
    entry = plan["cases"][ident]
    whole_iq.checked(work / ident / "control/raw.json", entry["stock_raw_receipt_sha256"])
    whole_iq.checked(report / "dispatch.json", entry["dispatch"]["sha256"])
    return plan


@contextmanager
def configured(work, ident):
    plan = source(work, ident)
    case = plan["cases"][ident]
    intent = case["dispatch"]
    visits = whole_iq.read(whole_iq.checked(Path(intent["path"]), intent["sha256"]))
    policy = SimpleNamespace(
        needs_partner=on_hit_waveforms_raw.needs_partner,
        mark=lambda doc, probes: on_hit_waveforms.mark(
            doc, probes, case["stock_analysis_sha256"], visits
        ),
    )
    with (
        trial.whole.patched_case(plan),
        patch.object(
            whole_iq.recording, "_load_case", lambda key: trial.whole.local_case(plan, key)
        ),
        patch.multiple(
            service,
            MODULE=MODULE,
            raw=on_hit_waveforms_raw,
            source=lambda _: plan,
            second_on_miss=policy,
        ),
    ):
        yield


def launch(work, ident):
    plan = trial.whole.source(work)
    stock = work / ident / "control"
    if not (
        (stock / "service.json").is_file() or (stock.parent / "control-failure.json").is_file()
    ):
        raise ValueError("the same-core stock replay must be terminal before candidate work")
    if not (stock / "raw.json").is_file():
        save_json(
            stock.parent / "candidate-failure.json",
            dict(
                error="stock raw visit metadata unavailable for predeclared primary dispatch",
                status="unavailable",
            ),
        )
        return
    if not (roots(work, ident)[1] / "source-lock.json").is_file():
        stage(work, ident, plan)
    with configured(work, ident):
        service.run(work, ident)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("run", "worker", "position"))
    parser.add_argument("value")
    parser.add_argument("--work", type=local_output, default=trial.WORK)
    args = parser.parse_args()
    if args.action == "run":
        with trial.context():
            launch(args.work, args.value)
    elif args.action == "worker":
        attempt = local_output(args.value)
        with configured(attempt.parents[1], attempt.parent.name):
            service.worker(attempt)
    else:
        whole_iq.position(local_output(args.value))
