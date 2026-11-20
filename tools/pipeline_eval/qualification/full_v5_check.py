"""Compare the survey's deployed fractional detector with the native short-window detector.

Run from the repository root with the case's installed worker on PYTHONPATH,
the installed Python, one CPU of affinity and one BLAS thread. This command
accounts for the original-rate first eight visits and emits diagnostic v5 probe
rows. An incomplete recording cannot produce a v5 positioning request here.
"""

import argparse
import json
import os
import time
from dataclasses import dataclass
from functools import cache
from hashlib import file_digest, sha256
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
FROZEN = REPO / "tools/pipeline_eval/frozen"
BULK = Path("/srv/bulk")
MARGIN_GATE = 0.025
FRAME_HZ = 750
ALIAS_HZ = 1 / 4.4e-6
EPOCH_TOLERANCE_SAMPLES = 2
CFO_TOLERANCE_HZ = 1000
PREFIX_VISITS = 8
BUDGET_S = 15 * 60
NATIVE_LIBRARY = REPO / ".build-short-window-native-host/libleo-adaptive-detector.so"


@dataclass(frozen=True)
class Producer:
    root: Path
    input_manifest_sha256: str


PRODUCERS = {
    "DS26-0036": Producer(
        Path("/opt/leo-shared-scans/native-scope64-v2-3460060352b364a9/worker/src"),
        "sha256:8ac4a2b2e24de8ae2cccd592cb55e8d86226dd9e6c0f5046b8957a5880c4d76b",
    ),
    "DS29-0082": Producer(
        Path("/opt/leo-standard-fast/17bf8ccfa3dd495f040fcb05fbcffcb1e11c42e3/native-worker/src"),
        "sha256:954f0fec1dfbd9c86e91272033683abeb9144466fb6810ca53f43c9e40809c6d",
    ),
}


def _sha(path):
    with path.open("rb") as stream:
        return file_digest(stream, "sha256").hexdigest()


def _load_case(case_id):
    data = (FROZEN / "inputs.jsonl").read_bytes()
    expected = json.loads((FROZEN / "provenance.json").read_bytes())["files"]["inputs.jsonl"]
    if sha256(data).hexdigest() != expected:
        raise ValueError("frozen input inventory changed")
    return next(row for row in map(json.loads, data.splitlines()) if row["id"] == case_id)


def _bind_producer(case, producer, policy):
    from leo.contracts.digests import canonical_digest
    from leo.processing.fast_scan import implementation_identity

    if not Path(implementation_identity.__code__.co_filename).is_relative_to(producer.root):
        raise ValueError(f"set PYTHONPATH to the installed producer at {producer.root}")
    code, environment = implementation_identity()
    configuration = {
        "stages": {"fast-scan": policy.model_dump(mode="json")},
        "implementation_digest": code,
        "execution": {"maximum_windows_per_job": 64},
    }
    release = "fast-" + canonical_digest([code, environment, configuration]).split(":")[1][:32]
    identity = [case["session_id"], producer.input_manifest_sha256, release]
    run_id = "fast-" + canonical_digest(identity).split(":")[1][:32]
    if run_id != case["run_id"]:
        raise ValueError(
            "installed source, environment and detector policy did not reproduce run identity"
        )
    return dict(
        root=str(producer.root),
        code_sha256=code,
        environment_sha256=environment,
        input_manifest_sha256=producer.input_manifest_sha256,
        release=release,
        run_id=run_id,
        configuration=configuration,
    )


def factor_candidate(rank, epoch, *, status, offset, cfo, exact, control, margin):
    """Project only complete fractional candidates into the published TrackingCandidate shape."""
    if status != "complete":
        return None
    if any(value is None for value in (offset, cfo, exact, control, margin)):
        raise ValueError("complete fractional detection is missing a numeric field")
    return dict(
        candidate_rank=rank,
        integer_epoch_sample=epoch,
        fractional_epoch_offset_samples=offset,
        fractional_tracking_cfo_hz=cfo,
        fractional_exact_score=exact,
        fractional_control_score=control,
        fractional_margin=margin,
        passed_fractional_margin_gate=margin >= MARGIN_GATE,
    )


def _from_production(candidate):
    return factor_candidate(
        candidate.candidate_rank,
        candidate.epoch_sample,
        status=candidate.fractional_epoch_status,
        offset=candidate.fractional_epoch_offset_samples,
        cfo=candidate.fractional_tracking_cfo_hz,
        exact=candidate.fractional_exact_score,
        control=candidate.fractional_control_score,
        margin=candidate.fractional_margin,
    )


def _from_native(rank, candidate):
    fractional = candidate["fractional_epoch"]
    return factor_candidate(
        rank,
        candidate["epoch"],
        status=fractional["status"],
        offset=fractional["offset_samples"],
        cfo=fractional["tracking_cfo_hz"],
        exact=fractional["exact_score"],
        control=fractional["control_score"],
        margin=fractional["margin"],
    )


def _probe(window, receiver, candidates):
    acquisition, target = window.acquisition, window.target
    visit = acquisition["global_visit"]
    return dict(
        visit_index=visit,
        receiver_id=receiver,
        probe_index=0,
        probe_start_ms=0,
        channel=target["channel"],
        edge=target["edge"],
        actual_rf_hz=float(acquisition["actual_if_center_hz"] + target["lnb_lo_hz"]),
        valid_start_counter=acquisition["sample_start"],
        payload_start_sample=visit * (window.sample_rate_hz // 50),
        candidates=[c for c in candidates if c is not None],
    )


def _wrapped(delta, period):
    return (delta + period / 2) % period - period / 2


def compare_probes(production, native, rate):
    """Match positive candidates once per receiver, allowing frame and CFO aliases."""
    if any(production[key] != native[key] for key in production if key != "candidates"):
        raise ValueError("matched probes do not share the same support")
    left, right = (
        [c for c in p["candidates"] if c["passed_fractional_margin_gate"]]
        for p in (production, native)
    )
    pairs = [[] for _ in left]
    for i, baseline in enumerate(left):
        for j, candidate in enumerate(right):
            epoch = _wrapped(
                candidate["integer_epoch_sample"]
                + candidate["fractional_epoch_offset_samples"]
                - baseline["integer_epoch_sample"]
                - baseline["fractional_epoch_offset_samples"],
                round(rate / FRAME_HZ),
            )
            cfo = candidate["fractional_tracking_cfo_hz"] - baseline["fractional_tracking_cfo_hz"]
            alias = _wrapped(cfo, ALIAS_HZ)
            if abs(epoch) <= EPOCH_TOLERANCE_SAMPLES and abs(alias) <= CFO_TOLERANCE_HZ:
                distance = abs(epoch) / EPOCH_TOLERANCE_SAMPLES + abs(alias) / CFO_TOLERANCE_HZ
                match = dict(
                    production_rank=baseline["candidate_rank"],
                    native_rank=candidate["candidate_rank"],
                    epoch_delta_samples=epoch,
                    raw_cfo_delta_hz=cfo,
                    aliased_cfo_delta_hz=alias,
                    margin_delta=candidate["fractional_margin"] - baseline["fractional_margin"],
                )
                pairs[i].append((j, distance, match))

    # Each receiver has at most eight candidates. The mask records which of
    # the native candidates have already been assigned.
    @cache
    def assign(i, used):
        if i == len(left):
            return 0, 0.0, ()
        best = assign(i + 1, used)
        for j, distance, match in pairs[i]:
            bit = 1 << j
            if used & bit:
                continue
            count, cost, matches = assign(i + 1, used | bit)
            score = count - 1, cost + distance
            if score < best[:2]:
                best = (*score, (match, *matches))
        return best

    _, _, matches = assign(0, 0)
    return dict(
        production_complete=len(production["candidates"]),
        native_complete=len(native["candidates"]),
        production_positive=len(left),
        native_positive=len(right),
        positive_matches=matches,
        production_only=len(left) - len(matches),
        native_only=len(right) - len(matches),
    )


def _run_prefix(case, policy, library, output):
    import numpy as np

    from leo.analysis.starlink import native_short_window, templates
    from leo.scanner.fast_scan_analysis import analyze_window
    from tools.pipeline_eval.variants.iq_stream import load_windows

    for module in (native_short_window, templates):
        rel = Path(module.__file__).relative_to(PRODUCERS[case["id"]].root)
        if _sha(Path(module.__file__)) != _sha(REPO / "src" / rel):
            raise ValueError(f"candidate arm source differs from iq_position: {rel}")
    locator = case["recording"]["segments"][0]
    started = time.perf_counter()
    windows = load_windows(
        dict(
            recording_path=str(BULK / locator["path"]),
            recording_sha256="sha256:" + locator["sha256"],
        ),
        range(PREFIX_VISITS),
    )
    reader_s = time.perf_counter() - started
    edge = windows[0].target["edge"]
    rate = windows[0].sample_rate_hz
    receivers = windows[0].receiver_ids
    exact = np.asarray(templates.qin_edge_pilot_frame(rate, edge), dtype="<c16")
    control = np.asarray(
        templates.qin_edge_pilot_frame(rate, edge, symbol_roll=templates.CONTROL_SYMBOL_ROLL),
        dtype="<c16",
    )
    rows = []
    with (
        native_short_window.NativeShortWindow(
            str(library),
            exact,
            control,
            sample_rate_hz=rate,
            receiver_count=len(receivers),
            fractional_epoch=True,
        ) as native,
        output.open("x", encoding="utf-8") as stream,
    ):
        for window in windows:
            visit = window.acquisition["global_visit"]
            if (
                visit != len(rows)
                or window.target["edge"] != edge
                or window.sample_rate_hz != rate
                or window.receiver_ids != receivers
            ):
                raise ValueError("recorded prefix changed order or detector geometry")
            start, cpu = time.perf_counter(), time.process_time()
            result = analyze_window(window, receivers, None, policy)
            row = dict(
                visit=visit,
                iq_sha256=window.iq_sha256,
                input_bytes=window.samples.nbytes,
                policy_status=result.status,
                reason=result.reason,
                sample_start=window.acquisition["sample_start"],
                sample_end=window.acquisition["sample_end"],
                quality_flags=window.acquisition.get("quality_flags", []),
                receiver_center_hz=(
                    window.target["rf_center_hz"]
                    - window.target["lnb_lo_hz"]
                    - window.acquisition["actual_if_center_hz"]
                ),
                production_s=time.perf_counter() - start,
                production_cpu_s=time.process_time() - cpu,
                production=[],
                native=[],
            )
            if result.status == "processed":
                start, cpu = time.perf_counter(), time.process_time()
                candidate_rows = native.analyze(window.samples)["rows"]
                row.update(
                    native_s=time.perf_counter() - start, native_cpu_s=time.process_time() - cpu
                )
                row["production"] = [
                    _probe(window, p.receiver_id, map(_from_production, p.candidates))
                    for p in result.receivers
                ]
                row["native"] = [
                    _probe(
                        window,
                        receivers[p["receiver_id"]],
                        (_from_native(rank, c) for rank, c in enumerate(p["candidates"])),
                    )
                    for p in candidate_rows
                ]
                if (
                    tuple(p["receiver_id"] for p in row["production"]) != receivers
                    or tuple(p["receiver_id"] for p in row["native"]) != receivers
                ):
                    raise ValueError("detector output is missing or reorders a receiver")
            stream.write(json.dumps(row, allow_nan=False) + "\n")
            stream.flush()
            rows.append(row)
    return rows, reader_s, rate


def _measure(case, rows, rate):
    # Access the original numerical rows only after the fresh replay is persisted.
    path = BULK / case["native"]["path"]
    if _sha(path) != case["native"]["sha256"]:
        raise ValueError("archived v5 probe reference changed")
    original = json.loads(path.read_bytes())
    source = original["source"]
    if (
        source["session_id"] != case["session_id"]
        or original["provenance"]["run_id"] != case["run_id"]
    ):
        raise ValueError("archived v5 probe reference belongs to another recording")
    visited = {row["visit"] for row in rows}
    reference = {
        (p["visit_index"], p["receiver_id"]): p
        for p in source["probes"]
        if p["visit_index"] in visited
    }
    replayed = {(p["visit_index"], p["receiver_id"]): p for row in rows for p in row["production"]}
    disagreements = [
        list(key)
        for key in sorted(reference.keys() | replayed.keys())
        if reference.get(key) != replayed.get(key)
    ]
    expected_invalid = {
        r["visit"]: r for r in original["provenance"]["excluded_windows"] if r["visit"] in visited
    }
    replayed_invalid = {
        r["visit"]: {
            k: r[k] for k in ("visit", "reason", "iq_sha256", "sample_start", "sample_end")
        }
        for r in rows
        if r["policy_status"] == "invalid_capture"
    }
    comparison = [
        dict(
            visit=left["visit_index"],
            receiver=left["receiver_id"],
            **compare_probes(left, right, rate),
        )
        for row in rows
        for left, right in zip(row["production"], row["native"], strict=True)
    ]
    return dict(
        archive_sha256=case["native"]["sha256"],
        archived_probe_rows=len(reference),
        exact_probe_rows=len(reference) - sum(tuple(key) in reference for key in disagreements),
        different_probe_keys=disagreements,
        archive_exclusions_equal=expected_invalid == replayed_invalid,
        archived_status_counts={
            k: original["provenance"][k]
            for k in ("processed_windows", "invalid_capture", "skipped_fast_score")
        },
        receivers=comparison,
    )


def main():
    from leo.contracts.fast_scan_native import FastScanPolicyV2

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", choices=PRODUCERS)
    parser.add_argument("output", type=Path)
    parser.add_argument("--native-library", type=Path, default=NATIVE_LIBRARY)
    args = parser.parse_args()
    cpus = sorted(os.sched_getaffinity(0))
    if len(cpus) != 1 or any(
        os.environ.get(key) != "1"
        for key in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS")
    ):
        parser.error(
            "this qualification requires one CPU of affinity and one thread per BLAS runtime"
        )
    directory = args.output.resolve()
    if directory.is_relative_to("/mnt/qnap01") or directory.is_relative_to(BULK / "leo"):
        parser.error("the qualification output must live outside the recording archive")
    policy = FastScanPolicyV2()
    case = _load_case(args.case)
    producer = _bind_producer(case, PRODUCERS[args.case], policy)
    library = args.native_library.resolve(strict=True)
    directory.mkdir(parents=True, exist_ok=False)
    rows, reader_s, rate = _run_prefix(case, policy, library, directory / "visits.jsonl")
    summary = _measure(case, rows, rate)
    status = summary["archived_status_counts"]
    production_cpu = [r["production_cpu_s"] for r in rows if r["policy_status"] == "processed"]
    summary.update(
        case=args.case,
        producer=producer,
        cpus=cpus,
        library=str(library),
        library_sha256=_sha(library),
        run_kind="authenticated recording prefix",
        recording_window_count=case["recording"]["window_count"],
        replayed_windows=len(rows),
        processed_windows=len(production_cpu),
        sample_rate_hz=rate,
        iq_bytes=sum(r["input_bytes"] for r in rows),
        reader_s=reader_s,
        two_core_budget_s=BUDGET_S,
        production_cpu_s_per_valid_window=production_cpu,
        two_core_detector_only_estimate_s=sum(production_cpu)
        / len(production_cpu)
        * status["processed_windows"]
        / 2,
        two_core_budget_cpu_s_per_valid_window=2 * BUDGET_S / status["processed_windows"],
        absolute_epoch_match_tolerance_samples=EPOCH_TOLERANCE_SAMPLES,
        alias_cfo_match_tolerance_hz=CFO_TOLERANCE_HZ,
    )
    (directory / "summary.json").write_text(json.dumps(summary, indent=2, allow_nan=False) + "\n")


if __name__ == "__main__":
    main()
