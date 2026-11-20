"""Select and bind held complete recordings for the qualified fifth-center replay."""

import argparse
import shutil
from pathlib import Path

from .. import corpus, iq_service, whole_iq
from ..__main__ import ROOT, local_output, save_json
from . import capture_release, diagnostic_whole, exact_wide_iq, frontier_whole_replay
from .full_v5_check import _sha

SCREEN = exact_wide_iq.SCREEN
REPORT = SCREEN / "support-preserving/whole-center-union"
WORK = Path("/var/tmp/leo-whole-center-union-20261119")
STOCK = frontier_whole_replay.STOCK
STOCK_SHA = frontier_whole_replay.STOCK_SHA
CORES = {"DS26": [4, 5], "DS29": [6, 7]}
RECENT = {"DS26-0237", "DS26-0168", "DS29-0082", "DS29-0604"}
LIMIT_S = 450
METHOD = "whole_center_union"
BASELINE = "whole_center_union_stock"


def history():
    sources = frontier_whole_replay.history()
    for relative in (
        "acquisition-frontier/whole-replay/prospective-lock.json",
        "acquisition-frontier/whole-fftw/source-lock.json",
        "acquisition-frontier/diagnostic-whole/source-lock.json",
    ):
        path = SCREEN / relative
        sources[relative] = dict(
            cases=exact_wide_iq.scheduled(whole_iq.read(path)), sha256=_sha(path)
        )
    return sources


def select(inputs, rosters, sources):
    excluded = RECENT | {ident for row in sources.values() for ident in row.get("cases", [])}
    ledger, cases = {}, {}
    for group, cpus in CORES.items():
        roster = rosters[group]
        pool = exact_wide_iq.ranked(inputs, roster, excluded)
        panel = ledger[group] = dict(eligible_order=pool, full_panel=roster, skipped=[])
        for digest, ident in pool:
            try:
                case, request = whole_iq.binding(ident)
                capture = capture_release.read_capture(case)
            except (OSError, ValueError) as error:
                panel["skipped"].append(dict(id=ident, reason=str(error)))
                continue
            panel["selected"] = dict(id=ident, first_manifest_sha256=digest, band=capture["edge"])
            cases[ident] = dict(
                id=ident,
                cpus=cpus,
                first="control",
                cohort="independent held potential",
                capture_native_sha256=case["native"]["sha256"],
                request_sha256=case["request"]["sha256"],
                catalog_sha256=case["catalog"]["sha256"],
                tile=case["regions"][0],
                recording=case["recording"],
                clock_authority=capture["input_manifest_sha256"],
                orbit_snapshots=request["causal_snapshots"],
            )
            break
        else:
            raise ValueError(f"no previously untested authenticated {group} waveform remains")
    return cases, dict(history=sources, exclusions=sorted(excluded), panels=ledger)


def freeze(work):
    report_path = REPORT / "source-lock.json"
    if report_path.exists():
        raise FileExistsError(report_path)
    cases26, digests = corpus._selection("ds26-common127")
    cases29 = [ident for ident in corpus._selection("roof16")[0] if ident.startswith("DS29-")]
    inputs = corpus._index(corpus._read_frozen("inputs.jsonl", digests))
    cases, selection = select(inputs, {"DS26": cases26, "DS29": cases29}, history())
    work.mkdir(parents=True, exist_ok=False)
    copied = work / "wide-stock.so"
    shutil.copyfile(whole_iq.checked(STOCK, STOCK_SHA), copied)
    whole_iq.checked(copied, STOCK_SHA)
    _, parent = diagnostic_whole.stock_sources()
    receiver = Path(parent["receiver"])
    if (
        whole_iq.receiver_identity(receiver) != parent["receiver_files"]
        or whole_iq.native_sources(receiver) != parent["native_sources"]
    ):
        raise ValueError("installed stock phase release does not match its original receipt")
    selection_path = REPORT / "selection.json"
    save_json(selection_path, selection)
    programs = (
        Path(__file__),
        Path(whole_iq.__file__),
        Path(iq_service.__file__),
        Path(whole_iq.raw.__file__),
        Path(whole_iq.recording.__file__),
        Path(capture_release.__file__),
    )
    lock = dict(
        selection_sha256=_sha(selection_path),
        protocol_sha256=_sha(REPORT / "PROTOCOL.md"),
        cases=cases,
        detectors={"control": dict(path=str(copied), sha256=STOCK_SHA)},
        programs={str(path.relative_to(ROOT)): _sha(path) for path in programs},
        receiver=str(receiver),
        receiver_files=parent["receiver_files"],
        native_sources=parent["native_sources"],
        memory_max=whole_iq.MEMORY,
        swap_max=0,
        limit_s=LIMIT_S,
        original_receiver_prediction_lock=diagnostic_whole.STOCK_PIN,
    )
    save_json(work / "source-lock.json", lock)
    save_json(report_path, lock)
    for ident in cases:
        print(ident, cases[ident]["clock_authority"], flush=True)


def source(work):
    path = REPORT / "source-lock.json"
    lock = whole_iq.read(whole_iq.checked(work / path.name, _sha(path)))
    whole_iq.checked(REPORT / "selection.json", lock["selection_sha256"])
    whole_iq.checked(REPORT / "PROTOCOL.md", lock["protocol_sha256"])
    for name, digest in lock["programs"].items():
        whole_iq.checked(ROOT / name, digest)
    return lock


def service(work, case, role, lock, evaluator=whole_iq.evaluate):
    planned = lock["cases"][case]
    receiver = Path(lock["receiver"])
    if (
        whole_iq.receiver_identity(receiver) != lock["receiver_files"]
        or whole_iq.native_sources(receiver) != lock["native_sources"]
    ):
        raise ValueError("installed phase release changed after freeze")
    det = lock["detectors"][role]
    dest = work / case / role
    dest.parent.mkdir(exist_ok=True)
    terminal = dest / "service.json"
    failure = dest.parent / f"{role}-failure.json"
    if terminal.exists() or failure.exists():
        raise FileExistsError("a bounded terminal attempt already exists")
    try:
        evaluator(
            case,
            Path(det["path"]),
            det["sha256"],
            receiver,
            dest,
            planned["cpus"],
            lock["limit_s"],
        )
    except (FileExistsError, iq_service.UnsettledService):
        raise
    except (OSError, RuntimeError, ValueError) as error:
        if (dest / "service.log").exists() and not terminal.exists():
            raise iq_service.UnsettledService(
                f"terminal service state unconfirmed at {dest}"
            ) from error
        save_json(failure, dict(error=str(error)))
    print(case, role, "failed" if failure.exists() else "completed", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("freeze", "stock"))
    parser.add_argument("--work", type=local_output, default=WORK)
    parser.add_argument("--case")
    args = parser.parse_args()
    if args.action == "freeze":
        freeze(args.work)
    elif args.case:
        service(args.work, args.case, "control", source(args.work))
    else:
        parser.error("--case is required for a stock replay")
