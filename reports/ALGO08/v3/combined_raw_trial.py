"""Verify one resident North combination and prepare the original DS30-0016 pair."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from combined_raw_research import Portable


BASELINE = Path("/dev/shm/leo-v3-north-historical-orbits-result03/result.json")
BASELINE_PIN = "459d5355ad522fe0637d0e23834665fd978f35a91dae49e838b947abcdde1cdf"
PRODUCER = Portable(Path("/dev/shm/leo-v3-portable-orbit-prep-02/dense-orbits.bin"),
    "sha256:fc51655ff19185cc382aeed925e466cea7290453256d45f80446aceef6f9e30e",
    "c1c2f5d911c978ad7673a2a53f05e272806f87c539f2f0a552b7e02916fe9c8b")
ENTRY = HERE/"combined_raw_research.py"
SOURCES = (ENTRY.name, Path(__file__).name, "combined-raw-protocol.md", "north_orbit_index_raw.py",
           "historical_orbit_index.py", "portable_orbit_index.py", "portable_orbit_compatibility.py",
           "catalogue_block_port.py", "catalogue_block_rank.py", "catalogue_block_bound.py", "cold_track_row_entry.py",
           "continued_cfo.py")


def flags(portable):
    return ["--catalogue-block-rank", *(() if portable is None else portable.arguments())]


def source_at(commit, name, pin):
    root = HERE.parents[2]
    path = f"reports/ALGO08/v3/{name}"
    data = subprocess.check_output(["git", "-c", f"safe.directory={root}", "-C", str(root), "show", f"{commit}:{path}"])
    if sha256(data).hexdigest() != pin:
        raise ValueError(f"Archived source does not match its authenticated pin: {name}")


def checked_producer(cutoff, eligible=None):
    from empty_bootstrap import checked

    producer = json.loads(checked(PRODUCER.file.parent/"artifact-bind.json", PRODUCER.producer_sha256))
    checked(PRODUCER.file, PRODUCER.sha256[7:])
    if producer["portable_sha256"] != PRODUCER.sha256 or producer["source"]["cutoff_utc_ns"] >= cutoff:
        raise ValueError("A signed producer must bind this index and predate the current recording")
    bodies = set(producer["source"]["body_digests"])
    return dict(producer_sha256=PRODUCER.producer_sha256, artifact_sha256=PRODUCER.sha256,
                producer_cutoff_utc_ns=producer["source"]["cutoff_utc_ns"], consumer_cutoff_utc_ns=cutoff,
                overlapping_bodies=len(bodies & set(eligible)) if eligible is not None else None)


def north_launch(root):
    from empty_bootstrap import checked
    from joint_held_north_raw import launch
    from north_orbit_index_trial import admitted_inputs

    controls, census = admitted_inputs()
    baseline = json.loads(checked(BASELINE, BASELINE_PIN))
    producer = checked_producer(controls["binding"]["request"]["cutoff_utc_ns"], census["72"]["body_digests"])
    if (baseline["solve"]["cold_track_rows"]["shared_ranks"] != 1 or baseline["diagnostics"]["infer_fallback"]
            or producer["overlapping_bodies"] == 0):
        raise ValueError("Saved North scope lacks an admitted rank or causal portable source overlap")
    launch(root, continued=True, entrypoint=ENTRY, trial_protocol=HERE/"combined-raw-protocol.md",
           extra_sources=tuple(HERE/name for name in (*SOURCES, "north_orbit_index_trial.py")), experiment_flags=flags(PRODUCER))


def north_score(root):
    from aperture_trial import read, write
    from empty_bootstrap import checked
    from north_orbit_index_trial import admitted_inputs, score

    archived, _ = admitted_inputs()
    expected_source = archived["sealed"]["raw"]["receiver_recipe"]["continued_cfo"]["wrapper_sha256"]
    binding = read(root/"binding.json")
    raw = read(root/"containing/unified-short-bootstrap.json")
    source_at(binding["commit"], "continued_cfo.py", expected_source)
    if raw["receiver_recipe"]["continued_cfo"]["wrapper_sha256"] != expected_source:
        raise ValueError("The executed continuation source differs from the prior guarded receiver")
    # Early launch receipts pinned the combined shim and the actual receiver
    # recipe, but did not separately enumerate its continuation import.
    score(root, receiver_source_pin=expected_source)
    observed = read(root/"result.json")
    prior = json.loads(checked(BASELINE, BASELINE_PIN))
    rank = read(root/"catalogue-block-rank.json")
    preparation = observed["audit"]
    transfer, = preparation["transfers"]
    producer = checked_producer(observed["graph_and_media"]["cutoff_utc_ns"], observed["archive_sizes"]["72"]["body_digests"])
    if (transfer["compatibility"]["fallback"] or transfer["loading"]["fallback"]
            or transfer["counts"]["sidecar_hit_bodies"] != producer["overlapping_bodies"]
            or transfer["counts"]["invalid_bodies"] or not rank["requested"]
            or observed["diagnostics"] != prior["diagnostics"]
            or observed["ordered_roles"] != prior["ordered_roles"]
            or observed["graph_and_media"]["verified"]["scientific_digests"] != prior["graph_and_media"]["verified"]["scientific_digests"]
            or observed["graph_and_media"]["figures"] != prior["graph_and_media"]["figures"]
            or raw["raw_acquisitions"] != 1 or raw["verified_handoffs"] != 1):
        raise ValueError("The combined publication failed portable activation or changed the signed proof or published science")
    write(root/"combined-raw-result.json", dict(signed_reference=BASELINE_PIN, controls=prior["clock"],
          candidate=observed, rank=rank, producer=producer, graph_proof=raw["graph_proof"],
          index_sha256=sha256((root/"orbits-indexed.json").read_bytes()).hexdigest(),
          rank_sha256=sha256((root/"catalogue-block-rank.json").read_bytes()).hexdigest(),
          raw_receipt_sha256=sha256((root/"containing/unified-short-bootstrap.json").read_bytes()).hexdigest()))


def physical_plan(root, stage, *, portable=None):
    from guarded_cfo_0016_raw import CASE, ORIGINAL, ORDER, RECORDING, RECIPE, commands, upstream
    from tools.pipeline_eval.qualification.paired_publication import NAMED_V3, verified_v3

    _, pack, pack_pin, admission = upstream(verify_historical_source=source_at)
    named = verified_v3(NAMED_V3)
    producer = None if portable is None else checked_producer(ORIGINAL.cutoff_ns)
    argv = commands(root, pack, NAMED_V3, candidate_entry=ENTRY, candidate_options=flags(portable))
    return dict(case=CASE.id, order=ORDER, output=str(root), recording=str(RECORDING), stage_receipt=str(stage/"staging.json"),
                orbit_mode="cold" if portable is None else "portable", producer=producer, pack_sha256=pack_pin, receiver_recipe_sha256=RECIPE,
                offer=admission["offer"], offer_sha256=admission["offer_sha256"], archive=admission["archive"],
                native_library_sha256=admission["library_sha256"], inventory=ORIGINAL.inventory, named=named,
                combined_raw_sources={name: sha256((HERE/name).read_bytes()).hexdigest() for name in SOURCES},
                commands={mode: list(map(str, command)) for mode, command in argv.items()})


def physical_launch(root, stage, *, portable=None):
    from guarded_cfo_0016_raw import launch

    # The pair's existing launch verifies the full stage and read-only mount
    # before looking up the original tree. Planning itself stays saved-only.
    if not (stage/"staging.json").is_file():
        raise ValueError("No authenticated full DS30-0016 stage exists")
    plan = physical_plan(root, stage, portable=portable)
    launch(root, stage, candidate_entry=ENTRY, candidate_options=flags(portable),
           verify_historical_source=source_at, combined_raw_sources=plan["combined_raw_sources"])


def small_launch(root):
    from guarded_cfo_small_raw import launch

    sources = {name: sha256((HERE/name).read_bytes()).hexdigest() for name in SOURCES}
    launch(root, candidate_entry=ENTRY, candidate_options=flags(PRODUCER), verify_historical_source=source_at,
           combined_raw_sources=sources)


def small_score(root):
    from aperture_trial import read, write
    from guarded_cfo_small_raw import verify

    verified = root/"verified.json"
    verify(root, verified, verify_historical_source=source_at)
    result = read(verified)
    orbit = read(root/"orbits-indexed.json")
    rank = read(root/"catalogue-block-rank.json")
    raw = read(root/"candidate/unified-short-bootstrap.json")
    if (orbit["requested"] != "portable" or "transfers" in orbit or orbit.get("attempts")
            or rank["status"] != "no_compatible_rank_scope" or not rank["requested"]
            or any(rank.get("counts", {}).values()) or raw["raw_acquisitions"] != 1 or raw["verified_handoffs"] != 1):
        raise ValueError("The withheld path unexpectedly paid preparation, portable loading or rank work")
    write(root/"combined-raw-result.json", dict(result=result, orbit=orbit, rank=rank, raw=raw,
          verifier_sha256=sha256(verified.read_bytes()).hexdigest()))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("mode", choices=("north-launch", "north-score", "physical-plan", "physical-launch", "small-launch", "small-score"))
    cli.add_argument("root", type=Path)
    cli.add_argument("--stage", type=Path, default=Path("/dev/shm/leo-v3-guarded-selective-0016-stage01"))
    cli.add_argument("--with-portable", action="store_true")
    args = cli.parse_args()
    if args.mode == "north-launch":
        north_launch(args.root)
    elif args.mode == "north-score":
        north_score(args.root)
    elif args.mode == "physical-plan":
        print(json.dumps(physical_plan(args.root, args.stage, portable=PRODUCER if args.with_portable else None), indent=2))
    elif args.mode == "physical-launch":
        physical_launch(args.root, args.stage, portable=PRODUCER if args.with_portable else None)
    else:
        (small_launch if args.mode == "small-launch" else small_score)(args.root)
