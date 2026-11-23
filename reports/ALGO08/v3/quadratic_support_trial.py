"""Capture and ablate exact memberships from the two archived quadratic development saves."""

import argparse
import gzip
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter, process_time
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

from aperture_trial import archive_identity, configuration, machine, read, write
from arc_design_trial import fit, retained
from mixture_trial import ARMS, elapsed, summarize
from quadratic_support import acquisition_ceiling, incidence, native_rows, paid_holdout, uncertainty


HERE = Path(__file__).resolve().parent
CASES = ("DS30-0016", "south-containing")
PINS = {
    "complete": ("sparse-consensus-summary.json.gz", "b843cfad5e324ad0c856019e3e607634a526f422520cc89e163bc3da6d58df73"),
    "quadratic": ("paid-quadratic.json.gz", "9237e3c1d1cbcca9b234dcb5782c1667857efe201683d84634e732004d2e40e1"),
}


def baseline(case, mode):
    file, pin = PINS[mode]
    content = (HERE / "measurements" / file).read_bytes()
    if sha256(content).hexdigest() != pin:
        raise ValueError(f"Unmodified archived comparator required for {mode}")
    return json.loads(gzip.decompress(content))[case][mode]


def inputs(case, mode):
    if mode == "complete":
        from sparse_consensus_trial import load

        native, archive, offer, _, identity = load(case, mode)
        paid = None
    else:
        from paid_graph_trial import prepared_packet

        native, archive, offer, identity, _, paid = prepared_packet(case, "margin")
    expected = baseline(case, mode)["identity"]
    fields = ("case", "archive", "source", "offer", "ledger", "native_sha256")
    if any(identity[key] != expected[key] for key in fields):
        raise ValueError("Reconstructed input differs from the frozen packet")
    return native, archive, offer, {key: identity[key] for key in fields}, paid


def runtime(publication, specification, native, archive, offer, mode, analyze_loaded):
    from leo.operations.tle_archive import TleArchiveReader
    from tools import algo08_position, algo08_scan
    from paid_quadratic import quadratic

    def analyze(_recording, _root, assets, archive_root, region):
        factory = algo08_position.TrackConfig
        shape = factory if mode == "complete" else lambda **cfg: quadratic(factory(**cfg))
        with patch.object(algo08_position, "TrackConfig", shape):
            return analyze_loaded(native, TleArchiveReader(archive_root), assets, region)

    with TemporaryDirectory() as directory:
        scratch = Path(directory)
        offer_path = scratch / "offer.json"
        write(offer_path, offer)
        root = scratch / "output"
        root.mkdir()
        args = SimpleNamespace(recording=scratch / "saved", bulk_root=root, archive=archive, region=offer_path)
        with patch.object(algo08_scan, "analyze", analyze):
            return publication.run(args, specification)


def capture_support(candidate, native, packet):
    from blind_joint_signed import describe
    from leo.analysis.research.retained_track_likelihood import PERIOD

    by_oid = native_rows(native)
    saved = describe(candidate)
    tracks = {t["key"]: {oid: value for oid, value in zip(t["observation_ids"], t["values"], strict=True)}
              for t in candidate["scan"].tracks}
    labels = {}
    for role, blocks in (("conditional", saved["curved"]), ("predictive", saved["predictive"])):
        for component, row in blocks.items():
            for oid in row["ids"]:
                lifted = (tracks[component][oid] - by_oid[oid]["signal"][-1]) / PERIOD
                if abs(lifted - round(lifted)) > 1e-8 or oid in labels:
                    raise ValueError("Could not trace the original total alias for a unique published row")
                labels[oid] = dict(norad=row["norad"], role=role, component=component, alias=row["alias"],
                                   effective_alias=int(row["alias"] + round(lifted)))
    expected = {oid: (v["norad"], v["role"]) for oid, v in labels.items()}
    for arm in ARMS:
        published = {r["observation_id"]: (r["norad"], r["role"]) for r in packet["rows"][arm]}
        if published != expected:
            raise ValueError("The captured curved and predictive witness differs from its published owners")
    return dict(labels=labels,
                calibration_hz_per_ghz=float(candidate["arms"]["fitted_c"]["state"]["beta"][-1]),
                positions={arm: row["endpoint_east_north_km"] for arm, row in candidate["arms"].items()})


def capture(publication, specification, case, mode, source):
    from blind_joint_route import make_route
    from tools import algo08_position
    from tools.pipeline_eval.variants import v5_core

    native, archive, offer, identity, _ = source
    expected = baseline(case, mode)

    def run(native, reader, assets, region):
        witnesses, attempts = [], []
        finish = algo08_position.selected_packet

        def observe(prepared, signed, fit):
            packet = finish(prepared, signed, fit)
            if fit is None:
                witnesses.append(capture_support(signed, native, packet))
            return packet

        route = make_route(v5_core.infer, reader, attempts, repair=True, signed_finish=True)
        clocks = (process_time(), perf_counter())
        with (patch.object(algo08_position, "selected_packet", observe), patch.object(v5_core, "infer", route)):
            outcome = algo08_position.solve(native, reader, assets, region)
        summarized, _ = summarize(*outcome)
        if summarized != expected["result"] or len(witnesses) != 1 or attempts[-1]["decision"] != "complete":
            raise ValueError(f"Cold {case} {mode} did not reproduce its archived selected scientific output")
        return dict(terminal=summarized, witness=witnesses[0], clocks=elapsed(*clocks))

    result = runtime(publication, specification, native, archive, offer, mode, run)
    if archive_identity(archive) != identity["archive"]:
        raise ValueError("The original causal archive changed")
    return dict(identity=identity, **result)


def cold_variants(publication, specification, source, mode, labels, populations):
    from blind_joint_finish import digest
    from survey_owner_oracle import restrict
    from tools import algo08_position
    from tools.pipeline_eval.variants import v5_core

    native, archive, offer, identity, _ = source
    outcomes = {}

    def run(native, reader, assets, region):
        def infer(prepared, region, bound, stages, *, selected_evidence):
            if prepared["status"] != "inputs_prepared":
                raise ValueError(prepared["status"])
            for name, ids in populations.items():
                start = (process_time(), perf_counter())
                owners = {oid: (labels[oid]["norad"], labels[oid]["role"]) for oid in ids}
                aliases = {oid: (labels[oid]["norad"], labels[oid]["alias"]) for oid in ids}
                tracks, memberships, description = restrict(prepared["tracks"], owners, aliases)
                curved_families = {row["norad"] for row in description
                                   if not row["issues"] and row["role"] == "conditional"}
                for row in description:
                    if row["role"] == "predictive" and row["norad"] not in curved_families:
                        row["issues"].append("no_eligible_conditional_family")
                result = dict(rows=len(ids), arcs=len(tracks), role_issues=[r for r in description if r["issues"]],
                              status="unsupported_original_roles")
                outcomes[name] = result
                if tracks:
                    layout = retained(prepared, tracks, memberships, refit=False)
                    scan = v5_core.scan_context(layout, region, digest(layout["noise"]), bound, "genuine_previous")
                    result["uncertainty"] = uncertainty(scan, memberships)
                if tracks and not result["role_issues"]:
                    stage = retained(prepared, tracks, memberships, refit=True)
                    publish = algo08_position.selected_packet

                    def trace(prepared, candidate, selected):
                        result["calibration_hz_per_ghz"] = float(candidate["arms"]["fitted_c"]["state"]["beta"][-1])
                        result["east_north_km"] = {arm: r["endpoint_east_north_km"]
                                                  for arm, r in candidate["arms"].items()}
                        return publish(prepared, candidate, selected)

                    try:
                        with patch.object(algo08_position, "selected_packet", trace):
                            result.update(fit(stage, region, bound, reader, owners, memberships, result))
                    except (ValueError, AssertionError, np.linalg.LinAlgError) as error:
                        result.update(status="fixed_fit_failed", reason=f"{type(error).__name__}: {error}")
                if name == "paid_quadratic":
                    try:
                        result["held_prediction"] = paid_holdout(prepared, region, bound, tracks, memberships)
                    except (ValueError, AssertionError, np.linalg.LinAlgError) as error:
                        result["held_prediction"] = dict(status="held_prediction_failed",
                                                         reason=f"{type(error).__name__}: {error}")
                result["cpu_wall"] = elapsed(*start)
            return {}

        with patch.object(v5_core, "infer", infer):
            algo08_position.solve(native, reader, assets, region)
        return {}

    runtime(publication, specification, native, archive, offer, mode, run)
    if archive_identity(archive) != identity["archive"]:
        raise ValueError("The original causal archive changed")
    return outcomes


def run(case, output):
    publication, specification = configuration()
    host = machine()
    if (host["cpu"] != [2] or host["nice"] < 15 or "prio 7" not in host["ionice"]
            or set(host["threads"].values()) != {"1"}):
        raise ValueError("Expected the shared low-priority Gauss process")
    sources = {mode: inputs(case, mode) for mode in PINS}
    captures = {mode: capture(publication, specification, case, mode, source) for mode, source in sources.items()}
    complete, sparse = (captures[key]["witness"]["labels"] for key in PINS)
    full_rows, paid_rows = (native_rows(sources[key][0]) for key in PINS)
    paid = sources["quadratic"][-1]
    exact_paid, common, overlap = incidence(complete, sparse, full_rows, paid_rows, paid)
    fixed = {}
    for key, labels, populations in (
        ("complete", complete, {"full": complete.keys(), "paid_stock": exact_paid, "common_stock": common}),
        ("quadratic", sparse, {"paid_quadratic": sparse.keys(), "common_quadratic": common}),
    ):
        fixed.update(cold_variants(publication, specification, sources[key], key, labels, populations))
    donors = acquisition_ceiling(complete, sparse, full_rows, paid)
    write(output, dict(case=case, captures=captures, paid_visits=len(paid), comparison=overlap,
                       fixed=fixed, acquisition_ceiling=donors, worker=host,
                       source_sha256=sha256(Path(__file__).read_bytes()).hexdigest()))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", choices=CASES)
    parser.add_argument("output", type=Path)
    run(**vars(parser.parse_args()))
