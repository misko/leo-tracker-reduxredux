"""Run the four-anchor batch winner veto through the unchanged compact release."""

import argparse
import gzip
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from time import perf_counter, process_time

from .. import whole_iq
from ..__main__ import ROOT, local_output, save_json, write
from ..scoring import validate_result
from ..variants import coherent_peak_filter
from ..variants import consistent_peaks as policy
from . import bracketed_position as release
from . import complete_timing, hard_pilots_eval, prefix_evidence_trial, support_cross_trial
from .complete_detector_roster import FOUR
from .fractional_runtime_whole import verify_request
from .full_v5_check import _sha
from .phase_support_results import pack

SCREEN = complete_timing.SCREEN
REPORT = SCREEN / "pilot-influence/consistent-peaks"
WORK = Path("/var/tmp/leo-consistent-peaks-20261119")
CASES = (*hard_pilots_eval.HARD, *hard_pilots_eval.CONTROLS)
CPUS = (16, 17, 18, 19)


def product_sources():
    files = (
        Path(__file__),
        Path(policy.__file__),
        Path(coherent_peak_filter.__file__),
        Path(support_cross_trial.__file__),
        Path(support_cross_trial.margin_admission_trial.__file__),
        REPORT / "PROTOCOL.md",
        hard_pilots_eval.REPORT / "source-lock.json",
        complete_timing.REPORT / "prediction-lock.json",
    )
    return {str(p.relative_to(ROOT)): _sha(p) for p in files}


def planned_release():
    folder = complete_timing.roster.EIGHT
    original = whole_iq.read(folder / "prediction-lock.json")
    path = whole_iq.checked(folder / "source-lock.json", original["files"]["source-lock.json"])
    data = whole_iq.read(path)
    release.check_release(data)
    return {k: data[k] for k in ("receiver", "receiver_files", "native_sources")}


def prepare(work, ident, entry, installed, cpu):
    native = prefix_evidence_trial.native_path(entry)
    parsed = prefix_evidence_trial.native(native, entry["native_sha256"])
    case, parent = whole_iq.binding(ident)
    if (
        parsed["source"]["session_id"] != case["session_id"]
        or parsed["source"]["input_manifest_sha256"] != entry["clock_authority"]
        or parsed["source"]["raw_recording_authority_digest"] != entry["raw_authority"]
        or parsed["provenance"]["detector_sha256"] != "sha256:" + complete_timing.historic.STOCK_SHA
        or entry["capture_sha256"] != case["native"]["sha256"]
        or entry["request_sha256"] != case["request"]["sha256"]
        or entry["catalog_sha256"] != case["catalog"]["sha256"]
    ):
        raise ValueError("Four-region factor source differs from original matched blind input")
    cpu_start, wall = process_time(), perf_counter()
    selected, counts = policy.select(parsed)
    selection_cost = dict(cpu_s=process_time() - cpu_start, wall_s=perf_counter() - wall)
    lineage = whole_iq.recording.digest([policy.METHOD, entry["native_sha256"], selected])
    output = policy.apply(parsed, selected, lineage)
    if hard_pilots_eval.support(parsed) != hard_pilots_eval.support(output):
        raise ValueError("Winner selection changed acquisition or recording coordinates")
    base = work / ident / "selected"
    folder = base / "recording"
    folder.mkdir(parents=True, exist_ok=False)
    path = folder / "native.json"
    whole_iq.recording.save(path, output)
    if not selected:
        whole_iq.checked(path, entry["native_sha256"])
    request = folder / "request.json"
    bound = whole_iq.recording.bind_request(case, path, request)
    verify_request(
        whole_iq.read(request), parent, native_path=path, native_sha256=bound["native_sha256"]
    )
    save_json(base / "plan.json", dict(receiver=installed["receiver"]))
    save_json(
        base / "raw.json", dict(native_sha256=bound["native_sha256"], request_sha256=_sha(request))
    )
    receipt = dict(
        id=ident,
        method=policy.METHOD,
        condition="selected",
        cpu=cpu,
        mode="matched-tile",
        cohort="hard" if ident in hard_pilots_eval.HARD else "control",
        tile=case["regions"][0],
        native_sha256=_sha(path),
        prepared_request_sha256=_sha(request),
        original_request_sha256=case["request"]["sha256"],
        catalog_sha256=case["catalog"]["sha256"],
        paired_capture_sha256=case["native"]["sha256"],
        stock_native_sha256=entry["native_sha256"],
        stock_source=str(native),
        full_probe_count=counts["probes"],
        counts=counts,
        selection_cost=selection_cost,
        plan_sha256=_sha(base / "plan.json"),
        raw_sha256=_sha(base / "raw.json"),
        clock_authority=entry["clock_authority"],
    )
    return receipt, selected


def freeze(work):
    work.mkdir(exist_ok=False)
    _, entries, parent = prefix_evidence_trial.old_parents()
    installed = planned_release()
    save_json(
        REPORT / "source-lock.json",
        dict(
            files=product_sources(),
            cases=CASES,
            cpu=CPUS,
            receiver=installed,
            official_timing_sha256=parent,
            service_limit_s=support_cross_trial.LIMIT,
        ),
    )
    ready, edits = {}, {}
    for i, ident in enumerate(CASES):
        known = entries[ident, FOUR]
        receipt, factors = prepare(work, ident, known, installed, CPUS[i % len(CPUS)])
        ready[ident] = receipt
        edits[ident] = factors
        print(ident, receipt["counts"].get("changed_winners"), receipt["counts"], flush=True)
    save_json(REPORT / "prepared.json", ready)
    save_json(REPORT / "edits.json", edits)
    save_json(
        REPORT / "predecision-lock.json",
        dict(
            cases=CASES,
            files={
                n: _sha(REPORT / n) for n in ("source-lock.json", "prepared.json", "edits.json")
            },
        ),
    )


def sealed(work):
    lock = whole_iq.read(REPORT / "predecision-lock.json")
    for name, digest in lock["files"].items():
        whole_iq.checked(REPORT / name, digest)
    source = whole_iq.read(REPORT / "source-lock.json")
    if source["files"] != product_sources() or source["cases"] != list(CASES):
        raise ValueError("Frozen selector or measurement protocol changed")
    release.check_release(source["receiver"])
    inputs = whole_iq.read(REPORT / "prepared.json")
    for ident, receipt in inputs.items():
        attempt = work / ident / "selected"
        whole_iq.checked(attempt / "plan.json", receipt["plan_sha256"])
        whole_iq.checked(attempt / "raw.json", receipt["raw_sha256"])
    return inputs


def execute(work):
    inputs = sealed(work)

    def lane(cpu):
        for ident in CASES:
            if inputs[ident]["cpu"] != cpu:
                continue
            out = work / ident / "selected"
            if not (out / "attempt.json").is_file():
                support_cross_trial.service(work, inputs[ident])
            receipt = whole_iq.read(out / "attempt.json")
            if receipt["native_sha256"] != inputs[ident]["native_sha256"]:
                raise ValueError("The position service consumed another edited native file")
            validate_result(receipt["result"])
            yield receipt

    with ThreadPoolExecutor(max_workers=len(CPUS)) as pool:
        by_cpu = pool.map(lambda cpu: list(lane(cpu)), CPUS)
        results = sorted([r for children in by_cpu for r in children], key=lambda r: r["id"])
    if sorted(r["id"] for r in results) != sorted(CASES):
        raise ValueError("Terminal position services differ from the frozen roster")
    files = [
        "source-lock.json",
        "prepared.json",
        "edits.json",
        "predecision-lock.json",
        "PROTOCOL.md",
    ]
    for row in results:
        path = work / row["id"] / "selected"
        for name in ("attempt.json", "service.log", "measured.json", "position.json"):
            asset = path / name
            if not asset.is_file():
                continue
            archived = f"{row['id']}-{name}.gz"
            write(REPORT / archived, gzip.compress(asset.read_bytes(), mtime=0))
            files.append(archived)
        whole_iq.checked(path / "service.log", row["log_sha256"])
    pack(REPORT / "positions.jsonl.gz", results)
    files.append("positions.jsonl.gz")
    save_json(
        REPORT / "prediction-lock.json",
        dict(cases=CASES, files={name: _sha(REPORT / name) for name in files}),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("freeze", "fit"))
    parser.add_argument("--work", type=local_output, default=WORK)
    args = parser.parse_args()
    if args.action == "freeze":
        freeze(args.work)
    else:
        execute(args.work)
