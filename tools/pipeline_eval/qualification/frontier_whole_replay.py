"""Freeze and run the acquisition-frontier whole-recording study."""

import argparse
import shutil
from pathlib import Path

from .. import cavity_runtime, iq_compare, iq_service, whole_iq
from ..__main__ import local_output, save_json
from . import capture_release
from . import exact_wide_iq as earlier
from .full_v5_check import _sha

REPORT = earlier.SCREEN / "acquisition-frontier/whole-replay"
PROTOCOL = REPORT / "PROTOCOL.md"
STOCK_SHA = earlier.LIBRARIES["control"]
STOCK = Path("/srv/bulk/leo-dev/20261119-wide-regional/wide/libleo-adaptive-detector.so")
CORES = {"DS26": [14, 15], "DS29": [22, 23]}
LIMIT_S = 450
METHOD = "frontier-whole-iq"
TITLE = "Acquisition change on held complete IQ"
CAPTION = (
    "Two fresh complete saved-IQ recordings, one per dataset, under 512 MiB and zero swap. "
    "Both branches share phase release. The four original v5 policies use capture-era factors."
)


def history():
    sources = earlier.exclusions()
    for folder, name in (
        ("track-recovery/wide-roster", "prediction-lock.json"),
        ("track-recovery/exact-wide-iq", "source-lock.json"),
        ("factors/iq-to-joint", "source-lock.json"),
        ("next/full-held-pair", "source-lock.json"),
        ("receiver-core/measured-boundary-policy", "source-lock.json"),
        ("track-recovery/bracketed-position", "source-lock.json"),
    ):
        path = earlier.SCREEN / folder / name
        sources[f"{folder}/{name}"] = dict(
            cases=earlier.scheduled(whole_iq.read(path)), sha256=_sha(path)
        )
    return sources


def selected(rows, sources):
    """Select independently of scores, with first segment digest as the ordering key."""
    excluded = {ident for source in sources.values() for ident in source.get("cases", [])}
    cases, ledger = [], {}
    for dataset, cpus in CORES.items():
        pool = earlier.ranked(
            rows, [ident for ident in rows if ident.startswith(dataset)], excluded
        )
        panel = ledger[dataset] = dict(held_candidates=pool, ineligible=[])
        for digest, ident in pool:
            try:
                case, _ = whole_iq.binding(ident)
                capture = capture_release.read_capture(case)
            except (OSError, ValueError) as error:
                panel["ineligible"].append(dict(id=ident, reason=str(error)))
                continue
            panel["selected"] = dict(
                id=ident,
                first_segment_sha256=digest,
                clock_authority=capture["input_manifest_sha256"],
                edge=capture["edge"],
            )
            cases.append(dict(id=ident, cpus=cpus, first="control", cohort="new-holdout"))
            break
        else:
            raise ValueError(f"no eligible complete new capture remains for {dataset}")
    return cases, dict(sources=sources, excluded=sorted(excluded), ranking=ledger)


def freeze(base):
    cases26, digests = earlier.corpus._selection("ds26-common127")
    cases29 = [i for i in earlier.corpus._selection("roof16")[0] if i.startswith("DS29-")]
    inputs = earlier.corpus._index(earlier.corpus._read_frozen("inputs.jsonl", digests))
    cases, authority = selected({i: inputs[i] for i in (*cases26, *cases29)}, history())
    base.mkdir(mode=0o755, exist_ok=False)
    stock = base / "wide-stock.so"
    shutil.copyfile(whole_iq.checked(STOCK, STOCK_SHA), stock)
    receiver = cavity_runtime.install(base / "receiver", profile="phase-release")
    selection_path = REPORT / "selection.json"
    save_json(selection_path, authority)
    spec = dict(
        id=METHOD,
        cases=cases,
        limit_s=LIMIT_S,
        title=TITLE,
        caption=CAPTION,
        control=dict(sha256=STOCK_SHA, label="Stock 21-bin wide"),
        selection_sha256=_sha(selection_path),
        launcher_sha256=_sha(Path(__file__)),
    )
    # The common builder verifies all recording/clock/source bindings. Its stand-in is
    # outside the stock runner and never eligible for execution as the new candidate.
    stock_spec = base / "stock-spec.json"
    save_json(stock_spec, dict(spec, candidate=dict(spec["control"])))
    iq_compare.prepare(
        stock_spec, PROTOCOL, receiver, dict(control=stock, candidate=stock), base / "stock-plan"
    )
    lock = whole_iq.read(base / "stock-plan/source-lock.json")
    lock["spec"] = spec
    lock.pop("spec_sha256")
    lock["detectors"].pop("candidate")
    save_json(REPORT / "prospective-lock.json", lock)
    (base / "prospective-lock.sha256").write_text(_sha(REPORT / "prospective-lock.json") + "\n")
    (base / "runs").mkdir()
    print(cases, flush=True)


def prospective(base):
    lock = whole_iq.read(
        whole_iq.checked(
            REPORT / "prospective-lock.json",
            (base / "prospective-lock.sha256").read_text().strip(),
        )
    )
    whole_iq.checked(PROTOCOL, lock["protocol_sha256"])
    whole_iq.checked(REPORT / "selection.json", lock["spec"]["selection_sha256"])
    return lock


def stock(base, ident):
    lock = prospective(base)
    planned = lock["cases"][ident]
    for name, digest in lock["programs"].items():
        whole_iq.checked(earlier.ROOT / name, digest)
    detector = lock["detectors"]["control"]
    receiver = Path(lock["receiver"])
    if whole_iq.receiver_identity(receiver) != lock["receiver_files"]:
        raise ValueError("installed receiver differs from the prospective stock lock")
    case, _ = whole_iq.binding(ident)
    if (
        planned["request_sha256"] != case["request"]["sha256"]
        or planned["recording"] != case["recording"]
    ):
        raise ValueError("stock request or recording differs from the frozen plan")
    folder = base / "runs" / ident / "control"
    if folder.exists():
        raise FileExistsError(folder)
    try:
        whole_iq.evaluate(
            ident,
            Path(detector["path"]),
            detector["sha256"],
            receiver,
            folder,
            planned["cpus"],
            lock["limit_s"],
        )
    except (FileExistsError, iq_service.UnsettledService):
        raise
    except (OSError, RuntimeError, ValueError) as error:
        if (folder / "service.log").exists() and not (folder / "service.json").exists():
            raise iq_service.UnsettledService(f"terminal state unconfirmed for {folder}") from error
        save_json(folder.parent / "control-failure.json", dict(error=str(error)))
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("freeze", "stock"))
    parser.add_argument("base", type=local_output)
    parser.add_argument("--case")
    args = parser.parse_args()
    if args.action == "freeze":
        freeze(args.base)
    elif args.case:
        stock(args.base, args.case)
    else:
        parser.error("a stock run requires --case")


if __name__ == "__main__":
    main()
