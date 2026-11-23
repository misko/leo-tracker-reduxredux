"""Run the maximum-degree-only transfer on authenticated short receiver packets."""

import argparse
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

from aperture_trial import archive_identity, machine, read
from full_short_graph_transfer import inputs
from full_short_raw import RECIPE_SHA
from full_short_run import geographic_projection
from joint_publication import run


def degree_only(config):
    if (config.max_degree, config.min_points, config.points_per_coefficient) != (4, 8, 4):
        raise ValueError("The installed track configuration changed")
    return replace(config, max_degree=2)


def dense_inputs(source):
    from dense_control_clocks import HERE

    common = read(HERE / "measurements/dense-control-clocks.json")["common"]
    binding = read(source / "binding.json")
    if read(source / "process.json")["status"] != 0 or binding["authority"] != common["raw_authority"]:
        raise ValueError("The dense raw publication does not match the archived recording")
    output = source / "publication"
    original = read(output / "joint-research-receipt.json")
    receipt = original["receipt"]
    if receipt["decision"] != "complete" or receipt["region"] != common["region"]:
        raise ValueError("Expected the sealed candidate containing-region fix")
    work = output / "fast-scan-automatic-work"
    terminal = read(work / receipt["run_id"] / "terminal.json")
    packet, = work.glob("*/detections.json")
    return (Path(binding["command"][binding["command"].index("--recording")+1]), common["archive"],
            Path(binding["region"]), packet, terminal["native_sha256"], common["region"])


def replay(case, output, geographic, dense_root, screen):
    host = machine()
    if host["cpu"] != [2] or host["nice"] < 15 or "prio 7" not in host["ionice"] or set(host["threads"].values()) != {"1"}:
        raise ValueError("Use the shared low-priority Gauss slot")
    if case == "dense":
        if screen is None or not read(screen)["passed"]:
            raise ValueError("The physical and missing-region screens must pass first")
        recording, archive, region, packet, pin, offer = dense_inputs(dense_root)
    else:
        recording, archive, region, packet, pin, offer = inputs(case)
    args = SimpleNamespace(recording=recording, archive=Path(archive["root"]), region=region, saved=packet,
                           saved_digest=pin, output=output, verify_images=True, optimized_full_catalogue=True)
    run(args, saved_receiver=RECIPE_SHA, track_config=degree_only, early_regional=True, keep_selected_rows=True,
        geographic_projector=lambda: geographic_projection(geographic))
    report = read(output / "joint-research-receipt.json")
    if report["receipt"]["region"] != offer or report["saved_digest"] != pin or archive_identity(args.archive) != archive:
        raise ValueError("The original archive, region or native packet changed")


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("case", choices=("physical", "south-far", "dense"))
    cli.add_argument("output", type=Path)
    cli.add_argument("geographic", type=Path)
    cli.add_argument("--dense-root", type=Path, default=Path("/var/tmp/leo-full-short-dense-DS30-0008"))
    cli.add_argument("--screen", type=Path)
    args = cli.parse_args()
    replay(args.case, args.output, args.geographic, args.dense_root, args.screen)
