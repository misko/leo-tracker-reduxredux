"""Time the real strict packed and orbit-health raw CLI against installed ALGO08v3."""

import argparse
import gzip
from hashlib import sha256
import json
from pathlib import Path
import shutil
import sys


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.append(str(HERE.parents[2]))
RAW_RISK = "ff335cb69524253255168c93138497639e3342ab615a602d0d502aab873ff75b"
SOURCE_NAMES = (Path(__file__).name, "strict-history-raw-protocol.md", "exact_named_raw.py",
                "exact_named_raw_transfer.py", "unified_short_bootstrap.py", "packed_combined_input.py",
                "seekable_eight_raw.py", "seekable_member.py", "ci16_packing.py", "ci16_packing.c",
                "history_risk_route.py")


def read(path):
    return json.loads(path.read_bytes())


def sources():
    return {name: sha256((HERE/name).read_bytes()).hexdigest() for name in SOURCE_NAMES}


def controls():
    from empty_bootstrap import checked
    from north_strict_reverse import FIRST, FIRST_RECEIPT, sealed_conversion

    strict = json.loads(gzip.decompress(checked(HERE/"measurements/north-strict-read.json.gz", FIRST_RECEIPT)))
    _, conversion = sealed_conversion(strict, FIRST)
    routed = json.loads(gzip.decompress(checked(HERE/"measurements/history-risk-raw.json.gz", RAW_RISK)))
    return strict, conversion, routed


def launch(root):
    from empty_bootstrap import clock, now

    start = now()
    from exact_named_raw import parser, staged_path, write
    from exact_named_raw_transfer import referenced_binding
    from eight_ms_south_transfer import environment_for
    from history_risk_raw_trial import without_prebuilt
    from north_strict_reverse import admitted_derivative
    from portable_orbit_index_trial import local_launcher_tools

    local_launcher_tools()
    from short_raw_diagnostic import measure

    staged_path(root.parent)
    strict, conversion, routed = controls()
    raw_job = routed["raw"]["binding.json"]["value"]
    source_root, original_snapshot, _, job = referenced_binding(root)
    if (job["request"] != strict["publication"]["plan"]["clip"] or job["request"] != raw_job["request"]
            or job["machine"] != raw_job["machine"] or job["machine"] != strict["publication"]["plan"]["machine"]):
        raise ValueError("The original recorded region, members or CPU settings differ from the sealed North controls")
    args = without_prebuilt(job["candidate_args"])
    request = conversion["request"]
    packed_args = ["--history-risk-route", "--strict-packed-eight", "--packed-ci16-map", request["map"],
                   "--packed-ci16-map-sha256", request["map_sha256"], "--packed-ci16-codec", request["codec"]]
    parser().parse_args([*args, *packed_args])
    root.mkdir()
    (root/"tmp").mkdir()
    shutil.copytree(source_root/"fonts", root/"fonts")
    prefix = ["/usr/bin/timeout", "--kill-after=2s", "75s", sys.executable, "-IB"]
    commands = {
        "named": [*prefix, __file__, "named", str(root)],
        "candidate": [*prefix, str(HERE/"exact_named_raw.py"), *args, *packed_args],
    }
    common_setup = clock(start)
    stage = now()
    packed_before, packed_snapshot = admitted_derivative(conversion)
    packed_setup = clock(stage)
    write(root/"binding.json", dict(request=job["request"], machine=job["machine"], commands=commands,
        sources=sources(), common_setup=common_setup, packed_setup=packed_setup, packed_before=packed_before,
        conversion=request, routed_control=RAW_RISK))
    env = environment_for(root)
    for mode, command in commands.items():
        scope = now()
        before = original_snapshot()
        if mode == "candidate":
            packed_before = packed_snapshot()
        before_snapshot = clock(scope)
        observed = measure(command, env, root/mode)
        write(root/f"{mode}-clock.json", observed)
        write(root/f"{mode}-residency.json", dict(original_before=before, original_after=original_snapshot(),
            packed_before=packed_before if mode == "candidate" else None,
            packed_after=packed_snapshot() if mode == "candidate" else None, admission=before_snapshot))
        if observed["exit_code"]:
            raise RuntimeError(observed["stderr_tail"])


def named_worker(root):
    from exact_named_raw_transfer import named

    binding = read(root/"binding.json")
    if binding["sources"] != sources():
        raise ValueError("The fresh named control no longer matches its frozen adapter")
    named(root, binding)


def packed_integrity(usage, conversion):
    from collections import Counter

    expected, rows = conversion["sections"], usage["members"]
    if (usage["strict_packed_eight"] is not True or usage["fallback"] is not None or usage["original_windows"]
            or usage["map_sha256"] != conversion["request"]["map_sha256"] or len(rows) != len(expected)
            or any(row["state"] != "strict-packed-eight"
                   or row["encoded_blocks"] != 2*spec["original"]["window_count"]
                   or row["original_decoded_sha256"] != spec["original"]["uncompressed_sha256"]
                   or row["checks"]["payload_bytes"] != spec["checked_derivative"]["payload_bytes"]
                   or row["seek_sha256"] != spec["binding"]["seek_sha256"] for row, spec in zip(rows, expected, strict=True))):
        raise ValueError("Expected strict complete authentication of every derivative member and block")
    return dict(encoded=sum(x["checks"]["payload_bytes"] for x in rows),
        encoded_blocks=sum(x["encoded_blocks"] for x in rows), decoded=sum(x["checks"]["decoded_bytes"] for x in rows),
        apertures=dict(Counter(value for row in rows for value in row["loads"].values())), members=len(rows))


def score(root):
    from empty_bootstrap import load_runtime
    from eight_ms_held_score import geographic_reference, owner_differences
    from exact_named_raw import ARM_NAMES, write
    from exact_named_raw_transfer import RAW_PACKET, authenticate_packet
    from history_risk_raw_trial import prior_controls
    from raw_cfo_north_trial import STOCK_PACKET

    _, specification, _, _, _ = load_runtime()
    from leo.contracts.digests import canonical_digest
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
    from tools.pipeline_eval.scoring import distance_km

    strict, conversion, routed = controls()
    exact, _, previous = prior_controls()
    same = routed["raw"]["verified-result-grid.json"]["value"]
    job = read(root/"binding.json")
    req = job["request"]
    clocks = {key: read(root/f"{key}-clock.json") for key in ("named", "candidate")}
    residency = {key: read(root/f"{key}-residency.json") for key in clocks}
    if job["sources"] != sources() or any(row["exit_code"] for row in clocks.values()):
        raise ValueError("The comparison must contain the two frozen through-exit children")
    raw = read(root/"candidate/unified-short-bootstrap.json")
    observed = read(root/"candidate/exact-named-raw-witness.json")
    named = read(root/"named/named-raw-witness.json")
    ports, risk = observed["ports"], observed["ports"]["history_risk"]
    authenticate_packet(root/"named", req, STOCK_PACKET, specification["detector_sha256"])
    authenticate_packet(root/"candidate", req, RAW_PACKET, raw["detector_recipe_sha256"][7:])
    acquisition = packed_integrity(raw["packed_ci16_input"], conversion)
    old_raw = routed["raw"]["candidate/unified-short-bootstrap.json"]["value"]
    identity = ("native_sha256", "detector_recipe_sha256", "receiver_recipe", "archive_root", "causal_cutoff_utc_ns",
                "requested_offer_sha256", "clock_anchor", "raw_acquisitions", "verified_handoffs")
    named_ref = exact["named/named-raw-witness.json"]["value"]
    evidence = observed["evidence"]
    same_evidence = same["witness"]["evidence"]
    if (any(raw[attr] != old_raw[attr] for attr in identity) or raw["raw_acquisitions"] != 1 or raw["verified_handoffs"] != 1
            or acquisition["apertures"] != raw["receiver_audit"]["native"]["visits"] or raw["scientific_imports_before"]
            or named["evidence"]["detail"]["terminal_sha256"] != named_ref["evidence"]["detail"]["terminal_sha256"]
            or named["evidence"]["images"] != named_ref["evidence"]["images"]
            or named["evidence"]["owner_rows"] != named_ref["evidence"]["owner_rows"]
            or raw["receipt"]["region"] != named["receipt"]["region"] or raw["route"] != "history_risk_installed"
            or any(len(ports["history"][name]) != 1 for name in ("prepare", "infer", "exterior_proof"))
            or risk["inference_calls"] != 1 or observed["solver_recipe"]["orbit_index"] != "cold"
            or risk["choice"]["route"] != "lean" or risk["lean_attempts"][0]["named_survivor_fit"]["status"] != "accepted"
            or risk["boundary_checks"] != same["route"]["boundary_checks"]):
        raise ValueError("The original observation authority, held route, both fits and paid late guard must match")
    clock_setup = {mode: data["admission"]["elapsed_s"] for mode, data in residency.items()}
    for data in residency.values():
        for when in ("original_before", "original_after"):
            if any(c["cached_pages"] != c["observed_file_pages"] or c["unavailable"] for c in data[when].values()):
                raise ValueError("An original member stopped being resident")
    if any(residency["candidate"][k]["cached_pages"] != job["packed_before"]["cached_pages"]
           for k in ("packed_before", "packed_after")):
        raise ValueError("The verified packed archive stopped being resident")
    run = raw["receipt"]["run_id"]
    stock_root = Path(routed["raw"]["binding.json"]["value"]["command"][
        routed["raw"]["binding.json"]["value"]["command"].index("--output")+1])
    grid = FastStandardAnalysisStore(root/"candidate").position_grid(run)
    standard = FastStandardAnalysisStore(stock_root).position_grid(run)
    if (canonical_digest(grid) != evidence["sidecars"]["grid"]
            or canonical_digest(standard) != same_evidence["sidecars"]["grid"]
            or {k:v for k,v in grid.items() if k != "elapsed_seconds"}
            != {k:v for k,v in standard.items() if k != "elapsed_seconds"}
            or evidence["sidecars"]["path"] != same_evidence["sidecars"]["path"]
            or evidence["images"] != same_evidence["images"]
            or evidence["owner_rows"] != same_evidence["owner_rows"]
            or evidence["detail"]["terminal_sha256"] != same_evidence["detail"]["terminal_sha256"]
            or grid["evaluated_points"] != 137 or not grid["complete"] or len(evidence["images"]) != 8):
        raise ValueError("Every science and standard figure value must match the independent same-route control")
    truth, reference = geographic_reference("north")
    terminal = read(root/"candidate"/"fast-scan-automatic-work"/run/"terminal.json")
    if canonical_digest(terminal) != raw["receipt"]["terminal_sha256"] or set(terminal["arms"]) != set(ARM_NAMES):
        raise ValueError("Both signed calibration outcomes must bind to the verified terminal")
    arms = {arm: dict(value, error_km=distance_km(truth, value["latlon"])) for arm, value in terminal["arms"].items()}
    wall = clocks["candidate"]["elapsed_s"]
    migrated = conversion["total_including_compiler_and_verification"]["wall_ns"]/1e9
    denominators = dict(fresh_named=clocks["named"]["elapsed_s"], prior_pure_installed=routed["compared"]["separate_installed"]["reference_seconds"],
        prior_verified_installed=previous["clocks"]["named"]["elapsed_s"], original_format_risk=same["clock"]["elapsed_s"])
    ready_overhead = job["packed_setup"]["elapsed_s"] + clock_setup["candidate"]
    ratios = {label: dict(ready=old/wall, ready_with_packed_admission=old/(wall+ready_overhead),
                           charged_legacy_first_use=old/(wall+migrated+ready_overhead)) for label, old in denominators.items()}
    write(root/"result.json", dict(clocks=clocks, setup=dict(common=job["common_setup"], packed=job["packed_setup"], residency=clock_setup),
        original_input=dict(compressed_bytes=req["compressed_bytes"], decoded_bytes=req["decoded_bytes"], members=len(conversion["sections"])),
        derivative=acquisition, migration=conversion["total_including_compiler_and_verification"], denominators=denominators,
        wall_ratios=ratios, region=raw["receipt"]["region"], reference_sha256=reference, arms=arms,
        named_arms=previous["runs"]["named"]["arms"], witness=observed, original_format_risk=same["raw_phases"],
        owners={arm: owner_differences(named["evidence"]["owner_rows"][arm], evidence["owner_rows"][arm]) for arm in ARM_NAMES},
        candidate_raw=raw, same_routed_science=True,
        named=named, residency=residency, scope="resident original North simulation"))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("launch", "named", "score"))
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    {"launch": launch, "named": named_worker, "score": score}[args.action](args.root)
