"""Seal the full chronological experiment, then score matched detections and position."""

import argparse
import gzip
import io
import json
import tarfile
from collections import Counter
from hashlib import file_digest
from pathlib import Path

from .. import whole_iq
from ..__main__ import ROOT, local_output, save_json
from ..scoring import ARMS, ROLES, distance_km, validate_result
from . import hinted_whole as trial
from . import hinted_whole_raw as live
from .full_held_scores import held_references
from .full_receiver_comparison import read, require_fields, seal, sha
from .full_v5_check import ALIAS_HZ, CFO_TOLERANCE_HZ, EPOCH_TOLERANCE_SAMPLES
from .winner_stream_results import csv_file, scientific_result

CASES = tuple(trial.SCHEDULE)
MODES = {"stock": "hinted_whole_stock", "hinted": "hinted_whole"}
PROOFS = (
    "clock_sha256",
    "excluded_sha256",
    "raw_authority",
    "probes_sha256",
    "input_manifest_sha256",
)
ARCHIVE = "positions.jsonl.gz"
TRACES = "trace.jsonl.gz"
PREDICTIONS = "prediction-lock.json"


def pack(path, rows):
    raw = "".join(json.dumps(row, sort_keys=True, allow_nan=False) + "\n" for row in rows)
    path.write_bytes(gzip.compress(raw.encode(), mtime=0))


def unpack(path):
    with gzip.open(path, "rt") as content:
        return [json.loads(line) for line in content]


def measurements(work, plan, ident, role):
    attempt = work / ident / role
    bind = plan["cases"][ident]
    require_fields(
        read(attempt / "plan.json"),
        dict(
            id=ident,
            role=role,
            binding=bind,
            detector=plan["libraries"][role],
            receiver_files=plan["receiver"]["files"],
        ),
    )
    service = read(attempt / "service.json")
    whole_iq.checked(attempt / "service.log", service["log_sha256"])
    complete = service["exit_code"] == 0 and service["systemd"]["Result"] == "success"
    start = read(attempt / "start.json") if (attempt / "start.json").exists() else None
    raw = read(attempt / "raw.json") if (attempt / "raw.json").exists() else None
    end = read(attempt / "end.json") if (attempt / "end.json").exists() else None
    raw_end, position = (raw[key] if raw else None for key in ("raw_end", "position_start"))
    for mark in (start, raw_end, position, end):
        if mark and (
            mark["cpus"] != [bind["cpu"]]
            or mark["cgroup"] != start["cgroup"]
            or mark["memory.max"] != plan["memory"]
            or mark["memory.swap.current"] != 0
            or mark["memory.swap.max"] != 0
        ):
            raise ValueError("detector or position worker left its matched physical envelope")
    if complete:
        result = read(attempt / "position.json")
    else:
        status = "timed_out" if service["systemd"]["Result"] == "timeout" else "failed"
        result = dict(
            status=status,
            reason=service["systemd"]["Result"],
            metrics={},
            arms={a: {"latlon": None} for a in ARMS},
        )
    validate_result(result)
    traces = []
    if raw:
        out = attempt / "recording"
        whole_iq.checked(out / "chronological.jsonl", raw["chronological_sha256"])
        whole_iq.checked(out / "native.winners", raw["private_sha256"])
        log = whole_iq.checked(out / "detector.log", raw["detector_log_sha256"])
        prefix = "hint-trace: "
        for line in log.read_text().splitlines():
            if line.startswith(prefix):
                traces.append(dict(json.loads(line[len(prefix) :]), id=ident, role=role))
        counts = raw["feedback"]["counts"]
        if (
            len(traces) != counts.get("trace_visits", 0)
            or sum(sum(row["applied"]) for row in traces) != counts.get("applied", 0)
            or any(b["visit"] <= a["visit"] for a, b in zip(traces, traces[1:], strict=False))
        ):
            raise ValueError("chronological feedback summary differs from its event ledger")
    result_row = dict(
        id=ident,
        role=role,
        method=MODES[role],
        mode="matched-tile",
        tile=bind["tile"],
        capture_native_sha256=bind["capture_native_sha256"],
        catalog_sha256=bind["catalog_sha256"],
        input_sha256=bind["request_sha256"],
        native_sha256=raw["native_sha256"].removeprefix("sha256:") if raw else None,
        result=result,
        start=start,
        raw=raw,
        end=end,
        service=service,
    )
    return result_row, traces


def freeze_outputs(work, dest):
    pin = (work / "study.sha256").read_text().strip()
    source = whole_iq.checked(dest / "source-lock.json", pin)
    plan = read(source)
    records, traces = [], []
    for ident in CASES:
        for role in MODES:
            row, events = measurements(work, plan, ident, role)
            records.append(row)
            traces.extend(events)
    for ident in CASES:
        a, b = (r["raw"] for r in records if r["id"] == ident)
        if a and b:
            require_fields(a, {field: b[field] for field in PROOFS})
    pack(dest / ARCHIVE, records)
    pack(dest / TRACES, traces)
    src = "as-measured-source.tar.gz"
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as archive:
        for name, pin in plan["sources"].items():
            data = whole_iq.checked(ROOT / name, pin).read_bytes()
            item = tarfile.TarInfo(name)
            item.size = len(data)
            archive.addfile(item, io.BytesIO(data))
    (dest / src).write_bytes(gzip.compress(buffer.getvalue(), mtime=0))
    owners = "owner-verification.json"
    scout = dest.parent / "causal-track-scout/source-lock.json"
    scout_pin = plan["sources"][str(scout.relative_to(ROOT))]
    whole_iq.checked(scout, scout_pin)
    dependencies = {
        name: bound
        for name, bound in read(scout)["sources"].items()
        if Path(name).name in {"causal_track_scout.py", "coherent_peak_filter.py", "track_epoch.py"}
    }
    if len(dependencies) != 3:
        raise ValueError("the scout's required source closure differs from its owner seal")
    for name, bound in dependencies.items():
        whole_iq.checked(ROOT / name, bound)
    whole_iq.checked(trial.BUILD, plan["build_lock_sha256"])
    abi = read(trial.BUILD)
    if abi["library_sha256"] != {role: item["sha256"] for role, item in plan["libraries"].items()}:
        raise ValueError("loaded hint ABI and stock library changed from the booked build")
    save_json(
        dest / owners,
        dict(
            scout_source_lock_sha256=scout_pin,
            scout_dependencies=dependencies,
            native_build_lock_sha256=plan["build_lock_sha256"],
            native_build=abi,
        ),
    )
    names = ("source-lock.json", src, ARCHIVE, TRACES, owners)
    save_json(dest / PREDICTIONS, dict(cases=list(CASES), files={n: sha(dest / n) for n in names}))


def key(probe):
    return tuple(
        probe[k]
        for k in (
            "visit_index",
            "receiver_id",
            "valid_start_counter",
            "channel",
            "actual_rf_hz",
        )
    )


def qualified_probes(rows):
    result = {}
    for probe in rows:
        token = key(probe)
        if token in result:
            raise ValueError("duplicate native receiver probe")
        result[token] = [
            c for c in probe["candidates"] if c["passed_fractional_margin_gate"] is True
        ]
    return result


def matches(a, b, frame):
    def within(difference, period, tolerance):
        return abs((difference + period / 2) % period - period / 2) <= tolerance

    if a is None or b is None:
        return False

    def epoch(candidate):
        return candidate["integer_epoch_sample"] + candidate["fractional_epoch_offset_samples"]

    y = "fractional_tracking_cfo_hz"
    return within(epoch(a) - epoch(b), frame, EPOCH_TOLERANCE_SAMPLES) and within(
        a[y] - b[y], ALIAS_HZ, CFO_TOLERANCE_HZ
    )


def detector_scores(work, records, traces):
    out = {}
    intervention = {
        (row["id"], row["visit"], receiver)
        for row in traces
        if row["role"] == "hinted"
        for receiver, applied in enumerate(row["applied"])
        if applied
    }
    for ident in CASES:
        roles = {r["role"]: r for r in records if r["id"] == ident}
        if not all(r["raw"] for r in roles.values()):
            out[ident] = {"available": False}
            continue
        joined = {}
        for role, row in roles.items():
            path = work / ident / role / "recording/chronological.jsonl"
            whole_iq.checked(path, row["raw"]["chronological_sha256"])
            with path.open() as handle:
                joined[role] = qualified_probes(
                    p
                    for visit in map(json.loads, handle)
                    if visit["kind"] == "visit"
                    for p in visit["probes"]
                )
        stock, changed = (joined[name] for name in MODES)
        if stock.keys() != changed.keys():
            raise ValueError("detector replay support changed")
        _, request = whole_iq.binding(ident)
        archived = request["job"]["native_input"]
        trusted = whole_iq.checked(Path(archived["path"]), archived["sha256"])
        teacher = qualified_probes(read(trusted)["source"]["probes"])
        pairs = Counter()
        for token, before in stock.items():
            after = changed[token]
            pairs["added_positive"] += not before and bool(after)
            pairs["lost_positive"] += bool(before) and not after
            anchor = live.choose(teacher.get(token, ()))
            if anchor is None:
                continue
            pairs["capture_era_positive_on_exact_support"] += 1
            had, now = (
                matches(anchor, live.choose(options), trial.hinted_glrt.FRAME)
                for options in (before, after)
            )
            pairs["matched_capture_era_stock"] += had
            pairs["matched_capture_era_hinted"] += now
            pairs["capture_era_match_gained"] += now and not had
            pairs["capture_era_match_lost"] += had and not now
            was_available, available = (
                any(matches(anchor, candidate, trial.hinted_glrt.FRAME) for candidate in options)
                for options in (before, after)
            )
            pairs["available_capture_era_stock"] += was_available
            pairs["available_capture_era_hinted"] += available
            pairs["capture_era_prior_miss_gained"] += available and not was_available
            pairs["capture_era_prior_detection_lost"] += was_available and not available
            if (ident, *token[:2]) in intervention:
                pairs["capture_era_match_gained_at_replacement"] += now and not had
                pairs["capture_era_match_lost_at_replacement"] += had and not now
                pairs["capture_era_prior_miss_gained_at_replacement"] += (
                    available and not was_available
                )
        out[ident] = dict(
            available=True, paired_probes=len(stock), capture_era_sha256=sha(trusted), **pairs
        )
    return out


def independent_stock(source, records):
    folder = source.parent / "full-stride"
    pin = read(folder / PREDICTIONS)
    whole_iq.checked(folder / "source-lock.json", pin["files"]["source-lock.json"])
    archive = {
        r["id"]: r
        for r in unpack(whole_iq.checked(folder / ARCHIVE, pin["files"][ARCHIVE]))
        if r["method"] == "wide-cfo-stride_control"
    }
    matched = {}
    for stock in records:
        if stock["role"] != "stock":
            continue
        earlier = archive[stock["id"]]
        require_fields(
            earlier, {field: stock[field] for field in ("native_sha256", "catalog_sha256", "tile")}
        )
        name = f"native/control/{stock['id']}.json.gz"
        with gzip.open(whole_iq.checked(folder / name, pin["files"][name]), "rb") as stream:
            if file_digest(stream, "sha256").hexdigest() != stock["native_sha256"]:
                raise ValueError("the independent stock factor archive has a different digest")
        equal = scientific_result(earlier["result"]) == scientific_result(stock["result"])
        matched[stock["id"]] = dict(native_sha256=stock["native_sha256"], exact_science=equal)
    return dict(
        prediction_lock_sha256=sha(folder / PREDICTIONS),
        positions_sha256=pin["files"][ARCHIVE],
        method="wide-cfo-stride_control",
        matches=matched,
    )


def score(source, destination, *, work=None):
    seal(source, PREDICTIONS, (ARCHIVE, TRACES, "source-lock.json"))
    records = unpack(source / ARCHIVE)
    if [(r["id"], r["role"]) for r in records] != [(i, m) for i in CASES for m in MODES]:
        raise ValueError("position records lost a scheduled full-IQ role")
    _, reference = held_references("roof16", CASES)
    by_id = {r["id"]: r for r in reference}
    scores, resources = [], []
    for row in records:
        ident, role, result = (row[k] for k in ("id", "role", "result"))
        raw, start, end = (row[k] for k in ("raw", "start", "end"))
        feedback = raw["feedback"] if raw else {}
        counts = feedback.get("counts", {})
        resources.append(
            dict(
                id=ident,
                role=role,
                status=result["status"],
                reason=result.get("reason"),
                elapsed_s=row["service"]["wall_s"],
                cgroup_cpu_s=(end["cpu.stat.usage_usec"] - start["cpu.stat.usage_usec"]) / 1e6
                if end
                else None,
                peak_charge_mib=end["memory.peak"] / 2**20 if end else None,
                swap_bytes=end["memory.swap.current"] if end else None,
                detector_lane_wall_s=raw["raw_end"]["monotonic_s"] - start["monotonic_s"]
                if raw
                else None,
                detector_cpu_s=feedback["native_cpu_ns"] / 1e9 if raw else None,
                scout_cpu_s=feedback["feedback_cpu_ns"] / 1e9 if raw else None,
                proposals=counts.get("proposal_lanes"),
                proposed_centers=counts.get("proposed_centers"),
                applied=counts.get("applied", 0) if raw else None,
                processed_visits=counts.get("visits"),
                positive_lanes=counts.get("positive_lanes"),
                excluded_visits=raw["counts"]["invalid_capture"] if raw else None,
                solve_wall_s=end["monotonic_s"] - raw["position_start"]["monotonic_s"]
                if end
                else None,
            )
        )
        ref = by_id[ident]
        for arm in ARMS:
            fit = result["arms"][arm]
            scores.append(
                dict(
                    id=ident,
                    role=role,
                    status=result["status"],
                    arm=arm,
                    error_km=distance_km(ref["truth"], fit["latlon"]) if fit["latlon"] else None,
                    conditional_rms_hz=fit.get("rf_rms_hz"),
                    frequency_score=result["metrics"].get(f"{arm}_frequency_score"),
                    **{r: ref["reference"][r][arm]["error_km"] for r in ROLES},
                )
            )
    destination.mkdir(exist_ok=True, parents=True)
    csv_file(destination / "resources.csv", resources)
    csv_file(destination / "scores.csv", scores)
    if work is not None:
        detector = detector_scores(work, records, unpack(source / TRACES))
        save_json(destination / "detector-scores.json", detector)
        save_json(destination / "independent-stock.json", independent_stock(source, records))
        figure_inputs = (
            ARCHIVE,
            PREDICTIONS,
            TRACES,
            "resources.csv",
            "scores.csv",
            "detector-scores.json",
            "independent-stock.json",
        )
        save_json(
            destination / "figure-lock.json",
            dict(
                cases=list(CASES),
                source_lock_sha256=sha(source / "source-lock.json"),
                files={n: sha(destination / n) for n in figure_inputs},
            ),
        )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("action", choices=("seal", "score"))
    p.add_argument("source", type=local_output)
    p.add_argument("--out", type=local_output, default=trial.REPORT)
    args = p.parse_args()
    if args.action == "seal":
        freeze_outputs(args.source, args.out)
        score(args.out, args.out, work=args.source)
    else:
        score(args.source, args.out)


if __name__ == "__main__":
    main()
