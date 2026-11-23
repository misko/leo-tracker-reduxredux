"""Measure one genuine saved named final fit on the fast causal 0402 roster."""

import argparse
import gzip
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
if __name__ == "__main__":
    sys.path.insert(0, str(HERE))

from fragment_gate_cross_0402 import admission, build_pair, capture_named, compare_named_capture
from isolated_salvage_0402_trial import POLICY_PINS, worker as combined_worker
from named_survivor_fit import ARMS, arm_witness, binding, clock, now
from owner_loss_0402 import ARCHIVED, ARCHIVED_SHA, STAGED, request
from prospective_0402_solver import SETTINGS, checked, inspect, orbit_legends, verify_sources


WARM = Path("/dev/shm/leo-v3-isolated-salvage-0402-run01")
WARM_RECEIPT = "8ca92dd3cb30c2ea77565984c4d422894c8f63ee83d4b62bf31e0444d76a23bd"
WARM_NATIVE = "fdc6fd2b3c6c0eac6d1859ce748129bfb844a259040e2324f96bb09a7df5139f"
MODES = ("fixed", "named-cut")


def fixed_worker(root):
    import unified_short_bootstrap as entry

    publish = entry.publish_active
    witness = {}

    def configured(*args, **kwargs):
        with binding(witness):
            return publish(*args, **kwargs)

    with patch.object(entry, "publish_active", configured):
        combined_worker(root)
    from aperture_trial import write

    started = now()
    write(root / "likelihood-witness.json", witness)
    write(root / "witness-write-clock.json", clock(started))


def named_worker(root):
    import empty_bootstrap as boot
    from aperture_trial import archive_identity, write

    runtime = boot.load_runtime()
    job, _ = admission(boot.checked, archive_identity)
    root.mkdir()
    with patch.object(boot, "load_runtime", return_value=runtime):
        result = capture_named(job, root / "incomplete")
    from tools.pipeline_eval.variants import orbit_projector, v5_direct_cavity

    began = now()
    projector = orbit_projector.Projector(boot.RELEASE / "assets/projector.so")
    with v5_direct_cavity.numerical_bindings(projector):
        frame = build_pair(result["signed"])
        arms = {arm: arm_witness(frame["problems"][arm], frame["entries"], frame["powers"],
                                 frame["means"], frame["arms"][arm]) for arm in ARMS}
    signed = result.pop("signed")
    witness = dict(
        **result, qualification=signed["signed"]["selection"],
        signed=dict(arms={arm: {k: row[k] for k in ("endpoint_latlon", "RMS_hz")}
                          for arm, row in signed["arms"].items()}), signed_adopted=signed["signed"]["accepted"],
        likelihood=dict(model=frame["model"], arms=arms), likelihood_witness_clock=clock(began),
    )
    if list(root.glob("incomplete/**/terminal.json")):
        raise ValueError("This ground-truth witness stops before standard publication")
    write(root / "named-witness.json", witness)


def launch(root):
    from aperture_trial import RELEASE, write
    from dense_geographic_trial import host
    from full_short_physical import environment
    from short_raw_diagnostic import measure

    machine = host()
    job, req = request()
    verify_sources(checked, POLICY_PINS)
    if subprocess.check_output(["findmnt", "-no", "FSTYPE", "-T", root.parent], text=True).strip() != "tmpfs":
        raise ValueError("Use one fresh private tmpfs")
    root.mkdir()
    (root / "tmp").mkdir()
    env = environment(STAGED)
    env["TMPDIR"] = str(root / "tmp")
    sources = ("final-fit-0402-protocol.md", "named_survivor_fit.py", Path(__file__).name,
               "isolated_salvage.py", "fragment_gate_cross_0402.py", "blind_joint_signed.py")
    write(root / "launch.json", dict(machine=machine, request_sha256=sha256(job.read_bytes()).hexdigest(),
          native_sha256=req["native_sha256"], archive=req["local_archive"]["snapshots_sha256"], order=MODES,
          source_sha256={name: sha256((HERE / name).read_bytes()).hexdigest() for name in sources}))
    for mode in MODES:
        target = root / mode
        command = [RELEASE / "venv/bin/python", "-IB", __file__, mode, target]
        timing = measure(command, env, target)
        write(root / f"{mode}-clock.json", dict(timing=timing, command=list(map(str, command))))
        if timing["exit_code"]:
            raise RuntimeError(f"{mode} failed. Original timing and child logs were sealed.")


def difference(left, right, keys):
    common = left.keys() & right.keys()
    return dict(
        left_only=sorted(left.keys() - common), right_only=sorted(right.keys() - common),
        common=len(common), changed={key: sorted(name for name in common if left[name][key] != right[name][key])
                                     for key in keys},
    )


def compare_arms(named, fixed):
    """Compare original global layouts and each actually active likelihood input."""
    active_n = {k: v for k, v in named["curves"].items() if v["ids"]}
    active_f = {k: v for k, v in fixed["curves"].items() if v["ids"]}
    active_fields = ("norad", "alias", "ids", "power", "clock_cfo_rf", "sigma", "hardware", "smooth")
    linear_fields = ("ids", "norad", "alias", "cross_receiver", "clock_cfo_rf", "lifted_variance")
    phase_fields = ("active", "orbital_modes", "phase_width", "signed_prior_mean", "phase_reference",
                    "posterior_phase", "causal_sky", "mode_geometry")
    numeric = ("phase_width", "signed_prior_mean", "phase_reference", "posterior_phase")
    a, b = named["families"], fixed["families"]
    active = [key for key in sorted(a.keys() & b.keys()) if a[key]["active"] and b[key]["active"]]
    changes = {key: {tag: [a[key][tag], b[key][tag]] for tag in numeric if a[key][tag] != b[key][tag]}
               for key in active}
    columns = ("phase_labels", "orbital_mode_families", "likelihood_columns", "total_curve_slots", "normalization")
    return dict(active_curved=difference(active_n, active_f, active_fields),
                nominal_curved=difference(named["curves"], fixed["curves"], ("norad", "alias", "ids")),
                predictive=difference(named["predictive"], fixed["predictive"], linear_fields),
                families=difference(a, b, phase_fields), active_family_differences={
                    key: values for key, values in changes.items() if values},
                active_family_count=len(active), nominal_columns={key: [named[key], fixed[key]] for key in columns},
                same_noise_history_clock={name: named[name] == fixed[name] for name in (
                    "original_noise", "original_previous_tle", "timing_origin_ns")},
                unshared_family_parameters={
                    mode: {key: target[key] for key in sorted(target.keys() - other.keys())}
                    for mode, (target, other) in (("named", (a, b)), ("fixed", (b, a)))},
                maximum_active_delta={tag: max((abs(a[key][tag]-b[key][tag]) for key in active), default=0.)
                                      for tag in numeric})


def evaluate(root, destination):
    from aperture_trial import read, write
    from tools.pipeline_eval.scoring import distance_km
    from triage_bounds import REFERENCE, REFERENCE_SHA256

    _, req = request()
    clocks = {mode: read(root / f"{mode}-clock.json") for mode in MODES}
    if any(row["timing"]["exit_code"] for row in clocks.values()):
        raise ValueError("The two fresh process clocks must seal before scoring")
    previous = json.loads(checked(WARM / "result.json", WARM_RECEIPT))
    warm = json.loads(checked(WARM / "candidate/joint-research-receipt.json", WARM_NATIVE))
    old = json.loads(gzip.decompress(checked(ARCHIVED, ARCHIVED_SHA)))
    path = root / "fixed"
    trace = read(path / SETTINGS["audit_name"])
    actual = inspect(path, "cumulative", trace["receipt"], clocks["fixed"]["timing"], req, **SETTINGS)
    named = read(root / "named-cut/named-witness.json")
    fresh = read(path / "likelihood-witness.json")
    parity = compare_named_capture(named, old)
    stock = old["runs"]["stock"]
    if actual["science"]["receipt"]["decision"] != "complete" or not named["signed_adopted"]:
        raise ValueError("Expected the earlier enrolled fixed roster and exact signed named witness")
    keep = {arm: dict(
        count=len(actual["selected_rows"][arm]), named=actual["selected_rows"][arm] == named["owners"][arm],
        earlier_candidate=actual["selected_rows"][arm] == warm["selected_rows"][arm]) for arm in ARMS}
    ref, = (row["reference"] for row in json.loads(checked(REFERENCE, REFERENCE_SHA256))["cases"]
            if row["dataset_label"] == "DS30-0402" and row["authority_eligible"] and row["sealed_metadata_digests_verified"])
    survey = [ref["latitude_deg"], ref["longitude_deg"]]
    terminal = dict(named=stock["terminal"], warm=previous["publication"]["terminal"], fixed=actual["terminal"])
    error = {name: {arm: distance_km(survey, doc["arms"][arm]["latlon"]) for arm in ARMS}
             for name, doc in terminal.items()}
    displacement = {name: {arm: distance_km(terminal[name]["arms"][arm]["latlon"], actual["terminal"]["arms"][arm]["latlon"])
                            for arm in ARMS} for name in ("named", "warm")}
    details = actual["route_details"]
    inputs = {arm: compare_arms(named["likelihood"]["arms"][arm], fresh["arms"][arm]) for arm in ARMS}
    picture = json.loads(json.dumps(actual["figures"]))
    figures = {label: {name: {key: value == ref[name][key] for key, value in body.items()}
                       for name, body in picture.items()}
               for label, ref in (("named", stock["figures"]), ("warm", previous["publication"]["figures"]))}
    write(destination, dict(
        launch=read(root / "launch.json"), clocks=clocks, named_parity=parity, ownership=keep,
        witness_sha256={key: sha256(file.read_bytes()).hexdigest() for key, file in (
            ("candidate", path / "likelihood-witness.json"), ("named", root / "named-cut/named-witness.json"))},
        witness_overhead_write=read(path / "witness-write-clock.json"),
        named_stage={key: named[key] for key in ("to_cut", "through_witness", "likelihood_witness_clock")},
        same_model=named["likelihood"]["model"] == fresh["model"],
        same_signed_qualification=named["qualification"] == details["signed"]["selection"],
        likelihood_comparison=inputs, terminal=terminal, horizontal_error_km=error, displacement_km=displacement,
        fits={mode: {arm: content["arms"][arm]["fit"] for arm in ARMS}
              for mode, content in (("named", named["likelihood"]), ("fixed", fresh))},
        scientific_grid=actual["sidecars"], media=picture, media_equality=figures,
        legends=orbit_legends(path, actual), candidate_solve=actual["worker"]["solve"],
        signed_fit=details["named_survivor_fit"], signed_total=details["signed_total_clocks"],
        signed_qualification=details["signed_qualify_clocks"], signed_prior=details["signed_prior_clocks"],
        earlier_warm_fit=warm["route_details"]["warm_signed_fit"], earlier_check=warm["route_details"]["signed_total_clocks"],
    ))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    for name in ("launch", "fixed", "named-cut", "evaluate"):
        command = sub.add_parser(name)
        command.add_argument("root", type=Path)
        if name == "evaluate":
            command.add_argument("destination", type=Path)
    options = vars(parser.parse_args())
    action = options.pop("action")
    {"launch": launch, "fixed": fixed_worker, "named-cut": named_worker, "evaluate": evaluate}[action](**options)
