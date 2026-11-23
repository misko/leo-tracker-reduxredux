"""Exercise the local-future flag on the tiny warm physical withdrawal control."""

import argparse
from hashlib import sha256
import os
from pathlib import Path
import subprocess

from aperture_trial import read, write
from dense_full_short_raw import checked
from dense_geographic_trial import host
from empty_graph_trial import PAIR, PIN
from full_short_physical import environment
from full_short_raw import RECIPE_SHA
from local_future_pins import checked_dependencies
from short_raw_diagnostic import (
    CACHE_LIB, CACHE_SHA, CASES, HERE, LIBRARIES, RELEASE, FastScanStore, assignment, cache_residency,
    canonical_digest, measure, pairs, require_warm, science, warm_recording,
)


def native_packet(root):
    path, = root.glob("fast-scan-automatic-work/*/detections.json")
    return path


def cache_before(store, recording, manifests, query):
    size = os.sysconf("SC_PAGE_SIZE")
    original = cache_residency.bound_snapshot(store, recording, manifests, size, query)
    warmed = original
    if original["cached_pages"] != original["observed_file_pages"]:
        warm_recording(manifests)
        warmed = cache_residency.bound_snapshot(store, recording, manifests, size, query)
    require_warm(warmed)
    return dict(at_launch=warmed, before_warming=original, explicitly_warmed=warmed is not original)


def policy_evidence(root, mode, expected_native, expected_terminal):
    recipe = read(root / "full-short-recipe.json")
    policy = read(root / "local-future-policy.json")
    dependencies = checked_dependencies()
    if (policy["ingress"] != mode or policy["native_sha256"] != expected_native
            or policy["terminal_sha256"] != expected_terminal or policy["original_receiver_sha256"] != "sha256:" + RECIPE_SHA
            or policy["implementation"] != dependencies or policy["selection_passes"] != {"forward": 1, "reverse": 1}
            or recipe["solver_policy_sha256"] != policy["policy_sha256"]
            or policy["policy_sha256"] != canonical_digest([policy["policy"], dependencies, policy["tracks_sha256"]])
            or policy["status"] != "empty_graph" or policy["solver_preparations"] != 1):
        raise ValueError("Local policy or no-graph solver binding differs")
    return policy


def run(root, short, geo, region_tracks, resume_stock=False):
    settings = host()
    if subprocess.check_output(["findmnt", "-no", "FSTYPE", "-T", root.parent], text=True).strip() != "tmpfs":
        raise ValueError("Use separate experiment roots on tmpfs")
    if resume_stock and ({p.name for p in root.iterdir()} != {"stock", "fonts", "stock.stdout", "stock.stderr", "stock-clock.json"}):
        raise ValueError("Resume requires one already sealed stock arm and an untouched candidate directory")
    case, pin, decision, visits, order = CASES[0]
    if (case, visits, order) != ("DS30-0227", 18, ("stock", "candidate")):
        raise ValueError("Only the frozen tiny physical case is enrolled")
    pair, archived = assignment(case, pin, decision, visits)
    original = read(checked(PAIR / "result.json", PIN))["runs"]["candidate"]
    original_native = original["native_sha256"]
    stock_build = pairs.verified_v3(pairs.NAMED_V3)
    libraries = {kind: dict(path=str(checked(path, LIBRARIES[kind])), sha256=LIBRARIES[kind])
                 for kind, path in (("short", short), ("geographic", geo), ("regional", region_tracks))}
    cache_query = cache_residency.load_query(checked(CACHE_LIB, CACHE_SHA))
    if not resume_stock:
        root.mkdir()
        (root / "stock").mkdir()
    env = environment(root)
    python = RELEASE / "venv/bin/python"
    subprocess.run([python, "-Bc", "from matplotlib import font_manager; font_manager.findfont('DejaVu Sans')"],
                   env=env, check=True, timeout=30)
    store = FastScanStore(root)
    recording = Path(pair["recording"])
    session, inventory_pin, inventory = store.inventory(recording, verify_windows=False)
    if session != archived["receipt"]["session_id"] or inventory["window_count"] != visits:
        raise ValueError("The frozen raw inventory changed")
    manifests = tuple((Path(row["path"]), row["sha256"]) for row in pair["cache_observation"]["manifests"])
    common = ["--recording", recording, "--archive", pair["archive"]["root"], "--region", pair["region"]]
    research = [python, "-BPs", HERE / "full_short_run.py", *common, "--geographic-library", geo,
                "--regional-track-library", region_tracks, "--reuse-cold-track-rows", "--reuse-grid-phase-states",
                "--skip-empty-proof", "--local-future-repair"]
    commands = dict(stock=[pairs.NAMED_V3, *common, "--bulk-root", root / "stock"],
                    candidate=[*research, "--short-binary", short, "--output", root / "candidate"])
    raw = {}
    for arm in order:
        if arm == "stock" and resume_stock:
            raw[arm] = read(root / "stock-clock.json")
            timing = raw[arm]["timing"]
            require_warm(raw[arm]["cache"]["at_launch"])
            if raw[arm]["command"] != list(map(str, commands[arm])):
                raise ValueError("The resumed stock invocation differs from the frozen launch")
        else:
            cache = cache_before(store, recording, manifests, cache_query)
            timing = measure(commands[arm], env, root / arm)
            raw[arm] = dict(timing=timing, cache=cache, command=list(map(str, commands[arm])))
            write(root / f"{arm}-clock.json", raw[arm])
        if timing["exit_code"]:
            raise RuntimeError(f"{arm} failed: {timing['stderr_tail']}")
        raw[arm]["verified"] = science(root, arm, timing, archived, inventory_pin)
    stock, candidate = (raw[arm]["verified"] for arm in order)
    packets = {arm: native_packet(root / arm) for arm in order}
    documents = {arm: read(path) for arm, path in packets.items()}
    metadata = {arm: [dict(row, candidates=[]) for row in doc["source"]["probes"]] for arm, doc in documents.items()}
    if (metadata["stock"] != metadata["candidate"] or candidate["native_sha256"] != original_native
            or candidate["terminal_sha256"] != original["terminal_sha256"] or stock["counts"] != candidate["counts"]
            or any(row["decision"] != decision or row["reason"] != "no_active_curvature"
                   or row["pngs"] for row in (stock, candidate)) or stock["arms"] != candidate["arms"]):
        raise ValueError("The matched warm replay changed admitted raw opportunities or the withheld decision")
    policy = policy_evidence(root / "candidate", "raw", original_native, candidate["terminal_sha256"])
    write(root / "raw-verified.json", dict(raw=raw, solver_policy=policy))
    command = [*research, "--saved", packets["candidate"], "--saved-digest", original_native, "--output", root / "saved"]
    smoke = measure(command, env, root / "saved")
    write(root / "saved-clock.json", smoke)
    if smoke["exit_code"]:
        raise RuntimeError(f"Saved launcher failed: {smoke['stderr_tail']}")
    saved_report = read(root / "saved/joint-research-receipt.json")
    saved_policy = policy_evidence(root / "saved", "saved", original_native, candidate["terminal_sha256"])
    saved_recipe = read(root / "saved/full-short-recipe.json")
    if (native_packet(root / "saved").read_bytes() != packets["candidate"].read_bytes()
            or saved_report["saved_handoff_manifest"] != inventory_pin or saved_recipe["receiver_audit"]
            or saved_report["receipt"]["terminal_sha256"] != candidate["terminal_sha256"]
            or any(saved_policy[key] != policy[key] for key in ("policy_sha256", "forward_sha256", "future_ids"))):
        raise ValueError("Saved handoff changed the original raw/bound policy or issued a waveform callback")
    write(root / "result.json", dict(case=case, machine=settings, storage=dict(publication="tmpfs", input="original signed recording"),
          order=order, issued=visits, raw=raw, original_pair_sha256=pin, stock_build=stock_build, libraries=libraries,
          resumed_unstarted_candidate=resume_stock,
          compared_probe_metadata=len(metadata["stock"]), percent_elapsed=100*raw["candidate"]["timing"]["elapsed_s"]/raw["stock"]["timing"]["elapsed_s"],
          solver_policy=policy, saved=dict(timing=smoke, command=list(map(str, command)), policy=saved_policy,
                                         receipt=saved_report["receipt"], solve=saved_report["solve"], receiver_callbacks=0),
          driver_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
          protocol_sha256=sha256((HERE / "local-future-cli-protocol.md").read_bytes()).hexdigest()))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    for name in ("root", "short", "geo", "region_tracks"):
        cli.add_argument(name, type=Path)
    cli.add_argument("--resume-stock", action="store_true", help="Validate the sealed stock arm and run the unstarted candidate")
    run(**vars(cli.parse_args()))
