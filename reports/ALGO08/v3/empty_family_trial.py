"""Replay the two failed 0340 detector handoffs and a previously successful 0016 fix."""

import argparse
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


SOURCES = {
    "0340": ("/dev/shm/leo-v3-raw-combined-0340-result01",
             "865d739da0c028c0b14f7ef8100c8026e50cd781841b0d60fc69fe96aa4eb82c"),
    "0016": ("/dev/shm/leo-v3-raw-cfo-0016-result03",
             "7fd4978443af6de439cfc60d53f2660ff2fd64dd95494f3dd2877d9592563d3b"),
}
REFINED = "701c05ac380d8c1b4b528ddbfd6925d1c13dd9b1832dbe2959f52c3177065d66"


def trial(case, arm, output, *, score_only=False):
    from empty_bootstrap import bind_native, checked, load_runtime

    _, spec, _, publication, _ = load_runtime()
    from aperture_trial import archive_identity
    from cumulative_grid_projection import saved_inventory_port
    from leo.contracts.digests import canonical_digest
    import joint_publication
    from unified_short_bootstrap import Handoff, publish_active

    location, pin = SOURCES[case]
    root = Path(location)
    seal = json.loads(checked(root / "prediction-seal.json", pin))
    admission = json.loads(checked(root / "admission.json", seal["admission.json"]))
    if case == "0016" and arm != "candidate":
        raise ValueError("The refined 0016 release receipt contains only the candidate")
    def sealed(name):
        (key,) = [k for k in seal if k.startswith(arm + "/") and Path(k).name == name]
        return json.loads(checked(root / key, seal[key]))

    native = sealed("detections.json")
    session, inventory = admission["session"], admission["inventory"]
    detector = REFINED if arm == "candidate" else spec["detector_sha256"]
    bind_native(native, session, inventory, detector)
    offer = root / "offer.json"
    checked(offer, admission["offer_sha256"])
    if (native["source"]["raw_recording_authority_digest"] != admission["raw_authority"]
            or native["clock_anchor"]["before"]["realtime_ns"] != admission["cutoff_utc_ns"]
            or archive_identity(root / "tle")["snapshots_sha256"] != admission["archive"]["sha256"]):
        raise ValueError("Original recording authority, acquisition time or causal archive changed")
    manifest = root / arm / "fast-scan-inputs" / (session + ".json")
    request = dict(session=session, inventory=inventory, recording=admission["recording"],
                   saved_inventory=str(manifest), receiver="named-v3" if arm == "stock" else "refined-20-12")
    args = SimpleNamespace(recording=Path(admission["recording"]), archive=root / "tle",
                           region=offer, output=output, one_pass_web_png=True, exact_graph_reuse=True,
                           reuse_verified_png_reads=True, direct_residual_figures=True, direct_orbit_figures=True,
                           named_survivor_finish=True, withhold_empty_family_calibration=True,
                           geographic_library=root / "geographic.so", regional_track_library=root / "regional.so",
                           frontier_block_library=root / "block.so", grid_feature_projection_library=root / "projection.so")
    handoff = Handoff(session, inventory, detector, native)
    if not score_only:
        with saved_inventory_port(request):
            if arm == "stock":
                args.saved = args.saved_digest = None
                args.stock_control = args.verify_images = True
                with patch.object(joint_publication, "configuration", return_value=(publication, dict(spec, startup="stock"))):
                    joint_publication.run(args, raw_context=handoff.install, keep_selected_rows=True)
            else:
                publish_active(args, publication, spec, handoff, {}, graph_audit={}, png_read_audit={})
        if handoff.calls != 1:
            raise ValueError("Expected one authenticated saved handoff")
    result = json.loads((output / "joint-research-receipt.json").read_bytes())
    (terminal_path,) = output.rglob("terminal.json")
    terminal = json.loads(terminal_path.read_bytes())
    if (terminal["session_id"] != session or terminal["native_sha256"] != canonical_digest(native)
            or terminal["region"] != admission["offer"]):
        raise ValueError("Terminal does not bind the original native packet and region")
    proof = result["empty_family_calibration"]
    figures = result["evidence"]["images"]
    summary = dict(case=case, arm=arm, publication_s=result["publication_elapsed_s"],
                   cpu_s=result["publication_cpu_s"], terminal=terminal, proof=proof,
                   pngs=len(figures), native_sha256=canonical_digest(native),
                   waveform_reads=0, source_seal_sha256=pin, guard_sha256=result["source_sha256"]["empty_family_calibration.py"])
    if case == "0340":
        if (len(proof) != 1 or proof[0]["independent_rows"] != 0 or terminal["decision"] != "withheld"
                or terminal["reason"] != "no_independent_family_calibration" or figures
                or any(a["latlon"] is not None for a in terminal["arms"].values())
                or any(result["selected_rows"].values())):
            raise ValueError("Expected a witnessed empty independent calibration and no published fix")
    else:
        old = sealed("joint-research-receipt.json")
        old_grid = sealed("position-grid.json")["document"]
        (grid_file,) = output.rglob("position-grid.json")
        new_grid = json.loads(grid_file.read_bytes())["document"]
        for grid in (old_grid, new_grid):
            del grid["elapsed_seconds"]
        summary.update(unchanged_terminal=terminal == sealed("terminal.json"),
                       unchanged_owners=result["selected_rows"] == old["selected_rows"],
                       unchanged_images=figures == old["evidence"]["images"],
                       unchanged_scientific_grid=new_grid == old_grid,
                       unchanged_path=result["evidence"]["path"] == old["evidence"]["path"])
        if proof or len(figures) != 8 or not all(v for k, v in summary.items() if k.startswith("unchanged_")):
            raise ValueError("The opt-in changed the positive control")
    (output / "calibration-trial.json").write_text(json.dumps(summary, indent=2) + "\n")


if __name__ == "__main__":
    cmd = argparse.ArgumentParser(description=__doc__)
    cmd.add_argument("case", choices=SOURCES)
    cmd.add_argument("arm", choices=("candidate", "stock"))
    cmd.add_argument("output", type=Path)
    cmd.add_argument("--score-only", action="store_true")
    opts = cmd.parse_args()
    trial(opts.case, opts.arm, opts.output, score_only=opts.score_only)
