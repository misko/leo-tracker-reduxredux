"""Score sealed causal proposals against authentic targets and paired time controls."""

import gzip
import json
from collections import Counter, defaultdict
from hashlib import sha256
from pathlib import Path

from ..__main__ import save_json
from ..variants.coherent_peak_filter import FOLD_HZ, FRAME_RATE_HZ, wrapped
from .causal_track_scout_stride import CASES as STRIDE
from .causal_track_scout_stride import PARENT
from .causal_track_scout_trial import BAND, ORDER, REPORT
from .factor_cross import CFO, GATE, MARGIN, winner
from .factor_cross_trial import write_members
from .full_v5_check import _load_case
from .input_factor_bridge import BULK, REPO, SCREEN, _sha, check, read
from .input_factor_comparison import sealed
from .peak_support import lane
from .prefix_figures import csv_file

STRIDE_HELD = SCREEN / "receiver-core/cfo-stride"
LIMITS = (1, 2, 20)


def epoch(row):
    return row["integer_epoch_sample"] + row["fractional_epoch_offset_samples"]


def error(centers, observed, frame):
    return min((abs(wrapped(center - observed, frame)) for center in centers), default=None)


def present(peak, target, frame):
    return any(
        abs(wrapped(epoch(row) - epoch(peak), frame)) <= 2
        and abs(wrapped(row[CFO] - peak[CFO], FOLD_HZ)) <= 1000
        for row in target
        if row[GATE]
    )


def load_inputs(case, timing):
    capture = _load_case(case)
    origin = BULK / capture["native"]["path"]
    check(origin, capture["native"]["sha256"])
    wide = (
        BAND / "native" / f"{case}.json.gz"
        if case in ORDER
        else PARENT / "native" / "control" / f"{case}.json.gz"
    )
    content = gzip.decompress(wide.read_bytes())
    if sha256(content).hexdigest() != timing["wide_native_sha256"]:
        raise ValueError("target controls differ from the prospectively emitted wide stream")
    doc, historical = json.loads(content), read(origin)
    if (
        doc["source"]["session_id"] != capture["session_id"]
        or any(
            doc[k] != historical[k]
            for k in ("clock_anchor", "delivery_clocks", "last_sample_counter")
        )
        or doc["source"]["input_manifest_sha256"] != historical["source"]["input_manifest_sha256"]
        or doc["provenance"]["excluded_windows"] != historical["provenance"]["excluded_windows"]
    ):
        raise ValueError("target inputs differ in underlying acquisition authority")
    return doc, historical


def baseline_centers():
    pin = sealed(STRIDE_HELD, "prediction-lock.json")
    recorded = {}
    for case in ORDER[:2]:
        path = STRIDE_HELD / f"{case}-held.json.gz"
        check(path, pin["files"][path.name])
        doc = json.loads(gzip.decompress(path.read_bytes()))
        controls = {}
        for row in doc["rows"]:
            if row["status"] != "processed":
                continue
            if any(len(rx) > 4 for rx in row["centers"]):
                raise ValueError("held trace does not represent four-start control")
            for number, centers in enumerate(row["centers"]):
                controls[row["visit"], number] = centers
        recorded[case] = dict(
            centers=controls,
            detector_sha256=doc["release"]["library_sha256"]["control"],
            input_manifest_sha256=doc["producer"]["input_manifest_sha256"],
            sha256=_sha(path),
        )
    return recorded


def targets(case, document, historical, forecasts, baseline):
    samples = document["source"]["sample_rate_hz"]
    frame = samples / FRAME_RATE_HZ
    anchor = document["clock_anchor"]["sample_counter"]
    left, right = (d["source"]["probes"] for d in (document, historical))
    samples_per_block = 30 * samples
    if baseline and (
        baseline["input_manifest_sha256"] != document["source"]["input_manifest_sha256"]
        or "sha256:" + baseline["detector_sha256"] != document["provenance"]["detector_sha256"]
    ):
        raise ValueError("held four-start centers identify another detector or waveform")
    for a, b, predicted in zip(left, right, forecasts, strict=True):
        planned = (predicted["visit"], predicted["receiver_id"])
        if (
            planned != (a["visit_index"], a["receiver_id"])
            or predicted["counter"] != a["valid_start_counter"]
            or predicted["channel"] != a["channel"]
            or predicted["case"] != case
            or any(b[k] != v for k, v in a.items() if k != "candidates")
        ):
            raise ValueError("post-seal target/proposal join changed probe support or order")
        i, j = (winner(p["candidates"]) for p in (a, b))
        gate_wide = i is not None
        ref_wide = a["candidates"][i] if gate_wide else None
        ref_capture = b["candidates"][j] if j is not None else None
        choices = []
        if gate_wide:
            choices.append(("wide", ref_wide))
        if ref_capture:
            choices.append(("capture-era", ref_capture))
            if not gate_wide:
                choices.append(("capture-wide-no-positive", ref_capture))
            if not present(ref_capture, a["candidates"], round(frame)):
                choices.append(("capture-family-missed", ref_capture))
        standard = None if baseline is None else baseline["centers"].get(planned)
        for condition, peak in choices:
            measured = epoch(peak)
            yield dict(
                condition=condition,
                case=case,
                lane=list(lane(a)),
                visit=planned[0],
                counter=predicted["counter"],
                block=(predicted["counter"] - anchor) // samples_per_block,
                centers=predicted["centers"],
                measured_epoch_samples=measured,
                strength="weak" if peak[MARGIN] < 0.1 else "strong",
                observed_error=error(predicted["centers"], measured, frame),
                four_start_error=None if standard is None else error(standard, measured, frame),
                four_start_recorded=standard is not None,
            )


def paired(rows, frame):
    """Half-turn only the target epochs in each condition, lane, block and eligible set."""
    groups = defaultdict(list)
    for row in rows:
        row["null_error"] = None
        if row["centers"]:
            groups[row["condition"], row["strength"], tuple(row["lane"]), row["block"]].append(row)
    for group in groups.values():
        if len(group) < 2:
            continue
        mid = len(group) // 2
        for index, row in enumerate(group):
            null = group[(index + mid) % len(group)]
            row["null_error"] = error(row["centers"], null["measured_epoch_samples"], frame)
    return rows


def summarize(rows):
    groups = defaultdict(Counter)
    for r in rows:
        for strength in ("all", r["strength"]):
            counts = groups[f"{r['condition']}/{strength}"]
            counts["targets"] += 1
            counts["eligible"] += bool(r["centers"])
            counts["paired"] += r["null_error"] is not None
            counts["four_start_recorded"] += r["four_start_recorded"]
            for x in LIMITS:
                hit = r["observed_error"] is not None and r["observed_error"] <= x
                counts[f"hit_{x}"] += hit
                counts[f"paired_hit_{x}"] += hit and r["null_error"] is not None
                counts[f"null_hit_{x}"] += r["null_error"] is not None and r["null_error"] <= x
                counts[f"four_start_hit_{x}"] += (
                    r["four_start_error"] is not None and r["four_start_error"] <= x
                )
                counts[f"hint_hit_on_four_start_{x}"] += hit and r["four_start_recorded"]
                counts[f"hint_hits_four_start_miss_{x}"] += (
                    hit
                    and r["four_start_recorded"]
                    and not (r["four_start_error"] is not None and r["four_start_error"] <= x)
                )
    return dict(groups)


def read_rows(filename):
    output = defaultdict(list)
    with gzip.open(REPORT / filename, "rt") as stream:
        for row in map(json.loads, stream):
            output[row["case"]].append(row)
    return output


def publish():
    pin = sealed(REPORT, "prediction-lock.json")
    root = read(REPORT / "source-lock.json")
    for rel, digest in root["sources"].items():
        check(REPO / rel, digest)
    extension = read(REPORT / "stride-prediction-lock.json")
    check(REPORT / "stride-source-lock.json", extension["source_lock_sha256"])
    for name, digest in extension["files"].items():
        check(REPORT / name, digest)
    if pin["cases"] != list(ORDER) or extension["cases"] != list(STRIDE):
        raise ValueError("scoring roster differs from both prospective seals")
    history = read(REPORT / "timing.json") | read(REPORT / "stride-timing.json")
    forecasts = read_rows("proposals.jsonl.gz") | read_rows("stride-proposals.jsonl.gz")
    baseline = baseline_centers()
    by_case, csv_rows, targets_rows = {}, [], []
    for ident in (*ORDER, *STRIDE):
        wide, legacy = load_inputs(ident, history[ident])
        rows = paired(
            list(targets(ident, wide, legacy, forecasts[ident], baseline.get(ident))),
            wide["source"]["sample_rate_hz"] / FRAME_RATE_HZ,
        )
        targets_rows.extend(rows)
        by_case[ident] = summarize(rows)
        for key, count in sorted(by_case[ident].items()):
            csv_rows.append(dict(case=ident, condition=key, **count))
    save_json(
        REPORT / "scores.json",
        dict(
            cases=by_case,
            baseline={case: data["sha256"] for case, data in baseline.items()},
        ),
    )
    fields = sorted({key for row in csv_rows for key in row if key not in ("case", "condition")})
    csv_file(
        REPORT / "scores.csv",
        [
            dict(case=r["case"], condition=r["condition"], **{k: r.get(k, 0) for k in fields})
            for r in csv_rows
        ],
    )
    write_members(REPORT / "targets-after-seal.jsonl.gz", targets_rows)
    save_json(
        REPORT / "score-lock.json",
        dict(
            source_sha256=_sha(Path(__file__)),
            prediction_lock_sha256=_sha(REPORT / "prediction-lock.json"),
            stride_prediction_lock_sha256=_sha(REPORT / "stride-prediction-lock.json"),
            files={
                n: _sha(REPORT / n)
                for n in ("scores.json", "scores.csv", "targets-after-seal.jsonl.gz")
            },
        ),
    )


if __name__ == "__main__":
    publish()
