"""Verify the exact raw entry on the already-staged complete DS30-0107 input."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))


def launch(root):
    from continued_cfo_small_raw import CASE, INPUTS, RECORDING, input_inventory, residency
    from dense_geographic_trial import host
    from eight_ms_0107_pair import NORTH, archived, is_resident, verified_scope
    from eight_ms_south_transfer import environment_for
    from empty_bootstrap import checked
    from exact_named_raw import write
    from guarded_cfo_small_raw import PRIOR, PRIOR_RESULT, PRIOR_SEAL
    from portable_orbit_index_trial import local_launcher_tools

    local_launcher_tools()
    from short_raw_diagnostic import measure
    from tools.pipeline_eval.qualification.paired_publication import archive_identity

    machine = host()
    verified_scope(PRIOR/RECORDING.name, RECORDING)
    previous = json.loads(checked(PRIOR/"result.json", PRIOR_RESULT))
    checked(PRIOR/"prediction-seal.json", PRIOR_SEAL)
    archive, offer = PRIOR/"tle", PRIOR/"offer.json"
    old = previous["admission"]
    checked(offer, old["offer_sha256"])
    session, members = input_inventory()
    if (old["session"] != session or old["case"] != CASE.id or old["inventory"] != INPUTS.inventory
            or archive_identity(archive)["snapshots_sha256"] != INPUTS.archive
            or any({"path": str(p), "bytes": size, "sha256": digest} != old["members"][kind]
                   for kind, (p, size, digest) in members.items())):
        raise ValueError("Expected the exact complete physical tmpfs stage")

    north = archived(NORTH)["raw_binding"]
    for row in north["libraries"].values():
        checked(Path(row["path"]), row["sha256"])
    original = archived(("eight-ms-0107-pair.json.gz",
                         "2cf87dd38df076e00ac1bc555a38cb4bd57e65f5404800897bbfaddb149a6b3e"))
    expected = original["documents"]["post-verification.json"]["modes"]
    command = ["/usr/bin/timeout", "--kill-after=2s", "15s", sys.executable, "-IB",
               str(HERE/"exact_named_raw.py"), "--recording", str(RECORDING), "--archive", str(archive),
               "--region", str(offer), "--output", str(root/"candidate"), "--archive-sha256", INPUTS.archive]
    for key in ("--short-binary", "--geographic-library", "--regional-track-library", "--frontier-block-library"):
        command.extend((key, north["libraries"][key]["path"]))
    root.mkdir()
    (root/"tmp").mkdir()
    before = residency(members)
    if not is_resident(before):
        raise ValueError("All authenticated physical members must be resident before launch")
    write(root/"binding.json", dict(case=CASE.id, command=command, machine=machine, inputs=old["members"],
        stage=str(PRIOR/RECORDING.name), archive=INPUTS.archive, offer_sha256=old["offer_sha256"], prior=PRIOR_RESULT,
        source=sha256((HERE/"exact_named_raw.py").read_bytes()).hexdigest(), cache_before=before))
    clock = measure(command, environment_for(root), root/"candidate")
    after = residency(members)
    write(root/"clock.json", dict(candidate=clock, cache_after=after))
    if clock["exit_code"] or not is_resident(after):
        raise ValueError(f"The resident physical withhold failed: {clock['stderr_tail']}")
    output = root/"candidate"
    raw = json.loads((output/"unified-short-bootstrap.json").read_bytes())
    detail = json.loads((output/"exact-named-raw-witness.json").read_bytes())
    receipt = raw["receipt"]
    terminal, = output.glob("fast-scan-automatic-work/*/terminal.json")
    signed = json.loads(terminal.read_bytes())
    prior = expected["candidate"]
    if (receipt["decision"] != "withheld" or signed["reason"] != "no_active_curvature"
            or raw["native_sha256"] != prior["native_sha256"]
            or receipt["terminal_sha256"] != prior["science"]["receipt"]["terminal_sha256"]
            or raw["causal_cutoff_utc_ns"] != INPUTS.cutoff_ns
            or raw["raw_acquisitions"] != 1 or raw["verified_handoffs"] != 1
            or detail["ports"] is not None or raw["scientific_imports_after"]
            or raw["graph_proof"] != prior["bootstrap"]["graph_proof"]
            or set(signed["arms"]) != {"c0", "fitted_c"}
            or any(row["latlon"] is not None or row.get("rf_rms_hz") is not None for row in signed["arms"].values())
            or any(file.suffix == ".png" or file.name in ("position-grid.json", "position-path.json")
                   for file in output.rglob("*") if file.is_file())):
        raise ValueError("The physical entry changed the archived authenticated early withhold")
    write(root/"verified-result.json", dict(receipt=receipt, native_sha256=raw["native_sha256"],
          clock=clock, candidate_phases=raw["phases"], terminal=signed, proof=raw["graph_proof"],
          candidate_receiver=raw["receiver_audit"], evidence=detail,
          prior_named=expected["stock"]["process"]["clock"], cache_before=before, cache_after=after,
          binding_sha256=sha256((root/"binding.json").read_bytes()).hexdigest()))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    launch(parser.parse_args().root)
