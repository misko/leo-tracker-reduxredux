"""Bound receiver-only savings and replay two modest stereo lane masks."""

import argparse
from collections import Counter, defaultdict, deque
import gzip
from hashlib import sha256
import json
from pathlib import Path
import subprocess
from time import perf_counter, process_time
from types import SimpleNamespace
from unittest.mock import patch

from aperture_trial import RELEASE, archive_identity, read, write
from contiguous_third import native_signature, observe_prepared
from dense_full_short_raw import PAIR, PAIR_SHA, checked, usage
from dense_geographic_trial import elapsed, host, now
from full_short_physical import environment
from full_short_raw import RECIPE_SHA
from full_short_run import GEOGRAPHIC_SHA, TRACK_SCORES_SHA, geographic_projection
from late_prefix_stop import GEOGRAPHIC, SCORES, native_budget, record
from stereo_lane_schedule import RESIDUES, StereoSchedule, recipe
from tools.pipeline_eval.variants.capture_bursts import inventories, visit_pairs


HERE = Path(__file__).resolve().parent
ORDER = {"DS30-0008": ("target", "quarter"), "DS30-0016": ("quarter", "target"), "south": ("quarter", "target")}
CONTROLS = {
    "DS30-0008": (Path("/var/tmp/leo-v3-regional-dense-pair/native"), "11c554cbcca4f756e07e810bbc7b34b548a799fd005645fd4d9e5fcbba8ef72e"),
    "DS30-0016": (Path("/dev/shm/leo-cumulative-grid-projection-01/weak/installed"), "e96fbfd7283dadf675a8db58cae0c33c799c7354f205b237afd7756a559f5883"),
    "south": (Path("/var/tmp/leo-short-graph-20261123-south-inside"), "5d7b28ab3ce6dd3f06e09153481eb125dfad45a11486cc863fdd2fd2e018ce64"),
    "south-far": (Path("/var/tmp/leo-short-graph-20261123-south-far"), "f7842cbaac7d7de050336b177cb72527f6d2cb3af2f62abc23019235aa6578fc"),
}


def project(native, mode):
    from leo.contracts.digests import canonical_digest

    started = process_time()
    inventories(native)
    source, provenance = native["source"], native["provenance"]
    probes, detector = source["probes"], provenance["detector_sha256"]
    if (detector != "sha256:" + RECIPE_SHA or provenance["scope"] != "cancellation"
            or source["sample_rate_hz"] != 10_000_000 or not source["qualified"]
            or native_signature(source, detector, probes) != source["analysis_manifest_sha256"]):
        raise ValueError("Expected original, unfiltered complete 20/12 ms receiver evidence")
    result, skipped, short_empty, lost_ids = [], [], 0, []
    paid, unpaid, per_radio, lost, affected = Counter(), Counter(), Counter(), Counter(), Counter()
    history = defaultdict(lambda: deque(maxlen=12))
    schedule = StereoSchedule(mode)
    for visit, pair in visit_pairs(probes):
        first, _ = pair
        stream = tuple(first[k] for k in ("edge", "channel", "actual_rf_hz"))
        aperture, omit = schedule.next(stream)
        for probe in pair:
            radio, now = probe["receiver_id"], probe["valid_start_counter"]
            factors = probe["candidates"]
            lane = (radio, probe["channel"], probe["actual_rf_hz"])
            earlier = history[lane]
            short_empty += aperture == "short_primary" and not factors
            if radio == omit:
                skipped.append((visit, radio))
                unpaid[aperture] += 1
                per_radio[radio] += 1
                lost[radio] += len(factors)
                if factors:
                    key = f"{source['session_id']}:{radio}:{now}".encode()
                    lost_ids.append("sha256:" + sha256(key).hexdigest())
                result.append(dict(probe, candidates=[]))
            else:
                paid[aperture] += 1
                result.append(probe)
                if factors and any(0 < now - t <= 80_000_000 and positive for t, positive in earlier):
                    affected[radio] += 1
            earlier.append((now, radio == omit and bool(factors)))
    planner_cpu = process_time() - started
    identity = recipe(mode, detector)
    pin = canonical_digest(identity)
    digest = native_signature(source, pin, result)
    projected = dict(native, source=dict(source, probes=result, analysis_manifest_sha256=digest),
                     provenance=dict(provenance, detector_sha256=pin, run_id="blind-compact-" + digest[7:39]))
    audit = dict(recipe=identity, kept_native_lanes=dict(paid), skipped_native_lanes=dict(unpaid), skipped_slots=skipped,
                 omitted_by_radio=dict(per_radio), lost_factors_by_radio=dict(lost), lost_positive_ids=lost_ids,
                 paid_positive_lanes_with_missing_past_donor=dict(affected), oracle_short_empty_lanes=short_empty,
                 original_factors=sum(len(p["candidates"]) for p in probes),
                 paid_factors=sum(len(p["candidates"]) for p in result), plan_and_history_audit_cpu_s=planner_cpu,
                 mask_sha256=canonical_digest(skipped), native_sha256=canonical_digest(projected),
                 detector_sha256=pin, issued=provenance["window_count"], admitted_stereo=len(probes)//2)
    return projected, audit


def bind(case):
    from leo.contracts.algo08_region import Algo08Region
    from leo.contracts.digests import canonical_digest

    full, report_pin = CONTROLS[case]
    report = read(checked(full / "joint-research-receipt.json", report_pin))
    receipt = report["receipt"]
    terminal = read(full / "fast-scan-automatic-work" / receipt["run_id"] / "terminal.json")
    if case == "DS30-0008":
        compressed = checked(HERE / "measurements/dense-full-short-raw.json.gz",
                             "51521b26848532823922cc43a198b7f91d59d3f1d81e155e5862b04b53193f38")
        prior = json.loads(gzip.decompress(compressed.read_bytes()))
        request = prior["binding"]
        command = request["command"]
        recording, region, archive = command[command.index("--recording") + 1], Path(request["region"]), request["archive"]
        native = full / "fast-scan-automatic-work" / receipt["run_id"] / "detections.json"
        pin, raw = prior["candidate"]["native_sha256"], prior["candidate"]["recipe"]["receiver_audit"]
        named = read(checked(PAIR, PAIR_SHA))["runs"]["baseline"]["arms"]
    else:
        from full_short_graph_transfer import inputs

        capture = {"DS30-0016": "physical", "south": "south-inside", "south-far": "south-far"}[case]
        recording, archive, region, native, pin, _ = inputs(capture)
        if capture == "physical":
            raw_path = Path("/dev/shm/leo-v3-combined-frontier-weak-01/candidate/full-short-recipe.json")
            raw_pin = "4dbe5140d7148aaa255107fe8abff147ccf551b82b74987f2bc8fabd779a3979"
            named = read(checked(HERE / "measurements/weak-combined-raw.json",
                                 "a704861e37e40e7364fbf97bcb74e98bb9c701ca474c12821e8ed7df86cab233"))["runs"]["stock"]["arms"]
        else:
            from full_short_south import INSIDE

            raw_path = Path("/var/tmp/leo-full-short-south-transfer-final/containing/full-short-recipe.json")
            raw_pin = "602bada259cb691808740d1ce6f3a38818be2d508e01caa175a1279499ff6a07"
            named = read(checked(INSIDE, "48fed3c62639ef81fb99e4b76921bcacd999e769a78ebb607b2b886b6f0951f0"))["runs"]["candidate"]["arms"]
        raw = read(checked(raw_path, raw_pin))["receiver_audit"]
    original = read(checked(native, pin.removeprefix("sha256:")))
    offer, authority = receipt["region"], raw["recording_authority"]
    if (canonical_digest(original) != pin or terminal["native_sha256"] != pin
            or canonical_digest(terminal) != receipt["terminal_sha256"] or terminal["region"] != offer
            or Algo08Region.parse(read(region)).document() != offer or archive_identity(Path(archive["root"])) != archive
            or original["source"]["raw_recording_authority_digest"] != authority
            or original["source"]["analysis_manifest_sha256"] != raw["analysis_manifest"]
            or original["provenance"]["window_count"] != raw["issued"]):
        raise ValueError("Signed waveform parent, compared terminal, region, raw audit or causal archive changed")
    binding = dict(case=case, recording=str(recording), archive=archive, region=str(region), offer=offer,
                   original_native_sha256=pin, raw_authority=authority)
    control = dict(arms=terminal["arms"], selected_rows=report["selected_rows"], solve=report["solve"],
                   state=receipt["decision"], report_sha256=report_pin, terminal_sha256=receipt["terminal_sha256"])
    return original, binding, dict(full=control, named=dict(arms=named), raw_audit=raw)


def charged(raw, audit):
    result = native_budget(raw, audit)
    short_calls = raw["native"]["native_calls"]["short_primary"]
    rate = raw["native"]["native_cpu_ns"]["short_primary"] / short_calls / 1e9
    skipped = len(audit["skipped_slots"])
    return dict(result, skipped_short_fraction=skipped/short_calls, per_short_cpu_s=rate,
                short_only_oracle_empty_cpu_s=audit["oracle_short_empty_lanes"]*rate,
                both_targets_short_calls={str(seconds): int(seconds/rate)+1 for seconds in (2.735, 4.616)},
                omitted_lane_iq_bytes_minimum=800000*skipped, corresponding_stereo_iq_bytes=1600000*skipped,
                retry_mode="pay all omitted short searches and a fresh complete-input solver")


def worker(recording, archive, region, output, saved, saved_pin, detector):
    from joint_publication import run
    from tools.pipeline_eval.qualification import experimental_publication as publication

    publish = publication.run
    graph = []

    def instrument(*args, **kwargs):
        from leo.application import localization_v3 as application

        prepare = application.prepare_tracks

        def measure(*values, **options):
            start = now()
            try:
                return prepare(*values, **options)
            finally:
                graph.append(elapsed(start))

        with patch.object(application, "prepare_tracks", measure):
            return publish(*args, **kwargs)

    options = SimpleNamespace(recording=recording, archive=archive, region=region, output=output, saved=saved,
                              saved_digest=saved_pin, optimized_full_catalogue=True, observe_prepared=observe_prepared,
                              verify_images=True)
    with patch.object(publication, "run", instrument):
        run(options, early_regional=True, saved_receiver=detector,
            geographic_projector=lambda: geographic_projection(GEOGRAPHIC, SCORES), reuse_cold_rows=True,
            reuse_grid_phase_states=True)
    write(output / "timed-graph.json", graph)


def run(case, root, mode=None):
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore

    machine = host()
    if case == "south-far" and mode not in RESIDUES or case != "south-far" and mode is not None:
        raise ValueError("Containing runs require both frozen masks; far needs the qualified mask")
    for binary, pin in ((GEOGRAPHIC, GEOGRAPHIC_SHA), (SCORES, TRACK_SCORES_SHA)):
        checked(binary, pin)
    if subprocess.check_output(["findmnt", "-no", "FSTYPE", "-T", root.parent], text=True).strip() != "tmpfs":
        raise ValueError("Use private tmpfs saved publication")
    native, binding, controls = bind(case)
    root.mkdir()
    env = environment(root)
    env["TMPDIR"] = str(root)
    python = str(RELEASE / "venv/bin/python")
    subprocess.run([python, "-Bc", "from matplotlib import font_manager; font_manager.findfont('DejaVu Sans')"],
                   env=env, check=True, timeout=20)
    write(root / "binding.json", dict(binding=binding, controls=controls, machine=machine,
        driver_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
        protocol_sha256=sha256((HERE / "stereo-mask-protocol.md").read_bytes()).hexdigest()))
    for choice in ((mode,) if mode else ORDER[case]):
        projected, mask = project(native, choice)
        saved, output = root / f"{choice}-input.json", root / choice
        write(saved, projected)
        command = [python, "-BPs", str(Path(__file__)), "worker", binding["recording"], binding["archive"]["root"],
                   binding["region"], str(output), str(saved), mask["native_sha256"], mask["detector_sha256"][7:]]
        before, start = usage(), perf_counter()
        launched = subprocess.run(command, env=env, capture_output=True, text=True, timeout=120)
        after = usage()
        clock = dict(elapsed_s=perf_counter()-start, exit_code=launched.returncode,
                     **{key: after[key]-before[key] for key in before})
        write(root / f"{choice}-clock.json", clock)
        (root / f"{choice}-stderr").write_text(launched.stderr)
        launched.check_returncode()
        result = record(output, projected, binding)
        complete = result["terminal"]["decision"] == "ok"
        if complete:
            store = FastStandardAnalysisStore(output)
            rid = read(output / "joint-research-receipt.json")["receipt"]["run_id"]
            expected = result["evidence"]["images"]["position"]["sha256"]
            for sidecar in (store.position_grid(rid), store.position_path(rid)):
                if sidecar["binding"]["position_png_sha256"] != expected:
                    raise ValueError("Numeric sidecar does not bind its own position PNG")
        write(root / f"{choice}-sealed.json", dict(process=clock, mask=mask, budget=charged(controls["raw_audit"], mask),
              result=result, waveform_calls=0, command=command))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_subparsers(dest="command", required=True)
    replay = modes.add_parser("run")
    replay.add_argument("case", choices=CONTROLS)
    replay.add_argument("root", type=Path)
    replay.add_argument("--mode", choices=RESIDUES)
    save = modes.add_parser("worker")
    for path in ("recording", "archive", "region", "output", "saved"):
        save.add_argument(path, type=Path)
    save.add_argument("saved_pin")
    save.add_argument("detector")
    args = vars(parser.parse_args())
    {"run": run, "worker": worker}[args.pop("command")](**args)
