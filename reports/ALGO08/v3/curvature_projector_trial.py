"""Price whole-curve projection on one sealed dense family pair and one South pair."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys
from time import perf_counter, process_time
from unittest.mock import patch

import numpy as np


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from curvature_projector import CurveRows, ReceiverProjector, rank_preference

DENSE_RECEIPT = Path("/dev/shm/leo-0008-family-refit02/sealed.json")
DENSE_SEAL = "3e4f8e014ddc4b2e2c6869632acb932e1b5eaa9708ecdf57c6c6b35478f0a553"
FROZEN_SOURCE = Path("/dev/shm/leo-v3-0008-family-refit/reports/ALGO08/v3")
FAMILY_SOURCE = "e0e2650cbad3b0bb0177da2766fc85edf0f7f916a650ae40fd1806b3f8ea1662"
ARMS = ("c0", "fitted_c")


class SignedCapture(BaseException):
    """End the saved worker at its scientific context port."""


def now():
    return process_time(), perf_counter()


def cost(start):
    return dict(cpu_s=process_time()-start[0], elapsed_s=perf_counter()-start[1])


def verify(path, expected):
    data = path.read_bytes()
    if sha256(data).hexdigest() != expected:
        raise ValueError(f"Enrolled source or receipt changed: {path}")
    return data


def table(scan, memberships, common_keys):
    meta = scan.fixed_window_noise
    sigma = meta["per_observation_noise_sigma_hz"]
    orbit_by_norad = {n: i for i, n in enumerate(scan.norads)}
    rows, labels, receivers = [], [[], []], []
    for i, track in enumerate(scan.tracks):
        key = track["key"]
        if key not in common_keys:
            continue
        (ra, a, ida), (rb, b, idb) = (m[key] for m in memberships)
        if ra != rb:
            raise ValueError("Matched track role changed")
        common = ida & idb
        ids = [oid for oid in track["observation_ids"] if oid in common]
        if len(ids) != len(common) or len(ids) < 3:
            raise ValueError("Whole-curve comparison requires a fixed valid common observation set")
        keep = np.isin(track["observation_ids"], ids)
        q = track["rf_hz"]/11.5e9
        scale = [sigma[oid] if meta["extra_parameter_BIC_gain"] > 0 else scan.radio_sigma_hz for oid in ids]
        rows.append(CurveRows(track["times"][keep], track["values"][keep], 1./np.asarray(scale), scan.rx_basis[i][keep], q))
        for destination, norad in zip(labels, (a, b), strict=True):
            destination.append(np.full(len(ids), orbit_by_norad[norad]))
        receivers.append(track["receiver"])
    if len(rows) != len(common_keys) or not rows:
        raise ValueError("A nominal common curve is absent from the prepared scan")
    return rows, [np.concatenate(alternatives) for alternatives in labels], receivers


def phase_vector(scan, labels, reference):
    if len(labels) != len(reference) or len(set(labels)) != len(labels):
        raise ValueError("Archive phase references do not match the ordered family labels")
    phases = np.full(len(scan.norads), np.nan)
    phases[np.asarray(labels, int)] = reference
    return phases


def diagnostic(scan, common, states):
    from leo.analysis.research.continuous_curve_fit import paired_phase_frequency

    started = now()
    rows, labels, receivers = table(scan, common, common[0].keys() & common[1].keys())
    table_cpu = cost(started)
    started = now()
    times = np.concatenate([r.times for r in rows])
    boundaries = np.cumsum([len(r.times) for r in rows])[:-1]
    groups = {r: [i for i, rx in enumerate(receivers) if rx == r] for r in sorted(set(receivers))}
    projectors = {r: ReceiverProjector([rows[i] for i in idx]) for r, idx in groups.items()}
    setup = cost(started)
    result = {}
    for arm, records in states.items():
        result[arm] = {}
        for name in ("reference", "posterior"):
            started = now()
            entries = []
            for j, record in enumerate(records):
                phases = record[name]
                if not np.isfinite(phases[labels[j]]).all():
                    raise ValueError("Actual bounded phase state missing an observation owner")
                f, elevation = paired_phase_frequency(scan.sky, times, labels[j], phases, *record["latlon"])
                per_track = np.split(f, boundaries)
                scores = [projectors[r].score([per_track[i] for i in ids]) for r, ids in groups.items()]
                entries.append(dict(score=sum(scores), below_horizon=int(np.count_nonzero(elevation < 0.))))
            result[arm][name] = dict(scores=entries, clock=cost(started),
                                     preferred=rank_preference([v["score"] for v in entries]))
    return dict(points=len(times), tracks=len(rows), dimensions={str(r): p.dimension for r, p in projectors.items()},
                smooth_ranks={str(r): p.rank for r, p in projectors.items()},
                differing_row_labels=int(np.count_nonzero(labels[0] != labels[1])),
                table=table_cpu, projector=setup, arms=result)


def load_dense(root):
    verify(FROZEN_SOURCE/"dense_family_refit.py", FAMILY_SOURCE)
    sys.path.insert(0, str(FROZEN_SOURCE))
    import dense_family_refit as family
    import joint_publication

    if Path(family.__file__).resolve() != FROZEN_SOURCE/"dense_family_refit.py":
        raise ValueError("The frozen saved worker was not loaded")
    original_route = joint_publication.make_route
    signed_context = []

    def route(*args, collect=None, **kwargs):
        def collect_here(*, ordinary, signed):
            signed_context.append(signed)
            if collect is not None:
                collect(ordinary=ordinary, signed=signed)
            raise SignedCapture

        return original_route(*args, collect=collect_here, **kwargs)

    started = now()
    with patch.object(joint_publication, "make_route", route):
        try:
            family.worker(root)
        except SignedCapture:
            pass
        else:
            raise ValueError("Saved worker did not reach the bounded signed state port")
    captured, = signed_context
    return family, captured, cost(started)


def dense(root):
    archived = json.loads(verify(DENSE_RECEIPT, DENSE_SEAL))
    family, signed, replay = load_dense(root)
    from local_future_repair import memberships

    current = json.loads(family.checked(family.HYBRID/family.JOINT, family.HYBRID_SHA))["selected_rows"]
    current_maps = [memberships(signed, arm) for arm in ARMS]
    if current_maps[0] != current_maps[1]:
        raise ValueError("Original arm support differs")
    for arm, members in zip(ARMS, current_maps, strict=True):
        flattened = sorted((oid, norad, role) for role, norad, ids in members.values() for oid in ids)
        if flattened != sorted(map(tuple, current[arm])):
            raise ValueError("Captured hypothesis is not the original signed publication roster")
    changed = {oid for arc in archived["arcs"].values() for oid in arc["active_ids"]}
    alternate, arcs = family.exchanged(signed, current_maps[0], changed)
    if json.loads(json.dumps(arcs)) != archived["arcs"]:
        raise ValueError("The reproduced hybrid exchange changed the archived seven active curves")
    scan = signed["scan"]
    states, reference, mappings = {}, {}, []
    for arm in ARMS:
        states[arm], reference[arm], arm_members = [], [], []
        for label, branch in (("identity", signed), ("fixed_alternate", alternate)):
            started = now()
            model_state = family.fixed(branch, arm)
            paid = cost(started)
            witness = family.witness(model_state)
            old = archived[label][arm]
            for field in ("objective", "curved_objective", "rf_rms_hz", "latlon", "east_north_km"):
                np.testing.assert_allclose(witness[field], old[field], rtol=0., atol=1e-8)
            members = memberships(dict(branch, arms={arm: model_state}), arm)
            expected = {key: (role, family.OLD if label == "fixed_alternate" and key in arcs else norad, ids)
                        for key, (role, norad, ids) in current_maps[0].items()}
            if members != expected:
                raise ValueError("The fixed objective replay lost original owner rows")
            arm_members.append(members)
            labels = sorted({row["candidate_index"] for row in branch["node"]["seed"]["rows"] if row["active_curvature"]})
            states[arm].append(dict(latlon=witness["latlon"], reference=phase_vector(scan, labels, model_state["phase_reference"]),
                                    posterior=model_state["state"]["phases"]))
            reference[arm].append(dict(objective=witness["objective"], rf_rms_hz=witness["rf_rms_hz"],
                                       coordinates=witness["east_north_km"], clock=paid))
        mappings.append(arm_members)
    if mappings[0] != mappings[1]:
        raise ValueError("Expected identical observation support across calibration arms")
    maps = mappings[0]
    return dict(pinned_control=DENSE_SEAL, captured=1, capture_clock=replay, compared_candidates=[family.NEW, family.OLD],
                next_stage=reference, whole=diagnostic(scan, maps, states),
                changed_only=diagnostic(scan, [{k: m[k] for k in arcs} for m in maps], states),
                signed_original_rows=len(current["c0"]), changed_rows=len(changed), full_data_conditioned=True)


def south():
    from curvature_filter_trial import CONTROLS, inputs
    from empty_bootstrap import RELEASE, checked, load_runtime
    from held_spatial_start_trial import json_pin

    _, spec, _, _, _ = load_runtime()
    from exact_graph_execution import graph_execution
    from full_short_run import geographic_projection
    from historical_orbit_index import TRACK_PIN
    from leo.analysis.localization_v3.discovery import signature
    from leo.analysis.localization_v3.event_position import cached
    from leo.analysis.localization_v3.position import NormalPosition
    from leo.analysis.localization_v3.region import SearchRegion
    from leo.analysis.localization_v3.tracks import TrackConfig
    from leo.analysis.localization_v4.backend import read_manifest, validate_manifest
    from leo.application.localization_v3 import prepare_native_scan
    from tools.algo08_position import NativeBound
    from tools.pipeline_eval.variants import v5_core
    from tools.pipeline_eval.variants.algo08_causal_reuse import CausalPreparationParser
    from tools.pipeline_eval.variants.algo08_causal_table import causal_table
    from tools.pipeline_eval.variants.experimental.preparation_gc import defer_collection
    from tools.pipeline_eval.variants.experimental.tle_records import batch_records

    native, reader, offer, projector, identity = inputs("south")
    stock = json_pin(*CONTROLS["south"])["route_details"]["cold"]
    tracks = TrackConfig(**json.loads(checked(RELEASE/"assets/tracks.json", TRACK_PIN))["config"])
    parser = Path(spec["tle_parser"]["library"])
    checked(parser, spec["tle_parser"]["sha256"])
    bound = NativeBound(validate_manifest(read_manifest(RELEASE/"assets/native/manifest.json"), check_provider=True)["binary"])
    region = SearchRegion(offer.center, offer.width_km)
    started = now()
    with (batch_records(parser) as parsed, causal_table(canonical_exports=True, previous_catalogues=True),
          graph_execution(enabled=True)):
        prepared = defer_collection(prepare_native_scan)(native, reader, tracks, element_parser=CausalPreparationParser(),
                   screen_latitude_deg=offer.screen_center[0], screen_longitude_deg=offer.screen_center[1])
    preparation = cost(started)
    if prepared["status"] != "inputs_prepared" or parsed["fallback"]:
        raise ValueError("Expected the original fully prepared South packet")
    with geographic_projection(projector):
        started = now()
        scan = v5_core.scan_context(prepared, region, None, bound, "previous")
        candidates = v5_core.ranked_initial_nodes(scan)[:2]
        shortlist = cost(started)
        if len(candidates) != 2 or signature(candidates[0]) == signature(candidates[1]):
            raise ValueError("Expected two distinct original cold candidate rosters")
        reference, states = {arm: [] for arm in ARMS}, {arm: [] for arm in ARMS}
        members = []
        for index, (node, old, complete) in enumerate(zip(candidates, stock["prefix"][:2], stock["completed"][:2], strict=True), start=1):
            point = np.array(old["parameters"])
            if index != old["branch"] or index != complete["branch"]:
                raise ValueError("Archive did not retain the first two ranked original options")
            labels = sorted({r["candidate_index"] for r in node["seed"]["rows"]})
            if labels != complete["labels"]:
                raise ValueError("The actual South candidate catalogue identities changed")
            for arm in ARMS:
                started = now()
                p = cached(NormalPosition(scan, node, scan.radio_sigma_hz, arm == "fitted_c", reference=np.zeros(len(labels))))
                residual = p.residual(point)
                objective = float(residual @ residual)
                state = p.state(point)
                paid = cost(started)
                if arm == "c0":
                    np.testing.assert_allclose(objective, old["score"], rtol=0., atol=1e-7)
                    members.append({r["component"]: ("conditional", r["candidate_norad"], frozenset(scan.tracks[i]["observation_ids"]))
                                    for r, i in zip(p.rows, p.members, strict=True)})
                states[arm].append(dict(latlon=region.latlon(point), reference=phase_vector(scan, labels, p.reference), posterior=state["phases"]))
                reference[arm].append(dict(objective=objective, coordinates=point.tolist(), clock=paid))
    return dict(pinned_control=CONTROLS["south"][1], compared_candidates=[1, 2], input=identity,
                preparation=preparation, prepared_rank=shortlist, next_stage=reference,
                whole=diagnostic(scan, members, states), capture_clock=None, original_optimizer_calls=0)


def run(case, root):
    from dense_geographic_trial import host

    machine = host()
    started = now()
    result = dense(root) if case == "dense" else south()
    for arm in ARMS:
        result["next_stage_preferred_"+arm] = rank_preference([entry["objective"] for entry in result["next_stage"][arm]])
    result.update(machine=machine, original_waveform_reads=0, grid_evaluations=0, plots=0, total=cost(started),
                  source={p.name: sha256(p.read_bytes()).hexdigest() for p in
                          (Path(__file__), HERE/"curvature_projector.py", HERE/"curvature-projector-protocol.md")})
    def numeric(value):
        if isinstance(value, (np.ndarray, np.generic)):
            return value.tolist()
        raise TypeError(f"Unsupported trial receipt value {type(value).__name__}")

    serial = json.dumps(result, sort_keys=True, indent=2, allow_nan=False, default=numeric)
    with (root/f"{case}.json").open("x") as file:
        file.write(serial+"\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", choices=("dense", "south"))
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    if args.root.resolve().parent != Path("/dev/shm"):
        raise ValueError("Expected a new direct tmpfs trial directory")
    run(args.case, args.root)
