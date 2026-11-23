"""Compare the differential start with the original saved full-catalogue cold winner."""

import argparse
from pathlib import Path
from runpy import run_path
from unittest.mock import patch

import numpy as np

from aperture_trial import archive_identity, configuration, read, solve, write
from arc_doppler_start import propose
from cold_track_row_trial import SHARING, fit_evidence, rank_and_race
from dense_geographic_trial import elapsed, host, now
from dense_full_short_crossover import TRACK_ASSET_PIN, file_sha


HERE = Path(__file__).resolve().parent
SOURCES = {
    "weak": (Path("/var/tmp/leo-short-graph-20261123-physical"),
             "032fa7ed291639e816f733af1589c12872b4f1a6340648e0307d129988b229cc"),
    "north": (Path("/var/tmp/leo-north-short-regional-nov23/containing"),
              "3d8beaf10a6d3e9c4025627fec4a8a0f864f78e6fd4d6c6061573b1a4b7f2f13"),
    "dense": (Path("/var/tmp/leo-v3-regional-dense-pair/native"),
              "11c554cbcca4f756e07e810bbc7b34b548a799fd005645fd4d9e5fcbba8ef72e"),
}
ARMS = {"c0": False, "fitted_c": True}


def source(case):
    from leo.contracts.digests import canonical_digest
    from regional_track_trial import assignment

    directory, pin = SOURCES[case]
    receipt = directory / "joint-research-receipt.json"
    if file_sha(receipt) != pin:
        raise ValueError("Unexpected saved control")
    archived = read(receipt)
    identity = archived["receipt"]
    terminal = read(directory / "fast-scan-automatic-work" / identity["run_id"] / "terminal.json")
    packet, = (directory / "fast-scan-automatic-work").glob("*/detections.json")
    native = read(packet)
    if case == "north":
        from short_stereo_trial import load_source

        _, archive, _, key, offer, expected = load_source("north")
        if expected != native:
            raise ValueError("Expected the unfiltered northern packet")
    else:
        archive, _, key, offer, _ = assignment("dense" if case == "dense" else "physical")
    if (archive_identity(Path(archive["root"])) != archive or offer != terminal["region"]
            or key != terminal["native_sha256"] or key != "sha256:" + file_sha(packet)
            or canonical_digest(native) != key or canonical_digest(terminal) != identity["terminal_sha256"]
            or identity["decision"] != "complete" or archived["route"] != "complete"):
        raise ValueError("Expected a completed same-packet, same-region saved control")
    binding = dict(archive=archive, offer=offer, native_sha256=key, terminal_sha256=identity["terminal_sha256"],
                   archived_control_sha256=pin)
    return native, binding, archived, terminal


def score(model, xy):
    result = model.calculate(xy)
    whitened = np.r_[result["residual"], np.maximum(0, -result["elevation"][model.keep]) / 2]
    return dict(loss=float(whitened @ whitened), rows=int(model.keep.sum()),
                residual_rms_hz=float(np.sqrt(np.mean(result["conditional_residual_hz"][model.keep]**2))))


def exact_candidate(scan, shadow, *, optimize):
    from leo.analysis.localization_v3 import discovery, position
    from leo.analysis.localization_v3.families import AnchoredFamilies
    from tools.pipeline_eval.variants.v5_core import cold_node

    xy = shadow["diagnostic_point"]
    state = discovery.zero_state(scan)
    state["beta"][:] = shadow["beta"]
    start = now()
    seed, state_stats = discovery.explore(scan, state, xy, "receiver_smooth", compact_update=False)
    anchors = AnchoredFamilies(scan, seed, "receiver_smooth", False, xy)
    node = cold_node(scan, dict(seed=seed, aliases=anchors.alias))
    labels = {r["candidate_index"] for r in node["seed"]["rows"]}
    rebuild = elapsed(start)
    start = now()
    exact = {}
    for name, fitted in ARMS.items():
        reference = np.zeros(len(labels))
        model = position.NormalPosition(scan, node, scan.radio_sigma_hz, fitted, reference=reference)
        readout = score(model, xy)
        if optimize:
            fit = position.fit(model, xy, iterations=48)
            point = np.asarray(fit["parameters"])
            reference = np.clip(model.state(point)[model.labels], -15., 15.)
            model = position.NormalPosition(scan, node, scan.radio_sigma_hz, fitted, reference=reference)
            final = position.fit(model, point, iterations=48)
            readout["fit"] = dict(east_north_km=final["parameters"], score=final["score"],
                                  latlon=scan.search_region.latlon(final["parameters"]),
                                  rf_rms_hz=final["residual_rms_hz"])
        exact[name] = readout
    return dict(signature=discovery.signature(node), phase_hypothesis_orbits=state_stats["candidate_hypotheses"],
                assigned_orbits=len(labels), rebuild=rebuild, exact=exact, exact_clocks=elapsed(start))


def recall(stock, counter, shortlist):
    stock_rows = {r[0]: tuple(r[1:]) for r in stock}
    matched = sum(r[0] in stock_rows and tuple(r[1:]) == stock_rows[r[0]] for r in counter)
    return dict(full_signature=matched == len(stock_rows) == len(counter), matching_owner_alias_rows=matched,
                original_rows=len(stock_rows), tested_rows=len(counter), sampled_original_winners=sum(
                    stock_rows[key][0] in candidates for key, candidates in shortlist.items()),
                sampled_rows=len(shortlist))


def compare(prepared, region, bound, archived, terminal):
    from blind_joint_finish import digest
    from tools.pipeline_eval.variants import v5_core

    share = run_path(str(SHARING))["shared_rank_preparation"]
    start = now()
    scan = v5_core.scan_context(prepared, region, digest(prepared["noise"]), bound, "previous")
    scan_clock = elapsed(start)
    start = now()
    scout = propose(scan)
    scout_clock = elapsed(start)
    accepted = scout["point"] is not None
    choice = exact_candidate(scan, scout, optimize=accepted) if "diagnostic_point" in scout else None
    control = rank_and_race(prepared, region, bound, True, share)
    expected = archived["route_details"]["cold"]
    actual = control["branch"]
    matched = fit_evidence({key: actual[key] for key in expected}) == fit_evidence(expected)
    if not matched or scout["catalogue"] != len(control["orbits"]):
        raise ValueError("Original cold winner or common full catalogue failed verification")

    charged = scan_clock["cpu_s"] + scout_clock["cpu_s"]
    if choice is not None:
        choice["recall"] = recall(actual["selected_signature"], choice["signature"], scout["shortlisted_labels"])
        if accepted:
            charged += choice["rebuild"]["cpu_s"] + choice["exact_clocks"]["cpu_s"]
    # The experiment never substitutes a speculative branch for the checked result.
    return dict(candidate=scout, candidate_cold=choice, clocks=dict(scan=scan_clock, scout=scout_clock,
                original_cold=control["cold"], charged_cpu_s=charged+control["cold"]["cpu_s"],
                pre_fallback_cpu_s=charged), original_branch=actual,
                original_ranked_signatures=[row["signature"] for row in control["records"]],
                archived_arms=terminal["arms"], archived_cold_match=matched,
                fallback="shadow_unqualified" if accepted else scout["abstain"])


def run(case, output):
    settings = host()
    publication, spec = configuration()
    from tools import algo08_position
    from tools.pipeline_eval.variants import v5_core

    native, binding, archived, terminal = source(case)
    library = Path(binding["archive"]["root"])
    offer = binding["offer"]
    original = algo08_position.solve
    evidence = {}

    class SavedColdFinished(Exception):
        pass

    def evaluate(prepared, region, bound, _stages, **_options):
        evidence.update(compare(prepared, region, bound, archived, terminal))
        raise SavedColdFinished()

    def observed(document, reader, assets, region):
        if (document is not native or reader.root != library or region.document() != offer
                or file_sha(assets / "tracks.json") != TRACK_ASSET_PIN):
            raise ValueError("Saved detector, installed graph, archive or offer changed")
        with patch.object(v5_core, "infer", evaluate):
            return original(document, reader, assets, region)

    with patch.object(algo08_position, "solve", observed):
        try:
            solve(publication, spec, native, library, offer)
        except SavedColdFinished:
            pass
    if not evidence:
        raise ValueError("The bounded cold trial did not reach the normal inference path")
    pins = {name: file_sha(HERE / name) for name in ("arc_doppler_start_trial.py", "arc_doppler_start.py",
                                                     "arc-doppler-start-protocol.md")}
    write(output, dict(case=case, host=settings, input=binding, pins=pins, **evidence))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", choices=tuple(SOURCES))
    parser.add_argument("output", type=Path)
    run(**vars(parser.parse_args()))
