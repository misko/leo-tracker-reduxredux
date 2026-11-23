"""Run a saved two-child composition check against the already sealed named v3 publication."""

import argparse
from io import BytesIO
import json
from pathlib import Path
import subprocess

from empty_bootstrap import RELEASE, checked
from prospective_0402_solver import ARCHIVE_SHA, INVENTORY_SHA, OFFER_SHA, SETTINGS


HERE = Path(__file__).resolve().parent
STAGE = Path("/dev/shm/leo-v3-saved-0402-pair-01")
REFERENCE = Path("/dev/shm/leo-v3-saved-0402-score-02.json")
REFERENCE_PIN = "9ae7020102cad2356ce7b8beaf5799e421d750bde358dd486b6130558334ddd4"
REQUEST_PIN = "a2d730f64833eafd096877650e24b5c250b3bcfbef69d6bb5a44b70f0cbf1274"
ORDER = ("combined", "fitted-first")


def launch(root):
    from aperture_trial import archive_identity, write
    from dense_geographic_trial import host
    from full_short_physical import environment
    from short_raw_diagnostic import measure

    machine = host()
    if subprocess.check_output(["findmnt", "-no", "FSTYPE", "-T", root.parent], text=True).strip() != "tmpfs":
        raise ValueError("Use fresh tmpfs outputs")
    req = json.loads(checked(STAGE / "request.json", REQUEST_PIN))
    for name, digest in (("named-detections.json", SETTINGS["native_sha"]), ("inventory.json", INVENTORY_SHA),
                         ("operator-offer.json", OFFER_SHA)):
        checked(STAGE / name, digest)
    archive = archive_identity(STAGE / "tle")
    if archive["snapshots_sha256"] != ARCHIVE_SHA:
        raise ValueError("The staged orbit archive differs from the named solver's")
    root.mkdir()
    (root / "tmp").mkdir()
    env = environment(root)
    env["TMPDIR"] = str(root / "tmp")
    python = RELEASE / "venv/bin/python"
    subprocess.run([python, "-Bc", "from matplotlib import font_manager; font_manager.findfont('DejaVu Sans')"],
                   env=env, check=True, timeout=30)
    write(root / "admission.json", dict(machine=machine, archive=archive, order=ORDER, request=REQUEST_PIN,
          packet=SETTINGS["native_sha"], inventory=INVENTORY_SHA, offer=OFFER_SHA))
    for mode in ORDER:
        output = root / mode
        command = [python, "-IB", HERE / "named_constrained_research.py", "--recording", req["recording"],
                   "--archive", STAGE / "tle", "--region", STAGE / "operator-offer.json", "--output", output,
                   "--saved", STAGE / "named-detections.json", "--saved-digest", SETTINGS["native_sha"],
                   "--saved-inventory", STAGE / "inventory.json", "--constrained", "fitted-first"]
        if mode == "combined":
            command.append("--optimized-publication")
        timing = measure(command, env, output)
        write(root / f"{mode}-clock.json", dict(command=list(map(str, command)), timing=timing))
        if timing["exit_code"]:
            raise RuntimeError(timing["stderr_tail"])


def verify(root, output):
    from PIL import Image
    from aperture_trial import read, write
    from joint_publication import artifacts
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
    from local_future_cli_trial import native_packet
    from named_weak_visual import registered_orbits
    from prospective_0155_solver import orbit_legends
    from publication_media_checks import verify_position_sidecars
    from short_raw_diagnostic import pairs

    sealed = json.loads(checked(REFERENCE, REFERENCE_PIN))
    named = sealed["runs"]["stock"]
    runs = {}
    for mode in ORDER:
        target = root / mode
        process = read(root / f"{mode}-clock.json")["timing"]
        run = read(target / "named-weak-exact.json")
        audit = read(target / "named-constrained-research.json")
        pub = run["publication"]
        science = pairs.evidence(target, pub, process["started_unix_ns"], read_only=True)
        figures = json.loads(json.dumps(artifacts(target, pub)["images"]))
        checked(native_packet(target), SETTINGS["native_sha"])
        combined = mode == "combined"
        named_pub = named["science"]["receipt"]
        if (process["exit_code"] or run["acquisition"]["mode"] != "saved" or run["optimized"] != combined
                or audit["optimized_publication"] != combined or audit["publication"] != pub
                or any(pub[k] != named_pub[k] for k in ("terminal_sha256", "decision", "region", "counts", "session_id"))
                or any(science[k] != named["science"][k] for k in ("arms", "owners", "scientific_digests", "raw_authority"))
                or named["selected_rows"] != audit["selected_rows"] or audit["prepared_counts"]["visits"] != 58
                or len(audit["pair_audit"]["rejected_trials"]) != 1 or audit["pair_audit"]["first_arm"] != "fitted_c"
                or any(figures[k]["size"] != previous["size"] for k, previous in named["figures"].items())
                or (not combined and figures != named["figures"])):
            raise ValueError(f"{mode} changed the original publication, owners, constrained route or dimensions")
        legend = None
        if combined:
            work = run["rendering"]["work"]
            if (not run["graph"]["enabled"] or not run["graph"]["graph"].get("calls")
                    or not run["forecast"]["executions"] or not all(e["used"] for e in run["forecast"]["executions"])
                    or work.get("native_orbit_figures") != 4 or work.get("native_residual_figures") != 2):
                raise ValueError("The combined preparation or raster path did not activate")
            legend = orbit_legends(target, dict(worker=dict(layout=run["rendering"], receipt=pub),
                                  selected_rows=audit["selected_rows"], figures=figures))
        runs[mode] = dict(process=process, named=run, research_sha256=audit["research_sha256"], figures=figures,
                          owners=science["owners"], counts={k: len(v) for k, v in audit["selected_rows"].items()},
                          pair=audit["pair_audit"], prepared=audit["prepared_counts"], legend=legend)
    original, combined = runs["fitted-first"], runs["combined"]
    run_id = combined["named"]["publication"]["run_id"]
    docs = verify_position_sidecars(root/"fitted-first", root/"combined", run_id, original["figures"], combined["figures"])
    registration = {}
    for name in combined["legend"]["checked"]:
        images = []
        for mode in ("fitted-first", "combined"):
            store = FastStandardAnalysisStore(root/mode)
            with Image.open(BytesIO(store.artifact(run_id, name, runs[mode]["figures"][name]["sha256"]))) as image:
                images.append(image.convert("RGB"))
        registration[name] = registered_orbits(*images, require_match=False)
    failed_layers = [
        dict(sheet=name, panel=i+1, layer=kind, fraction=layer["fraction"])
        for name, sheet in registration.items() for i, row in enumerate(sheet["rows"])
        for kind, layer in row.items() if layer["fraction"] and min(layer["fraction"]) < .98
    ]
    write(output, dict(case=sealed["case"], admission=read(root/"admission.json"), runs=runs, sidecars=docs,
                       registration=registration, failed_layers=failed_layers, visual_pass=not failed_layers,
                       historical_v3=named["process"], scores=sealed["scores"]["stock"],
                       reference=REFERENCE_PIN))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("launch", "verify"))
    parser.add_argument("root", type=Path)
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args()
    if args.action == "launch":
        launch(args.root)
    elif args.receipt is not None:
        verify(args.root, args.receipt)
    else:
        parser.error("Verification requires --receipt")
