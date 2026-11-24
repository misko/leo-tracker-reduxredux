"""Run and score one guarded saved successor against both sealed DS30-0289 controls."""

import argparse
from contextlib import ExitStack
from functools import partial
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(HERE), str(ROOT)]
STAGED = Path("/dev/shm/leo-v3-nomination-handoff-0289-local01")
CONTROL = STAGED.with_name(STAGED.name + "-comparison.json")
CONTROL_SHA = "bef06fcc3d7c52d4268485e8ee211f45a30710e62ea7a38a8f8a58cef2eb3973"
JOB_SHA = "52a81b06b6a876c87a656b36e59c8a4ed4c995496c8ea6eba139b4dd852bfd48"
SEAL_SHA = "4977e485fed90a7000aceb530f0d91e28967ea4fc7b10423e18b675a13f60aa2"
PROJECTION = Path("/dev/shm/leo-grid-feature-projection-02/native-map.so")
MAP_OWNER = Path("/dev/shm/leo-v3-exact-grid-0138-active01")
MAP_ATTESTATION = "71394d999de87401eb130a01680742f34e797022f448efd3195688b2311df6ba"
TEMPLATE = MAP_OWNER / "template.so"
TEMPLATE_SHA = "d55bb5bbcd33de7a610221558c3727d86e827279c56b09d9142524afd4e4aa0b"
CASE = "DS30-0289"
ARMS = ("c0", "fitted_c")


def read(path):
    return json.loads(path.read_bytes())


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def source_pins():
    from nomination_handoff_0255_publication import remediation_pins

    return remediation_pins() | {
        str((HERE/name).relative_to(ROOT)): digest(HERE/name) for name in (
            "combined-successor-0289-protocol.md", "combined_successor.py", Path(__file__).name,
            "two_centre_seeds.py", "grid_design_template.py", "grid_design_template.c",
            "grid_feature_projection.py", "grid_feature_projection.c", "prepared_exterior.py")}


def admitted_libraries():
    from empty_bootstrap import checked
    from exact_named_route import resident_path
    from grid_feature_projection import LIBRARY_SHA

    template = json.loads(checked(resident_path(MAP_OWNER/"grid-binding.json"), MAP_ATTESTATION))
    # The C source built template.so. The Python composition helper moved
    # out of exact_grid_0138.py later and has its own current source pin.
    if (template["template_sha256"] != TEMPLATE_SHA
            or any(template["sources"][name] != digest(HERE/name)
                   for name in ("grid_design_template.c", "grid_feature_projection.py"))):
        raise ValueError("The source that built the qualified grid kernel changed")
    pins = {str(PROJECTION): LIBRARY_SHA, str(TEMPLATE): TEMPLATE_SHA}
    for path, expected in pins.items():
        checked(resident_path(Path(path)), expected)
    return pins


def worker(root):
    import empty_bootstrap as boot
    from aperture_trial import write
    import clean_saved_publication as generic
    from combined_successor import exact_grid, successor_binding
    from solver_exception_live import worker as guarded

    book = read(root/"admission.json")
    if book["sources"] != source_pins() or book["job_sha256"] != JOB_SHA or book["libraries"] != admitted_libraries():
        raise ValueError("The admitted successor implementation changed")
    original, audit = boot.load_runtime, {}
    routed = root/"routed"
    try:
        with ExitStack() as scope:
            def load():
                result = original()
                scope.enter_context(exact_grid(PROJECTION, TEMPLATE, audit))
                return result

            scope.enter_context(patch.object(boot, "load_runtime", load))
            scope.enter_context(patch.object(generic, "routed", partial(generic.routed, route_binding=successor_binding)))
            guarded(STAGED/"job.json", JOB_SHA, routed)
    finally:
        write(routed/"combined-grid.json", audit)


def prepare(root):
    import empty_bootstrap as boot
    from aperture_trial import write
    from clean_saved_publication import load_job
    from dense_geographic_trial import host
    from exact_named_route import checked_catalogue, resident_path
    from leo.contracts.digests import canonical_digest
    from leo.operations.tle_archive import TleArchiveReader
    from nomination_handoff_0255_publication import remediation_pins
    from visit_frame_raw_0016 import resident

    started = boot.now()
    if root.exists() or resident_path(root.parent) != Path("/dev/shm"):
        raise ValueError("Choose a fresh private tmpfs output")
    prior = json.loads(boot.checked(resident_path(CONTROL), CONTROL_SHA))
    old = prior["admission"]
    machine = host()
    if (prior["case"] != CASE or old["machine"] != machine or old["job_sha256"] != JOB_SHA
            or old["source_pins"] != remediation_pins() or old["portable"] is not None
            or prior["prediction_seal_sha256"] != SEAL_SHA):
        raise ValueError("The original guarded worker, machine or saved scope changed")
    boot.checked(resident_path(STAGED/"prediction-seal.json"), SEAL_SHA)
    bound, req = load_job(STAGED/"job.json", JOB_SHA)
    _, refs = checked_catalogue(bound, req, TleArchiveReader, canonical_digest)
    libs = admitted_libraries()
    admission = resident([*(ref.path for ref in refs), *map(Path, bound["packets"]), *map(Path, libs)])
    root.mkdir(mode=0o700)
    for name in ("fonts", "tmp", "routed"):
        (root/name).mkdir()
    for path in (STAGED/"fonts").glob("fontlist-*.json"):
        os.link(resident_path(path), root/"fonts"/path.name)
    write(root/"routed/binding.json", {"input": bound})
    argv = ["/usr/bin/timeout", "--kill-after=2s", "95s", str(boot.RELEASE/"venv/bin/python"), "-IB",
            str(Path(__file__).resolve()), "worker", str(root)]
    head = subprocess.check_output(
        ["git", "-c", f"safe.directory={ROOT}", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip()
    write(root/"admission.json", dict(case=CASE, command=argv, machine=machine, commit=head, sources=source_pins(),
          job_sha256=JOB_SHA, libraries=libs, prior_controls_sha256=CONTROL_SHA, prior_prediction_sha256=SEAL_SHA,
          resident=admission, causal_snapshots=len(refs), original_inputs=old["original_inputs"],
          setup=boot.clock(started), causal_election=False, planned_children=1))
    return argv


def launch(root):
    from aperture_trial import write
    from clean_saved_0169_trial import output_seal
    from full_short_physical import environment
    from short_raw_diagnostic import measure

    argv = prepare(root)
    env = environment(root) | {"TMPDIR": str(root/"tmp"), "XDG_CACHE_HOME": str(root/"tmp")}
    write(root/"routed/clock.json", measure(argv, env, root/"routed/candidate"))
    write(root/"prediction-seal.json", output_seal(root))


def score(root):
    from aperture_trial import write
    from clean_saved_0169_trial import output_seal
    from clean_saved_publication import load_job
    from empty_bootstrap import checked
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
    from prospective_0316_solver import inspect, owner_delta
    from tools.pipeline_eval.scoring import distance_km
    from unseen_saved_holdout_score import REFERENCE_PIN

    book, prior = read(root/"admission.json"), json.loads(checked(CONTROL, CONTROL_SHA))
    if (read(root/"prediction-seal.json") != output_seal(root)
            or book["sources"] != source_pins() or book["case"] != CASE):
        raise ValueError("The sealed predictions or input study changed")
    routed = root/"routed"
    paid = read(routed/"clock.json")
    result = dict(admission=book, clock=paid, controls={mode: job["clock"] for mode, job in prior["jobs"].items()},
                  original_waveform_reads=0, saved_children=1, prediction_seal_sha256=digest(root/"prediction-seal.json"))
    if paid["exit_code"]:
        write(root/"result.json", result | dict(qualified=False, decision="failed"))
        return
    bound, req = load_job(STAGED/"job.json", JOB_SHA)
    output = routed/"candidate"
    receipt = read(output/"worker.json")["receipt"]
    original = prior["jobs"]["routed"]["publication"]
    installed = prior["jobs"]["installed"]["publication"]
    proposed = inspect(output, "successor", receipt, paid, req, native_sha=req["native_sha256"],
                       windows=bound["issued"], admitted=bound["admitted"], audit_name="worker.json")
    if any(proposed["terminal"][key] != original["terminal"][key] for key in ("session_id", "region", "native_sha256")):
        raise ValueError("The outcome did not retain the genuine native input and operator region")
    reference = subprocess.check_output(
        ["git", "-c", f"safe.directory={ROOT}", "-C", str(ROOT), "show",
         "2d0ad2dfd:reports/2026_11_21_ds30_full/reference-audit.json"])
    if sha256(reference).hexdigest() != REFERENCE_PIN:
        raise ValueError("The qualified reference changed")
    site, = (row["reference"] for row in json.loads(reference)["cases"]
             if row["dataset_label"] == CASE and row["authority_eligible"] and row["sealed_metadata_digests_verified"])
    truth = [site[name] for name in ("latitude_deg", "longitude_deg")]

    def position_arm(publication, arm):
        value = publication["terminal"]["arms"][arm]
        coordinates = value["latlon"]
        return dict(endpoint=coordinates, horizontal_error_m=1000 * distance_km(truth, coordinates) if coordinates else None,
                    conditional_rf_rms_hz=value.get("rf_rms_hz"),
                    all_owned_rf_rms_hz=None,
                    owners=len(publication["selected_rows"].get(arm, [])))

    science = {mode: {arm: position_arm(pub, arm) for arm in ARMS}
               for mode, pub in (("installed", installed), ("routed", original), ("successor", proposed))}
    earlier_store = FastStandardAnalysisStore(STAGED/"routed/candidate")
    prior_detail = earlier_store.detail(original["science"]["receipt"]["run_id"])
    for arm in ARMS:
        science["routed"][arm]["all_owned_rf_rms_hz"] = prior_detail["arms"][arm]["residual_rms_hz"]
    if receipt["decision"] == "complete":
        store = FastStandardAnalysisStore(output)
        detail = store.detail(receipt["run_id"])
        grid = store.position_grid(receipt["run_id"])
        if not grid["matched_c_grid"] or len(grid["points"]) != 179:
            raise ValueError("A published fix must retain the full matched grid")
        for arm in ARMS:
            science["successor"][arm]["all_owned_rf_rms_hz"] = detail["arms"][arm]["residual_rms_hz"]
    latest, = read(routed/"risk-route.json")["solves"]
    earlier, = prior["candidate_traces"]["risk-route.json"]["solves"]
    fit = latest["lean_attempts"][0] if latest["lean_attempts"] else {}
    old_fit, = earlier["lean_attempts"]
    geography = {key: fit.get("exterior", {}).get(key) for key in ("evaluated", "would_withhold", "bound_arms")}
    old_geography = {key: old_fit.get("exterior", {}).get(key) for key in geography}
    errors = {arm: None if row["horizontal_error_m"] is None else
        row["horizontal_error_m"]-science["routed"][arm]["horizontal_error_m"] for arm, row in science["successor"].items()}
    qualified = (receipt["decision"] == "complete" and geography == old_geography
                 and all(value is not None and value <= 250 for value in errors.values()))
    owners = {mode: {arm: owner_delta(pub["selected_rows"].get(arm, []), proposed["selected_rows"].get(arm, []))
                    for arm in ARMS} for mode, pub in (("installed", installed), ("routed", original))}
    images = {name: value == original["figures"].get(name) for name, value in proposed["figures"].items()}
    sides = {name: value["scientific_sha256"] == original["sidecars"][name]["scientific_sha256"]
             for name, value in proposed["sidecars"].items()}
    proposed.pop("selected_rows")
    traces = {name: read(routed/name) for name in ("combined-grid.json", "live-corner.json", "render-usage.json")}
    write(root/"result.json", result | dict(
        decision=receipt["decision"], installed_decision=installed["terminal"]["decision"], qualified=qualified,
        publication=proposed, science=science, reference_sha256=REFERENCE_PIN,
        candidate_minus_routed_horizontal_m=errors, owner_changes=owners, images_equal=images, sidecars_equal=sides,
        exact_terminal=proposed["terminal"] == original["terminal"], geography=geography, earlier_geography=old_geography,
        route=latest, earlier_route=earlier, traces=traces, ports=read(output/"ports.json"),
        publication_clocks=read(output/"joint-research-receipt.json")["solve"],
        prior_publication_clocks=prior["publication_clocks"]))


if __name__ == "__main__":
    from history_risk_weak_physical import deny_original

    sys.addaudithook(deny_original)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("launch", "worker", "score"))
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    {"launch": launch, "worker": worker, "score": score}[args.action](args.root)
