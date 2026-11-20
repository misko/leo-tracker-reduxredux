"""Count live project Python lines and calls on bounded receiver stages."""

import json
import sys
from collections import Counter, defaultdict
from dataclasses import fields, is_dataclass, replace
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
from leo.analysis.localization_v3 import tracks
from leo.operations.localization_v3_job import read_bound

from leo.analysis.polynomial_tracklets import TrackConfig
from leo.analysis.research import phase_linear_geometry as reference
from tools.pipeline_eval.__main__ import ROOT, encoded
from tools.pipeline_eval.qualification import cold_input
from tools.pipeline_eval.qualification.full_v5_check import BULK, _load_case
from tools.pipeline_eval.variants import (
    joint_pass_id,
    orbit_projector,
    point_votes,
    rate_triplets,
    v5_lean,
    v5_stream_prepare,
)

CASE = "DS26-0036"
SPAN_S = 32
ROOTS = (
    (str(v5_lean.SOURCE) + "/", "frozen/"),
    (str(ROOT / "tools/pipeline_eval") + "/", "pipeline_eval/"),
)


def trace(operation):
    lines, calls, files = defaultdict(set), Counter(), {}

    def line(frame, event, _):
        if event == "line":
            lines[files[frame.f_code.co_filename]].add(frame.f_lineno)
        return line

    def call(frame, event, _):
        if event == "call":
            code = frame.f_code
            name = code.co_filename
            if name not in files:
                files[name] = next(
                    (label + name[len(root) :] for root, label in ROOTS if name.startswith(root)),
                    None,
                )
            if files[name] is not None:
                if not code.co_name.startswith("<"):
                    calls[files[name], code.co_firstlineno, code.co_name] += 1
                return line
        return None

    sys.settrace(call)
    try:
        result = operation()
    finally:
        sys.settrace(None)
    return result, dict(
        named_functions=len(calls),
        named_calls=sum(calls.values()),
        executed_lines=sum(map(len, lines.values())),
        files_with_executed_lines=len(lines),
        lines_by_file={name: sorted(hit) for name, hit in sorted(lines.items())},
        functions=[
            dict(file=name, line=start, function=method, calls=count)
            for (name, start, method), count in sorted(calls.items())
        ],
    )


def archive(locator):
    raw = (BULK / locator["path"]).read_bytes()
    assert sha256(raw).hexdigest() == locator["sha256"]
    return json.loads(raw)


def subset(document):
    source, provenance = document["source"], document["provenance"]
    rate, first = source["sample_rate_hz"], document["clock_anchor"]["sample_counter"]
    window = rate * source["probe_ms"] // 1000
    cutoff = first + SPAN_S * rate
    probes = [p for p in source["probes"] if p["valid_start_counter"] + window <= cutoff]
    excluded = [p for p in provenance["excluded_windows"] if p["sample_end"] <= cutoff]
    valid = {p["visit_index"]: p["valid_start_counter"] + window for p in probes}
    visited = valid | {p["visit"]: p["sample_end"] for p in excluded}
    assert set(visited) == set(range(len(visited)))
    return dict(
        document,
        source=dict(source, probes=probes),
        delivery_clocks=document["delivery_clocks"][: len(visited)],
        last_sample_counter=visited[len(visited) - 1],
        provenance=dict(
            provenance,
            window_count=len(visited),
            processed_windows=len(valid),
            invalid_capture=len(excluded),
            excluded_windows=excluded,
        ),
    )


def receiver_stages(work):
    case = _load_case(CASE)
    document = subset(archive(case["native"]))
    config = TrackConfig(**archive(case["track_config"])["config"])
    payload = encoded(document)
    path = work / "native-prefix.json"
    path.write_bytes(payload)
    bound = dict(path=str(path), sha256="sha256:" + sha256(payload).hexdigest())
    cold = cold_input.load(CASE)
    cold = replace(
        cold,
        probes=[p for p in cold.probes if p["visit_index"] < len(document["delivery_clocks"])],
        duration_s=(document["last_sample_counter"] - cold.first_counter) / cold.sample_rate_hz,
    )
    assert len(cold.probes) == len(document["source"]["probes"])

    baseline, stock_trace = trace(lambda: tracks.prepare_tracks(read_bound(bound), config))
    streamed, stream_trace = trace(
        lambda: v5_stream_prepare.prepare_owned(
            tracks.prepare_tracks, v5_stream_prepare.read_native(bound), config
        )
    )
    assert baseline["observations"] == streamed["observations"]
    assert baseline["curved_indices"] == streamed["curved_indices"]
    for a, b in zip(baseline["tracks"], streamed["tracks"], strict=True):
        assert a["observation_ids"] == b["observation_ids"]
        np.testing.assert_array_equal(a["values"], b["values"])
        np.testing.assert_array_equal(a["times"], b["times"])
    stock_shape = dict(
        winners=len(baseline["observations"]),
        tracks=len(baseline["tracks"]),
        graph_points=baseline["graph_points"],
    )
    (pairs, pair_metrics), pair_trace = trace(lambda: point_votes.pair_votes(cold))
    rate_rows, rate_trace = trace(lambda: rate_triplets.tracklets(cold))
    joint_rows, joint_trace = trace(lambda: joint_pass_id.native_tracks(cold))
    return dict(
        input=dict(
            case=CASE,
            native_sha256=case["native"]["sha256"],
            track_config_sha256=case["track_config"]["sha256"],
            prefix_sha256=bound["sha256"],
            prefix_bytes=len(payload),
            targeted_seconds=SPAN_S,
            sample_span_s=cold.duration_s,
            valid_probes=len(cold.probes),
            scheduled_visits=len(document["delivery_clocks"]),
        ),
        stock_graph=dict(output=stock_shape, **stock_trace),
        stream_graph=dict(output=stock_shape, **stream_trace),
        from_scratch_point_pairs=dict(output=dict(pairs=len(pairs), **pair_metrics), **pair_trace),
        from_scratch_rate_triplets=dict(output=dict(tracklets=len(rate_rows)), **rate_trace),
        from_scratch_joint_pass=dict(output=dict(tracklets=len(joint_rows)), **joint_trace),
    )


def array_bytes(value):
    if isinstance(value, np.ndarray):
        return value.nbytes
    if is_dataclass(value):
        return sum(array_bytes(getattr(value, field.name)) for field in fields(value))
    return 0


def projection_stages(work):
    rng = np.random.default_rng(22617)
    satellites, knots_count, points = 32, 17, 160
    knots = np.arange(knots_count, dtype=float) * 2.0
    starts = rng.normal(size=(satellites, 1, 3))
    starts *= 7000 / np.linalg.norm(starts, axis=-1, keepdims=True)
    velocity = rng.normal(size=(satellites, knots_count, 3))
    bank = dict(
        time_s=knots, position_km=starts + knots[None, :, None] * velocity, velocity_km_s=velocity
    )
    times, phases = np.linspace(2.0, 29.0, points), np.linspace(-0.8, 0.9, satellites)
    sites = ((0, 0), (45, 80), (-65, 179))
    binary = work / "projector.so"
    orbit_projector.compile_kernel(binary)
    engine = orbit_projector.Projector(binary)

    def projected(prepare, evaluate):
        geometry = prepare(bank, times, phases)
        return geometry, [evaluate(geometry, lat, lon) for lat, lon in sites]

    (stock, a), stock_trace = trace(
        lambda: projected(reference.prepare_phase_geometry, reference.phase_linear_frequency)
    )
    (compact, b), compact_trace = trace(lambda: projected(orbit_projector.prepare, engine.evaluate))
    for aa, bb in zip(a, b, strict=True):
        for x, y, tolerance in zip(aa, bb, (1e-5, 1e-8, 1e-5), strict=True):
            np.testing.assert_allclose(x, y, atol=tolerance, rtol=0)
    return dict(
        shape=dict(
            satellites=satellites,
            knots=knots_count,
            observation_times=points,
            site_evaluations=len(sites),
        ),
        stock_numpy=dict(retained_geometry_bytes=array_bytes(stock), **stock_trace),
        compact_c=dict(
            retained_geometry_bytes=compact.bytes,
            native_calls=engine.calls,
            kernel_source_bytes=orbit_projector.KERNEL.stat().st_size,
            compiled_library_bytes=binary.stat().st_size,
            **compact_trace,
        ),
    )


def main():
    if not Path(tracks.__file__).is_relative_to(v5_lean.SOURCE):
        raise ValueError("Run with the pinned v5 source first on PYTHONPATH")
    with TemporaryDirectory(prefix="leo-complexity-trace-") as directory:
        work = Path(directory)
        receiver = receiver_stages(work)
        projection = projection_stages(work)
    print(json.dumps(dict(receiver=receiver, projection=projection), sort_keys=True))


if __name__ == "__main__":
    main()
