"""Rebuild a cold exact signed fit when every paid stock membership is reproducible."""

import argparse
import gzip
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter, process_time
from types import SimpleNamespace
from unittest.mock import patch

from aperture_trial import ARMS, archive_identity, configuration, machine, read, write
from survey_owner_diagnostic import CASES, MEASUREMENTS, SAVED, bind, exact_owners, native_rows


def restrict(full, paid, aliases):
    """Carry only stock membership and integer alias witnesses into the paid fit."""
    import numpy as np
    from leo.analysis.localization_v3.tracks import active_curvature

    seen, descriptions, tracks, members = set(), [], [], []
    for track in full["tracks"]:
        ids = track["observation_ids"]
        keep = [i for i, oid in enumerate(ids) if oid in paid]
        if not keep:
            continue
        selected = [ids[i] for i in keep]
        owners = {paid[oid] for oid in selected}
        if seen.intersection(selected) or len(owners) != 1:
            raise ValueError("Full Graph membership is duplicate or ambiguously labelled")
        seen.update(selected)
        norad, role = owners.pop()
        times, values = np.asarray(track["times"])[keep], np.asarray(track["values"])[keep]
        kept = dict(key=track["key"], receiver=track["receiver"], channel=track["channel"], rf_hz=track["rf_hz"],
                    times=times, values=values, observation_ids=selected, start_s=times[0], end_s=times[-1],
                    pieces=[{key: p[key] for key in ("start_s", "end_s", "degree")} for p in track["pieces"]])
        witnessed = [aliases.get(oid) for oid in selected]
        rolls = {tuple(row) for row in witnessed if row is not None}
        alias = (next(iter(rolls))[1] if all(row is not None for row in witnessed) and len(rolls) == 1
                 and next(iter(rolls))[0] == norad else None)
        curvature = active_curvature(kept)
        reasons = []
        if role not in ("conditional", "predictive"):
            reasons.append("unsupported_publication_role")
        if len(selected) < (4 if role == "conditional" else 6):
            reasons.append("insufficient_original_track_gate_points")
        if role == "conditional" and not curvature:
            reasons.append("lost_contiguous_curvature")
        if role == "predictive" and curvature:
            reasons.append("changed_curvature_class")
        if alias is None:
            reasons.append("missing_exact_stock_alias")
        descriptions.append(dict(component=track["key"], points=len(selected), norad=norad, role=role,
                                 alias=alias, duration_s=float(np.ptp(times)), issues=reasons))
        tracks.append(kept)
        members.append((norad, role, alias))
    if seen != paid.keys():
        raise ValueError("Some paid stock observations lack an original Graph track")
    return tracks, members, descriptions


def run(case, output, census, saved_receipts):
    publication, spec = configuration()
    import numpy as np
    from leo.analysis.localization_v3 import event_position
    from leo.analysis.localization_v3.discovery import zero_state
    from leo.analysis.localization_v3.history_policy import pair_passes
    from leo.analysis.polynomial_tracklets import TrackConfig
    from leo.application import localization_v3 as policy
    from leo.contracts.digests import canonical_digest
    from leo.operations.tle_archive import TleArchiveReader
    from tools import algo08_position, algo08_scan
    from tools.pipeline_eval.variants import v5_core
    from tools.pipeline_eval.variants.experimental import regional_bound_guard
    from blind_joint_finish import build_at, digest, elapsed, history_model, readout
    from blind_joint_signed import update

    host = machine()
    if (host["cpu"] != [2] or host["nice"] < 15 or "prio 7" not in host["ionice"]
            or any(n != "1" for n in host["threads"].values())):
        raise ValueError("Expected the shared single-core numerical slot")
    native, sparse, paid, archive, offer, identity, account, stock, _, _ = bind(case, saved_receipts)
    saved = read(census)
    if saved["identity"] != identity or canonical_digest(saved["mask"]) != canonical_digest(account):
        raise ValueError("Imported owner diagnostic differs from this survey timetable")
    with gzip.open(MEASUREMENTS / "mixture-oracle.json.gz", "rt") as stream:
        witness = json.load(stream)["cases"][case]
    if witness["identity"] != identity or witness["control"]["owners"] != stock["owners"]:
        raise ValueError("Original curved alias witness differs from installed owner identity")
    metadata, _, _ = native_rows(native, paid)
    owners = exact_owners(stock["selected_rows"], stock)
    if owners["c0"] != owners["fitted_c"]:
        raise ValueError("Cannot carry a common fixed membership across different stock assignments")
    selected = {oid: value for oid, value in owners["c0"].items() if metadata[oid]["paid"]}
    result = {}

    def analyze(_recording, _root, assets, archive_root, region):
        reader = TleArchiveReader(archive_root)
        clocks = (process_time(), perf_counter())
        cfg = TrackConfig(**read(assets / "tracks.json")["config"])
        full = policy.prepare_tracks(native, cfg)
        tracks, members, restrictions = restrict(full, selected, witness["labels"]["curved"])
        result.update(layout=restrictions, full_graph_clock=elapsed(*clocks), retained_rows=len(selected),
                      status="infeasible_original_support")
        if any(row["issues"] for row in restrictions):
            return {}
        observations = [row for row in full["observations"] if row["observation_id"] in selected]
        curved = [i for i, (_, role, _) in enumerate(members) if role == "conditional"]
        retained = dict(full, observations=observations, tracks=tracks, curved_indices=curved,
                        graph_points=len(selected), status="tracks_prepared")

        def infer(prepared, region, bound, _stages, *, selected_evidence):
            scan = v5_core.scan_context(prepared, region, digest(prepared["noise"]), bound, "genuine_previous")
            labels = {int(number): j for j, number in enumerate(scan.norads)}
            rows, rolls, entries = [], [], []
            receivers = {}
            for i in curved:
                receivers.setdefault(members[i][0], set()).add(scan.tracks[i]["receiver"])
            for i, (norad, role, alias) in enumerate(members):
                track = scan.tracks[i]
                entry = dict(component=track["key"], candidate_index=labels[norad], points=len(track["times"]))
                if role == "conditional":
                    rows.append(dict(entry, candidate_norad=norad, active_curvature=True, parts=1, split_at=-1))
                    rolls.append(alias)
                else:
                    if norad not in receivers:
                        raise ValueError("A restricted predictive family lacks a curved owner")
                    entries.append(dict(entry, track_index=i, norad=norad, alias=alias,
                                        observation_ids=track["observation_ids"],
                                        cross_receiver_curved_support=len(receivers[norad]) == 2))
            node = dict(seed=dict(rows=rows, state=zero_state(scan)), aliases=rolls)
            point = np.zeros(2)
            model, _ = history_model(prepared, scan)
            base, powers, means = build_at(scan, node, None, point, {j: 0. for j in labels.values()}, model)
            keeps = base.keep
            clocks = (process_time(), perf_counter())
            paired = {arm: event_position.refit(scan, node, keeps, arm, powers, means, model, [], entries) for arm in ARMS}
            result.update(ordinary={arm: readout(dict(fit, history=[dict(step, movement_km=None) for step in fit["history"]]))
                                    for arm, fit in paired.items()}, ordinary_clocks=elapsed(*clocks), status="ordinary_rejected")
            if pair_passes(paired, include_linear=bool(entries), half_width_km=region.half_width_km):
                clocks = (process_time(), perf_counter())
                support = dict(scan=scan, node=node, keep=keeps, powers=powers, means=means, model=model,
                               arms=paired, entries=entries)
                chosen = update(prepared, support, result)
                result.update(signed_clocks=elapsed(*clocks), status="ready_for_evidence")
                points = {arm: fit["endpoint_east_north_km"] for arm, fit in chosen["arms"].items()}
                clocks = (process_time(), perf_counter())
                bounds = regional_bound_guard.inspect_boundary(
                    points, region.width_km,
                    lambda: regional_bound_guard.causal_probes(prepared["tracks"], reader, region, terminal_only=True),
                    terminal_only=True,
                )
                result.update(exterior=bounds, exterior_clocks=elapsed(*clocks))
                if bounds["would_withhold"] or bounds.get("diagnostic_error"):
                    result["status"] = "exterior_rejected"
                else:
                    clocks = (process_time(), perf_counter())
                    packet = algo08_position.selected_packet(prepared, chosen, None)
                    numerics = dict(owners={arm: fit["owner_sha256"] for arm, fit in packet["arms"].items()},
                                    associated={arm: fit["associated_points"] for arm, fit in packet["arms"].items()})
                    exact_owners({arm: [(r["observation_id"], r["norad"], r["role"]) for r in rows]
                                  for arm, rows in packet["rows"].items()}, numerics)
                    if any({r["observation_id"]: (r["norad"], r["role"]) for r in actual} != selected
                           for actual in packet["rows"].values()):
                        raise ValueError("Exact finish changed a fixed paid membership")
                    result.update(status="oracle_complete" if packet["position_grid"]["complete"] else "oracle_grid_incomplete",
                                  fits={arm: dict(latlon=fit["endpoint_latlon"], rf_rms_hz=fit["RMS_hz"])
                                        for arm, fit in chosen["arms"].items()},
                                  evidence=dict(**numerics, replay=packet["objective_replay"],
                                                grid_points=packet["position_grid"]["evaluated_points"]),
                                  evidence_clocks=elapsed(*clocks))
            return dict(status="withheld", reason="fixed_membership_oracle_only", arms={a: {"latlon": None} for a in ARMS})

        clocks = (process_time(), perf_counter())
        with patch.object(policy, "prepare_tracks", return_value=retained), patch.object(v5_core, "infer", infer):
            algo08_position.solve(sparse, reader, assets, region)
        result["cold_solve_clock"] = elapsed(*clocks)
        return {}

    with TemporaryDirectory() as scratch:
        root = Path(scratch)
        region_path = root / "region.json"
        write(region_path, offer)
        destination = root / "output"
        destination.mkdir()
        resources = SimpleNamespace(recording=root / "saved", bulk_root=destination, archive=archive, region=region_path)
        with patch.object(algo08_scan, "analyze", analyze):
            publication.run(resources, spec)
    if archive_identity(archive) != identity["archive"]:
        raise ValueError("Original archive changed")
    write(output, dict(case=case, identity=identity, census_sha256=sha256(census.read_bytes()).hexdigest(),
                       host=host, result=result, source_sha256=sha256(Path(__file__).read_bytes()).hexdigest()))


def score(directory, output):
    from aperture_score import references, distance_km

    sealed = {case: read(directory / f"{case}.oracle.json") for case in CASES}
    refs = references()
    for case, row in sealed.items():
        for arm in row["result"].get("fits", {}).values():
            arm["horizontal_error_km"] = distance_km(arm["latlon"], refs[case])
    write(output, sealed)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    trial = sub.add_parser("run")
    trial.add_argument("case", choices=CASES)
    trial.add_argument("output", type=Path)
    trial.add_argument("census", type=Path)
    trial.add_argument("--saved-receipts", type=Path, default=SAVED)
    scoring = sub.add_parser("score")
    scoring.add_argument("directory", type=Path)
    scoring.add_argument("output", type=Path)
    settings = vars(parser.parse_args())
    action = settings.pop("action")
    (run if action == "run" else score)(**settings)
