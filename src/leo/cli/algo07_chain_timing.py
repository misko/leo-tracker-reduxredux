"""Separate exclusive worker timings from a validated public ALGO07 terminal."""

import math
import time


def seconds(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("Numeric worker duration required")
    if not math.isfinite(value) or value < 0:
        raise ValueError("Finite nonnegative worker duration required")
    return value


def summarize(terminal):
    rows = []
    node = terminal
    for version in range(6, 0, -1):
        if node["schema_version"] != version or node["state"] != "complete":
            raise ValueError("Complete ALGO02 through ALGO07 chain required")
        if version == 1:
            elapsed = seconds(node["elapsed_seconds"])
            row = dict(algorithm="ALGO02", model_version=node["model_version"],
                       worker_seconds=elapsed, decision="baseline")
            row["substeps"] = [dict(stage=s["stage"], seconds=seconds(s["seconds"]))
                               for s in node.get("stages", [])]
            if sum(s["seconds"] for s in row["substeps"]) > elapsed + 1e-6:
                raise ValueError("Baseline substeps exceed elapsed duration")
            rows.append(row)
            break
        upstream = node["baseline" if version == 2 else "incumbent"]
        upstream_total = seconds(upstream["elapsed_seconds" if version == 2 else "total_seconds"])
        recorded_upstream = seconds(node["baseline_seconds" if version == 2
                                         else "incumbent_seconds"])
        own = seconds(node["numerical_seconds" if version == 3 else "recovery_seconds"])
        if (upstream_total != recorded_upstream or not math.isclose(
                upstream_total + own, seconds(node["total_seconds"]), rel_tol=1e-12, abs_tol=1e-6)):
            raise ValueError("Cumulative and exclusive worker durations disagree")
        rows.append(dict(algorithm=f"ALGO{version+1:02d}", model_version=node["model_version"],
                         worker_seconds=own, decision=node["decision"]))
        node = upstream
    rows.reverse()
    total = sum(r["worker_seconds"] for r in rows)
    if not math.isclose(total, terminal["total_seconds"], rel_tol=1e-12, abs_tol=1e-6):
        raise ValueError("Worker sum does not match published cumulative duration")
    return dict(stages=rows, position_worker_seconds=total, end_to_end_seconds=None,
                scope="Recorded position-worker wall durations; not CPU or end-to-end latency",
                excluded=["native GLRT", "acquisition", "queue waiting",
                          "watcher work outside worker timers, including publication"],
                scientific_inference_rerun=False)


def collect(args, *, store=None, native_store=None):
    if store is None or native_store is None:
        from leo.storage.fast_graph_position_v6 import FastGraphPositionStoreV6
        from leo.storage.fast_scan import FastScanStore

        store = store if store is not None else FastGraphPositionStoreV6(args.bulk_root)
        native_store = native_store if native_store is not None else FastScanStore(args.bulk_root)
    job = store.status(args.job)
    if not job or job.get("state") != "complete" or job.get("job_id") != args.job:
        raise ValueError("Completed ALGO07 job required")
    began = time.monotonic()
    terminal, receipt = store.terminal(job)
    validation_seconds = time.monotonic() - began
    result = summarize(terminal)
    native = native_store.detail(job["run_id"], include_points=False)
    if native["run_id"] != job["run_id"] or native["session_id"] != terminal["session_id"]:
        raise ValueError("Native report and position terminal identities differ")
    return dict(result, job_id=job["job_id"], run_id=job["run_id"],
                recording_name=native["recording_name"], window_count=native["window_count"],
                terminal_sha256=receipt["sha256"],
                observed_utc_ns=time.time_ns(), validation_seconds=validation_seconds,
                timing_note="This read's validation time is not part of the recorded worker sum")
