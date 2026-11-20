"""Verify selector edits and stage only the private promoted-factor copies."""

import argparse
import json
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from pathlib import Path
from time import monotonic, process_time

from .. import whole_iq
from ..__main__ import local_output, save_json, write
from . import bracketed_position as trial
from .full_v5_check import _sha

GATE = "passed_fractional_margin_gate"


def apply_edits(blob, edits):
    if not edits:
        return blob, []
    document = json.loads(blob)
    probes = document["source"]["probes"]
    if document["schema_version"] != 2:
        raise ValueError("a complete schema-2 native archive is required")
    selected, receipt, seen = [], [], set()
    for edit in edits:
        pi, ci = edit["probe_index"], edit["candidate_index"]
        if type(pi) is not int or type(ci) is not int or pi in seen or not 0 <= pi < len(probes):
            raise ValueError("edits must select a single authentic row in each addressed probe")
        seen.add(pi)
        probe = probes[pi]
        rows = probe["candidates"]
        if not 0 <= ci < len(rows) or any(row.get(GATE) is not False for row in rows):
            raise ValueError("selected row must come from an entirely failing original probe")
        candidate = rows[ci]
        selected.append(candidate)
        receipt.append(
            dict(
                edit,
                recorded_visit_index=probe["visit_index"],
                recorded_receiver_id=probe["receiver_id"],
                candidate=candidate.copy(),
            )
        )
    for row in selected:
        row[GATE] = True
    derived = (whole_iq.recording.encoded(document) + "\n").encode()
    for row in selected:
        row[GATE] = False
    if (whole_iq.recording.encoded(document) + "\n").encode() != blob:
        raise ValueError("restoring the gate bits must restore the original archive bytes")
    return derived, receipt


def source_lock(work, report):
    doc = report / "source-lock.json"
    whole_iq.checked(doc, whole_iq.read(work / "launch-lock.json")["source_sha256"])
    source = whole_iq.read(doc)
    for path, digest in source["paths"].items():
        whole_iq.checked(Path(path), digest)
    trial.check_release(source)
    return source


def prepare(work, report, path, digest):
    source = source_lock(work, report)
    selected = whole_iq.read(whole_iq.checked(path, digest))
    names = ("edits.json", "source-lock.json", "selection.csv")
    paths = {name: whole_iq.checked(path.parent / name, selected["files"][name]) for name in names}
    edits = whole_iq.read(paths["edits.json"])
    if not set(source["cases"]) <= edits.keys():
        raise ValueError("selector does not cover the frozen four recordings")
    result = report / "candidate-lock.json"
    if result.exists():
        raise FileExistsError("derived candidate replay is already planned")
    cases = {}
    for ident, original in source["cases"].items():
        baseline = original["archived"]["native_sha256"]
        if edits[ident]["native_sha256"] != baseline:
            raise ValueError("the selector was evaluated on different native factors")
        control = work / ident / "control"
        if not (control / "service.json").exists():
            raise ValueError("fresh controls must release their CPUs before the candidate enters")
        native = whole_iq.checked(control / "native.json", baseline)
        plan = whole_iq.read(
            whole_iq.checked(control / "request.json", original["control_request_sha256"])
        )
        blob = native.read_bytes()
        wall, cpu = monotonic(), process_time()
        derived, receipt = apply_edits(blob, edits[ident]["bracketed"])
        elapsed_wall, elapsed_cpu = monotonic() - wall, process_time() - cpu
        new_digest = sha256(derived).hexdigest()
        line = dict(
            stock_native_sha256=baseline,
            derived_native_sha256=new_digest,
            materialization_wall_s=elapsed_wall,
            materialization_cpu_s=elapsed_cpu,
            edits=receipt,
            exact_archive_reuse=not receipt,
            detector_sha256=original["detection"]["detector_sha256"],
            original_analysis_manifest_sha256=json.loads(blob)["source"][
                "analysis_manifest_sha256"
            ],
            original_input_manifest_sha256=original["input_manifest_sha256"],
        )
        if receipt:
            dest = work / ident / "candidate"
            dest.mkdir(exist_ok=False)
            write(dest / "native.json", derived)
            save_json(
                dest / "request.json",
                dict(plan, native=str(dest / "native.json"), native_sha256=new_digest),
            )
            line["candidate_request_sha256"] = _sha(dest / "request.json")
        elif derived != blob or new_digest != baseline:
            raise ValueError("a zero-edit candidate must reproduce the exact original bytes")
        cases[ident] = line
    write(report / "selection.csv", paths["selection.csv"].read_bytes())
    lock = dict(
        cases=cases,
        selector_sha256=digest,
        selector_files={name: _sha(p) for name, p in paths.items()},
        materializer_sha256=_sha(Path(__file__)),
        source_sha256=_sha(report / "source-lock.json"),
    )
    save_json(result, lock)
    save_json(work / "candidate-lock.json", {"candidate_sha256": _sha(result)})
    return lock


def run(work, report, path, digest):
    lock = prepare(work, report, path, digest)

    def lane(cpu):
        for ident in trial.LANES[cpu]:
            planned = lock["cases"][ident]
            if not planned["exact_archive_reuse"]:
                directory = work / ident / "candidate"
                whole_iq.checked(directory / "request.json", planned["candidate_request_sha256"])
                whole_iq.checked(directory / "native.json", planned["derived_native_sha256"])
                trial.launch_case(directory, cpu)

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lane, trial.LANES))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("selection_lock", type=Path)
    parser.add_argument("--selection-sha256", required=True)
    parser.add_argument("--work", type=local_output, default=trial.WORK)
    parser.add_argument("--out", type=local_output, default=trial.REPORT)
    args = parser.parse_args()
    run(args.work, args.out, args.selection_lock, args.selection_sha256)


if __name__ == "__main__":
    main()
