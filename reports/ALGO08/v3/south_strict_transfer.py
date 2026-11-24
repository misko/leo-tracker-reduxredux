"""Transfer the frozen strict packed North entry to the signed original South input."""

import argparse
from collections import Counter
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(HERE), str(ROOT)]
BASE = "0285f1ec4"
SOUTH = Path("/dev/shm/leo-v3-south-adaptive-raw-result01")
NORTH = Path("/dev/shm/leo-v3-north-strict-result02/candidate")
ORDINARY = Path("/dev/shm/leo-v3-eight-ms-south-result01")
TARGET = 1.6
DERIVATIVE_BUDGET = 2_100_000_000
NORTH_RESERVE = 8 * 2**30
PINS = {
    SOUTH / "verified-result.json": "36b84b7be5213f84ec53bd812ecd01555bddc8fd4895d456ec914f91c1ba1449",
    SOUTH / "binding.json": "009b14be3fad0261a91457def4d12f94a4d60f12ac3b0d8c8504554f2d9c479d",
    ORDINARY / "omitted-seal.json": "4818d97f203140b69a9b12a81d692ffbd85c29424fcadb7a9f83ab1d84ffa346",
    ORDINARY / "near-omitted-score.json": "4d62de2deb4adf9dfeb181ce3bbe7b40842c84e5946e2aaa279fccac212b4471",
    ORDINARY / "omitted-recovery-job.json": "232653f8c5f2d6dfb0042473835637f9225b3647164724f248cd644fce4b4209",
}
SOURCES = (Path(__file__), HERE/"south-strict-transfer-protocol.md")
ORIGINAL_SOURCES = ("north_strict_read.py", "adaptive_raw_trial.py", "combined_raw_research.py", "unified_short_bootstrap.py",
                    "packed_combined_input.py", "seekable_member.py", "seekable_eight_raw.py", "ci16_packing.c",
                    "live_adaptive_grid.py", "live_adaptive_grid_entry.py")


def pinned(path):
    from empty_bootstrap import checked

    return json.loads(checked(path, PINS[path]))


def selected_causal(refs, cutoff):
    """All bodies selected by the original 48 h reads and oldest 72 h phase history."""
    earlier, direct = {}, set()
    for ref in sorted(refs):
        age = cutoff - ref.collected_utc_ns
        if 0 <= age <= 48 * 3_600_000_000_000:
            direct.add(ref.path)
        if 0 <= age <= 72 * 3_600_000_000_000:
            earlier.setdefault(ref.sha256, ref.path)
    return direct | set(earlier.values())


def causal_cache(request):
    from leo.operations.tle_archive import TleArchiveReader
    from north_held_anchor_pair import tmpfs

    root = Path(request["archive"]["root"])
    tmpfs(root)
    refs = TleArchiveReader(root).list_snapshots("space-track")
    used = selected_causal(refs, request["cutoff_utc_ns"])
    raw = subprocess.check_output(["fincore", "--json", "--bytes", "-o", "RES,SIZE,FILE", *(ref.path for ref in refs)], text=True)
    rows = json.loads(raw)["fincore"]
    if {Path(row["file"]) for row in rows} != {ref.path for ref in refs}:
        raise ValueError("Incomplete passive snapshot residency")
    missing_used = sum(max(0, row["size"] - row["res"]) for row in rows if Path(row["file"]) in used)
    if not used or missing_used:
        raise ValueError(f"Nonresident in-use causal body bytes: {missing_used}")
    return dict(catalogue_refs=len(rows), catalogue_bytes=sum(row["size"] for row in rows), used_refs=len(used),
                in_use_bytes=sum(row["size"] for row in rows if Path(row["file"]) in used),
                unused_nonresident=[row for row in rows if Path(row["file"]) not in used and row["res"] < row["size"]])


def named_reference(request):
    from empty_bootstrap import checked
    from isolated_salvage_south import ORIGINAL, PAIR_SHA
    from leo.contracts.algo08_region import Algo08Region
    from tools.pipeline_eval.qualification.paired_publication import V3_IDENTITY

    pair = json.loads(checked(ORIGINAL/"pair.json", PAIR_SHA))
    stock = pair["runs"]["candidate"]
    offer = Algo08Region.parse(json.loads(checked(Path(request["offers"]["containing"]),
                                                request["offer_sha256"]["containing"]))).document()
    if (pair["candidate_specification_digest"] != V3_IDENTITY["frozen_specification"]
            or pair["candidate_specification"]["detector_sha256"] != V3_IDENTITY["detector_sha256"]
            or pair["recording"] != request["recording"] or pair["archive"] != request["archive"]
            or stock["receipt"]["region"] != offer or stock["raw_authority"] != request["authority"]):
        raise ValueError("The archived deployed control no longer names the same South assignment")
    return ORIGINAL, stock, offer


def omission_join(request, expected):
    from empty_bootstrap import checked
    from leo.contracts.algo08_region import Algo08Region
    from raw_cfo_north_trial import native_file

    omitted, scored, job = (pinned(ORDINARY/name) for name in ("omitted-seal.json", "near-omitted-score.json", "omitted-recovery-job.json"))
    worker = omitted["saved"]
    persisted = native_file(ORDINARY/"near-omitted")
    offer = Algo08Region.parse(json.loads(checked(Path(request["offers"]["near-omitted"]),
                                                request["offer_sha256"]["near-omitted"]))).document()
    if (job["native_sha256"] != expected["native_sha256"] or worker["native_sha256"] != expected["native_sha256"]
            or worker["detector_recipe_sha256"] != expected["receiver_recipe_sha256"]
            or worker["receipt"]["region"] != offer or worker["receipt"]["session_id"] != request["session"]
            or worker["waveform_calls"] or worker["handoffs"] != 1 or omitted["clock"]["exit_code"]
            or scored["seal_sha256"] != PINS[ORDINARY/"omitted-seal.json"]):
        raise ValueError("The previous omitted offer must bind this actual authorized signed packet")
    digest = expected["native_sha256"]
    checked(persisted, digest[7:])
    return dict(native_sha256=digest, offer=offer, signed_region_sha256=request["offer_sha256"]["near-omitted"],
        persisted_packet=str(persisted), solver_options=omitted["options"], scoring=scored, measured=omitted["clock"],
        geographic_outcome_from_previous_saved_solve=True, output_grid="full grid on the previous saved solve", replayed_here=False)


def preflight(root):
    from adaptive_raw_trial import work
    from empty_bootstrap import checked
    from north_held_anchor_pair import tmpfs
    from raw_cfo_north_trial import native_file

    request, cache = work("south", root)
    raw_before = cache()
    ordinary = pinned(SOUTH/"verified-result.json")
    prior = pinned(SOUTH/"binding.json")
    if not ordinary["passed"] or prior["clip"] != request:
        raise ValueError("Require the previously verified ordinary 20/8 South pipeline and full science")
    checked(native_file(SOUTH/"containing"), ordinary["native_sha256"][7:])
    names, stock, _ = named_reference(request)
    for path in (names, SOUTH, ORDINARY):
        tmpfs(path)
    omitted = omission_join(request, ordinary)
    catalogue = causal_cache(request)
    capacity = shutil.disk_usage(root.parent).free
    memory = int(next(line.split()[1] for line in Path("/proc/meminfo").read_text().splitlines()
                      if line.startswith("MemAvailable:"))) * 1024
    if min(capacity, memory) < DERIVATIVE_BUDGET + NORTH_RESERVE:
        raise ValueError(f"South packing must leave independent North headroom: {capacity=} {memory=}")
    budget = dict(tmpfs_available=capacity, host_available=memory, incremental_budget=DERIVATIVE_BUDGET,
                  untouched_headroom=NORTH_RESERVE)
    return request, cache, dict(original=raw_before, causal=catalogue, space=budget, omission=omitted,
                                prior_named_elapsed_s=stock["elapsed_s"], prior_ordinary_elapsed_s=ordinary["clock"]["elapsed_s"])


def run(root):
    from adaptive_raw_trial import launch, prepare
    from aperture_trial import write
    from dense_geographic_trial import host
    from eight_ms_south_transfer import environment_for
    from north_strict_read import resident_packed, transform
    from short_raw_diagnostic import measure
    from tools.pipeline_eval.qualification.paired_publication import NAMED_V3, verified_v3

    machine = host()
    request, cache, admission = preflight(root)
    git = ["git", "-C", str(ROOT)]
    if subprocess.check_output([*git, "status", "--porcelain", "--untracked-files=no"]).strip():
        raise ValueError("Commit the source and protocol before the one South pair")
    revision = subprocess.check_output([*git, "rev-parse", "HEAD"], text=True).strip()
    if subprocess.check_output([*git, "diff", "--name-only", BASE, "HEAD", "--", *(
            str((HERE/name).relative_to(ROOT)) for name in ORIGINAL_SOURCES)]).strip():
        raise ValueError("The frozen strict, conversion or geometric entry changed")
    root.mkdir(mode=0o700)
    write(root/"plan.json", dict(admission=admission, request=request, revision=revision, frozen_base=BASE,
         machine=machine, order=("candidate", "named"), source_sha256={p.name: sha256(p.read_bytes()).hexdigest() for p in SOURCES}))
    manifest = Path(request["recording"])/"manifest.json"
    clip = request | {"manifests": [{"path": str(manifest), "digest": "sha256:"+request["manifest_sha256"]}]}
    strict, members, codec = transform(root, clip, admission["original"])
    retained = sum(path.lstat().st_size for path in (root/"conversion").rglob("*") if path.is_file())
    if retained > DERIVATIVE_BUDGET or shutil.disk_usage(root.parent).free < NORTH_RESERVE:
        raise ValueError(f"South derivative used {retained} bytes and must leave independent North headroom")
    write(root/"conversion-space.json", dict(derivative_bytes=retained, free_after=shutil.disk_usage(root.parent).free))
    prepare("south", root/"candidate", strict=strict)
    packed = lambda: resident_packed(Path(strict["map"]).parent, members, codec)
    write(root/"packed-before.json", packed())
    write(root/"causal-before.json", causal_cache(request))
    clock = launch(root/"candidate", north=NORTH)
    write(root/"packed-after.json", packed())
    if clock["exit_code"]:
        raise RuntimeError(clock["stderr_tail"])

    named = root/"named"
    named.mkdir()
    (named/"tmp").mkdir()
    shutil.copytree(root/"candidate/fonts", named/"fonts")
    command = [str(NAMED_V3), "--recording", request["recording"], "--archive", request["archive"]["root"],
               "--region", request["offers"]["containing"], "--bulk-root", str(named/"stock")]
    (named/"stock").mkdir()
    write(named/"binding.json", dict(binary=verified_v3(NAMED_V3), command=command, before=cache(),
         causal=causal_cache(request)))
    clock = measure(command, environment_for(named), named/"stock")
    write(named/"clock.json", clock)
    write(named/"after.json", dict(original=cache(), causal=causal_cache(request)))
    if clock["exit_code"]:
        raise RuntimeError(clock["stderr_tail"])


def strict_match(usage, conversion):
    rows, expected = usage["members"], conversion["sections"]
    if (not usage["strict_packed_eight"] or usage["fallback"] is not None or usage["original_windows"]
            or len(rows) != len(expected) or any(
                got["state"] != "strict-packed-eight" or got["encoded_blocks"] != 2*want["original"]["window_count"]
                or got["original_decoded_sha256"] != want["original"]["uncompressed_sha256"]
                or got["checks"]["payload_bytes"] != want["checked_derivative"]["payload_bytes"]
                or got["seek_sha256"] != want["binding"]["seek_sha256"]
                for got, want in zip(rows, expected, strict=True))):
        raise ValueError("Strict input must authenticate all independently verified source members")
    return Counter(value for row in rows for value in row["loads"].values())


def figures(images):
    return {name: (entry["sha256"], entry["rgba_sha256"], tuple(entry["size"])) for name, entry in images.items()}


def score(root):
    from adaptive_raw_trial import RESULT, same_page_counts, score as adaptive_score
    from aperture_trial import read, write
    from eight_ms_south_transfer import KEY_SHA
    from empty_bootstrap import checked
    from joint_publication import artifacts
    from north_held_anchor_pair import publication_evidence
    from south_cfo_route import admissible
    from tools.pipeline_eval.scoring import distance_km

    plan, conversion = (read(root/f"{name}.json") for name in ("plan", "conversion"))
    request = plan["request"]
    seal = root/"candidate"/RESULT
    candidate = read(seal) if seal.exists() else adaptive_score(root/"candidate")
    old = pinned(SOUTH/"verified-result.json")
    raw = read(root/"candidate/containing/unified-short-bootstrap.json")
    usage = raw["packed_ci16_input"]
    apertures = strict_match(usage, conversion)
    if (not candidate["passed"] or candidate["native_sha256"] != old["native_sha256"]
            or any(candidate[key] != old[key] for key in ("owners_sha256", "owner_counts", "arms", "native_calls", "geographic"))
            or not all(candidate["layout"][key] == old["layout"][key] for key in ("sampled", "phase_sha256"))
            or figures(candidate["images"]) != figures(old["images"])
            or apertures != Counter(raw["receiver_audit"]["native"]["visits"])):
        raise ValueError("Strict acquisition changed the earlier ordinary lean pipeline's output")

    named = root/"named"
    clock = read(named/"clock.json")
    original, archived, offer = named_reference(request)
    receipt = json.loads((named/"stock.stdout").read_text().splitlines()[-1])
    assignment = dict(session=request["session"], inventory=request["inventory"], offered_region=offer, stock=archived)
    fresh = publication_evidence(named/"stock", receipt, clock, assignment)
    fresh.pop("native")
    historical = artifacts(original/"candidate", archived["receipt"])
    if (fresh["native_sha256"] != request["packets"]["named"]["native_sha256"] or fresh["cutoff_utc_ns"] != request["cutoff_utc_ns"]
            or fresh["grid_points"] != 137 or figures(fresh["figures"]) != figures(historical["images"])
            or fresh["verified"]["receipt"]["terminal_sha256"] != archived["receipt"]["terminal_sha256"]
            or any(fresh["verified"][key] != archived[key] for key in ("arms", "owners", "scientific_digests"))):
        raise ValueError("Fresh installed control changed the archived South science or official products")
    before = read(named/"binding.json")["before"]
    after = read(named/"after.json")["original"]
    if not all(admissible(cache) for cache in (before, after)) or not same_page_counts(before, after):
        raise ValueError("Original recording residency changed during the fresh named arm")

    key = json.loads(checked(HERE.parent/"regional-release/scoring-key.json", KEY_SHA))
    truth, = {tuple(row["truth"]) for row in key["answers"].values() if row["recording"] == Path(request["recording"]).name}
    science = {name: {arm: dict(latlon=row["latlon"], rf_rms_hz=row["rf_rms_hz"],
                         horizontal_error_km=distance_km(truth, row["latlon"])) for arm, row in arms.items()}
               for name, arms in (("candidate", archived_candidate_arms(root, candidate)), ("named", fresh["verified"]["arms"]))}
    paid = conversion["total_including_compiler_and_verification"]["wall_ns"] / 1e9
    wall, fresh_wall, prior = candidate["clock"]["elapsed_s"], clock["elapsed_s"], archived["elapsed_s"]
    write(root/"result.json", dict(plan=plan, conversion=conversion, candidate=candidate, named=fresh,
        named_clock=clock, historical_named_clock_s=prior, paired_savings=price(wall, fresh_wall, prior, paid),
        both_arms=science, apertures=apertures, strict_members=usage, original_pages_named=dict(before=before, after=after),
        conversion_space=read(root/"conversion-space.json"),
        inherited_omission=plan["admission"]["omission"], packed_exact=True, no_new_omitted_launch=True))


def archived_candidate_arms(root, candidate):
    """Use terminal conditional RMS, separate from the all-owned plot residuals."""
    from aperture_trial import read

    run = candidate["receipt"]["run_id"]
    return read(root/"candidate/containing/fast-scan-automatic-work"/run/"terminal.json")["arms"]


def price(candidate, fresh, archived, conversion):
    first = candidate+conversion
    return dict(prebuilt_s=candidate, fresh_named_s=fresh, archived_named_s=archived, paid_conversion_s=conversion,
                first_use_s=first, prebuilt_vs_fresh=fresh/candidate, prebuilt_vs_archived=archived/candidate,
                first_use_vs_fresh=fresh/first, first_use_vs_archived=archived/first,
                clears_fresh_1_6x=fresh/candidate >= TARGET, clears_archived_1_6x=archived/candidate >= TARGET)


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("action", choices=("preflight", "run", "score"))
    cli.add_argument("root", type=Path)
    args = cli.parse_args()
    if args.action == "preflight":
        print(json.dumps(preflight(args.root)[2], sort_keys=True))
    else:
        (run if args.action == "run" else score)(args.root)
