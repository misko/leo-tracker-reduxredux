"""Replay a predetermined portion of one authenticated selected grid."""

import argparse
from collections import Counter
from contextlib import nullcontext
from hashlib import sha256
import json
from pathlib import Path
import struct
import sys
from time import perf_counter_ns, process_time_ns
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[2])]
OLD = Path("/dev/shm/leo-v3-history-risk-0169-01")
RUN = "algo08-v2-0a1d7d68673f132f547dc8a743b7b946"
GRID = OLD / "candidate/fast-scan-standard-v2" / RUN / "final-error-v7/position-grid.json"
GRID_PIN = "3834422a464ebaeff26cd0e85e350a99008942efa6f38936ddaf787039ae3a4e"
WITNESS = OLD / "risk-route.json"
WITNESS_PIN = "6922f4bb992a339fae2bc532c69618d41243dbc24e6e3ddf8952410805421b30"
INDICES = (0, 1, 2, 3, 8, 13, 21, 34, 45, 58, 71, 82, 91, 114, 130, 147, 161, 178)
ARMS = ("c0", "fitted_c")
ORDERS = ((False, True), (True, False), (True, False), (False, True))
FIELDS = ("features", "coefficient", "coefficient_prior_precision", "latent_coefficient",
          "residual", "conditional_residual_hz", "linear_raw_prediction_residual_hz", "elevation",
          "linear_elevation", "noise_precision", "negative_twice_elbo", "normalization_constant")


def clock():
    return process_time_ns(), perf_counter_ns()


def elapsed(tick):
    return dict(cpu_ns=process_time_ns()-tick[0], elapsed_ns=perf_counter_ns()-tick[1])


def check_fingerprints(value, pin):
    if json.loads(json.dumps(value)) != pin:
        raise ValueError("Reconstructed numerical input differs from selected witness")


def selected(scan, witness, arm, ordered_predictive, model, factory):
    import numpy as np
    from leo.analysis.localization_v3.discovery import zero_state
    from leo.analysis.localization_v3.event_position import make_event_problem
    from leo.analysis.localization_v3.predictive_linear import linear_geometry
    from leo.analysis.localization_v3.recovery_inventory import attach_event_predictive
    from named_survivor_fit import fingerprint

    roster = {track["key"]: i for i, track in enumerate(scan.tracks)}
    catalogue = {int(n): j for j, n in enumerate(scan.norads)}
    curves = witness["curves"]
    if {scan.tracks[i]["key"] for i in scan.curved} != curves.keys():
        raise ValueError("Prepared graph differs from the archived curved roster")
    rows, aliases, mask, powers = [], [], [], []
    for i in scan.curved:
        track = scan.tracks[i]
        key = track["key"]
        row = curves[key]
        rows.append(dict(component=key, candidate_index=catalogue[row["norad"]],
                         candidate_norad=row["norad"], active_curvature=True))
        aliases.append(row["alias"])
        # A group with no retained points never enters active powers or volume.
        powers.append(row.get("power", 1.))
        use = set(row["ids"])
        match = [oid in use for oid in track["observation_ids"]]
        if [oid for oid, keep in zip(track["observation_ids"], match, strict=True) if keep] != row["ids"]:
            raise ValueError("Selected curvilinear support order differs")
        mask.extend(match)
    node = dict(seed=dict(rows=rows, state=zero_state(scan)), aliases=aliases)
    families = witness["families"]
    labels = sorted({row["candidate_index"] for row in rows})
    ordered = [families[str(scan.norads[j])] for j in labels]
    means, reference = (np.asarray([row[k] for row in ordered])
                        for k in ("signed_prior_mean", "phase_reference"))
    powers, mask = np.asarray(powers), np.asarray(mask)
    p = make_event_problem(scan, node, mask, arm, reference, powers, means, model, [],
                           base_problem_factory=factory)
    entries = []
    if set(witness["predictive"]) != {key for key, _, _ in ordered_predictive}:
        raise ValueError("Archived predictive selection order cannot be bound")
    for key, norad, alias in ordered_predictive:
        row = witness["predictive"][key]
        i = roster[key]
        track = scan.tracks[i]
        if ((norad, alias) != (row["norad"], row["alias"])
                or list(track["observation_ids"]) != row["ids"]):
            raise ValueError("Selected predictive order differs")
        entries.append(dict(track_index=i, candidate_index=catalogue[norad], component=key,
                            norad=norad, alias=alias, points=len(row["ids"]), observation_ids=row["ids"],
                            cross_receiver_curved_support=row["cross_receiver"]))
    attach_event_predictive(p, entries, powers)

    def verify():
        if (int(p.keep.sum()), sum(entry["points"] for entry in entries)) != (1782, 454):
            raise ValueError("Unexpected authenticated selected DS30-0169 support")
        for i, sl, selected_row in zip(p.members, p.slices, p.rows, strict=True):
            tr, use = scan.tracks[i], p.keep[sl]
            row = curves[selected_row["component"]]
            if not np.any(use):
                continue
            for k, values in dict(clock_cfo_rf=(tr["times"][use], tr["values"][use], p.q[sl][use]),
                                  sigma=(p.point_noise[sl][use],), hardware=(p.hardware[sl][use],),
                                  smooth=(p.smooth[sl][use],)).items():
                check_fingerprints(fingerprint(*values), row[k])
        view, values, sigma, _groups, slices = linear_geometry(p, entries)
        for entry, sl in zip(entries, slices, strict=True):
            row = witness["predictive"][entry["component"]]
            tr = scan.tracks[entry["track_index"]]
            check_fingerprints(fingerprint(tr["times"], tr["values"], view.q[sl]), row["clock_cfo_rf"])
            check_fingerprints(fingerprint(values[sl], sigma[sl]), row["lifted_variance"])
        for k, archived in enumerate(ordered):
            span = slice(3*k, 3*k+3)
            if p.phase_sigma[k] != archived["phase_width"] or (labels[k] in p.supported) != archived["orbital_modes"]:
                raise ValueError("Selected family prior differs")
            check_fingerprints(fingerprint(p.sky["position_km"][k], p.sky["velocity_km_s"][k]),
                               archived["causal_sky"])
            check_fingerprints(fingerprint(p.mode_bank["position_km"][span], p.mode_bank["velocity_km_s"][span]),
                               archived["mode_geometry"])

    return p, verify


def strip(prepared, region, native_bound, original_grid, archived, target, original_curved):
    import numpy as np
    from leo.analysis.localization_v3 import history_position
    from leo.analysis.localization_v3.reassociation_context import objective
    from leo.contracts.digests import canonical_digest
    from leo.presentation import localization_v3 as presentation
    from named_survivor_fit import fingerprint
    from tools.pipeline_eval.variants import algo08_posterior_handoff as handoff, v5_core
    from grid_fixed_context import PredictiveByView, curved_factory
    from mixture_finish import digest

    start = clock()
    scan = v5_core.scan_context(prepared, region, digest(prepared["noise"]), native_bound, "genuine_previous")
    reconstruction = elapsed(start)
    witness = archived["lean_final_fit"]
    order = archived["lean_attempts"][0]["support"]["predictive_labels"]
    target["causal_grid_inputs"] = dict(noise=scan.fixed_window_noise_sha256, previous=scan.previous_tle_sha256,
                                        origin=scan.origin_utc_ns, endpoints=original_grid["endpoints"])
    for arm in ARMS:
        row = witness["arms"][arm]
        if (scan.fixed_window_noise_sha256 != row["original_noise"]
                or scan.previous_tle_sha256 != row["original_previous_tle"]
                or scan.origin_utc_ns != row["timing_origin_ns"]
                or original_grid["endpoints"][arm] != row["fit"]["position"]):
            raise ValueError("Fixed causal grid context changed")
    points = [original_grid["points"][i] for i in INDICES]
    if not original_grid["complete"] or original_grid["evaluated_points"] != 179 or any(p["failures"] for p in points):
        raise ValueError("Expected original complete retained standard grid")
    ordinary = handoff.predictive_factor

    def run(candidate, check=False):
        construction = clock()
        # The release already compiles its selected-row fast path. Carry the
        # live checked selector into the fixed-input version of the same source.
        selector = history_position.make_problem.__globals__.get("_select")
        if not callable(selector):
            raise ValueError("The released direct selected design must be active")
        factory = (curved_factory(original_curved, handoff.PYTHON_SHA256["make_problem"], select=selector)
                   if candidate else None)
        by_arm = {arm: selected(scan, witness["arms"][arm], arm, order, witness["model"], factory)
                  for arm in ARMS}
        pro = {arm: value[0] for arm, value in by_arm.items()}
        setup = elapsed(construction)
        if check:
            for _, validate in by_arm.values():
                validate()
        pending = []

        def coordinate(arm, point):
            p = pro[arm]
            result = {}
            calculate = p.calculate

            def remember(x):
                r = calculate(x)
                result.update(r)
                return r

            with patch.object(p, "calculate", remember):
                score = objective(p, {"families": []}, np.asarray(point))
            return score, result

        before = clock()
        workspace = PredictiveByView(ordinary, handoff.whiten) if candidate else None
        scope = patch.object(handoff, "predictive_factor", workspace) if candidate else nullcontext()
        with scope:
            for point in points:
                xy = (point["east_km"], point["north_km"])
                pending.append({arm: coordinate(arm, xy) for arm in ARMS})
        evaluations = elapsed(before)
        output = [{arm: dict(score=score, outputs=fingerprint(*(result[f] for f in FIELDS)))
                   for arm, (score, result) in row.items()} for row in pending]
        return dict(build=setup, evaluations=evaluations, work={} if workspace is None else dict(workspace.counts)), output

    def sample(_score, _endpoints, **kwargs):
        # The installed sampler wrappers activate native exports and cached phase
        # interpolation here. Each strip gets a fresh problem/view in the scope.
        _, expected = run(False, check=True)
        differences = {a: [expected[j][a]["score"] - p["scores"][a]
                           for j, p in enumerate(points)] for a in ARMS}
        target.update(scan=reconstruction, archived_checks=differences, indices=INDICES,
                      input_rows={a: dict(curves=len(witness["arms"][a]["curves"]), predictive=len(order))
                                  for a in ARMS})
        if not all(struct.pack("d", expected[j][a]["score"]) == struct.pack("d", point["scores"][a])
                   for j, point in enumerate(points) for a in ARMS):
            raise ValueError(f"Ordinary grid scores do not reproduce archived bytes: {differences}")
        target["times"] = []
        for pair in ORDERS:
            record = {}
            for candidate in pair:
                timing, output = run(candidate)
                if output != expected:
                    raise ValueError("Grid scores or numerical output bytes changed")
                record["candidate" if candidate else "stock"] = timing
            target["times"].append(record)
        target["nodes"] = [{a: row[a]["score"] for a in ARMS} for row in expected]
        target["product_sha256"] = canonical_digest(expected)
        return {}

    # The outer installed grid scopes retain the earlier callable and enter it
    # synchronously. Set the strip callback before installing those scopes.
    target["_sample"] = sample


def run(output):
    from aperture_trial import solve, write
    import empty_bootstrap as boot
    from exact_named_route import exact_ports, resident_path
    from history_risk_0169_input import bind

    start = clock()
    _, spec, _, publication, _ = boot.load_runtime()
    from leo.analysis.localization_v3 import history_position
    from leo.contracts.digests import canonical_digest
    from leo.presentation import localization_v3 as presentation
    from tools import algo08_position
    from tools.pipeline_eval.variants import v5_core

    if resident_path(output.parent) != Path("/dev/shm") or output.exists():
        raise ValueError("Use a fresh private tmpfs receipt path")
    bound, req = bind()
    native = json.loads(resident_path(Path(req["native_file"])).read_bytes())
    offer = json.loads(resident_path(Path(req["offer_file"])).read_bytes())
    grid = json.loads(boot.checked(resident_path(GRID), GRID_PIN))
    old = json.loads(boot.checked(resident_path(WITNESS), WITNESS_PIN))["solves"][0]
    if canonical_digest(grid["document"]) != grid["sha256"]:
        raise ValueError("Archived grid contract digest mismatch")
    result = dict(archive_sha256=req["local_archive"]["snapshots_sha256"], input_sha256=req["native_sha256"],
                  offer_sha256=req["offer_sha256"], grid_sha256=GRID_PIN, witness_sha256=WITNESS_PIN,
                  original_evidence_clocks=old["lean_attempts"][0]["standard_evidence_clocks"],
                  original_grid_elapsed_seconds=grid["document"]["elapsed_seconds"], binding=elapsed(start),
                  sources={p.name: sha256(p.read_bytes()).hexdigest() for p in (
                      Path(__file__), HERE/"grid-fixed-context-protocol.md", HERE/"grid_fixed_context.py")})
    archive = resident_path(Path(bound["archive"]))
    # load_runtime already installed the checked release startup in this process.
    spec["startup"] = "stock"
    audit = dict(rank=[], blocks=Counter(), graph={}, gates=Counter(), portable={}, verified_tle=Counter())
    stock_solve = algo08_position.solve
    original_curved = history_position.make_problem
    ready = clock()

    def sample(*args, **kwargs):
        return result["_sample"](*args, **kwargs)

    def infer(prepared, region, native_bound, _stages, *, selected_evidence):
        if prepared["status"] != "inputs_prepared":
            raise ValueError("Cannot prepare the pinned saved likelihood")
        result["preparation"] = elapsed(ready)
        strip(prepared, region, native_bound, grid["document"], old, result, original_curved)
        presentation.sample_position_grid(None, grid["document"]["endpoints"])
        return dict(status="grid_replay", reason=None, arms={a: dict(latlon=None) for a in ARMS})

    def observed(document, reader, assets, region):
        with exact_ports(bound, req, audit), patch.object(v5_core, "infer", infer):
            return stock_solve(document, reader, assets, region)

    try:
        with patch.object(presentation, "sample_position_grid", sample), patch.object(algo08_position, "solve", observed):
            trace = solve(publication, spec, native, archive, offer)
        result["ports"] = dict(phase_cache=dict(audit["grid"]), factor=trace["posterior_grid_handoff"],
                               archive_reads=dict(audit["verified_tle"]))
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        result.pop("_sample", None)
        write(output, result)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("receipt", type=Path)
    run(parser.parse_args().receipt)
