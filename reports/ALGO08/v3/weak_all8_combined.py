"""Measure the authenticated all-visit weak 8 ms packet on the combined saved solver."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import empty_bootstrap as staged
from preloaded_saved_worker import read, write


CASE = "weak"
PROTOCOL = HERE/"weak-all8-combined-protocol.md"
SOURCES = (Path(__file__), PROTOCOL, *(HERE/name for name in (
    "eight_ms_held_fit.py", "preloaded_saved_worker.py", "preloaded_saved_score.py", "combined_raw_research.py",
    "unified_short_bootstrap.py", "raw_cfo_north_trial.py", "cumulative_grid_projection.py", "catalogue_block_port.py",
    "historical_orbit_index.py", "portable_orbit_index.py", "portable_orbit_compatibility.py")))
PRIOR = Path("/dev/shm/leo-v3-eight-ms-held-fit-result01/containing/weak-history8/published")
PRIOR_RESEARCH_SHA = "6814d778d8d49d838a10e901590b2e0b168d02497d4b41e465c7a9064c1d339d"
RAW_CLOCK_SHA = "4aa997867ef20c45cd80162370962c95c25ed26486dd06115bd992129fb67c4b"
RAW_BINDING_SHA = "4e61f165347710aa3e84d36497a844070a0459cc386c914437b5795ef3b308bb"
NAMED_SHA = "33d6cab032ab19f6093d57d6017be32820d479e5e96c082a21b40d4ea75824c0"
TIMES = ("cpu_s", "elapsed_s")
RECEIPT = "all8-combined-publication.json"


def pins():
    return {path.name: sha256(path.read_bytes()).hexdigest() for path in SOURCES}


def reference():
    from whole_stereo_8ms import SAVED_PIN, SAVED_SEAL

    return json.loads(staged.checked(SAVED_SEAL, SAVED_PIN))["runs"][CASE]["history8"]


def acquired():
    from anchor_exposure import PINS, packet
    from eight_ms_held_fit import RECEIVER_RECIPE_PINS
    from full_short_run import EIGHT_MS_RECIPE_SHA, EIGHT_MS_SHA, checked_recipe

    folder, digest = PINS["DS30-0016"]["8ms"]
    folder = Path(folder)
    original = packet(folder, digest)
    receipt = json.loads(staged.checked(folder/"full-short-recipe.json", RECEIVER_RECIPE_PINS[CASE]))
    spec, source = receipt["receiver_audit"], original["source"]
    if (receipt["saved_digest"] is not None or receipt["recipe"] != checked_recipe(eight_ms=True)
            or spec["detector_pin"] != EIGHT_MS_RECIPE_SHA or spec["analysis_manifest"] != source["analysis_manifest_sha256"]
            or spec["input_manifest"] != source["input_manifest_sha256"]
            or spec["recording_authority"] != source["raw_recording_authority_digest"]
            or spec["issued"] != 808 or spec["selected"] != 506
            or spec["native"]["short_primary_sha256"] != EIGHT_MS_SHA
            or spec["native"]["native_calls"] != {"full": 186, "short_primary": 1240}
            or "cfo_refinement" in spec["native"] or len(source["probes"]) != 1426):
        raise ValueError("Expected the genuine zero-tail acquisition on the entire original weak recording")
    return original, receipt, folder, digest


def worker(root):
    from anchor_exposure import bind
    from combined_raw_research import combined_runtime, rank_status
    from combined_raw_trial import PRODUCER
    from eight_ms_held_fit import select
    from preloaded_saved_worker import enrolled
    from raw_cfo_north_trial import ORDER, publish_saved

    started = staged.now()
    if read(root/"binding.json")["sources"] != pins():
        raise ValueError("Unfrozen candidate and stage clocks")
    orbit, rank = {}, {}
    phases = {}
    with combined_runtime(orbit, rank, PRODUCER, use_blocks=True):
        begin = staged.now()
        runtime = staged.load_runtime()
        phases["runtime_validation"] = staged.clock(begin)
        begin = staged.now()
        from leo.contracts.digests import canonical_digest
        from leo.storage.fast_scan import immutable_json

        request, archive, offer, libraries, _, control, identity = enrolled(CASE)
        old = reference()
        expected = old["identity"]
        binding_keys = ("offer_sha256", "issued", "session", "inventory", "authority", "cutoff_utc_ns", "archive")
        if any(identity[key] != expected[key] for key in binding_keys):
            raise ValueError("A causal or geographic input differs from the matching all-visit control")
        phases["request_and_causal_input"] = staged.clock(begin)
        begin = staged.now()
        original, raw, _, original_pin = acquired()
        native, witness = select(original, raw["recipe"])
        bind(control, native)
        if (witness["refinement_calls"] or canonical_digest(witness["choice"]) != canonical_digest(old["selector"]["choice"])
                or witness["choice"]["route"] != "unfiltered" or witness["selected"] != 506
                or witness["native_sha256"] != expected["native_sha256"]
                or witness["detector_recipe_sha256"] != expected["detector"]
                or native["source"]["probes"] != original["source"]["probes"]):
            raise ValueError("The current held policy must reproduce every original measured 8 ms factor")
        packet = root/"selected-detections.json"
        immutable_json(packet, native)
        staged.checked(packet, expected["native_sha256"][7:])
        phases["detector_load_selection_and_seal"] = staged.clock(begin)
        request = dict(request, archive={"root": str(archive)}, libraries=libraries,
                       offer_sha256={ORDER[1]: expected["offer_sha256"]}, receiver="native-20-8-held-history")
        prepare = dict(native_sha256=witness["native_sha256"], detector_recipe_sha256=witness["detector_recipe_sha256"])
        begin = staged.now()
        publish_saved(request, root/"candidate", offer, packet, native, prepare, started=started,
                      runtime=runtime, receipt_name=RECEIPT, flags=expected["flags"])
        phases["saved_publication"] = staged.clock(begin)
    write(root/"execution.json", dict(identity=expected, selection=witness, original_native_sha256=original_pin,
          phases=phases, orbit=orbit, rank=rank, rank_status=rank_status(True, rank)))


def launch(root):
    from dense_geographic_trial import host
    from full_short_physical import environment
    from north_held_anchor_pair import tmpfs
    from short_raw_diagnostic import measure

    tmpfs(root.parent)
    checkout = HERE.parents[2]
    git = ["git", "-c", f"safe.directory={checkout}", "-C", str(checkout)]
    if subprocess.check_output([*git, "status", "--porcelain", "--untracked-files=no"], text=True).strip():
        raise ValueError("Commit the frozen run sources before launch")
    root.mkdir()
    (root/"fonts").mkdir()
    (root/"tmp").mkdir()
    env = environment(root) | {"TMPDIR": str(root/"tmp"), "XDG_CACHE_HOME": str(root/"tmp")}
    python = staged.RELEASE/"venv/bin/python"
    subprocess.run([python, "-Bc", "from matplotlib import font_manager; font_manager.findfont('DejaVu Sans')"],
                   env=env, check=True, timeout=25)
    command = ["/usr/bin/timeout", "--kill-after=2s", "35s", python, "-IB", Path(__file__), "worker", root]
    write(root/"binding.json", dict(host=host(), commit=subprocess.check_output([*git, "rev-parse", "HEAD"], text=True).strip(),
                                   sources=pins(), command=list(map(str, command))))
    clock = measure(command, env, root/"candidate")
    write(root/"clock.json", clock)
    if clock["exit_code"]:
        raise RuntimeError(clock["stderr_tail"])


def disjoint(total, phases, solve, render):
    pieces = {key: phases[key] for key in ("runtime_validation", "request_and_causal_input", "detector_load_selection_and_seal")}
    pieces.update(numerical_solve={key: solve[key] for key in TIMES}, images={key: render[key] for key in TIMES})
    pieces["other_saved_publication"] = {key: phases["saved_publication"][key]-solve[key]-render[key] for key in TIMES}
    pieces["launch_receipt_and_exit"] = {key: total[key]-sum(scope[key] for scope in pieces.values()) for key in TIMES}
    if any(value < 0 for scope in pieces.values() for value in scope.values()):
        raise ValueError("Saved process subclocks must partition the measured boundary")
    return pieces


def price(acquisition, native, saved, named):
    scopes = {}
    for key in TIMES:
        target = named[key]/2
        model = acquisition[key]+saved[key]
        room = target-saved[key]
        scopes[key] = dict(half_original=target, separate_clock_sum=model, gap_to_half=model-target,
                           room_for_acquisition=room, gap_if_native_free=model-target-native[key],
                           percent_acquisition_reduction_with_saved_fixed=100*(acquisition[key]-room)/acquisition[key])
    return scopes


def seal(root):
    from eight_ms_native_score import same_images
    from preloaded_saved_score import science
    from raw_cfo_north_trial import native_file

    binding, clock, execution = (read(root/f"{name}.json") for name in ("binding", "clock", "execution"))
    if binding["sources"] != pins():
        raise ValueError("The frozen sources needed for verification changed")
    old = reference()
    controls = json.loads(staged.checked(PRIOR/"joint-research-receipt.json", PRIOR_RESEARCH_SHA))
    directory = root/"candidate"
    published = read(directory/RECEIPT)
    receipt, identity = published["receipt"], execution["identity"]
    trace = read(directory/"joint-research-receipt.json")
    staged.checked(native_file(directory), identity["native_sha256"][7:])
    if (clock["exit_code"] or published["waveform_calls"] or published["handoffs"] != 1
            or not published["staged_inventory"] or receipt["counts"]["processed"] != 713
            or receipt["counts"]["invalid_capture"] != 95 or identity != old["identity"]):
        raise ValueError("Expected one waveform-free all-visit signed publication on the matched original assignment")
    observed = science(directory, receipt, clock, identity)
    exact = {key: observed[key] == old["science"][key] for key in ("terminal", "arms", "roles", "grid_and_path", "grid_points", "named_finish")}
    exact["images"] = same_images(observed["images"], old["science"]["images"])
    exact["regional"] = [row["result"] for row in trace["early_regional"]] == [row["result"] for row in controls["early_regional"]]
    transfer, = execution["orbit"]["transfers"]
    rank = execution["rank"]["counts"]
    if (transfer["compatibility"]["fallback"] or transfer["loading"]["fallback"] or not transfer["counts"]["sidecar_hit_bodies"]
            or not rank["compact_calls"] or not all(exact.values())):
        raise ValueError(f"The intended paid options or verified weak publication differ from the saved control: {exact}")
    costs = disjoint(clock, execution["phases"], published["solve"], published["layout"]["render"])
    write(root/"seal.json", dict(binding=binding, clock=clock, execution=execution, published=published, parity=exact,
          science=observed, regional=trace["early_regional"], route=trace["route_details"], disjoint_saved_costs=costs,
          prior=dict(clock=old["measured"]["clock"], solve=old["publication"]["solve"], layout=old["publication"]["layout"])))


def score(root):
    from eight_ms_held_score import geographic_reference
    from eight_ms_native_score import outcome
    from leo.contracts.digests import canonical_digest
    from whole_stereo_blocks import load_checked

    saved = read(root/"seal.json")
    original, prior, folder, native_pin = acquired()
    raw_launch = json.loads(staged.checked(folder.parent/"8ms-clock.json", RAW_CLOCK_SHA))
    raw_binding = json.loads(staged.checked(folder.parent/"binding.json", RAW_BINDING_SHA))
    external = load_checked(HERE/"measurements/raw-0016-best.json.gz", NAMED_SHA)
    stock = external["original"]["stock"]
    admission = external["admission"]
    identity = saved["science"]["identity"]
    opportunity = canonical_digest([{k:v for k,v in row.items() if k != "candidates"} for row in original["source"]["probes"]])
    if (native_pin != saved["execution"]["original_native_sha256"] or raw_binding["inventory"] != identity["inventory"]
            or admission["inventory"] != identity["inventory"] or admission["offer_sha256"] != identity["offer_sha256"]
            or admission["cutoff_utc_ns"] != identity["cutoff_utc_ns"] or admission["archive"]["sha256"] != identity["archive"]["snapshots_sha256"]
            or stock["science"]["raw_authority"] != identity["authority"] or raw_launch["status"]
            or stock["process"]["clock"]["exit_code"] or stock["opportunities"] != opportunity
            or any(row["unavailable"] or row["cached_pages"] != row["observed_file_pages"]
                   for row in (stock["process"]["cache_before"], stock["process"]["cache_after"]))):
        raise ValueError("Historic cost transfer must use the original signature and verified resident named raw result")
    budget = prior["receiver_audit"]
    acquire = {"cpu_s": budget["acquire"]["cpu_ns"]/1e9, "elapsed_s": budget["acquire"]["wall_ns"]/1e9}
    native = {key: dict(cpu_s=budget["native"]["native_cpu_ns"][key]/1e9, elapsed_s=budget["native"]["native_wall_ns"][key]/1e9)
              for key in ("full", "short_primary")}
    total_native = {key: sum(row[key] for row in native.values()) for key in TIMES}
    nonnative = {key: acquire[key]-total_native[key] for key in TIMES}
    truth, pin = geographic_reference(CASE)
    offer = identity["original_offer"]
    arms = dict(combined=outcome(saved["science"]["arms"], offer, truth), named=outcome(stock["science"]["arms"], offer, truth))
    report = dict(seal_sha256=sha256((root/"seal.json").read_bytes()).hexdigest(), scientific_arms=arms, reference_sha256=pin,
                  historical_raw_8ms=raw_launch, historical_raw_8ms_acquisition=acquire, historical_acquisition_native=native,
                  historical_acquisition_others=nonnative, original_v3=stock["process"]["clock"],
                  original_v3_file_boundaries=stock["time_boundaries"], recorded_full_source_bytes=admission["compressed_bytes"],
                  model=price(acquire, total_native, saved["clock"], stock["process"]["clock"]))
    write(root/"score.json", report)


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("action", choices=("launch", "worker", "seal", "score"))
    cli.add_argument("root", type=Path)
    options = cli.parse_args()
    dict(launch=launch, worker=worker, seal=seal, score=score)[options.action](options.root)
