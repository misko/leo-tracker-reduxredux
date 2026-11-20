"""Seal and replay six exact-capture-support winner interventions."""

import argparse
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from time import monotonic

from .. import whole_iq
from ..__main__ import ROOT, encoded, local_output, save_json, write
from . import factor_cross, peak_support, shared_winner_cross, support_cross, support_cross_trial
from .fractional_runtime_whole import verify_request
from .full_v5_check import _sha
from .portable_gate_trials import compressed_rows
from .support_cross_trial import CASES, LIMIT, load, read, service, sources

PARENT = support_cross_trial.REPORT
REPORT = PARENT.with_name("shared-winners")
MODES = shared_winner_cross.TREATMENTS


def parent_lock():
    lock = read(PARENT / "prediction-lock.json")
    for name, digest in lock["files"].items():
        whole_iq.checked(PARENT / name, digest)
    return read(PARENT / "plan.json")


def incoming(ident, support_work, source, plan):
    case, request, _, a, b = load(ident, source)
    (metadata,) = [r for r in plan["schedule"] if (r["id"], r["condition"]) == (ident, "both")]
    native = support_work / ident / "both" / "recording/native.json"
    whole_iq.checked(native, metadata["native_sha256"])
    wide, capture = map(json.loads, (a, b))
    roster = support_cross.join(wide, capture)
    base = read(native)
    baseline = support_cross.intervene(wide, capture, roster, "both")
    if baseline["source"]["probes"] != base["source"]["probes"]:
        raise ValueError("parent hybrid differs from exact capture-era support")
    return case, request, metadata, base, capture, shared_winner_cross.assess(wide, capture, roster)


def stage(work, ident, support_work, source, plan):
    case, parent, metadata, base, capture, (choices, stats) = incoming(
        ident, support_work, source, plan
    )
    records = []
    for mode in MODES:
        payload, changed = shared_winner_cross.replace(base, capture, choices, mode)
        lineage = whole_iq.recording.digest(
            [
                "discordant-winners/v1",
                mode,
                metadata["native_sha256"],
                metadata["paired_capture_sha256"],
            ]
        )
        payload["source"]["analysis_manifest_sha256"] = lineage
        payload["provenance"] = dict(payload["provenance"], run_id="shared-winner-" + lineage[7:32])
        location = work / ident / mode
        folder = location / "recording"
        folder.mkdir(parents=True, exist_ok=False)
        native, request = folder / "native.json", folder / "request.json"
        write(native, encoded(payload) + b"\n")
        actual = whole_iq.recording.bind_request(case, native, request)["native_sha256"]
        verify_request(read(request), parent, native_path=native, native_sha256=actual)
        save_json(location / "plan.json", dict(receiver=source["receiver"]))
        save_json(location / "raw.json", dict(native_sha256=actual, request_sha256=_sha(request)))
        rows = payload["source"]["probes"]
        if tuple(map(support_cross.positive, rows)) != tuple(
            map(support_cross.positive, capture["source"]["probes"])
        ):
            raise ValueError("intervention changed an element of the exact positive roster")
        records.append(
            dict(
                metadata,
                method="shared_winner_" + mode,
                condition=mode,
                changed=changed,
                native_sha256=actual.removeprefix("sha256:"),
                baseline_native_sha256=metadata["native_sha256"],
                prepared_request_sha256=_sha(request),
                positive_candidates=sum(
                    c[factor_cross.GATE] is True for p in rows for c in p["candidates"]
                ),
            )
        )
    return records, dict(id=ident, counts=stats, choices=choices)


def run(work, support_work):
    if (REPORT / "plan.json").exists():
        raise FileExistsError("the shared-winner experiment already has a frozen plan")
    work.mkdir(exist_ok=False)
    parent = parent_lock()
    source = sources()
    if source["receiver_files"] != parent["receiver_files"]:
        raise ValueError("all winner treatments must use the parent receiver package")
    jobs, census = [], []
    for ident, cpu in CASES.items():
        rows, choices = stage(work, ident, support_work, source, parent)
        jobs.extend(rows if cpu == 6 else rows[::-1])
        census.append(choices)
    counts = {r["id"]: r["counts"] for r in census}
    save_json(REPORT / "census.json", counts)
    write(REPORT / "selections.jsonl.gz", compressed_rows(census))
    dependencies = [
        Path(__file__),
        *(
            Path(m.__file__)
            for m in (
                shared_winner_cross,
                support_cross,
                support_cross_trial,
                factor_cross,
                peak_support,
            )
        ),
        REPORT / "PROTOCOL.md",
        REPORT / "census.json",
        REPORT / "selections.jsonl.gz",
        PARENT / "prediction-lock.json",
    ]
    save_json(
        REPORT / "plan.json",
        dict(
            schedule=jobs,
            cpus=CASES,
            memory_bytes=whole_iq.MEMORY,
            swap_bytes=0,
            limit_s=LIMIT,
            exact_support_parent_sha256=_sha(PARENT / "prediction-lock.json"),
            receiver_files=source["receiver_files"],
            files={str(p.relative_to(ROOT)): _sha(p) for p in dependencies},
        ),
    )
    digest = _sha(REPORT / "plan.json")
    print("sealed", digest, counts, flush=True)

    def lane(ident):
        return [service(work, row) for row in jobs if row["id"] == ident]

    start = monotonic()
    with ThreadPoolExecutor(2) as pool:
        results = [r for group in pool.map(lane, CASES) for r in group]
    predictions = REPORT / "predictions.jsonl.gz"
    write(predictions, compressed_rows(results))
    save_json(
        REPORT / "prediction-lock.json",
        dict(
            attempted=len(results),
            cases=list(CASES),
            measured_wall_s=monotonic() - start,
            files={
                "plan.json": digest,
                "census.json": _sha(REPORT / "census.json"),
                "selections.jsonl.gz": _sha(REPORT / "selections.jsonl.gz"),
                predictions.name: _sha(predictions),
            },
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=local_output)
    parser.add_argument("--support-work", required=True, type=local_output)
    args = parser.parse_args()
    run(args.work, args.support_work)
