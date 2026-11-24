"""Verify the saved combined publication and reduce controls on the same signed packet."""

import argparse
from pathlib import Path

from residual_portable_saved import committed_orbits, controls, digest, read, require_active, seal, source_pins


PORT_ROSTER = {
    "0138": "/dev/shm/leo-v3-history-risk-0138-pair02/routed/candidate/ports.json",
    "0160": "/dev/shm/leo-v3-history-risk-0160-01/candidate/ports.json",
    "0169": "/dev/shm/leo-v3-history-risk-0169-01/candidate/ports.json",
    "0316": "/dev/shm/leo-v3-history-risk-0316-01/candidate/ports.json",
    "0374": "/dev/shm/leo-v3-history-risk-0374-01/candidate/ports.json",
    "0402": "/dev/shm/leo-v3-history-risk-0402-pair01-routed/candidate/ports.json",
}


def cohort_ports(path_roster, expected):
    from exact_named_route import resident_path

    result = {}
    for case, leaf in path_roster.items():
        path = resident_path(Path(leaf))
        portable, = read(path)["portable"]["transfers"]
        if portable["sha256"] != expected or portable["compatibility"]["fallback"] or portable["loading"]["fallback"]:
            raise ValueError(f"Saved control does not use the same earlier artifact: DS30-{case}")
        counts = portable["counts"]
        result[case] = dict(path=leaf, sha256=digest(path), hits=counts["sidecar_hit_bodies"],
                            rows=counts["sidecar_hit_rows"], cold=counts["cold_bodies"])
    return result


def time_prices(current, prior, named, setup, admission_ns, prior_admission_ns, build):
    out = {}
    for measure, stamp in (("elapsed_s", "elapsed_ns"), ("cpu_s", "cpu_ns")):
        admitted = current[measure] + setup[measure] + admission_ns[stamp]/1e9
        old_admitted = prior[measure] + prior_admission_ns[stamp]/1e9
        out[measure] = dict(child=current[measure], prior_child=prior[measure], named=named[measure],
                            admission=admitted-current[measure], prepared=admitted, prior_prepared=old_admitted,
                            vs_named=named[measure]/admitted, vs_prior_ready=old_admitted/admitted,
                            target_1_6=named[measure]/1.6, remaining_to_1_6=admitted-named[measure]/1.6,
                            earlier_producer=build[measure], first_use_with_producer=admitted+build[measure])
    return out


def score(case, root):
    from aperture_trial import write
    from exact_named_cairo_media import verify_publication
    from exact_named_route_score import parity
    from held_adaptive_0160_score import verified
    from history_risk_cairo_physical import clean
    from history_risk_0169_input import STOCK_WORKER
    from history_risk_route_trial import request_binding

    admission = read(root/"outer-admission.json")
    if admission["pins"] != source_pins(case) or read(root/"prediction-seal.json") != seal(root):
        raise ValueError("Require unchanged preflight and publication evidence")
    baseline, previous = controls(case)
    binding, request = request_binding(case)
    bound = read(root/"binding.json")
    if bound["input"] != admission["scope"] or bound["input"] != binding:
        raise ValueError("The original signed packet, region, cutoff or archive differs")
    clock = read(root/"clock.json")
    new_root, old_root = root/"candidate", baseline/"candidate"
    new = verified(new_root, clock, "worker.json", request)
    old = verified(old_root, previous["clock.json"], "worker.json", request)
    named_clock = previous["result.json"]["archive_stock_clock"]
    named = verified(Path(binding["stage"])/"stock", named_clock, STOCK_WORKER, request)
    checks, sides = verify_publication(old, new, old_root, new_root)
    stock_checks = parity(named, new)
    stock_checks.pop("eight_pngs")
    if not all(stock_checks.values()) or clean(read(root/"risk-route.json")) != clean(read(baseline/"risk-route.json")):
        raise ValueError("The fitted science and numerical route must match both ordinary comparisons")

    worker, replay = (read(root/f"{name}.json") for name in ("render", "replay"))
    if worker["scene_sha256"] != replay["source_scene_sha256"] or worker["sources"] != admission["pins"]:
        raise ValueError("The independently tested render scene must be from the single timed publication")
    require_active(worker["work"])
    require_active(replay["work"])
    old_figures, live = (record["products"]["images"] for record in (old, new))
    identical = committed_orbits(old_figures, live, replay["hashes"])
    ports = read(new_root/"ports.json")
    original_port = previous["candidate/ports.json"]["portable"]
    if (clean(ports["portable"]) != clean(original_port)
            or tuple(ports["png"][key] for key in ("verified", "reused", "fallbacks")) != (8, 8, 0)):
        raise ValueError("Keep original portable and cold body use and verify all eight PNGs")
    charged = time_prices(clock, previous["clock.json"], named_clock, admission["checks"],
                          read(root/"route-binding.json")["preflight"], previous["route-binding.json"]["preflight"],
                          admission["producer_clock"])
    scientific = {model: data["science"] for model, data in (("named", named), ("previous", old), ("candidate", new))}
    write(root/"result.json", dict(case=request["case"], qualified=True, science=scientific, admission=admission,
          measured=clock, clocks=charged, checks=dict(routed=checks, named=stock_checks),
          geography=previous["result.json"]["scientific"], ordered_owner_counts={arm: len(rows) for arm, rows in new["rows"].items()},
          owner_digests=new["science"]["owners"], products=new["products"], sidecars=sides, grid_points=new["sample"]["evaluated_points"],
          same_original_title_from_ordinary_replay=True, image_encoded_parity=identical, waveform_reads=0, backing_reads=0,
          live_renderer=worker, render_replay=replay, solve={"candidate": new["trace"]["solve"], "previous": old["trace"]["solve"]},
          orbit_index=ports["portable"], previous_orbit_index=original_port,
          existing_same_index=cohort_ports(PORT_ROSTER, admission["producer"]["artifact_sha256"]),
          prediction_sha256=digest(root/"prediction-seal.json")))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case")
    parser.add_argument("root", type=Path)
    options = parser.parse_args()
    score(options.case, options.root)
