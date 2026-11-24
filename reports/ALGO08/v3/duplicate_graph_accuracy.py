"""Charge one true saved publication per case for the frozen duplicate Graph rule."""

import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
from time import perf_counter, process_time


HERE = Path(__file__).resolve().parent
ROOTS = {
    "south": Path("/dev/shm/leo-combined-south-run.yF2Ole7s/pair"),
    "north": Path("/dev/shm/leo-v3-combined-raw-north-result01"),
}
PINS = {
    "south": ("8e32d5299ebe847f32456f30e8d11f2e80f20495771941cb0cd2c327b094f315",
              "ea3308e7c298dcc105c8e252a03e830e316966a1ef24ee794fbd27ddba4f0aac",
              "696a34f4622cbc256facfd908ac9295fa3ebcd0a9fdba98575f3be0d05bc0793"),
    "north": ("da2d6859a2d01ce852a41ba1b637fc334df9a28f523ed6583fdf313564082bed",
              "c27d2100da995c456642e21642a7ebca97a8aa155f29d96a627f884c68422deb",
              "715f7ebaff5bd31a7a58c898c38d0bc23915951f87ebe6b27f5ac629245fb4a7"),
}


def enrolled(case):
    from aperture_trial import archive_identity
    from combined_raw_trial import checked_producer
    from empty_bootstrap import checked

    root = ROOTS[case]
    binding, raw, research = (json.loads(checked(root / name, pin)) for name, pin in zip(
        ("binding.json", "containing/unified-short-bootstrap.json", "containing/joint-research-receipt.json"), PINS[case], strict=True))
    request = binding["request"]
    original_cmd = binding["command"]
    offer = original_cmd[original_cmd.index("--region") + 1]
    offer_sha = raw["requested_offer_sha256"]
    checked(Path(offer), offer_sha)
    request["offer_sha256"] = {"north-mirror-outside": offer_sha}
    request["libraries"] = {}
    for flag, row in binding["libraries"].items():
        checked(Path(row["path"]), row["sha256"])
        request["libraries"][flag[2:].replace("-", "_")] = row["path"]
    checked(Path(request["saved_inventory"]), request["inventory"][7:])
    checked_producer(request["cutoff_utc_ns"])
    if (raw["receipt"]["decision"] != "complete" or raw["raw_acquisitions"] != 1
            or raw["verified_handoffs"] != 1 or raw["causal_cutoff_utc_ns"] != request["cutoff_utc_ns"]
            or archive_identity(Path(request["archive"]["root"])) != request["archive"]):
        raise ValueError("Expected the original complete signed combined publication")
    return request, Path(offer), raw, research


def worker(case, output):
    import empty_bootstrap as staged
    from aperture_trial import write
    from combined_raw_research import combined_runtime, rank_status
    from combined_raw_trial import PRODUCER
    from duplicate_graph_proposals import stable_finalization
    from raw_cfo_north_trial import native_file, publish_saved

    started = process_time(), perf_counter()
    duplicates = Counter()
    orbit, rank = {}, {}
    with combined_runtime(orbit, rank, PRODUCER, use_blocks=True):
        runtime = staged.load_runtime()
        request, offer, raw, _ = enrolled(case)
        packet = native_file(ROOTS[case] / "containing")
        native = json.loads(staged.checked(packet, raw["native_sha256"][7:]))
        staged.bind_native(native, request["session"], request["inventory"], raw["detector_recipe_sha256"][7:], expected=raw["native_sha256"])
        if native["source"]["raw_recording_authority_digest"] != request["authority"]:
            raise ValueError("The saved handoff changed raw authority")
        with stable_finalization(duplicates):
            publish_saved(request, output, offer, packet, native, raw, started=started, runtime=runtime,
                          receipt_name="saved-accuracy.json")
    rank["status"] = rank_status(True, rank)
    write(output / "accuracy-audit.json", dict(duplicates=dict(duplicates), orbit=orbit, rank=rank))


def analyze(case, output, clock):
    from aperture_trial import read
    from combined_raw_south import owner_delta
    from joint_publication import artifacts
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
    from north_interlaced_raw import TRUTH_SHA
    from tools.pipeline_eval.qualification.paired_publication import evidence
    from tools.pipeline_eval.qualification.score_paired_holdout import face_clearance_km
    from tools.pipeline_eval.scoring import distance_km

    request, _, raw, original = enrolled(case)
    data = subprocess.check_output(["git", "-C", str(HERE.parents[2]), "show", "HEAD:reports/ALGO08/regional-release/scoring-key.json"])
    if sha256(data).hexdigest() != TRUTH_SHA:
        raise ValueError("Independent public scoring key changed")
    (truth,) = {tuple(row["truth"]) for row in json.loads(data)["answers"].values()
                if row["recording"] == Path(request["recording"]).name}
    found = read(output / "saved-accuracy.json")
    proof = read(output / "accuracy-audit.json")
    receipt, previous = found["receipt"], raw["receipt"]
    if (receipt["region"] != previous["region"] or found["native_sha256"] != raw["native_sha256"]
            or found["waveform_calls"] or not found["staged_inventory"] or found["handoffs"] != 1):
        raise ValueError("Saved accuracy replay changed its original signed input")
    arms = {}
    figures = {}
    for name, root, result in (("original", ROOTS[case] / "containing", previous), ("filtered", output, receipt)):
        science = evidence(root, result, clock["started_unix_ns"], read_only=True)
        images = artifacts(root, result)["images"]
        if images:
            store = FastStandardAnalysisStore(root)
            grid, path = store.position_grid(result["run_id"]), store.position_path(result["run_id"])
            if (len(images) != 8 or not grid["complete"] or not grid["matched_c_grid"]
                    or grid["evaluated_points"] != grid["planned_points"] or not path["stages"]
                    or any(doc["binding"]["position_png_sha256"] != images["position"]["sha256"] for doc in (grid, path))):
                raise ValueError("Incomplete verified two-arm position evidence")
        arms[name] = {arm: dict(row, horizontal_error_m=1000*distance_km(truth, row["latlon"]),
                                face_clearance_km=face_clearance_km(result["region"], row["latlon"]) if row["latlon"] else None)
                      for arm,row in science["arms"].items()}
        figures[name] = images
    selected = output / "joint-research-receipt.json"
    research = read(selected) if selected.exists() else {}
    owners = owner_delta(original["selected_rows"], research.get("selected_rows", {}))
    return dict(clock=clock, original_solve=original["solve"], original_graph=raw["exact_graph_reuse"],
                saved=found, proof=proof, quality=arms, figures=figures, owner_delta=owners,
                original_decision=previous["decision"], original_receipt=previous, new_early_proof=research.get("early_regional"),
                fit_reason=research.get("route_details", {}).get("reason"), scoring_key_sha256=TRUTH_SHA)


def run(root):
    from aperture_trial import RELEASE, write
    from dense_geographic_trial import host
    from full_short_physical import environment
    from short_raw_diagnostic import measure

    machine = host()
    if subprocess.check_output(["findmnt", "-no", "FSTYPE", "-T", root.parent], text=True).strip() != "tmpfs":
        raise ValueError("Use fresh private tmpfs output")
    root.mkdir()
    (root / "tmp").mkdir()
    (root / "fonts").mkdir()
    (root / "fonts/fontlist-v3.11.0.json").write_bytes((ROOTS["north"] / "fonts/fontlist-v3.11.0.json").read_bytes())
    env = environment(root)
    env.update(TMPDIR=str(root/"tmp"), XDG_CACHE_HOME=str(root/"tmp"))
    result = {}
    for case in ROOTS:
        output = root / case
        command = ["/usr/bin/timeout", "--kill-after=2s", "22s", RELEASE / "venv/bin/python", "-IB", __file__, "worker", case, output]
        timing = measure(command, env, output)
        result[case] = (dict(clock=timing) if timing["exit_code"] else analyze(case, output, timing))
        write(root / f"{case}-evidence.json", result[case])
    write(root / "result.json", dict(machine=machine, cases=result, source_pins=PINS, raw_runs=0, waveform_reads=0,
          source_sha256={name:sha256((HERE / name).read_bytes()).hexdigest()
                        for name in ("duplicate_graph_accuracy.py", "duplicate_graph_proposals.py", "duplicate-graph-accuracy-protocol.md")}))


if __name__ == "__main__":
    sys.path.insert(0, str(HERE))
    parser = argparse.ArgumentParser(description=__doc__)
    if sys.argv[1:2] == ["worker"]:
        parser.add_argument("case", choices=ROOTS)
        parser.add_argument("output", type=Path)
        worker(**vars(parser.parse_args(sys.argv[2:])))
    else:
        parser.add_argument("root", type=Path)
        run(parser.parse_args().root)
