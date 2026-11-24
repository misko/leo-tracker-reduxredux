"""Freeze and verify one resident North publication with the cold source index."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
SELECTIVE = Path("/dev/shm/leo-v3-continued-north-result01")
SELECTIVE_PINS = {"binding": "ed37b61ea850c8f6eca9362c17a06c97fa141b0323a327ece77bd0285337ac3b",
                  "sealed": "4411ba5508e7cec22d0ded179af3da1d50fc2c8a3e75c235852a646e66dfb424",
                  "clock": "a4f9836e229c68f9878348c10e6c0964846920ef48fb86f91245e27955fcdd06",
                  "score": "5be2a821f7646466ebd261264bea2eb6ab52eb246ea06a6923f8b4b54ea81cae"}
PORTABLE = Path("/dev/shm/leo-v3-portable-orbit-publication-01/result.json")
PORTABLE_PIN = "f052e299962f557ee220b7485f3d356fbdee3b7797ee1bc1217341e57b37c2d2"
FALLBACK = Path("/dev/shm/leo-v3-north-historical-orbits-result01")
FALLBACK_PIN = "d332e7b04bd7712fa296ed5bae941ab978a6d89b2a0f1eecae30eb80ff2b4a8c"
RESEARCH_PIN = "9faf7ab1bbb401e84089ea9a370562e1ca8387838bf23c20ea120584a5eb7154"
HOUR_NS = 3_600_000_000_000


def snapshot_census(snapshots, cutoff):
    result = {}
    for hours in (48, 72):
        rows = [s for s in snapshots if 0 <= cutoff-s.collected_utc_ns <= hours*HOUR_NS]
        bodies = {s.sha256: s.byte_size for s in rows}
        result[str(hours)] = dict(references=len(rows), unique_bodies=len(bodies), total_bytes=sum(s.byte_size for s in rows),
                                  unique_bytes=sum(bodies.values()), body_digests=sorted(bodies))
    return result


def admitted_inputs():
    from empty_bootstrap import checked
    from leo.contracts.digests import canonical_digest
    from leo.operations.tle_archive import TleArchiveReader

    originals = {name: json.loads(checked(SELECTIVE/f"{name}.json", pin)) for name, pin in SELECTIVE_PINS.items()}
    prior = originals["sealed"]
    if (prior["binding_sha256"] != SELECTIVE_PINS["binding"] or prior["clock"] != originals["clock"]
            or originals["score"]["sealed_sha256"] != SELECTIVE_PINS["sealed"]
            or originals["clock"]["exit_code"] or not all(prior["comparisons"].values())):
        raise ValueError("The archived selective control did not complete and verify")
    portable = json.loads(checked(PORTABLE, PORTABLE_PIN))
    if portable["processes"]["candidate"]["exit_code"] or any(row["fallback"] for row in portable["audit"]["attempts"]):
        raise ValueError("The prerequisite saved portable publication is incomplete")
    request = originals["binding"]["request"]
    archive = Path(request["archive"]["root"])
    snapshots = TleArchiveReader(archive).list_snapshots("space-track")
    if (any(not s.path.resolve(strict=True).is_relative_to(archive) for s in snapshots)
            or canonical_digest({s.path.name: s.sha256 for s in snapshots}) != request["archive"]["snapshots_sha256"]):
        raise ValueError("The sealed original North archive inventory changed")
    return originals, snapshot_census(snapshots, request["cutoff_utc_ns"])


def launch(root):
    from continued_cfo_north_trial import control
    from joint_held_north_raw import launch as original_launch

    _, counts = admitted_inputs()
    control()
    if counts["72"]["unique_bodies"] <= 1:
        raise ValueError("A single immutable source body cannot price historical materialization")
    helpers = ("north_orbit_index_raw.py", "north_orbit_index_trial.py", "historical_orbit_index.py", "continued_cfo.py")
    original_launch(root, continued=True, entrypoint=HERE/"north_orbit_index_raw.py",
        trial_protocol=HERE/"north-orbit-index-protocol.md", extra_sources=tuple(HERE/name for name in helpers))


def diagnostics(research):
    route = research["route_details"]
    return dict(probes=[row["result"] for row in research["early_regional"]], exterior=route["exterior"],
                decision=route["decision"], fallback_reason=route.get("reason"), infer_fallback="fallback_clocks" in route,
                orbit_policy=research["solve"]["orbit_policy"])


def score(root, *, retain_broken=False, receiver_source_pin=None):
    from aperture_trial import read, write
    from continued_cfo_north_trial import control, score as existing_score, seal as existing_seal
    from empty_bootstrap import checked
    from joint_held_north_raw import REFERENCE, check_arms, compare_figure, references
    from leo.contracts.digests import canonical_digest
    from north_held_anchor_pair import publication_evidence, tmpfs
    from regional_history_score import one, scientific

    archives, counts = admitted_inputs()
    binding = read(root/"binding.json")

    def verified_source(name, pin):
        path = f"reports/ALGO08/v3/{name}"
        content = subprocess.check_output(["git", "-C", str(HERE.parents[2]), "show", f"{binding['commit']}:{path}"])
        if sha256(content).hexdigest() != pin:
            raise ValueError(f"The frozen scoring input changed for {name}")

    # Process-level paging can include program and library pages. The original
    # signed waveform and its index remain physically backed by resident tmpfs.
    for port in ("recording", "inside_offer"):
        tmpfs(Path(binding["request"][port]))
    tmpfs(Path(binding["request"]["archive"]["root"]))
    existing_seal(root, verified_source=verified_source, allow_resident_process_paging=True,
                  receiver_source_pin=receiver_source_pin)
    existing_score(root)
    new, old = read(root/"sealed.json"), archives["sealed"]
    fallback = json.loads(checked(FALLBACK/"sealed.json", FALLBACK_PIN))
    audit = read(root/"orbits-indexed.json")
    attempt, = audit["attempts"]
    named_binding, original = references()
    named = original["stock"]
    named_folder = REFERENCE/"stock"
    attested_named = publication_evidence(named_folder, named["verified"]["receipt"], named["clock"], named_binding["assignment"])
    attested_named.pop("native")
    named_manifest = read(one(named_folder, "manifest.json"))
    check_arms(named["verified"]["arms"])
    _, all_paid = control()
    prior_research = json.loads(checked(SELECTIVE/"containing/joint-research-receipt.json", RESEARCH_PIN))
    matched_diag = diagnostics(read(root/"containing/joint-research-receipt.json"))
    old_diag = diagnostics(prior_research)
    if retain_broken:
        if (matched_diag["fallback_reason"] != "exterior_evidence_unavailable" or not matched_diag["infer_fallback"]
                or not any(row.get("diagnostic_error", "").startswith("every item must be a Satrec")
                           for row in matched_diag["probes"])):
            raise ValueError("Expected the known misplaced-materialization diagnostic")
    elif matched_diag != old_diag or matched_diag["infer_fallback"] or any("diagnostic_error" in row for row in matched_diag["probes"]):
        raise ValueError("Indexed preparation changed the original exterior diagnostics")
    current = new["raw"]
    if (not attempt["guard"] or attempt["fallback"] is not None or attempt["port"] != "regional"
            or audit["adapter_sha256"] != binding["source_sha256"]["historical_orbit_index.py"]
            or attempt["bodies"] != counts["72"]["unique_bodies"] or not all(new["comparisons"].values())
            or new["candidate"]["native_sha256"] != old["candidate"]["native_sha256"]
            or current["held_anchor_route"] != old["raw"]["held_anchor_route"]
            or current["receipt"]["terminal_sha256"] != old["raw"]["receipt"]["terminal_sha256"]
            or current["receipt"]["terminal_sha256"] != fallback["raw"]["receipt"]["terminal_sha256"]
            or current["receipt"]["region"] != named["verified"]["receipt"]["region"]
            or any(canonical_digest(attested_named[key]) != canonical_digest(named[key])
                   for key in ("grid_points", "verified", "figures", "native_sha256"))
            or any(named_manifest["arms"][arm]["owner_sha256"] != owner for arm, owner in named["verified"]["owners"].items())
            or scientific(root/"containing") != scientific(SELECTIVE/"containing")):
        raise ValueError("The cold index did not activate or changed the sealed selective publication")
    historical = {"selective": dict(clock=old["clock"], phases=old["raw"]["phases"],
                  solve=old["solver"]["solve"], evidence=old["candidate"], roles=old["roles"]),
                  "all_paid": dict(clock=old["controls"]["guarded_clock"], phases=old["controls"]["guarded_phases"],
                                   evidence=all_paid["candidate"], roles=all_paid["owners"]),
                  "named": named}
    write(root/"result.json", dict(candidate_seal_sha256=sha256((root/"sealed.json").read_bytes()).hexdigest(),
        selected_reference_pins=SELECTIVE_PINS, saved_portable_sha256=PORTABLE_PIN, archive_sizes=counts,
        phases=current["phases"], solve=new["solver"]["solve"], clock=new["clock"], audit=audit,
        graph_and_media=new["candidate"], ordered_roles=new["roles"], prior=historical,
        diagnostics=matched_diag, original_diagnostics=old_diag, diagnostic_fallback=retain_broken,
        named_owner_counts={arm: data["associated_points"] for arm, data in named_manifest["arms"].items()},
        named_grid_path_match={name: digest == named["verified"]["scientific_digests"][name]
                               for name, digest in new["candidate"]["verified"]["scientific_digests"].items()},
        named_figures={name: compare_figure(image, named["figures"][name])
                       for name, image in new["candidate"]["figures"].items()},
        score=read(root/"score.json"), comparisons=new["comparisons"], cache=new["cache"],
        fallback=dict(sealed_sha256=FALLBACK_PIN, clock=fallback["clock"], phases=fallback["raw"]["phases"],
                      solve=fallback["solver"]["solve"]),
        source_sha256=sha256(Path(__file__).read_bytes()).hexdigest()))


def preflight():
    from contextlib import nullcontext
    from functools import partial
    from unittest.mock import patch

    import empty_bootstrap
    import joint_publication
    from historical_orbit_index import installed_guard, preparation_port
    from north_orbit_index_raw import bind_runtime

    runtime = empty_bootstrap.load_runtime()
    from leo.operations.tle_archive import TleArchiveReader
    from tools import algo08_position
    from tools.pipeline_eval.variants import algo08_causal_reuse as installed
    from tools.pipeline_eval.variants.experimental.regional_bound_guard import bound_exterior_veto

    source, _ = admitted_inputs()
    reader = TleArchiveReader(Path(source["binding"]["request"]["archive"]["root"]))
    causal = partial(installed.prepare, algo08_position.prepare_native_scan, statistics={})
    audit = {}
    with patch.object(algo08_position, "prepare_native_scan", causal), bound_exterior_veto(reader, terminal_only=True):
        original = algo08_position.prepare_native_scan
        if not installed_guard() or preparation_port(original, installed.prepare) != "regional":
            raise ValueError("The real installed regional wrapper did not qualify")

        def probe(*, raw_context):
            with raw_context(None):
                if algo08_position.prepare_native_scan is original or audit != {"attempts": []}:
                    raise ValueError("The shared publication port did not bind index preparation")

        with (patch.object(empty_bootstrap, "load_runtime", return_value=runtime),
              patch.object(joint_publication, "run", probe), bind_runtime(audit)):
            empty_bootstrap.load_runtime()
            joint_publication.run(raw_context=lambda scan: nullcontext())
        if algo08_position.prepare_native_scan is not original:
            raise ValueError("The probe did not restore the original preparation")
    print("Installed raw publication wrapper activated without archive or waveform reads")


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("mode", choices=("screen", "preflight", "launch", "score"))
    cli.add_argument("root", nargs="?", type=Path)
    cli.add_argument("--retain-broken", action="store_true")
    args = cli.parse_args()
    if args.mode == "screen":
        _, sizes = admitted_inputs()
        print(json.dumps(sizes, indent=2, sort_keys=True))
    elif args.mode == "preflight":
        preflight()
    else:
        if args.root is None:
            cli.error("An output root is required")
        if args.mode == "launch":
            launch(args.root)
        else:
            score(args.root, retain_broken=args.retain_broken)
