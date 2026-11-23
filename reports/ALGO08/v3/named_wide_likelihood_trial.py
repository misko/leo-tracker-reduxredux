"""Measure one matched named CLI pair on the staged independent DS30-0316 input."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import subprocess

from empty_bootstrap import RELEASE, checked


HERE = Path(__file__).resolve().parent
STAGE = Path("/dev/shm/leo-v3-saved-0316-pair-01")
ORDER = ("stock", "wider")
PINS = dict(request="e1e3d9cd482bc4b8837f782c329702472b60e34eba8616616b5ec20ef759b739",
            native="6bbbb2575df6a203dd0d183a3ad8390110fbac778504803e275b7493b8422bed",
            inventory="061f319935b349c7d5edc858adb0a9827d95d1d87c48a5b8786a2068fe98b595",
            offer="2698d6858da0a2d989d8c2185c9e3bbbba20d539988204c1f93a591eb9471236",
            reference="39be27ab7fee47b6db239207e23bcf7a53d99e1ea65fe269dd607ef0c3958b1a",
            archive="sha256:2b0884d96825e99d15d46036f1dee00620351a9665ab6511dfd5e9ada47811a6")


def enrollment():
    from aperture_trial import archive_identity
    from leo.contracts.digests import canonical_digest

    request = json.loads(checked(STAGE / "request.json", PINS["request"]))
    inventory = STAGE / "stock/fast-scan-inputs" / (request["session"] + ".json")
    manifest = json.loads(checked(inventory, PINS["inventory"]))
    native = json.loads(checked(STAGE / "named-detections.json", PINS["native"]))
    checked(STAGE / "operator-offer.json", PINS["offer"])
    archive = archive_identity(STAGE / "tle")
    if (request["case"] != "DS30-0316" or archive["snapshots_sha256"] != PINS["archive"]
            or archive["root"] != request["local_archive"]["root"]
            or manifest["window_count"] != 3042 or native["provenance"]["processed_windows"] != 2702
            or canonical_digest(manifest) != request["inventory"]
            or native["source"]["raw_recording_authority_digest"] != request["raw_authority"]
            or native["clock_anchor"]["before"]["realtime_ns"] != request["causal_cutoff_utc_ns"]):
        raise ValueError("Original signed saved inputs changed")
    return request, archive, inventory


def launch(root):
    from aperture_trial import write
    from dense_geographic_trial import host
    from full_short_physical import environment
    from short_raw_diagnostic import measure

    machine = host()
    if root.absolute() != root.resolve() or not root.is_relative_to("/dev/shm"):
        raise ValueError("Use fresh private tmpfs output and scratch")
    request, archive, inventory = enrollment()
    root.mkdir()
    (root / "tmp").mkdir()
    env = environment(root)
    env["TMPDIR"] = str(root / "tmp")
    python = RELEASE / "venv/bin/python"
    subprocess.run([python, "-Bc", "from matplotlib import font_manager; font_manager.findfont('DejaVu Sans')"],
                   env=env, check=True, timeout=20)
    compilation = measure([python, "-IB", HERE / "named_wide_likelihood.py", root / "library"], env, root / "build")
    write(root / "build-clock.json", compilation)
    if compilation["exit_code"]:
        raise RuntimeError(compilation["stderr_tail"])
    library = root / "library/private_width.so"
    binary_pin = sha256(library.read_bytes()).hexdigest()
    sources = (HERE / "named-wide-likelihood-protocol.md", Path(__file__), HERE / "named_constrained_research.py",
               HERE / "named_wide_likelihood.py")
    write(root / "admission.json", dict(case=request["case"], inputs=PINS, machine=machine, archive=archive, order=ORDER,
          binary_sha256=binary_pin, sources={p.name: sha256(p.read_bytes()).hexdigest() for p in sources}))
    for mode in ORDER:
        output = root / mode
        command = [python, "-IB", HERE / "named_constrained_research.py", "--recording", request["recording"],
                   "--archive", archive["root"], "--region", STAGE / "operator-offer.json", "--output", output,
                   "--saved", STAGE / "named-detections.json", "--saved-digest", PINS["native"], "--saved-inventory", inventory]
        if mode == "wider":
            command.extend(("--wide-private-likelihood", library, "--wide-private-likelihood-sha256", binary_pin))
        clock = measure(command, env, output)
        write(root / f"{mode}-clock.json", dict(timing=clock, command=list(map(str, command))))
        if clock["exit_code"]:
            raise RuntimeError(clock["stderr_tail"])


def verify(root, destination):
    from aperture_trial import read, write
    from joint_publication import artifacts
    from leo.contracts.digests import canonical_digest
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
    from local_future_cli_trial import native_packet
    from short_raw_diagnostic import pairs

    request, _, _ = enrollment()
    reference = json.loads(checked(STAGE / "result.json", PINS["reference"]))
    named = reference["runs"]["stock"]
    admission = read(root / "admission.json")
    runs = {}
    for mode in ORDER:
        output = root / mode
        external = read(root / f"{mode}-clock.json")
        trace, audit = (read(output / key) for key in ("named-weak-exact.json", "named-constrained-research.json"))
        receipt = trace["publication"]
        science = pairs.evidence(output, receipt, external["timing"]["started_unix_ns"], read_only=True)
        figures = json.loads(json.dumps(artifacts(output, receipt)["images"]))
        store = FastStandardAnalysisStore(output)
        documents = {"grid": store.position_grid(receipt["run_id"]), "path": store.position_path(receipt["run_id"])}
        sidecars = {name: dict(position_png_sha256=body["binding"]["position_png_sha256"],
                              scientific_sha256=canonical_digest({k: v for k, v in body.items()
                                  if k not in ("binding", "elapsed_seconds")})) for name, body in documents.items()}
        keys = ("arms", "owners", "scientific_digests", "raw_authority")
        if (external["timing"]["exit_code"] or trace["acquisition"]["mode"] != "saved" or trace["optimized"]
                or trace["graph"]["enabled"] or receipt["decision"] != "complete" or audit["mode"] != "stock"
                or receipt["terminal_sha256"] != named["science"]["receipt"]["terminal_sha256"]
                or any(science[k] != named["science"][k] for k in keys)
                or audit["selected_rows"] != named["selected_rows"] or audit["raw_authority"] != request["raw_authority"]
                or audit["publication"] != receipt or figures != named["figures"] or len(figures) != 8
                or sidecars != named["sidecars"] or not documents["grid"]["complete"]
                or any(body["position_png_sha256"] != figures["position"]["sha256"] for body in sidecars.values())):
            raise ValueError(f"{mode} changed the signed named numerical or media evidence")
        checked(native_packet(output), PINS["native"])
        wide = audit.get("wide_private_likelihood")
        if (mode == "stock" and wide is not None) or (mode == "wider" and (
                wide is None or not wide["inferences"] or wide["stock_selected_packets"] != 1
                or wide["library_sha256"] != "sha256:" + admission["binary_sha256"]
                or wide["attempts"] != wide["counts"].get("calls", 0)
                or wide["activations"] != wide["counts"].get("activated", 0))):
            raise ValueError("Expected the stock default and one verified opt-in inference")
        rows = audit.pop("selected_rows")
        runs[mode] = dict(process=external, named=trace, research=audit, science={k: science[k] for k in keys},
                          figures=figures, sidecars=sidecars, grid_points=documents["grid"]["evaluated_points"],
                          owners={arm: dict(count=len(v), sha256=canonical_digest(v)) for arm, v in rows.items()})
    if runs["stock"]["research"]["research_sha256"] == runs["wider"]["research"]["research_sha256"]:
        raise ValueError("The opt-in library must have distinct research provenance")
    write(destination, dict(admission=admission, build=read(root / "build-clock.json"),
          library_manifest=read(root / "library/manifest.json"), runs=runs,
          scores={k: reference["scores"][k]["stock"] for k in ("horizontal_error_km", "rf_rms_hz")},
          equal_science_and_media=True, waveform_calls=0))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="mode", required=True)
    for mode in ("launch", "verify"):
        command = sub.add_parser(mode)
        command.add_argument("root", type=Path)
        if mode == "verify":
            command.add_argument("destination", type=Path)
    options = parser.parse_args()
    if options.mode == "launch":
        launch(options.root)
    else:
        verify(options.root, options.destination)
