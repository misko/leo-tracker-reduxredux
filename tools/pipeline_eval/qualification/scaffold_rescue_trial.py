"""Freeze real stock and donor packets and run fixed-Graph rescue fits."""

import argparse
import gzip
import json
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from pathlib import Path
from time import monotonic

from .. import whole_iq
from ..__main__ import ROOT, local_output, save_json, write
from ..variants import scaffold_rescue, selective_capture
from . import scaffold_rescue_worker, support_cross, support_cross_trial
from .factor_cross import winner
from .fractional_runtime_whole import verify_request
from .full_v5_check import _sha
from .portable_gate_trials import compressed_rows

SCREEN = ROOT / "reports/2026_11_19_receiver_screening"
REPORT = SCREEN / "support-preserving/scaffold-rescue"
ACQ = SCREEN / "acquisition-frontier"
WHOLE = ACQ / "whole-replay"
FFTW = ACQ / "whole-fftw"
DIAG = ACQ / "diagnostic-whole"
NEG = ACQ / "negative-rescue"
STRIDE = SCREEN / "receiver-core/full-stride"
RAW = Path("/var/tmp/leo-frontier-whole-20261119/runs")
CASES = {"DS26-0168": 12, "DS29-0604": 13, "DS26-0237": 12, "DS29-0082": 13}
PRIMARY = ("DS26-0168", "DS29-0604")
METHOD = "scaffold_rescue"
read = whole_iq.read


def member(report, filename):
    return support_cross_trial.checked(report, filename)


def parent_sources(ident, negative):
    if ident in PRIMARY:
        (stock_proof,) = [r for r in negative["scheduled"] if r["id"] == ident]
        stored = whole_iq.checked(
            RAW / ident / "control/recording/native.json", stock_proof["stock_native_sha256"]
        )
        stock = stored.read_bytes()
        group, context = FFTW, read(member(WHOLE, "source-lock.json"))["cases"][ident]
    else:
        stored = member(STRIDE, f"native/control/{ident}.json.gz")
        stock = gzip.decompress(stored.read_bytes())
        group, context = DIAG, read(member(DIAG, "source-lock.json"))["cases"][ident]
    donor_path = member(group, f"native/{ident}.json.gz")
    donor = gzip.decompress(donor_path.read_bytes())
    a, b = map(json.loads, (stock, donor))
    profile = read(member(group, "source-lock.json"))
    if (
        b["provenance"]["detector_sha256"]
        != "sha256:" + profile["detectors"]["candidate"]["sha256"]
    ):
        raise ValueError("donor native bytes do not declare the frozen FFTW hinted ABI")
    selective_capture.same_support(a, b)
    return (
        stock,
        a,
        b,
        dict(
            stock_sha=sha256(stock).hexdigest(),
            donor_sha=sha256(donor).hexdigest(),
            stock_file_sha=_sha(stored),
            donor_file_sha=_sha(donor_path),
        ),
        context,
    )


def sidecar(stock, donor):
    source, overlay = (doc["source"] for doc in (stock, donor))
    anchor = stock["clock_anchor"]["sample_counter"]
    rate, probe_ms, session = (source[k] for k in ("sample_rate_hz", "probe_ms", "session_id"))
    roster = support_cross.join(stock, donor)
    possible, lanes = [], {}
    receivers = sorted({p["receiver_id"] for p in source["probes"]})
    for label, p, q in zip(roster, source["probes"], overlay["probes"], strict=True):
        rx, ch, edge, rf, counter = (
            p[k] for k in ("receiver_id", "channel", "edge", "actual_rf_hz", "valid_start_counter")
        )
        oid = "sha256:" + sha256(f"{session}:{rx}:{counter}".encode()).hexdigest()
        lane = (rx, ch, edge, rf)
        if oid in lanes:
            raise ValueError("duplicate physical observation identity")
        lanes[oid] = lane
        if label != "01":
            continue
        selected = q["candidates"][winner(q["candidates"])]
        possible.append(
            [
                lane,
                dict(
                    observation_id=oid,
                    receiver=receivers.index(rx) + 1,
                    native_receiver_id=rx,
                    channel=ch,
                    time_s=(counter - anchor) / rate + probe_ms * 0.0005,
                    measured_cfo_hz=selected["fractional_tracking_cfo_hz"],
                    actual_rf_hz=rf,
                    fractional_margin=selected["fractional_margin"],
                ),
            ]
        )
    return dict(
        donors=possible, lanes=lanes, duration_s=(stock["last_sample_counter"] - anchor) / rate
    ), dict(Counter(roster))


def stage(work, ident, negative, root):
    stock_bytes, stock, donor, parents, context = parent_sources(ident, negative)
    cases, request = whole_iq.binding(ident)
    if (
        cases["request"]["sha256"] != context["request_sha256"]
        or cases["catalog"]["sha256"] != context["catalog_sha256"]
        or request["job"]["search_center"] != context["tile"]["center"]
    ):
        raise ValueError("existing position authority differs from the full archived parent")
    clock, census = sidecar(stock, donor)
    out = work / ident / "scaffold"
    folder = out / "recording"
    folder.mkdir(parents=True, exist_ok=False)
    write(folder / "native.json", stock_bytes)
    bound = whole_iq.recording.bind_request(cases, folder / "native.json", folder / "request.json")[
        "native_sha256"
    ]
    verify_request(
        read(folder / "request.json"),
        request,
        native_path=folder / "native.json",
        native_sha256=bound,
    )
    save_json(out / "donors.json", clock)
    variant, worker = Path(scaffold_rescue.__file__), Path(scaffold_rescue_worker.__file__)
    runner = out / "scaffold-runtime.json"
    save_json(
        runner,
        dict(
            install=root,
            attach_path=str(variant),
            attach_sha256=_sha(variant),
            donor_sidecar_sha256=_sha(out / "donors.json"),
        ),
    )
    save_json(out / "plan.json", dict(receiver=str(worker)))
    save_json(
        out / "raw.json", dict(native_sha256=bound, request_sha256=_sha(folder / "request.json"))
    )
    return dict(
        id=ident,
        condition="scaffold",
        method=METHOD,
        mode="matched-tile",
        cpu=CASES[ident],
        cohort="diagnostic" if ident in PRIMARY else "replication",
        prepared_request_sha256=_sha(folder / "request.json"),
        native_sha256=parents["stock_sha"],
        parents=parents,
        sidecar_sha256=_sha(out / "donors.json"),
        scaffold_runtime_sha256=_sha(runner),
        paired_capture_sha256=context["capture_native_sha256"],
        catalog_sha256=context["catalog_sha256"],
        original_request_sha256=context["request_sha256"],
        tile=context["tile"],
        paired_roster=census,
    )


def run(work):
    if (REPORT / "plan.json").exists():
        raise FileExistsError("scaffold trial already locked")
    work.mkdir(exist_ok=False)
    source = read(member(WHOLE, "source-lock.json"))
    root = source["receiver"]
    identity = whole_iq.receiver_identity(Path(root))
    if identity != source["receiver_files"]:
        raise ValueError("installed release differs from its stock source receipt")
    for other in (DIAG, STRIDE, FFTW):
        inventory = read(member(other, "source-lock.json"))["receiver_files"]
        if any(identity[k] != v for k, v in inventory.items() if k != "native/manifest.json"):
            raise ValueError("different numerical receiver in the comparator")
    negative = read(member(NEG, "plan.json"))
    rows = [stage(work, ident, negative, root) for ident in CASES]
    files = (
        Path(__file__),
        Path(scaffold_rescue.__file__),
        Path(scaffold_rescue_worker.__file__),
        Path(support_cross_trial.__file__),
        REPORT / "PROTOCOL.md",
        *(p / "prediction-lock.json" for p in (WHOLE, FFTW, STRIDE, NEG, DIAG)),
    )
    save_json(
        REPORT / "plan.json",
        dict(
            cases=rows,
            receiver=root,
            receiver_files=identity,
            memory_bytes=whole_iq.MEMORY,
            cap_s=support_cross_trial.LIMIT,
            swap_bytes=0,
            files={str(p.relative_to(ROOT)): _sha(p) for p in files},
        ),
    )
    print("locked", [(r["id"], r["paired_roster"].get("01", 0)) for r in rows], flush=True)

    def lane(cpu):
        completed = []
        for row in rows:
            if row["cpu"] != cpu:
                continue
            out = work / row["id"] / "scaffold"
            whole_iq.checked(out / "scaffold-runtime.json", row["scaffold_runtime_sha256"])
            result = support_cross_trial.service(work, row)
            evidence = out / "scaffold-proof.json"
            result["scaffold"] = read(evidence) if evidence.exists() else None
            completed.append(result)
        return completed

    start = monotonic()
    with ThreadPoolExecutor(2) as pool:
        result = [row for lane_results in pool.map(lane, (12, 13)) for row in lane_results]
    write(REPORT / "predictions.jsonl.gz", compressed_rows(result))
    names = ("plan.json", "predictions.jsonl.gz")
    save_json(
        REPORT / "prediction-lock.json",
        dict(
            cases=list(CASES),
            elapsed_s=monotonic() - start,
            attempted=len(result),
            files={name: _sha(REPORT / name) for name in names},
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=local_output)
    run(parser.parse_args().work)
