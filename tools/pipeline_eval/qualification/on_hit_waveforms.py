"""Select and replay independent complete waveforms with the fixed partner-on-hit policy."""

import argparse
import shutil
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from .. import whole_iq
from ..__main__ import ROOT, local_output, save_json
from ..variants import one_lane_schedule, partner_on_hit
from . import capture_release, on_hit_waveforms_raw, one_lane_roster, partner_on_hit_trial
from . import second_on_miss_whole as raw_service
from . import second_on_miss_whole_raw as prior_raw
from .full_v5_check import _load_case, _sha

REPORT = one_lane_roster.REPORT.parent.with_name("antenna-confirmation") / "on-hit-waveforms"
WORK = Path("/var/tmp/leo-on-hit-waveforms-20261119")
METHOD = "partner_on_hit_whole"
MODULE = "tools.pipeline_eval.qualification.on_hit_waveforms"
STRATA = (("DS26", "lower", [10, 11]), ("DS29", "upper", [12, 13]))


def select(groups, extensions):
    confirmation = sorted(set(groups["all"]) - set(partner_on_hit_trial.CASES))
    if len(confirmation) != 14:
        raise ValueError("the independent antenna roster must contain fourteen recordings")
    inventory, selected = {}, {}
    for ident in confirmation:
        if ident in extensions:
            inventory[ident] = dict(
                available=False, reason="frozen ordinary waveform reader unavailable"
            )
            continue
        case = _load_case(ident)
        authority = capture_release.read_capture(case)
        inventory[ident] = dict(
            available=True,
            edge=authority["edge"],
            digest=case["recording"]["segments"][0]["sha256"],
            clock_authority=authority["input_manifest_sha256"],
        )
    for dataset, edge, cores in STRATA:
        eligible = [
            (row["digest"], ident)
            for ident, row in inventory.items()
            if row["available"] and ident.startswith(dataset) and row["edge"] == edge
        ]
        _, ident = min(eligible)
        selected[ident] = dict(inventory[ident], cpus=cores, eligible=sorted(eligible))
    return dict(confirmed=confirmation, candidates=inventory, selected=selected)


def mark(doc, probes, stock_analysis_sha256, schedule):
    """Preserve the standard lineage from measured probes and the bound stock digest."""
    if probes != doc["source"]["probes"]:
        raise ValueError("native assembly passed a different observation array")
    origin = dict(doc, source=dict(doc["source"], analysis_manifest_sha256=stock_analysis_sha256))
    result, _ = partner_on_hit.project(origin, schedule)
    if result["source"]["probes"] != probes:
        raise ValueError("actual raw detector rows differ from the gate projection")
    return result


def freeze(work):
    sealpath = REPORT / "source-lock.json"
    if sealpath.exists():
        raise FileExistsError("whole raw roster already selected")
    groups, assets, bindings, extensions, release = one_lane_roster.inventory()
    selection = select(groups, extensions)
    frozen = REPORT / "selection.json"
    save_json(frozen, selection)
    prior = raw_service.prior
    # Reuse the exact receiver library and authenticated installed source from the direct service.
    parent = prior.source(prior.WORK)
    binary = next(iter(parent["detectors"].values()))
    if any(parent[key] != value for key, value in release.items()):
        raise ValueError("archived and direct trials use different installed compact receivers")
    work.mkdir(parents=True, exist_ok=False)
    detectors, cases = {}, {}
    for ident, selected in selection["selected"].items():
        case, request = whole_iq.binding(ident)
        stock = one_lane_roster.stock_document(assets[ident])
        authority = bindings[ident]
        if tuple(authority[k] for k in one_lane_roster.fixed.BINDINGS) != (
            case["native"]["sha256"],
            case["request"]["sha256"],
            case["catalog"]["sha256"],
            case["regions"][0],
        ):
            raise ValueError("whole replay differs in recording, causal input or offered tile")
        mapped, _, clock = prior.parent.tune_plan(case)
        if (stock["source"]["input_manifest_sha256"], stock["provenance"]["detector_sha256"]) != (
            clock,
            "sha256:" + binary["sha256"],
        ) or clock != selected["clock_authority"]:
            raise ValueError("stock packet and fresh capture metadata disagree")
        dest = work / "libraries" / ident / "wide-stock.so"
        dest.parent.mkdir(parents=True)
        shutil.copyfile(whole_iq.checked(Path(binary["path"]), binary["sha256"]), dest)
        whole_iq.checked(dest, binary["sha256"])
        schedule = dest.with_name("dispatch.json")
        save_json(schedule, one_lane_schedule.dispatch(stock, mapped))
        schedule.chmod(0o644)
        detectors[ident] = dict(path=str(dest), sha256=binary["sha256"])
        cases[ident] = dict(
            id=ident,
            cpus=selected["cpus"],
            cohort="independent confirmation",
            capture_native_sha256=case["native"]["sha256"],
            request_sha256=case["request"]["sha256"],
            catalog_sha256=case["catalog"]["sha256"],
            tile=case["regions"][0],
            recording=case["recording"],
            clock_authority=clock,
            orbit_snapshots=request["causal_snapshots"],
            dispatch=dict(path=str(schedule), sha256=_sha(schedule)),
            stock=assets[ident],
            stock_analysis_sha256=stock["source"]["analysis_manifest_sha256"],
            edge=selected["edge"],
        )
    paths = (
        Path(__file__),
        Path(on_hit_waveforms_raw.__file__),
        Path(raw_service.__file__),
        Path(prior_raw.__file__),
        Path(partner_on_hit.__file__),
        frozen,
        REPORT / "PROTOCOL.md",
    )
    lock = dict(
        parent,
        cases=cases,
        detectors=detectors,
        policy=partner_on_hit.POLICY,
        programs=parent["programs"] | {str(p.relative_to(ROOT)): _sha(p) for p in paths},
        prior_one_prediction_sha256=_sha(one_lane_roster.REPORT / "prediction-lock.json"),
        complete_four_lock_sha256=_sha(one_lane_roster.fixed.REPORT / "all-figure-lock.json"),
        development_lock_sha256=_sha(partner_on_hit_trial.REPORT / "prediction-lock.json"),
    )
    for path in (work / sealpath.name, sealpath):
        save_json(path, lock)
        path.chmod(0o644)
    print("frozen", [*cases], flush=True)


@contextmanager
def configured(work, ident=None):
    with patch.multiple(raw_service, REPORT=REPORT, MODULE=MODULE, raw=on_hit_waveforms_raw):
        if ident is None:
            yield
            return
        case = raw_service.source(work)["cases"][ident]
        schedule = whole_iq.read(
            whole_iq.checked(Path(case["dispatch"]["path"]), case["dispatch"]["sha256"])
        )
        policy = SimpleNamespace(
            needs_partner=on_hit_waveforms_raw.needs_partner,
            mark=lambda doc, probes: mark(doc, probes, case["stock_analysis_sha256"], schedule),
        )
        with patch.object(raw_service, "second_on_miss", policy):
            yield


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("stage", choices=("freeze", "run", "worker", "position"))
    cli.add_argument("value", nargs="?")
    cli.add_argument("--work", type=local_output, default=WORK)
    args = cli.parse_args()
    if args.stage == "freeze":
        freeze(args.work)
    elif args.stage == "run":
        with configured(args.work):
            raw_service.run(args.work, args.value)
    elif args.stage == "worker":
        attempt = local_output(args.value)
        with configured(attempt.parents[1], attempt.parent.name):
            raw_service.worker(attempt)
    else:
        whole_iq.position(local_output(args.value))
