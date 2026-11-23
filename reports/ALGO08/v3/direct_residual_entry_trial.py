"""Measure the candidate-only residual renderer through the complete saved entry."""

import argparse
import gzip
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
MODES = ("control", "native")
REFERENCE_PIN = "3358c1dd2be21370606518fb770e39119cbf0cc26a39d1cba6a629d69688daec"


def worker(job, mode, output):
    from cumulative_grid_projection import worker as saved_publication
    import unified_short_bootstrap as entry

    publish = entry.publish_active

    def opted_in(args, *values, **options):
        args.direct_residual_figures = mode == "native"
        return publish(args, *values, **options)

    with patch.object(entry, "publish_active", opted_in):
        saved_publication(job, "installed", output)


def reference():
    from empty_bootstrap import checked

    blob = checked(HERE / "measurements/direct-residual-figures-DS30-0016.json.gz", REFERENCE_PIN)
    witness = json.loads(gzip.decompress(blob))
    checked(HERE / "direct_residual_figures.py", witness["source_sha256"]["direct_residual_figures.py"])
    return witness


def verify(output, timing, native, expected, witness):
    from aperture_trial import read
    from cumulative_grid_projection import proof_fields
    from joint_publication import artifacts
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
    from short_raw_diagnostic import pairs

    worker_proof = read(output / "cumulative-grid-worker.json")
    research = read(output / "joint-research-receipt.json")
    receipt = worker_proof["receipt"]
    evidence = pairs.evidence(output, receipt, timing["started_unix_ns"], read_only=True)
    figures = artifacts(output, receipt)["images"]
    layout = worker_proof["layout"]["work"]
    store = FastStandardAnalysisStore(output)
    grid = store.position_grid(receipt["run_id"])
    (regional,) = research["early_regional"]
    if (receipt["terminal_sha256"] != expected["terminal_sha256"]
            or any(evidence[key] != expected[key] for key in ("arms", "owners", "scientific_digests"))
            or research["selected_rows"] != expected["owner_rows"] or proof_fields(regional) != expected["proof"]
            or worker_proof["waveform_calls"] != 0 or worker_proof["handoffs"] != 1
            or worker_proof["graph"]["enabled"] or worker_proof["projection"] is not None
            or not grid["complete"] or grid["evaluated_points"] != 179 or len(figures) != 8):
        raise ValueError(f"{output.name} changed the original signed publication")
    if (native and (layout.get("native_residual_figures") != 2 or layout.get("residual_figures", 0)
                    or "native_residual_fallback" in layout)
            or not native and (layout.get("residual_figures") != 2 or "native_residual_figures" in layout)):
        raise ValueError(f"{output.name} used the wrong renderer route: {layout}")

    for name, figure in json.loads(json.dumps(figures)).items():
        known = (witness["images"] if native else expected["figures"])[name]
        if figure != known:
            raise ValueError(f"{output.name} failed the file and decoded-pixel binding for {name}")
        if name in witness["render"]["candidate"]:
            comparison = witness["render"]["candidate"][name]
            checked_pixels = comparison["media"]["candidate_rgba_sha256" if native else "stock_rgba_sha256"]
            if figure["rgba_sha256"] != checked_pixels or comparison["science"]["axis_tick_sets"] != 16:
                raise ValueError("The published residual differs from the original axis and scatter qualification")
    for name in ("grid", "path"):
        precise = getattr(store, "position_" + name)(receipt["run_id"])
        if precise["binding"]["position_png_sha256"] != figures["position"]["sha256"]:
            raise ValueError("The numerical sidecar no longer identifies its official position figure")
    return dict(worker=worker_proof, science=evidence, figures=figures, process=timing)


def run(root):
    from aperture_trial import RELEASE, archive_identity, write
    from combined_frontier_run import BLOCK_SHA
    from cumulative_grid_projection import enrolled
    from dense_geographic_trial import host
    from empty_bootstrap import checked
    from full_short_physical import environment
    from full_short_run import GEOGRAPHIC_SHA, TRACK_SCORES_SHA
    from short_raw_diagnostic import measure
    from unified_short_bootstrap import LAYOUT_SHA256

    machine = host()
    if subprocess.check_output(["findmnt", "-no", "FSTYPE", "-T", root.parent], text=True).strip() != "tmpfs":
        raise ValueError("Use a fresh private tmpfs parent")
    witness = reference()
    request, packet, expected = enrolled("weak")
    data = checked(packet, request["native"].removeprefix("sha256:"))
    source = json.loads(data)
    if archive_identity(Path(request["archive"]["root"])) != request["archive"]:
        raise ValueError("The original causal archive changed")
    for path, pin in zip(request["libraries"].values(), (GEOGRAPHIC_SHA, TRACK_SCORES_SHA, BLOCK_SHA), strict=True):
        checked(Path(path), pin)
    checked(HERE / "one_pass_web_png.py", LAYOUT_SHA256)
    root.mkdir()
    (root / "tmp").mkdir()
    local = root / "detections.json"
    local.write_bytes(data)
    request.update(packet=str(local), cutoff_utc_ns=source["clock_anchor"]["before"]["realtime_ns"])
    job = root / "binding.json"
    write(job, request)
    env, python = environment(root), RELEASE / "venv/bin/python"
    env["TMPDIR"] = str(root / "tmp")
    subprocess.run([python, "-Bc", "from matplotlib import font_manager; font_manager.findfont('DejaVu Sans')"],
                   check=True, env=env, timeout=30)

    clocks = {}
    for mode in MODES:
        output = root / mode
        clocks[mode] = measure([python, "-IB", __file__, "worker", job, mode, output], env, output)
        write(root / f"{mode}-clock.json", clocks[mode])
        if clocks[mode]["exit_code"]:
            raise RuntimeError(clocks[mode]["stderr_tail"])
    runs = {mode: verify(root / mode, clocks[mode], mode == "native", expected, witness) for mode in MODES}
    write(root / "result.json", dict(case="DS30-0016", machine=machine, order=MODES, inputs=request,
          runs=runs, reference_sha256=REFERENCE_PIN, reference_semantics={
              name: info["science"] for name, info in witness["render"]["candidate"].items()
          }, source_sha256={name: sha256((HERE / name).read_bytes()).hexdigest() for name in (
              "direct_residual_entry.py", "direct_residual_entry_trial.py", "direct_residual_figures.py",
              "unified_short_bootstrap.py", "direct-residual-entry-protocol.md",
          )}))


if __name__ == "__main__":
    sys.path.insert(0, str(HERE))
    parser = argparse.ArgumentParser(description=__doc__)
    if sys.argv[1:2] == ["worker"]:
        parser.add_argument("job", type=Path)
        parser.add_argument("mode", choices=MODES)
        parser.add_argument("output", type=Path)
        worker(**vars(parser.parse_args(sys.argv[2:])))
    else:
        parser.add_argument("root", type=Path)
        run(parser.parse_args().root)
