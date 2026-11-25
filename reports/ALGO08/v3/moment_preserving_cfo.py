"""Keep the ordinary Graph polynomial moments of the sealed short CFO edits."""

from collections import Counter
from hashlib import sha256
from importlib import import_module
import json
from math import fsum
import os
from pathlib import Path
import sys
from unittest.mock import patch

import numpy as np
from numpy.polynomial.legendre import legder, legval, legvander

import held_installed_carrier_transfer as legacy
import masked_cfo_0212_installed_agreement as case_0212
import masked_cfo_0218_installed_agreement as metric


residual = metric.residual
HERE = metric.HERE
CELLS = {
    case_0212.CASE: (case_0212.CELLS, "masked-cfo-0212-fixed-residuals", case_0212.FIXED),
    metric.CASE: (metric.CELLS, "masked-cfo-0218-prospective-fixed-residuals", metric.SEALED),
}
CASES = (*legacy.CASES, *CELLS)
PINS = {
    **legacy.PINS,
    "held_installed_carrier_transfer.py": "bc2d3ed01193a7fe0aee173498f3652a50437b0782a25127507dae265f0896fd",
    "masked_cfo_0212_installed_agreement.py": "f05a5729fee4f6388ce2d3bf13f250d68604109ec9c3dc2bb901d6523e5bb28f",
}
READBACKS = {
    "held-cfo-fixed-residual": "e7705f64c74db7eb8bd88df6ade99c01ca2d0053fefc82e1d3790fa1d71a9816",
    "held-installed-carrier-transfer": "1218e84dabc75f5323f9f12bc69971de859bd7807d92bf2aba03535c196e436b",
    "masked-cfo-0218-installed-agreement": "f07190e63c92d9b499da83a6522b4d3835a4f31c7d4bea2b12abbb18ce8d6997",
    "masked-cfo-0212-installed-agreement": "b4e731ced2c795f03c2c2bba5caf7498748696bc0df32fa6eed65f6bf51232ea",
}
PROTOCOL = "843795f7ff776ce6e53f65a978f6b4cdb9782532b94948242aa5b810429a485f"
EPS = np.finfo(float).eps


def basis(pieces):
    """Ordinary Legendre model evaluated only on rows allowed to change."""
    widths = [part["degree"] + 1 for part, _ in pieces]
    design = np.zeros((sum(len(t) for _, t in pieces), sum(widths)))
    constraints = np.zeros((2, sum(widths)))
    if len(pieces) == 2:
        joins = {part.get("join_time_s") for part, _ in pieces}
        if len(joins) != 1 or None in joins:
            raise ValueError("The released two-piece model must have one authenticated C1 join")
        knot = joins.pop()
    elif len(pieces) != 1:
        raise ValueError("Expected the released one- or two-piece polynomial model")
    row = col = 0
    for j, ((part, track_times), width) in enumerate(zip(pieces, widths, strict=True)):
        ref, scale = part["reference_time_s"], part["time_scale_s"]
        if not np.isfinite([ref, scale]).all() or scale <= 0 or not 1 <= width <= 5:
            raise ValueError("The released polynomial basis is invalid")
        block = slice(col, col + width)
        times = (np.asarray(track_times) - ref) / scale
        design[row:row + len(times), block] = legvander(times, width - 1).reshape((-1, width))
        if len(pieces) == 2:
            x = (knot - ref) / scale
            sign = 1 if j == 0 else -1
            constraints[0, block] = sign * legvander(x, width - 1)[0]
            constraints[1, block] = [sign * legval(x, legder(c)) / scale for c in np.eye(width)]
        row += len(times)
        col += width
    if len(pieces) == 2:
        _, singular, right = np.linalg.svd(constraints, full_matrices=True)
        if singular[-1] <= EPS * max(constraints.shape) * singular[0]:
            raise ValueError("The released join lost its two independent continuity constraints")
        design = design @ right[2:].T
    return design


def project(design, original, previous, cap):
    """Return stored CFO and a certificate for its track-level edit."""
    delta = previous - original
    left, singular, _ = np.linalg.svd(design, full_matrices=False)
    rank = int(np.sum(singular > EPS * max(design.shape) * singular[0]))
    q = left[:, :rank]
    before = float(np.max(np.abs(q.T @ delta), initial=0.))
    rounding = 2 * np.spacing(np.abs(original))
    tolerance = float(rounding.sum() + 64 * EPS * max(design.shape) * max(1., np.linalg.norm(delta)))
    if rank < design.shape[1]:
        return original, dict(status="insufficient_rank", rank=rank, before=before, after=0., tolerance=tolerance)
    if rank == len(delta):
        return original, dict(status="fully_in_span", rank=rank, before=before, after=0., tolerance=tolerance)
    remainder = delta - q @ (q.T @ delta)
    largest = float(np.max(np.abs(remainder)))
    scale = min(1., (cap - float(rounding.max())) / largest) if largest else 1.
    stored = original + scale * remainder
    actual = stored - original
    after = float(np.max(np.abs(q.T @ actual)))
    if np.max(np.abs(actual)) > cap or after > tolerance:
        raise ValueError("The stored edit violates the half-bin bound or the fixed-track moments")
    return stored, dict(status="projected", rank=rank, scale=scale, before=before, after=after, tolerance=tolerance)


def project_tracks(packet, edits):
    cap = residual.BIN_HZ / 2
    winners = {row["observation_id"]: row for row in packet["observations"]}
    if not edits.keys() <= winners.keys() or any(
            edit["original_hz"] != winners[oid]["measured_cfo_hz"] or not residual.finite_hz(edit["updated_hz"])
            or abs(edit["updated_hz"] - edit["original_hz"]) > cap + 2*np.spacing(abs(edit["original_hz"]))
            for oid, edit in edits.items()):
        raise ValueError("Original edits must match the released signed winners and half-bin bound")
    revised = {oid: edit["original_hz"] for oid, edit in edits.items()}
    membership, proof = {}, {}
    degrees = Counter()
    matched = 0
    for track in packet["tracks"]:
        indexed = dict(zip(sorted(track["indices"]), track["observation_ids"], strict=True))
        pieces, edited_ids, ledger = [], [], []
        for part in track["pieces"]:
            ids = [indexed[ix] for ix in sorted(part["indices"])]
            if any(oid in membership for oid in ids):
                raise ValueError("The released Graph membership is not exclusive")
            membership.update({oid: track["key"] for oid in ids})
            edited = [oid for oid in ids if oid in edits]
            edited_ids.extend(edited)
            pieces.append((part, [winners[oid]["time_s"] for oid in edited]))
            ledger.append([ids, [part.get(key) for key in ("degree", "reference_time_s", "time_scale_s", "join_time_s")]])
        if edited_ids:
            design = basis(pieces)
            original = np.array([edits[oid]["original_hz"] for oid in edited_ids])
            previous = np.array([edits[oid]["updated_hz"] for oid in edited_ids])
            stored, certificate = project(design, original, previous, cap)
            revised.update(zip(edited_ids, map(float, stored), strict=True))
            proof[track["key"]] = dict(**certificate, observations=len(edited_ids), model_columns=design.shape[1],
                                       membership_sha256=residual.digest(ledger))
            degrees.update(part["degree"] for part, _ in pieces)
            matched += len(edited_ids)
    if len(membership) != packet["graph_points"]:
        raise ValueError("The released polynomial pieces do not cover the original Graph roster")
    old = [edit["updated_hz"] - edit["original_hz"] for edit in edits.values()]
    new = [revised[oid] - edit["original_hz"] for oid, edit in edits.items()]
    status = Counter(item["status"] for item in proof.values())
    return revised, dict(
        old_energy_hz2=fsum(d*d for d in old), projected_energy_hz2=fsum(d*d for d in new),
        original_edits=len(edits), surviving_edits=sum(d != 0 for d in new), unassigned_edits=len(edits)-matched,
        track_status=dict(status), model_piece_degrees=dict(degrees),
        capped_tracks=sum(item.get("scale", 1.) < 1. for item in proof.values()),
        max_before_moment_hz=max((item["before"] for item in proof.values()), default=0.),
        max_after_moment_hz=max((item["after"] for item in proof.values()), default=0.),
        max_moment_bound_hz=max((item["tolerance"] for item in proof.values()), default=0.),
        max_after_to_bound=max((item["after"]/item["tolerance"] for item in proof.values()), default=0.),
        max_abs_projected_cfo_change_hz=max(map(abs, new), default=0.),
        moments_valid=True, exact_mask_sha256=residual.digest(sorted(edits)), membership_sha256=residual.digest(membership),
        track_moment_ledger_sha256=residual.digest(proof), projected_cfo_sha256=residual.digest(revised))


def readback(name):
    return residual.read(HERE / "measurements" / (name + ".json"), READBACKS[name])


def candidate(case):
    if case in legacy.CASES:
        native, edits, _, bindings = legacy.capsules(case)
        published = readback("held-cfo-fixed-residual")["cases"][case]
        graph = (published["rebuilt_graph_tracks"][0], published["rebuilt_graph_assigned"][0])
        return native, edits, graph, bindings, None, None
    cell, name, pin = CELLS[case]
    fixed = residual.read(HERE / "measurements" / (name + ".json"), pin)
    pins = residual.read(cell / "verification-pins.json", fixed["closure_sha256"])
    if fixed["case"] != case or pins != fixed["plan_pins"]:
        raise ValueError("The case and sealed ordinary/corrected cells disagree")
    with patch.object(residual, "CASE", case):
        ordinary, corrected = (residual.read_cell(cell / mode, mode, pins[mode]) for mode in residual.MODES)
    native = ordinary["native"]
    if corrected["native"] != native or any(operand["plan"]["original"] != fixed["original_field"]
                                           for operand in (ordinary, corrected)):
        raise ValueError("The sealed cells must share their unedited signed input and offer")
    replay = residual.rederive(native, residual.original_winners(native), corrected["scope"])
    if replay is None or replay["digest"] != fixed["edit_readback"]["digest"] or replay["changed"] != len(replay["edits"]):
        raise ValueError("Cannot reproduce the sealed masked CFO edits")
    witness = residual.read(cell / "ordinary/substituted/exact-named-raw-witness.json", ordinary["run"]["witness"])
    graph = witness["ports"]["graph"]["graph"]
    bindings = dict(ordinary_native_sha256=fixed["original_native_sha256"], edits_sha256=replay["digest"],
                    ordinary_witness_sha256=ordinary["run"]["witness"], closure_sha256=fixed["closure_sha256"])
    return native, replay["edits"], (graph["tracks"], graph["assigned"]), bindings, fixed, replay["readback"]


def score(case, prepared, signed, held):
    native, edits, revised, observed, fixed, previous_proof = prepared
    if case in legacy.CASES:
        installed, _ = legacy.installed(case, native, signed)
        previous = readback("held-installed-carrier-transfer")["cases"][case]
        expected, pin = previous["all_edits"], previous["signed_pairs_sha256"]
    else:
        with patch.object(metric, "PAIR", legacy.FIELD / case):
            installed, _, _ = metric.load_pair(fixed, native, signed)
        previous = readback(f"masked-cfo-{case[-4:]}-installed-agreement")
        expected, pin = previous["result"]["all_edits"], previous["coverage_records_sha256"]
    reference = signed.opportunities(installed)
    signed.bind_pair(installed, native, reference, observed)
    prior_rows = metric.matched_rows(edits, observed, reference, held.aligned_errors)
    if residual.digest(prior_rows) != pin:
        raise ValueError("Installed coverage and prior paired observations differ from the frozen readout")
    projected_rows = [None if row is None else (
        row[0], revised[oid] - reference[oid]["factor"][residual.HERTZ], row[2]) for oid, row in prior_rows.items()]
    args = held.evaluate, held.odd.WINDOWS, signed.ALIAS
    prior = metric.summarize(list(prior_rows.values()), *args)
    new = metric.summarize(projected_rows, *args)
    if prior != expected or any(prior[key] != new[key] for key in ("eligible", "scored", "installed_empty", "original")):
        raise ValueError("Paired metrics or their frozen denominators changed")
    previous_proof.update(previous_half_blend=prior, moment_preserving=new, prior_signed_pairs_sha256=pin)


def main():
    if os.sched_getaffinity(0) != {3} or any(os.environ.get(name) != "1" for name in (
            "OMP_NUM_THREADS", "OMP_THREAD_LIMIT", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
            "BLIS_NUM_THREADS", "NUMEXPR_NUM_THREADS")):
        raise ValueError("The bounded audit requires one numerical thread on CPU 3")

    def protect_inputs(event, args):
        if event == "open" and isinstance(args[0], (str, bytes)):
            path = Path(os.fsdecode(args[0])).resolve()
            if (path.suffix in (".tle", ".iq", ".sigmf-data") or "fast-scan-recordings" in path.parts
                    or path.is_relative_to("/mnt/qnap01") or "DS30-0280" in path.parts
                    or path.name in ("evaluation-reference.json", "reference-audit.json", "score.json")
                    or path.is_relative_to(legacy.FIELD) and not any(path.is_relative_to(legacy.FIELD / c) for c in CASES)):
                raise RuntimeError("Only development-case signed numerical operands are eligible")

    sys.addaudithook(protect_inputs)
    for name, pin in PINS.items():
        residual.checked(HERE / name, pin)
    residual.checked(HERE / "moment-preserving-cfo-protocol.md", PROTOCOL)
    tracklet_source = "8e3917e1bb94bf59e37d97a7a3782254612e459d36075f67acfdfe15b3a19414"
    for name, pin in {**residual.RELEASE_PINS, "leo/analysis/tracklet_fitting.py": tracklet_source}.items():
        residual.checked(residual.RELEASE / "src" / name, pin)
    for name in ("leo.analysis.localization_v3.tracks", "leo.analysis.graph_tracklets",
                 "leo.analysis.polynomial_tracklets", "leo.analysis.tracklet_fitting"):
        module = import_module(name)
        if Path(module.__file__).resolve() != residual.RELEASE / "src" / (name.replace(".", "/") + ".py"):
            raise ValueError("Require the released numerical implementation")

    import signed_cfo_time_readout as signed
    from leo.analysis.localization_v3.tracks import prepare_tracks
    from leo.analysis.polynomial_tracklets import TrackConfig
    from reports.ALGO08.v3 import held_short_cfo_shrink as held

    config = TrackConfig(**residual.read(residual.RELEASE / "assets/tracks.json", residual.CONFIG)["config"])
    if held.odd.WINDOWS != ((250, 2), (2250, 6)) or held.odd.PERIOD != 40_000/3:
        raise ValueError("The frozen signed installed-carrier metric changed")
    prepared, result = {}, {}
    started = residual.clock()
    for case in CASES:
        clock = residual.clock()
        native, edits, graph, bindings, fixed, rederive = candidate(case)
        observed = signed.opportunities(native)
        if any(oid not in observed or not observed[oid]["short"] for oid in edits):
            raise ValueError("Only frozen short-observation edits can enter the projection")
        load = residual.elapsed(clock)
        clock = residual.clock()
        ordinary = prepare_tracks(native, config)
        graph_time = residual.elapsed(clock)
        if (len(ordinary["tracks"]), ordinary["graph_points"]) != graph:
            raise ValueError("Reconstructed ordinary Graph differs from archived track and assigned counts")
        clock = residual.clock()
        revised, proof = project_tracks(ordinary, edits)
        projection_time = residual.elapsed(clock)
        proof.update(binding=bindings, graph=dict(tracks=graph[0], assigned=graph[1]),
                     clocks=dict(candidate_only_readback=load, rederive_previous_edits=rederive,
                                 ordinary_graph=graph_time, projection=projection_time))
        result[case] = proof
        prepared[case] = native, edits, revised, observed, fixed, proof
    development_mask = residual.digest({case: item["projected_cfo_sha256"] for case, item in result.items()})
    for case, operands in prepared.items():
        clock = residual.clock()
        score(case, operands, signed, held)
        result[case]["clocks"]["installed_comparison"] = residual.elapsed(clock)
    strict = [entry["moment_preserving"]["windows"]["250Hz_2samples"] for entry in result.values()]
    differences = [window["joint_after"] - window["joint_before"] for window in strict]
    screen = dict(cases_improved=sum(change > 0 for change in differences), pooled_net_matches=sum(differences),
                  moments_valid=all(entry["moments_valid"] for entry in result.values()),
                  retained_energy_hz2=fsum(entry["projected_energy_hz2"] for entry in result.values()))
    eligible = (screen["cases_improved"] >= 3 and screen["pooled_net_matches"] >= 0
                and screen["moments_valid"] and screen["retained_energy_hz2"] > 0)
    return dict(cases=result, development_projection_sha256=development_mask, screen=screen,
                forward=dict(case="DS30-0280", rank=68, development_screen_passed=eligible, opened=False),
                source_pins=PINS, readback_pins=READBACKS, track_config_sha256=residual.CONFIG,
                tracklet_source_sha256=tracklet_source, protocol_sha256=PROTOCOL,
                total_clock=residual.elapsed(started), receiver_runs=0, solver_runs=0, waveform_reads=0,
                archive_reads=0, survey_reads=0, source_sha256=sha256(Path(__file__).read_bytes()).hexdigest())


if __name__ == "__main__":
    print(json.dumps(main(), sort_keys=True, indent=2, allow_nan=False))
