"""Run or independently score the frozen full-aperture primary transfer."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
from resource import RUSAGE_CHILDREN, getrusage
from shutil import copytree
import subprocess


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
CASE = "DS30-0016"
CHART = Path("/dev/shm/leo-v3-integrated-original-03") / CASE
STOCK = Path("/dev/shm/leo-v3-stock-raw-repeat-DS30-0016-score01.json")
STAGE = Path("/dev/shm/leo-v3-guarded-selective-0016-stage01")
PINS = {
    CHART / "admission.json": "df4f56b294b4a8542565d79629088f812b73a3064574dc36a0288a539ab76c82",
    CHART / "prediction-seal.json": "08d3d3a68102e3d57808ee576154aa95fd0d7ed6378974d1d3c6dd08f4ece31f",
    CHART / "result.json": "24fde18f18a3670fd6590ef9f767c6a3b63c068b1b7e4d012ed822128f418e46",
    STOCK: "68803c12437fe159278ca31183e9e1a6632e601310eead70f0be71a10e358648",
    STAGE / "staging.json": "daaffec8a4e8d944db2989c108b547ee81ce38cb53b41344de38617d9a2a139a",
}
CHANGED = {"exact_named_raw.py", "integrated_original_entry.py", "unified_short_bootstrap.py"}
ADDED = {Path(__file__).name, "ds30-0016-full-primary-transfer-protocol.md",
         "full_primary_nonanchor_receiver.py", "mixed_aperture_receiver.py"}
MAX_REGRESSION_KM = 0.25


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_bytes())


def checked(path):
    data = path.read_bytes()
    if sha256(data).hexdigest() != PINS[path]:
        raise ValueError(f"Unbound prior receipt {path}")
    return json.loads(data)


def sources(admission):
    current = {name: digest(ROOT / name) for name in admission["sources"]}
    if {Path(name).name for name, pin in current.items() if pin != admission["sources"][name]} != CHANGED:
        raise ValueError("The frozen charted worker changed outside the enrolled receiver modules")
    return current | {str((HERE / name).relative_to(ROOT)): digest(HERE / name) for name in ADDED}


def invocation(command, output):
    argv = list(command)
    argv[5] = str(HERE / "integrated_original_entry.py")
    argv[argv.index("--output") + 1] = str(output)
    start = argv.index("--short-binary")
    del argv[start:start + 2]
    argv[argv.index("--sparse8-primary")] = "--full-primary-nonanchors"
    return argv


def launch(root):
    import empty_bootstrap as boot
    from aperture_trial import write
    from clean_saved_0169_trial import output_seal
    from dense_geographic_trial import host
    from eight_ms_south_transfer import environment_for
    from full_primary_nonanchor_receiver import LIBRARY, LIBRARY_SHA256
    from raw_0016_best_trial import measure_mode
    from visit_frame_raw_0016 import resident

    started = boot.now()
    previous, stage = (checked(path) for path in (CHART / "admission.json", STAGE / "staging.json"))
    enrolled = previous["case_source"]
    origin = Path(enrolled["request"]["recording"])
    mount = subprocess.check_output(["findmnt", "-no", "FSTYPE,OPTIONS", "-T", origin], text=True).split()
    if (root.exists() or root.parent != Path("/dev/shm") or mount[0] != "tmpfs"
            or "ro" not in mount[1].split(",") or not origin.samefile(STAGE / origin.name)
            or stage["raw_authority"] != enrolled["request"]["authority"]
            or stage["inventory"] != enrolled["request"]["inventory"]):
        raise ValueError("Expected the exact signed recording bound read-only to its complete stage")
    machine = host()
    if machine != previous["machine"]:
        raise ValueError("Expected the charted one-thread low-priority CPU2 worker")
    pins = sources(previous)
    if digest(LIBRARY) != LIBRARY_SHA256:
        raise ValueError("The measured 20 ms primary helper changed")

    def residency():
        return resident(enrolled["wavepaths"])

    if residency() != enrolled["resident"]["waveform"]:
        raise ValueError("The original stage differs from the complete charted recording")
    root.mkdir(mode=0o700)
    (root / "tmp").mkdir()
    copytree(CHART / "fonts", root / "fonts")
    command = invocation(previous["command"], root / "candidate")
    write(root / "admission.json", dict(case=CASE, request=enrolled["request"], machine=machine, sources=pins,
          command=command, historical_pins={str(path): pin for path, pin in PINS.items()},
          receiver_helper_sha256=LIBRARY_SHA256, raw_conditioning_bytes=0, planned_children=1, setup=boot.clock(started)))
    env = environment_for(root)
    started, before = boot.now(), getrusage(RUSAGE_CHILDREN)
    probe = subprocess.run([*command, "--first-map-setup-only"], env=env, check=False, capture_output=True,
                           text=True, timeout=15)
    after = getrusage(RUSAGE_CHILDREN)
    write(root / "startup.json", dict(clock=boot.clock(started), exit_code=probe.returncode,
          child_cpu_s=after.ru_utime + after.ru_stime - before.ru_utime - before.ru_stime,
          stdout=probe.stdout, stderr=probe.stderr))
    probe.check_returncode()
    scanner, solver = (json.loads(line) for line in probe.stdout.splitlines())
    if (not scanner["reached_scanner"] or scanner["waveform_opens"] or scanner["audit"]["authority_mode"] != "verified-once"
            or not solver["solver_setup"] or not solver["lookahead_setup"] or solver["waveform_opens"]
            or solver["witness_shape"] != [["decision"], ["ports", "timing"]] or (root / "candidate").exists()):
        raise ValueError("The setup-only probe escaped its original no-waveform scope")
    measure_mode(root, "candidate", command, env, residency, require_success=False)
    write(root / "prediction-seal.json", output_seal(root))


def score(root):
    from alternate_original_members_score import geographic, reference
    from aperture_trial import write
    from clean_saved_0169_trial import output_seal
    from combined_successor_cairo_trial import require_renderer
    from full_primary_nonanchor_receiver import LIBRARY_SHA256, recipe
    from legacy_block_raw_score import snapshot
    from legacy_verify_original_trial import inspect_once
    from leo.contracts.digests import canonical_digest

    prior = checked(CHART / "admission.json")
    seal = root / "prediction-seal.json"
    admission, log = (read(root / name) for name in ("admission.json", "candidate-clock.json"))
    if (read(seal) != output_seal(root) or admission["sources"] != sources(prior)
            or admission["command"] != log["command"] or checked(CHART / "prediction-seal.json") != output_seal(CHART)):
        raise ValueError("The prediction or benchmark scope changed after admission")
    result = dict(qualified=False, case=CASE, process=log["clock"], prediction_seal_sha256=digest(seal))
    if log["clock"]["exit_code"]:
        write(root / "result.json", result | dict(decision="failed"))
        return
    chart, stock = checked(CHART / "result.json"), checked(STOCK)["stock"]
    path = root / "candidate"
    raw, witness = (read(path / name) for name in ("unified-short-bootstrap.json", "exact-named-raw-witness.json"))
    new_recipe = recipe()
    native_file, = path.glob("fast-scan-automatic-work/*/detections.json")
    native = read(native_file)
    request = prior["case_source"]["request"] | dict(detector=canonical_digest(new_recipe), native=canonical_digest(native))
    reconciliation = inspect_once(path, request, chart["acquisition"])
    science = snapshot(path, log, request, prior["case_source"]["producer"], verify_renderer=require_renderer)
    native_audit = raw["receiver_audit"]["native"]
    arms = science["published"]["arms"]
    local = reference()
    geography = {name: geographic({"science": payload}, local) for name, payload in
                 (("installed", stock["science"]), ("charted", chart["science"]["published"]),
                  ("full_primary", science["published"]))}
    deltas = {ctrl: {arm: geography["full_primary"][arm]["horizontal_error_km"] - geography[ctrl][arm]["horizontal_error_km"]
                    for arm in arms} for ctrl in ("installed", "charted")}
    checks = dict(
        receiver=(raw["receiver_recipe"] == new_recipe and raw["detector_recipe_sha256"] == request["detector"]
                  and native_audit["primary_helper_sha256"] == LIBRARY_SHA256
                  and sum(native_audit["native_calls"].values()) == 1426 and "held_anchor_route" not in raw),
        member_auth=all(row["complete_encoded_auth"] for row in reconciliation["members"]),
        coverage=science["positions"]["grid_points"] == 179 and len(science["images"]) == 8,
        regions=all(p["region"] == science["receipt"]["region"] for p in
                    (stock["science"]["receipt"], chart["science"]["receipt"])),
        geography=all(delta <= MAX_REGRESSION_KM for ctrl in deltas.values() for delta in ctrl.values()),
    )
    rf = {name: r for name, r in (("installed", stock["all_owned_rf_rms_hz"]),
          ("charted", {arm: val["residual_rms_hz"] for arm, val in chart["witness"]["evidence"]["detail"]["arms"].items()}),
          ("full_primary", {arm: val["residual_rms_hz"] for arm, val in witness["evidence"]["detail"]["arms"].items()}))}
    write(root / "result.json", result | dict(qualified=all(checks.values()), decision=science["receipt"]["decision"],
          checks=checks, geography=geography, horizontal_regression_km=deltas, all_owned_rf_rms_hz=rf,
          clock={"installed": stock["process"]["clock"], "charted": chart["process"], "full_primary": log["clock"]},
          science=science, receiver=raw, acquisition=reconciliation, request=request))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("action", choices=("launch", "score"))
    cli.add_argument("root", type=Path)
    options = cli.parse_args()
    {"launch": launch, "score": score}[options.action](options.root)
