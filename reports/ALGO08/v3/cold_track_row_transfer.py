"""Qualify the explicit full-short cold row option on three archived saved offers."""

import argparse
from math import isclose
from pathlib import Path
from runpy import run_path

from aperture_trial import ARMS, archive_identity, configuration, inputs, read, write
from cold_track_row_trial import REPLAY_PIN, fit_evidence
from dense_full_short_crossover import CASE, HERE, file_sha
from dense_geographic_trial import host
from proof_rank_short_transfer import receipt, saved


SMALL_CONTROLS = {
    "physical": "032fa7ed291639e816f733af1589c12872b4f1a6340648e0307d129988b229cc",
    "south-far": "f7842cbaac7d7de050336b177cb72527f6d2cb3af2f62abc23019235aa6578fc",
}
SMALL = ("physical", "south-far")
PREVIOUS = Path("/var/tmp/leo-v3-dense-full-short-crossover")
RAW = Path("/var/tmp/leo-full-short-dense-DS30-0008")
GEOGRAPHIC = Path("/var/tmp/leo-dense-short-pins.0zaX7eSH/geographic.so")
DENSE = Path("/var/tmp/leo-v3-dense-full-short-crossover-results/replay.json")
SCIENCE_KEYS = ("decision", "pair_passes", "support", "salvage_shortlists", "finish", "signed", "exterior")


def dense_inputs(binary):
    if file_sha(DENSE) != REPLAY_PIN:
        raise ValueError("The archived dense complete installed-graph control changed")
    control = read(DENSE)
    code = PREVIOUS / "reports/ALGO08/v3/dense_full_short_crossover.py"
    if file_sha(code) != control["code"][code.name]:
        raise ValueError("The archived dense source verifier changed")
    verify = run_path(str(code))["raw_candidate"]
    original, _, offer, _, identity = inputs(CASE)
    _, source = verify(RAW / "publication", RAW / "process.json", binary, original, identity)
    binding = source["binding"]
    command = binding["command"]
    packet, = (RAW / "publication/fast-scan-automatic-work").glob("*/detections.json")
    return (Path(command[command.index("--recording")+1]), identity["archive"], Path(binding["region"]), packet,
            source["raw_native_sha256"], offer), control


def small_inputs(case):
    from full_short_graph_transfer import inputs as graph_inputs

    if case == "physical":
        saved(case)
    else:
        receipt("full-short-south.json")
    archived = Path(f"/var/tmp/leo-short-graph-20261123-{case}/joint-research-receipt.json")
    if file_sha(archived) != SMALL_CONTROLS[case]:
        raise ValueError("The archived small installed-graph control changed")
    return graph_inputs(case), read(archived)


def same_proof(left, right):
    if isinstance(left, dict) and isinstance(right, dict):
        return left.keys() == right.keys() and all(same_proof(x, right[key]) for key, x in left.items())
    if isinstance(left, list) and isinstance(right, list):
        return len(left) == len(right) and all(same_proof(x, y) for x, y in zip(left, right, strict=True))
    if type(left) is float and type(right) is float:
        return isclose(left, right, rel_tol=0, abs_tol=1e-8)
    return left == right


def same_route(left, right):
    if left is None or right is None:
        return left is right
    return (all(left[key] == right[key] for key in SCIENCE_KEYS)
            and fit_evidence(left["cold"]) == fit_evidence(right["cold"]))


def compare(case, root, pin, proof, report, control):
    from leo.contracts.digests import canonical_digest
    from leo.contracts.fast_standard_analysis import PLOTS
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore

    store = FastStandardAnalysisStore(root)
    receipt = report["receipt"]
    identifier = receipt["run_id"]
    terminal = read(root / "fast-scan-automatic-work" / identifier / "terminal.json")
    detail = store.detail(identifier)
    evidence = report["evidence"]
    images = evidence["images"]
    cold = report["solve"]["cold_track_rows"]
    result = dict(terminal_bound=(terminal["native_sha256"] == pin
                  and canonical_digest(terminal) == receipt["terminal_sha256"] == detail["terminal_sha256"]),
                  genuinely_reused=(cold["shared_ranks"] == int(case != "south-far") and cold["ordinary_ranks"] == 0
                  and (cold.get("reused_requests", 0) > 0) == (case != "south-far")))
    source = None
    if case != "dense":
        expected = control["receipt"]
        small_root = Path(f"/var/tmp/leo-short-graph-20261123-{case}")
        source = read(small_root / "fast-scan-automatic-work" / expected["run_id"] / "terminal.json")
        if canonical_digest(source) != expected["terminal_sha256"]:
            raise ValueError("The comparable small terminal changed")
        result.update(terminal=terminal == source, decision=receipt["decision"] == expected["decision"],
                      owners=report["selected_rows"] == control["selected_rows"],
                      path_grid={k: evidence.get(k) for k in ("path", "grid")} == {
                          k: control["evidence"].get(k) for k in ("path", "grid")},
                      proof=same_proof(proof, control["early_regional"][0]["result"]),
                      route=report["route"] == control["route"] and same_route(report["route_details"], control["route_details"]),
                      image_pixels=all((row["size"], row["rgba_sha256"]) == (
                          control["evidence"]["images"][name]["size"], control["evidence"]["images"][name]["rgba_sha256"])
                          for name, row in images.items()) and images.keys() == control["evidence"]["images"].keys())
    if case == "south-far":
        result["withheld_before_fit"] = (receipt["decision"] == "withheld" and not images
                                         and report["route_details"] is None and proof["probes_evaluated"] == 96
                                         and proof["complete"] and proof["would_withhold"])
    elif case == "dense":
        grid = store.position_grid(identifier)
        path = store.position_path(identifier)
        science = {name: canonical_digest({k: v for k, v in doc.items() if k not in ("binding", "elapsed_seconds")})
                   for name, doc in (("path", path), ("grid", grid))}
        owner_counts = {arm: detail["arms"][arm]["associated_points"] for arm in ARMS}
        owner_digests = {arm: detail["arms"][arm]["owner_sha256"] for arm in ARMS}
        result.update(decision=receipt["decision"] == "complete" and control["status"] == "ok"
                      and terminal["reason"] == control["reason"],
                      arms=terminal["arms"] == control["arms"],
                      owners=(report["selected_rows"] == control["selected_rows"]
                              and owner_counts == control["associated"] and owner_digests == control["owners"]),
                      path_grid=(science == control["science"] and {
                          k: v for k, v in grid.items() if k not in ("binding", "elapsed_seconds")} == control["grid"]),
                      proof=proof == control["regional"][0]["result"],
                      route=(terminal["orbit_policy"] == control["orbit_policy"]
                             and same_route(report["route_details"], control["attempts"][0])),
                      grid_replay=(report["solve"]["objective_replay"] == control["objective_replay"]
                                   and report["solve"]["grid_points"] == control["grid_points"] == 179
                                   and report["solve"]["grid_complete"] is True),
                      images_valid=tuple(images) == tuple(PLOTS))
    return result, dict(terminal=terminal, source_small_terminal=source,
                        small_png_byte_identity=images == control["evidence"]["images"] if case in SMALL else None)


def run(case, output, binary, screen):
    machine = host()
    configuration()
    from full_short_run import main

    if case == "dense":
        if not all(read(screen / name / "cold-track-transfer.json")["passed"] for name in SMALL):
            raise ValueError("Both earlier weak controls must pass scientific parity before dense")
        chosen, control = dense_inputs(binary)
    else:
        chosen, control = small_inputs(case)
    recording, archive, region, packet, pin, offer = chosen
    if file_sha(packet) != pin.removeprefix("sha256:") or archive_identity(Path(archive["root"])) != archive:
        raise ValueError("The selected saved packet or causal archive changed")
    parameters = dict(recording=recording, archive=archive["root"], region=region, output=output, saved=packet,
                      saved_digest=pin, geographic_library=binary, track_graph="installed")
    main([item for name, value in parameters.items() for item in ("--"+name.replace("_", "-"), str(value))]
         + ["--reuse-cold-track-rows"])
    report = read(output / "joint-research-receipt.json")
    proof, = report["early_regional"]
    matches, detail = compare(case, output, pin, proof["result"], report, control)
    matches.update(binding=report["saved_digest"] == pin and report["receipt"]["region"] == offer
                   and archive_identity(Path(archive["root"])) == archive)
    passed = all(matches.values())
    scores = None
    if passed and case == "dense":
        scores = read(HERE / "measurements/dense-full-short-crossover-summary.json")["runs"]["short_installed"]["arms"]
    if passed and case == "physical":
        scores = read(receipt("full-short-graph-transfer.json"))[case]["score"]["arms"]
    write(output / "cold-track-transfer.json", dict(case=case, passed=passed, checks=matches, machine=machine,
          input_sha256=pin, archive=archive, offer=offer, solve=report["solve"], control_solve=control["solve"],
          proof=proof, images=report["evidence"]["images"], scores_from_identical_endpoints=scores,
          publication_cpu_s=report["publication_cpu_s"], publication_elapsed_s=report["publication_elapsed_s"],
          control_publication_cpu_s=control.get("publication_cpu_s"),
          receipts={name: file_sha(output / name) for name in ("full-short-recipe.json", "joint-research-receipt.json")},
          source_sha256=dict(report["source_sha256"], **{Path(__file__).name: file_sha(Path(__file__))}), **detail))
    if not passed:
        raise ValueError(f"Saved publication science mismatch for {case}: {matches}")


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("case", choices=(*SMALL, "dense"))
    cli.add_argument("output", type=Path)
    cli.add_argument("--binary", default=GEOGRAPHIC, type=Path)
    cli.add_argument("--screen", type=Path)
    run(**vars(cli.parse_args()))
