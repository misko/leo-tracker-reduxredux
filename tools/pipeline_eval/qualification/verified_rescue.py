"""Check later pilot symbols on added wide detections, then fit matched positions."""

import argparse
import gzip
import json
import subprocess
from collections import defaultdict
from hashlib import sha256
from pathlib import Path

from .. import whole_iq
from ..__main__ import ROOT, THREAD_ENV, encoded, local_output, save_json, write
from ..variants import pilot_confirmation, selective_capture
from . import diagnostic_whole, exact_wide_iq_results, support_cross_trial, verified_rescue_raw
from .differential_agreement import best
from .fractional_runtime_whole import verify_request
from .frontier_whole_replay_results import fingerprint
from .full_v5_check import BULK, _sha
from .portable_gate_trials import compressed_rows
from .recording_to_v5 import ARCHIVE_PYTHON

REPORT = diagnostic_whole.REPORT.parents[1] / "support-preserving/verified-rescue"
FOUR = diagnostic_whole.REPORT
POOL_PIN = "0f2de2305f2d42bbe19e95115168c197a47a3e2433ceaf17c141a77af31a00b4"
CASES = ("DS26-0168", "DS29-0604", "DS26-0237", "DS29-0082")
CONDITIONS = ("verified", "count_control")


def lines(path):
    with gzip.open(path) as stream:
        return list(map(json.loads, stream))


def matched_count(ident, gains):
    """Keep the same count per instrument and RF setting with a fixed hash order."""
    strata = defaultdict(list)
    for row in gains:
        strata[row["lane"], row["channel"], row["edge"]].append(row)
    chosen = set()
    for group in strata.values():

        def order(row):
            return sha256(
                encoded(["late-symbol-count-control-20261119", ident, row["visit"], row["lane"]])
            ).digest()

        for row in sorted(group, key=order)[: sum(r["passed"] for r in group)]:
            chosen.add((row["visit"], row["lane"]))
    return chosen


def parents(ident, work):
    lock = whole_iq.read(whole_iq.checked(FOUR / "pooled-figure-lock.json", POOL_PIN))
    name = "pooled-positions.jsonl.gz"
    records = lines(whole_iq.checked(FOUR / name, lock["files"][name]))
    pair = {r["method"]: r for r in records if r["id"] == ident}
    held = ident in CASES[:2]
    folder = FOUR.parent / "whole-fftw" if held else FOUR
    raw = work / ("leo-frontier-fftw-20261119" if held else "leo-diagnostic-whole-20261119")
    candidate = raw / ident / "candidate"
    source = (
        work / "leo-frontier-whole-20261119/runs" / ident / "control/recording/native.json"
        if held
        else diagnostic_whole.STOCK / f"native/control/{ident}.json.gz"
    )
    docs = []
    for path, role in ((source, "stock"), (folder / f"native/{ident}.json.gz", "fftw")):
        content = path.read_bytes()
        if path.suffix == ".gz":
            content = gzip.decompress(content)
        if sha256(content).hexdigest() != pair[f"diagnostic_whole_{role}"]["native_sha256"]:
            raise ValueError("source differs from the matched four-recording study")
        docs.append(json.loads(content))
    selective_capture.same_support(*docs)
    return pair, docs, folder, candidate


def bind_gains(ident, docs, folder, attempt):
    case, _ = whole_iq.binding(ident)
    role = "fftw" if ident in CASES[:2] else "candidate"
    receipt = whole_iq.read(folder / "prediction-lock.json")
    trace = lines(whole_iq.checked(folder / "visits.jsonl.gz", receipt["files"]["visits.jsonl.gz"]))
    visit_authority = {
        r["visit"]: r["full_visit_sha256"] for r in trace if (r["id"], r["role"]) == (ident, role)
    }
    recorded, _, _ = exact_wide_iq_results.detector_rows(attempt)
    if len(recorded) != len(visit_authority) or any(
        fingerprint(v) != visit_authority[v["visit"]] for v in recorded
    ):
        raise ValueError("full detector visit, IQ hash, or clock changed")
    clock = {v["visit"]: v for v in recorded}
    windows = {}
    for stock, donor in zip(*(d["source"]["probes"] for d in docs), strict=True):
        if best(stock["candidates"]) is not None:
            continue
        winner = best(donor["candidates"])
        if winner is None:
            continue
        v, lane = donor["visit_index"], donor["receiver_id"]
        row = clock[v]
        if row["probes"][lane] != donor or donor["probe_start_ms"] != 0:
            raise ValueError("native donor differs from the authenticated raw output")
        if v not in windows:
            windows[v] = dict(
                visit=v,
                segment=row["segment"],
                sequence=row["sequence"],
                counter=row["sample_start"],
                iq_sha256=row["iq_sha256"],
                channel=donor["channel"],
                edge=donor["edge"],
                gains=[],
            )
        windows[v]["gains"].append(dict(lane=lane, winner=winner))
    return dict(
        segments=[
            dict(path=str(BULK / s["path"]), sha256=s["sha256"])
            for s in case["recording"]["segments"]
        ],
        visits=list(windows.values()),
    )


def verify_raw(ident, selection, work, cpu):
    stage = work / ident
    stage.mkdir(parents=True, exist_ok=False)
    save_json(stage / "raw-plan.json", selection)
    with (stage / "witness.jsonl").open("xb") as out:
        subprocess.run(
            [
                "timeout",
                "--kill-after=3s",
                "240s",
                "sudo",
                "-n",
                "-u",
                "leo",
                "--",
                "env",
                f"PYTHONPATH={ROOT / 'src'}:{ROOT}",
                *[f"{k}={v}" for k, v in THREAD_ENV.items()],
                "taskset",
                "-c",
                str(cpu),
                str(ARCHIVE_PYTHON),
                "-B",
                "-m",
                verified_rescue_raw.__name__,
            ],
            input=encoded(selection),
            stdout=out,
            check=True,
        )
    visits = {r["visit"]: r for r in selection["visits"]}
    measured = []
    with (stage / "witness.jsonl").open() as source:
        rows = list(map(json.loads, source))
    if rows.pop() != dict(complete=True, visits=len(visits)) or len(rows) != len(visits):
        raise ValueError("raw witness did not complete the declared panel")
    for row in rows:
        ref = visits.pop(row["visit"])
        if (row["sequence"], row["iq_sha256"]) != (ref["sequence"], ref["iq_sha256"]):
            raise ValueError("waveform changed in the witness result")
        lookup = {g["lane"]: g["winner"] for g in ref["gains"]}
        if {g["lane"] for g in row["probes"]} != lookup.keys():
            raise ValueError("incomplete physical receiver witness")
        for probe in row["probes"]:
            measured.append(
                dict(
                    id=ident,
                    visit=row["visit"],
                    channel=ref["channel"],
                    edge=ref["edge"],
                    iq_sha256=row["iq_sha256"],
                    **probe,
                    winner_sha256=fingerprint(lookup[probe["lane"]]),
                )
            )
    return measured, [dict(id=ident, visit=r["visit"], cpu_ns=r["cpu_ns"]) for r in rows]


def choose_packet(stock, donor, included):
    if included:
        if best(stock["candidates"]) is not None or best(donor["candidates"]) is None:
            raise ValueError("only an additional winning donor may replace a negative packet")
        return donor
    return stock


def prepare(work, raw_root, ident, cpu):
    refs, docs, folder, attempt = parents(ident, raw_root)
    raw_plan = bind_gains(ident, docs, folder, attempt)
    measures, costs = verify_raw(ident, raw_plan, work, cpu)
    accepted = {(m["visit"], m["lane"]) for m in measures if m["passed"]}
    control = matched_count(ident, measures)
    for row in measures:
        row["count_control"] = (row["visit"], row["lane"]) in control
    write(work / ident / "measures.jsonl.gz", compressed_rows(measures))
    write(work / ident / "costs.jsonl.gz", compressed_rows(costs))
    case, request = whole_iq.binding(ident)
    authority = whole_iq.read(folder / "source-lock.json")
    identity = whole_iq.receiver_identity(Path(authority["receiver"]))
    if identity != authority["receiver_files"]:
        raise ValueError("installed compact solver differs from the original paired service")
    jobs = []
    for condition, include in zip(CONDITIONS, (accepted, control), strict=True):
        target = work / ident / condition
        (target / "recording").mkdir(parents=True, exist_ok=False)
        stock, donor = docs
        probes = [
            choose_packet(a, b, (a["visit_index"], a["receiver_id"]) in include)
            for a, b in zip(stock["source"]["probes"], donor["source"]["probes"], strict=True)
        ]
        token = whole_iq.recording.digest(["verified-rescue/v1", condition, ident, sorted(include)])
        native = dict(
            stock,
            source=dict(stock["source"], probes=probes, analysis_manifest_sha256=token),
            provenance=dict(stock["provenance"], run_id="verified-rescue-" + token[7:30]),
        )
        native["provenance"].pop("detector_sha256", None)
        path = target / "recording/native.json"
        req = target / "recording/request.json"
        write(path, encoded(native) + b"\n")
        bound = whole_iq.recording.bind_request(case, path, req)["native_sha256"]
        verify_request(whole_iq.read(req), request, native_path=path, native_sha256=bound)
        save_json(target / "plan.json", dict(receiver=authority["receiver"]))
        save_json(target / "raw.json", dict(native_sha256=bound, request_sha256=_sha(req)))
        base = refs["diagnostic_whole_stock"]
        jobs.append(
            dict(
                id=ident,
                condition=condition,
                method="late_symbol_rescue_" + condition,
                cpu=cpu,
                accepted=len(include),
                proposed=len(measures),
                native_sha256=_sha(path),
                prepared_request_sha256=_sha(req),
                stock_native_sha256=base["native_sha256"],
                donor_native_sha256=refs["diagnostic_whole_fftw"]["native_sha256"],
                **{
                    k: base[k]
                    for k in (
                        "tile",
                        "mode",
                        "catalog_sha256",
                        "original_request_sha256",
                        "paired_capture_sha256",
                    )
                },
            )
        )
    source = dict(
        source_sha256={
            str(p.relative_to(ROOT)): _sha(p)
            for p in (
                Path(__file__),
                Path(verified_rescue_raw.__file__),
                Path(pilot_confirmation.__file__),
                REPORT / "PROTOCOL.md",
            )
        },
        original_four_lock=POOL_PIN,
        detector_lock=_sha(folder / "prediction-lock.json"),
        raw_plan_sha256=_sha(work / ident / "raw-plan.json"),
        witness_sha256=_sha(work / ident / "witness.jsonl"),
        measures_sha256=_sha(work / ident / "measures.jsonl.gz"),
        costs_sha256=_sha(work / ident / "costs.jsonl.gz"),
        receiver=authority["receiver"],
        receiver_files=identity,
        jobs=jobs,
    )
    save_json(work / ident / "prepared.json", source)
    print(ident, len(accepted), "of", len(measures), "corroborated by later symbols", flush=True)


def fit_case(work, ident):
    receipt = whole_iq.read(work / ident / "prepared.json")
    for row in receipt["jobs"] if ident.startswith("DS26") else reversed(receipt["jobs"]):
        result = support_cross_trial.service(work, row)
        save_json(work / ident / row["condition"] / "terminal.json", result)


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("action", choices=("prepare", "fit"))
    cli.add_argument("work", type=local_output)
    cli.add_argument("--case", choices=CASES, required=True)
    cli.add_argument("--raw-root", type=Path, default=Path("/var/tmp"))
    cli.add_argument("--cpu", type=int, default=23)
    args = cli.parse_args()
    if args.action == "prepare":
        prepare(args.work, args.raw_root, args.case, args.cpu)
    else:
        fit_case(args.work, args.case)
