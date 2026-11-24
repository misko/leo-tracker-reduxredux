"""Cross two sealed South receiver inputs at the installed Graph boundary."""

import argparse
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import sys
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
OLD = Path("/dev/shm/leo-v3-south-cfo-route-02/containing")
NEW = Path("/dev/shm/leo-combined-south-run.yF2Ole7s/pair/containing")
PINS = {
    "old": (OLD, "b0926955297126a160679dc4d1be549726739bf1fc399a53ce97a8e0e932b2d8",
            "02c118d9ab3750033a9df3b7db379499ad76c40fc2cae24f2a5ae2cd9a74883f"),
    "new": (NEW, "d57cc4507e58a9ce80b776959aa0e589471bf69ad7f9118d34a0d5df1a9d9bb7",
            "696a34f4622cbc256facfd908ac9295fa3ebcd0a9fdba98575f3be0d05bc0793"),
}
CFO = "fractional_tracking_cfo_hz"
MARKS = ("fractional_control_score", "fractional_exact_score", "fractional_margin")


def switched(old, new, *, cfo, marks):
    """Use the earlier packet layout with only the chosen numeric fields substituted."""
    both = deepcopy(old)
    for target, original, altered in zip(both["source"]["probes"], old["source"]["probes"], new["source"]["probes"], strict=True):
        if dict(original, candidates=[]) != dict(altered, candidates=[]):
            raise ValueError("Native opportunities do not match")
        for into, left, right in zip(target["candidates"], original["candidates"], altered["candidates"], strict=True):
            if dict(left, **{name: right[name] for name in (CFO, *MARKS)}) != right:
                raise ValueError("Native receiver differences exceed the crossed fields")
            if cfo:
                into[CFO] = right[CFO]
            if marks:
                into.update({name: right[name] for name in MARKS})
    return both


def piece(item):
    return None if item is None else [item["degree"], item["indices"].tolist()]


def graph_run(rows, config, library):
    import numpy as np

    from leo.analysis import graph_tracklets as graph, polynomial_tracklets as polynomial, tracklet_fitting as finish
    from leo.analysis.localization_v3 import tracks
    from leo.application.localization_v3_engine import _json_value
    from tools.pipeline_eval.variants.experimental.graph_path import NativePath, native_paths
    from exact_graph_execution import graph_execution

    lanes = iter(sorted({(r["actual_rf_hz"], r["receiver"], r["channel"]) for r in rows}))
    trace, audit = {}, {}
    with graph_execution(enabled=True, audit=audit), native_paths(library, required=True, verify=True) as metrics:
        stock_fit, build, best_path = tracks.fit_lane, graph._graph, NativePath.solve
        path_models, best_piece, repair = graph._path_models, polynomial._best_piece, finish._repair_structured
        arbitrate = graph.finish_lane

        def lane(t, y, cfg):
            rf, rx, channel = next(lanes)
            events, numeric, candidates = [], [], []
            trace[f"{rx}:{channel}:{rf:g}"] = dict(events=events, numeric=numeric, candidates=candidates,
                                                  lane=[rx, channel, rf])

            def edges(*args):
                result = build(*args)
                digest = sha256(b"".join(a.tobytes() for a in result[:3])).hexdigest()
                events.append(["edges", len(result[0]), digest])
                return result

            def path(instance, packed, y, available, enabled, cfg):
                result = best_path(instance, packed, y, available, enabled, cfg)
                events.append(["path", result[0].tolist(), result[2].tolist()])
                numeric.append(dict(event=len(events)-1, path_score=result[3]))
                return result

            def models(*args, **kwargs):
                events.append(["path_models_input", args[2].tolist()])
                result = path_models(*args, **kwargs)
                events.append(["path_models_output", [piece(item) for item in result]])
                return result

            def choose(*args):
                result = best_piece(*args)
                events.append(["best_piece", args[2].tolist(), piece(result)])
                return result

            def compress(*args):
                events.append(["grouping_input", [piece(item) for item in args[0]]])
                result = repair(*args)
                events.append(["grouping_output", [[piece(item) for item in group] for group in result]])
                return result

            def final(t, y, order, n, models, cfg, **kwargs):
                gate = cfg.association_sigma * cfg.noise_sigma_hz
                distance = np.full(len(y), np.inf)
                for index, model in enumerate(models):
                    ix = np.unique(model["indices"])
                    raw = y[ix] - finish._predict(model, t[ix])
                    circular = np.abs(finish._wrap(raw, cfg.alias_spacing_hz))
                    improved = (circular < gate) & (circular < distance[ix])
                    candidates.append(dict(model=index, gate_hz=gate, support=ix.tolist(),
                        degree=model["degree"], coefficients=model["coefficients_hz"].tolist(),
                        reference_time_s=model["reference_time_s"], time_scale_s=model["time_scale_s"], rows=[
                        dict(input_index=int(order[i]), raw_residual_hz=float(r), circular_residual_hz=float(c),
                             prior=None if np.isinf(distance[i]) else float(distance[i]), kept=bool(ok))
                        for i, r, c, ok in zip(ix, raw, circular, improved, strict=True)]))
                    distance[ix[improved]] = circular[improved]
                return arbitrate(t, y, order, n, models, cfg, **kwargs)

            with (patch.object(graph, "_graph", edges), patch.object(NativePath, "solve", path),
                  patch.object(graph, "_path_models", models), patch.object(polynomial, "_best_piece", choose),
                  patch.object(finish, "_repair_structured", compress), patch.object(graph, "finish_lane", final)):
                result = stock_fit(t, y, cfg)
            events.append(["output", [item["indices"].tolist() for item in result["tracks"]]])
            return result

        with patch.object(tracks, "fit_lane", lane):
            all_tracks, points = tracks.graph_tracks(rows, config)
    support = {track["key"]: track["observation_ids"] for track in all_tracks}

    def original_values(value):
        if isinstance(value, np.ndarray):
            return [value.dtype.str, value.shape, value.tobytes().hex()]
        return _json_value(value)

    payload = json.dumps(all_tracks, default=original_values, allow_nan=False, sort_keys=True, separators=(",", ":"))
    return dict(points=points, tracks=len(all_tracks), support=support, trace=trace, execution=audit, paths=dict(metrics),
                complete_graph_sha256=sha256(payload.encode()).hexdigest())


def first_forks(old, new):
    result = {}
    for lane, a in old["trace"].items():
        b = new["trace"][lane]
        for index, (x, y) in enumerate(zip(a["events"], b["events"])):
            if x != y:
                result[lane] = dict(index=index, old=x, new=y, preceding=a["events"][max(0,index-2):index],
                                    old_path_scores=a["numeric"], new_path_scores=b["numeric"])
                break
        else:
            if len(a["events"]) != len(b["events"]):
                raise ValueError("A discrete lane trace ended without recording its final supports")
    return result


def run(output):
    import empty_bootstrap as staged
    from aperture_trial import write
    from dense_geographic_trial import host
    from short_graph_guard import RELEASE_PINS, TRACK_CONFIG

    machine = host()
    _, spec, _, publication, _ = staged.load_runtime()
    from leo.analysis.localization_v3.tracks import winning_observations
    from leo.analysis.polynomial_tracklets import TrackConfig
    from leo.contracts.digests import canonical_digest

    for name, digest in RELEASE_PINS.items():
        staged.checked(staged.RELEASE / "src" / name, digest)
    actual = staged.RELEASE / "assets/tracks.json"
    config_doc = json.loads(staged.checked(actual, TRACK_CONFIG))["config"]
    library = Path(spec["graph_path"]["library"])
    publication._checked_graph_path(spec)
    inputs, owners = {}, {}
    for mode, (root, native_pin, research_pin) in PINS.items():
        (path,) = (root / "fast-scan-automatic-work").glob("*/detections.json")
        inputs[mode] = json.loads(staged.checked(path, native_pin))
        owners[mode] = json.loads(staged.checked(root / "joint-research-receipt.json", research_pin))["selected_rows"]
    samples, rows = {}, {}
    for mode, cfo, marks in (("old", False, False), ("marks_only", False, True), ("cfo_only", True, False), ("new", True, True)):
        native = switched(inputs["old"], inputs["new"], cfo=cfo, marks=marks)
        rows[mode], _ = winning_observations(native)
        samples[mode] = graph_run(rows[mode], TrackConfig(**config_doc), library)
    old, new = (samples[arm] for arm in ("old", "new"))
    if (old["points"], new["points"], old["tracks"], new["tracks"]) != (442, 438, 30, 30):
        raise ValueError("Graph-only replay must reproduce both archived Graphs first")
    forks = first_forks(old, new)
    assigned = {mode: set().union(*map(set, samples[mode]["support"].values())) for mode in samples}
    losing = {index: dict(row, in_old=index in assigned["old"], in_new=index in assigned["new"])
              for row in rows["new"] if (index := row["observation_id"]) in assigned["old"] ^ assigned["new"]}
    time_pairs = {mode: {row["observation_id"]: row["measured_cfo_hz"] for row in observations}
                  for mode, observations in rows.items()}
    owner_losses = {}
    decisive_residuals = {}
    competing_models = {}
    for label in forks:
        lane = old["trace"][label]["lane"]
        records = [row for row in rows["new"] if [row["receiver"], row["channel"], row["actual_rf_hz"]] == lane]
        decisive_residuals[label] = {mode: [dict(item, observation_id=records[item["input_index"]]["observation_id"],
                                                  gate_hz=model["gate_hz"], model=model["model"])
                                           for model in value["trace"][label]["candidates"] for item in model["rows"]
                                           if records[item["input_index"]]["observation_id"] in losing]
                                     for mode, value in samples.items()}
        competing_models[label] = {mode: [{key: value for key,value in item.items() if key != "rows"}
                                           for item in record["trace"][label]["candidates"]]
                                   for mode, record in samples.items()}
    for arm in ("c0", "fitted_c"):
        before = {oid: [norad, role] for oid, norad, role in owners["old"][arm]}
        after = {oid: [norad, role] for oid, norad, role in owners["new"][arm]}
        owner_losses[arm] = [dict(losing[oid], historical_owner=before[oid],
                                  cfo_delta_hz=time_pairs["new"][oid]-time_pairs["old"][oid])
                             for oid in sorted(before.keys() - after.keys())]
    write(output, dict(machine=machine, graph_path=spec["graph_path"], track_config=config_doc,
                       native_pins={mode: [str(root), native, receipt] for mode,(root,native,receipt) in PINS.items()},
                       source_sha256={name: sha256((HERE / name).read_bytes()).hexdigest()
                                      for name in ("south_graph_sensitivity.py", "south-graph-sensitivity-protocol.md")},
                       cells={mode: dict(points=value["points"], tracks=value["tracks"], paths=value["paths"],
                                         assigned_digest=canonical_digest(sorted(assigned[mode])),
                                         support_digest=canonical_digest(value["support"]), winning_rows=len(rows[mode]))
                              for mode, value in samples.items()}, first_forks=forks,
                       cross_forks={mode: sorted(first_forks(old, samples[mode])) for mode in ("marks_only", "cfo_only")},
                       track_membership_changes=losing, owner_losses=owner_losses, decisive_residuals=decisive_residuals,
                       competing_models=competing_models,
                       waveform_reads=0, solver_calls=0))


if __name__ == "__main__":
    sys.path.insert(0, str(HERE))
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("output", type=Path)
    run(cli.parse_args().output)
