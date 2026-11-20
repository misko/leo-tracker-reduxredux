"""Challenge selected factor rows against both real frontends on bounded saved CI16."""

import argparse
import json
from hashlib import sha256
from pathlib import Path
from time import perf_counter_ns, process_time_ns
from unittest.mock import patch

import numpy as np

from ..__main__ import ROOT, encoded, local_output, save_json
from ..variants import iq_stream, selective_capture
from . import capture_detector_lineage as lineage
from .capture_detector_replay import scan_capture_window
from .full_v5_check import BULK, _from_native, _load_case, _probe, _sha

REPORT = ROOT / "reports/2026_11_19_receiver_screening/acquisition-support/selective-capture"
CONTROL = Path("/srv/bulk/leo-dev/20261119-wide-regional/wide/libleo-adaptive-detector.so")
CONTROL_SHA = "db80b772cf9f52941cc0073067816e571308cb43c3096516b77f73ed54986c66"
CHOICES = {
    "DS26-0036": "first_16",
    "DS29-0082": "first_16",
    "DS26-0237": "first_128",
    "DS29-0174": "first_128",
}


def layout(case):
    start = 0
    for seg, locator in enumerate(case["recording"]["segments"]):
        path = (BULK / locator["path"]).resolve()
        if not path.is_relative_to(iq_stream.ARCHIVE_ROOT):
            raise ValueError("saved segment is outside the local corpus")
        data = iq_stream._read_prefix(path, 65_537)
        if sha256(data).hexdigest() != locator["sha256"]:
            raise ValueError("segment manifest differs from original replay")
        count = json.loads(data)["window_count"]
        yield seg, start, count
        start += count
    if start != case["recording"]["window_count"]:
        raise ValueError("the physical capture visit inventory is incomplete")


def plan():
    select = REPORT / "selection-lock.json"
    authority = json.loads(select.read_bytes())["cases"]
    cases = {}
    for ident, method in CHOICES.items():
        selected = {r["visit"] for r in authority[ident]["selection"]["policies"][method]}
        case = _load_case(ident)
        candidates = [
            (visit, seg, visit - start)
            for seg, start, count in layout(case)
            for visit in selected
            if start <= visit < start + min(count, 30)
        ]
        if not candidates:
            cases[ident] = dict(
                policy=method, status="unavailable", reason="no bounded selected prefix"
            )
            continue
        visit, segment, sequence = min(
            candidates,
            key=lambda x: sha256(
                f"selective-capture-witness-v1:{ident}:{method}:{x[0]}".encode()
            ).hexdigest(),
        )
        cases[ident] = dict(policy=method, visit=visit, segment=segment, sequence=sequence)
    return dict(selection_sha256=_sha(select), source_sha256=_sha(Path(__file__)), cases=cases)


def once(case_id, work):
    from leo.analysis.starlink.native_short_window import NativeShortWindow
    from leo.analysis.starlink.templates import CONTROL_SYMBOL_ROLL, qin_edge_pilot_frame

    frozen = json.loads((REPORT / "waveform-plan.json").read_bytes())
    if frozen["source_sha256"] != _sha(Path(__file__)) or frozen["selection_sha256"] != _sha(
        REPORT / "selection-lock.json"
    ):
        raise ValueError("saved waveform witness differs from its freeze")
    sample = frozen["cases"][case_id]
    if sample.get("status") == "unavailable":
        return sample
    case = _load_case(case_id)
    meta, policy, lineage_receipt = lineage.source_lineage(case)
    segment, sequence = sample["segment"], sample["sequence"]
    locator = case["recording"]["segments"][segment]
    with patch.object(iq_stream, "MAX_CHUNK_PREFIX", 48 * iq_stream.MIB):
        (window,) = iq_stream.load_windows(
            dict(
                recording_path=str(BULK / locator["path"]),
                recording_sha256="sha256:" + locator["sha256"],
            ),
            (sequence,),
        )
    if window.acquisition["global_visit"] != sample["visit"] or _sha(CONTROL) != CONTROL_SHA:
        raise ValueError("waveform, fast detector, or selected visit changed")
    wide_file = work / f"{case_id}-wide.json"
    capture_file = BULK / case["native"]["path"]
    selection = json.loads((REPORT / "selection-lock.json").read_bytes())["cases"][case_id]
    if (
        _sha(wide_file) != selection["wide_sha256"]
        or _sha(capture_file) != case["native"]["sha256"]
    ):
        raise ValueError("witness factor authority changed")
    archival = {
        role: dict(
            selective_capture.visit_pairs(json.loads(path.read_bytes())["source"]["probes"])
        )[sample["visit"]]
        for role, path in (("wide", wide_file), ("capture", capture_file))
    }
    rate = window.sample_rate_hz
    references = tuple(
        np.asarray(qin_edge_pilot_frame(rate, meta["edge"], symbol_roll=r), dtype="<c16")
        for r in (0, CONTROL_SYMBOL_ROLL)
    )
    begin, cpu = perf_counter_ns(), process_time_ns()
    status, captured = scan_capture_window(window, window.receiver_ids, policy)
    capture_time = dict(
        wall_ms=(perf_counter_ns() - begin) / 1e6, cpu_ms=(process_time_ns() - cpu) / 1e6
    )
    with NativeShortWindow(
        str(CONTROL), *references, sample_rate_hz=rate, fractional_epoch=True
    ) as wide:
        start, cpu = perf_counter_ns(), process_time_ns()
        rows = wide.analyze(window.samples)["rows"]
        wide_time = dict(
            wall_ms=(perf_counter_ns() - start) / 1e6, cpu_ms=(process_time_ns() - cpu) / 1e6
        )
    fast = [
        _probe(
            window, r["receiver_id"], (_from_native(i, c) for i, c in enumerate(r["candidates"]))
        )
        for r in rows
    ]
    outputs = dict(capture=captured, wide=fast)
    valid = status.status == "processed" and all(
        encoded(rows) == encoded(archival[m]) for m, rows in outputs.items()
    )
    return dict(
        sample,
        id=case_id,
        status="ok" if valid else "failed",
        iq_sha256=window.iq_sha256,
        exact={m: encoded(rows) == encoded(archival[m]) for m, rows in outputs.items()},
        payloads=outputs,
        archived_pair_sha256={m: sha256(encoded(rows)).hexdigest() for m, rows in archival.items()},
        clocks=dict(capture=capture_time, wide=wide_time),
        release=lineage_receipt["capture"]["release"],
        wide_library_sha256=CONTROL_SHA,
    )


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("action", choices=("plan", *CHOICES))
    cli.add_argument("work", type=local_output)
    args = cli.parse_args()
    if args.action == "plan":
        target = REPORT / "waveform-plan.json"
        if target.exists():
            raise ValueError("waveform plan already frozen")
        save_json(target, plan())
    else:
        save_json(REPORT / f"{args.action}-waveform.json", once(args.action, args.work))
