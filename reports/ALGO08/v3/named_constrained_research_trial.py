"""Run and verify the single frozen saved transfer of the generic named CLI."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import subprocess

from empty_bootstrap import RELEASE, checked


HERE = Path(__file__).resolve().parent
STAGE = Path("/dev/shm/leo-v3-saved-0155-pair-01")
REFERENCE = Path("/dev/shm/leo-v3-saved-0155-result.json")
REFERENCE_PIN = "63efc82d3c0fa0889f3c85e630ddb427f041b6174a7c9f175676c1f0fec64d75"
REQUEST_PIN = "c0533ae6b92b66593d59a2f9a7aaf2b64194563c18ef8038ec2afdfc66c1da79"
NATIVE_PIN = "d7f52f2ad771cd17dc3434548bb079e3cd1552b22f390949da6eef9993f4d0d3"
INVENTORY_PIN = "2e52b6ce8091e0bd8c39a44d8d847c65402b487091a7102beb0b847b377ffbb6"
OFFER_PIN = "2698d6858da0a2d989d8c2185c9e3bbbba20d539988204c1f93a591eb9471236"
ARCHIVE_PIN = "sha256:8ea284d7b0d6aab59dec80477ada3e1cbddb59c44714ebb103c047fa12de839e"
ORDER = ("stock", "fitted-first")


def enrollment():
    from aperture_trial import archive_identity
    from leo.contracts.digests import canonical_digest

    req = json.loads(checked(STAGE / "request.json", REQUEST_PIN))
    native = json.loads(checked(STAGE / "named-detections.json", NATIVE_PIN))
    inv = json.loads(checked(STAGE / "inventory.json", INVENTORY_PIN))
    checked(STAGE / "operator-offer.json", OFFER_PIN)
    archive = archive_identity(STAGE / "tle")
    if (archive["snapshots_sha256"] != ARCHIVE_PIN or canonical_digest(inv) != req["inventory"]
            or inv["window_count"] != 6773 or native["provenance"]["processed_windows"] != 6179
            or native["clock_anchor"]["before"]["realtime_ns"] != req["causal_cutoff_utc_ns"]
            or native["source"]["raw_recording_authority_digest"] != req["raw_authority"]):
        raise ValueError("The frozen named enrollment changed")
    return req, archive


def launch(root):
    from aperture_trial import write
    from dense_geographic_trial import host
    from full_short_physical import environment
    from short_raw_diagnostic import measure

    machine = host()
    if subprocess.check_output(["findmnt", "-no", "FSTYPE", "-T", root.parent], text=True).strip() != "tmpfs":
        raise ValueError("Use one fresh private tmpfs output")
    req, archive = enrollment()
    root.mkdir()
    (root / "tmp").mkdir()
    env = environment(root)
    env["TMPDIR"] = str(root / "tmp")
    python = RELEASE / "venv/bin/python"
    subprocess.run([python, "-Bc", "from matplotlib import font_manager; font_manager.findfont('DejaVu Sans')"],
                   env=env, check=True, timeout=20)
    source = tuple(HERE / name for name in (
        "constrained-research-cli-protocol.md", "named_constrained_research_trial.py",
        "named_constrained_research.py", "prepared_constrained_checks.py", "constrained_pair_veto.py",
    ))
    write(root / "admission.json", dict(case=req["case"], machine=machine, archive=archive, order=ORDER,
          inputs=dict(request=REQUEST_PIN, native=NATIVE_PIN, inventory=INVENTORY_PIN, offer=OFFER_PIN),
          source={path.name: sha256(path.read_bytes()).hexdigest() for path in source}))
    for mode in ORDER:
        output = root / mode
        command = [python, "-IB", HERE / "named_constrained_research.py",
                   "--recording", req["recording"], "--archive", archive["root"],
                   "--region", STAGE / "operator-offer.json", "--output", output,
                   "--saved", STAGE / "named-detections.json", "--saved-digest", NATIVE_PIN,
                   "--saved-inventory", STAGE / "inventory.json"]
        if mode != "stock":
            command.extend(("--constrained", mode))
        clock = measure(command, env, output)
        write(root / f"{mode}-clock.json", dict(timing=clock, command=list(map(str, command))))
        if clock["exit_code"]:
            raise RuntimeError(f"{mode} failed. Process clock and logs were sealed.")


def verify(root, destination):
    from aperture_trial import read, write
    from joint_publication import artifacts
    from leo.contracts.digests import canonical_digest
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
    from local_future_cli_trial import native_packet
    from short_raw_diagnostic import pairs

    req, _ = enrollment()
    reference = json.loads(checked(REFERENCE, REFERENCE_PIN))
    historical = reference["runs"]["stock"]
    runs = {}
    for mode in ORDER:
        output = root / mode
        external = read(root / f"{mode}-clock.json")
        trace = read(output / "named-weak-exact.json")
        audit = read(output / "named-constrained-research.json")
        pub = trace["publication"]
        evidence = pairs.evidence(output, pub, external["timing"]["started_unix_ns"], read_only=True)
        visual = json.loads(json.dumps(artifacts(output, pub)))
        store = FastStandardAnalysisStore(output)
        grid, path = store.position_grid(pub["run_id"]), store.position_path(pub["run_id"])
        science = ("arms", "owners", "scientific_digests", "raw_authority")
        named_basis = historical["science"]["receipt"]
        if (external["timing"]["exit_code"] or trace["acquisition"]["mode"] != "saved"
                or trace["optimized"] or trace["graph"]["enabled"] or pub["decision"] != "complete"
                or any(pub[key] != named_basis[key] for key in ("terminal_sha256", "counts", "region", "session_id"))
                or any(evidence[key] != historical["science"][key] for key in science)
                or audit["selected_rows"] != historical["selected_rows"]
                or audit["mode"] != mode or audit["detector_sha256"] != "sha256:"+trace["detector_sha256"]
                or audit["named_input_sha256"] != "sha256:"+NATIVE_PIN or audit["raw_authority"] != req["raw_authority"]
                or audit["publication"] != pub or audit["named_specification"] != trace["frozen_specification"]
                or audit["prepared_counts"] or not audit["nominations"]
                or any(row["status"] != "complete" or row["positive_offers"] for row in audit["nominations"])
                or not grid["complete"] or grid["evaluated_points"] != 179 or len(visual["images"]) != 8
                or any(doc["binding"]["position_png_sha256"] != visual["images"]["position"]["sha256"]
                       for doc in (grid, path))):
            raise ValueError(f"{mode} changed named science, source identity, no-offer behavior or web evidence")
        checked(native_packet(output), NATIVE_PIN)
        computed = audit.pop("selected_rows")
        if mode == "stock":
            if audit["first_arm"] is not None or audit["prepared_release_sources"] or audit["pair_audit"]:
                raise ValueError("The default enabled candidate code")
        elif (audit["first_arm"] != "fitted_c" or not audit["prepared_release_sources"]
              or audit["pair_audit"]["first_arm"] != "fitted_c" or audit["pair_audit"]["rescues"]
              or audit["pair_audit"]["rejected_trials"] or audit["pair_audit"]["second_arms_started"]):
            raise ValueError("The fitted-first option did not bind a no-offer zero-work policy")
        runs[mode] = dict(process=external, named=trace, research=audit, visual=visual,
                          science={key: evidence[key] for key in science}, grid_points=grid["evaluated_points"],
                          grid_elapsed_seconds=grid["elapsed_seconds"],
                          grid_without_elapsed_sha256=canonical_digest({
                              key: value for key, value in grid.items() if key != "elapsed_seconds"
                          }),
                          owners={arm: len(rows) for arm, rows in computed.items()},
                          own_receipt_sha256=sha256((output / "named-constrained-research.json").read_bytes()).hexdigest(),
                          historical_pngs_identical=visual["images"] == historical["figures"])
    stock, fitted = (runs[mode] for mode in ORDER)
    if (stock["visual"]["path"] != fitted["visual"]["path"] or stock["visual"]["images"] != fitted["visual"]["images"]
            or stock["grid_without_elapsed_sha256"] != fitted["grid_without_elapsed_sha256"]
            or stock["research"]["research_sha256"] == fitted["research"]["research_sha256"]):
        raise ValueError("The option must preserve web evidence and keep separate research provenance")
    write(destination, dict(admission=read(root / "admission.json"), reference_sha256=REFERENCE_PIN,
                            equal_ordered_owners=True, equal_web_evidence=True, runs=runs, scores=reference["scores"]["stock"]))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("launch", "verify"))
    parser.add_argument("output", type=Path)
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args()
    if args.action == "launch":
        launch(args.output)
    elif args.receipt is not None:
        verify(args.output, args.receipt)
    else:
        parser.error("--receipt is required for verification")
