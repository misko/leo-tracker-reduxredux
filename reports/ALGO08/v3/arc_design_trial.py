"""Price complete owner arcs and solve a frozen paid waveform on saved v3 inputs."""

import argparse
from collections import Counter, defaultdict
import gzip
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter, process_time
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

from aperture_trial import archive_identity, configuration, inputs, machine, read, write
from arc_design import ARMS, Block, geometry, named_rows, select, union
from mixture_trial import elapsed
from owner_union_trial import CONTINUATION_SHA256, histories


HERE = Path(__file__).resolve().parent
STOCK_WITNESS = "9ab0632563cc2ceacd043569956ef7fa1dfb9e24f26de370df57b8a19681221f"
ALIAS_WITNESS = "f74d0a12dd7b3a493df66328853b72ad06cf3a6133defcd823567fc4e6b97d65"
CASES = ("south-containing", "south-far", "DS30-0008")


def witness(name, pin):
    content = (HERE / "measurements" / name).read_bytes()
    if sha256(content).hexdigest() != pin:
        raise ValueError(f"Saved membership authority changed in {name}")
    return json.loads(gzip.decompress(content))


def labels(case, identity, expected):
    from survey_owner_diagnostic import exact_owners

    stock = witness("track-quadrature.json.gz", STOCK_WITNESS)["runs"][case]["stock"]
    aliases = witness("mixture-oracle.json.gz", ALIAS_WITNESS)["cases"][case]
    if (stock["identity"] != identity or aliases["identity"] != identity
            or stock["owners"] != expected["owners"] or aliases["control"]["owners"] != expected["owners"]):
        raise ValueError("Frozen owner, alias and native packet identities disagree")
    owners = exact_owners(stock["selected_rows"], stock)
    if owners["c0"] != owners["fitted_c"]:
        raise ValueError("The installed arms disagree on owner or publication role")
    return owners["c0"], aliases["labels"]["curved"]


def opportunity_rows(native, owners):
    from tools.pipeline_eval.variants import carrier_continuation

    if sha256(Path(carrier_continuation.__file__).read_bytes()).hexdigest() != CONTINUATION_SHA256:
        raise ValueError("The continuation opportunity geometry requires the released implementation")
    source = native["source"]
    probes = source["probes"]
    anchor = native["clock_anchor"]["sample_counter"]
    if source["sample_rate_hz"] != 10_000_000:
        raise ValueError("The continuation geometry requires the original 10 MHz sample clock")
    duration = native["last_sample_counter"] - anchor
    joins = {}
    for i, row in enumerate(probes):
        counter = row["valid_start_counter"]
        receiver = row["receiver_id"]
        oid = "sha256:" + sha256(f"{source['session_id']}:{receiver}:{counter}".encode()).hexdigest()
        if oid in owners:
            if oid in joins or len(row["candidates"]) != 1:
                raise ValueError("An installed owner has no unique admitted lane")
            third = min(2, (3 * (counter - anchor)) // duration)
            if third < 0:
                raise ValueError("A published owner precedes the recording anchor")
            joins[oid] = (i, (f"receiver:{receiver}", f"rf_half:{int(row['channel'] > 4)}", f"time_third:{third}"))
    if joins.keys() != owners.keys():
        raise ValueError("Some published owners are absent from the native causal timeline")
    donors = histories(probes, {row[0] for row in joins.values()})
    return {oid: (i, frozenset((i, *donors[i])), strata) for oid, (i, strata) in joins.items()}


def geometry_blocks(tracks, memberships, opportunities, grams):
    points, lanes, strata = defaultdict(set), defaultdict(set), defaultdict(set)
    for track, (norad, _, _) in zip(tracks, memberships, strict=True):
        for oid in track["observation_ids"]:
            i, required_lanes, coverage = opportunities[oid]
            points[norad].add(i)
            lanes[norad].update(required_lanes)
            strata[norad].update(coverage)
    blocks = [Block(norad, frozenset(lanes[norad]), frozenset(strata[norad]), grams[norad]) for norad in sorted(points)]
    return blocks, points


def retained(prepared, tracks, roles, *, refit):
    from leo.analysis.localization_v3.noise import estimate_noise

    full = prepared["tracks"]
    ids = {oid for track in tracks for oid in track["observation_ids"]}
    observations = [row for row in full["observations"] if row["observation_id"] in ids]
    if len(observations) != len(ids):
        raise ValueError("At least one retained arc measurement is missing or repeated")
    curves = [i for i, (_, role, _) in enumerate(roles) if role == "conditional"]
    stream = dict(full, observations=observations, tracks=tracks, curved_indices=curves, graph_points=len(ids))
    return dict(prepared, tracks=stream, noise=estimate_noise(tracks, observations) if refit else prepared["noise"])


def design(prepared, region, bound, tracks, roles, descriptions, rows, total_lanes):
    from blind_joint_finish import digest
    from tools.pipeline_eval.variants import v5_core

    stage = retained(prepared, tracks, roles, refit=False)
    scan = v5_core.scan_context(stage, region, digest(stage["noise"]), bound, "genuine_previous")
    blocks, points = geometry_blocks(tracks, roles, rows, geometry(scan, roles))
    diagnostics = defaultdict(list)
    for row in descriptions:
        if row["issues"]:
            diagnostics[row["norad"]].append(row)
    all_blocks = select(blocks, total_lanes)
    known = [block for block in blocks if block.norad not in diagnostics]
    witnessed = all_blocks if len(known) == len(blocks) else select(known, total_lanes, authority=blocks)
    chosen = all_blocks["frontier"]["3"]["selected"]
    if chosen is None:
        return dict(nominal=all_blocks, fully_witnessed=witnessed, selected_norads=[], selected_indices=[],
                    paid_indices=[], unresolved={})
    selected = [block for block in blocks if block.norad in chosen["norads"]]
    return dict(nominal=all_blocks, fully_witnessed=witnessed, selected_norads=sorted(b.norad for b in selected),
                selected_indices=sorted(set().union(*(points[b.norad] for b in selected))),
                paid_indices=sorted(union(selected, "lanes")),
                unresolved={norad: diagnostics[norad] for norad in chosen["norads"] if norad in diagnostics},
                populations={b.norad: dict(retained_lanes=len(points[b.norad]), single_block_cost=len(b.lanes),
                                           strata=sorted(b.strata), missing_witnesses=diagnostics[b.norad])
                             for b in blocks})


def fit(prepared, region, bound, reader, owners, roles, result):
    from leo.analysis.localization_v3 import event_position
    from leo.analysis.localization_v3.history_policy import pair_passes
    from tools import algo08_position
    from tools.pipeline_eval.variants import v5_core
    from tools.pipeline_eval.variants.experimental import regional_bound_guard

    from blind_joint_finish import build_at, digest, history_model, readout
    from blind_joint_signed import update
    from survey_owner_diagnostic import exact_owners

    scan = v5_core.scan_context(prepared, region, digest(prepared["noise"]), bound, "genuine_previous")
    node, predictive = named_rows(scan, roles, predictive=True)
    model, _ = history_model(prepared, scan)
    centre = np.zeros(2)
    base, powers, means = build_at(scan, node, None, centre,
                                 {row["candidate_index"]: 0. for row in node["seed"]["rows"]}, model)
    clock = (process_time(), perf_counter())
    ordinary = {arm: event_position.refit(scan, node, base.keep, arm, powers, means, model, [], predictive)
                for arm in ARMS}
    result["ordinary_clocks"] = elapsed(*clock)
    result["ordinary"] = {arm: readout(dict(row, history=[dict(step, movement_km=None) for step in row["history"]]))
                          for arm, row in ordinary.items()}
    if not pair_passes(ordinary, include_linear=bool(predictive), half_width_km=region.half_width_km):
        return dict(status="fixed_owner_gate_rejected", reason="original_ordinary_pair_gate")
    support = dict(scan=scan, node=node, keep=base.keep, powers=powers, means=means, model=model,
                   arms=ordinary, entries=predictive)
    clock = (process_time(), perf_counter())
    chosen = update(prepared, support, result)
    result["signed_clocks"] = elapsed(*clock)
    endpoints = {arm: value["endpoint_east_north_km"] for arm, value in chosen["arms"].items()}
    clock = (process_time(), perf_counter())
    exterior = regional_bound_guard.inspect_boundary(
        endpoints, region.width_km,
        lambda: regional_bound_guard.causal_probes(prepared["tracks"], reader, region, terminal_only=True),
        terminal_only=True,
    )
    result.update(exterior=exterior, exterior_clocks=elapsed(*clock))
    if exterior["would_withhold"]:
        return dict(status="withheld", reason="both_receivers_support_far_exterior")
    if exterior.get("diagnostic_error"):
        return dict(status="fixed_owner_gate_rejected", reason="exterior_evidence_unavailable")
    clock = (process_time(), perf_counter())
    packet = algo08_position.selected_packet(prepared, chosen, None)
    evidence = dict(owners={arm: value["owner_sha256"] for arm, value in packet["arms"].items()},
                    associated={arm: value["associated_points"] for arm, value in packet["arms"].items()})
    maps = exact_owners({arm: [(r["observation_id"], r["norad"], r["role"]) for r in rows]
                         for arm, rows in packet["rows"].items()}, evidence)
    if any(maps[arm] != owners for arm in ARMS):
        raise ValueError("The original likelihood changed a frozen owner or role")
    result.update(evidence=dict(**evidence, replay=packet["objective_replay"],
                               grid_points=packet["position_grid"]["evaluated_points"]),
                  evidence_clocks=elapsed(*clock))
    status = "ok" if packet["position_grid"]["complete"] else "fixed_owner_grid_incomplete"
    return dict(status=status, reason=None, arms={arm: dict(latlon=row["endpoint_latlon"], rf_rms_hz=row["RMS_hz"])
                                                for arm, row in chosen["arms"].items()})


def trial(case, output, *, selection_path=None, dense_fit=False):
    publication, specification = configuration()
    from leo.contracts.digests import canonical_digest
    from leo.operations.tle_archive import TleArchiveReader
    from tools import algo08_position, algo08_scan
    from tools.pipeline_eval.variants import v5_core
    from survey_owner_oracle import restrict

    host = machine()
    if (host["cpu"] != [2] or host["nice"] < 15 or "prio 7" not in host["ionice"]
            or any(n != "1" for n in host["threads"].values())):
        raise ValueError("Expected the shared low-priority single-core worker")
    native, archive, offer, expected, identity = inputs(case)
    authority_case = "south-containing" if case == "south-far" else case
    authority = identity
    if authority_case != case:
        _, _, _, expected, authority = inputs(authority_case)
    owner_map, alias_map = labels(authority_case, authority, expected)
    rows = opportunity_rows(native, owner_map)
    source = None
    if case == "south-far":
        if selection_path is None:
            raise ValueError("The omitted offer requires the containing offer's frozen design")
        selection_bytes = selection_path.read_bytes()
        source = json.loads(selection_bytes)
        if source["identity"] != authority or source["identity"]["native_sha256"] != identity["native_sha256"]:
            raise ValueError("The omitted offer needs the same frozen waveform")
        source = source["design"]
    result = {}

    def analyze(_recording, _root, assets, archive_root, region):
        reader = TleArchiveReader(archive_root)

        def infer(prepared, region, bound, _stages, *, selected_evidence):
            if prepared["status"] != "inputs_prepared":
                result.update(status="preparation_rejected", reason=prepared["status"])
                return {}
            clock = (process_time(), perf_counter())
            full, roles, descriptions = restrict(prepared["tracks"], owner_map, alias_map)
            result.update(full_support_summary=dict(arcs=len(full), rows=len(owner_map),
                                                   families=len(set(n for n, _, _ in roles)),
                                                   issues=dict(Counter(issue for row in descriptions for issue in row["issues"]))))
            selected = source
            if selected is None:
                selected = design(prepared, region, bound, full, roles, descriptions, rows, len(native["source"]["probes"]))
            result.update(design=selected, design_clocks=elapsed(*clock))
            result["selected_lanes_sha256"] = canonical_digest(selected["selected_indices"])
            result["paid_lanes_sha256"] = canonical_digest(selected["paid_indices"])
            if not selected["selected_norads"]:
                result.update(status="no_balanced_design")
                return {}
            if selected["unresolved"] or (case == "DS30-0008"
                                          and (not dense_fit or selected["nominal"]["frontier"]["3"]["target"] is None)):
                result.update(status="frontier_only")
                return {}
            keep = set(selected["selected_norads"])
            tracks, memberships = zip(*((track, role) for track, role in zip(full, roles, strict=True) if role[0] in keep),
                                      strict=True)
            selected_owners = {oid: owner_map[oid] for track in tracks for oid in track["observation_ids"]}
            paid = sorted(set().union(*(rows[oid][1] for oid in selected_owners)))
            if (sorted(rows[oid][0] for oid in selected_owners) != selected["selected_indices"]
                    or paid != selected["paid_indices"]):
                raise ValueError("Selected measured inputs or paid donor lanes changed in the fixed fit")
            clock = (process_time(), perf_counter())
            stage = retained(prepared, list(tracks), memberships, refit=True)
            try:
                result.update(fit(stage, region, bound, reader, selected_owners, memberships, result))
            except (ValueError, AssertionError, np.linalg.LinAlgError) as exc:
                result.update(status="fixed_owner_fit_error", reason=f"{type(exc).__name__}: {exc}")
            result["retained_fit_clocks"] = elapsed(*clock)
            return {}

        clock = (process_time(), perf_counter())
        with patch.object(v5_core, "infer", infer):
            algo08_position.solve(native, reader, assets, region)
        result["all_saved_work_clocks"] = elapsed(*clock)
        return {}

    with TemporaryDirectory() as directory:
        scratch = Path(directory)
        offer_path = scratch / "offer.json"
        write(offer_path, offer)
        root = scratch / "output"
        root.mkdir()
        args = SimpleNamespace(recording=scratch / "saved", bulk_root=root, archive=archive, region=offer_path)
        with patch.object(algo08_scan, "analyze", analyze):
            publication.run(args, specification)
    if archive_identity(archive) != identity["archive"]:
        raise ValueError("The causal archive changed during the saved replay")
    write(output, dict(case=case, identity=identity, support_authority=authority, worker=host,
                       containing_receipt_sha256=None if source is None else sha256(selection_bytes).hexdigest(),
                       source_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
                       selector_sha256=sha256((HERE / "arc_design.py").read_bytes()).hexdigest(),
                       stock_witness_sha256=STOCK_WITNESS, alias_witness_sha256=ALIAS_WITNESS, **result))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", choices=CASES)
    parser.add_argument("output", type=Path)
    parser.add_argument("--selection-path", type=Path)
    parser.add_argument("--dense-fit", action="store_true")
    trial(**vars(parser.parse_args()))
