"""Compare both qualified Cairo routes together on the sealed exact weak path."""

import argparse
import gzip
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
JOB = Path("/dev/shm/leo-cumulative-grid-projection-01/weak-pair/binding.json")
JOB_SHA = "d081f501dbff1a13f9426c9109fd7b57ff594b627528ac82607d9c61b8166a3d"
FIGURES = "direct-orbits-corrected.json.gz"
FIGURES_SHA = "7b63475c1e47d7df045bf3f18af8cd518fa4bf0dd0b50017a7ff1dc34f9f1a9c"
MODES = ("control", "cairo")


def worker(job, mode, output):
    from aperture_trial import write
    from cumulative_grid_projection import worker as saved
    import unified_short_bootstrap as cumulative

    publish, png = cumulative.publish_active, {}

    def configured(args, *values, **options):
        args.reuse_verified_png_reads = True
        args.direct_residual_figures = args.direct_orbit_figures = mode == "cairo"
        return publish(args, *values, png_read_audit=png, **options)

    with patch.object(cumulative, "publish_active", configured):
        saved(job, "combined", output)
    write(output / "verified-png-audit.json", png)


def verify(output, mode, timing, expected, expected_figures, request):
    from aperture_trial import read
    from cumulative_grid_projection import proof_fields
    from joint_publication import artifacts
    from leo.contracts.digests import canonical_digest
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
    from local_future_cli_trial import native_packet
    from short_raw_diagnostic import pairs

    worker = read(output / "cumulative-grid-worker.json")
    png = read(output / "verified-png-audit.json")
    research = read(output / "joint-research-receipt.json")
    receipt = worker["receipt"]
    original = pairs.evidence(output, receipt, timing["started_unix_ns"], read_only=True)
    outputs = artifacts(output, receipt)
    store, run_id = FastStandardAnalysisStore(output), receipt["run_id"]
    grid, path = store.position_grid(run_id), store.position_path(run_id)
    (regional,) = research["early_regional"]
    if (receipt["terminal_sha256"] != expected["terminal_sha256"]
            or original["raw_authority"] != request["authority"] or receipt["session_id"] != request["session"]
            or sha256(native_packet(output).read_bytes()).hexdigest() != request["native"][7:]
            or any(original[key] != expected[key] for key in ("arms", "owners", "scientific_digests"))
            or research["selected_rows"] != expected["owner_rows"] or proof_fields(regional) != expected["proof"]
            or not grid["complete"] or grid["evaluated_points"] != 179
            or not worker["graph"]["enabled"] or worker["projection"]["calls"].get("native_selection") != 356
            or worker["waveform_calls"] or worker["handoffs"] != 1):
        raise ValueError("The exact cumulative path or original weak scientific evidence changed")
    figures = outputs["images"]
    if (canonical_digest(figures) != canonical_digest(expected_figures) or len(figures) != 8
            or png.get("verified") != 8 or png.get("reused") != 8 or png.get("fallbacks")):
        raise ValueError("Expected all eight verified mode-specific encoded and decoded figures")
    work = worker["layout"]["work"]
    want = {"native_orbit_figures": 4, "native_residual_figures": 2} if mode == "cairo" else {
        "orbit_figures": 2, "residual_figures": 2}
    if (any(work.get(k) != v for k, v in want.items()) or set(work).intersection(
            ("native_orbit_fallback", "native_residual_fallback", "layout_fallback"))):
        raise ValueError(f"Expected the configured draw path: {work!r}")
    sidecars = {}
    for name, document in (("grid", grid), ("path", path)):
        if document["binding"]["position_png_sha256"] != figures["position"]["sha256"]:
            raise ValueError("Numerical document does not own the published position PNG")
        sidecars[name] = canonical_digest({key: v for key, v in document.items() if key != "elapsed_seconds"})
    return dict(process=timing, worker=worker, media_verification=png, figures=figures, sidecars=sidecars,
                persisted_sidecars={name: outputs[name] for name in sidecars}, proof=proof_fields(regional),
                science={key: original[key] for key in ("arms", "owners", "scientific_digests")},
                owner_roles_sha256=canonical_digest(research["selected_rows"]))


def run(root, admission):
    from aperture_trial import archive_identity, read, write
    from cumulative_grid_projection import enrolled
    from dense_geographic_trial import host
    from empty_bootstrap import RELEASE, checked
    from full_short_physical import environment
    from short_raw_diagnostic import measure

    machine = host()
    if subprocess.check_output(["findmnt", "-no", "FSTYPE", "-T", root.parent], text=True).strip() != "tmpfs":
        raise ValueError("Require private tmpfs publication output")
    approved = read(admission)
    request, packet, expected = enrolled("weak")
    binding = json.loads(checked(JOB, JOB_SHA))
    if (approved["raw_admissible"] or approved["warmed_pages"] or approved["waveform_reads"]
            or any(approved[k] != request[k] for k in ("recording", "session", "inventory"))
            or request != {key: binding[key] for key in request}
            or sha256(packet.read_bytes()).hexdigest() != request["native"][7:]
            or archive_identity(Path(request["archive"]["root"])) != request["archive"]):
        raise ValueError("Expected the preserved cold reading and original unfiltered DS30-0016 handoff")
    corrected = json.loads(gzip.decompress(checked(HERE / "measurements" / FIGURES, FIGURES_SHA)))
    expected_figures = {"control": expected["figures"], "cairo": corrected["figures"]}
    root.mkdir()
    (root / "tmp").mkdir()
    job = root / "binding.json"
    write(job, binding)
    env = environment(root)
    env["TMPDIR"] = str(root / "tmp")
    python = RELEASE / "venv/bin/python"
    subprocess.run([python, "-Bc", "from matplotlib import font_manager; font_manager.findfont('DejaVu Sans')"],
                   env=env, check=True, timeout=30)
    runs = {}
    for mode in MODES:
        output = root / mode
        command = [python, "-IB", __file__, "worker", job, mode, output]
        timing = measure(command, env, output)
        write(root / f"{mode}-clock.json", timing)
        if timing["exit_code"]:
            raise RuntimeError(timing["stderr_tail"])
        runs[mode] = verify(output, mode, timing, expected, expected_figures[mode], request)
        write(root / f"{mode}-verified.json", runs[mode])
    if runs["control"]["sidecars"] != runs["cairo"]["sidecars"]:
        raise ValueError("Scientific sidecar fields differ")
    changed = [name for name, first in runs["control"]["figures"].items() if first != runs["cairo"]["figures"][name]]
    if len(changed) != 6 or set(changed).intersection(("position", "track-rms")):
        raise ValueError("Only the six specified Cairo sheets should change raster")
    sources = ("weak-cairo-combined-protocol.md", "weak_cairo_combined.py", "unified_short_bootstrap.py",
               "direct_orbit_entry.py", "direct_orbit_figures.py", "direct_residual_entry.py", "direct_residual_figures.py")
    write(root / "result.json", dict(case="DS30-0016", order=MODES, machine=machine, admission=approved,
          signed_inputs=binding, raw_runs=0, waveform_reads=0, runs=runs, changed_images=changed,
          prior_cairo_receipt_sha256=FIGURES_SHA, staged_binding_sha256=JOB_SHA,
          source_sha256={name: sha256((HERE / name).read_bytes()).hexdigest() for name in sources}))


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
        parser.add_argument("admission", type=Path)
        run(**vars(parser.parse_args()))
