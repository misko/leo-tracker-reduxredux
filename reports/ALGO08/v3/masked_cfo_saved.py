"""Opt in to the frozen CFO sidecar at normal saved position preparation."""

from contextlib import ExitStack, contextmanager
from pathlib import Path
import sys
from time import perf_counter_ns, process_time_ns
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[2])]

import matched_donor_0049_trial as saved  # noqa: E402
import signed_cfo_time_readout as signed  # noqa: E402


CONFIG_PIN = "a7a252b2fd9a9fe7c617f4565b171c159846705803f4fb80ab755ba9ea94710a"
FEATURE_PIN = "65a9934437d2d495b269f7377dd4d82ebe4d4e1e6f6b8e3e89717f89a25e8843"


class GraphReadback(RuntimeError):
    """Stop the test at the original normal Graph return."""


def clock():
    return perf_counter_ns(), process_time_ns()


def elapsed(start):
    return {unit: end - beginning for unit, end, beginning in zip(("wall_ns", "cpu_ns"), clock(), start, strict=True)}


def overlay_rows(stage, native, original, features):
    updated = stage.apply_to_winners(native, original, features)
    if len(updated) != len(original):
        raise ValueError("CFO correction changed the native winner count")
    changed = 0
    for left, right in zip(original, updated, strict=True):
        if left is not right:
            delta = features.edits[left["observation_id"]]
            if right != dict(left, measured_cfo_hz=delta["updated_hz"]):
                raise ValueError("CFO overlay altered another signed observation field")
            changed += left["measured_cfo_hz"] != right["measured_cfo_hz"]
    return updated, changed


@contextmanager
def bind_graph(app, tracks, feature_stage, approved_config, native, audit, *, stock_ports=(), probe=False):
    original_prepare = app.prepare_tracks
    expected = signed.canonical(native)
    features = None
    audit.update(native_sha256=expected, attempts=[], feature_calls=0)

    def prepare(document, config):
        nonlocal features
        if config != approved_config or signed.canonical(document) != expected:
            raise ValueError("Normal Graph entry changed its prepared detector or approved configuration")
        if features is None:
            started = clock()
            with ExitStack() as stock:
                for module, name, operation in stock_ports:
                    stock.enter_context(patch.object(module, name, operation))
                features = feature_stage.derive(document, config)
            audit.update(feature_calls=1, derive=elapsed(started), eligible=len(features.edits),
                         masked_graph=features.masked_graph, eligible_gates=features.gates,
                         nomination_gates=features.eligibility, edit_sha256=signed.canonical(features.edits))
        extract = tracks.winning_observations
        attempt = {}

        def winning(packet):
            if packet is not document or attempt:
                raise ValueError("Ordinary Graph changed its caller or extracted twice")
            original, metadata = extract(packet)
            started = clock()
            adjusted, changed = overlay_rows(feature_stage, packet, original, features)
            attempt.update(overlay=elapsed(started), edited_winners=changed, winners=len(original),
                           original_rows_sha256=signed.canonical(original),
                           consumed_rows_sha256=signed.canonical(adjusted),
                           detector_sha256=metadata["detector_sha256"])
            return adjusted, metadata

        started = clock()
        with patch.object(tracks, "winning_observations", winning):
            prepared = original_prepare(document, config)
        attempt.update(
            ordinary_graph_with_extraction_and_overlay=elapsed(started), graph_status=prepared["status"],
            graph_points=prepared["graph_points"], tracks=len(prepared["tracks"]),
        )
        if (not attempt.get("overlay") or attempt["detector_sha256"] != feature_stage.identity(native)[-1]
                or signed.canonical(prepared["observations"]) != attempt["consumed_rows_sha256"]):
            raise ValueError("Ordinary Graph did not receive the bound observation overlay")
        audit["attempts"].append(attempt)
        if probe:
            raise GraphReadback()
        return prepared

    with patch.object(app, "prepare_tracks", prepare):
        try:
            yield
        finally:
            if signed.canonical(native) != expected:
                raise ValueError("The original detector was mutated")


def attach(native, audit, *, probe=False):
    from empty_bootstrap import RELEASE
    from leo.analysis import graph_tracklets, polynomial_tracklets
    from leo.analysis.localization_v3 import tracks
    from leo.application import localization_v3 as app
    from reports.ALGO08.v3 import held_cfo_features as feature_stage

    from tools.pipeline_eval.variants import v5_core

    if (saved.identifier(Path(feature_stage.__file__)) != FEATURE_PIN
            or Path(app.__file__).resolve() != RELEASE/"src/leo/application/localization_v3.py"
            or app.prepare_tracks is not tracks.prepare_tracks):
        raise ValueError("Require the frozen feature rule and installed Graph entry")
    config = polynomial_tracklets.TrackConfig(
        **saved.document(RELEASE/"assets/tracks.json", CONFIG_PIN)["config"])
    stock = [(module, name, getattr(module, name)) for module, name in (
        (tracks, "graph_tracks"), (tracks, "fit_lane"), (graph_tracklets, "_graph"),
        (polynomial_tracklets, "_best_piece"),
    )]
    if not probe:
        return bind_graph(app, tracks, feature_stage, config, native, audit, stock_ports=stock)

    @contextmanager
    def readback():
        def deny(*_args, **_kwargs):
            raise RuntimeError("Graph readback cannot enter orbit preparation or numerical inference")

        with (patch.object(app, "prepare_initial_sky", deny), patch.object(v5_core, "infer", deny),
              bind_graph(app, tracks, feature_stage, config, native, audit, stock_ports=stock, probe=True)):
            yield

    return readback()


def validate_exit(audit, receipt, native_pin, *, enabled):
    decision = receipt["decision"]
    if decision not in ("withheld", "complete"):
        raise ValueError("Expected an ordinary terminal fix or withholding decision")
    if enabled and not audit["attempts"] and decision != "withheld":
        raise ValueError("Complete publication skipped the enabled CFO observation stage")
    if enabled and audit["native_sha256"] != native_pin:
        raise ValueError("Published correction belongs to a different native detector packet")
    return dict(audit, enabled=enabled, decision=decision, native_sha256=native_pin,
                feature_source_sha256=FEATURE_PIN, approved_track_config_sha256=CONFIG_PIN)


def entry(root, pin, make_experiment, *, mode, fd=None):
    plan = saved.document(root/"plan.json", pin)
    if plan["enabled"] != (mode != "ordinary") or plan["probe"] != (mode == "graph-probe"):
        raise ValueError("Saved mode differs from the sealed plan")
    started = clock()
    experiment = make_experiment(probe=plan["probe"])
    audit = {}
    options = dict(
        lease_fd=fd, enrollment=(plan["case"], Path(plan["stage"]), plan["admission_sha256"], plan["references"]),
        admission_path=root/"admission.json", original_control=True,
        observation_scope=(lambda native: attach(native, audit, probe=plan["probe"])) if plan["enabled"] else None,
    )
    try:
        saved.worker(root, pin, experiment, **options)
    except GraphReadback:
        if not plan["probe"] or not audit["attempts"]:
            raise
        matches, = (root/"substituted/fast-scan-automatic-work").glob("*/detections.json")
        saved.document(matches, plan["original_native_sha256"])
        if list((root/"substituted").rglob("terminal.json")):
            raise ValueError("The no-fit readback progressed to a terminal")
        document = dict(audit, fit_calls=0, decision="graph_probe", enabled=True)
    else:
        receipt = saved.document(root/"receipt.json")["receipt"]
        document = validate_exit(audit, receipt, plan["original_native_sha256"], enabled=plan["enabled"])
    print(saved.write(root/"masked-cfo-observation-witness.json", dict(
        document, clock_through_verified_output=elapsed(started), original_native_sha256=plan["original_native_sha256"],
        stage_plan_sha256=pin, waveform_reads=0, forecast_cache_reads=0,
    )))
