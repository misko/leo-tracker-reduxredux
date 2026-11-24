"""Measure the verified original once against the same-build first-map publication."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
PRIOR = "4abf70d6b570c4bd1d2343f584b0c135a4228865261d3e39e8e13350c15f3df2"
ORDER = {"DS30-0107": ("once", "fused"), "DS30-0016": ("fused", "once")}
PROTOCOL = HERE / "legacy-verify-original-protocol.md"


def once_command(command, output):
    result = list(command)
    if "--legacy-first-map-fast" not in result or "--verify-original-once" in result:
        raise ValueError("Need the same exact first-use configuration for both modes")
    for flag in ("--legacy-first-map-replay", "--legacy-first-map-replay-sha256"):
        index = result.index(flag)
        del result[index:index + 2]
    result[result.index("--output") + 1] = str(output)
    return [*result, "--verify-original-once"]


def pins():
    return {path.name: sha256(path.read_bytes()).hexdigest() for path in (Path(__file__), PROTOCOL)}


def launch(root):
    from aperture_trial import write
    import empty_bootstrap as boot
    import legacy_first_map_finalist as finalist
    import raw_0016_best_trial as timing

    ordinary = timing.measure_mode

    def pair(folder, mode, command, env, residency, **options):
        if mode != "fused":
            raise ValueError("Expected the existing complete mapped reference path")
        commands = dict(fused=command, once=once_command(command, folder / "once"))
        began = boot.now()
        probe = subprocess.run([*commands["once"], "--first-map-setup-only"], capture_output=True,
                               text=True, env=env, timeout=15)
        write(folder / "once-probe.json", dict(clock=boot.clock(began), exit=probe.returncode,
              stdout=probe.stdout, stderr=probe.stderr))
        probe.check_returncode()
        result = json.loads(probe.stdout)
        if (not result["reached_scanner"] or result["waveform_opens"]
                or result["audit"]["authority_mode"] != "verified-once" or (folder / "once").exists()):
            raise ValueError("Expected the actual no-map scanner with waveform access blocked")
        order = ORDER[folder.name]
        write(folder / "once-binding.json", dict(order=order, commands=commands, sources=pins()))
        for arm in order:
            ordinary(folder, arm, commands[arm], env, residency, **options)

    with patch.object(timing, "measure_mode", pair):
        finalist.launch(root)


def inspect_once(root, reference, mapped):
    from visit_frame_raw_0016 import read

    acquisition = read(root / "legacy-original-acquisition.json")
    bound = dict(session=reference["session"], inventory=reference["inventory"],
                 windows=sum(row["windows"] for row in mapped["members"]),
                 raw_authority=reference["authority"])
    if (acquisition["authority_mode"] != "verified-once" or acquisition["verified_source"] != bound
            or acquisition["finished_raw_authority"] != reference["authority"]
            or (root / "legacy-first-maps").exists() or (root / "legacy-first-map-acquisition.json").exists()
            or "replay_sha256" in acquisition or "map_publication" in acquisition):
        raise ValueError("Single-use publication did not retain original custody or bypass replay")
    for actual, old in zip(acquisition["members"], mapped["members"], strict=True):
        identity = ("manifest_sha256", "chunk_index", "member_sha256", "index_sha256", "raw_sha256",
                    "first_sequence", "windows", "encoded", "decoded", "owned_window_capacity")
        if (any(actual.get(key) != old.get(key) for key in identity) or actual.get("hash_prefix")
                or any(key in actual for key in ("proof", "block_map_workspace_bytes", "map_reopen", "exceptional_ordinals"))):
            raise ValueError("Original member scope or optional map work changed")
    return acquisition


def score(root):
    import gzip
    import legacy_first_map_finalist as finalist
    from aperture_trial import write
    from empty_bootstrap import checked
    from history_risk_residual_layout_0402 import media_identity
    from legacy_block_0107_score import snapshot as withheld, speedup_gate
    from legacy_block_raw_score import snapshot as complete
    from leo.contracts.digests import canonical_digest
    from publication_media_checks import verify_position_sidecars
    from visit_frame_raw_0016 import read

    prior = json.loads(gzip.decompress(checked(HERE / "measurements/legacy-first-map-finalist.json.gz", PRIOR)))
    finalist.score(root)
    paired = read(root / "finalist.json")
    results = {}
    for case, row in paired["cases"].items():
        folder, req = root / case, paired["admission"]["inputs"][case]["request"]
        book, log = (read(folder / name) for name in ("once-binding.json", "once-clock.json"))
        mapped_output, once = folder / "fused", folder / "once"
        if (book["sources"] != pins() or book["order"] != list(ORDER[case]) or log["clock"]["exit_code"]
                or log["command"] != once_command(row["clock"]["command"], once)
                or book["commands"]["fused"] != row["clock"]["command"] or book["commands"]["once"] != log["command"]):
            raise ValueError("The verified-once clock does not bind the planned same-code comparison")
        baseline = row["science"]
        if case == "DS30-0107":
            current = withheld(once, log["clock"], req)
            parity = ("factors", "graph_proof", "native_digest", "opportunities", "receiver_visits",
                      "scan_digest", "science", "terminal", "witness")
            checks = None
        else:
            current = complete(once, log, req, paired["admission"]["inputs"][case]["producer"])
            parity = ("native_sha256", "native_source", "ordered_owners", "history_risk")
            if (any(current["published"][key] != baseline["published"][key]
                    for key in ("raw_authority", "owners", "arms", "scientific_digests"))
                    or canonical_digest(current["positions"]) != canonical_digest(baseline["positions"])
                    or media_identity(current["images"]) != media_identity(baseline["images"])):
                raise ValueError("Verified-once changed the installed fix or a standard image")
            checks = verify_position_sidecars(mapped_output, once, current["receipt"]["run_id"],
                                               baseline["images"], current["images"])
        if any(current[key] != baseline[key] for key in parity):
            raise ValueError("The verified-once publication changed from the ordinary mapped comparison")
        mapped = read(mapped_output / "legacy-first-map-acquisition.json")
        acquisition = inspect_once(once, req, mapped)
        if acquisition["acceleration"] != mapped["acceleration"]:
            raise ValueError("The timed science configuration or eligible solver work changed")
        results[case] = dict(clock=log, science=current, original=acquisition, sidecars=checks, comparison=book)
    clocks = {case: dict(once=results[case]["clock"]["clock"], mapped=paired["cases"][case]["clock"]["clock"],
                        finalist=prior["cases"][case]["clock"]["clock"], installed=paired["cases"][case]["original"])
              for case in results}
    comparisons = {metric: {label: speedup_gate({case: arms[label][metric] for case, arms in clocks.items()},
                                                {case: arms["once"][metric] for case, arms in clocks.items()})
                            for label in ("mapped", "finalist", "installed")} for metric in ("elapsed_s", "cpu_s")}
    write(root / "verified-once.json", dict(qualified=True, clocks=clocks, comparisons=comparisons,
          checked=results, admission=paired["admission"], same_build_mapped=paired["cases"],
          prediction_seal_sha256=paired["prediction_seal_sha256"]))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("mode", choices=("launch", "score"))
    cli.add_argument("root", type=Path)
    args = cli.parse_args()
    {"launch": launch, "score": score}[args.mode](args.root)
