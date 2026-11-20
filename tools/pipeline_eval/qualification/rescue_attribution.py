"""Run two complete packet subsets of the authenticated negative-rescue experiment."""

import argparse
import csv
import gzip
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from pathlib import Path

from .. import whole_iq
from ..__main__ import ROOT, encoded, local_output, save_json, write
from ..variants import negative_rescue
from . import differential_agreement as agreement
from . import negative_rescue_trial as parent
from . import support_cross, support_cross_trial
from .fractional_runtime_whole import verify_request
from .full_v5_check import BULK, _sha
from .portable_gate_trials import compressed_rows

REPORT = parent.REPORT.with_name("rescue-attribution")
CHANGES = ("corroborated", "remainder")
EXPECTED = {"DS26-0168": (118, 283), "DS29-0604": (132, 269)}
PARENT_WORK = Path.home() / ".cache/leo-negative-rescue-final-20261119"
read = whole_iq.read


def key(packet):
    return tuple(int(packet[field]) for field in support_cross.IDENTITY_FIELDS)


def digest(value):
    return sha256(encoded(value)).hexdigest()


def partition(ident, stock, differential, capture, union, labels):
    support_cross.join(stock, differential)
    support_cross.join(stock, capture)
    support_cross.join(stock, union)
    frame = capture["source"]["sample_rate_hz"] / agreement.factor_cross.FRAME_HZ
    rows = [doc["source"]["probes"] for doc in (stock, differential, capture, union)]
    groups, audit = {group: [] for group in CHANGES}, []
    if len(labels) != len(rows[0]):
        raise ValueError("agreement ledger does not cover every stock probe")
    for a, b, ref, u in zip(*rows, strict=True):
        row_id = key(a)
        label = labels[row_id]
        if not (
            label["id"] == ident
            and int(label["channel"]) == a["channel"]
            and label["edge"] == a["edge"]
        ):
            raise ValueError("agreement row differs from physical packet metadata")
        gained = not negative_rescue.positive(a) and negative_rescue.positive(b)
        if gained != (label["transition"] == "gained"):
            raise ValueError("frozen gain roster differs from the native detector gates")
        if encoded(u) != encoded(b if gained else a):
            raise ValueError("original union includes a modified probe packet")
        chosen = None
        if gained:
            label_value = agreement.label(agreement.best(b["candidates"]), ref["candidates"], frame)
            if label["hinted"] != label_value or label_value not in agreement.LABELS:
                raise ValueError("sealed capture family disagrees with authentic native candidates")
            chosen = "corroborated" if label_value in agreement.LABELS[:2] else "remainder"
            audit.append(
                dict(
                    id=ident,
                    probe=list(row_id),
                    group=chosen,
                    label=label_value,
                    stock_packet_sha256=digest(a),
                    replacement_packet_sha256=digest(b),
                )
            )
        for group in CHANGES:
            groups[group].append(b if group == chosen else a)
    return groups, audit


def sealed(folder, seal, name):
    return whole_iq.checked(folder / name, read(folder / seal)["files"][name])


def authority():
    ledger = agreement.REPORT / "result-lock.json"
    closed = read(ledger)
    if closed["parent_sha256"] != _sha(parent.PARENT / "prediction-lock.json") or closed[
        "source_sha256"
    ] != _sha(Path(agreement.__file__)):
        raise ValueError("agreement ledger is detached from the measured detector experiment")
    label_path = sealed(agreement.REPORT, ledger.name, "probes.csv.gz")
    labels = {ident: {} for ident in parent.CASES}
    with gzip.open(label_path, "rt", newline="") as stream:
        for row in csv.DictReader(stream):
            case, row_id = row["id"], key(row)
            if row_id in labels[case]:
                raise ValueError("duplicate physical probe in the agreement ledger")
            labels[case][row_id] = row
    return closed, labels


def stage(work, raw, union):
    work.mkdir(exist_ok=False)
    if (REPORT / "plan.json").exists():
        raise FileExistsError("attribution experiment already frozen")
    evidence, labels = authority()
    origin = read(sealed(parent.REPORT, "prediction-lock.json", "plan.json"))
    if whole_iq.receiver_identity(Path(origin["receiver"])) != origin["receiver_files"]:
        raise ValueError("installed receiver changed since the parent rescue")
    jobs, membership = [], []
    for spec in origin["scheduled"]:
        ident = spec["id"]
        case, parent_request = whole_iq.binding(ident)
        if (
            spec["paired_capture_sha256"] != case["native"]["sha256"]
            or spec["catalog_sha256"] != case["catalog"]["sha256"]
            or spec["original_request_sha256"] != case["request"]["sha256"]
            or spec["tile"]["center"] != parent_request["job"]["search_center"]
        ):
            raise ValueError("original recording, causal sky or offer changed")
        paths = {
            "control": raw / ident / "control/recording/native.json",
            "candidate": raw / ident / "candidate/recording/native.json",
            "capture": BULK / case["native"]["path"],
        }
        doc = {
            role: read(whole_iq.checked(path, evidence["input_sha256"][f"{ident}/{role}"]))
            for role, path in paths.items()
        }
        if (
            evidence["input_sha256"][f"{ident}/control"] != spec["stock_native_sha256"]
            or evidence["input_sha256"][f"{ident}/candidate"] != spec["differential_native_sha256"]
        ):
            raise ValueError("negative rescue used different genuine detectors")
        union_path = union / ident / "rescue/recording/native.json"
        full = read(whole_iq.checked(union_path, spec["native_sha256"]))
        groups, members = partition(
            ident, doc["control"], doc["candidate"], doc["capture"], full, labels[ident]
        )
        counts = Counter(row["group"] for row in members)
        if tuple(counts[g] for g in CHANGES) != EXPECTED[ident]:
            raise ValueError("partition differs from the frozen counts")
        membership.extend(members)
        for name in CHANGES if ident == "DS26-0168" else reversed(CHANGES):
            base = doc["control"]
            lineage = whole_iq.recording.digest(
                [
                    "rescue-attribution/v1",
                    name,
                    _sha(agreement.REPORT / "result-lock.json"),
                    spec["stock_native_sha256"],
                    spec["differential_native_sha256"],
                ]
            )
            probes = groups[name]
            payload = dict(
                base, source=dict(base["source"], probes=probes, analysis_manifest_sha256=lineage)
            )
            payload["provenance"] = dict(
                base["provenance"], run_id="rescue-attribution-" + lineage[7:29]
            )
            payload["provenance"].pop("detector_sha256")
            root = work / ident / name
            folder = root / "recording"
            folder.mkdir(parents=True)
            native, request = folder / "native.json", folder / "request.json"
            write(native, encoded(payload) + b"\n")
            actual = whole_iq.recording.bind_request(case, native, request)["native_sha256"]
            verify_request(read(request), parent_request, native_path=native, native_sha256=actual)
            save_json(root / "plan.json", dict(receiver=origin["receiver"]))
            save_json(root / "raw.json", dict(native_sha256=actual, request_sha256=_sha(request)))
            jobs.append(
                {
                    key: spec[key]
                    for key in (
                        "id",
                        "cpu",
                        "tile",
                        "mode",
                        "paired_capture_sha256",
                        "original_request_sha256",
                        "catalog_sha256",
                        "stock_native_sha256",
                        "differential_native_sha256",
                        "original_probes",
                        "admitted_visits",
                    )
                }
                | dict(
                    condition=name,
                    method="rescue_attribution_" + name,
                    native_sha256=actual.removeprefix("sha256:"),
                    prepared_request_sha256=_sha(request),
                    positive_probes=sum(map(negative_rescue.positive, probes)),
                    positive_candidates=sum(
                        c[negative_rescue.GATE] is True for p in probes for c in p["candidates"]
                    ),
                    selected_packets=counts[name],
                    packets_sha256=digest(probes),
                )
            )
    write(REPORT / "packets.jsonl.gz", compressed_rows(membership))
    save_json(
        REPORT / "plan.json",
        dict(
            scheduled=jobs,
            receiver=origin["receiver"],
            receiver_files=origin["receiver_files"],
            agreement_sha256=_sha(agreement.REPORT / "result-lock.json"),
            parent_prediction_sha256=_sha(parent.REPORT / "prediction-lock.json"),
            parent_figure_sha256=_sha(parent.REPORT / "figure-lock.json"),
            packets_sha256=_sha(REPORT / "packets.jsonl.gz"),
            service_cap_s=support_cross_trial.LIMIT,
            memory_bytes=whole_iq.MEMORY,
            swap_bytes=0,
            sources=sources(),
        ),
    )
    print("Pre-inference source and packet lock", _sha(REPORT / "plan.json"), flush=True)


def sources():
    paths = (
        Path(__file__),
        Path(agreement.__file__),
        Path(support_cross.__file__),
        Path(negative_rescue.__file__),
        Path(support_cross_trial.__file__),
        Path(support_cross_trial.margin_admission_trial.__file__),
        REPORT / "PROTOCOL.md",
    )
    return {str(p.relative_to(ROOT)): _sha(p) for p in paths}


def run(work):
    planfile = REPORT / "plan.json"
    plan = read(planfile)
    if plan["sources"] != sources() or (
        whole_iq.receiver_identity(Path(plan["receiver"])) != plan["receiver_files"]
    ):
        raise ValueError("frozen solver sources changed before inference")

    def lane(ident):
        return [
            support_cross_trial.service(work, job)
            for job in plan["scheduled"]
            if job["id"] == ident
        ]

    with ThreadPoolExecutor(2) as pool:
        rows = [row for jobs in pool.map(lane, parent.CASES) for row in jobs]
    write(REPORT / "predictions.jsonl.gz", compressed_rows(rows))
    names = ("plan.json", "packets.jsonl.gz", "predictions.jsonl.gz")
    save_json(
        REPORT / "prediction-lock.json",
        dict(cases=list(parent.CASES), files={name: _sha(REPORT / name) for name in names}),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=local_output)
    parser.add_argument("--raw", type=Path, default=parent.DEFAULT_RAW)
    parser.add_argument("--union", type=Path, default=PARENT_WORK)
    args = parser.parse_args()
    stage(args.work, args.raw, args.union)
    run(args.work)
