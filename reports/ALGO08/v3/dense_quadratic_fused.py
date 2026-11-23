"""Replay the actual candidate's quadratic graph and fused geographic projection."""

import argparse
from contextlib import contextmanager
import gzip
from hashlib import sha256
import json
from math import isfinite
from pathlib import Path
from time import perf_counter_ns, process_time_ns
from unittest.mock import patch

from aperture_trial import read, write
from dense_geographic_trial import SCORE_TOLERANCE, difference
from dense_quadratic_proxy import GraphAudit, replay


CONTROL_SHA = "4b58d6487be44897f7528e383b2bb108f3e2dd0e5c81d9ae027fdaafbe91b5fb"
BINARY_SHA = "b8c8e0bb22e62fc69585909f193c76ab22ab4f2892d7fcbedd2cc31c78c573ee"
HERE = Path(__file__).resolve().parent


def checked_control(path):
    body = path.read_bytes()
    if sha256(body).hexdigest() != CONTROL_SHA:
        raise ValueError("Expected the original quadratic control on the dense detector proxy")
    control = json.loads(body)
    for name, digest in control["source_sha256"].items():
        if sha256((HERE / name).read_bytes()).hexdigest() != digest:
            raise ValueError(f"The measured live control route changed at {name}")
    if sha256((HERE / "dense_quadratic_proxy.py").read_bytes()).hexdigest() != control["experiment_source_sha256"]:
        raise ValueError("Expected the same original quadratic graph hook and timing instrumentation")
    return control


def compare(control, candidate):
    fields = ("identity", "status", "reason", "orbit_policy", "arms", "owners", "selected_rows", "associated",
              "science", "grid", "grid_points", "objective_replay", "source_sha256", "experiment_source_sha256")
    same = {name: control[name] == candidate[name] for name in fields}
    same["graph"] = (
        {k: v for k, v in control["graph"].items() if k != "clocks"}
        == {k: v for k, v in candidate["graph"].items() if k != "clocks"}
    )
    same["routes"] = [row["decision"] for row in control["attempts"]] == [row["decision"] for row in candidate["attempts"]]
    error = difference(control["visited_probes"], candidate["visited_probes"])
    same["probe_scores_and_owners"] = error <= SCORE_TOLERANCE and bool(candidate["visited_probes"])
    same["regional_decision"] = difference(
        [row["result"] for row in control["regional"]], [row["result"] for row in candidate["regional"]],
    ) <= SCORE_TOLERANCE
    tally = candidate["fused_geography"]["counts"]
    same["native_coverage"] = tally.get("calls") == len(candidate["visited_probes"]) and not tally.get("original_fallback")
    return same, error if isfinite(error) else None


def run(control_path, binary, output, summary, archive):
    control = checked_control(control_path)
    graph = GraphAudit()
    geo = {}

    @contextmanager
    def configure(assets, route):
        from dense_geographic_projection import Projector, checked_runtime

        start = process_time_ns(), perf_counter_ns()
        kernel, original = checked_runtime()
        projector = Projector(binary, BINARY_SHA, original)
        geo["setup"] = dict(cpu_s=(process_time_ns()-start[0])/1e9, elapsed_s=(perf_counter_ns()-start[1])/1e9)
        with (graph.configure(assets, route), patch.object(kernel, "phase_linear_frequency", projector)):
            yield
        geo["counts"] = dict(projector.counts)
        geo["binary_sha256"] = BINARY_SHA

    def report():
        return dict(graph.report(), fused_geography=geo)

    replay("control", output, configure_solve=configure, result_details=report)
    candidate = read(output)
    same, error = compare(control, candidate)
    for row in (control, candidate):
        if row["status"] != "ok" or not row["grid"]["complete"] or len(row["grid"]["points"]) != row["grid_points"]:
            raise ValueError("Expected terminal both-arm comparison with complete numerical grid")
    result = dict(
        valid=all(same.values()), checks=same, probe_max_difference=error, control_sha256=CONTROL_SHA,
        projector=geo, candidate_sha256=sha256(output.read_bytes()).hexdigest(),
        graph=candidate["graph"], identity=candidate["identity"],
        records={name: dict(solve=row["solve"], regional=row["regional"], arms=row["arms"],
                           owners=row["associated"], grid_points=row["grid_points"], science=row["science"])
                 for name, row in (("control", control), ("fused", candidate))},
    )
    write(summary, result)
    with archive.open("xb") as stream:
        stream.write(gzip.compress(output.read_bytes(), mtime=0))
    if not result["valid"]:
        raise ValueError(f"The combined replay changed original quadratic evidence: {same}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("control_path", "binary", "output", "summary", "archive"):
        parser.add_argument(name, type=Path)
    run(**vars(parser.parse_args()))
