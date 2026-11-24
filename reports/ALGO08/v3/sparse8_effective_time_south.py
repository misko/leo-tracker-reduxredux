"""Compare one provenance-qualified South saved publication with its ordinary control."""

import argparse
import fcntl
from hashlib import sha256
import json
import os
from pathlib import Path
from resource import RUSAGE_CHILDREN, getrusage
import subprocess
import sys
from time import perf_counter_ns, time_ns
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sparse8_cfo_epoch_trial import ARMS, LOCK, attrs, document, identifier, write
from sparse8_effective_time import binding, source_rows


HERE = Path(__file__).resolve().parent
ORDINARY = Path("/tmp/leo-v3-frozen-south-saved-01")
ORDINARY_PIN = "cddc872a8990560d9342d5dd17b89d21920f527f61de66405dfac8a940f34716"
SOURCE = Path("/tmp/leo-v3-frozen-geographic-audit/reports/ALGO08/v3")
SOURCE_PINS = {
    "frozen_south_saved.py": "47d70a51031fad5f83793f01180b4ac30305c9dc71218f7c09debf3c0dc56e9c",
    "frozen_south_saved_score.py": "320cc51a7bac13867cef56d19a40a6307add8b7078cfdc2481156c6018701777",
}
PROTOCOL = HERE / "sparse8-effective-time-south-protocol.md"
MODE = "containing:integrated"


def load_south():
    for name, pin in SOURCE_PINS.items():
        if identifier(SOURCE / name) != pin:
            raise ValueError("The coupled ordinary South source has changed")
    sys.path.insert(0, str(SOURCE))
    import frozen_south_saved as south
    return south


def original_selector(freeze):
    native = Path(freeze["proposed_saved_pair"]["packets"]["integrated"]["path"])
    home = native.parents[3]
    seal_pin = freeze["south_existing_raw"]["containing_prediction_seal_sha256"]
    sealed = document(home / "prediction-seal.json", seal_pin)
    relative = "candidate-held-anchor-route.json"
    selector = document(home / relative, sealed[relative])
    bootstrap = "candidate/unified-short-bootstrap.json"
    if selector != document(home / bootstrap, sealed[bootstrap])["held_anchor_route"]:
        raise ValueError("The historical aperture witness differs from the original raw bootstrap")
    return selector, sealed[relative]


def candidate(stage):
    south = load_south()
    freeze = document(south.PINS / "frozen-build-geography.json", south.FREEZE_SHA)
    selector, selector_pin = original_selector(freeze)
    original = south.charted
    audit = {}

    def corrected(publication, spec, sources, args, handoff, *rest):
        with binding(handoff.native, selector, audit):
            output = original(publication, spec, sources, args, handoff, *rest)
        if not audit["applied"]:
            raise ValueError(f"The frozen South effective-time port was not applied: {audit}")
        return output

    with patch.object(south, "charted", corrected):
        south.worker(MODE, stage / "centroid")
    return dict(clockless_science_sha256=identifier(stage / "centroid/saved-south-worker.json"),
                exact_publication_sha256=identifier(stage / "centroid/exact-named-raw-witness.json"),
                original_selector_sha256=selector_pin, source=SOURCE_PINS, protocol_sha256=identifier(PROTOCOL),
                correction=audit)


def probe():
    south = load_south()
    freeze, _, cutoff, _, _, _, crossover = south.bootstrap()
    _, _, packets, _, _, _, _ = south.inputs(freeze, cutoff, crossover.batch)
    selector, selector_pin = original_selector(freeze)
    native = packets["integrated"]
    route, new = source_rows(native, selector)
    from leo.analysis.localization_v3.tracks import winning_observations
    from sparse8_cfo_epoch_saved import correction_rows, graph_rows

    rows, _ = winning_observations(native)
    graph_rows(rows, new)
    if new != correction_rows(native) or route != "history":
        raise ValueError("The source-bound adapter changed the frozen correction")
    from collections import Counter
    return dict(route=route, selector_sha256=selector_pin, graph_winners=len(rows),
                offsets_us=dict(sorted(Counter(round(value[1]*1e6, 4) for value in new.values()).items())))


def run(stage):
    config = attrs()
    document(ORDINARY / "prediction-seal.json", ORDINARY_PIN)
    with LOCK.open("rb") as lease:
        fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        stage.mkdir(mode=0o700)
        scratch = stage / "scratch"
        scratch.mkdir()
        environment = os.environ | dict(TMPDIR=str(scratch), MPLCONFIGDIR=str(scratch), XDG_CACHE_HOME=str(scratch))
        command = [sys.executable, "-IB", str(Path(__file__)), str(stage), "--candidate"]
        with (stage / "centroid.stdout").open("x") as out, (stage / "centroid.stderr").open("x") as err:
            begin = getrusage(RUSAGE_CHILDREN)
            started, wall = time_ns(), perf_counter_ns()
            try:
                child = subprocess.run(command, env=environment, check=False, stdout=out, stderr=err, timeout=120)
                code = child.returncode
            except subprocess.TimeoutExpired:
                code = 124
            finished, elapsed = time_ns(), (perf_counter_ns()-wall)*1e-9
            end = getrusage(RUSAGE_CHILDREN)
        clock = dict(started_unix_ns=started, finished_unix_ns=finished, elapsed_s=elapsed, exit_code=code,
                     user_s=end.ru_utime-begin.ru_utime, system_s=end.ru_stime-begin.ru_stime,
                     major_faults=end.ru_majflt-begin.ru_majflt, input_blocks=end.ru_inblock-begin.ru_inblock,
                     command=command)
        clock_pin = write(stage / "centroid-clock.json", clock)
    if code:
        raise ValueError(f"Corrected South saved worker exited {code}; inspect {stage / 'centroid.stderr'}")
    return write(stage / "prediction-seal.json", dict(
        ordinary_sha256=ORDINARY_PIN, protocol_sha256=identifier(PROTOCOL), clock_sha256=clock_pin,
        receipt_sha256=identifier(stage / "centroid-receipt.json"), host=config, survey_reads=0))


def score(stage, pin):
    south = load_south()
    from frozen_south_saved_score import publication

    seal = document(stage / "prediction-seal.json", pin)
    if seal["ordinary_sha256"] != ORDINARY_PIN or seal["protocol_sha256"] != identifier(PROTOCOL):
        raise ValueError("South comparison was not frozen on its containing control")
    frozen_seal = document(ORDINARY / "prediction-seal.json", ORDINARY_PIN)
    worker = document(stage / "centroid-receipt.json", seal["receipt_sha256"])
    clock = document(stage / "centroid-clock.json", seal["clock_sha256"])
    for filename, key in (("saved-south-worker.json", "clockless_science_sha256"),
                          ("exact-named-raw-witness.json", "exact_publication_sha256")):
        document(stage / "centroid" / filename, worker[key])
        prior = f"containing-integrated/{filename}"
        document(ORDINARY / prior, frozen_seal[prior])
    freeze, _, cutoff, _, _, _, crossover = south.bootstrap()
    authority, _, _, _, _, roster, offers = south.inputs(freeze, cutoff, crossover.batch)
    from prospective_0316_solver import owner_delta
    from tools.pipeline_eval.scoring import distance_km

    authority["archive_sha256"] = roster
    trial = freeze["proposed_saved_pair"]
    offer = document(offers["containing"])
    packet = "sha256:"+trial["packets"]["integrated"]["sha256"]
    old_clock = document(ORDINARY / "containing-integrated.clock.json", frozen_seal["containing-integrated.clock.json"])
    a = publication(ORDINARY / "containing-integrated", old_clock, MODE, offer, authority, packet)
    b = publication(stage / "centroid", clock, MODE, offer, authority, packet)
    summary = dict(seal_sha256=pin, correction=worker["correction"], ordinary_clock=old_clock,
                   corrected_clock=clock, native_sha256=packet,
                   states=[row["receipt"]["decision"] for row in (a,b)])
    if summary["states"] != ["complete", "complete"]:
        return dict(summary, stop=True)
    root = south.RUNTIME.parents[2]
    body = subprocess.check_output(["git", "-c", f"safe.directory={root}", "-C", str(root),
                                    "show", "HEAD:"+trial["reference_key_path"]])
    if sha256(body).hexdigest() != trial["reference_key_sha256"].removeprefix("sha256:"):
        raise ValueError("The sealed South simulation reference changed")
    truth = json.loads(body)["answers"][trial["reference_key_row"]]
    if truth["recording"] != trial["recording_name"]:
        raise ValueError("The reference belongs to a different South input")
    reference = truth["truth"]
    arms = {}
    for arm in ARMS:
        x, y = (row["terminal"]["arms"][arm] for row in (a, b))
        ea, eb = (1e3*distance_km(row["latlon"], reference) for row in (x, y))
        arms[arm] = dict(ordinary_error_m=ea, corrected_error_m=eb, change_m=eb-ea,
                         ordinary_rf_hz=x["rf_rms_hz"], corrected_rf_hz=y["rf_rms_hz"],
                         endpoint_shift_m=1e3*distance_km(x["latlon"], y["latlon"]),
                         owners=owner_delta(a["ordered_owners"][arm], b["ordered_owners"][arm]))
    return dict(summary, arms=arms, stop=any(row["change_m"]>250. for row in arms.values()),
                figures={mode: row["figures"] for mode,row in (("ordinary",a),("corrected",b))},
                grid={mode: row["grid"]["evaluated_points"] for mode,row in (("ordinary",a),("corrected",b))},
                routes={mode: row["charted_witness"]["recipe"]["history_risk"] for mode,row in
                        (("ordinary",a),("corrected",b))})


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("stage", type=Path)
    execution = cli.add_mutually_exclusive_group(required=True)
    execution.add_argument("--candidate", action="store_true")
    execution.add_argument("--run", action="store_true")
    execution.add_argument("--probe", action="store_true")
    execution.add_argument("--score")
    args = cli.parse_args()
    if args.probe:
        print(json.dumps(probe(), sort_keys=True))
    elif args.candidate:
        print(write(args.stage / "centroid-receipt.json", candidate(args.stage)))
    elif args.run:
        print(run(args.stage))
    else:
        print(write(args.stage / "score.json", score(args.stage, args.score)))
