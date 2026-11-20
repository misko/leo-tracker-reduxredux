"""Observe terminal compact support and capture-start catalogue use in one capped worker."""

import hashlib
import json
import os
import runpy
import sys
from contextlib import ExitStack
from pathlib import Path
from resource import RUSAGE_SELF, getrusage
from time import perf_counter
from unittest.mock import patch


def local_support(problem, endpoint, gates, geometry):
    diagnostic = geometry(problem, endpoint, gates)
    latest = {}
    tracks = {t["key"]: t for t in problem.scan.tracks}
    for row in gates["tracks"]:
        if row["compatible"]:
            track = tracks[row["component"]]
            times = dict(zip(track["observation_ids"], track["times"], strict=True))
            norad = str(row["norad"])
            latest[norad] = max(
                latest.get(norad, 0), *(float(times[i]) for i in row["observation_ids"])
            )
    return dict(diagnostic, latest_by_norad=latest)


def measure(attempt):
    request = json.loads((attempt / "request.json").read_bytes())
    root = Path(request["receiver"])
    args = request["compact"]
    expected = request["support"]
    group = Path("/sys/fs/cgroup") / Path("/proc/self/cgroup").read_text().strip().split(":", 2)[
        2
    ].lstrip("/")
    if (
        os.sched_getaffinity(0) != {request["cpu"]}
        or (group / "memory.max").read_text().strip() != str(512 * 1024**2)
        or (group / "memory.swap.max").read_text().strip() != "0"
    ):
        raise ValueError("the compact worker lacks its fixed CPU and memory envelope")
    begin = perf_counter()
    geometry = runpy.run_path(str(Path(__file__).with_name("short_compact_worker.py")))["geometry"]
    entry = runpy.run_path(str(root / "__main__.py"))
    entry["activate"](root)
    entry["validate_region"](args["tile"], args["screen_center"], args["width_km"])
    from leo.analysis.localization_v3 import (
        event_position,
        family_cavity,
        history_position,
        predictive_linear,
        signed_context,
    )

    from leo.application import localization_v3
    from tools.pipeline_eval.variants import v5_direct_cavity

    candidates, terminal, audit = {}, {}, {}
    original = history_position.retained_metrics
    prepare = localization_v3.prepare_native_scan
    diagnostic_s = 0.0

    def capture(problem, endpoint):
        nonlocal diagnostic_s
        gates = original(problem, endpoint)
        if gates["tracks"]:
            start = perf_counter()
            try:
                support = local_support(problem, endpoint, gates, geometry)
            except (ArithmeticError, ValueError) as error:
                support = {"geometry_error": str(error)}
            diagnostic_s += perf_counter() - start
            candidates[id(gates)] = (gates, support)
        return gates

    def observe(original_step, arm_field):
        def wrapped(*positional, **kwargs):
            decision = original_step(*positional, **kwargs)
            if arm_field in decision:
                terminal.clear()
                for arm, result in decision[arm_field].items():
                    selected = candidates.get(id(result["gates"]))
                    if selected is not None:
                        terminal[arm] = dict(selected[1], latlon=list(result["endpoint_latlon"]))
            return decision

        return wrapped

    def prepared(document, *args, **kwargs):
        if len(document["delivery_clocks"]) != expected["scheduled"]:
            raise ValueError("unexpected native window scope")
        first = document["clock_anchor"]["sample_counter"]
        anchor = document["clock_anchor"]["before"]["realtime_ns"]
        rate = document["source"]["sample_rate_hz"]
        cutoff = (document["last_sample_counter"] - first) / rate
        if (
            cutoff != expected["actual_end_s"]
            or len(document["source"]["probes"]) != expected["probe_count"]
        ):
            raise ValueError("native factor support exceeds its registered checkpoint")
        values = prepare(document, *args, **kwargs)
        tracks, sky = values["tracks"], values["sky"]
        end = max((row["time_s"] for row in tracks["observations"]), default=0)
        if end > cutoff or tracks["metadata"]["causal_cutoff_utc_ns"] != anchor:
            raise ValueError("Graph changed the capture-start time authority")
        audit.update(latest_graph_s=end, causal_cutoff_utc_ns=anchor)
        if sky is not None:
            metadata = sky["metadata"]
            latest_tle = max(
                value
                for element in sky["nominal_elements"].values()
                for value in (
                    element["provenance"]["collected_utc_ns"],
                    element["provenance"]["element_epoch_utc_ns"],
                )
            )
            if metadata["cutoff_utc_ns"] != anchor or latest_tle > anchor:
                raise ValueError("candidate geometry used a later catalogue")
            audit.update(
                candidate_count=metadata["candidate_count"],
                latest_tle_utc_ns=latest_tle,
                selected_tle_sha256=hashlib.sha256(sky["selected_tle"].encode()).hexdigest(),
            )
        return values

    with ExitStack() as stack:
        if request["diagnostics"]:
            for module in (history_position, predictive_linear, event_position):
                stack.enter_context(patch.object(module, "retained_metrics", capture))
            stack.enter_context(
                patch.object(
                    signed_context, "signed_context", observe(signed_context.signed_context, "arms")
                )
            )
            stack.enter_context(
                patch.object(
                    family_cavity,
                    "cavity_policy",
                    observe(family_cavity.cavity_policy, "policy_arms"),
                )
            )
        stack.enter_context(patch.object(localization_v3, "prepare_native_scan", prepared))
        result = v5_direct_cavity.run(**args)
    entry["verify_project_modules"](root)
    for arm, row in terminal.items():
        if row["latlon"] != result["arms"][arm]["latlon"] or any(
            t > expected["actual_end_s"] for t in row.get("latest_by_norad", {}).values()
        ):
            raise ValueError("terminal support differs from the selected endpoint or checkpoint")
    if request["diagnostics"] and result["status"] == "ok" and set(terminal) != set(result["arms"]):
        raise ValueError("selected compact outcome is missing terminal support diagnostics")
    result["metrics"].update(
        terminal_support=terminal, causal_audit=audit, support_diagnostic_wall_s=diagnostic_s
    )
    result["metrics"].update(
        worker_wall_s=perf_counter() - begin,
        process_rss_peak_kib=getrusage(RUSAGE_SELF).ru_maxrss,
    )
    (attempt / "worker-result.json").write_text(json.dumps(result, allow_nan=False))


if __name__ == "__main__":
    measure(Path(sys.argv[1]))
